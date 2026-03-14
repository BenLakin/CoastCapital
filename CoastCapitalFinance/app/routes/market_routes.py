"""
Market data routes for the Finance Dashboard.

Provides real-time and near-real-time market data for:
  - Market overview (indices, VIX, macro)
  - Fortune 500 top movers (gainers / losers / unusual volume)
  - Big Noise alerts (stocks with unusual price/volume activity)
  - Configurable watchlist prices + 30d sparkline history
  - Per-ticker news headlines

Caching: All endpoints use TTL-based in-memory cache to avoid
yfinance rate limits. Heavy endpoints (Fortune 500 batch) cache 10 min.
"""
import time
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timezone
from flask import Blueprint, jsonify, send_from_directory, current_app, request
import yfinance as yf
import pandas as pd
import numpy as np
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

market_bp = Blueprint("market", __name__)

# ---------------------------------------------------------------------------
# Fortune 500 (publicly-traded, major US large-caps across all sectors)
# ---------------------------------------------------------------------------

FORTUNE_500_TICKERS = [
    # Technology
    "AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA","AVGO","ORCL","CSCO",
    "IBM","INTC","AMD","QCOM","NOW","ADBE","CRM","INTU","TXN","MU",
    "AMAT","LRCX","KLAC","ADI","MRVL","PANW","SNDK","HPQ","HPE",
    # Financial
    "JPM","BAC","WFC","GS","MS","C","BLK","AXP","USB","COF",
    "MET","PRU","TRV","AFL","PGR","ALL","CME","ICE","SPGI","MCO",
    # Healthcare
    "JNJ","UNH","PFE","ABBV","LLY","MRK","CVS","ABT","TMO","DHR",
    "BMY","AMGN","GILD","REGN","VRTX","ISRG","BSX","MDT","SYK","ZBH",
    # Energy
    "XOM","CVX","COP","SLB","EOG","MPC","PSX","VLO","HES","OXY",
    # Consumer (Staples + Discretionary)
    "WMT","HD","MCD","COST","TGT","NKE","SBUX","DG","LOW","AMZN",
    "F","GM","FORD","TJX","ROST","YUM","CMG","DHI","LEN","PG",
    "KO","PEP","PM","MO","CL","KMB","GIS","K","HSY","MDLZ",
    # Industrial
    "CAT","HON","RTX","GE","UPS","FDX","BA","LMT","NOC","DE",
    "MMM","ETN","EMR","PH","GWW","FAST","ROK","IR","XYL","CARR",
    # Telecom / Media
    "T","VZ","TMUS","CMCSA","DIS","NFLX","WBD","PARA","FOX",
    # Utilities
    "NEE","DUK","SO","D","SRE","AEP","EXC","PCG","ED","FE",
    # Materials
    "LIN","APD","FCX","NEM","DOW","DD","PPG","ALB","CF","MOS",
    # Real Estate
    "AMT","PLD","EQIX","CCI","DLR","O","WELL","AVB","EQR","PSA",
    # ETFs (for reference/benchmark)
    "SPY","QQQ","IWM","DIA","GLD","SLV","USO","XLE","XLF","XLK",
]

