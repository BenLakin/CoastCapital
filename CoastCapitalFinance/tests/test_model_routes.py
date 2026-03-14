"""Tests for model management API endpoints."""
import pytest
import json
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from datetime import datetime


def _mock_get_db(mock_db):
    """Create a context-manager mock for get_db()."""
    @contextmanager
    def _ctx():
        yield mock_db
    return _ctx


@pytest.fixture
def app():
    """Create test Flask app."""
    from app import create_app
    with patch("app._init_database"):
        test_app = create_app()
        test_app.config["TESTING"] = True
        yield test_app


@pytest.fixture
def client(app):
    return app.test_client()


class TestModelsPage:
    def test_models_page_serves_html(self, client):
        resp = client.get("/models")
        assert resp.status_code == 200
        assert b"Model Management" in resp.data


class TestListTickers:
    def test_returns_tickers(self, client):
        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)

            # Handle multiple query calls
            def mock_query_side_effect(model):
                result = MagicMock()
                result.distinct.return_value.all.return_value = [("AAPL",)]
                result.filter.return_value.first.return_value = None
                result.filter.return_value.scalar.return_value = 1
                return result

            mock_db.query.side_effect = mock_query_side_effect

            resp = client.get("/api/v1/models/tickers")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "tickers" in data


class TestTrainModel:
    def test_train_success(self, client):
        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)

            with patch("app.forecasting.models.train_model") as mock_train:
                mock_train.return_value = {
                    "ticker": "AAPL",
                    "model_id": 1,
                    "model_version": "v3.0",
                    "sequence_num": 1,
                    "train_rows": 500,
                    "training_duration_sec": 30.0,
                    "hpo_method": "none",
                    "metrics": {"1d": {"oof_rmse": 0.012}},
                }

                resp = client.post(
                    "/api/v1/models/AAPL/train",
                    data=json.dumps({"hpo_method": "none"}),
                    content_type="application/json",
                )
                assert resp.status_code == 200
                data = json.loads(resp.data)
                assert data["success"] is True
                assert data["sequence_num"] == 1

    def test_train_invalid_hpo_method(self, client):
        resp = client.post(
            "/api/v1/models/AAPL/train",
            data=json.dumps({"hpo_method": "invalid"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data


class TestBacktestModel:
    def test_backtest_missing_model(self, client):
        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)
            mock_db.query.return_value.filter.return_value.first.return_value = None

            resp = client.post("/api/v1/models/AAPL/backtest/999")
            assert resp.status_code == 404

    def test_backtest_success(self, client):
        from app.models.schema import FactModelRegistry

        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)

            mock_entry = MagicMock(spec=FactModelRegistry)
            mock_entry.hpo_method = "none"
            mock_db.query.return_value.filter.return_value.first.return_value = mock_entry

            with patch("app.forecasting.backtesting.run_backtest") as mock_bt:
                mock_bt.return_value = {
                    "ticker": "AAPL",
                    "directional_accuracy": 0.55,
                    "sharpe_ratio": 1.2,
                    "alpha": 0.05,
                    "max_drawdown": -0.08,
                }
                resp = client.post("/api/v1/models/AAPL/backtest/1")
                assert resp.status_code == 200
                data = json.loads(resp.data)
                assert data["success"] is True


class TestListVersions:
    def test_list_versions_empty(self, client):
        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)
            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

            resp = client.get("/api/v1/models/AAPL/versions")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["versions"] == []

    def test_list_versions_returns_entries(self, client):
        from app.models.schema import FactModelRegistry

        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)

            mock_entry = MagicMock(spec=FactModelRegistry)
            mock_entry.model_id = 1
            mock_entry.ticker = "AAPL"
            mock_entry.sequence_num = 1
            mock_entry.status = "candidate"
            mock_entry.model_version = "v3.0"
            mock_entry.hpo_method = "none"
            mock_entry.training_duration_sec = 30.0
            mock_entry.train_rows = 500
            mock_entry.n_features = 25
            mock_entry.horizons = [1, 5]
            mock_entry.train_metrics = {}
            mock_entry.backtest_id = None
            mock_entry.backtest_metrics = None
            mock_entry.feature_importance = {}
            mock_entry.notes = ""
            mock_entry.trained_at = datetime(2025, 1, 15, 10, 0)
            mock_entry.promoted_at = None

            mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [mock_entry]

            resp = client.get("/api/v1/models/AAPL/versions")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert len(data["versions"]) == 1
            assert data["versions"][0]["sequence_num"] == 1


class TestCompareModels:
    def test_compare_no_models(self, client):
        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

            resp = client.get("/api/v1/models/AAPL/compare")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["recommendation"] in ("no_models", "needs_backtest")


class TestPromoteModel:
    def test_promote_requires_backtest(self, client):
        from app.models.schema import FactModelRegistry

        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)

            mock_entry = MagicMock(spec=FactModelRegistry)
            mock_entry.status = "candidate"
            mock_entry.backtest_metrics = None
            mock_db.query.return_value.filter.return_value.first.return_value = mock_entry

            resp = client.post("/api/v1/models/AAPL/promote/1")
            assert resp.status_code == 400
            data = json.loads(resp.data)
            assert "backtest" in data["error"].lower()

    def test_promote_not_found(self, client):
        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)
            mock_db.query.return_value.filter.return_value.first.return_value = None

            resp = client.post("/api/v1/models/AAPL/promote/999")
            assert resp.status_code == 404


class TestAggregatePerformance:
    def test_performance_empty(self, client):
        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)
            mock_db.query.return_value.filter.return_value.all.return_value = []

            resp = client.get("/api/v1/models/performance")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["n_champions"] == 0

    def test_performance_with_champions(self, client):
        from app.models.schema import FactModelRegistry

        with patch("app.routes.model_routes.get_db") as mock_get_db:
            mock_db = MagicMock()
            mock_get_db.side_effect = _mock_get_db(mock_db)

            mock_champion = MagicMock(spec=FactModelRegistry)
            mock_champion.ticker = "AAPL"
            mock_champion.model_id = 1
            mock_champion.sequence_num = 2
            mock_champion.hpo_method = "grid"
            mock_champion.backtest_metrics = {
                "directional_accuracy": 0.55,
                "sharpe_ratio": 1.2,
                "alpha": 0.05,
                "max_drawdown": -0.08,
                "win_rate": 0.52,
            }
            mock_champion.trained_at = datetime(2025, 1, 15)

            mock_db.query.return_value.filter.return_value.all.return_value = [mock_champion]

            resp = client.get("/api/v1/models/performance")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert data["n_champions"] == 1
            assert data["avg_directional_accuracy"] == 0.55
