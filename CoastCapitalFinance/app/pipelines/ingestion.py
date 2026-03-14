"""
Stock data ingestion pipeline.

Data Sources:
  - yfinance  : Primary OHLCV, splits, earnings, stock info (free, reliable)
  - NewsAPI   : News articles (100 req/day free)
  - Alpha Vantage: Supplemental fundamentals (25 req/day free)
  - FRED      : Macro indicators (Fed, Treasury yields, free)
"""
import time
import json
from datetime import date, datetime, timedelta
from typing import Optional
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import feedparser
from sqlalchemy.orm import Session
from sqlalchemy.dialects.mysql import insert as mysql_insert
from app.models.schema import (
    DimStock, DimDate, FactStockPrice, FactStockNews,
    FactEarnings, FactMacroIndicator, FactStockSplit
)
from app.models.database import get_db
from app.config import settings
from app.utils.logging_config import get_logger
from app.utils.llm_utils import analyze_news_article, analyze_earnings_report
from tenacity import retry, stop_after_attempt, wait_exponential

logger = get_logger(__name__)

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = settings.FRED_API_KEY or "abcdef"  # FRED accepts any key for public series


# ---------------------------------------------------------------------------
# Stock Dimension
# ---------------------------------------------------------------------------

def upsert_dim_stock(ticker: str, db: Session) -> DimStock:
    """Fetch stock metadata from yfinance and upsert into dim_stock."""
    yf_ticker = yf.Ticker(ticker)
    info = yf_ticker.info or {}

    market_cap = info.get("marketCap", 0) or 0
    if market_cap >= 200e9:
        cap_cat = "Mega"
    elif market_cap >= 10e9:
        cap_cat = "Large"
    elif market_cap >= 2e9:
        cap_cat = "Mid"
    elif market_cap >= 300e6:
        cap_cat = "Small"
    elif market_cap >= 50e6:
        cap_cat = "Micro"
    else:
        cap_cat = "Nano"

    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        stock = DimStock(ticker=ticker)
        db.add(stock)

    stock.company_name = info.get("longName") or info.get("shortName") or ticker
    stock.exchange = info.get("exchange")
    stock.sector = info.get("sector")
    stock.industry = info.get("industry")
    stock.country = info.get("country", "USA")
    stock.currency = info.get("currency", "USD")
    stock.market_cap_category = cap_cat
    stock.is_active = True
    stock.is_etf = info.get("quoteType") == "ETF"
    stock.description = (info.get("longBusinessSummary") or "")[:2000]

    db.flush()
    logger.info("Upserted dim_stock", ticker=ticker, stock_id=stock.stock_id)
    return stock


# ---------------------------------------------------------------------------
# Date Dimension
# ---------------------------------------------------------------------------

def populate_dim_date(start: date, end: date, db: Session) -> None:
    """Ensure date dimension covers the full range."""
    import calendar
    current = start
    while current <= end:
        date_id = int(current.strftime("%Y%m%d"))
        exists = db.query(DimDate).filter(DimDate.date_id == date_id).first()
        if not exists:
            d = DimDate(
                date_id=date_id,
                date=current,
                year=current.year,
                quarter=(current.month - 1) // 3 + 1,
                month=current.month,
                month_name=current.strftime("%B"),
                week_of_year=int(current.strftime("%W")),
                day_of_month=current.day,
                day_of_week=current.weekday(),
                day_name=current.strftime("%A"),
                is_weekend=current.weekday() >= 5,
                is_trading_day=current.weekday() < 5,
                is_quarter_end=current.month in (3, 6, 9, 12) and current.day == calendar.monthrange(current.year, current.month)[1],
                is_year_end=(current.month == 12 and current.day == 31),
            )
            db.add(d)
        current += timedelta(days=1)
    db.flush()
    logger.info("Populated dim_date", start=str(start), end=str(end))


