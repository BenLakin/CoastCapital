"""Tests for portfolio optimizer: MVO constraints, Monte Carlo, covariance matrix."""
import pytest
import numpy as np
import pandas as pd
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from dataclasses import asdict


class TestOptimizePortfolio:
    def _make_cov_matrix(self, tickers: list[str]) -> pd.DataFrame:
        """Create a valid positive-definite covariance matrix."""
        n = len(tickers)
        np.random.seed(42)
        A = np.random.randn(n, n) * 0.01
        cov = A @ A.T + np.eye(n) * 0.0001  # ensure positive definite
        return pd.DataFrame(cov, index=tickers, columns=tickers)

    def test_weights_sum_to_one(self):
        from app.forecasting.portfolio import optimize_portfolio

        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        cov = self._make_cov_matrix(tickers)
        expected_returns = {t: np.random.uniform(-0.01, 0.03) for t in tickers}

        allocations = optimize_portfolio(expected_returns, cov, max_weight=0.20)

        total_weight = sum(a.weight for a in allocations)
        assert abs(total_weight - 1.0) < 0.01, f"Weights must sum to 1, got {total_weight}"

    def test_no_weight_exceeds_max(self):
        from app.forecasting.portfolio import optimize_portfolio

        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
        cov = self._make_cov_matrix(tickers)
        expected_returns = {"AAPL": 0.05, "MSFT": 0.03, "GOOGL": 0.02, "AMZN": 0.01, "NVDA": 0.04}

        allocations = optimize_portfolio(expected_returns, cov, max_weight=0.20)

        for a in allocations:
            assert a.weight <= 0.201, f"{a.ticker} weight {a.weight:.3f} exceeds max 20%"

    def test_long_only(self):
        from app.forecasting.portfolio import optimize_portfolio

        tickers = ["AAPL", "MSFT", "GOOGL"]
        cov = self._make_cov_matrix(tickers)
        expected_returns = {"AAPL": 0.02, "MSFT": -0.01, "GOOGL": 0.01}

        allocations = optimize_portfolio(expected_returns, cov, max_weight=0.50)

        for a in allocations:
            assert a.weight >= 0, f"{a.ticker} has negative weight {a.weight}"

    def test_dollars_match_weights(self):
        from app.forecasting.portfolio import optimize_portfolio

        tickers = ["AAPL", "MSFT", "GOOGL"]
        cov = self._make_cov_matrix(tickers)
        expected_returns = {t: 0.01 for t in tickers}
        capital = 100.0

        allocations = optimize_portfolio(expected_returns, cov, max_weight=0.50, initial_capital=capital)

        for a in allocations:
            expected_dollars = a.weight * capital
            assert abs(a.dollars - expected_dollars) < 0.01

    def test_custom_max_weight(self):
        from app.forecasting.portfolio import optimize_portfolio

        tickers = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
        cov = self._make_cov_matrix(tickers)
        expected_returns = {t: 0.01 for t in tickers}

        allocations = optimize_portfolio(expected_returns, cov, max_weight=0.10)

        for a in allocations:
            assert a.weight <= 0.101


class TestMonteCarloSimulation:
    def _setup(self):
        from app.forecasting.portfolio import PortfolioAllocation, monte_carlo_simulation

        tickers = ["AAPL", "MSFT", "GOOGL"]
        n_days = 252
        np.random.seed(42)

        returns_data = {
            t: np.random.normal(0.0005, 0.015, n_days)
            for t in tickers
        }
        returns_df = pd.DataFrame(returns_data,
                                  index=pd.date_range("2024-01-01", periods=n_days, freq="B"))

        cov_matrix = returns_df.cov()

        allocations = [
            PortfolioAllocation("AAPL", 0.4, 40, 0.01, 0.05, 0.7, 1.5),
            PortfolioAllocation("MSFT", 0.35, 35, 0.008, 0.04, 0.65, 1.2),
            PortfolioAllocation("GOOGL", 0.25, 25, 0.005, 0.02, 0.6, 0.8),
        ]

        return allocations, cov_matrix, returns_df, monte_carlo_simulation

    def test_mc_returns_valid_result(self):
        alloc, cov, ret_df, mc_sim = self._setup()
        result = mc_sim(alloc, cov, ret_df, holding_days=21, n_paths=500, initial_capital=100)

        assert result.mean_final_value > 0
        assert result.median_final_value > 0
        assert 0 <= result.prob_profit <= 1

    def test_mc_percentile_ordering(self):
        alloc, cov, ret_df, mc_sim = self._setup()
        result = mc_sim(alloc, cov, ret_df, holding_days=21, n_paths=1000, initial_capital=100)

        assert result.p10_final_value <= result.p25_final_value
        assert result.p25_final_value <= result.median_final_value
        assert result.median_final_value <= result.p75_final_value
        assert result.p75_final_value <= result.p90_final_value

    def test_mc_daily_path_length(self):
        alloc, cov, ret_df, mc_sim = self._setup()
        holding = 21
        result = mc_sim(alloc, cov, ret_df, holding_days=holding, n_paths=100, initial_capital=100)

        # Path should have holding_days + 1 points (day 0 + 21 days)
        assert len(result.daily_mean_path) == holding + 1
        assert len(result.daily_p10_path) == holding + 1
        assert len(result.daily_p90_path) == holding + 1

    def test_mc_initial_value_correct(self):
        alloc, cov, ret_df, mc_sim = self._setup()
        result = mc_sim(alloc, cov, ret_df, holding_days=21, n_paths=100, initial_capital=100)

        assert result.daily_mean_path[0] == 100.0
        assert result.daily_p10_path[0] == 100.0

    def test_mc_max_drawdown_negative(self):
        alloc, cov, ret_df, mc_sim = self._setup()
        result = mc_sim(alloc, cov, ret_df, holding_days=21, n_paths=500, initial_capital=100)

        assert result.max_drawdown_mean <= 0

    def test_mc_optimal_exit_day_in_range(self):
        alloc, cov, ret_df, mc_sim = self._setup()
        holding = 21
        result = mc_sim(alloc, cov, ret_df, holding_days=holding, n_paths=100, initial_capital=100)

        assert 0 <= result.optimal_exit_day <= holding


class TestCovarianceMatrix:
    def test_ledoit_wolf_positive_definite(self):
        """Ledoit-Wolf shrinkage should produce a positive-definite matrix."""
        np.random.seed(42)
        n_days, n_stocks = 100, 5
        tickers = ["A", "B", "C", "D", "E"]
        returns = pd.DataFrame(
            np.random.normal(0, 0.015, (n_days, n_stocks)),
            columns=tickers,
            index=pd.date_range("2024-01-01", periods=n_days),
        )

        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf()
        lw.fit(returns.values)
        cov = lw.covariance_

        eigenvalues = np.linalg.eigvalsh(cov)
        assert all(ev > 0 for ev in eigenvalues), "Covariance matrix should be positive definite"

    def test_covariance_matrix_symmetric(self):
        np.random.seed(42)
        n_days, n_stocks = 100, 3
        tickers = ["X", "Y", "Z"]
        returns = pd.DataFrame(
            np.random.normal(0, 0.015, (n_days, n_stocks)),
            columns=tickers,
            index=pd.date_range("2024-01-01", periods=n_days),
        )

        from sklearn.covariance import LedoitWolf
        lw = LedoitWolf()
        lw.fit(returns.values)
        cov = lw.covariance_

        assert np.allclose(cov, cov.T), "Covariance matrix should be symmetric"
