"""Tests for database schema and models."""
import pytest
from datetime import date, datetime
from unittest.mock import MagicMock, patch
from app.models.schema import (
    DimStock, DimDate, FactStockPrice, FactTechnicalIndicator,
    FactStockNews, FactEarnings, FactForecast, FactBacktestResult, FactStockSplit
)


class TestDimStock:
    def test_create_dim_stock(self):
        stock = DimStock(
            ticker="AAPL",
            company_name="Apple Inc.",
            exchange="NASDAQ",
            sector="Technology",
            industry="Consumer Electronics",
            country="USA",
            currency="USD",
            market_cap_category="Mega",
            is_active=True,
            is_etf=False,
        )
        assert stock.ticker == "AAPL"
        assert stock.company_name == "Apple Inc."
        assert stock.sector == "Technology"
        assert stock.is_etf is False

    def test_repr(self):
        stock = DimStock(ticker="MSFT")
        assert "MSFT" in repr(stock)


class TestDimDate:
    def test_create_dim_date(self):
        d = DimDate(
            date_id=20240101,
            date=date(2024, 1, 1),
            year=2024,
            quarter=1,
            month=1,
            month_name="January",
            week_of_year=1,
            day_of_month=1,
            day_of_week=0,
            day_name="Monday",
            is_weekend=False,
            is_trading_day=True,
            is_quarter_end=False,
            is_year_end=False,
        )
        assert d.date_id == 20240101
        assert d.is_trading_day is True
        assert d.is_weekend is False


class TestFactStockPrice:
    def test_create_price_record(self):
        price = FactStockPrice(
            stock_id=1,
            trade_date=date(2024, 1, 15),
            open_raw=185.0,
            high_raw=187.5,
            low_raw=184.0,
            close_raw=186.5,
            volume_raw=55_000_000,
            open_adj=185.0,
            high_adj=187.5,
            low_adj=184.0,
            close_adj=186.5,
            volume_adj=55_000_000,
            daily_return=0.012,
            log_return=0.0119,
            data_source="yfinance",
        )
        assert price.close_adj == 186.5
        assert price.daily_return == 0.012
        assert price.data_source == "yfinance"


class TestFactForecast:
    def test_create_forecast(self):
        f = FactForecast(
            stock_id=1,
            ticker="AAPL",
            forecast_date=date(2024, 1, 15),
            target_date=date(2024, 1, 16),
            model_name="lgbm_xgb_ensemble",
            model_version="v2.0",
            predicted_return=0.015,
            predicted_direction=1,
            confidence_score=0.72,
            opportunity_score=1.45,
        )
        assert f.predicted_direction == 1
        assert f.confidence_score == 0.72

    def test_directional_accuracy_tracking(self):
        f = FactForecast(
            stock_id=1,
            ticker="NVDA",
            forecast_date=date(2024, 1, 15),
            target_date=date(2024, 1, 16),
            model_name="lgbm_xgb_ensemble",
            predicted_return=0.02,
            predicted_direction=1,
            actual_return=0.018,
            actual_direction=1,
            was_correct=True,
        )
        assert f.was_correct is True


class TestFactStockSplit:
    def test_split_record(self):
        split = FactStockSplit(
            stock_id=1,
            ticker="NVDA",
            split_date=date(2021, 7, 19),
            split_ratio=4.0,
            numerator=4,
            denominator=1,
            history_restated=True,
            data_source="yfinance",
        )
        assert split.split_ratio == 4.0
        assert split.history_restated is True


class TestFactBacktestResult:
    def test_backtest_result(self):
        bt = FactBacktestResult(
            run_date=date(2024, 1, 15),
            model_name="lgbm_xgb_ensemble",
            model_version="v2.0",
            tickers_tested=["AAPL"],
            n_folds=4,
            directional_accuracy=0.58,
            sharpe_ratio=1.42,
            max_drawdown=-0.12,
            alpha=0.08,
            win_rate=0.55,
        )
        assert bt.directional_accuracy == 0.58
        assert bt.sharpe_ratio == 1.42
