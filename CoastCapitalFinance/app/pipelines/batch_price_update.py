"""
Batch price updater: uses yf.download() to fetch OHLCV for many tickers at once.

yf.download(["AAPL","MSFT",...], period="5d") fetches multiple tickers in a single
API call, avoiding the per-ticker rate limiting that kills 50K+ ticker pipelines.

Rate limit math: 50K tickers / 100 per batch = 500 calls × 2s delay ≈ 17 minutes.
"""
import time
import math
from datetime import date, datetime, timedelta
from typing import Optional
import numpy as np
import pandas as pd
import yfinance as yf
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.models.database import get_db
from app.models.schema import DimStock, FactStockPrice, FactBulkLoadLog
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def batch_download_prices(
    tickers: list[str],
    start_date: Optional[date],
    end_date: Optional[date],
    db: Session,
    batch_size: Optional[int] = None,
    delay: Optional[float] = None,
    period: Optional[str] = None,
) -> dict:
    """
    Download OHLCV for many tickers using yf.download() batching.

    Args:
        tickers: List of ticker symbols
        start_date: Start date for price data (None if using period)
        end_date: End date for price data (None if using period)
        db: SQLAlchemy session
        batch_size: Tickers per API call (default from config)
        delay: Seconds between batches (default from config)
        period: yfinance period string (e.g. "max", "1y", "5d").
                If set, overrides start_date/end_date.

    Returns:
        Stats dict with counts of rows loaded, errors, etc.
    """
    batch_size = batch_size or settings.UNIVERSE_BATCH_SIZE
    delay = delay if delay is not None else settings.UNIVERSE_BATCH_DELAY

    start_time = time.time()
    log_entry = FactBulkLoadLog(
        source="yf_batch",
        start_date=start_date,
        end_date=end_date,
        status="running",
    )
    db.add(log_entry)
    db.flush()

    stats = {
        "total_tickers": len(tickers),
        "batches": 0,
        "rows_loaded": 0,
        "tickers_with_data": 0,
        "tickers_no_data": 0,
        "errors": [],
    }

    # Build ticker→stock_id mapping
    ticker_to_id = _get_ticker_id_map(tickers, db)

    n_batches = math.ceil(len(tickers) / batch_size)
    logger.info("Starting batch download",
                total_tickers=len(tickers), n_batches=n_batches, batch_size=batch_size)

    for batch_num in range(n_batches):
        batch_start = batch_num * batch_size
        batch_tickers = tickers[batch_start:batch_start + batch_size]

        try:
            rows = _download_and_upsert_batch(
                batch_tickers, start_date, end_date, ticker_to_id, db,
                period=period,
            )
            stats["rows_loaded"] += rows["loaded"]
            stats["tickers_with_data"] += rows["tickers_with_data"]
            stats["tickers_no_data"] += rows["tickers_no_data"]
            stats["batches"] += 1

            if batch_num % 10 == 0:
                logger.info("Batch progress",
                            batch=f"{batch_num + 1}/{n_batches}",
                            rows_so_far=stats["rows_loaded"])

        except Exception as e:
            error_msg = f"Batch {batch_num + 1} failed: {str(e)}"
            logger.warning(error_msg)
            stats["errors"].append(error_msg)

        # Rate limit between batches
        if batch_num < n_batches - 1 and delay > 0:
            time.sleep(delay)

    # Finalize log entry
    elapsed = round(time.time() - start_time, 2)
    log_entry.status = "success" if not stats["errors"] else "error"
    log_entry.tickers_loaded = stats["tickers_with_data"]
    log_entry.rows_loaded = stats["rows_loaded"]
    log_entry.rows_errored = len(stats["errors"])
    log_entry.duration_sec = elapsed
    log_entry.completed_at = datetime.utcnow()
    if stats["errors"]:
        log_entry.error_message = "; ".join(stats["errors"][:10])
    db.flush()

    stats["duration_sec"] = elapsed
    logger.info("Batch download complete", **{k: v for k, v in stats.items() if k != "errors"})
    return stats


