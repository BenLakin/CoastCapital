"""
migrate_columns.py — Apply incremental column migrations to all schemas.

Mirrors the ``add_column_if_not_exists`` stored procedure from init_db.sql
but runs from Python so it can be called on live databases that were already
initialised (not just on first Docker start).

Callable via ``POST /migrate-db`` or standalone::

    python -m scripts.migrate_columns
"""

import logging

from database import get_connection

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Migration registry
# -------------------------------------------------------------------------
# Each entry is (schema, table, column, definition).
# Append new column migrations at the bottom — order matters if a later
# migration depends on an earlier one.
#
# The definition string is everything after ``ADD COLUMN <name>`` in an
# ALTER TABLE statement (type, default, constraints, position hint).
# -------------------------------------------------------------------------

MIGRATIONS: list[tuple[str, str, str, str]] = [
    # Example:
    # ("ncaa_mbb_silver", "fact_game_results", "home_team_espn_id", "VARCHAR(20)"),
]


def _column_exists(cursor, schema: str, table: str, column: str) -> bool:
    """Check whether *column* already exists on *schema.table*."""
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (schema, table, column),
    )
    return cursor.fetchone()[0] > 0


def run_migrations() -> dict:
    """Apply all pending column migrations.

    Returns
    -------
    dict with ``applied`` (list of newly added columns) and
    ``skipped`` (list of already-existing columns).
    """
    conn = get_connection()
    cursor = conn.cursor()

    applied = []
    skipped = []

    for schema, table, column, definition in MIGRATIONS:
        if _column_exists(cursor, schema, table, column):
            skipped.append(f"{schema}.{table}.{column}")
            continue

        alter_sql = (
            f"ALTER TABLE `{schema}`.`{table}` "
            f"ADD COLUMN `{column}` {definition}"
        )
        try:
            cursor.execute(alter_sql)
            applied.append(f"{schema}.{table}.{column}")
            logger.info("migrate_columns: added %s.%s.%s", schema, table, column)
        except Exception as exc:
            logger.error(
                "migrate_columns: failed to add %s.%s.%s — %s",
                schema, table, column, exc,
            )
            skipped.append(f"{schema}.{table}.{column} (ERROR: {exc})")

    conn.commit()
    cursor.close()
    conn.close()

    logger.info(
        "migrate_columns: done — %d applied, %d skipped",
        len(applied), len(skipped),
    )

    return {
        "status": "ok",
        "applied": applied,
        "skipped": skipped,
        "total_migrations": len(MIGRATIONS),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_migrations()
    print(result)
