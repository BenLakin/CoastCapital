"""
Tests for CoastCapital Database Maintenance API.

Tests health check, authentication, and maintenance job routing.
"""
import logging
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# Inject required env vars BEFORE any app module is imported
os.environ.setdefault("API_KEY", "test-api-key-123")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "dbadmin")
os.environ.setdefault("MYSQL_PASSWORD", "test-password")

# Ensure app directory is on path
_app_dir = os.path.join(os.path.dirname(__file__), "..", "maintenance-api")
sys.path.insert(0, _app_dir)

# Create logs dir to prevent FileNotFoundError from hardcoded /app/logs path
_logs_dir = os.path.join(_app_dir, "logs")
os.makedirs(_logs_dir, exist_ok=True)

# Monkey-patch the logging FileHandler before app import to use local log dir
_orig_file_handler = logging.FileHandler
def _patched_file_handler(filename, *args, **kwargs):
    if filename.startswith("/app/logs/"):
        filename = os.path.join(_logs_dir, os.path.basename(filename))
    return _orig_file_handler(filename, *args, **kwargs)

logging.FileHandler = _patched_file_handler


@pytest.fixture(autouse=True)
def mock_db():
    """Mock MySQL connection for all tests."""
    with patch("app.get_db_connection") as mock_conn:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = None
        conn.cursor.return_value = cursor
        mock_conn.return_value = conn
        yield mock_conn


@pytest.fixture()
def client():
    """FastAPI test client."""
    from fastapi.testclient import TestClient
    from app import app
    return TestClient(app)


@pytest.fixture()
def api_headers():
    return {"X-API-Key": os.environ["API_KEY"]}


@pytest.fixture()
def bad_headers():
    return {"X-API-Key": "wrong-key"}


# ── Health ─────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, client, mock_db):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["mysql_connected"] is True

    def test_health_degraded_on_db_failure(self, client, mock_db):
        mock_db.side_effect = Exception("connection refused")
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["mysql_connected"] is False


# ── Auth ───────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_maintenance_requires_api_key(self, client):
        resp = client.post("/maintenance/run", json={
            "job_type": "optimize",
            "schema_name": "finance_silver",
        })
        assert resp.status_code in (401, 403)

    def test_maintenance_rejects_wrong_key(self, client, bad_headers):
        resp = client.post("/maintenance/run", json={
            "job_type": "optimize",
            "schema_name": "finance_silver",
        }, headers=bad_headers)
        assert resp.status_code in (401, 403)

    def test_status_requires_api_key(self, client):
        resp = client.get("/maintenance/status")
        assert resp.status_code in (401, 403)

    def test_recommendations_requires_api_key(self, client):
        resp = client.get("/maintenance/recommendations")
        assert resp.status_code in (401, 403)


# ── Maintenance Run ────────────────────────────────────────────────────────────

class TestMaintenanceRun:
    def test_optimize_success(self, client, api_headers, mock_db):
        resp = client.post("/maintenance/run", json={
            "job_type": "optimize",
            "schema_name": "finance_silver",
        }, headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["job_type"] == "optimize"
        assert data["schema_name"] == "finance_silver"

    def test_invalid_job_type(self, client, api_headers):
        resp = client.post("/maintenance/run", json={
            "job_type": "drop_all_tables",
            "schema_name": "finance_silver",
        }, headers=api_headers)
        assert resp.status_code == 400

    def test_report_job_type(self, client, api_headers, mock_db):
        resp = client.post("/maintenance/run", json={
            "job_type": "report",
            "schema_name": "finance_silver",
        }, headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "Report:" in data["message"]

    def test_all_valid_job_types(self, client, api_headers, mock_db):
        """Every valid job type should return 200."""
        for job in ["optimize", "analyze", "check", "health",
                     "slow_queries", "full", "flush", "recommendations", "report"]:
            resp = client.post("/maintenance/run", json={
                "job_type": job,
                "schema_name": "finance_silver",
            }, headers=api_headers)
            assert resp.status_code == 200, f"job_type={job} returned {resp.status_code}"


# ── Read Endpoints ─────────────────────────────────────────────────────────────

class TestReadEndpoints:
    def test_status_returns_entries(self, client, api_headers, mock_db):
        resp = client.get("/maintenance/status", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "entries" in data

    def test_recommendations_returns_list(self, client, api_headers, mock_db):
        resp = client.get("/maintenance/recommendations", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "recommendations" in data

    def test_health_snapshot_returns_data(self, client, api_headers, mock_db):
        resp = client.get("/maintenance/health-snapshot", headers=api_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "snapshot" in data