TICKER_NAMES = {
    "AAPL":"Apple","MSFT":"Microsoft","NVDA":"NVIDIA","GOOGL":"Alphabet",
    "META":"Meta Platforms","AMZN":"Amazon","TSLA":"Tesla","AVGO":"Broadcom",
    "ORCL":"Oracle","CSCO":"Cisco","IBM":"IBM","INTC":"Intel","AMD":"AMD",
    "QCOM":"Qualcomm","NOW":"ServiceNow","ADBE":"Adobe","CRM":"Salesforce",
    "INTU":"Intuit","TXN":"Texas Instruments","MU":"Micron",
    "AMAT":"Applied Materials","LRCX":"Lam Research","HPQ":"HP Inc",
    "JPM":"JPMorgan","BAC":"Bank of America","WFC":"Wells Fargo",
    "GS":"Goldman Sachs","MS":"Morgan Stanley","C":"Citigroup",
    "BLK":"BlackRock","AXP":"American Express","USB":"U.S. Bancorp",
    "COF":"Capital One","MET":"MetLife","PRU":"Prudential",
    "TRV":"Travelers","AFL":"Aflac","PGR":"Progressive","ALL":"Allstate",
    "CME":"CME Group","ICE":"Intercontinental Exchange",
    "SPGI":"S&P Global","MCO":"Moody's",
    "JNJ":"Johnson & Johnson","UNH":"UnitedHealth","PFE":"Pfizer",
    "ABBV":"AbbVie","LLY":"Eli Lilly","MRK":"Merck","CVS":"CVS Health",
    "ABT":"Abbott","TMO":"Thermo Fisher","DHR":"Danaher","BMY":"Bristol-Myers",
    "AMGN":"Amgen","GILD":"Gilead","REGN":"Regeneron","VRTX":"Vertex",
    "ISRG":"Intuitive Surgical","BSX":"Boston Scientific","MDT":"Medtronic",
    "XOM":"Exxon Mobil","CVX":"Chevron","COP":"ConocoPhillips","SLB":"Schlumberger",
    "EOG":"EOG Resources","MPC":"Marathon Petroleum","PSX":"Phillips 66",
    "VLO":"Valero Energy","HES":"Hess","OXY":"Occidental",
    "WMT":"Walmart","HD":"Home Depot","MCD":"McDonald's","COST":"Costco",
    "TGT":"Target","NKE":"Nike","SBUX":"Starbucks","DG":"Dollar General",
    "LOW":"Lowe's","F":"Ford","GM":"General Motors","TJX":"TJX Companies",
    "ROST":"Ross Stores","YUM":"Yum! Brands","CMG":"Chipotle",
    "DHI":"D.R. Horton","LEN":"Lennar","PG":"Procter & Gamble",
    "KO":"Coca-Cola","PEP":"PepsiCo","PM":"Philip Morris","MO":"Altria",
    "CL":"Colgate-Palmolive","KMB":"Kimberly-Clark","GIS":"General Mills",
    "K":"Kellogg's","HSY":"Hershey","MDLZ":"Mondelez",
    "CAT":"Caterpillar","HON":"Honeywell","RTX":"RTX Corp","GE":"GE Aerospace",
    "UPS":"UPS","FDX":"FedEx","BA":"Boeing","LMT":"Lockheed Martin",
    "NOC":"Northrop Grumman","DE":"John Deere","MMM":"3M","ETN":"Eaton",
    "EMR":"Emerson Electric","PH":"Parker Hannifin","GWW":"W.W. Grainger",
    "T":"AT&T","VZ":"Verizon","TMUS":"T-Mobile","CMCSA":"Comcast","DIS":"Disney",
    "NFLX":"Netflix","WBD":"Warner Bros. Discovery","PARA":"Paramount",
    "NEE":"NextEra Energy","DUK":"Duke Energy","SO":"Southern Company",
    "D":"Dominion Energy","SRE":"Sempra","AEP":"American Electric Power",
    "LIN":"Linde","APD":"Air Products","FCX":"Freeport-McMoRan",
    "NEM":"Newmont","DOW":"Dow Inc","DD":"DuPont",
    "AMT":"American Tower","PLD":"Prologis","EQIX":"Equinix",
    "CCI":"Crown Castle","DLR":"Digital Realty","O":"Realty Income",
    "SPY":"SPDR S&P 500","QQQ":"Invesco QQQ","IWM":"iShares Russell 2000",
    "DIA":"SPDR Dow Jones","GLD":"SPDR Gold Shares","SLV":"iShares Silver",
    "USO":"United States Oil","XLE":"Energy Select SPDR",
    "XLF":"Financial Select SPDR","XLK":"Technology Select SPDR",
    # Watchlist-specific
    "Z":"Zillow Group","ZG":"Zillow Group A","GLD":"SPDR Gold Shares",
    "IAU":"iShares Gold Trust","BTC-USD":"Bitcoin",
}

