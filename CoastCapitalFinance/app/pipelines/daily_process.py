"""
Daily forecasting pipeline — called by n8n each morning before market open.

Process:
  1. Update prices for all watchlist tickers (yesterday's close)
  2. Fetch new news articles and analyze with LLM
  3. Recompute technical indicators
  4. Update macro data
  5. Run forecasts for next trading day
  6. Score and rank all stocks by opportunity
  7. Generate LLM morning brief
  8. Return structured output for n8n consumption
"""
from datetime import date, timedelta
from typing import Optional
from app.models.database import get_db
from app.models.schema import DimStock, FactForecast, FactMacroIndicator
from app.pipelines.ingestion import (
    upsert_dim_stock, fetch_and_store_prices, fetch_and_store_news,
    fetch_and_store_macro, check_and_handle_splits
)
from app.pipelines.technicals import compute_and_store_technicals
from app.forecasting.models import generate_forecast, generate_multi_horizon_forecast, train_model
from app.utils.llm_utils import generate_daily_market_brief
from app.config import settings
from app.utils.logging_config import get_logger
import pandas as pd

logger = get_logger(__name__)


def get_next_trading_day(from_date: date) -> date:
    """Return next Monday-Friday trading day (simplified, no holidays)."""
    next_day = from_date + timedelta(days=1)
    while next_day.weekday() >= 5:  # Skip weekends
        next_day += timedelta(days=1)
    return next_day