# ---------------------------------------------------------------------------
# Stock Price Ingestion
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_and_store_prices(
    ticker: str,
    start_date: date,
    end_date: date,
    db: Session,
) -> int:
    """
    Fetch daily OHLCV from yfinance (auto-adjusted for splits & dividends)
    and store in fact_stock_price. Returns number of rows inserted/updated.
    """
    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        raise ValueError(f"Stock {ticker} not in dim_stock. Run upsert_dim_stock first.")

    yf_ticker = yf.Ticker(ticker)

    # yfinance 'auto_adjust=True' applies split + dividend adjustments
    hist = yf_ticker.history(
        start=start_date.strftime("%Y-%m-%d"),
        end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,  # gives adjusted prices
        actions=True,       # includes Dividends + Stock Splits columns
    )

    # Also fetch raw (unadjusted) for audit
    hist_raw = yf_ticker.history(
        start=start_date.strftime("%Y-%m-%d"),
        end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=False,
        actions=False,
    )

    if hist.empty:
        logger.warning("No price data returned", ticker=ticker, start=str(start_date))
        return 0

    populate_dim_date(start_date, end_date, db)

    rows_processed = 0
    prev_close = None

    for idx, (ts, row) in enumerate(hist.iterrows()):
        trade_date = ts.date() if hasattr(ts, 'date') else ts

        close_adj = float(row["Close"]) if not pd.isna(row["Close"]) else None
        if close_adj is None:
            continue

        # Raw prices
        raw_row = hist_raw.iloc[hist_raw.index.get_loc(ts)] if ts in hist_raw.index else None
        open_raw = float(raw_row["Open"]) if raw_row is not None and not pd.isna(raw_row["Open"]) else float(row["Open"])
        high_raw = float(raw_row["High"]) if raw_row is not None and not pd.isna(raw_row["High"]) else float(row["High"])
        low_raw = float(raw_row["Low"]) if raw_row is not None and not pd.isna(raw_row["Low"]) else float(row["Low"])
        close_raw = float(raw_row["Close"]) if raw_row is not None and not pd.isna(raw_row["Close"]) else float(row["Close"])

        open_adj = float(row["Open"]) if not pd.isna(row["Open"]) else None
        high_adj = float(row["High"]) if not pd.isna(row["High"]) else None
        low_adj = float(row["Low"]) if not pd.isna(row["Low"]) else None
        volume = int(row["Volume"]) if not pd.isna(row["Volume"]) else 0

        # Daily return
        daily_ret = (close_adj - prev_close) / prev_close if prev_close else None
        log_ret = float(np.log(close_adj / prev_close)) if prev_close and prev_close > 0 else None

        # VWAP approximation (need intraday for true VWAP; use midpoint)
        vwap = (high_adj + low_adj + close_adj) / 3 if high_adj and low_adj else None
        dollar_vol = close_adj * volume if volume else None
        intraday_range = ((high_adj - low_adj) / open_adj * 100) if high_adj and low_adj and open_adj else None
        gap_pct = ((open_adj - prev_close) / prev_close * 100) if prev_close and open_adj else None

        # Upsert
        existing = db.query(FactStockPrice).filter(
            FactStockPrice.stock_id == stock.stock_id,
            FactStockPrice.trade_date == trade_date
        ).first()

        if existing:
            existing.open_adj = open_adj
            existing.high_adj = high_adj
            existing.low_adj = low_adj
            existing.close_adj = close_adj
            existing.volume_adj = volume
            existing.open_raw = open_raw
            existing.high_raw = high_raw
            existing.low_raw = low_raw
            existing.close_raw = close_raw
            existing.volume_raw = volume
            existing.daily_return = daily_ret
            existing.log_return = log_ret
            existing.vwap = vwap
            existing.dollar_volume = dollar_vol
            existing.intraday_range_pct = intraday_range
            existing.gap_pct = gap_pct
        else:
            price = FactStockPrice(
                stock_id=stock.stock_id,
                trade_date=trade_date,
                open_raw=open_raw, high_raw=high_raw, low_raw=low_raw, close_raw=close_raw, volume_raw=volume,
                open_adj=open_adj, high_adj=high_adj, low_adj=low_adj, close_adj=close_adj, volume_adj=volume,
                daily_return=daily_ret, log_return=log_ret,
                vwap=vwap, dollar_volume=dollar_vol,
                intraday_range_pct=intraday_range, gap_pct=gap_pct,
                data_source="yfinance",
            )
            db.add(price)

        prev_close = close_adj
        rows_processed += 1

    db.flush()
    logger.info("Prices ingested", ticker=ticker, rows=rows_processed)
    return rows_processed