DEFAULT_WATCHLIST = ["META","AAPL","Z","NVDA","GOOGL","GLD","BTC-USD"]

# ---------------------------------------------------------------------------
# TTL Cache
# ---------------------------------------------------------------------------

_cache: dict = {}
_cache_lock = threading.Lock()


def _cache_get(key: str):
    with _cache_lock:
        entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < entry["ttl"]:
        return entry["data"]
    return None


def _cache_set(key: str, data, ttl: int = 300):
    with _cache_lock:
        _cache[key] = {"data": data, "ts": time.time(), "ttl": ttl}


def _safe_float(val, default=None):
    try:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return default
        return round(float(val), 4)
    except Exception:
        return default


def _ticker_name(ticker: str) -> str:
    return TICKER_NAMES.get(ticker.upper(), ticker)


def _format_large_number(v, prefix: str = "", use_thousands: bool = False) -> str:
    """Format a large number to human-readable string (e.g. $1.2T, 3.5M, 120K)."""
    if v is None:
        return "—"
    v = abs(float(v))
    if v >= 1e12:
        return f"{prefix}{v/1e12:.1f}T"
    if v >= 1e9:
        return f"{prefix}{v/1e9:.1f}B"
    if v >= 1e6:
        return f"{prefix}{v/1e6:.1f}M"
    if use_thousands and v >= 1e3:
        return f"{prefix}{v/1e3:.0f}K"
    if prefix:
        return f"{prefix}{v:,.0f}"
    return str(int(v))


def _format_volume(v):
    return _format_large_number(v, use_thousands=True)


def _fmt_mcap(v):
    return _format_large_number(v, prefix="$")


