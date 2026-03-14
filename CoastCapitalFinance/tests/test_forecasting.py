"""Tests for v3.0 forecast engine: stacking ensemble, multi-horizon, conformal intervals, Kelly scoring."""
import pytest
import numpy as np
import pandas as pd
from datetime import date, timedelta
from unittest.mock import patch, MagicMock


def _make_feature_df(n: int = 300, horizons: list[int] = None) -> pd.DataFrame:
    """Create synthetic feature DataFrame for testing."""
    horizons = horizons or [1, 5]
    np.random.seed(42)
    dates = pd.date_range(date.today() - timedelta(days=n + 50), periods=n, freq="B")
    close = 100 + np.cumsum(np.random.normal(0.05, 1.0, n))

    df = pd.DataFrame({
        "close": close,
        "daily_return": np.random.normal(0.001, 0.015, n),
        "log_return": np.random.normal(0.001, 0.015, n),
        "rsi_14": np.random.uniform(30, 70, n),
        "macd_histogram": np.random.normal(0, 0.5, n),
        "bb_pct_b": np.random.uniform(0, 1, n),
        "bb_bandwidth": np.random.uniform(0.02, 0.1, n),
        "volatility_20d": np.random.uniform(0.15, 0.40, n),
        "volatility_5d": np.random.uniform(0.15, 0.40, n),
        "volume_ratio": np.random.uniform(0.5, 2.0, n),
        "stoch_k": np.random.uniform(20, 80, n),
        "roc_10": np.random.normal(0, 3, n),
        "vix": np.random.uniform(12, 35, n),
        "yield_curve_2_10": np.random.normal(0.3, 0.5, n),
        "day_of_week": np.random.randint(0, 5, n),
        "month": np.random.randint(1, 13, n),
        "earnings_week": np.random.randint(0, 2, n),
        "recent_eps_surprise": np.random.normal(5, 10, n),
        "sentiment_score_wavg": np.random.uniform(-0.5, 0.5, n),
        "return_lag_1d": np.random.normal(0, 0.015, n),
        "cum_return_20d": np.random.normal(0, 0.08, n),
        "momentum_quality": np.random.normal(0, 0.5, n),
        "realized_vol_20d": np.random.uniform(0.15, 0.40, n),
        "realized_vs_implied_vol": np.random.uniform(0.7, 1.3, n),
        "rank_momentum_20d": np.random.uniform(0, 1, n),
        "rank_volatility_20d": np.random.uniform(0, 1, n),
    }, index=dates)

    # Multi-horizon targets
    for h in horizons:
        signal = df["rsi_14"].apply(lambda x: 0.003 if x < 35 else (-0.003 if x > 65 else 0))
        df[f"target_return_{h}d"] = signal + np.random.normal(0, 0.01, n)

    df["target_direction"] = np.sign(df["target_return_1d"])
    return df.dropna()


class TestKellyOpportunityScore:
    def test_positive_return_high_confidence(self):
        from app.forecasting.models import kelly_opportunity_score
        score = kelly_opportunity_score(
            predicted_return=0.02, confidence=0.80, volatility=0.20, sentiment=0.5,
        )
        assert score > 0

    def test_negative_return_yields_negative_score(self):
        from app.forecasting.models import kelly_opportunity_score
        score = kelly_opportunity_score(
            predicted_return=-0.02, confidence=0.80, volatility=0.20, sentiment=-0.3,
        )
        assert score < 0

    def test_score_is_bounded(self):
        from app.forecasting.models import kelly_opportunity_score
        score = kelly_opportunity_score(
            predicted_return=1.0, confidence=1.0, volatility=0.01, sentiment=1.0,
        )
        assert -3.0 <= score <= 3.0

    def test_zero_volatility_handled(self):
        from app.forecasting.models import kelly_opportunity_score
        score = kelly_opportunity_score(
            predicted_return=0.01, confidence=0.6, volatility=0.0,
        )
        assert isinstance(score, float)

    def test_backward_compat_alias(self):
        from app.forecasting.models import opportunity_score, kelly_opportunity_score
        assert opportunity_score is kelly_opportunity_score


class TestDirectionLabel:
    def test_thresholds(self):
        from app.forecasting.models import direction_label
        assert direction_label(0.01) == 2
        assert direction_label(0.003) == 2
        assert direction_label(0.001) == 1
        assert direction_label(-0.01) == 0
        assert direction_label(-0.003) == 0
        assert direction_label(0.0) == 1


