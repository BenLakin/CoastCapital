"""Tests for market data routes (market_routes.py)."""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timezone


@pytest.fixture
def app():
    """Create test Flask app with market blueprint registered."""
    with patch("app.models.database.create_db_engine", return_value=MagicMock()):
        from app import create_app
        application = create_app()
        application.config["TESTING"] = True
        yield application


@pytest.fixture
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close_df(tickers, periods=30, base=100.0):
    """Return a multi-ticker Close DataFrame mimicking yfinance output."""
    dates = pd.bdate_range(end="2024-03-01", periods=periods)
    data = {t: base + np.random.randn(periods).cumsum() for t in tickers}
    return pd.DataFrame(data, index=dates)


def _make_volume_df(tickers, periods=30):
    dates = pd.bdate_range(end="2024-03-01", periods=periods)
    data = {t: (np.random.randint(1_000_000, 5_000_000, periods)).astype(float) for t in tickers}
    return pd.DataFrame(data, index=dates)


def _make_ohlcv_multiindex(tickers, periods=30):
    """MultiIndex DataFrame as returned by yf.download for multiple tickers."""
    closes  = _make_close_df(tickers, periods)
    volumes = _make_volume_df(tickers, periods)
    combined = pd.concat({"Close": closes, "Volume": volumes}, axis=1)
    return combined


# ---------------------------------------------------------------------------
# /api/v1/market/status
# ---------------------------------------------------------------------------

