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

  Universe expansion:
  POST /n8n/universe/load        → Load tickers from SEC EDGAR + NASDAQ Trader
  GET  /n8n/universe/stats       → Universe stats by tier
  POST /n8n/universe/promote     → Move tickers between tiers
  POST /n8n/universe/bulk-price-load → Import CSV/parquet price files
  POST /n8n/screener/update      → Batch price + technicals for screener tier
  POST /n8n/reference/update     → Batch price update for reference tier
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


# ---------------------------------------------------------------------------
# Universe expansion routes
# ---------------------------------------------------------------------------

@n8n_bp.route("/universe/load", methods=["POST"])
@require_n8n_auth
def universe_load():
    """
    Load tickers from SEC EDGAR + NASDAQ Trader into dim_stock.
    3 HTTP requests total, zero yfinance calls.

    Body (optional):
      {
        "sources": ["sec_edgar", "nasdaq_trader"]  // default: both
      }
    """
    from app.pipelines.universe_loader import load_full_universe
    from app.models.database import get_db

    logger.info("n8n universe/load triggered")

    try:
        with get_db() as db:
            result = load_full_universe(db)
        return success_response(result)
    except Exception as e:
        logger.error("Universe load error", error=str(e), exc_info=True)
        return error_response(str(e))


@n8n_bp.route("/universe/stats", methods=["GET"])
@require_n8n_auth
def universe_stats():
    """
    Get universe statistics by tier.

    Returns:
      {
        "tier_counts": {"watchlist": 12, "screener": 500, "reference": 9000},
        "total": 9512,
        "last_load": "2025-01-15T10:30:00"
      }
    """
    from app.models.database import get_db
    from sqlalchemy import text

    try:
        with get_db() as db:
            # Tier counts
            tier_rows = db.execute(text(
                "SELECT stock_tier, COUNT(*) as cnt, "
                "SUM(is_etf) as etf_count "
                "FROM dim_stock WHERE is_active = 1 GROUP BY stock_tier"
            )).fetchall()

            tier_counts = {}
            etf_counts = {}
            for row in tier_rows:
                tier_counts[row[0]] = row[1]
                etf_counts[row[0]] = int(row[2] or 0)

            # Last bulk load
            last_load = db.execute(text(
                "SELECT source, status, tickers_loaded, rows_loaded, duration_sec, created_at "
                "FROM fact_bulk_load_log ORDER BY created_at DESC LIMIT 5"
            )).fetchall()

            recent_loads = [{
                "source": r[0], "status": r[1],
                "tickers_loaded": r[2], "rows_loaded": r[3],
                "duration_sec": r[4], "created_at": str(r[5]),
            } for r in last_load]

            # Price data coverage
            price_stats = db.execute(text(
                "SELECT COUNT(DISTINCT stock_id) as stocks_with_prices, "
                "COUNT(*) as total_price_rows, "
                "MIN(trade_date) as earliest, MAX(trade_date) as latest "
                "FROM fact_stock_price"
            )).fetchone()

            return success_response({
                "tier_counts": tier_counts,
                "etf_counts": etf_counts,
                "total": sum(tier_counts.values()),
                "recent_loads": recent_loads,
                "price_coverage": {
                    "stocks_with_prices": price_stats[0] if price_stats else 0,
                    "total_price_rows": price_stats[1] if price_stats else 0,
                    "earliest_date": str(price_stats[2]) if price_stats and price_stats[2] else None,
                    "latest_date": str(price_stats[3]) if price_stats and price_stats[3] else None,
                },
            })
    except Exception as e:
        logger.error("Universe stats error", error=str(e))
        return error_response(str(e))


@n8n_bp.route("/universe/promote", methods=["POST"])
@require_n8n_auth
def universe_promote():
    """
    Move tickers between tiers.

    Body:
      {
        "tickers": ["AAPL", "MSFT"],
        "target_tier": "screener"  // "watchlist", "screener", "reference"
      }
    """
    from app.models.database import get_db
    from sqlalchemy import text

    body = request.get_json(silent=True) or {}
    tickers = [t.upper().strip() for t in body.get("tickers", [])]
    target_tier = body.get("target_tier", "").lower()

    if not tickers:
        return error_response("No tickers provided", 400)
    if target_tier not in ("watchlist", "screener", "reference"):
        return error_response("target_tier must be: watchlist, screener, or reference", 400)

    try:
        with get_db() as db:
            placeholders = ", ".join([f":t{i}" for i in range(len(tickers))])
            params = {f"t{i}": t for i, t in enumerate(tickers)}
            params["tier"] = target_tier

            result = db.execute(
                text(f"UPDATE dim_stock SET stock_tier = :tier WHERE ticker IN ({placeholders})"),
                params,
            )
            updated = result.rowcount

        return success_response({
            "updated": updated,
            "tickers": tickers,
            "target_tier": target_tier,
        })
    except Exception as e:
        logger.error("Universe promote error", error=str(e))
        return error_response(str(e))


