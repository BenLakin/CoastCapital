"""
Shared pytest fixtures for CoastCapital Personal Assistant.

Env vars are set at module level BEFORE any app imports so that
Config class attributes (set at class-definition time) pick up
test values. MySQL and Anthropic are patched to prevent real
network connections during tests.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

# ── Set test env vars before any app module is imported ──────────────────────

os.environ.update({
    "API_KEY": "test-api-key",
    "ANTHROPIC_API_KEY": "sk-test-key",
    "MYSQL_HOST": "localhost",
    "MYSQL_PORT": "3306",
    "MYSQL_USER": "testuser",
    "MYSQL_PASSWORD": "testpass",
    "MYSQL_DATABASE": "test_assistant_db",
    "ICLOUD_EMAIL": "test@icloud.com",
    "ICLOUD_APP_PASSWORD": "test-app-password",
    "KIM_LAKIN_EMAIL": "kim@example.com",
    "FAMILY_EMAILS": "sibling@example.com",
    "OWNER_NAME": "Test Owner",
    "OWNER_CITY": "Denver",
    "CLAUDE_MODEL": "claude-haiku-4-5-20251001",
    "LOG_LEVEL": "WARNING",  # keep test output clean
})


# ── Flask app fixture (session-scoped — imported once) ───────────────────────

@pytest.fixture(scope="session")
def app():
    """
    Flask application configured for testing.

    mysql.connector is patched so init_db() doesn't try to connect,
    and anthropic.Anthropic is patched so pipeline __init__ methods
    don't require a real API key.
    """
    with patch("mysql.connector.connect", side_effect=Exception("no DB in tests")), \
         patch("mysql.connector.pooling.MySQLConnectionPool"), \
         patch("anthropic.Anthropic"):
        from app.main import app as flask_app
        flask_app.config["TESTING"] = True
        flask_app.config["SECRET_KEY"] = "test-secret"
        yield flask_app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


@pytest.fixture
def auth_headers():
    """Valid API key header for protected endpoints."""
    return {"X-API-Key": "test-api-key"}


# ── DB mock helpers ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_db(monkeypatch):
    """
    Patches app.db.get_conn to return a mock connection + cursor.

    Returns (mock_conn, mock_cursor) so tests can inspect calls or
    set return values:
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "Kim"}]
    """
    cur = MagicMock()
    cur.fetchall.return_value = []
    cur.fetchone.return_value = None
    cur.lastrowid = 1

    conn = MagicMock()
    conn.cursor.return_value = cur

    monkeypatch.setattr("app.db.get_conn", lambda: conn)
    return conn, cur
