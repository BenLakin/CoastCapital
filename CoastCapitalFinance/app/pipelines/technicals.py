"""
Technical indicator computation pipeline.
Computes 25+ indicators from adjusted price history using the `ta` library.
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from sqlalchemy.orm import Session
import ta
from app.models.schema import DimStock, FactStockPrice, FactTechnicalIndicator
from app.models.database import get_db
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def compute_and_store_technicals(
    ticker: str,
    start_date: date,
    end_date: date,
    db: Session,
    lookback_buffer: int = 250,  # extra days before start for indicator warm-up
) -> int:
    """
    Compute all technical indicators for a ticker over the given date range.
    Uses a lookback buffer so indicators are valid from start_date.
    """
    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        return 0

    # Fetch prices with buffer
    buffer_start = start_date - timedelta(days=lookback_buffer)
    prices = (
        db.query(FactStockPrice)
        .filter(
            FactStockPrice.stock_id == stock.stock_id,
            FactStockPrice.trade_date >= buffer_start,
            FactStockPrice.trade_date <= end_date,
        )
        .order_by(FactStockPrice.trade_date)
        .all()
    )

    if len(prices) < 30:
        logger.warning("Insufficient price data for technicals", ticker=ticker, rows=len(prices))
        return 0

    # Build DataFrame
    df = pd.DataFrame([{
        "date": p.trade_date,
        "open": float(p.open_adj or 0),
        "high": float(p.high_adj or 0),
        "low": float(p.low_adj or 0),
        "close": float(p.close_adj),
        "volume": float(p.volume_adj or 0),
    } for p in prices])
    df = df.set_index("date").sort_index()
    df = df[df["close"] > 0]  # remove zero-price rows

    if len(df) < 30:
        return 0

    # --- Compute all indicators ---
    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # Trend
    df["sma_5"] = ta.trend.sma_indicator(close, window=5)
    df["sma_10"] = ta.trend.sma_indicator(close, window=10)
    df["sma_20"] = ta.trend.sma_indicator(close, window=20)
    df["sma_50"] = ta.trend.sma_indicator(close, window=50)
    df["sma_200"] = ta.trend.sma_indicator(close, window=200)
    df["ema_9"] = ta.trend.ema_indicator(close, window=9)
    df["ema_12"] = ta.trend.ema_indicator(close, window=12)
    df["ema_26"] = ta.trend.ema_indicator(close, window=26)

    # Momentum
    df["rsi_14"] = ta.momentum.rsi(close, window=14)
    macd_indicator = ta.trend.MACD(close)
    df["macd"] = macd_indicator.macd()
    df["macd_signal"] = macd_indicator.macd_signal()
    df["macd_histogram"] = macd_indicator.macd_diff()

    stoch = ta.momentum.StochasticOscillator(high, low, close)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()
    df["williams_r"] = ta.momentum.williams_r(high, low, close, lbp=14)
    df["roc_10"] = ta.momentum.roc(close, window=10)
    df["roc_20"] = ta.momentum.roc(close, window=20)

    # Volatility
    bb = ta.volatility.BollingerBands(close, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_middle"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_pct_b"] = bb.bollinger_pband()
    df["bb_bandwidth"] = bb.bollinger_wband()
    df["atr_14"] = ta.volatility.average_true_range(high, low, close, window=14)

    # Realized volatility (annualized)
    log_returns = np.log(close / close.shift(1))
    df["volatility_20d"] = log_returns.rolling(20).std() * np.sqrt(252)
    df["volatility_5d"] = log_returns.rolling(5).std() * np.sqrt(252)

    # Volume
    df["obv"] = ta.volume.on_balance_volume(close, volume)
    df["volume_sma_20"] = volume.rolling(20).mean()
    df["volume_ratio"] = volume / df["volume_sma_20"]
    df["mfi_14"] = ta.volume.money_flow_index(high, low, close, volume, window=14)
    df["cmf_20"] = ta.volume.chaikin_money_flow(high, low, close, volume, window=20)

    # Price position
    df["52w_high"] = close.rolling(252).max()
    df["52w_low"] = close.rolling(252).min()
    df["price_vs_sma50"] = (close - df["sma_50"]) / df["sma_50"] * 100
    df["price_vs_sma200"] = (close - df["sma_200"]) / df["sma_200"] * 100
    df["price_vs_52w_high"] = (close - df["52w_high"]) / df["52w_high"] * 100
    df["price_vs_52w_low"] = (close - df["52w_low"]) / df["52w_low"] * 100

    # Cross signals
    df["golden_cross"] = df["sma_50"] > df["sma_200"]
    df["macd_bullish"] = df["macd"] > df["macd_signal"]
    df["rsi_oversold"] = df["rsi_14"] < 30
    df["rsi_overbought"] = df["rsi_14"] > 70

    # Only write rows within requested date range
    df_write = df[df.index >= start_date]
    count = 0

    for trade_date, row in df_write.iterrows():
        def safe(val):
            if pd.isna(val):
                return None
            return float(val)

        existing = db.query(FactTechnicalIndicator).filter(
            FactTechnicalIndicator.stock_id == stock.stock_id,
            FactTechnicalIndicator.trade_date == trade_date,
        ).first()

        indicator_data = dict(
            stock_id=stock.stock_id,
            trade_date=trade_date,
            sma_5=safe(row.get("sma_5")),
            sma_10=safe(row.get("sma_10")),
            sma_20=safe(row.get("sma_20")),
            sma_50=safe(row.get("sma_50")),
            sma_200=safe(row.get("sma_200")),
            ema_9=safe(row.get("ema_9")),
            ema_12=safe(row.get("ema_12")),
            ema_26=safe(row.get("ema_26")),
            rsi_14=safe(row.get("rsi_14")),
            macd=safe(row.get("macd")),
            macd_signal=safe(row.get("macd_signal")),
            macd_histogram=safe(row.get("macd_histogram")),
            stoch_k=safe(row.get("stoch_k")),
            stoch_d=safe(row.get("stoch_d")),
            williams_r=safe(row.get("williams_r")),
            roc_10=safe(row.get("roc_10")),
            roc_20=safe(row.get("roc_20")),
            bb_upper=safe(row.get("bb_upper")),
            bb_middle=safe(row.get("bb_middle")),
            bb_lower=safe(row.get("bb_lower")),
            bb_pct_b=safe(row.get("bb_pct_b")),
            bb_bandwidth=safe(row.get("bb_bandwidth")),
            atr_14=safe(row.get("atr_14")),
            volatility_20d=safe(row.get("volatility_20d")),
            volatility_5d=safe(row.get("volatility_5d")),
            obv=safe(row.get("obv")),
            volume_sma_20=safe(row.get("volume_sma_20")),
            volume_ratio=safe(row.get("volume_ratio")),
            mfi_14=safe(row.get("mfi_14")),
            cmf_20=safe(row.get("cmf_20")),
            price_vs_sma50=safe(row.get("price_vs_sma50")),
            price_vs_sma200=safe(row.get("price_vs_sma200")),
            price_vs_52w_high=safe(row.get("price_vs_52w_high")),
            price_vs_52w_low=safe(row.get("price_vs_52w_low")),
            golden_cross=bool(row.get("golden_cross")) if pd.notna(row.get("golden_cross")) else None,
            macd_bullish=bool(row.get("macd_bullish")) if pd.notna(row.get("macd_bullish")) else None,
            rsi_oversold=bool(row.get("rsi_oversold")) if pd.notna(row.get("rsi_oversold")) else None,
            rsi_overbought=bool(row.get("rsi_overbought")) if pd.notna(row.get("rsi_overbought")) else None,
        )

        if existing:
            for k, v in indicator_data.items():
                if k not in ("stock_id", "trade_date"):
                    setattr(existing, k, v)
        else:
            db.add(FactTechnicalIndicator(**indicator_data))
            count += 1

    db.flush()
    logger.info("Technicals computed", ticker=ticker, rows=count)
    return count