@n8n_bp.route("/universe/bulk-price-load", methods=["POST"])
@require_n8n_auth
def universe_bulk_price_load():
    """
    Import prices from CSV/parquet files (e.g. Kaggle datasets).

    Body:
      {
        "file_path": "/app/data/kaggle/AAPL.csv",      // single file
        "directory": "/app/data/kaggle/stocks/",        // OR entire directory
        "mapping": "kaggle_huge",                       // column mapping preset
        "chunk_size": 10000                             // rows per batch
      }
    """
    from app.pipelines.bulk_price_loader import load_price_csv, load_directory
    from app.models.database import get_db

    body = request.get_json(silent=True) or {}
    file_path = body.get("file_path")
    directory = body.get("directory")
    mapping_name = body.get("mapping", "kaggle_huge")
    chunk_size = int(body.get("chunk_size", 10000))

    if not file_path and not directory:
        return error_response("Provide 'file_path' or 'directory'", 400)

    try:
        with get_db() as db:
            if directory:
                result = load_directory(
                    directory=directory, db=db,
                    mapping_name=mapping_name, chunk_size=chunk_size,
                )
            else:
                result = load_price_csv(
                    file_path=file_path, db=db,
                    mapping_name=mapping_name, chunk_size=chunk_size,
                )
        return success_response(result)
    except Exception as e:
        logger.error("Bulk price load error", error=str(e), exc_info=True)
        return error_response(str(e))


@n8n_bp.route("/screener/update", methods=["POST"])
@require_n8n_auth
def screener_update():
    """
    Batch price + technicals update for screener-tier tickers.

    Body (optional):
      {
        "days_back": 5,        // calendar days to fetch (default 5)
        "batch_size": 100      // tickers per yf.download call
      }
    """
    from app.pipelines.batch_price_update import run_daily_universe_update
    from app.pipelines.backfill import backfill_by_tier
    from app.models.database import get_db

    body = request.get_json(silent=True) or {}
    days_back = int(body.get("days_back", 5))
    full_backfill = body.get("full_backfill", False)

    logger.info("n8n screener/update triggered", days_back=days_back)

    try:
        if full_backfill:
            result = backfill_by_tier(
                tier="screener",
                batch_size=int(body.get("batch_size", 100)),
            )
        else:
            with get_db() as db:
                result = run_daily_universe_update(tier="screener", db=db, days_back=days_back)
        return success_response(result)
    except Exception as e:
        logger.error("Screener update error", error=str(e), exc_info=True)
        return error_response(str(e))


@n8n_bp.route("/reference/update", methods=["POST"])
@require_n8n_auth
def reference_update():
    """
    Batch price update for reference-tier tickers (prices only, no technicals).

    Body (optional):
      {
        "days_back": 5,        // calendar days to fetch (default 5)
        "batch_size": 100,     // tickers per yf.download call
        "full_backfill": false // true = fetch full history (period=max)
      }
    """
    from app.pipelines.batch_price_update import run_daily_universe_update
    from app.pipelines.backfill import backfill_by_tier
    from app.models.database import get_db

    body = request.get_json(silent=True) or {}
    days_back = int(body.get("days_back", 5))
    full_backfill = body.get("full_backfill", False)

    logger.info("n8n reference/update triggered", days_back=days_back, full_backfill=full_backfill)

    try:
        if full_backfill:
            result = backfill_by_tier(
                tier="reference",
                batch_size=int(body.get("batch_size", 100)),
            )
        else:
            with get_db() as db:
                result = run_daily_universe_update(tier="reference", db=db, days_back=days_back)
        return success_response(result)
    except Exception as e:
        logger.error("Reference update error", error=str(e), exc_info=True)
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
