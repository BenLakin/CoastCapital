"""
n8n webhook routes — all endpoints designed for easy n8n HTTP Request node consumption.

Authentication: X-API-Key header via API_KEY env var (same as all other modules).

Endpoints:
  POST /n8n/daily-forecast       → Run daily pipeline, return top opportunities
  POST /n8n/backfill             → Backfill one or more tickers
  POST /n8n/forecast/:ticker     → Single ticker forecast
  POST /n8n/backtest/:ticker     → Run backtest for a ticker
  POST /n8n/train/:ticker        → Retrain model for a ticker
  POST /n8n/retrain-all          → Retrain all watchlist models
  GET  /n8n/watchlist            → Get current watchlist
  POST /n8n/watchlist/add        → Add ticker to watchlist
  GET  /n8n/health               → Health check
"""
import json
import os
from datetime import date
from functools import wraps
from flask import Blueprint, request, jsonify, current_app
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

n8n_bp = Blueprint("n8n", __name__, url_prefix="/n8n")

# Dynamic watchlist (in-memory; persisted to DB in production)
_dynamic_watchlist: list[str] = list(settings.watchlist)

API_KEY = os.environ.get("API_KEY", "") or getattr(settings, "API_KEY", "")


# ---------------------------------------------------------------------------
# Auth middleware
# ---------------------------------------------------------------------------

def require_n8n_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not API_KEY:
            # If no key configured, allow all (dev mode)
            return f(*args, **kwargs)

        key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if key != API_KEY:
            logger.warning("Unauthorized n8n request", ip=request.remote_addr)
            return jsonify({"error": "Unauthorized"}), 401

        return f(*args, **kwargs)
    return decorated


def success_response(data: dict, status: int = 200):
    return jsonify({"success": True, "data": data}), status


def error_response(message: str, status: int = 500):
    return jsonify({"success": False, "error": message}), status


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@n8n_bp.route("/health", methods=["GET"])
def health():
    """Health check endpoint for n8n monitoring."""
    from app.models.database import check_db_health
    db_health = check_db_health()
    return jsonify({
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "database": db_health,
        "version": "2.0",
    })


@n8n_bp.route("/daily-forecast", methods=["POST"])
@require_n8n_auth
def daily_forecast():
    """
    Run the full daily forecasting pipeline.

    Body (optional JSON):
      {
        "tickers": ["AAPL", "MSFT"],  // override watchlist
        "use_llm": true,              // default: true
        "top_n": 10                   // number of top picks
      }

    Returns:
      {
        "run_date": "YYYY-MM-DD",
        "target_date": "YYYY-MM-DD",
        "top_opportunities": [
          {
            "rank": 1,
            "ticker": "AAPL",
            "signal": "LONG",
            "predicted_return_pct": 1.23,
            "confidence_pct": 72.5,
            "opportunity_score": 1.45
          }, ...
        ],
        "market_brief": "...",
        "pipeline_stats": {...}
      }
    """
    from app.pipelines.daily_process import run_daily_pipeline

    body = request.get_json(silent=True) or {}
    tickers = body.get("tickers", _dynamic_watchlist)
    use_llm = body.get("use_llm", True)
    top_n = int(body.get("top_n", 10))
    forecast_date_str = body.get("forecast_date")
    forecast_date = date.fromisoformat(forecast_date_str) if forecast_date_str else date.today()

    logger.info("n8n daily-forecast triggered",
               tickers=len(tickers), use_llm=use_llm, forecast_date=str(forecast_date))

    try:
        result = run_daily_pipeline(
            tickers=tickers,
            forecast_date=forecast_date,
            use_llm=use_llm,
            top_n=top_n,
        )
        return success_response(result)
    except Exception as e:
        logger.error("Daily forecast pipeline error", error=str(e), exc_info=True)
        return error_response(str(e))


@n8n_bp.route("/forecast/<ticker>", methods=["POST", "GET"])
@require_n8n_auth
def single_forecast(ticker: str):
    """
    Generate a forecast for a single ticker.

    Query params / body:
      forecast_date: YYYY-MM-DD (default: today)
    """
    from app.pipelines.daily_process import get_next_trading_day
    from app.forecasting.models import generate_forecast
    from app.models.database import get_db

    body = request.get_json(silent=True) or {}
    forecast_date_str = body.get("forecast_date") or request.args.get("forecast_date")
    forecast_date = date.fromisoformat(forecast_date_str) if forecast_date_str else date.today()
    target_date = get_next_trading_day(forecast_date)

    ticker = ticker.upper()

    try:
        with get_db() as db:
            result = generate_forecast(ticker, forecast_date, target_date, db)
        return success_response(result)
    except Exception as e:
        logger.error("Single forecast error", ticker=ticker, error=str(e))
        return error_response(str(e))


