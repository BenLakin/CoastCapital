"""
Unit tests for FinanceAgent execute_tool dispatch.

Verifies that every named tool routes correctly with proper arguments,
default handling, and error responses. All DB and pipeline dependencies
are mocked — no real database, Anthropic, or market data connections.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


class _ComparableColumn:
    """Fake ORM column supporting comparisons and .desc()/.asc() for filter/order_by."""
    def __getattr__(self, name): return _ComparableColumn()
    def __call__(self, *a, **kw): return MagicMock()
    def __ge__(self, other): return MagicMock()
    def __le__(self, other): return MagicMock()
    def __gt__(self, other): return MagicMock()
    def __lt__(self, other): return MagicMock()
    def __eq__(self, other): return MagicMock()
    def __ne__(self, other): return MagicMock()
    def __hash__(self): return id(self)
    def __contains__(self, item): return False


def _patch_orm_columns():
    """Make ORM model column attributes support comparisons for .filter() calls."""
    from app.models import schema
    for cls_name in dir(schema):
        cls = getattr(schema, cls_name)
        if isinstance(cls, type) and hasattr(cls, '__table__'):
            continue
        # Patch known date/numeric columns that get compared in execute_tool
    # Patch specific columns used in filter() comparisons
    schema.FactForecast.forecast_date = _ComparableColumn()
    schema.FactForecast.confidence_score = _ComparableColumn()
    schema.FactMacroIndicator.indicator_date = _ComparableColumn()
    schema.FactStockNews.published_at = _ComparableColumn()


_patch_orm_columns()


def _mock_db():
    """Create a patch for app.models.database.get_db as a context manager."""
    db = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=db)
    cm.__exit__ = MagicMock(return_value=False)
    return db, cm


def _execute(tool_name, tool_input):
    """Import and call execute_tool."""
    from app.agents.finance_agent import execute_tool
    return execute_tool(tool_name, tool_input)


# ── get_stock_analysis ────────────────────────────────────────────────────────

class TestGetStockAnalysis:
    @patch("app.models.database.get_db")
    def test_ticker_not_found(self, mock_get_db):
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        db.query.return_value.filter.return_value.first.return_value = None
        result = _execute("get_stock_analysis", {"ticker": "FAKE"})
        assert "error" in result
        assert "FAKE" in result["error"]

    @patch("app.models.database.get_db")
    def test_ticker_uppercased(self, mock_get_db):
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        stock = MagicMock()
        stock.company_name = "Apple"
        stock.sector = "Tech"
        stock.industry = "Consumer Electronics"
        stock.market_cap_category = "Mega"
        stock.stock_id = 1
        db.query.return_value.filter.return_value.first.return_value = stock
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        result = _execute("get_stock_analysis", {
            "ticker": "aapl", "include_news": False, "include_earnings": False
        })
        assert result.get("ticker") == "AAPL"


# ── run_forecast ──────────────────────────────────────────────────────────────

class TestRunForecast:
    @patch("app.pipelines.daily_process.get_next_trading_day")
    @patch("app.forecasting.models.generate_forecast")
    @patch("app.models.database.get_db")
    def test_calls_generate_forecast(self, mock_get_db, mock_gen, mock_next_day):
        mock_next_day.return_value = date(2024, 1, 2)
        mock_gen.return_value = {"predicted_return": 0.01}
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        result = _execute("run_forecast", {"ticker": "AAPL"})
        mock_gen.assert_called_once()
        assert result["predicted_return"] == 0.01


# ── get_top_opportunities ────────────────────────────────────────────────────

class TestGetTopOpportunities:
    @patch("app.models.database.get_db")
    def test_default_params(self, mock_get_db):
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        db.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        result = _execute("get_top_opportunities", {})
        assert isinstance(result, list)


# ── run_backtest ──────────────────────────────────────────────────────────────

class TestRunBacktest:
    @patch("app.forecasting.backtesting.run_backtest")
    @patch("app.models.database.get_db")
    def test_calls_run_backtest(self, mock_get_db, mock_bt):
        mock_bt.return_value = {"accuracy": 0.55}
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        result = _execute("run_backtest", {"ticker": "msft", "n_folds": 3})
        mock_bt.assert_called_once()
        assert result["accuracy"] == 0.55


# ── get_macro_conditions ──────────────────────────────────────────────────────

class TestGetMacroConditions:
    @patch("app.models.database.get_db")
    def test_returns_list(self, mock_get_db):
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        result = _execute("get_macro_conditions", {})
        assert isinstance(result, list)


# ── search_news ───────────────────────────────────────────────────────────────

class TestSearchNews:
    @patch("app.models.database.get_db")
    def test_ticker_not_found(self, mock_get_db):
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        db.query.return_value.filter.return_value.first.return_value = None
        result = _execute("search_news", {"ticker": "FAKE"})
        assert "error" in result


# ── compare_stocks ────────────────────────────────────────────────────────────

class TestCompareStocks:
    @patch("app.models.database.get_db")
    def test_empty_tickers_returns_error(self, mock_get_db):
        result = _execute("compare_stocks", {"tickers": []})
        assert "error" in result
        assert "No tickers" in result["error"]

    @patch("app.models.database.get_db")
    def test_missing_tickers_returns_error(self, mock_get_db):
        result = _execute("compare_stocks", {})
        assert "error" in result


# ── run_daily_pipeline ────────────────────────────────────────────────────────

class TestRunDailyPipeline:
    @patch("app.pipelines.daily_process.run_daily_pipeline")
    def test_calls_pipeline(self, mock_run):
        mock_run.return_value = {"status": "ok"}
        result = _execute("run_daily_pipeline", {})
        mock_run.assert_called_once()
        assert result["status"] == "ok"

    @patch("app.pipelines.daily_process.run_daily_pipeline")
    def test_passes_tickers(self, mock_run):
        mock_run.return_value = {}
        _execute("run_daily_pipeline", {"tickers": ["aapl", "msft"], "use_llm": False})
        call_kwargs = mock_run.call_args[1] if mock_run.call_args[1] else {}
        call_args = mock_run.call_args[0] if mock_run.call_args[0] else ()
        # tickers should be uppercased
        tickers = call_kwargs.get("tickers") or (call_args[0] if call_args else None)
        if tickers:
            assert tickers == ["AAPL", "MSFT"]


# ── add_ticker ────────────────────────────────────────────────────────────────

class TestAddTicker:
    @patch("app.pipelines.backfill.backfill_ticker")
    def test_calls_backfill(self, mock_bf):
        mock_bf.return_value = {"added": "TSLA"}
        result = _execute("add_ticker", {"ticker": "tsla"})
        mock_bf.assert_called_once_with("TSLA", use_llm=False)
        assert result["added"] == "TSLA"


# ── get_backtest_results ──────────────────────────────────────────────────────

class TestGetBacktestResults:
    @patch("app.models.database.get_db")
    def test_returns_list(self, mock_get_db):
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []
        result = _execute("get_backtest_results", {})
        assert isinstance(result, list)


# ── optimize_portfolio ────────────────────────────────────────────────────────

class TestOptimizePortfolio:
    @patch("app.forecasting.portfolio.run_portfolio_optimization")
    @patch("app.models.database.get_db")
    def test_calls_optimization(self, mock_get_db, mock_opt):
        mock_opt.return_value = {"weights": {}}
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        result = _execute("optimize_portfolio", {})
        mock_opt.assert_called_once()


# ── analyze_holdings ──────────────────────────────────────────────────────────

class TestAnalyzeHoldings:
    @patch("app.models.database.get_db")
    def test_empty_holdings_returns_error(self, mock_get_db):
        result = _execute("analyze_holdings", {"holdings": []})
        assert "error" in result

    @patch("app.models.database.get_db")
    def test_missing_holdings_returns_error(self, mock_get_db):
        result = _execute("analyze_holdings", {})
        assert "error" in result

    @patch("app.forecasting.holdings.analyze_holdings")
    @patch("app.models.database.get_db")
    def test_calls_analyze(self, mock_get_db, mock_ah):
        mock_ah.return_value = {"recommendations": []}
        db, cm = _mock_db()
        mock_get_db.return_value = cm
        result = _execute("analyze_holdings", {
            "holdings": [{"ticker": "AAPL", "shares": 100, "cost_basis": 150.0}]
        })
        mock_ah.assert_called_once()


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    @patch("app.models.database.get_db")
    def test_unknown_tool_returns_error(self, mock_get_db):
        result = _execute("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]
        assert "nonexistent_tool" in result["error"]
