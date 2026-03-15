"""
Bulk price loader: imports historical OHLCV from CSV/parquet files (e.g. Kaggle datasets).

Zero API calls — reads from local files only.
Memory-safe: processes data in configurable chunks (default 10K rows).

Common Kaggle datasets this supports:
- "Huge Stock Market Dataset" (8K+ US stocks, 2010–present)
- "Daily Stock Prices" (S&P 500, extended history)
- Custom CSVs with configurable column mapping
"""
import os
import time
import math
from datetime import date, datetime
from typing import Optional
import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
from app.models.database import get_db
from app.models.schema import DimStock, FactBulkLoadLog
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

# Common column mappings for popular Kaggle datasets
COLUMN_MAPPINGS = {
    # "Huge Stock Market Dataset" by Boris Marjanovic
    "kaggle_huge": {
        "ticker": None,  # derived from filename (e.g. AAPL.csv)
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    },
    # Generic/standard format
    "standard": {
        "ticker": "ticker",
        "date": "date",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
    },
    # Yahoo Finance CSV export
    "yahoo_csv": {
        "ticker": None,  # derived from filename
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "adj_close": "Adj Close",
        "volume": "Volume",
    },
}


def load_price_csv(
    file_path: str,
    db: Session,
    column_mapping: Optional[dict] = None,
    mapping_name: Optional[str] = None,
    ticker_override: Optional[str] = None,
    chunk_size: int = 10_000,
) -> dict:
    """
    Load historical OHLCV prices from a CSV file into fact_stock_price.

    Args:
        file_path: Path to the CSV file
        db: SQLAlchemy session
        column_mapping: Dict mapping our fields to CSV columns
        mapping_name: Name of a preset column mapping (e.g. "kaggle_huge")
        ticker_override: Force all rows to this ticker (for single-ticker CSVs)
        chunk_size: Rows to process per batch (memory management)

    Returns:
        Stats dict with load results
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    # Resolve column mapping
    if column_mapping is None:
        mapping_name = mapping_name or "standard"
        column_mapping = COLUMN_MAPPINGS.get(mapping_name)
        if not column_mapping:
            raise ValueError(f"Unknown mapping: {mapping_name}. Available: {list(COLUMN_MAPPINGS.keys())}")

    # Derive ticker from filename if needed
    if not ticker_override and not column_mapping.get("ticker"):
        basename = os.path.splitext(os.path.basename(file_path))[0]
        ticker_override = basename.upper()

    start_time = time.time()
    log_entry = FactBulkLoadLog(
        source="csv_import",
        file_name=file_path,
        status="running",
    )
    db.add(log_entry)
    db.flush()

    stats = {"rows_loaded": 0, "rows_skipped": 0, "rows_errored": 0, "chunks": 0}

    try:
        # Build ticker→stock_id map
        if ticker_override:
            row = db.execute(
                text("SELECT stock_id FROM dim_stock WHERE ticker = :t"),
                {"t": ticker_override},
            ).fetchone()
            if not row:
                # Auto-create the stock entry
                db.execute(text(
                    "INSERT INTO dim_stock (ticker, company_name) VALUES (:t, :t)"
                ), {"t": ticker_override})
                db.flush()
                row = db.execute(
                    text("SELECT stock_id FROM dim_stock WHERE ticker = :t"),
                    {"t": ticker_override},
                ).fetchone()
            ticker_to_id = {ticker_override: row[0]}
        else:
            ticker_to_id = {}

        # Read CSV in chunks
        date_col = column_mapping.get("date", "date")
        reader = pd.read_csv(file_path, chunksize=chunk_size, parse_dates=[date_col])

        for chunk_df in reader:
            loaded, skipped, errored = _process_chunk(
                chunk_df, column_mapping, ticker_to_id, ticker_override, db,
            )
            stats["rows_loaded"] += loaded
            stats["rows_skipped"] += skipped
            stats["rows_errored"] += errored
            stats["chunks"] += 1

            # Flush and free memory
            db.flush()
            db.expire_all()

            if stats["chunks"] % 50 == 0:
                logger.info("CSV import progress",
                            file=os.path.basename(file_path),
                            chunks=stats["chunks"],
                            rows=stats["rows_loaded"])

        # Update date range in log
        log_entry.status = "success"
        log_entry.rows_loaded = stats["rows_loaded"]
        log_entry.rows_skipped = stats["rows_skipped"]
        log_entry.rows_errored = stats["rows_errored"]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()

        logger.info("CSV import complete", file=os.path.basename(file_path), **stats)
        return stats

    except Exception as e:
        log_entry.status = "error"
        log_entry.error_message = str(e)[:2000]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()
        logger.error("CSV import failed", file=file_path, error=str(e))
        raise


def _process_chunk(
    df: pd.DataFrame,
    mapping: dict,
    ticker_to_id: dict,
    ticker_override: Optional[str],
    db: Session,
) -> tuple[int, int, int]:
    """Process a single chunk of CSV rows. Returns (loaded, skipped, errored)."""
    loaded, skipped, errored = 0, 0, 0

    date_col = mapping.get("date", "date")
    open_col = mapping.get("open", "open")
    high_col = mapping.get("high", "high")
    low_col = mapping.get("low", "low")
    close_col = mapping.get("close", "close")
    volume_col = mapping.get("volume", "volume")
    adj_close_col = mapping.get("adj_close")
    ticker_col = mapping.get("ticker")

    for _, row in df.iterrows():
        try:
            # Determine ticker
            ticker = ticker_override or str(row.get(ticker_col, "")).strip().upper()
            if not ticker:
                skipped += 1
                continue

            # Resolve stock_id
            stock_id = ticker_to_id.get(ticker)
            if not stock_id:
                # Try to look up or create
                db_row = db.execute(
                    text("SELECT stock_id FROM dim_stock WHERE ticker = :t"),
                    {"t": ticker},
                ).fetchone()
                if db_row:
                    stock_id = db_row[0]
                else:
                    db.execute(text(
                        "INSERT IGNORE INTO dim_stock (ticker, company_name) VALUES (:t, :t)"
                    ), {"t": ticker})
                    db.flush()
                    db_row = db.execute(
                        text("SELECT stock_id FROM dim_stock WHERE ticker = :t"),
                        {"t": ticker},
                    ).fetchone()
                    stock_id = db_row[0] if db_row else None
                if stock_id:
                    ticker_to_id[ticker] = stock_id
                else:
                    skipped += 1
                    continue

            # Parse date
            trade_date = pd.to_datetime(row[date_col]).date()

            # Parse OHLCV
            close_raw = _safe_float(row.get(close_col))
            if close_raw is None or close_raw <= 0:
                skipped += 1
                continue

            open_raw = _safe_float(row.get(open_col))
            high_raw = _safe_float(row.get(high_col))
            low_raw = _safe_float(row.get(low_col))
            volume_raw = _safe_int(row.get(volume_col))
            close_adj = _safe_float(row.get(adj_close_col)) if adj_close_col else close_raw

            # Derived
            vwap = None
            if high_raw and low_raw and close_raw:
                vwap = (high_raw + low_raw + close_raw) / 3.0

            intraday_range = None
            if high_raw and low_raw and open_raw and open_raw > 0:
                intraday_range = ((high_raw - low_raw) / open_raw) * 100

            db.execute(text("""
                INSERT INTO fact_stock_price
                    (stock_id, trade_date, open_raw, high_raw, low_raw, close_raw,
                     volume_raw, close_adj, vwap, intraday_range_pct, data_source)
                VALUES
                    (:stock_id, :trade_date, :open_raw, :high_raw, :low_raw, :close_raw,
                     :volume_raw, :close_adj, :vwap, :intraday_range, :data_source)
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
            """), {
                "stock_id": stock_id,
                "trade_date": trade_date,
                "open_raw": open_raw,
                "high_raw": high_raw,
                "low_raw": low_raw,
                "close_raw": close_raw,
                "volume_raw": volume_raw,
                "close_adj": close_adj or close_raw,
                "vwap": vwap,
                "intraday_range": intraday_range,
                "data_source": "csv_import",
            })
            loaded += 1

        except Exception as e:
            errored += 1
            if errored <= 5:
                logger.debug("Row error in CSV chunk", error=str(e))

    return loaded, skipped, errored


def load_directory(
    directory: str,
    db: Session,
    mapping_name: str = "kaggle_huge",
    file_pattern: str = "*.csv",
    chunk_size: int = 10_000,
) -> dict:
    """
    Load all CSV files from a directory (e.g. Kaggle dataset with one CSV per ticker).

    Args:
        directory: Path to directory containing CSV files
        db: SQLAlchemy session
        mapping_name: Column mapping preset name
        file_pattern: Glob pattern for files (default: *.csv)
        chunk_size: Rows per processing batch

    Returns:
        Aggregate stats
    """
    import glob

    if not os.path.isdir(directory):
        raise FileNotFoundError(f"Directory not found: {directory}")

    files = sorted(glob.glob(os.path.join(directory, file_pattern)))
    if not files:
        raise FileNotFoundError(f"No files matching {file_pattern} in {directory}")

    start_time = time.time()
    log_entry = FactBulkLoadLog(
        source="csv_directory",
        file_name=directory,
        status="running",
    )
    db.add(log_entry)
    db.flush()

    total_stats = {"files": 0, "rows_loaded": 0, "rows_skipped": 0, "errors": []}

    for file_path in files:
        try:
            stats = load_price_csv(
                file_path=file_path,
                db=db,
                mapping_name=mapping_name,
                chunk_size=chunk_size,
            )
            total_stats["files"] += 1
            total_stats["rows_loaded"] += stats["rows_loaded"]
            total_stats["rows_skipped"] += stats["rows_skipped"]
        except Exception as e:
            total_stats["errors"].append(f"{os.path.basename(file_path)}: {str(e)}")

        if total_stats["files"] % 100 == 0:
            logger.info("Directory import progress",
                        files=total_stats["files"],
                        total=len(files),
                        rows=total_stats["rows_loaded"])

    elapsed = round(time.time() - start_time, 2)
    log_entry.status = "success" if not total_stats["errors"] else "error"
    log_entry.tickers_loaded = total_stats["files"]
    log_entry.rows_loaded = total_stats["rows_loaded"]
    log_entry.rows_errored = len(total_stats["errors"])
    log_entry.duration_sec = elapsed
    log_entry.completed_at = datetime.utcnow()
    if total_stats["errors"]:
        log_entry.error_message = "; ".join(total_stats["errors"][:10])
    db.flush()

    total_stats["duration_sec"] = elapsed
    logger.info("Directory import complete", **{k: v for k, v in total_stats.items() if k != "errors"})
    return total_stats


def _safe_float(val) -> Optional[float]:
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        f = float(val)
        if np.isnan(f) or np.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None
