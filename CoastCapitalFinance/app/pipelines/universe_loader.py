"""
Universe loader: populates dim_stock from SEC EDGAR and NASDAQ Trader data.

Total HTTP requests: 3 (company_tickers.json, nasdaqlisted.txt, otherlisted.txt).
Zero yfinance calls — no rate limiting concerns.
"""
import time
import requests
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.schema import DimStock, FactBulkLoadLog
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

SEC_EDGAR_URL = "https://www.sec.gov/files/company_tickers.json"
NASDAQ_LISTED_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
NASDAQ_OTHER_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

# SEC EDGAR requires a User-Agent header
SEC_HEADERS = {
    "User-Agent": "CoastCapital Finance Platform support@coastcapital.dev",
    "Accept-Encoding": "gzip, deflate",
}


def load_sec_edgar_tickers(db: Session) -> dict:
    """
    Download SEC EDGAR company_tickers.json and bulk insert into dim_stock.
    ~10K US-listed companies with CIK numbers.
    Idempotent: uses INSERT ... ON DUPLICATE KEY UPDATE.
    """
    start_time = time.time()
    log_entry = FactBulkLoadLog(source="sec_edgar", status="running")
    db.add(log_entry)
    db.flush()

    stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

    try:
        logger.info("Downloading SEC EDGAR tickers")
        resp = requests.get(SEC_EDGAR_URL, headers=SEC_HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Format: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc"}, ...}
        tickers_data = []
        for entry in data.values():
            ticker = entry.get("ticker", "").strip().upper()
            if not ticker or len(ticker) > 20:
                stats["skipped"] += 1
                continue
            # Skip tickers with special chars (warrants, units, etc.)
            if any(c in ticker for c in ["/", "^", "=", "+", " "]):
                stats["skipped"] += 1
                continue
            tickers_data.append({
                "ticker": ticker,
                "company_name": entry.get("title", ticker)[:255],
                "cik": str(entry.get("cik_str", ""))[:20],
            })

        logger.info("Parsed SEC EDGAR tickers", count=len(tickers_data))

        # Bulk upsert using raw SQL for performance
        if tickers_data:
            batch_size = 500
            for i in range(0, len(tickers_data), batch_size):
                batch = tickers_data[i:i + batch_size]
                _bulk_upsert_stocks(batch, db, source="sec_edgar")
                stats["inserted"] += len(batch)

            db.flush()

        log_entry.status = "success"
        log_entry.tickers_loaded = stats["inserted"]
        log_entry.rows_skipped = stats["skipped"]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()

        logger.info("SEC EDGAR load complete", **stats)
        return stats

    except Exception as e:
        log_entry.status = "error"
        log_entry.error_message = str(e)[:2000]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()
        logger.error("SEC EDGAR load failed", error=str(e))
        raise


def load_nasdaq_trader_tickers(db: Session) -> dict:
    """
    Download NASDAQ Trader symbol files and bulk insert into dim_stock.
    nasdaqlisted.txt — NASDAQ-listed securities
    otherlisted.txt  — NYSE, AMEX, ARCA, BATS, etc.
    Idempotent: INSERT ... ON DUPLICATE KEY UPDATE.
    """
    start_time = time.time()
    log_entry = FactBulkLoadLog(source="nasdaq_trader", status="running")
    db.add(log_entry)
    db.flush()

    stats = {"nasdaq": 0, "other": 0, "skipped": 0}

    try:
        # --- NASDAQ-listed ---
        logger.info("Downloading NASDAQ listed tickers")
        resp = requests.get(NASDAQ_LISTED_URL, timeout=60)
        resp.raise_for_status()
        nasdaq_tickers = _parse_nasdaq_listed(resp.text)
        stats["nasdaq"] = len(nasdaq_tickers)

        # --- Other exchanges (NYSE, AMEX, ARCA, BATS) ---
        logger.info("Downloading other exchange tickers")
        resp = requests.get(NASDAQ_OTHER_URL, timeout=60)
        resp.raise_for_status()
        other_tickers = _parse_other_listed(resp.text)
        stats["other"] = len(other_tickers)

        # Combine and bulk upsert
        all_tickers = nasdaq_tickers + other_tickers
        logger.info("Parsed NASDAQ Trader tickers", total=len(all_tickers))

        if all_tickers:
            batch_size = 500
            for i in range(0, len(all_tickers), batch_size):
                batch = all_tickers[i:i + batch_size]
                _bulk_upsert_stocks(batch, db, source="nasdaq_trader")

            db.flush()

        log_entry.status = "success"
        log_entry.tickers_loaded = len(all_tickers)
        log_entry.rows_skipped = stats["skipped"]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()

        logger.info("NASDAQ Trader load complete", **stats)
        return stats

    except Exception as e:
        log_entry.status = "error"
        log_entry.error_message = str(e)[:2000]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()
        logger.error("NASDAQ Trader load failed", error=str(e))
        raise


def _parse_nasdaq_listed(raw_text: str) -> list[dict]:
    """Parse nasdaqlisted.txt pipe-delimited format."""
    tickers = []
    lines = raw_text.strip().split("\n")
    # Header: Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
    for line in lines[1:]:  # skip header
        if line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        ticker = parts[0].strip().upper()
        if not ticker or len(ticker) > 20:
            continue
        if any(c in ticker for c in ["/", "^", "=", "+", " "]):
            continue
        # Test issues: Y = test, N = real
        if parts[3].strip().upper() == "Y":
            continue
        is_etf = parts[6].strip().upper() == "Y"
        tickers.append({
            "ticker": ticker,
            "company_name": parts[1].strip()[:255] or ticker,
            "exchange": "NASDAQ",
            "is_etf": is_etf,
        })
    return tickers


def _parse_other_listed(raw_text: str) -> list[dict]:
    """Parse otherlisted.txt pipe-delimited format."""
    tickers = []
    lines = raw_text.strip().split("\n")
    # Header: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            continue
        parts = line.split("|")
        if len(parts) < 7:
            continue
        ticker = parts[0].strip().upper()
        if not ticker or len(ticker) > 20:
            continue
        if any(c in ticker for c in ["/", "^", "=", "+", " "]):
            continue
        # Test issues
        if parts[6].strip().upper() == "Y":
            continue
        # Exchange mapping
        exchange_code = parts[2].strip().upper()
        exchange_map = {
            "A": "AMEX", "N": "NYSE", "P": "ARCA",
            "Z": "BATS", "V": "IEXG",
        }
        exchange = exchange_map.get(exchange_code, exchange_code)
        is_etf = parts[4].strip().upper() == "Y"
        tickers.append({
            "ticker": ticker,
            "company_name": parts[1].strip()[:255] or ticker,
            "exchange": exchange,
            "is_etf": is_etf,
        })
    return tickers


def _bulk_upsert_stocks(batch: list[dict], db: Session, source: str):
    """
    Bulk upsert stocks into dim_stock using INSERT ... ON DUPLICATE KEY UPDATE.
    Preserves existing stock_tier (doesn't downgrade watchlist to reference).
    """
    if not batch:
        return

    values_parts = []
    params = {}
    for idx, row in enumerate(batch):
        prefix = f"p{idx}"
        values_parts.append(
            f"(:{prefix}_ticker, :{prefix}_name, :{prefix}_exchange, "
            f":{prefix}_is_etf, :{prefix}_cik, :{prefix}_is_active)"
        )
        params[f"{prefix}_ticker"] = row["ticker"]
        params[f"{prefix}_name"] = row.get("company_name", row["ticker"])
        params[f"{prefix}_exchange"] = row.get("exchange")
        params[f"{prefix}_is_etf"] = row.get("is_etf", False)
        params[f"{prefix}_cik"] = row.get("cik")
        params[f"{prefix}_is_active"] = 1

    sql = f"""
        INSERT INTO dim_stock (ticker, company_name, exchange, is_etf, cik, is_active)
        VALUES {', '.join(values_parts)}
        ON DUPLICATE KEY UPDATE
            company_name = IF(
                company_name = ticker OR company_name = '',
                VALUES(company_name),
                company_name
            ),
            exchange = COALESCE(VALUES(exchange), exchange),
            is_etf = VALUES(is_etf),
            cik = COALESCE(VALUES(cik), cik),
            updated_at = NOW()
    """
    db.execute(text(sql), params)


def load_full_universe(db: Session) -> dict:
    """
    Orchestrate full universe load: SEC EDGAR + NASDAQ Trader.
    Marks existing watchlist tickers to preserve their tier.
    Returns combined stats.
    """
    from app.config import settings

    logger.info("Starting full universe load")
    results = {}

    # 1. Load SEC EDGAR (~10K tickers, 1 HTTP request)
    try:
        results["sec_edgar"] = load_sec_edgar_tickers(db)
    except Exception as e:
        results["sec_edgar_error"] = str(e)

    # 2. Load NASDAQ Trader (~8K tickers, 2 HTTP requests)
    try:
        results["nasdaq_trader"] = load_nasdaq_trader_tickers(db)
    except Exception as e:
        results["nasdaq_trader_error"] = str(e)

    # 3. Ensure watchlist tickers are marked as 'watchlist' tier
    watchlist_tickers = settings.watchlist
    if watchlist_tickers:
        placeholders = ", ".join([f":wl{i}" for i in range(len(watchlist_tickers))])
        params = {f"wl{i}": t for i, t in enumerate(watchlist_tickers)}
        db.execute(
            text(f"UPDATE dim_stock SET stock_tier = 'watchlist' WHERE ticker IN ({placeholders})"),
            params,
        )
        db.flush()
        results["watchlist_marked"] = len(watchlist_tickers)

    # 4. Get tier counts
    tier_counts = {}
    for row in db.execute(text(
        "SELECT stock_tier, COUNT(*) as cnt FROM dim_stock WHERE is_active = 1 GROUP BY stock_tier"
    )):
        tier_counts[row[0]] = row[1]
    results["tier_counts"] = tier_counts
    results["total_tickers"] = sum(tier_counts.values())

    logger.info("Universe load complete", total=results["total_tickers"], tiers=tier_counts)
    return results
