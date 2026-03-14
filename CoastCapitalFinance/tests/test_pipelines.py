"""Tests for data ingestion pipelines."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
import numpy as np


class TestUpsertDimStock:
    @patch("app.pipelines.ingestion.yf.Ticker")
    def test_upsert_new_stock(self, mock_yf_ticker):
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "longName": "Apple Inc.",
            "exchange": "NASDAQ",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "country": "USA",
            "currency": "USD",
            "marketCap": 3_000_000_000_000,
            "quoteType": "EQUITY",
        }
        mock_yf_ticker.return_value = mock_ticker

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        from app.pipelines.ingestion import upsert_dim_stock
        from app.models.schema import DimStock

        with patch("app.pipelines.ingestion.DimStock") as MockDimStock:
            MockDimStock.return_value = MagicMock()
            mock_stock = MockDimStock.return_value
            mock_db.query.return_value.filter.return_value.first.return_value = None

            # Create a real DimStock to add
            new_stock = DimStock(ticker="AAPL")
            mock_db.query.return_value.filter.return_value.first.side_effect = [None, new_stock]

            result = upsert_dim_stock("AAPL", mock_db)
            mock_db.add.assert_called_once()
            mock_db.flush.assert_called()

    @patch("app.pipelines.ingestion.yf.Ticker")
    def test_market_cap_classification(self, mock_yf_ticker):
        """Test that market cap is correctly classified into categories."""
        from app.pipelines.ingestion import upsert_dim_stock
        from app.models.schema import DimStock

        test_cases = [
            (300_000_000_000, "Mega"),
            (15_000_000_000, "Large"),
            (3_000_000_000, "Mid"),
            (500_000_000, "Small"),
            (100_000_000, "Micro"),
            (10_000_000, "Nano"),
        ]

        for market_cap, expected_cat in test_cases:
            mock_ticker = MagicMock()
            mock_ticker.info = {
                "longName": "Test Corp",
                "exchange": "NYSE",
                "marketCap": market_cap,
                "quoteType": "EQUITY",
            }
            mock_yf_ticker.return_value = mock_ticker

            mock_db = MagicMock()
            existing = DimStock(ticker="TEST")
            mock_db.query.return_value.filter.return_value.first.return_value = existing

            result = upsert_dim_stock("TEST", mock_db)
            assert existing.market_cap_category == expected_cat, \
                f"Market cap {market_cap} should be {expected_cat}, got {existing.market_cap_category}"


class TestFetchPrices:
    @patch("app.pipelines.ingestion.yf.Ticker")
    def test_fetch_prices_returns_count(self, mock_yf_ticker):
        """Test that price fetching returns correct row count."""
        from app.pipelines.ingestion import fetch_and_store_prices
        from app.models.schema import DimStock, FactStockPrice

        # Mock yfinance data
        dates = pd.date_range("2024-01-02", periods=5, freq="B")
        hist_data = pd.DataFrame({
            "Open": [180.0, 181.0, 182.0, 183.0, 184.0],
            "High": [182.0, 183.0, 184.0, 185.0, 186.0],
            "Low": [179.0, 180.0, 181.0, 182.0, 183.0],
            "Close": [181.0, 182.0, 183.0, 184.0, 185.0],
            "Volume": [50_000_000] * 5,
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist_data
        mock_yf_ticker.return_value = mock_ticker

        mock_db = MagicMock()
        mock_stock = DimStock(ticker="AAPL", stock_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_stock
        # No existing price records
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

        with patch("app.pipelines.ingestion.populate_dim_date"):
            result = fetch_and_store_prices(
                "AAPL",
                date(2024, 1, 2),
                date(2024, 1, 8),
                mock_db,
            )

        assert result == 5
        assert mock_db.add.call_count == 5

    @patch("app.pipelines.ingestion.yf.Ticker")
    def test_fetch_prices_ticker_not_found(self, mock_yf_ticker):
        """Test that ValueError raised when ticker not in dim_stock."""
        from app.pipelines.ingestion import fetch_and_store_prices

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not in dim_stock"):
            fetch_and_store_prices("UNKNOWN", date(2024, 1, 1), date(2024, 1, 5), mock_db)


class TestSplitHandling:
    @patch("app.pipelines.ingestion.yf.Ticker")
    def test_detects_split(self, mock_yf_ticker):
        """Test that splits are detected and recorded."""
        from app.pipelines.ingestion import check_and_handle_splits
        from app.models.schema import DimStock, FactStockSplit

        dates = pd.date_range("2021-07-01", periods=30, freq="B")
        hist_data = pd.DataFrame({
            "Close": [600.0] * 30,
            "Stock Splits": [0.0] * 18 + [4.0] + [0.0] * 11,
        }, index=dates)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = hist_data
        mock_yf_ticker.return_value = mock_ticker

        mock_db = MagicMock()
        mock_stock = DimStock(ticker="NVDA", stock_id=1)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_stock,  # DimStock lookup
            None,        # No existing FactStockSplit
        ]

        with patch("app.pipelines.ingestion._restate_prices_after_split"):
            splits = check_and_handle_splits("NVDA", mock_db)

        assert len(splits) == 1
        assert splits[0]["ratio"] == 4.0


class TestMacroIngestion:
    @patch("app.pipelines.ingestion.yf.download")
    def test_macro_data_stored(self, mock_download):
        """Test that macro indicators are correctly stored."""
        from app.pipelines.ingestion import fetch_and_store_macro
        from app.models.schema import FactMacroIndicator

        dates = pd.DatetimeIndex([pd.Timestamp("2024-01-15")])
        mock_download.return_value = pd.DataFrame(
            {"Close": [18.5]}, index=dates
        )

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = fetch_and_store_macro(date(2024, 1, 15), date(2024, 1, 15), mock_db)
        # Should have attempted to add macro records
        assert mock_db.flush.called


class TestTechnicals:
    def test_compute_technicals_insufficient_data(self):
        """Test graceful handling when not enough price data."""
        from app.pipelines.technicals import compute_and_store_technicals
        from app.models.schema import DimStock

        mock_db = MagicMock()
        mock_stock = DimStock(ticker="AAPL", stock_id=1)
        mock_db.query.return_value.filter.return_value.first.return_value = mock_stock

        # Return only 10 price records (not enough)
        mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = [
            MagicMock(trade_date=date(2024, 1, i),
                     open_adj=180.0, high_adj=182.0, low_adj=179.0,
                     close_adj=181.0, volume_adj=50_000_000)
            for i in range(1, 11)
        ]

        result = compute_and_store_technicals("AAPL", date(2024, 1, 1), date(2024, 1, 10), mock_db)
        assert result == 0  # Should return 0 due to insufficient data