# ---------------------------------------------------------------------------
# Stock Split Detection & Restatement
# ---------------------------------------------------------------------------

def check_and_handle_splits(ticker: str, db: Session) -> list[dict]:
    """
    Detect stock splits from yfinance, record them, and restate historical prices.
    Returns list of splits found.
    """
    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        return []

    yf_ticker = yf.Ticker(ticker)
    hist = yf_ticker.history(period="max", auto_adjust=False, actions=True)

    if hist.empty or "Stock Splits" not in hist.columns:
        return []

    splits = hist[hist["Stock Splits"] > 0]["Stock Splits"]
    splits_found = []

    for split_date_ts, ratio in splits.items():
        split_date = split_date_ts.date() if hasattr(split_date_ts, 'date') else split_date_ts
        if ratio <= 0:
            continue

        # Check if already recorded
        existing = db.query(FactStockSplit).filter(
            FactStockSplit.stock_id == stock.stock_id,
            FactStockSplit.split_date == split_date
        ).first()

        if not existing:
            # Determine numerator/denominator (ratio is new/old, e.g. 4.0 = 4:1)
            num = int(ratio) if ratio == int(ratio) else ratio
            split_record = FactStockSplit(
                stock_id=stock.stock_id,
                ticker=ticker,
                split_date=split_date,
                split_ratio=float(ratio),
                numerator=int(num),
                denominator=1,
                history_restated=False,
                data_source="yfinance",
            )
            db.add(split_record)
            db.flush()

            # Restate history: prices before split_date get divided by ratio
            # Since we store adjusted prices from yfinance, we re-fetch the full
            # adjusted history to ensure apples-to-apples
            logger.info("Split detected - restating history", ticker=ticker,
                       split_date=str(split_date), ratio=ratio)

            _restate_prices_after_split(ticker, stock.stock_id, split_date, db)
            split_record.history_restated = True
            split_record.restated_at = datetime.utcnow()

            splits_found.append({"date": str(split_date), "ratio": ratio})

    db.flush()
    return splits_found


def _restate_prices_after_split(
    ticker: str,
    stock_id: int,
    split_date: date,
    db: Session,
) -> None:
    """Re-fetch all adjusted prices from yfinance to ensure historical continuity."""
    # The simplest and most reliable approach: re-download full adjusted history
    yf_ticker = yf.Ticker(ticker)
    hist = yf_ticker.history(period="max", auto_adjust=True, actions=False)

    if hist.empty:
        return

    for ts, row in hist.iterrows():
        trade_date = ts.date() if hasattr(ts, 'date') else ts
        existing = db.query(FactStockPrice).filter(
            FactStockPrice.stock_id == stock_id,
            FactStockPrice.trade_date == trade_date
        ).first()

        if existing:
            existing.close_adj = float(row["Close"]) if not pd.isna(row["Close"]) else existing.close_adj
            existing.open_adj = float(row["Open"]) if not pd.isna(row["Open"]) else existing.open_adj
            existing.high_adj = float(row["High"]) if not pd.isna(row["High"]) else existing.high_adj
            existing.low_adj = float(row["Low"]) if not pd.isna(row["Low"]) else existing.low_adj
            existing.is_restated = True

    db.flush()
    logger.info("History restated after split", ticker=ticker, split_date=str(split_date))