def run_daily_pipeline(
    tickers: Optional[list[str]] = None,
    forecast_date: Optional[date] = None,
    use_llm: bool = True,
    top_n: int = 10,
) -> dict:
    """
    Main daily pipeline. Returns complete forecast package for n8n.

    Parameters:
        tickers: list of tickers to process. Defaults to settings.watchlist
        forecast_date: date to generate forecasts from (defaults to today)
        use_llm: whether to run LLM analysis (requires API key)
        top_n: number of top opportunities to highlight

    Returns:
        {
            "run_date": "YYYY-MM-DD",
            "target_date": "YYYY-MM-DD",
            "top_opportunities": [...],
            "market_brief": "...",
            "all_forecasts": [...],
            "pipeline_stats": {...}
        }
    """
    tickers = tickers or settings.watchlist
    forecast_date = forecast_date or date.today()
    target_date = get_next_trading_day(forecast_date)

    logger.info("Daily pipeline started",
               forecast_date=str(forecast_date),
               target_date=str(target_date),
               n_tickers=len(tickers))

    stats = {
        "tickers_processed": 0,
        "tickers_failed": 0,
        "prices_updated": 0,
        "news_added": 0,
        "forecasts_generated": 0,
    }

    all_forecasts = []

    # -- Step 1: Update macro data
    try:
        macro_start = forecast_date - timedelta(days=5)
        with get_db() as db:
            fetch_and_store_macro(macro_start, forecast_date, db)
    except Exception as e:
        logger.warning("Macro update failed", error=str(e))

    # -- Step 2: Process each ticker
    for ticker in tickers:
        try:
            with get_db() as db:
                # Ensure stock exists
                stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
                if not stock:
                    upsert_dim_stock(ticker, db)
                    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()

                # Check for splits
                check_and_handle_splits(ticker, db)

                # Update last 5 days of prices
                price_start = forecast_date - timedelta(days=5)
                rows = fetch_and_store_prices(ticker, price_start, forecast_date, db)
                stats["prices_updated"] += rows

                # Recompute technicals for recent window
                tech_start = forecast_date - timedelta(days=5)
                compute_and_store_technicals(ticker, tech_start, forecast_date, db)

                # Fetch news (last 2 days)
                news_count = fetch_and_store_news(
                    ticker=ticker,
                    company_name=stock.company_name,
                    days_back=2,
                    db=db,
                    use_llm=use_llm,
                )
                stats["news_added"] += news_count

            # Generate multi-horizon forecasts (separate session)
            with get_db() as db:
                multi = generate_multi_horizon_forecast(
                    ticker=ticker,
                    forecast_date=forecast_date,
                    db=db,
                )
                # Use the 1d forecast for ranking (backward compat)
                if "1d" in multi.get("horizons", {}):
                    forecast = multi["horizons"]["1d"]
                    if "error" not in forecast:
                        forecast["horizons"] = multi["horizons"]
                        all_forecasts.append(forecast)
                        stats["forecasts_generated"] += 1

            stats["tickers_processed"] += 1

        except Exception as e:
            logger.error("Ticker processing failed", ticker=ticker, error=str(e), exc_info=True)
            stats["tickers_failed"] += 1

    # -- Step 3: Rank by opportunity score
    all_forecasts.sort(key=lambda x: x.get("opportunity_score", 0), reverse=True)
    top_opportunities = all_forecasts[:top_n]

    # Format top opportunities for n8n
    n8n_opportunities = []
    for f in top_opportunities:
        direction_label = "🟢 LONG" if f.get("predicted_direction") == 1 else \
                         "🔴 SHORT" if f.get("predicted_direction") == -1 else "⚪ FLAT"
        n8n_opportunities.append({
            "rank": n8n_opportunities.__len__() + 1,
            "ticker": f["ticker"],
            "company_name": f.get("company_name", ""),
            "signal": direction_label,
            "predicted_return_pct": round(f.get("predicted_return", 0) * 100, 2),
            "confidence_pct": round(f.get("confidence_score", 0) * 100, 1),
            "opportunity_score": round(f.get("opportunity_score", 0), 3),
            "target_date": f.get("target_date", str(target_date)),
        })

    # -- Step 4: Market brief via LLM (uses primary provider)
    market_brief = ""
    if use_llm:
        try:
            # Get latest macro snapshot
            with get_db() as db:
                macro = db.query(FactMacroIndicator).order_by(
                    FactMacroIndicator.indicator_date.desc()
                ).first()
                market_conditions = {
                    "vix": macro.vix if macro else None,
                    "spy_close": macro.spy_close if macro else None,
                    "yield_curve_2_10": macro.yield_curve_2_10 if macro else None,
                    "treasury_10y": macro.treasury_10y if macro else None,
                    "gold": macro.gold_close if macro else None,
                } if macro else {}

            market_brief = generate_daily_market_brief(
                top_opportunities=n8n_opportunities,
                market_conditions=market_conditions,
                date_str=str(target_date),
            )
        except Exception as e:
            logger.warning("Market brief generation failed", error=str(e))
            market_brief = "Market brief unavailable."

    result = {
        "run_date": str(forecast_date),
        "target_date": str(target_date),
        "top_opportunities": n8n_opportunities,
        "market_brief": market_brief,
        "all_forecasts": all_forecasts,
        "pipeline_stats": stats,
        "status": "success" if stats["tickers_failed"] == 0 else "partial",
    }

    logger.info("Daily pipeline complete",
               forecasts=stats["forecasts_generated"],
               failed=stats["tickers_failed"],
               top_ticker=n8n_opportunities[0]["ticker"] if n8n_opportunities else None)

    return result


def retrain_all_models(tickers: Optional[list[str]] = None) -> dict:
    """
    Retrain forecasting models for all tickers.
    Typically run weekly or when data drift is detected.
    """
    tickers = tickers or settings.watchlist
    results = {}

    for ticker in tickers:
        try:
            with get_db() as db:
                metrics = train_model(ticker, db)
                results[ticker] = {"status": "success", **metrics}
        except Exception as e:
            logger.error("Model training failed", ticker=ticker, error=str(e))
            results[ticker] = {"status": "error", "error": str(e)}

    return {
        "trained": sum(1 for r in results.values() if r["status"] == "success"),
        "failed": sum(1 for r in results.values() if r["status"] == "error"),
        "details": results,
    }