class TestStockForecasterV3:
    def test_multi_horizon_train(self):
        from app.forecasting.models import StockForecaster
        df = _make_feature_df(300, horizons=[1, 5])
        model = StockForecaster("TEST")
        metrics = model.fit(df, horizons=[1, 5])

        assert "1d" in metrics
        assert "5d" in metrics
        assert metrics["1d"]["oof_rmse"] >= 0
        assert metrics["5d"]["oof_rmse"] >= 0

    def test_meta_weights_stored(self):
        from app.forecasting.models import StockForecaster
        df = _make_feature_df(300, horizons=[1])
        model = StockForecaster("TEST")
        metrics = model.fit(df, horizons=[1])

        assert "meta_weights" in metrics["1d"]
        assert len(metrics["1d"]["meta_weights"]) == 4  # 4 base models

    def test_predict_returns_dict(self):
        from app.forecasting.models import StockForecaster
        df = _make_feature_df(300, horizons=[1, 5])
        model = StockForecaster("TEST")
        model.fit(df, horizons=[1, 5])

        test_df = df.tail(10).drop(columns=[c for c in df.columns if c.startswith("target_")], errors="ignore")
        preds = model.predict(test_df)

        assert isinstance(preds, dict)
        assert 1 in preds
        assert 5 in preds
        assert len(preds[1]) == 10
        assert len(preds[5]) == 10

    def test_predict_1d_backward_compat(self):
        from app.forecasting.models import StockForecaster
        df = _make_feature_df(300, horizons=[1])
        model = StockForecaster("TEST")
        model.fit(df, horizons=[1])

        test_df = df.tail(5).drop(columns=[c for c in df.columns if c.startswith("target_")], errors="ignore")
        preds = model.predict_1d(test_df)

        assert isinstance(preds, pd.DataFrame)
        assert len(preds) == 5
        assert "predicted_return" in preds.columns

    def test_conformal_intervals(self):
        from app.forecasting.models import StockForecaster
        df = _make_feature_df(300, horizons=[1])
        model = StockForecaster("TEST")
        model.fit(df, horizons=[1])

        test_df = df.tail(5).drop(columns=[c for c in df.columns if c.startswith("target_")], errors="ignore")
        preds = model.predict(test_df)

        for _, row in preds[1].iterrows():
            assert row["lower_bound_95"] < row["predicted_return"] < row["upper_bound_95"]
            assert row["lower_bound_80"] < row["predicted_return"] < row["upper_bound_80"]
            # 95% interval should be wider than 80%
            assert (row["upper_bound_95"] - row["lower_bound_95"]) >= (row["upper_bound_80"] - row["lower_bound_80"])

    def test_confidence_in_range(self):
        from app.forecasting.models import StockForecaster
        df = _make_feature_df(300, horizons=[1])
        model = StockForecaster("TEST")
        model.fit(df, horizons=[1])

        test_df = df.tail(10).drop(columns=[c for c in df.columns if c.startswith("target_")], errors="ignore")
        preds = model.predict(test_df)

        for _, row in preds[1].iterrows():
            assert 0.0 <= row["confidence_score"] <= 1.0

    def test_direction_values(self):
        from app.forecasting.models import StockForecaster
        df = _make_feature_df(300, horizons=[1])
        model = StockForecaster("TEST")
        model.fit(df, horizons=[1])

        test_df = df.tail(20).drop(columns=[c for c in df.columns if c.startswith("target_")], errors="ignore")
        preds = model.predict(test_df)

        for _, row in preds[1].iterrows():
            assert row["predicted_direction"] in (-1, 0, 1)

    def test_model_save_load(self, tmp_path):
        from app.forecasting.models import StockForecaster
        import os

        df = _make_feature_df(300, horizons=[1, 5])
        model = StockForecaster("SAVETEST")

        with patch("app.forecasting.models.MODELS_DIR", str(tmp_path)):
            model.fit(df, horizons=[1, 5])
            path = model.save()
            assert os.path.exists(path)
            assert path.endswith(".pkl")

            loaded = StockForecaster.load("SAVETEST")
            assert loaded.horizons == [1, 5]
            assert len(loaded.models) == 2


class TestWalkForwardBacktestV3:
    def test_no_data_leakage(self):
        df = _make_feature_df(650)
        total = len(df)
        N_FOLDS, TEST_DAYS, TRAIN_MIN = 2, 60, 252

        fold_boundaries = []
        test_end_idx = total - 1
        for _ in range(N_FOLDS):
            test_start_idx = test_end_idx - TEST_DAYS + 1
            train_end_idx = test_start_idx - 1
            if train_end_idx < TRAIN_MIN:
                break
            fold_boundaries.insert(0, (0, train_end_idx, test_start_idx, test_end_idx))
            test_end_idx = test_start_idx - 1

        for (train_start, train_end, test_start, test_end) in fold_boundaries:
            assert train_end < test_start
            assert set(range(train_start, train_end + 1)).isdisjoint(
                set(range(test_start, test_end + 1))
            )

    def test_backtest_has_horizon_breakdown(self):
        from app.forecasting.backtesting import run_backtest

        df = _make_feature_df(650, horizons=[1, 5])
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(stock_id=1)

        with patch("app.forecasting.backtesting.build_feature_matrix", return_value=df), \
             patch("app.forecasting.backtesting.StockForecaster") as MockForecaster:

            mock_model = MagicMock()
            MockForecaster.return_value = mock_model

            n_test = 60
            mock_preds_1d = pd.DataFrame({
                "predicted_return": np.random.normal(0.001, 0.01, n_test),
                "confidence_score": np.random.uniform(0.4, 0.8, n_test),
                "opportunity_score": np.random.uniform(-1, 2, n_test),
            }, index=pd.date_range("2024-01-01", periods=n_test))

            mock_preds_5d = pd.DataFrame({
                "predicted_return": np.random.normal(0.003, 0.02, n_test),
                "confidence_score": np.random.uniform(0.3, 0.7, n_test),
                "opportunity_score": np.random.uniform(-1, 2, n_test),
            }, index=pd.date_range("2024-01-01", periods=n_test))

            mock_model.predict.return_value = {1: mock_preds_1d, 5: mock_preds_5d}

            result = run_backtest("AAPL", mock_db, n_folds=2, test_days=60,
                                 min_train_days=252, horizons=[1, 5], save_results=False)

        assert "horizons" in result
        assert "1d" in result["horizons"]
        assert "5d" in result["horizons"]

        required_keys = ["directional_accuracy", "sharpe_ratio", "max_drawdown", "alpha"]
        for key in required_keys:
            assert key in result, f"Missing top-level key: {key}"
            assert key in result["horizons"]["1d"], f"Missing 1d horizon key: {key}"