# ---------------------------------------------------------------------------
# News Ingestion
# ---------------------------------------------------------------------------

def fetch_and_store_news(
    ticker: str,
    company_name: str,
    days_back: int = 7,
    db: Session = None,
    use_llm: bool = True,
) -> int:
    """
    Fetch news for a ticker from multiple sources and store with LLM analysis.

    LLM analysis is limited to:
      - Only stocks of interest (watchlist) get LLM analysis automatically
      - Max LLM_MAX_ARTICLES_PER_STOCK (default 3) articles per stock per day
      - Uses parameterized provider (Gemini for watchlist, Ollama for big movers)

    Sources: yfinance news feed, NewsAPI (if configured)
    """
    from app.utils.llm_utils import get_provider_for_ticker, is_provider_available

    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        return 0

    articles_stored = 0
    llm_analyzed_count = 0
    max_llm_articles = settings.LLM_MAX_ARTICLES_PER_STOCK
    cutoff = datetime.utcnow() - timedelta(days=days_back)

    # Determine LLM provider for this ticker
    llm_provider = get_provider_for_ticker(ticker)
    provider_ready = use_llm and is_provider_available(llm_provider)

    # Source 1: yfinance news
    yf_ticker = yf.Ticker(ticker)
    yf_news = yf_ticker.news or []

    for item in yf_news[:20]:
        published_ms = item.get("providerPublishTime", 0)
        published_at = datetime.utcfromtimestamp(published_ms) if published_ms else datetime.utcnow()

        if published_at < cutoff:
            continue

        headline = item.get("title", "")
        url = item.get("link", "")
        source = item.get("publisher", "")

        # Skip duplicates
        exists = db.query(FactStockNews).filter(
            FactStockNews.stock_id == stock.stock_id,
            FactStockNews.headline == headline[:999],
        ).first()
        if exists:
            continue

        llm_data = {}
        if provider_ready and llm_analyzed_count < max_llm_articles:
            try:
                llm_data = analyze_news_article(
                    ticker=ticker,
                    company_name=company_name,
                    headline=headline,
                    article_text=headline,  # yfinance doesn't give full text
                    provider=llm_provider,
                )
                llm_analyzed_count += 1
            except Exception as e:
                logger.warning("LLM news analysis failed", ticker=ticker,
                               provider=llm_provider, error=str(e))

        news_record = FactStockNews(
            stock_id=stock.stock_id,
            ticker=ticker,
            headline=headline[:999],
            source=source[:199] if source else None,
            url=url[:1999] if url else None,
            published_at=published_at,
            llm_summary=llm_data.get("summary"),
            llm_key_points=llm_data.get("key_points"),
            llm_catalysts=llm_data.get("price_catalysts"),
            llm_risks=llm_data.get("price_risks"),
            sentiment_score=llm_data.get("sentiment_score"),
            sentiment_label=llm_data.get("sentiment_label"),
            relevance_score=llm_data.get("relevance_score"),
            llm_model=llm_data.get("llm_model"),
            llm_processed_at=datetime.fromisoformat(llm_data["llm_processed_at"]) if llm_data.get("llm_processed_at") else None,
            data_source="yfinance",
        )
        db.add(news_record)
        articles_stored += 1

    # Source 2: NewsAPI
    if settings.NEWS_API_KEY:
        remaining_llm = max_llm_articles - llm_analyzed_count
        articles_stored += _fetch_newsapi(
            ticker, company_name, stock.stock_id, days_back, cutoff, db,
            use_llm=provider_ready, llm_provider=llm_provider,
            max_llm_articles=remaining_llm,
        )

    db.flush()
    logger.info("News stored", ticker=ticker, articles=articles_stored)
    return articles_stored


