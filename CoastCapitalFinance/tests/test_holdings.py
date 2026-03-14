"""Tests for holdings analyzer: tax computation, sell/hold classification, long-term threshold."""
import pytest
import numpy as np
from datetime import date, timedelta


class TestComputeTaxImpact:
    def test_short_term_gain(self):
        from app.forecasting.holdings import compute_tax_impact

        result = compute_tax_impact(
            shares=10, cost_basis=100.0, current_price=120.0,
            purchase_date=date.today() - timedelta(days=100),
        )

        assert not result.is_long_term
        assert result.tax_rate == 0.37
        assert result.gain_loss == 200.0  # 10 * (120 - 100)
        assert result.tax_liability == 200.0 * 0.37  # 74.0
        assert result.after_tax_proceeds == 1200.0 - 74.0  # 1126.0
        assert result.days_to_long_term > 0

    def test_long_term_gain(self):
        from app.forecasting.holdings import compute_tax_impact

        result = compute_tax_impact(
            shares=10, cost_basis=100.0, current_price=150.0,
            purchase_date=date.today() - timedelta(days=400),
        )

        assert result.is_long_term
        assert result.tax_rate == 0.20
        assert result.gain_loss == 500.0
        assert result.tax_liability == 500.0 * 0.20  # 100.0
        assert result.days_to_long_term == 0

    def test_loss_generates_tax_benefit(self):
        from app.forecasting.holdings import compute_tax_impact

        result = compute_tax_impact(
            shares=10, cost_basis=100.0, current_price=80.0,
            purchase_date=date.today() - timedelta(days=200),
        )

        assert result.gain_loss == -200.0
        assert result.tax_liability < 0  # tax benefit
        assert result.after_tax_proceeds > 800.0  # proceeds + tax benefit

    def test_breakeven_no_tax(self):
        from app.forecasting.holdings import compute_tax_impact

        result = compute_tax_impact(
            shares=5, cost_basis=50.0, current_price=50.0,
            purchase_date=date.today() - timedelta(days=30),
        )

        assert result.gain_loss == 0
        assert result.tax_liability == 0
        assert result.after_tax_proceeds == 250.0  # 5 * 50

    def test_custom_tax_rates(self):
        from app.forecasting.holdings import compute_tax_impact

        result = compute_tax_impact(
            shares=10, cost_basis=100.0, current_price=120.0,
            purchase_date=date.today() - timedelta(days=100),
            short_term_rate=0.25,
            long_term_rate=0.15,
        )

        assert result.tax_rate == 0.25
        assert result.tax_liability == 200.0 * 0.25

    def test_days_to_long_term_calculation(self):
        from app.forecasting.holdings import compute_tax_impact

        # Exactly 320 days held — 45 days to long-term
        result = compute_tax_impact(
            shares=1, cost_basis=100.0, current_price=110.0,
            purchase_date=date.today() - timedelta(days=320),
        )

        assert not result.is_long_term
        assert result.days_to_long_term == 45


