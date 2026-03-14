"""Tests for Flask routes and n8n endpoints."""
import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import date


@pytest.fixture
def app():
    with patch("app._init_database"):
        from app import create_app
        application = create_app()
        application.config["TESTING"] = True
        return application


@pytest.fixture
def client(app):
    return app.test_client()


class TestHealthEndpoints:
    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "Coast Capital Finance Platform" in data["service"]

    @patch("app.routes.api_routes.check_db_health")
    def test_api_health(self, mock_health, client):
        mock_health.return_value = {"status": "healthy", "database": "finance_silver"}
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200


class TestN8nRoutes:
    def test_n8n_health(self, client):
        with patch("app.routes.n8n_routes.check_db_health",
                  return_value={"status": "healthy", "database": "finance_silver"}):
            resp = client.get("/n8n/health")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["status"] == "healthy"

    @patch("app.routes.n8n_routes.settings")
    def test_n8n_auth_rejected(self, mock_settings, client):
        mock_settings.N8N_WEBHOOK_SECRET = "secret123"
        mock_settings.watchlist = ["AAPL"]

        resp = client.post(
            "/n8n/daily-forecast",
            headers={"Authorization": "Bearer wrong-secret"},
            json={},
        )
        assert resp.status_code == 401

    @patch("app.routes.n8n_routes.settings")
    @patch("app.routes.n8n_routes.run_daily_pipeline")
    def test_daily_forecast_success(self, mock_pipeline, mock_settings, client):
        mock_settings.N8N_WEBHOOK_SECRET = None  # no auth
        mock_pipeline.return_value = {
            "run_date": str(date.today()),
            "target_date": str(date.today()),
            "top_opportunities": [
                {"rank": 1, "ticker": "AAPL", "signal": "LONG",
                 "predicted_return_pct": 1.5, "confidence_pct": 72.0,
                 "opportunity_score": 1.45}
            ],
            "market_brief": "Market looks bullish.",
            "pipeline_stats": {"tickers_processed": 1},
            "status": "success",
        }

        resp = client.post("/n8n/daily-forecast", json={"tickers": ["AAPL"], "use_llm": False})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True
        assert len(data["data"]["top_opportunities"]) == 1

    @patch("app.routes.n8n_routes.settings")
    def test_watchlist_get(self, mock_settings, client):
        mock_settings.N8N_WEBHOOK_SECRET = None
        resp = client.get("/n8n/watchlist")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "watchlist" in data["data"]

    @patch("app.routes.n8n_routes.settings")
    @patch("app.routes.n8n_routes.backfill_ticker")
    def test_add_ticker(self, mock_backfill, mock_settings, client):
        mock_settings.N8N_WEBHOOK_SECRET = None
        mock_backfill.return_value = {"status": "success", "ticker": "TSLA"}

        # Import routes to access _dynamic_watchlist
        resp = client.post("/n8n/watchlist/add", json={"tickers": ["TSLA"]})
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "TSLA" in data["data"]["watchlist"] or "TSLA" in data["data"]["added"]

    @patch("app.routes.n8n_routes.settings")
    def test_watchlist_add_empty(self, mock_settings, client):
        mock_settings.N8N_WEBHOOK_SECRET = None
        resp = client.post("/n8n/watchlist/add", json={"tickers": []})
        assert resp.status_code == 400


class TestApiRoutes:
    @patch("app.routes.api_routes.get_db")
    def test_list_stocks_empty(self, mock_get_db, client):
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.all.return_value = []
        mock_get_db.return_value = mock_db

        resp = client.get("/api/v1/stocks")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["data"] == []

    @patch("app.routes.api_routes.get_db")
    def test_get_prices_ticker_not_found(self, mock_get_db, client):
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.filter.return_value.first.return_value = None
        mock_get_db.return_value = mock_db

        resp = client.get("/api/v1/stocks/UNKNOWN/prices")
        assert resp.status_code == 404

    @patch("app.routes.api_routes.get_db")
    def test_get_todays_forecasts(self, mock_get_db, client):
        mock_db = MagicMock()
        mock_db.__enter__ = MagicMock(return_value=mock_db)
        mock_db.__exit__ = MagicMock(return_value=False)
        mock_db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        mock_get_db.return_value = mock_db

        resp = client.get("/api/v1/forecasts/today")
        assert resp.status_code == 200