def _fetch_newsapi(
    ticker: str,
    company_name: str,
    stock_id: int,
    days_back: int,
    cutoff: datetime,
    db: Session,
    use_llm: bool,
    llm_provider: str = None,
    max_llm_articles: int = 3,
) -> int:
    """Fetch articles from NewsAPI with parameterized LLM provider and article cap."""
    from_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    url = (
        f"https://newsapi.org/v2/everything"
        f"?q={ticker}+OR+\"{company_name}\""
        f"&from={from_date}"
        f"&sortBy=publishedAt"
        f"&pageSize=20"
        f"&apiKey={settings.NEWS_API_KEY}"
    )

    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning("NewsAPI fetch failed", ticker=ticker, error=str(e))
        return 0

    count = 0
    llm_count = 0
    for article in data.get("articles", []):
        published_str = article.get("publishedAt", "")
        try:
            published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            published_at = datetime.utcnow()

        if published_at < cutoff:
            continue

        headline = article.get("title", "")[:999]
        full_text = (article.get("content") or article.get("description") or "")[:5000]

        exists = db.query(FactStockNews).filter(
            FactStockNews.stock_id == stock_id,
            FactStockNews.headline == headline,
        ).first()
        if exists:
            continue

        llm_data = {}
        if use_llm and full_text and llm_count < max_llm_articles:
            try:
                llm_data = analyze_news_article(
                    ticker=ticker,
                    company_name=company_name,
                    headline=headline,
                    article_text=full_text,
                    provider=llm_provider,
                )
                llm_count += 1
            except Exception as e:
                logger.warning("LLM analysis failed", ticker=ticker,
                               provider=llm_provider, error=str(e))

        record = FactStockNews(
            stock_id=stock_id,
            ticker=ticker,
            headline=headline,
            source=(article.get("source", {}).get("name") or "")[:199],
            url=(article.get("url") or "")[:1999],
            published_at=published_at,
            author=(article.get("author") or "")[:199],
            full_text=full_text,
            llm_summary=llm_data.get("summary"),
            llm_key_points=llm_data.get("key_points"),
            llm_catalysts=llm_data.get("price_catalysts"),
            llm_risks=llm_data.get("price_risks"),
            sentiment_score=llm_data.get("sentiment_score"),
            sentiment_label=llm_data.get("sentiment_label"),
            relevance_score=llm_data.get("relevance_score"),
            llm_model=llm_data.get("llm_model"),
            llm_processed_at=datetime.fromisoformat(llm_data["llm_processed_at"]) if llm_data.get("llm_processed_at") else None,
            data_source="newsapi",
        )
        db.add(record)
        count += 1

    return count


# ---------------------------------------------------------------------------
# Earnings Ingestion
# ---------------------------------------------------------------------------

