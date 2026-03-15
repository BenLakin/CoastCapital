"""
schema_sync.py — dbt-style automatic schema evolution for ingestion tables.

Implements the equivalent of dbt's ``on_schema_change='append_new_columns'``
for the silver-layer ingest.  When a new column appears in the ingestion data
dict, it is automatically added to the target table before the row is inserted.

Usage::

    from ingestion.schema_sync import dynamic_upsert

    dynamic_upsert(cursor, "nfl_silver", "fact_game_results", {
        "game_id": "401547417",
        "game_date": "2024-01-15T20:15Z",
        "home_team": "Kansas City Chiefs",
        "new_column": some_value,   # ← auto-added to table
    })
"""

import logging
from datetime import date, datetime
from decimal import Decimal

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level column cache  (schema, table) → set[column_name]
# Avoids repeated INFORMATION_SCHEMA queries within a single process run.
# ---------------------------------------------------------------------------
_column_cache: dict[tuple[str, str], set[str]] = {}


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

def _infer_mysql_type(value) -> str:
    """Infer a MySQL column definition from a Python value.

    Used when a previously unseen column is discovered during ingestion and
    must be added to the table via ``ALTER TABLE``.  Falls back to
    ``VARCHAR(200)`` when the value is ``None``.
    """
    if value is None:
        return "VARCHAR(200)"
    if isinstance(value, bool):
        return "TINYINT"
    if isinstance(value, int):
        if abs(value) > 2_147_483_647:
            return "BIGINT"
        return "INT"
    if isinstance(value, float):
        return "DOUBLE"
    if isinstance(value, Decimal):
        return "DECIMAL(10,4)"
    if isinstance(value, datetime):
        return "DATETIME"
    if isinstance(value, date):
        return "DATE"
    if isinstance(value, str):
        length = max(len(value) * 2, 100)
        return f"VARCHAR({min(length, 500)})"
    return "TEXT"


# ---------------------------------------------------------------------------
# Column synchronisation
# ---------------------------------------------------------------------------

def _table_exists(cursor, schema: str, table: str) -> bool:
    """Return True if *schema.table* exists."""
    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
        (schema, table),
    )
    return cursor.fetchone()[0] > 0


def _create_table(cursor, schema: str, table: str, data: dict) -> None:
    """Create *schema.table* from the keys/values in *data*.

    The first key in *data* is used as the primary key.  All column types
    are inferred from the Python values via ``_infer_mysql_type``.
    """
    columns = list(data.keys())
    col_defs = []
    for col in columns:
        col_type = _infer_mysql_type(data[col])
        col_defs.append(f"`{col}` {col_type}")

    pk = columns[0]
    col_defs_str = ",\n  ".join(col_defs)
    sql = (
        f"CREATE TABLE `{schema}`.`{table}` (\n"
        f"  {col_defs_str},\n"
        f"  PRIMARY KEY (`{pk}`)\n"
        f") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
    )
    cursor.execute(sql)
    logger.info("schema_sync: created table %s.%s (%d columns)", schema, table, len(columns))

    # Prime the column cache
    _column_cache[(schema, table)] = set(columns)


def _get_existing_columns(cursor, schema: str, table: str) -> set[str]:
    """Return the set of column names for *schema.table*, with caching."""
    key = (schema, table)
    if key not in _column_cache:
        cursor.execute(
            "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
            (schema, table),
        )
        _column_cache[key] = {row[0] for row in cursor.fetchall()}
    return _column_cache[key]


def sync_columns(cursor, schema: str, table: str, data: dict) -> list[str]:
    """Ensure every key in *data* exists as a column on *schema.table*.

    Mirrors dbt's ``on_schema_change='append_new_columns'``: any column
    present in the incoming data but missing from the table is added via
    ``ALTER TABLE ADD COLUMN`` with a type inferred from the Python value.

    Returns
    -------
    list of newly added column names.
    """
    existing = _get_existing_columns(cursor, schema, table)
    added: list[str] = []

    for col, val in data.items():
        if col not in existing:
            col_type = _infer_mysql_type(val)
            alter_sql = (
                f"ALTER TABLE `{schema}`.`{table}` "
                f"ADD COLUMN `{col}` {col_type}"
            )
            try:
                cursor.execute(alter_sql)
                existing.add(col)
                added.append(col)
                logger.info(
                    "schema_sync: added column %s.%s.%s (%s)",
                    schema, table, col, col_type,
                )
            except Exception as exc:
                logger.error(
                    "schema_sync: failed to add %s.%s.%s — %s",
                    schema, table, col, exc,
                )

    return added


# ---------------------------------------------------------------------------
# Dynamic upsert
# ---------------------------------------------------------------------------

def dynamic_upsert(
    cursor,
    schema: str,
    table: str,
    data: dict,
    on_duplicate_update: bool = True,
) -> None:
    """Insert a row into *table*, auto-adding any missing columns first.

    Implements the dbt incremental-model pattern: new columns in *data*
    that do not yet exist on the target table are added via ``ALTER TABLE``
    before the ``INSERT`` is executed.

    Parameters
    ----------
    cursor :
        Active MySQL cursor whose default database matches *schema*.
    schema :
        Database schema name (used only for the ``INFORMATION_SCHEMA`` lookup).
    table :
        Target table name.
    data :
        Column → value mapping for the row.
    on_duplicate_update :
        If ``True`` (default), append ``ON DUPLICATE KEY UPDATE`` for every
        column in *data* (standard upsert pattern).  Set to ``False`` for
        append-only tables such as ``fact_market_odds``.
    """
    if not _table_exists(cursor, schema, table):
        _create_table(cursor, schema, table, data)
    else:
        sync_columns(cursor, schema, table, data)

    columns = list(data.keys())
    col_list = ", ".join(f"`{c}`" for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))

    sql = f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders})"

    if on_duplicate_update and columns:
        update_clause = ", ".join(
            f"`{c}` = VALUES(`{c}`)" for c in columns
        )
        sql += f" ON DUPLICATE KEY UPDATE {update_clause}"

    cursor.execute(sql, tuple(data.values()))


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def clear_cache() -> None:
    """Clear the column cache.

    Call between pipeline runs or after external schema changes so the
    next ``sync_columns`` call re-reads ``INFORMATION_SCHEMA``.
    """
    _column_cache.clear()
