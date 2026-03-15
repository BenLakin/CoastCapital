"""
Universe loader: populates dim_stock from SEC EDGAR, NASDAQ Screener, and
Twelve Data (international exchanges).

Data sources (all free, no API key required):
- SEC EDGAR: ~10K US companies with CIK numbers (1 HTTP request)
- NASDAQ Screener: ~7K US stocks with market cap (2 HTTP requests)
- Twelve Data: ~38K international stocks across 8 exchanges (8 HTTP requests)
- Total: ~48K unique tickers, zero yfinance calls
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
NASDAQ_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
TWELVE_DATA_STOCKS_URL = "https://api.twelvedata.com/stocks"

# SEC EDGAR requires a User-Agent header
SEC_HEADERS = {
    "User-Agent": "CoastCapital Finance Platform support@coastcapital.dev",
    "Accept-Encoding": "gzip, deflate",
}

# NASDAQ Screener API requires a browser-like User-Agent
NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}

# International exchange configs: (Twelve Data code, yfinance suffix, country)
INTERNATIONAL_EXCHANGES = [
    ("LSE", ".L", "United Kingdom"),
    ("XFRA", ".DE", "Germany"),
    ("JPX", ".T", "Japan"),
    ("TSX", ".TO", "Canada"),
    ("HKEX", ".HK", "Hong Kong"),
    ("ASX", ".AX", "Australia"),
    ("Euronext", ".PA", "France"),
    ("SIX", ".SW", "Switzerland"),
]


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
        resp = requests.get(SEC_EDGAR_URL, headers=SEC_HEADERS, timeout=90)
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


def load_nasdaq_screener_tickers(db: Session) -> dict:
    """
    Download tickers from NASDAQ Screener API and bulk insert into dim_stock.
    ~7K stocks across all US exchanges (NASDAQ, NYSE, AMEX, etc.).
    Paginated: 5000 per request, typically 2 API calls.
    Idempotent: INSERT ... ON DUPLICATE KEY UPDATE.
    """
    start_time = time.time()
    log_entry = FactBulkLoadLog(source="nasdaq_screener", status="running")
    db.add(log_entry)
    db.flush()

    stats = {"total": 0, "skipped": 0}

    try:
        all_tickers = []
        offset = 0
        page_size = 5000

        while True:
            logger.info("Downloading NASDAQ screener page", offset=offset)
            resp = requests.get(
                NASDAQ_SCREENER_URL,
                params={"tableonly": "true", "limit": page_size, "offset": offset},
                headers=NASDAQ_HEADERS,
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()

            rows = data.get("data", {}).get("table", {}).get("rows", [])
            total_records = data.get("data", {}).get("totalrecords", 0)

            if not rows:
                break

            for row in rows:
                ticker = (row.get("symbol") or "").strip().upper()
                if not ticker or len(ticker) > 20:
                    stats["skipped"] += 1
                    continue
                if any(c in ticker for c in ["/", "^", "=", "+", " "]):
                    stats["skipped"] += 1
                    continue

                name = (row.get("name") or ticker)[:255]

                all_tickers.append({
                    "ticker": ticker,
                    "company_name": name,
                    "exchange": None,  # screener API doesn't provide exchange
                    "is_etf": False,
                })

            offset += page_size
            if offset >= total_records:
                break
            # Brief delay between pages
            time.sleep(1)

        stats["total"] = len(all_tickers)
        logger.info("Parsed NASDAQ screener tickers", total=len(all_tickers))

        if all_tickers:
            batch_size = 500
            for i in range(0, len(all_tickers), batch_size):
                batch = all_tickers[i:i + batch_size]
                _bulk_upsert_stocks(batch, db, source="nasdaq_screener")

            db.flush()

        log_entry.status = "success"
        log_entry.tickers_loaded = len(all_tickers)
        log_entry.rows_skipped = stats["skipped"]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()

        logger.info("NASDAQ screener load complete", **stats)
        return stats

    except Exception as e:
        log_entry.status = "error"
        log_entry.error_message = str(e)[:2000]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()
        logger.error("NASDAQ screener load failed", error=str(e))
        raise


def load_international_tickers(db: Session) -> dict:
    """
    Download international tickers from Twelve Data free API and bulk insert.
    ~38K stocks across 8 major exchanges (LSE, XFRA, JPX, TSX, HKEX, ASX, Euronext, SIX).
    Tickers are suffixed for yfinance compatibility (e.g. AZN.L, 7203.T).
    No API key required. One HTTP request per exchange.
    """
    start_time = time.time()
    log_entry = FactBulkLoadLog(source="twelve_data_intl", status="running")
    db.add(log_entry)
    db.flush()

    stats = {"exchanges": {}, "total": 0, "skipped": 0, "errors": []}

    try:
        all_tickers = []

        for exchange_code, yf_suffix, country in INTERNATIONAL_EXCHANGES:
            try:
                logger.info("Downloading international tickers",
                            exchange=exchange_code, country=country)
                resp = requests.get(
                    TWELVE_DATA_STOCKS_URL,
                    params={"exchange": exchange_code},
                    timeout=90,
                )
                resp.raise_for_status()
                data = resp.json()
                stocks = data.get("data", [])

                exchange_count = 0
                for stock in stocks:
                    symbol = (stock.get("symbol") or "").strip()
                    if not symbol or len(symbol) > 15:
                        stats["skipped"] += 1
                        continue
                    # Skip symbols with spaces or special chars
                    if any(c in symbol for c in [" ", "=", "+"]):
                        stats["skipped"] += 1
                        continue

                    # Build yfinance-compatible ticker
                    yf_ticker = f"{symbol}{yf_suffix}"
                    name = (stock.get("name") or yf_ticker)[:255]
                    currency = (stock.get("currency") or "")[:10] or None

                    all_tickers.append({
                        "ticker": yf_ticker,
                        "company_name": name,
                        "exchange": exchange_code,
                        "country": country,
                        "currency": currency,
                        "is_etf": stock.get("type", "").lower() in ("etf", "fund"),
                    })
                    exchange_count += 1

                stats["exchanges"][exchange_code] = exchange_count
                logger.info("Parsed exchange tickers",
                            exchange=exchange_code, count=exchange_count)

                # Brief delay between exchanges
                time.sleep(0.5)

            except Exception as e:
                error_msg = f"{exchange_code}: {str(e)}"
                logger.warning("Exchange load failed", exchange=exchange_code,
                               error=str(e))
                stats["errors"].append(error_msg)

        stats["total"] = len(all_tickers)
        logger.info("Parsed all international tickers", total=len(all_tickers))

        if all_tickers:
            batch_size = 500
            for i in range(0, len(all_tickers), batch_size):
                batch = all_tickers[i:i + batch_size]
                _bulk_upsert_stocks(batch, db, source="twelve_data_intl")

            db.flush()

        log_entry.status = "success" if not stats["errors"] else "partial"
        log_entry.tickers_loaded = stats["total"]
        log_entry.rows_skipped = stats["skipped"]
        log_entry.rows_errored = len(stats["errors"])
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        if stats["errors"]:
            log_entry.error_message = "; ".join(stats["errors"][:10])
        db.flush()

        logger.info("International load complete", **{
            k: v for k, v in stats.items() if k != "errors"
        })
        return stats

    except Exception as e:
        log_entry.status = "error"
        log_entry.error_message = str(e)[:2000]
        log_entry.duration_sec = round(time.time() - start_time, 2)
        log_entry.completed_at = datetime.utcnow()
        db.flush()
        logger.error("International load failed", error=str(e))
        raise


def _bulk_upsert_stocks(batch: list[dict], db: Session, source: str):
    """
    Bulk upsert stocks into dim_stock using INSERT ... ON DUPLICATE KEY UPDATE.
    Preserves existing stock_tier (doesn't downgrade watchlist to universe).
    """
    if not batch:
        return

    values_parts = []
    params = {}
    for idx, row in enumerate(batch):
        prefix = f"p{idx}"
        values_parts.append(
            f"(:{prefix}_ticker, :{prefix}_name, :{prefix}_exchange, "
            f":{prefix}_is_etf, :{prefix}_cik, :{prefix}_is_active, "
            f":{prefix}_stock_tier, :{prefix}_country, :{prefix}_currency, NOW(), NOW())"
        )
        params[f"{prefix}_ticker"] = row["ticker"]
        params[f"{prefix}_name"] = row.get("company_name", row["ticker"])
        params[f"{prefix}_exchange"] = row.get("exchange")
        params[f"{prefix}_is_etf"] = row.get("is_etf", False)
        params[f"{prefix}_cik"] = row.get("cik")
        params[f"{prefix}_is_active"] = 1
        params[f"{prefix}_stock_tier"] = row.get("stock_tier", "universe")
        params[f"{prefix}_country"] = row.get("country", "USA")
        params[f"{prefix}_currency"] = row.get("currency", "USD")

    sql = f"""
        INSERT INTO dim_stock (ticker, company_name, exchange, is_etf, cik, is_active,
                               stock_tier, country, currency, created_at, updated_at)
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
            country = COALESCE(VALUES(country), country),
            currency = COALESCE(VALUES(currency), currency),
            updated_at = NOW()
    """
    db.execute(text(sql), params)


def load_full_universe(db: Session) -> dict:
    """
    Orchestrate full universe load: SEC EDGAR + NASDAQ Screener + International.
    ~48K tickers total. Marks watchlist tickers to preserve their tier.
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

    # 2. Load NASDAQ Screener (~7K tickers, 2 HTTP requests)
    try:
        results["nasdaq_screener"] = load_nasdaq_screener_tickers(db)
    except Exception as e:
        results["nasdaq_screener_error"] = str(e)

    # 3. Load international exchanges (~38K tickers, 8 HTTP requests)
    try:
        results["international"] = load_international_tickers(db)
    except Exception as e:
        results["international_error"] = str(e)

    # 4. Migrate any legacy 'screener'/'reference' tiers to 'universe'
    migrated = db.execute(
        text("UPDATE dim_stock SET stock_tier = 'universe' WHERE stock_tier IN ('screener', 'reference')")
    ).rowcount
    if migrated:
        db.flush()
        results["legacy_tiers_migrated"] = migrated
        logger.info("Migrated legacy tiers to universe", count=migrated)

    # 5. Ensure watchlist tickers are marked as 'watchlist' tier
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

    # 6. Get tier counts
    tier_counts = {}
    for row in db.execute(text(
        "SELECT stock_tier, COUNT(*) as cnt FROM dim_stock WHERE is_active = 1 GROUP BY stock_tier"
    )):
        tier_counts[row[0]] = row[1]
    results["tier_counts"] = tier_counts
    results["total_tickers"] = sum(tier_counts.values())

    logger.info("Universe load complete", total=results["total_tickers"], tiers=tier_counts)
    return results