def fetch_and_store_earnings(ticker: str, db: Session, use_llm: bool = True) -> int:
    """Fetch quarterly earnings from yfinance and store with LLM analysis."""
    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        return 0

    yf_ticker = yf.Ticker(ticker)
    count = 0

    try:
        # Quarterly financials
        quarterly_financials = yf_ticker.quarterly_financials
        quarterly_balance = yf_ticker.quarterly_balance_sheet
        quarterly_cashflow = yf_ticker.quarterly_cashflow
        earnings_history = yf_ticker.earnings_history
        info = yf_ticker.info or {}
    except Exception as e:
        logger.warning("Failed to fetch earnings data", ticker=ticker, error=str(e))
        return 0

    # Use earnings_history for EPS data
    if earnings_history is not None and not earnings_history.empty:
        for _, row in earnings_history.iterrows():
            try:
                report_date_raw = row.get("Earnings Date") if "Earnings Date" in row.index else None
                period = row.get("Period") if "Period" in row.index else None

                if period is None:
                    continue

                # Parse fiscal year/quarter from period like "4Q2023"
                period_str = str(period)
                if len(period_str) >= 6 and "Q" in period_str:
                    parts = period_str.split("Q")
                    if len(parts) == 2:
                        q_num = int(parts[0]) if parts[0].isdigit() else int(parts[1])
                        yr = int(parts[1]) if parts[0].isdigit() else int(parts[0])
                    else:
                        continue
                else:
                    continue

                eps_actual = float(row.get("EPS Actual", 0) or 0)
                eps_est = float(row.get("EPS Estimate", 0) or 0)
                eps_surprise = eps_actual - eps_est
                eps_surprise_pct = (eps_surprise / abs(eps_est) * 100) if eps_est != 0 else None

                existing = db.query(FactEarnings).filter(
                    FactEarnings.stock_id == stock.stock_id,
                    FactEarnings.fiscal_year == yr,
                    FactEarnings.fiscal_quarter == q_num,
                ).first()

                metrics = {
                    "ticker": ticker,
                    "period": period_str,
                    "eps_actual": eps_actual,
                    "eps_estimate": eps_est,
                    "eps_surprise": eps_surprise,
                    "eps_surprise_pct": eps_surprise_pct,
                    "pe_ratio": info.get("forwardPE"),
                    "gross_margin": info.get("grossMargins"),
                    "operating_margin": info.get("operatingMargins"),
                    "net_margin": info.get("netMargins"),
                }

                llm_data = {}
                if use_llm and settings.ANTHROPIC_API_KEY and not existing:
                    try:
                        llm_data = analyze_earnings_report(
                            ticker=ticker,
                            company_name=stock.company_name,
                            fiscal_year=yr,
                            fiscal_quarter=q_num,
                            metrics=metrics,
                        )
                    except Exception as e:
                        logger.warning("LLM earnings analysis failed", ticker=ticker, error=str(e))

                if existing:
                    existing.eps_actual = eps_actual
                    existing.eps_estimate = eps_est
                    existing.eps_surprise = eps_surprise
                    existing.eps_surprise_pct = eps_surprise_pct
                else:
                    earnings = FactEarnings(
                        stock_id=stock.stock_id,
                        ticker=ticker,
                        fiscal_year=yr,
                        fiscal_quarter=q_num,
                        eps_actual=eps_actual,
                        eps_estimate=eps_est,
                        eps_surprise=eps_surprise,
                        eps_surprise_pct=eps_surprise_pct,
                        gross_margin=info.get("grossMargins"),
                        operating_margin=info.get("operatingMargins"),
                        net_margin=info.get("netMargins"),
                        pe_ratio=info.get("forwardPE"),
                        peg_ratio=info.get("pegRatio"),
                        price_to_book=info.get("priceToBook"),
                        price_to_sales=info.get("priceToSalesTrailing12Months"),
                        debt_to_equity=info.get("debtToEquity"),
                        llm_summary=llm_data.get("summary"),
                        llm_bull_case=llm_data.get("bull_case"),
                        llm_bear_case=llm_data.get("bear_case"),
                        llm_key_metrics=llm_data.get("key_metrics"),
                        llm_model=llm_data.get("llm_model"),
                        llm_processed_at=datetime.fromisoformat(llm_data["llm_processed_at"]) if llm_data.get("llm_processed_at") else None,
                        data_source="yfinance",
                    )
                    db.add(earnings)
                    count += 1

            except Exception as e:
                logger.warning("Error processing earnings row", ticker=ticker, error=str(e))
                continue

    db.flush()
    logger.info("Earnings stored", ticker=ticker, records=count)
    return count


# ---------------------------------------------------------------------------
# Macro Data (FRED + ETF proxies)
# ---------------------------------------------------------------------------

