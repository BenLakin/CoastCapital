"""
Shared fixtures for CoastCapital HomeLab tests.

Mocks database connections, external service APIs, and SSH
so tests run without real infrastructure.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Ensure the project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── Mock heavy modules before import ──────────────────────────────────────

def _stub_module(name):
    """Register a MagicMock as a fake module so imports don't fail."""
    if name not in sys.modules:
        sys.modules[name] = MagicMock()

# Mock SSH lib so tests work without Docker-only dependencies
for _mod in ["paramiko"]:
    _stub_module(_mod)


# Set required env vars before importing app
os.environ.setdefault("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test_homelab")


def make_mock_cursor(rows=None):
    """Return a MagicMock that behaves like a mysql-connector cursor."""
    cur = MagicMock()
    cur.fetchall.return_value = rows or []
    cur.fetchone.return_value = (rows[0] if rows else None)
    cur.description = []
    cur.rowcount = len(rows) if rows else 0
    return cur


def make_mock_conn(cursor=None):
    """Return a MagicMock that behaves like a mysql-connector connection."""
    conn = MagicMock()
    conn.cursor.return_value = cursor or make_mock_cursor()
    return conn


@pytest.fixture(autouse=True)
def mock_db():
    """Auto-mock database connections for all tests."""
    with patch("app.db.get_conn") as mock_get, \
         patch("app.db.init_db") as mock_init:
        mock_get.return_value = make_mock_conn()
        yield {"get_conn": mock_get, "init_db": mock_init}


@pytest.fixture()
def client(mock_db):
    """Flask test client with mocked dependencies."""
    from app.main import create_app
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture()
def api_headers():
    """Headers for authenticated API requests."""
    return {"X-API-Key": os.environ["API_KEY"]}
