"""
General REST API routes for direct consumption (dashboards, admin, etc.)
"""
from datetime import date
from flask import Blueprint, request, jsonify
from app.utils.logging_config import get_logger
from app.models.database import get_db, check_db_health

logger = get_logger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def ok(data):
    return jsonify({"success": True, "data": data})


def err(msg, code=500):
    return jsonify({"success": False, "error": msg}), code


# -- Health --

@api_bp.route("/health", methods=["GET"])
def health():
    db = check_db_health()
    return ok({"database": db, "api": "healthy"})


# -- Stocks --

@api_bp.route("/stocks", methods=["GET"])
def list_stocks():
    """List all tracked stocks."""
    from app.models.schema import DimStock
    with get_db() as db:
        stocks = db.query(DimStock).filter(DimStock.is_active == True).all()
        return ok([{
            "ticker": s.ticker,
            "company_name": s.company_name,
            "sector": s.sector,
            "industry": s.industry,
            "exchange": s.exchange,
            "market_cap_category": s.market_cap_category,
            "is_etf": s.is_etf,
        } for s in stocks])


@api_bp.route("/stocks/<ticker>/prices", methods=["GET"])
def get_prices(ticker: str):
    """Get price history for a ticker."""
    from app.models.schema import DimStock, FactStockPrice
    ticker = ticker.upper()
    start = request.args.get("start", str(date.today().replace(day=1)))
    end = request.args.get("end", str(date.today()))
    limit = int(request.args.get("limit", 252))

    with get_db() as db:
        stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
        if not stock:
            return err(f"Ticker {ticker} not found", 404)

        prices = (
            db.query(FactStockPrice)
            .filter(
                FactStockPrice.stock_id == stock.stock_id,
                FactStockPrice.trade_date >= date.fromisoformat(start),
                FactStockPrice.trade_date <= date.fromisoformat(end),
            )
            .order_by(FactStockPrice.trade_date.desc())
            .limit(limit)
            .all()
        )

        return ok([{
            "date": str(p.trade_date),
            "open": float(p.open_adj or 0),
            "high": float(p.high_adj or 0),
            "low": float(p.low_adj or 0),
            "close": float(p.close_adj),
            "volume": int(p.volume_adj or 0),
            "daily_return_pct": round(float(p.daily_return or 0) * 100, 3),
        } for p in prices])


@api_bp.route("/stocks/<ticker>/news", methods=["GET"])
def get_news(ticker: str):
    """Get recent news with LLM analysis for a ticker."""
    from app.models.schema import DimStock, FactStockNews
    ticker = ticker.upper()
    limit = int(request.args.get("limit", 20))

    with get_db() as db:
        stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
        if not stock:
            return err(f"Ticker {ticker} not found", 404)

        news = (
            db.query(FactStockNews)
            .filter(FactStockNews.stock_id == stock.stock_id)
            .order_by(FactStockNews.published_at.desc())
            .limit(limit)
            .all()
        )

        return ok([{
            "headline": n.headline,
            "source": n.source,
            "published_at": str(n.published_at),
            "sentiment_label": n.sentiment_label,
            "sentiment_score": n.sentiment_score,
            "llm_summary": n.llm_summary,
            "llm_catalysts": n.llm_catalysts,
            "llm_risks": n.llm_risks,
            "url": n.url,
        } for n in news])


@api_bp.route("/stocks/<ticker>/earnings", methods=["GET"])
def get_earnings(ticker: str):
    """Get earnings history with LLM analysis."""
    from app.models.schema import DimStock, FactEarnings
    ticker = ticker.upper()

    with get_db() as db:
        stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
        if not stock:
            return err(f"Ticker {ticker} not found", 404)

        earnings = (
            db.query(FactEarnings)
            .filter(FactEarnings.stock_id == stock.stock_id)
            .order_by(FactEarnings.fiscal_year.desc(), FactEarnings.fiscal_quarter.desc())
            .limit(12)
            .all()
        )

        return ok([{
            "fiscal_year": e.fiscal_year,
            "fiscal_quarter": e.fiscal_quarter,
            "eps_actual": e.eps_actual,
            "eps_estimate": e.eps_estimate,
            "eps_surprise_pct": round(e.eps_surprise_pct or 0, 2),
            "llm_summary": e.llm_summary,
            "llm_bull_case": e.llm_bull_case,
            "llm_bear_case": e.llm_bear_case,
            "gross_margin": e.gross_margin,
            "operating_margin": e.operating_margin,
            "price_reaction_1d": e.price_reaction_1d,
        } for e in earnings])


@api_bp.route("/stocks/<ticker>/technicals", methods=["GET"])
def get_technicals(ticker: str):
    """Get most recent technical indicators."""
    from app.models.schema import DimStock, FactTechnicalIndicator
    ticker = ticker.upper()

    with get_db() as db:
        stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
        if not stock:
            return err(f"Ticker {ticker} not found", 404)

        latest = (
            db.query(FactTechnicalIndicator)
            .filter(FactTechnicalIndicator.stock_id == stock.stock_id)
            .order_by(FactTechnicalIndicator.trade_date.desc())
            .first()
        )

        if not latest:
            return err("No technical data found", 404)

        return ok({
            "date": str(latest.trade_date),
            "rsi_14": latest.rsi_14,
            "macd": latest.macd,
            "macd_signal": latest.macd_signal,
            "macd_histogram": latest.macd_histogram,
            "bb_pct_b": latest.bb_pct_b,
            "bb_bandwidth": latest.bb_bandwidth,
            "atr_14": latest.atr_14,
            "volatility_20d": latest.volatility_20d,
            "volume_ratio": latest.volume_ratio,
            "golden_cross": latest.golden_cross,
            "macd_bullish": latest.macd_bullish,
            "rsi_oversold": latest.rsi_oversold,
            "rsi_overbought": latest.rsi_overbought,
            "price_vs_52w_high": latest.price_vs_52w_high,
            "price_vs_sma50": latest.price_vs_sma50,
            "price_vs_sma200": latest.price_vs_sma200,
        })