def _download_and_upsert_batch(
    tickers: list[str],
    start_date: Optional[date],
    end_date: Optional[date],
    ticker_to_id: dict,
    db: Session,
    period: Optional[str] = None,
) -> dict:
    """Download a single batch of tickers via yf.download() and upsert prices."""
    result = {"loaded": 0, "tickers_with_data": 0, "tickers_no_data": 0}

    try:
        # Build yf.download kwargs — use period OR start/end, not both
        dl_kwargs = {
            "tickers": tickers,
            "auto_adjust": False,
            "group_by": "ticker",
            "threads": True,
            "progress": False,
        }
        if period:
            dl_kwargs["period"] = period
        else:
            dl_kwargs["start"] = str(start_date)
            dl_kwargs["end"] = str(end_date)

        # yf.download returns a DataFrame with multi-level columns for multiple tickers
        df = yf.download(**dl_kwargs)
    except Exception as e:
        logger.warning("yf.download failed for batch", error=str(e),
                       n_tickers=len(tickers))
        raise

    if df is None or df.empty:
        result["tickers_no_data"] = len(tickers)
        return result

    # Handle single vs multi-ticker response format
    if len(tickers) == 1:
        # Single ticker: flat columns (Open, High, Low, Close, Volume, Adj Close)
        ticker = tickers[0]
        stock_id = ticker_to_id.get(ticker)
        if stock_id and not df.empty:
            rows = _upsert_single_ticker_df(ticker, stock_id, df, db)
            result["loaded"] += rows
            result["tickers_with_data"] += 1 if rows > 0 else 0
            result["tickers_no_data"] += 1 if rows == 0 else 0
    else:
        # Multi-ticker: multi-level columns (ticker, field)
        for ticker in tickers:
            stock_id = ticker_to_id.get(ticker)
            if not stock_id:
                result["tickers_no_data"] += 1
                continue
            try:
                ticker_df = df[ticker].dropna(how="all") if ticker in df.columns.get_level_values(0) else pd.DataFrame()
                if ticker_df.empty:
                    result["tickers_no_data"] += 1
                    continue
                rows = _upsert_single_ticker_df(ticker, stock_id, ticker_df, db)
                result["loaded"] += rows
                result["tickers_with_data"] += 1 if rows > 0 else 0
                result["tickers_no_data"] += 1 if rows == 0 else 0
            except Exception as e:
                logger.debug("Skipping ticker in batch", ticker=ticker, error=str(e))
                result["tickers_no_data"] += 1

    db.flush()
    return result


def _upsert_single_ticker_df(
    ticker: str,
    stock_id: int,
    df: pd.DataFrame,
    db: Session,
) -> int:
    """Upsert price rows from a single-ticker DataFrame into fact_stock_price."""
    if df.empty:
        return 0

    rows_loaded = 0
    # Standardize column names (handle both 'Adj Close' and 'Close' cases)
    col_map = {}
    for col in df.columns:
        col_lower = str(col).lower().replace(" ", "_")
        col_map[col] = col_lower

    df = df.rename(columns=col_map)

    for idx, row in df.iterrows():
        trade_date = idx.date() if hasattr(idx, "date") else idx

        close_adj = _safe_float(row.get("adj_close") or row.get("close"))
        if close_adj is None or close_adj <= 0:
            continue

        open_raw = _safe_float(row.get("open"))
        high_raw = _safe_float(row.get("high"))
        low_raw = _safe_float(row.get("low"))
        close_raw = _safe_float(row.get("close"))
        volume_raw = _safe_int(row.get("volume"))

        # Compute derived fields
        vwap = None
        if high_raw and low_raw and close_raw:
            vwap = (high_raw + low_raw + close_raw) / 3.0

        intraday_range = None
        if high_raw and low_raw and open_raw and open_raw > 0:
            intraday_range = ((high_raw - low_raw) / open_raw) * 100

        # Use raw SQL for efficient upsert
        sql = text("""
            INSERT INTO fact_stock_price
                (stock_id, trade_date, open_raw, high_raw, low_raw, close_raw, volume_raw,
                 close_adj, vwap, intraday_range_pct, data_source)
            VALUES
                (:stock_id, :trade_date, :open_raw, :high_raw, :low_raw, :close_raw, :volume_raw,
                 :close_adj, :vwap, :intraday_range, :data_source)
            ON DUPLICATE KEY UPDATE
                open_raw = VALUES(open_raw),
                high_raw = VALUES(high_raw),
                low_raw = VALUES(low_raw),
                close_raw = VALUES(close_raw),
                volume_raw = VALUES(volume_raw),
                close_adj = VALUES(close_adj),
                vwap = VALUES(vwap),
                intraday_range_pct = VALUES(intraday_range_pct),
                updated_at = NOW()
        """)
        db.execute(sql, {
            "stock_id": stock_id,
            "trade_date": trade_date,
            "open_raw": open_raw,
            "high_raw": high_raw,
            "low_raw": low_raw,
            "close_raw": close_raw,
            "volume_raw": volume_raw,
            "close_adj": close_adj,
            "vwap": vwap,
            "intraday_range": intraday_range,
            "data_source": "yf_batch",
        })
        rows_loaded += 1

    return rows_loaded


