"""
Route tests for CoastCapital Sports API.

Tests health endpoint, authentication, dashboard pages, and pipeline API endpoints.
"""

import json
from unittest.mock import patch, MagicMock


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"
        assert data["service"] == "coastcapital-sports"
        assert "ts" in data

    def test_health_no_auth_required(self, client):
        """Health endpoint should not require API key."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_metrics_no_auth_required(self, client):
        """Metrics endpoint should not require API key."""
        resp = client.get("/metrics")
        assert resp.status_code == 200


class TestAuth:
    def test_pipeline_rejects_wrong_key(self, client, bad_headers):
        resp = client.post("/update", json={"sport": "mlb"}, headers=bad_headers)
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert data["success"] is False

    def test_pipeline_requires_key(self, client):
        """Pipeline endpoints should require API key when API_KEY is set."""
        resp = client.post("/update", json={"sport": "mlb"})
        assert resp.status_code == 401

    def test_pipeline_accepts_valid_key(self, client, api_headers):
        resp = client.post("/update", json={"sport": "mlb"}, headers=api_headers)
        assert resp.status_code == 200


class TestDashboardPages:
    def test_dashboard_page(self, client, api_headers):
        resp = client.get("/dashboard", headers=api_headers)
        assert resp.status_code == 200

    def test_betting_page(self, client, api_headers):
        resp = client.get("/dashboard/betting", headers=api_headers)
        assert resp.status_code == 200

    def test_model_performance_page(self, client, api_headers):
        resp = client.get("/dashboard/model-performance", headers=api_headers)
        assert resp.status_code == 200

    def test_model_diagnostics_page(self, client, api_headers):
        resp = client.get("/dashboard/model-diagnostics", headers=api_headers)
        assert resp.status_code == 200


class TestPipelineEndpoints:
    @patch("main.run_backfill_pipeline", return_value={"status": "ok", "rows": 100})
    def test_backfill_success(self, mock_pipeline, client, api_headers):
        resp = client.post("/backfill", json={"sport": "mlb"}, headers=api_headers)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"

    @patch("main.run_update_pipeline", return_value={"status": "ok", "new_rows": 10})
    def test_update_success(self, mock_pipeline, client, api_headers):
        resp = client.post("/update", json={"sport": "mlb"}, headers=api_headers)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"


class TestTrainingEndpoints:
    @patch("main.train_model", return_value={"status": "ok", "model_version": "v1"})
    def test_train_success(self, mock_train, client, api_headers):
        resp = client.post("/train-model", json={"sport": "mlb", "target": "home_win"},
                           headers=api_headers)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["status"] == "ok"

    @patch("main.train_model", return_value={"status": "ok"})
    def test_train_defaults_sport(self, mock_train, client, api_headers):
        """Training defaults to nfl when sport is omitted."""
        resp = client.post("/train-model", json={}, headers=api_headers)
        assert resp.status_code == 200
        mock_train.assert_called_once()
        assert mock_train.call_args.kwargs.get("sport") == "nfl"


class TestDashboardAPI:
    def test_quick_stats(self, client, api_headers):
        resp = client.get("/api/quick-stats", headers=api_headers)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "stats" in data

    def test_news_endpoint(self, client, api_headers):
        resp = client.get("/api/news", headers=api_headers)
        assert resp.status_code == 200

    def test_model_performance_api(self, client, api_headers):
        resp = client.get("/api/model-performance", headers=api_headers)
        assert resp.status_code == 200