def _fetch_ticker_changes(ticker_map: dict) -> list:
    """Download 2-day close data and compute daily change for a dict of {symbol: label}.

    Returns list of dicts with keys: symbol, label, price, change, change_pct, positive.
    """
    raw = yf.download(
        list(ticker_map.keys()),
        period="2d",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    if raw.empty:
        return []

    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    result = []

    for sym, label in ticker_map.items():
        try:
            if sym not in closes.columns:
                continue
            series = closes[sym].dropna()
            if len(series) < 2:
                continue
            price = float(series.iloc[-1])
            prev = float(series.iloc[-2])
            chg = price - prev
            pct = chg / prev * 100 if prev else 0
            result.append({
                "symbol": sym,
                "label": label,
                "price": _safe_float(price),
                "change": _safe_float(chg),
                "change_pct": _safe_float(pct),
                "positive": chg >= 0,
            })
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# Market Overview
# ---------------------------------------------------------------------------

@market_bp.route("/api/v1/market/overview")
def market_overview():
    cached = _cache_get("overview")
    if cached:
        return jsonify(cached)

    overview_tickers = {
        "SPY": "S&P 500", "QQQ": "NASDAQ 100", "DIA": "Dow Jones",
        "IWM": "Russell 2000", "^VIX": "VIX", "GLD": "Gold",
        "USO": "Oil (WTI)", "BTC-USD": "Bitcoin",
        "^TNX": "10Y Yield", "^IRX": "2Y Yield", "DX-Y.NYB": "DXY",
    }

    try:
        result = _fetch_ticker_changes(overview_tickers)
        _cache_set("overview", result, ttl=180)
        return jsonify(result)

    except Exception as e:
        logger.error("Market overview error", error=str(e))
        return jsonify([])


# ---------------------------------------------------------------------------
# Fortune 500 Movers + Big Noise
# ---------------------------------------------------------------------------

@market_bp.route("/api/v1/market/movers")
def fortune500_movers():
    cached = _cache_get("movers")
    if cached:
        return jsonify(cached)

    try:
        tickers = [t for t in FORTUNE_500_TICKERS if not t.startswith("^")]
        raw = yf.download(
            tickers,
            period="1mo",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        if raw.empty:
            return jsonify({"gainers": [], "losers": [], "big_noise": [], "unchanged": []})

        closes  = raw["Close"]
        volumes = raw["Volume"]

        if not isinstance(closes, pd.DataFrame):
            return jsonify({"gainers": [], "losers": [], "big_noise": [], "unchanged": []})

        # Daily return: most-recent vs prior day
        daily_pct   = (closes.pct_change().iloc[-1] * 100)
        daily_chg   = (closes.iloc[-1] - closes.iloc[-2])
        avg_vol_20d = volumes.rolling(20).mean().iloc[-1]
        today_vol   = volumes.iloc[-1]
        vol_ratio   = today_vol / avg_vol_20d.replace(0, np.nan)

        rows = []
        for ticker in tickers:
            if ticker not in closes.columns:
                continue
            price = _safe_float(closes.iloc[-1].get(ticker))
            pct   = _safe_float(daily_pct.get(ticker))
            chg   = _safe_float(daily_chg.get(ticker))
            vr    = _safe_float(vol_ratio.get(ticker), 1.0)
            vol   = _safe_float(today_vol.get(ticker))

            if price is None or pct is None:
                continue

            rows.append({
                "ticker":       ticker,
                "name":         _ticker_name(ticker),
                "price":        price,
                "change":       chg,
                "change_pct":   pct,
                "volume_ratio": vr,
                "volume":       _format_volume(vol),
                "positive":     pct >= 0,
            })

        gainers   = sorted([r for r in rows if r["change_pct"] > 0],  key=lambda x: -x["change_pct"])[:10]
        losers    = sorted([r for r in rows if r["change_pct"] < 0],  key=lambda x:  x["change_pct"])[:10]

        # Big Noise: large move OR volume spike with meaningful move
        big_noise = [
            r for r in rows
            if abs(r["change_pct"]) >= 3.0
            or (r.get("volume_ratio", 1) >= 2.5 and abs(r["change_pct"]) >= 1.5)
        ]
        big_noise.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

        result = {
            "gainers":   gainers,
            "losers":    losers,
            "big_noise": big_noise[:15],
            "as_of":     datetime.utcnow().strftime("%H:%M UTC"),
            "total_tracked": len(rows),
        }

        _cache_set("movers", result, ttl=600)
        return jsonify(result)

    except Exception as e:
        logger.error("Fortune 500 movers error", error=str(e), exc_info=True)
        return jsonify({"gainers": [], "losers": [], "big_noise": [], "error": str(e)})


# ---------------------------------------------------------------------------
# Market Highlights — % movers, market cap movers, indices
# ---------------------------------------------------------------------------

@market_bp.route("/api/v1/market/highlights")
def market_highlights():
    """Dashboard highlights: top % movers, market cap movers, S&P500/Nasdaq indices."""
    cached = _cache_get("highlights")
    if cached:
        return jsonify(cached)

    try:
        # ── Fetch major indices via shared helper ──
        index_tickers = {"^GSPC": "S&P 500", "^IXIC": "NASDAQ", "^DJI": "Dow Jones"}
        indices = _fetch_ticker_changes(index_tickers)

        # ── Use existing movers data (gracefully degrade if not cached yet) ──
        movers = _cache_get("movers") or {}
        pct_gainers = movers.get("gainers", [])[:5]
        pct_losers = movers.get("losers", [])[:5]

        # ── Market cap movers (parallel fetch) ──
        all_movers = movers.get("gainers", []) + movers.get("losers", [])
        movers_lookup = {m["ticker"]: m for m in all_movers}
        big_tickers = [m["ticker"] for m in all_movers[:12]]
        mcap_movers = _fetch_mcap_movers(big_tickers, movers_lookup)

        # Don't cache degraded results when movers data wasn't available
        has_movers = bool(movers)
        result = {
            "indices": indices,
            "pct_gainers": pct_gainers, "pct_losers": pct_losers,
            "mcap_movers": mcap_movers[:8],
            "as_of": datetime.utcnow().strftime("%H:%M UTC"),
        }
        if has_movers:
            _cache_set("highlights", result, ttl=300)
        return jsonify(result)

    except Exception as e:
        logger.error("Highlights error", error=str(e), exc_info=True)
        return jsonify({"indices": [], "pct_gainers": [], "pct_losers": [], "mcap_movers": []})


def _fetch_single_mcap(ticker: str) -> tuple:
    """Fetch market cap for a single ticker. Returns (ticker, market_cap) or (ticker, None)."""
    try:
        info = yf.Ticker(ticker).fast_info
        mc = getattr(info, "market_cap", None)
        return (ticker, mc if mc and mc > 0 else None)
    except Exception:
        return (ticker, None)


def _fetch_mcap_movers(tickers: list, movers_lookup: dict) -> list:
    """Fetch market caps in parallel and build sorted mcap movers list."""
    if not tickers:
        return []

    mcap_movers = []

    # Parallel fetch: up to 6 threads for I/O-bound yfinance calls
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(_fetch_single_mcap, t): t for t in tickers}
        for future in as_completed(futures):
            ticker, mc = future.result()
            if mc is None:
                continue
            mover = movers_lookup.get(ticker)
            if not mover:
                continue
            chg_pct = mover["change_pct"] or 0
            mc_change = mc * (chg_pct / 100)
            mcap_movers.append({
                "ticker": ticker, "name": mover["name"],
                "price": mover["price"], "change_pct": chg_pct,
                "market_cap": round(mc),
                "market_cap_change": round(mc_change),
                "market_cap_fmt": _fmt_mcap(mc),
                "mcap_change_fmt": _fmt_mcap(abs(mc_change)),
                "positive": mover.get("positive", True),
            })

    mcap_movers.sort(key=lambda x: abs(x.get("market_cap_change", 0)), reverse=True)
    return mcap_movers


# ---------------------------------------------------------------------------
# Watchlist — prices + 30d sparkline history
# ---------------------------------------------------------------------------

@market_bp.route("/api/v1/market/watchlist")
def watchlist_data():
    raw_tickers = request.args.get("tickers", ",".join(DEFAULT_WATCHLIST))
    tickers = [t.strip().upper() for t in raw_tickers.split(",") if t.strip()]
    cache_key = "watchlist:" + ",".join(sorted(tickers))

    cached = _cache_get(cache_key)
    if cached:
        return jsonify(cached)

    try:
        raw = yf.download(
            tickers,
            period="1mo",
            auto_adjust=True,
            progress=False,
            threads=True,
        )

        result = []

        if raw.empty:
            return jsonify(result)

        try:
            closes  = raw["Close"]
            volumes = raw["Volume"]
        except KeyError:
            return jsonify([])

        # Handle single-ticker case where yfinance returns flat Series
        if not isinstance(closes, pd.DataFrame):
            closes  = pd.DataFrame({tickers[0]: closes})
            volumes = pd.DataFrame({tickers[0]: volumes})

        for ticker in tickers:
            try:
                col = ticker if (closes is not None and ticker in closes.columns) else None
                if col is None:
                    continue

                series = closes[col].dropna()
                if len(series) < 2:
                    continue

                price = float(series.iloc[-1])
                prev  = float(series.iloc[-2])
                chg   = price - prev
                pct   = chg / prev * 100 if prev else 0

                # Sparkline: last 30 trading-day closes
                sparkline = [
                    {"date": str(idx.date()), "close": _safe_float(v)}
                    for idx, v in series.tail(30).items()
                    if not pd.isna(v)
                ]

                # Week / Month performance
                week_ago  = float(series.iloc[-6])  if len(series) >= 6  else None
                month_ago = float(series.iloc[0])
                week_pct  = (price - week_ago)  / week_ago  * 100 if week_ago  else None
                month_pct = (price - month_ago) / month_ago * 100

                # Volume
                vol_str = "—"
                if volumes is not None and col in volumes.columns:
                    vols = volumes[col].dropna()
                    if not vols.empty:
                        vol_str = _format_volume(float(vols.iloc[-1]))

                # 52-week hi/lo from full series
                hi52 = _safe_float(series.max())
                lo52 = _safe_float(series.min())

                result.append({
                    "ticker":     ticker,
                    "name":       _ticker_name(ticker),
                    "price":      _safe_float(price),
                    "change":     _safe_float(chg),
                    "change_pct": _safe_float(pct),
                    "week_pct":   _safe_float(week_pct),
                    "month_pct":  _safe_float(month_pct),
                    "volume":     vol_str,
                    "hi_52w":     hi52,
                    "lo_52w":     lo52,
                    "sparkline":  sparkline,
                    "positive":   chg >= 0,
                })

            except Exception as ex:
                logger.warning("Watchlist ticker error", ticker=ticker, error=str(ex))
                continue

        _cache_set(cache_key, result, ttl=300)
        return jsonify(result)

    except Exception as e:
        logger.error("Watchlist data error", error=str(e), exc_info=True)
        return jsonify([])


# ---------------------------------------------------------------------------
# Headlines
# ---------------------------------------------------------------------------

@market_bp.route("/api/v1/market/headlines")
def market_headlines():
    raw_tickers = request.args.get("tickers", ",".join(DEFAULT_WATCHLIST))
    tickers = [t.strip().upper() for t in raw_tickers.split(",") if t.strip()]
    cache_key = "headlines:" + ",".join(sorted(tickers))

    cached = _cache_get(cache_key)
    if cached:
        return jsonify(cached)

    result = {}
    for ticker in tickers:
        try:
            yf_ticker = yf.Ticker(ticker)
            news_items = yf_ticker.news or []
            articles = []
            for item in news_items[:8]:
                ts = item.get("providerPublishTime", 0)
                articles.append({
                    "headline":  item.get("title", ""),
                    "source":    item.get("publisher", ""),
                    "url":       item.get("link", ""),
                    "timestamp": ts,
                    "time_ago":  _time_ago(ts),
                    "thumbnail": (item.get("thumbnail") or {}).get("resolutions", [{}])[0].get("url"),
                })
            result[ticker] = {
                "ticker": ticker,
                "name":   _ticker_name(ticker),
                "articles": articles,
            }
        except Exception as e:
            logger.warning("Headlines error", ticker=ticker, error=str(e))
            result[ticker] = {"ticker": ticker, "name": _ticker_name(ticker), "articles": []}

    _cache_set(cache_key, result, ttl=900)
    return jsonify(result)


# ---------------------------------------------------------------------------
# Market status
# ---------------------------------------------------------------------------

@market_bp.route("/api/v1/market/status")
def market_status():
    now_utc = datetime.now(timezone.utc)
    # NYSE hours: 9:30-16:00 ET = 14:30-21:00 UTC
    # Simple check (ignores holidays)
    weekday = now_utc.weekday()
    hour    = now_utc.hour
    minute  = now_utc.minute
    total_min = hour * 60 + minute
    is_open = (
        weekday < 5  # Mon-Fri
        and 870 <= total_min < 1260  # 14:30 - 21:00 UTC
    )
    return jsonify({
        "is_open": is_open,
        "status":  "Open" if is_open else "Closed",
        "time_utc": now_utc.strftime("%H:%M UTC"),
        "day": now_utc.strftime("%a %b %-d, %Y"),
    })


# ---------------------------------------------------------------------------
# Serve dashboard HTML
# ---------------------------------------------------------------------------

@market_bp.route("/dashboard")
def dashboard():
    import os
    static_dir = os.path.join(current_app.root_path, "static")
    return send_from_directory(static_dir, "dashboard.html")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _time_ago(ts: int) -> str:
    if not ts:
        return ""
    diff = int(time.time()) - ts
    if diff < 60:
        return "just now"
    if diff < 3600:
        m = diff // 60
        return f"{m}m ago"
    if diff < 86400:
        h = diff // 3600
        return f"{h}h ago"
    d = diff // 86400
    return f"{d}d ago"