def _get_ticker_id_map(tickers: list[str], db: Session) -> dict:
    """Build a {ticker: stock_id} mapping for all requested tickers."""
    if not tickers:
        return {}

    # Query in chunks to avoid huge IN clauses
    ticker_map = {}
    chunk_size = 500
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        placeholders = ", ".join([f":t{j}" for j in range(len(chunk))])
        params = {f"t{j}": t for j, t in enumerate(chunk)}
        rows = db.execute(
            text(f"SELECT ticker, stock_id FROM dim_stock WHERE ticker IN ({placeholders})"),
            params,
        ).fetchall()
        for row in rows:
            ticker_map[row[0]] = row[1]

    return ticker_map


def smart_universe_update(
    db: Optional[Session] = None,
    batch_size: int = 100,
) -> dict:
    """
    Smart price update for all non-watchlist tickers.

    Per-stock logic:
      - No price history → yf.download(period="max") to get all history back to IPO
      - Has price history → yf.download(start=last_trade_date) to fill the gap

    Groups tickers by status for efficient batch downloading.

    Args:
        db: SQLAlchemy session (created if None)
        batch_size: Tickers per yf.download() batch (default 100)
    """
    def _run(session):
        # Get all active non-watchlist tickers with their last price date
        rows = session.execute(text("""
            SELECT ds.ticker, MAX(fsp.trade_date) as last_date
            FROM dim_stock ds
            LEFT JOIN fact_stock_price fsp ON ds.stock_id = fsp.stock_id
            WHERE ds.stock_tier != 'watchlist' AND ds.is_active = 1
            GROUP BY ds.ticker
        """)).fetchall()

        if not rows:
            logger.info("No universe tickers found")
            return {"tickers": 0, "message": "No universe tickers found"}

        # Split into no-history vs has-history
        no_history = []
        has_history = []
        for ticker, last_date in rows:
            if last_date is None:
                no_history.append(ticker)
            else:
                has_history.append((ticker, last_date))

        logger.info("Smart universe update",
                     total=len(rows),
                     no_history=len(no_history),
                     has_history=len(has_history))

        result = {
            "total_tickers": len(rows),
            "no_history_count": len(no_history),
            "has_history_count": len(has_history),
        }

        # 1. No-history tickers: full backfill with period="max"
        if no_history:
            logger.info("Backfilling tickers with no history",
                         count=len(no_history))
            full_stats = batch_download_prices(
                tickers=no_history,
                start_date=None,
                end_date=None,
                db=session,
                batch_size=batch_size,
                period="max",
            )
            result["full_backfill"] = full_stats

        # 2. Has-history tickers: fetch from their oldest last_date to today
        if has_history:
            tickers_to_update = [t for t, _ in has_history]
            # Use the oldest last_date as start — upsert handles duplicates
            oldest_last = min(d for _, d in has_history)
            start_date = oldest_last - timedelta(days=1)  # overlap by 1 day for safety
            end_date = date.today()

            logger.info("Updating tickers with history",
                         count=len(tickers_to_update),
                         start=str(start_date), end=str(end_date))
            incr_stats = batch_download_prices(
                tickers=tickers_to_update,
                start_date=start_date,
                end_date=end_date,
                db=session,
                batch_size=batch_size,
            )
            result["incremental"] = incr_stats

        return result

    if db:
        return _run(db)
    else:
        with get_db() as session:
            return _run(session)


def _safe_float(val) -> Optional[float]:
    """Convert a value to float, returning None on failure."""
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    """Convert a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None