@n8n_bp.route("/backfill", methods=["POST"])
@require_n8n_auth
def backfill():
    """
    Trigger historical data backfill.

    Body:
      {
        "tickers": ["AAPL"],        // required
        "start_date": "2020-01-01", // optional, defaults to 5 years ago
        "end_date": "2024-01-01",   // optional
        "use_llm": false             // default: false (expensive for bulk)
      }
    """
    from app.pipelines.backfill import backfill_watchlist

    body = request.get_json(silent=True) or {}
    tickers = body.get("tickers", _dynamic_watchlist)
    use_llm = body.get("use_llm", False)
    start_date_str = body.get("start_date")
    end_date_str = body.get("end_date")

    start_date = date.fromisoformat(start_date_str) if start_date_str else None
    end_date = date.fromisoformat(end_date_str) if end_date_str else None

    logger.info("n8n backfill triggered", tickers=len(tickers))

    try:
        result = backfill_watchlist(
            tickers=[t.upper() for t in tickers],
            start_date=start_date,
            end_date=end_date,
            use_llm=use_llm,
        )
        return success_response(result)
    except Exception as e:
        logger.error("Backfill error", error=str(e))
        return error_response(str(e))


@n8n_bp.route("/backtest/<ticker>", methods=["POST"])
@require_n8n_auth
def backtest_ticker(ticker: str):
    """
    Run walk-forward backtest for a single ticker.

    Body (optional):
      {
        "n_folds": 4,
        "test_days": 63
      }
    """
    from app.forecasting.backtesting import run_backtest
    from app.models.database import get_db

    body = request.get_json(silent=True) or {}
    n_folds = int(body.get("n_folds", 4))
    test_days = int(body.get("test_days", 63))
    ticker = ticker.upper()

    logger.info("n8n backtest triggered", ticker=ticker, n_folds=n_folds)

    try:
        with get_db() as db:
            result = run_backtest(ticker, db, n_folds=n_folds, test_days=test_days)
        return success_response(result)
    except Exception as e:
        logger.error("Backtest error", ticker=ticker, error=str(e))
        return error_response(str(e))


@n8n_bp.route("/train/<ticker>", methods=["POST"])
@require_n8n_auth
def train_ticker(ticker: str):
    """Retrain the forecasting model for a single ticker."""
    from app.forecasting.models import train_model
    from app.models.database import get_db

    ticker = ticker.upper()
    logger.info("n8n train triggered", ticker=ticker)

    try:
        with get_db() as db:
            result = train_model(ticker, db)
        return success_response(result)
    except Exception as e:
        logger.error("Training error", ticker=ticker, error=str(e))
        return error_response(str(e))


@n8n_bp.route("/retrain-all", methods=["POST"])
@require_n8n_auth
def retrain_all():
    """Retrain models for all watchlist tickers."""
    from app.pipelines.daily_process import retrain_all_models

    body = request.get_json(silent=True) or {}
    tickers = body.get("tickers", _dynamic_watchlist)

    logger.info("n8n retrain-all triggered", n_tickers=len(tickers))

    try:
        result = retrain_all_models(tickers=[t.upper() for t in tickers])
        return success_response(result)
    except Exception as e:
        logger.error("Retrain-all error", error=str(e))
        return error_response(str(e))


@n8n_bp.route("/watchlist", methods=["GET"])
@require_n8n_auth
def get_watchlist():
    """Get current ticker watchlist."""
    return success_response({"watchlist": _dynamic_watchlist, "count": len(_dynamic_watchlist)})


@n8n_bp.route("/watchlist/add", methods=["POST"])
@require_n8n_auth
def add_to_watchlist():
    """
    Add tickers to watchlist and trigger backfill.

    Body: { "tickers": ["AAPL", "NVDA"] }
    """
    from app.pipelines.backfill import backfill_ticker

    body = request.get_json(silent=True) or {}
    new_tickers = [t.upper().strip() for t in body.get("tickers", [])]

    if not new_tickers:
        return error_response("No tickers provided", 400)

    added = []
    for ticker in new_tickers:
        if ticker not in _dynamic_watchlist:
            _dynamic_watchlist.append(ticker)
            added.append(ticker)
            # Trigger backfill for new ticker
            try:
                backfill_ticker(ticker, use_llm=False)
            except Exception as e:
                logger.warning("Backfill failed for new ticker", ticker=ticker, error=str(e))

    return success_response({
        "added": added,
        "already_existed": [t for t in new_tickers if t not in added],
        "watchlist": _dynamic_watchlist,
    })


