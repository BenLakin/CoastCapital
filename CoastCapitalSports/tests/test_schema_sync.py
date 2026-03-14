"""
Tests for ingestion/schema_sync.py — dynamic schema evolution.

Validates type inference, column sync, dynamic upsert, and cache management.
All database interactions are mocked.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest

from ingestion.schema_sync import (
    _column_cache,
    _infer_mysql_type,
    clear_cache,
    dynamic_upsert,
    sync_columns,
)


@pytest.fixture(autouse=True)
def clean_cache():
    """Clear the column cache before and after each test."""
    clear_cache()
    yield
    clear_cache()


# ── Type inference ────────────────────────────────────────────────────────────

class TestInferMySQLType:
    def test_none_returns_varchar(self):
        assert _infer_mysql_type(None) == "VARCHAR(200)"

    def test_bool_returns_tinyint(self):
        assert _infer_mysql_type(True) == "TINYINT"
        assert _infer_mysql_type(False) == "TINYINT"

    def test_small_int(self):
        assert _infer_mysql_type(42) == "INT"

    def test_large_int_returns_bigint(self):
        assert _infer_mysql_type(3_000_000_000) == "BIGINT"

    def test_float_returns_double(self):
        assert _infer_mysql_type(3.14) == "DOUBLE"

    def test_decimal_returns_decimal(self):
        assert _infer_mysql_type(Decimal("10.5")) == "DECIMAL(10,4)"

    def test_datetime_returns_datetime(self):
        assert _infer_mysql_type(datetime(2024, 1, 1)) == "DATETIME"

    def test_date_returns_date(self):
        assert _infer_mysql_type(date(2024, 1, 1)) == "DATE"

    def test_short_string(self):
        result = _infer_mysql_type("hello")
        assert result.startswith("VARCHAR(")

    def test_string_length_scaling(self):
        """VARCHAR length should be at least 2x the string length, min 100."""
        result = _infer_mysql_type("ab")
        assert result == "VARCHAR(100)"  # min 100

    def test_unknown_type_returns_text(self):
        assert _infer_mysql_type([1, 2, 3]) == "TEXT"


# ── Column synchronisation ───────────────────────────────────────────────────

class TestSyncColumns:
    def test_no_new_columns(self):
        """No ALTER TABLE needed when all columns exist."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [("game_id",), ("score",)]
        data = {"game_id": "g1", "score": 100}

        added = sync_columns(cursor, "nfl_silver", "fact_games", data)

        assert added == []
        # Should NOT have called ALTER TABLE
        alter_calls = [
            c for c in cursor.execute.call_args_list
            if "ALTER TABLE" in str(c)
        ]
        assert len(alter_calls) == 0

    def test_new_column_added(self):
        """New columns should trigger ALTER TABLE ADD COLUMN."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [("game_id",)]
        data = {"game_id": "g1", "new_stat": 42}

        added = sync_columns(cursor, "nfl_silver", "fact_games", data)

        assert "new_stat" in added
        alter_calls = [
            c for c in cursor.execute.call_args_list
            if "ALTER TABLE" in str(c)
        ]
        assert len(alter_calls) == 1

    def test_cache_avoids_repeated_queries(self):
        """Second call should use cached columns, not query INFORMATION_SCHEMA again."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [("game_id",), ("score",)]

        sync_columns(cursor, "nfl_silver", "fact_games", {"game_id": "g1"})
        info_schema_calls_1 = len([
            c for c in cursor.execute.call_args_list
            if "INFORMATION_SCHEMA" in str(c)
        ])

        sync_columns(cursor, "nfl_silver", "fact_games", {"game_id": "g2"})
        info_schema_calls_2 = len([
            c for c in cursor.execute.call_args_list
            if "INFORMATION_SCHEMA" in str(c)
        ])

        # Should only query INFORMATION_SCHEMA once
        assert info_schema_calls_1 == 1
        assert info_schema_calls_2 == 1  # same count — no new query


# ── Dynamic upsert ───────────────────────────────────────────────────────────

class TestDynamicUpsert:
    def test_insert_with_upsert(self):
        """Default mode should include ON DUPLICATE KEY UPDATE."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [("game_id",), ("score",)]

        dynamic_upsert(cursor, "nfl_silver", "fact_games", {
            "game_id": "g1",
            "score": 100,
        })

        insert_call = cursor.execute.call_args_list[-1]
        sql = insert_call[0][0]
        assert "INSERT INTO" in sql
        assert "ON DUPLICATE KEY UPDATE" in sql

    def test_insert_without_upsert(self):
        """on_duplicate_update=False should omit UPDATE clause."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [("game_id",), ("spread",)]

        dynamic_upsert(cursor, "nfl_silver", "fact_odds", {
            "game_id": "g1",
            "spread": -3.0,
        }, on_duplicate_update=False)

        insert_call = cursor.execute.call_args_list[-1]
        sql = insert_call[0][0]
        assert "INSERT INTO" in sql
        assert "ON DUPLICATE KEY UPDATE" not in sql

    def test_values_passed_as_tuple(self):
        """Values should be passed as parameterized tuple, not interpolated."""
        cursor = MagicMock()
        cursor.fetchall.return_value = [("game_id",)]

        dynamic_upsert(cursor, "nfl_silver", "fact_games", {
            "game_id": "401547417",
        })

        insert_call = cursor.execute.call_args_list[-1]
        values = insert_call[0][1]
        assert values == ("401547417",)


# ── Cache management ─────────────────────────────────────────────────────────

class TestClearCache:
    def test_clear_removes_all_entries(self):
        _column_cache[("nfl_silver", "fact_games")] = {"game_id", "score"}
        assert len(_column_cache) > 0
        clear_cache()
        assert len(_column_cache) == 0