@api_bp.route("/forecasts/today", methods=["GET"])
def get_todays_forecasts():
    """Get today's forecasts ranked by opportunity score."""
    from app.models.schema import FactForecast, DimStock
    limit = int(request.args.get("limit", 20))

    with get_db() as db:
        rows = (
            db.query(FactForecast, DimStock.ticker, DimStock.company_name, DimStock.sector)
            .join(DimStock)
            .filter(FactForecast.forecast_date == date.today())
            .order_by(FactForecast.opportunity_score.desc())
            .limit(limit)
            .all()
        )

        return ok([{
            "ticker": ticker,
            "company_name": company,
            "sector": sector,
            "predicted_return_pct": round((f.predicted_return or 0) * 100, 2),
            "predicted_direction": f.predicted_direction,
            "confidence_score": f.confidence_score,
            "opportunity_score": f.opportunity_score,
            "target_date": str(f.target_date),
            "llm_rationale": f.llm_rationale,
        } for f, ticker, company, sector in rows])


# -- Multi-Horizon Forecasts --

@api_bp.route("/forecasts/multi-horizon", methods=["GET"])
def get_multi_horizon_forecasts():
    """Get multi-horizon forecasts (1d + 5d) for today."""
    from app.models.schema import FactForecast, DimStock
    ticker_filter = request.args.get("ticker", "").upper() or None
    limit = int(request.args.get("limit", 20))

    with get_db() as db:
        q = (
            db.query(FactForecast, DimStock.ticker, DimStock.company_name, DimStock.sector)
            .join(DimStock)
            .filter(FactForecast.forecast_date == date.today())
        )
        if ticker_filter:
            q = q.filter(DimStock.ticker == ticker_filter)

        rows = q.order_by(
            FactForecast.opportunity_score.desc()
        ).limit(limit * 2).all()  # fetch extra to group by ticker

        # Group by ticker, then by horizon
        grouped = {}
        for f, tkr, company, sector in rows:
            if tkr not in grouped:
                grouped[tkr] = {"ticker": tkr, "company_name": company, "sector": sector, "horizons": {}}
            h = f.forecast_horizon or 1
            grouped[tkr]["horizons"][f"{h}d"] = {
                "predicted_return_pct": round((f.predicted_return or 0) * 100, 2),
                "predicted_direction": f.predicted_direction,
                "confidence_score": f.confidence_score,
                "opportunity_score": f.opportunity_score,
                "lower_bound_95": f.lower_bound_95,
                "upper_bound_95": f.upper_bound_95,
                "target_date": str(f.target_date),
            }

        result = sorted(grouped.values(),
                        key=lambda x: x["horizons"].get("1d", {}).get("opportunity_score", 0),
                        reverse=True)[:limit]

        return ok(result)


# -- Portfolio Optimizer --

@api_bp.route("/portfolio/optimize", methods=["POST"])
def optimize_portfolio():
    """
    Run portfolio optimization.

    Body (optional):
      {
        "tickers": ["AAPL", "MSFT", ...],  // defaults to watchlist
        "initial_capital": 100,
        "max_weight_pct": 20,
        "holding_days": 21
      }
    """
    from app.forecasting.portfolio import run_portfolio_optimization

    body = request.get_json(silent=True) or {}
    tickers = [t.upper() for t in body.get("tickers", [])] or None
    initial_capital = float(body.get("initial_capital", 100))
    max_weight = float(body.get("max_weight_pct", 20)) / 100
    holding_days = int(body.get("holding_days", 21))

    try:
        with get_db() as db:
            result = run_portfolio_optimization(
                tickers=tickers,
                db=db,
                initial_capital=initial_capital,
                max_weight=max_weight,
                holding_days=holding_days,
            )
        return ok(result)
    except Exception as e:
        logger.error("Portfolio optimization error", error=str(e))
        return err(str(e))


# -- Holdings Analyzer --

@api_bp.route("/holdings/analyze", methods=["POST"])
def analyze_holdings():
    """
    Analyze current holdings with sell/hold recommendations.

    Body:
      {
        "holdings": [
          {"ticker": "AAPL", "shares": 10, "cost_basis": 150.0, "purchase_date": "2024-06-15"},
          {"ticker": "NVDA", "shares": 5, "cost_basis": 800.0, "purchase_date": "2025-01-10"}
        ]
      }
    """
    from app.forecasting.holdings import analyze_holdings as _analyze

    body = request.get_json(silent=True) or {}
    holdings = body.get("holdings", [])

    if not holdings:
        return err("No holdings provided. Send {\"holdings\": [{\"ticker\": ..., \"shares\": ..., \"cost_basis\": ..., \"purchase_date\": ...}]}", 400)

    try:
        with get_db() as db:
            result = _analyze(holdings=holdings, db=db)
        return ok(result)
    except Exception as e:
        logger.error("Holdings analysis error", error=str(e))
        return err(str(e))
