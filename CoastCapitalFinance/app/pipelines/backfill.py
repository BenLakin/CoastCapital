"""
Backfill pipeline: ingests full historical data for a list of tickers.
Handles: OHLCV, technical indicators, news, earnings, macro, and split restatement.

Supports tiered backfill:
  - watchlist:  Full pipeline (prices, technicals, news, earnings, splits, LLM)
  - screener:  Prices + technicals (batch download, no LLM)
  - reference: Prices only (batch download)
"""
from datetime import date, timedelta
from typing import Optional
from sqlalchemy import text
from app.models.database import get_db
from app.models.schema import DimStock
from app.pipelines.ingestion import (
    upsert_dim_stock,
    fetch_and_store_prices,
    fetch_and_store_news,
    fetch_and_store_earnings,
    fetch_and_store_macro,
    check_and_handle_splits,
    populate_dim_date,
)
from app.pipelines.technicals import compute_and_store_technicals
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_START_DATE = date(2010, 1, 1)


def backfill_ticker(
    ticker: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    use_llm: bool = True,
) -> dict:
    """
    Full historical backfill for a single ticker.
    Safe to re-run (idempotent — upserts on conflict).
    """
    end_date = end_date or date.today()
    start_date = start_date or DEFAULT_START_DATE

    logger.info("Starting backfill", ticker=ticker, start=str(start_date), end=str(end_date))
    result = {"ticker": ticker, "status": "success", "details": {}}

    try:
        with get_db() as db:
            # 1. Upsert stock dimension
            stock = upsert_dim_stock(ticker, db)
            result["details"]["stock_upserted"] = True

            # 2. Check & handle splits BEFORE price ingestion
            splits = check_and_handle_splits(ticker, db)
            result["details"]["splits_found"] = splits

            # 3. Fetch full price history
            price_rows = fetch_and_store_prices(ticker, start_date, end_date, db)
            result["details"]["price_rows"] = price_rows

            # 4. Compute technical indicators
            tech_rows = compute_and_store_technicals(ticker, start_date, end_date, db)
            result["details"]["technical_rows"] = tech_rows

            # 5. News (last 30 days for backfill)
            news_days = min((end_date - start_date).days, 30)
            news_rows = fetch_and_store_news(
                ticker=ticker,
                company_name=stock.company_name,
                days_back=news_days,
                db=db,
                use_llm=use_llm,
            )
            result["details"]["news_rows"] = news_rows

            # 6. Earnings history
            earnings_rows = fetch_and_store_earnings(ticker, db, use_llm=use_llm)
            result["details"]["earnings_rows"] = earnings_rows

        logger.info("Backfill complete", ticker=ticker, details=result["details"])

    except Exception as e:
        logger.error("Backfill failed", ticker=ticker, error=str(e), exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)

    return result


def backfill_watchlist(
    tickers: list[str],
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    use_llm: bool = True,
) -> dict:
    """
    Backfill multiple tickers. Also fetches macro data for the full range.
    """
    end_date = end_date or date.today()
    start_date = start_date or DEFAULT_START_DATE

    results = {}

    # Populate date dimension for the full range
    logger.info("Populating date dimension", start=str(start_date), end=str(end_date))
    try:
        with get_db() as db:
            populate_dim_date(start_date, end_date, db)
            results["dim_date_populated"] = True
    except Exception as e:
        logger.error("Date dimension population failed", error=str(e))
        results["dim_date_error"] = str(e)

    # Backfill macro data for the full range first
    logger.info("Backfilling macro indicators", start=str(start_date), end=str(end_date))
    try:
        with get_db() as db:
            macro_rows = fetch_and_store_macro(start_date, end_date, db)
            results["macro_rows"] = macro_rows
    except Exception as e:
        logger.error("Macro backfill failed", error=str(e))
        results["macro_error"] = str(e)

    # Backfill each ticker
    ticker_results = {}
    for ticker in tickers:
        ticker_results[ticker] = backfill_ticker(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date,
            use_llm=use_llm,
        )
        # Respect Yahoo Finance rate limits (more aggressive to avoid blocking)
        import time
        time.sleep(2)

    results["tickers"] = ticker_results
    results["total_tickers"] = len(tickers)
    results["successful"] = sum(1 for r in ticker_results.values() if r["status"] == "success")
    results["failed"] = sum(1 for r in ticker_results.values() if r["status"] == "error")

    logger.info("Watchlist backfill complete",
               total=len(tickers),
               successful=results["successful"],
               failed=results["failed"])

    return results


def backfill_by_tier(
    tier: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    batch_size: int = 100,
    use_llm: bool = False,
) -> dict:
    """
    Tier-aware backfill:
      - watchlist:  Full per-ticker pipeline (prices, technicals, news, earnings, LLM)
      - screener:  Batch prices + per-ticker technicals
      - reference: Batch prices only

    Args:
        tier: "watchlist", "screener", or "reference"
        start_date: Start date (default: DEFAULT_START_DATE)
        end_date: End date (default: today)
        batch_size: Tickers per yf.download() batch (screener/reference only)
        use_llm: Enable LLM analysis (watchlist only, default False)
    """
    from app.pipelines.batch_price_update import batch_download_prices

    end_date = end_date or date.today()
    start_date = start_date or DEFAULT_START_DATE

    logger.info("Starting tier backfill", tier=tier, start=str(start_date), end=str(end_date))

    with get_db() as db:
        # Get tickers for this tier
        rows = db.execute(
            text("SELECT ticker FROM dim_stock WHERE stock_tier = :tier AND is_active = 1"),
            {"tier": tier},
        ).fetchall()
        tickers = [r[0] for r in rows]

        if not tickers:
            return {"tier": tier, "tickers": 0, "message": "No tickers found for tier"}

        logger.info("Found tickers for tier", tier=tier, count=len(tickers))

        if tier == "watchlist":
            # Full pipeline — use existing per-ticker backfill
            return backfill_watchlist(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                use_llm=use_llm,
            )

        elif tier == "screener":
            # Batch prices + technicals
            result = {"tier": tier}

            # 1. Batch download prices
            price_stats = batch_download_prices(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                db=db,
                batch_size=batch_size,
            )
            result["price_stats"] = price_stats

            # 2. Compute technicals for each ticker (needs per-ticker processing)
            tech_success = 0
            tech_errors = 0
            for ticker in tickers:
                try:
                    compute_and_store_technicals(ticker, start_date, end_date, db)
                    tech_success += 1
                except Exception as e:
                    tech_errors += 1
                    if tech_errors <= 5:
                        logger.debug("Technicals failed", ticker=ticker, error=str(e))

            result["technicals"] = {"success": tech_success, "errors": tech_errors}
            return result

        elif tier == "reference":
            # Batch prices only
            price_stats = batch_download_prices(
                tickers=tickers,
                start_date=start_date,
                end_date=end_date,
                db=db,
                batch_size=batch_size,
            )
            return {"tier": tier, "price_stats": price_stats}

        else:
            raise ValueError(f"Unknown tier: {tier}. Expected: watchlist, screener, reference")