def fetch_and_store_macro(start_date: date, end_date: date, db: Session) -> int:
    """
    Fetch macro indicators from free sources:
    - VIX, SPY, QQQ, IWM from yfinance
    - Treasury yields via yfinance (^TNX, ^TYX, ^FVX, ^IRX)
    - DXY (dollar index) via yfinance (DX-Y.NYB)
    """
    macro_tickers = {
        "VIX": "^VIX",
        "SPY": "SPY",
        "QQQ": "QQQ",
        "IWM": "IWM",
        "DIA": "DIA",
        "GLD": "GLD",   # Gold
        "USO": "USO",   # Oil
        "T10Y": "^TNX", # 10Y Treasury yield
        "T30Y": "^TYX", # 30Y Treasury yield
        "T5Y": "^FVX",  # 5Y Treasury yield
        "T2Y": "^IRX",  # 3M Treasury (proxy)
        "HYG": "HYG",   # High Yield Bond
        "LQD": "LQD",   # Investment Grade Bond
        "DXY": "DX-Y.NYB",  # Dollar Index
    }

    data = {}
    for key, ticker in macro_tickers.items():
        try:
            hist = yf.download(
                ticker,
                start=start_date.strftime("%Y-%m-%d"),
                end=(end_date + timedelta(days=1)).strftime("%Y-%m-%d"),
                auto_adjust=True,
                progress=False,
            )
            if not hist.empty:
                data[key] = hist["Close"]
        except Exception as e:
            logger.warning("Failed to fetch macro ticker", ticker=ticker, error=str(e))

    if not data:
        return 0

    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df.index).date

    count = 0
    for idx_date, row in df.iterrows():
        existing = db.query(FactMacroIndicator).filter(
            FactMacroIndicator.indicator_date == idx_date
        ).first()

        vix = float(row.get("VIX")) if pd.notna(row.get("VIX")) else None
        spy = float(row.get("SPY")) if pd.notna(row.get("SPY")) else None
        t10y = float(row.get("T10Y")) if pd.notna(row.get("T10Y")) else None
        t2y = float(row.get("T2Y")) if pd.notna(row.get("T2Y")) else None
        yield_curve = (t10y - t2y) if (t10y and t2y) else None

        if existing:
            existing.vix = vix
            existing.spy_close = spy
            existing.qqq_close = float(row.get("QQQ")) if pd.notna(row.get("QQQ")) else None
            existing.iwm_close = float(row.get("IWM")) if pd.notna(row.get("IWM")) else None
            existing.dia_close = float(row.get("DIA")) if pd.notna(row.get("DIA")) else None
            existing.treasury_10y = t10y
            existing.treasury_2y = t2y
            existing.yield_curve_2_10 = yield_curve
            existing.treasury_30y = float(row.get("T30Y")) if pd.notna(row.get("T30Y")) else None
            existing.treasury_5y = float(row.get("T5Y")) if pd.notna(row.get("T5Y")) else None
            existing.gold_close = float(row.get("GLD")) if pd.notna(row.get("GLD")) else None
            existing.dollar_index = float(row.get("DXY")) if pd.notna(row.get("DXY")) else None
        else:
            macro = FactMacroIndicator(
                indicator_date=idx_date,
                vix=vix,
                spy_close=spy,
                qqq_close=float(row.get("QQQ")) if pd.notna(row.get("QQQ")) else None,
                iwm_close=float(row.get("IWM")) if pd.notna(row.get("IWM")) else None,
                dia_close=float(row.get("DIA")) if pd.notna(row.get("DIA")) else None,
                treasury_10y=t10y,
                treasury_2y=t2y,
                yield_curve_2_10=yield_curve,
                treasury_30y=float(row.get("T30Y")) if pd.notna(row.get("T30Y")) else None,
                treasury_5y=float(row.get("T5Y")) if pd.notna(row.get("T5Y")) else None,
                gold_close=float(row.get("GLD")) if pd.notna(row.get("GLD")) else None,
                dollar_index=float(row.get("DXY")) if pd.notna(row.get("DXY")) else None,
                data_source="yfinance",
            )
            db.add(macro)
            count += 1

    db.flush()
    logger.info("Macro data stored", start=str(start_date), end=str(end_date), rows=count)
    return count
