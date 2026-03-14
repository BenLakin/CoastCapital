"""
Shared fixtures for CoastCapital database test suite.
"""
import os
from unittest.mock import MagicMock

import pytest

# Inject required env vars BEFORE any app module is imported
os.environ.setdefault("API_KEY",        "test-api-key-123")
os.environ.setdefault("MYSQL_HOST",     "localhost")
os.environ.setdefault("MYSQL_PORT",     "3306")
os.environ.setdefault("MYSQL_USER",     "dbadmin")
os.environ.setdefault("MYSQL_PASSWORD", "test-password")


# ─── MOCK DB CURSOR FACTORY ────────────────────────────────────────────────────

def make_mock_cursor(rows=None, description=None, stored_results=None):
    """Return a MagicMock that behaves like a mysql-connector cursor."""
    cur = MagicMock()
    cur.fetchall.return_value   = rows or []
    cur.fetchone.return_value   = (rows[0] if rows else None)
    cur.description             = description or []
    cur.rowcount                = len(rows) if rows else 0
    cur.stored_results.return_value = iter(stored_results or [])
    return cur


def make_mock_conn(cursor=None):
    """Return a MagicMock that behaves like a mysql-connector connection."""
    conn = MagicMock()
    conn.cursor.return_value = cursor or make_mock_cursor()
    return conn


# ─── FIXTURES ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def api_headers():
    return {"X-API-Key": os.environ["API_KEY"]}


@pytest.fixture()
def bad_headers():
    return {"X-API-Key": "wrong-key"}