@n8n_bp.route("/forecasts", methods=["GET"])
@require_n8n_auth
def get_forecasts():
    """
    Get stored forecasts for a date range.

    Query params:
      ticker: filter by ticker (optional)
      forecast_date: YYYY-MM-DD (default: today)
      limit: number of results (default: 50)
    """
    from app.models.database import get_db
    from app.models.schema import FactForecast, DimStock

    ticker = request.args.get("ticker", "").upper() or None
    forecast_date_str = request.args.get("forecast_date", str(date.today()))
    limit = int(request.args.get("limit", 50))

    try:
        forecast_date = date.fromisoformat(forecast_date_str)
    except ValueError:
        return error_response("Invalid forecast_date format. Use YYYY-MM-DD.", 400)

    try:
        with get_db() as db:
            q = db.query(FactForecast, DimStock.ticker, DimStock.company_name).join(
                DimStock, FactForecast.stock_id == DimStock.stock_id
            ).filter(FactForecast.forecast_date == forecast_date)

            if ticker:
                q = q.filter(DimStock.ticker == ticker)

            q = q.order_by(FactForecast.opportunity_score.desc()).limit(limit)
            rows = q.all()

            forecasts = []
            for f, ticker_sym, company in rows:
                forecasts.append({
                    "ticker": ticker_sym,
                    "company_name": company,
                    "forecast_date": str(f.forecast_date),
                    "target_date": str(f.target_date),
                    "predicted_return_pct": round((f.predicted_return or 0) * 100, 2),
                    "predicted_direction": f.predicted_direction,
                    "confidence_score": f.confidence_score,
                    "opportunity_score": f.opportunity_score,
                    "was_correct": f.was_correct,
                    "model_name": f.model_name,
                })

        return success_response({"forecasts": forecasts, "count": len(forecasts)})
    except Exception as e:
        logger.error("Get forecasts error", error=str(e))
        return error_response(str(e))


@n8n_bp.route("/portfolio-optimize", methods=["POST"])
@require_n8n_auth
def portfolio_optimize():
    """
    Run portfolio optimization via n8n.

    Body (optional):
      {
        "tickers": ["AAPL", "MSFT"],
        "initial_capital": 100,
        "max_weight_pct": 20,
        "holding_days": 21
      }
    """
    from app.forecasting.portfolio import run_portfolio_optimization
    from app.models.database import get_db

    body = request.get_json(silent=True) or {}
    tickers = [t.upper() for t in body.get("tickers", [])] or None
    initial_capital = float(body.get("initial_capital", 100))
    max_weight = float(body.get("max_weight_pct", 20)) / 100
    holding_days = int(body.get("holding_days", 21))

    logger.info("n8n portfolio-optimize triggered", n_tickers=len(tickers) if tickers else "watchlist")

    try:
        with get_db() as db:
            result = run_portfolio_optimization(
                tickers=tickers,
                db=db,
                initial_capital=initial_capital,
                max_weight=max_weight,
                holding_days=holding_days,
            )
        return success_response(result)
    except Exception as e:
        logger.error("Portfolio optimization error", error=str(e))
        return error_response(str(e))


@n8n_bp.route("/holdings-analyze", methods=["POST"])
@require_n8n_auth
def holdings_analyze():
    """
    Analyze holdings with sell/hold recommendations via n8n.

    Body:
      {
        "holdings": [
          {"ticker": "AAPL", "shares": 10, "cost_basis": 150.0, "purchase_date": "2024-06-15"}
        ]
      }
    """
    from app.forecasting.holdings import analyze_holdings
    from app.models.database import get_db

    body = request.get_json(silent=True) or {}
    holdings = body.get("holdings", [])

    if not holdings:
        return error_response("No holdings provided", 400)

    logger.info("n8n holdings-analyze triggered", n_holdings=len(holdings))

    try:
        with get_db() as db:
            result = analyze_holdings(holdings=holdings, db=db)
        return success_response(result)
    except Exception as e:
        logger.error("Holdings analysis error", error=str(e))
        return error_response(str(e))


@n8n_bp.route("/backtest-results", methods=["GET"])
@require_n8n_auth
def get_backtest_results():
    """Get most recent backtest results for all tickers."""
    from app.models.database import get_db
    from app.models.schema import FactBacktestResult

    limit = int(request.args.get("limit", 20))

    try:
        with get_db() as db:
            results = (
                db.query(FactBacktestResult)
                .order_by(FactBacktestResult.run_date.desc(), FactBacktestResult.created_at.desc())
                .limit(limit)
                .all()
            )

            rows = [{
                "backtest_id": r.backtest_id,
                "run_date": str(r.run_date),
                "model_name": r.model_name,
                "directional_accuracy": r.directional_accuracy,
                "sharpe_ratio": r.sharpe_ratio,
                "alpha": r.alpha,
                "max_drawdown": r.max_drawdown,
                "win_rate": r.win_rate,
                "strategy_return_annualized": r.strategy_return_annualized,
            } for r in results]

        return success_response({"results": rows})
    except Exception as e:
        return error_response(str(e))
