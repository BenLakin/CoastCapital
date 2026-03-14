"""
Shared fixtures for CoastCapital Platform tests.

Mocks Ollama, Anthropic, and MySQL so tests run without external services.
"""

import os
import sys

import pytest
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars before importing app
os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "test-model")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("PLATFORM_API_KEY", "test-api-key")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test_platform")


@pytest.fixture(autouse=True)
def mock_db():
    """Auto-mock MySQL pool so tests never hit a real database."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.fetchone.return_value = {}
    mock_cursor.lastrowid = 1
    mock_cursor.rowcount = 1
    mock_conn.cursor.return_value = mock_cursor

    with patch("app.db._get_pool") as mock_pool:
        mock_pool.return_value.get_connection.return_value = mock_conn
        yield {"conn": mock_conn, "cursor": mock_cursor}


@pytest.fixture()
def client():
    """FastAPI TestClient with mocked dependencies."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def api_headers():
    return {"X-API-Key": os.environ["PLATFORM_API_KEY"]}