class TestAnalyzeHolding:
    def test_strong_hold_near_long_term_threshold(self):
        from app.forecasting.holdings import analyze_holding, HoldingInput

        holding = HoldingInput(
            ticker="AAPL", shares=10, cost_basis=150.0,
            purchase_date=date.today() - timedelta(days=340),  # 25 days from long-term
        )

        analysis = analyze_holding(
            holding=holding,
            current_price=170.0,
            predicted_return_5d=0.005,  # slightly positive (not deeply bearish)
            confidence=0.6,
        )

        assert analysis.recommendation == "STRONG_HOLD"
        assert "long-term" in analysis.recommendation_reason.lower()

    def test_sell_when_bearish_high_confidence(self):
        from app.forecasting.holdings import analyze_holding, HoldingInput

        holding = HoldingInput(
            ticker="TSLA", shares=5, cost_basis=200.0,
            purchase_date=date.today() - timedelta(days=60),
        )

        analysis = analyze_holding(
            holding=holding,
            current_price=180.0,
            predicted_return_5d=-0.03,  # bearish
            confidence=0.75,           # high confidence
        )

        assert analysis.recommendation == "SELL"

    def test_hold_with_no_strong_signal(self):
        from app.forecasting.holdings import analyze_holding, HoldingInput

        holding = HoldingInput(
            ticker="MSFT", shares=8, cost_basis=300.0,
            purchase_date=date.today() - timedelta(days=500),  # long-term
        )

        analysis = analyze_holding(
            holding=holding,
            current_price=310.0,
            predicted_return_5d=0.001,  # weak positive
            confidence=0.5,
        )

        assert analysis.recommendation == "HOLD"

    def test_market_value_correct(self):
        from app.forecasting.holdings import analyze_holding, HoldingInput

        holding = HoldingInput(
            ticker="AAPL", shares=10, cost_basis=150.0,
            purchase_date=date.today() - timedelta(days=100),
        )

        analysis = analyze_holding(holding, current_price=160.0)

        assert analysis.market_value == 1600.0
        assert analysis.current_price == 160.0

    def test_net_advantage_calculated(self):
        from app.forecasting.holdings import analyze_holding, HoldingInput

        holding = HoldingInput(
            ticker="NVDA", shares=5, cost_basis=800.0,
            purchase_date=date.today() - timedelta(days=200),
        )

        analysis = analyze_holding(
            holding, current_price=900.0,
            predicted_return_5d=0.02, confidence=0.7,
        )

        # Expected hold value should be higher since bullish
        assert analysis.expected_value_if_hold_1m > 0
        assert analysis.after_tax_sell_now > 0

    def test_deeply_bearish_overrides_strong_hold(self):
        """Even near long-term threshold, deep bearishness should trigger SELL."""
        from app.forecasting.holdings import analyze_holding, HoldingInput

        holding = HoldingInput(
            ticker="META", shares=10, cost_basis=300.0,
            purchase_date=date.today() - timedelta(days=340),  # near long-term
        )

        analysis = analyze_holding(
            holding, current_price=280.0,
            predicted_return_5d=-0.05,  # very bearish
            confidence=0.80,           # very high confidence
        )

        # Deeply bearish should override the STRONG_HOLD
        assert analysis.recommendation == "SELL"


class TestAnalyzeHoldingsBatch:
    """Test the batch analyze_holdings function with mocked DB and yfinance."""

    def test_empty_holdings_list(self):
        from app.forecasting.holdings import analyze_holdings

        with pytest.raises(Exception):
            # Should handle gracefully or raise
            analyze_holdings(holdings=[], db=None)

    def test_portfolio_summary_fields(self):
        from app.forecasting.holdings import analyze_holdings, HoldingInput
        from unittest.mock import patch, MagicMock
        import pandas as pd

        holdings = [
            {"ticker": "AAPL", "shares": 10, "cost_basis": 150.0, "purchase_date": "2024-06-15"},
            {"ticker": "MSFT", "shares": 5, "cost_basis": 300.0, "purchase_date": "2025-01-10"},
        ]

        mock_db = MagicMock()
        mock_stock = MagicMock()
        mock_stock.stock_id = 1
        mock_db.query.return_value.filter.return_value.first.return_value = mock_stock
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        # Mock yfinance
        mock_close = pd.DataFrame(
            {"AAPL": [170.0], "MSFT": [320.0]},
            index=[date.today()],
        )
        mock_download_data = pd.DataFrame({
            ("Close", "AAPL"): [170.0],
            ("Close", "MSFT"): [320.0],
        }, index=[date.today()])
        mock_download_data.columns = pd.MultiIndex.from_tuples([("Close", "AAPL"), ("Close", "MSFT")])

        with patch("app.forecasting.holdings.yf.download", return_value=mock_download_data):
            result = analyze_holdings(holdings=holdings, db=mock_db)

        assert "portfolio_summary" in result
        assert "holdings" in result
        assert "tax_rates_used" in result
        assert "disclaimer" in result

        summary = result["portfolio_summary"]
        assert "total_market_value" in summary
        assert "total_gain_loss" in summary
        assert "positions_to_sell" in summary