class TestMarketStatus:
    def test_returns_json_with_open_key(self, client):
        resp = client.get("/api/v1/market/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "open" in data
        assert isinstance(data["open"], bool)

    def test_has_timestamp(self, client):
        resp = client.get("/api/v1/market/status")
        data = resp.get_json()
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# /api/v1/market/overview
# ---------------------------------------------------------------------------

class TestMarketOverview:
    def _mock_overview_download(self, *args, **kwargs):
        tickers = ["SPY", "QQQ", "DIA", "IWM", "^VIX", "GLD", "USO",
                   "BTC-USD", "^TNX", "^IRX", "DX-Y.NYB"]
        closes  = _make_close_df(tickers, periods=5)
        volumes = _make_volume_df(tickers, periods=5)
        raw = pd.concat({"Close": closes, "Open": closes * 0.99,
                          "High": closes * 1.01, "Low": closes * 0.98,
                          "Volume": volumes}, axis=1)
        return raw

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_overview_returns_list(self, mock_set, mock_get, client):
        with patch("yfinance.download", side_effect=self._mock_overview_download):
            resp = client.get("/api/v1/market/overview")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert len(data) > 0

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_overview_has_required_fields(self, mock_set, mock_get, client):
        with patch("yfinance.download", side_effect=self._mock_overview_download):
            resp = client.get("/api/v1/market/overview")
        item = resp.get_json()[0]
        for field in ("ticker", "price", "change_pct"):
            assert field in item, f"Missing field: {field}"

    def test_overview_uses_cache(self, client):
        cached = [{"ticker": "SPY", "price": 500.0, "change_pct": 0.5}]
        with patch("app.routes.market_routes._cache_get", return_value=cached):
            resp = client.get("/api/v1/market/overview")
        assert resp.status_code == 200
        assert resp.get_json() == cached


# ---------------------------------------------------------------------------
# /api/v1/market/movers
# ---------------------------------------------------------------------------

class TestMarketMovers:
    def _mock_movers_download(self, *args, **kwargs):
        from app.routes.market_routes import FORTUNE_500_TICKERS
        unique = list(dict.fromkeys(FORTUNE_500_TICKERS))[:10]
        closes  = _make_close_df(unique, periods=22)
        volumes = _make_volume_df(unique, periods=22)
        return pd.concat({"Close": closes, "Volume": volumes}, axis=1)

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_movers_structure(self, mock_set, mock_get, client):
        with patch("yfinance.download", side_effect=self._mock_movers_download):
            resp = client.get("/api/v1/market/movers")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "gainers" in data
        assert "losers"  in data
        assert "big_noise" in data

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_movers_gainers_sorted_desc(self, mock_set, mock_get, client):
        with patch("yfinance.download", side_effect=self._mock_movers_download):
            resp = client.get("/api/v1/market/movers")
        gainers = resp.get_json().get("gainers", [])
        if len(gainers) > 1:
            pcts = [g["change_pct"] for g in gainers]
            assert pcts == sorted(pcts, reverse=True)

    def test_movers_uses_cache(self, client):
        cached = {"gainers": [], "losers": [], "big_noise": []}
        with patch("app.routes.market_routes._cache_get", return_value=cached):
            resp = client.get("/api/v1/market/movers")
        assert resp.get_json() == cached


# ---------------------------------------------------------------------------
# /api/v1/market/watchlist
# ---------------------------------------------------------------------------

class TestWatchlist:
    def _mock_watchlist_download(self, tickers_str, *args, **kwargs):
        tickers = tickers_str.split() if isinstance(tickers_str, str) else tickers_str
        closes  = _make_close_df(tickers, periods=30)
        volumes = _make_volume_df(tickers, periods=30)
        # Mimic MultiIndex structure for multiple tickers
        if len(tickers) > 1:
            return pd.concat({"Close": closes, "Volume": volumes}, axis=1)
        else:
            # Single ticker returns flat DataFrame
            df = pd.DataFrame({"Close": closes[tickers[0]], "Volume": volumes[tickers[0]]},
                               index=closes.index)
            return df

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_watchlist_returns_list(self, mock_set, mock_get, client):
        with patch("yfinance.download", side_effect=self._mock_watchlist_download):
            resp = client.get("/api/v1/market/watchlist?tickers=AAPL,MSFT")
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_watchlist_has_sparkline(self, mock_set, mock_get, client):
        with patch("yfinance.download", side_effect=self._mock_watchlist_download):
            resp = client.get("/api/v1/market/watchlist?tickers=AAPL,MSFT")
        data = resp.get_json()
        if data:
            assert "sparkline" in data[0]
            assert isinstance(data[0]["sparkline"], list)

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_watchlist_default_tickers_when_none_provided(self, mock_set, mock_get, client):
        with patch("yfinance.download", side_effect=self._mock_watchlist_download):
            resp = client.get("/api/v1/market/watchlist")
        assert resp.status_code == 200

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_watchlist_empty_download_returns_empty_list(self, mock_set, mock_get, client):
        with patch("yfinance.download", return_value=pd.DataFrame()):
            resp = client.get("/api/v1/market/watchlist?tickers=FAKE")
        assert resp.status_code == 200
        assert resp.get_json() == []


# ---------------------------------------------------------------------------
# /api/v1/market/headlines
# ---------------------------------------------------------------------------

class TestHeadlines:
    def _mock_ticker_news(self):
        return [
            {
                "title": "Test headline",
                "publisher": "Reuters",
                "link": "https://example.com/article",
                "providerPublishTime": 1700000000,
                "type": "STORY",
            }
        ]

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_headlines_returns_dict(self, mock_set, mock_get, client):
        mock_ticker = MagicMock()
        mock_ticker.news = self._mock_ticker_news()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            resp = client.get("/api/v1/market/headlines?tickers=AAPL")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "AAPL" in data

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_headlines_article_fields(self, mock_set, mock_get, client):
        mock_ticker = MagicMock()
        mock_ticker.news = self._mock_ticker_news()
        with patch("yfinance.Ticker", return_value=mock_ticker):
            resp = client.get("/api/v1/market/headlines?tickers=AAPL")
        articles = resp.get_json().get("AAPL", [])
        if articles:
            for field in ("title", "publisher", "link", "published_at"):
                assert field in articles[0], f"Missing field: {field}"

    @patch("app.routes.market_routes._cache_get", return_value=None)
    @patch("app.routes.market_routes._cache_set")
    def test_headlines_no_tickers_returns_empty(self, mock_set, mock_get, client):
        resp = client.get("/api/v1/market/headlines")
        assert resp.status_code == 200
        assert resp.get_json() == {}

    def test_headlines_uses_cache(self, client):
        cached = {"AAPL": [{"title": "Cached", "publisher": "Test",
                             "link": "https://x.com", "published_at": "2024-01-01"}]}
        with patch("app.routes.market_routes._cache_get", return_value=cached):
            resp = client.get("/api/v1/market/headlines?tickers=AAPL")
        assert resp.get_json() == cached


# ---------------------------------------------------------------------------
# /dashboard (serves HTML)
# ---------------------------------------------------------------------------

class TestDashboardPage:
    def test_dashboard_redirects_or_200(self, client):
        # May be 200 (static file) or 302/308 (redirect from root)
        resp = client.get("/dashboard")
        assert resp.status_code in (200, 302, 308)

    def test_dashboard_content_type_html(self, client):
        resp = client.get("/dashboard")
        if resp.status_code == 200:
            assert "text/html" in resp.content_type
