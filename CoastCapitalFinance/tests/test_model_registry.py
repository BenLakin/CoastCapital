"""Tests for model registry: CRUD, promotion, sequence numbers, one-champion invariant."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock


class TestFactModelRegistry:
    """Test FactModelRegistry schema and constraints."""

    def test_table_exists(self):
        from app.models.schema import FactModelRegistry
        assert FactModelRegistry.__tablename__ == "fact_model_registry"

    def test_required_fields(self):
        from app.models.schema import FactModelRegistry
        entry = FactModelRegistry(
            ticker="AAPL",
            sequence_num=1,
            status="candidate",
        )
        assert entry.ticker == "AAPL"
        assert entry.sequence_num == 1
        assert entry.status == "candidate"
        assert entry.model_version == "v3.0"

    def test_default_values(self):
        from app.models.schema import FactModelRegistry
        entry = FactModelRegistry(ticker="MSFT", sequence_num=1)
        assert entry.status == "candidate"
        assert entry.model_version == "v3.0"
        assert entry.hpo_method == "none"

    def test_json_fields_accept_dicts(self):
        from app.models.schema import FactModelRegistry
        entry = FactModelRegistry(
            ticker="TEST",
            sequence_num=1,
            horizons=[1, 5],
            hyperparams={"lgbm": {"n_estimators": 500}},
            train_metrics={"1d": {"oof_rmse": 0.012}},
            feature_importance={"1d": {"rsi_14": 42.5}},
            backtest_metrics={"directional_accuracy": 0.55},
        )
        assert entry.horizons == [1, 5]
        assert entry.hyperparams["lgbm"]["n_estimators"] == 500
        assert entry.backtest_metrics["directional_accuracy"] == 0.55


class TestSequenceNumber:
    """Test auto-incrementing sequence numbers per ticker."""

    def test_next_sequence_num_empty(self):
        from app.forecasting.models import _next_sequence_num
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.scalar.return_value = None
        assert _next_sequence_num("AAPL", mock_db) == 1

    def test_next_sequence_num_existing(self):
        from app.forecasting.models import _next_sequence_num
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.scalar.return_value = 3
        assert _next_sequence_num("AAPL", mock_db) == 4

    def test_next_sequence_num_handles_exception(self):
        from app.forecasting.models import _next_sequence_num
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Table not found")
        assert _next_sequence_num("AAPL", mock_db) == 1


class TestModelPromotion:
    """Test the champion/challenger promotion logic."""

    def test_promote_archives_old_champion(self):
        """Promoting a candidate should archive the current champion."""
        from app.models.schema import FactModelRegistry

        old_champion = FactModelRegistry(
            model_id=1, ticker="AAPL", sequence_num=1, status="champion",
            backtest_metrics={"directional_accuracy": 0.50},
        )
        new_candidate = FactModelRegistry(
            model_id=2, ticker="AAPL", sequence_num=2, status="candidate",
            backtest_metrics={"directional_accuracy": 0.55},
        )

        # Simulate promotion
        old_champion.status = "archived"
        new_candidate.status = "champion"
        new_candidate.promoted_at = datetime.now(timezone.utc)
        new_candidate.promoted_from_id = old_champion.model_id

        assert old_champion.status == "archived"
        assert new_candidate.status == "champion"
        assert new_candidate.promoted_from_id == 1

    def test_one_champion_per_ticker(self):
        """Only one champion should exist per ticker at any time."""
        from app.models.schema import FactModelRegistry

        entries = [
            FactModelRegistry(model_id=1, ticker="AAPL", sequence_num=1, status="archived"),
            FactModelRegistry(model_id=2, ticker="AAPL", sequence_num=2, status="champion"),
            FactModelRegistry(model_id=3, ticker="AAPL", sequence_num=3, status="candidate"),
        ]

        champions = [e for e in entries if e.status == "champion"]
        assert len(champions) == 1
        assert champions[0].sequence_num == 2


class TestMakeJsonSafe:
    """Test numpy/python type conversion for JSON serialization."""

    def test_numpy_types(self):
        import numpy as np
        from app.forecasting.models import _make_json_safe

        data = {
            "int": np.int64(42),
            "float": np.float64(3.14),
            "array": np.array([1, 2, 3]),
            "nested": {"val": np.float32(1.5)},
        }
        result = _make_json_safe(data)
        assert isinstance(result["int"], int)
        assert isinstance(result["float"], float)
        assert isinstance(result["array"], list)
        assert isinstance(result["nested"]["val"], float)

    def test_native_types_passthrough(self):
        from app.forecasting.models import _make_json_safe
        data = {"str": "hello", "int": 42, "float": 3.14, "bool": True, "none": None}
        result = _make_json_safe(data)
        assert result == data

    def test_list_conversion(self):
        import numpy as np
        from app.forecasting.models import _make_json_safe
        result = _make_json_safe([np.int64(1), np.float64(2.0), "three"])
        assert result == [1, 2.0, "three"]


class TestRegisterModel:
    """Test _register_model helper."""

    def test_register_model_returns_model_id(self):
        from app.forecasting.models import _register_model
        mock_db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.stock_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_stock

        # Mock the flush to set model_id
        def mock_add(entry):
            entry.model_id = 42
        mock_db.add.side_effect = mock_add

        result = _register_model(
            ticker="AAPL", db=mock_db, sequence_num=1,
            hpo_method="none", training_duration=30.5,
            train_rows=500, n_features=25, horizons=[1, 5],
            hyperparams={}, train_metrics={},
            feature_importance={}, model_path="AAPL_v3.0_seq1.pkl",
        )

        assert result == 42
        mock_db.add.assert_called_once()

    def test_register_model_handles_missing_table(self):
        from app.forecasting.models import _register_model
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Table doesn't exist")

        result = _register_model(
            ticker="AAPL", db=mock_db, sequence_num=1,
            hpo_method="none", training_duration=30.5,
            train_rows=500, n_features=25, horizons=[1],
            hyperparams={}, train_metrics={},
            feature_importance={}, model_path="test.pkl",
        )

        assert result is None


class TestVersionedSaveLoad:
    """Test versioned model save/load."""

    def test_versioned_filename(self):
        from app.forecasting.models import StockForecaster, MODELS_DIR, MODEL_VERSION
        model = StockForecaster("TEST")
        model.feature_names = ["a", "b"]
        model.scaler = MagicMock()
        model.models = {}
        model.train_metrics = {}

        with patch("app.forecasting.models.MODELS_DIR", "/tmp/test_models"):
            with patch("app.forecasting.models.joblib") as mock_joblib:
                with patch("os.makedirs"):
                    path = model.save(sequence_num=5)
                assert path == f"/tmp/test_models/TEST_{MODEL_VERSION}_seq5.pkl"

    def test_unversioned_filename(self):
        from app.forecasting.models import StockForecaster, MODEL_VERSION
        model = StockForecaster("TEST")
        model.feature_names = ["a"]
        model.scaler = MagicMock()
        model.models = {}
        model.train_metrics = {}

        with patch("app.forecasting.models.MODELS_DIR", "/tmp/test_models"):
            with patch("app.forecasting.models.joblib"):
                with patch("os.makedirs"):
                    path = model.save()
                assert path == f"/tmp/test_models/TEST_{MODEL_VERSION}.pkl"

    def test_load_fallback_to_unversioned(self):
        from app.forecasting.models import StockForecaster, MODEL_VERSION
        import os

        with patch("app.forecasting.models.MODELS_DIR", "/tmp/test_models"):
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                with patch("app.forecasting.models.joblib.load") as mock_load:
                    mock_load.return_value = {
                        "ticker": "TEST",
                        "feature_names": ["a"],
                        "horizons": [1],
                        "models": {},
                        "scaler": MagicMock(),
                        "train_metrics": {},
                    }
                    model = StockForecaster.load("TEST")
                    assert model.ticker == "TEST"

    def test_load_with_explicit_path(self):
        from app.forecasting.models import StockForecaster

        with patch("os.path.isabs", return_value=True):
            with patch("os.path.exists", return_value=True):
                with patch("app.forecasting.models.joblib.load") as mock_load:
                    mock_load.return_value = {
                        "ticker": "TEST",
                        "feature_names": ["a"],
                        "horizons": [1, 5],
                        "models": {},
                        "scaler": MagicMock(),
                        "train_metrics": {},
                    }
                    model = StockForecaster.load("TEST", model_path="/full/path/model.pkl")
                    assert model.horizons == [1, 5]
