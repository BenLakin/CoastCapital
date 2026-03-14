"""
Feature engineering for stock price forecasting — v3.0.

Features include:
  - Technical indicators (price-based, volume-based, volatility)
  - Momentum and mean-reversion signals
  - Earnings quality & surprise metrics
  - News sentiment aggregations
  - Macro conditions (VIX regime, yield curve, market breadth)
  - Calendar effects (day-of-week, month, earnings proximity)
  - Cross-sectional rank features (vs. market)
  - Momentum quality & realized-vs-implied vol
  - Multi-horizon targets (1d, 5d)
"""
import pandas as pd
import numpy as np
from datetime import date, timedelta
from scipy.stats import rankdata
from sqlalchemy.orm import Session
from app.models.schema import (
    DimStock, FactStockPrice, FactTechnicalIndicator,
    FactStockNews, FactEarnings, FactMacroIndicator
)
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


def build_feature_matrix(
    ticker: str,
    db: Session,
    start_date: date,
    end_date: date,
    include_target: bool = True,
    horizons: list[int] | None = None,
) -> pd.DataFrame:
    """
    Build full feature matrix for model training/inference.

    Returns a DataFrame indexed by trade_date with:
      - All feature columns (X)
      - target_return_{h}d columns for each horizon (if include_target)
      - target_direction (1=up, -1=down) based on 1d target (if include_target)

    Parameters:
        horizons: list of forecast horizons in trading days (default: settings.forecast_horizons)
    """
    horizons = horizons or settings.forecast_horizons

    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        raise ValueError(f"Ticker {ticker} not found in dim_stock")

    # ---- Price features ----
    prices = (
        db.query(FactStockPrice)
        .filter(
            FactStockPrice.stock_id == stock.stock_id,
            FactStockPrice.trade_date >= start_date,
            FactStockPrice.trade_date <= end_date,
        )
        .order_by(FactStockPrice.trade_date)
        .all()
    )

    if not prices:
        return pd.DataFrame()

    price_df = pd.DataFrame([{
        "date": p.trade_date,
        "close": float(p.close_adj),
        "open": float(p.open_adj or p.close_adj),
        "high": float(p.high_adj or p.close_adj),
        "low": float(p.low_adj or p.close_adj),
        "volume": float(p.volume_adj or 0),
        "daily_return": float(p.daily_return or 0),
        "log_return": float(p.log_return or 0),
        "dollar_volume": float(p.dollar_volume or 0),
        "gap_pct": float(p.gap_pct or 0),
        "intraday_range_pct": float(p.intraday_range_pct or 0),
    } for p in prices]).set_index("date")

    # Lag returns (momentum features)
    for lag in [1, 2, 3, 5, 10, 20]:
        price_df[f"return_lag_{lag}d"] = price_df["daily_return"].shift(lag)

    # Cumulative returns over windows
    for window in [5, 10, 20, 60]:
        price_df[f"cum_return_{window}d"] = price_df["close"].pct_change(window)

    # --- Momentum quality: risk-adjusted momentum (Sharpe of trailing returns) ---
    rolling_mean_20 = price_df["daily_return"].rolling(20).mean()
    rolling_std_20 = price_df["daily_return"].rolling(20).std()
    price_df["momentum_quality"] = (rolling_mean_20 / rolling_std_20.replace(0, np.nan)).fillna(0)

    # --- Realized vs implied vol ratio ---
    price_df["realized_vol_20d"] = price_df["daily_return"].rolling(20).std() * np.sqrt(252)

    # ---- Technical indicator features ----
    techs = (
        db.query(FactTechnicalIndicator)
        .filter(
            FactTechnicalIndicator.stock_id == stock.stock_id,
            FactTechnicalIndicator.trade_date >= start_date,
            FactTechnicalIndicator.trade_date <= end_date,
        )
        .order_by(FactTechnicalIndicator.trade_date)
        .all()
    )

    tech_df = pd.DataFrame([{
        "date": t.trade_date,
        "rsi_14": t.rsi_14,
        "macd_histogram": t.macd_histogram,
        "bb_pct_b": t.bb_pct_b,
        "bb_bandwidth": t.bb_bandwidth,
        "atr_14": t.atr_14,
        "volatility_20d": t.volatility_20d,
        "volatility_5d": t.volatility_5d,
        "volume_ratio": t.volume_ratio,
        "obv": t.obv,
        "mfi_14": t.mfi_14,
        "cmf_20": t.cmf_20,
        "stoch_k": t.stoch_k,
        "stoch_d": t.stoch_d,
        "williams_r": t.williams_r,
        "roc_10": t.roc_10,
        "roc_20": t.roc_20,
        "price_vs_sma50": t.price_vs_sma50,
        "price_vs_sma200": t.price_vs_sma200,
        "price_vs_52w_high": t.price_vs_52w_high,
        "price_vs_52w_low": t.price_vs_52w_low,
        "golden_cross": int(t.golden_cross) if t.golden_cross is not None else 0,
        "macd_bullish": int(t.macd_bullish) if t.macd_bullish is not None else 0,
        "rsi_oversold": int(t.rsi_oversold) if t.rsi_oversold is not None else 0,
        "rsi_overbought": int(t.rsi_overbought) if t.rsi_overbought is not None else 0,
    } for t in techs]).set_index("date") if techs else pd.DataFrame()

    # ---- News sentiment features ----
    news_raw = (
        db.query(FactStockNews)
        .filter(
            FactStockNews.stock_id == stock.stock_id,
            FactStockNews.published_at >= pd.Timestamp(start_date),
        )
        .all()
    )

    if news_raw:
        news_df = pd.DataFrame([{
            "date": n.published_at.date(),
            "sentiment": float(n.sentiment_score or 0),
            "relevance": float(n.relevance_score or 0.5),
        } for n in news_raw])

        def weighted_sentiment(g):
            w = g["relevance"]
            return (g["sentiment"] * w).sum() / w.sum() if w.sum() > 0 else 0

        news_agg = news_df.groupby("date").apply(weighted_sentiment).rename("sentiment_score_wavg")
        news_count = news_df.groupby("date").size().rename("news_count")
        news_features = pd.concat([news_agg, news_count], axis=1)

        news_features["sentiment_3d_avg"] = news_features["sentiment_score_wavg"].rolling(3).mean()
        news_features["sentiment_5d_avg"] = news_features["sentiment_score_wavg"].rolling(5).mean()
    else:
        news_features = pd.DataFrame()

    # ---- Earnings proximity features ----
    earnings_raw = (
        db.query(FactEarnings)
        .filter(FactEarnings.stock_id == stock.stock_id)
        .order_by(FactEarnings.report_date)
        .all()
    )

    if earnings_raw:
        report_dates = [e.report_date for e in earnings_raw if e.report_date]
        report_dates.sort()

        def days_to_next_earnings(d):
            future = [r for r in report_dates if r > d]
            return (future[0] - d).days if future else 999

        def days_since_last_earnings(d):
            past = [r for r in report_dates if r <= d]
            return (d - past[-1]).days if past else 999

        price_df["days_to_next_earnings"] = price_df.index.map(days_to_next_earnings)
        price_df["days_since_last_earnings"] = price_df.index.map(days_since_last_earnings)
        price_df["earnings_week"] = (price_df["days_to_next_earnings"] <= 5).astype(int)

        def recent_eps_surprise(d):
            past = [(e.report_date, e.eps_surprise_pct) for e in earnings_raw
                   if e.report_date and e.report_date <= d and e.eps_surprise_pct is not None]
            return past[-1][1] if past else 0

        price_df["recent_eps_surprise"] = price_df.index.map(recent_eps_surprise)
    else:
        price_df["days_to_next_earnings"] = 999
        price_df["days_since_last_earnings"] = 999
        price_df["earnings_week"] = 0
        price_df["recent_eps_surprise"] = 0

    # ---- Macro features ----
    macros = (
        db.query(FactMacroIndicator)
        .filter(
            FactMacroIndicator.indicator_date >= start_date,
            FactMacroIndicator.indicator_date <= end_date,
        )
        .order_by(FactMacroIndicator.indicator_date)
        .all()
    )

    if macros:
        macro_df = pd.DataFrame([{
            "date": m.indicator_date,
            "vix": m.vix,
            "yield_curve_2_10": m.yield_curve_2_10,
            "treasury_10y": m.treasury_10y,
            "sp500_return_1d": m.sp500_return_1d,
            "spy_return_1d": (m.spy_close or 0),
        } for m in macros]).set_index("date")

        macro_df["vix_regime"] = pd.cut(
            macro_df["vix"].fillna(20),
            bins=[0, 15, 20, 25, 35, 100],
            labels=[0, 1, 2, 3, 4],
        ).astype(float)
        macro_df["yield_curve_inverted"] = (macro_df["yield_curve_2_10"] < 0).astype(int)
        macro_df["vix_5d_avg"] = macro_df["vix"].rolling(5).mean()
        macro_df["vix_change_1d"] = macro_df["vix"].pct_change()
    else:
        macro_df = pd.DataFrame()

    # ---- Calendar features ----
    price_df["day_of_week"] = pd.to_datetime(price_df.index).dayofweek
    price_df["month"] = pd.to_datetime(price_df.index).month
    price_df["quarter"] = pd.to_datetime(price_df.index).quarter
    price_df["is_month_end"] = pd.to_datetime(price_df.index).is_month_end.astype(int)
    price_df["is_quarter_end"] = pd.to_datetime(price_df.index).is_quarter_end.astype(int)
    price_df["is_monday"] = (price_df["day_of_week"] == 0).astype(int)
    price_df["is_friday"] = (price_df["day_of_week"] == 4).astype(int)

    # ---- Cross-sectional rank features ----
    _add_cross_sectional_features(ticker, price_df, db, start_date, end_date)

    # ---- Merge all feature sets ----
    df = price_df.copy()

    if not tech_df.empty:
        df = df.join(tech_df, how="left")

    if not news_features.empty:
        df = df.join(news_features, how="left")

    if not macro_df.empty:
        df = df.join(macro_df[["vix", "vix_regime", "vix_5d_avg", "vix_change_1d",
                                "yield_curve_2_10", "yield_curve_inverted",
                                "treasury_10y"]], how="left")

    # Realized-vs-implied vol (needs volatility_20d from technicals)
    if "volatility_20d" in df.columns and "realized_vol_20d" in df.columns:
        implied = df["volatility_20d"].replace(0, np.nan)
        df["realized_vs_implied_vol"] = (df["realized_vol_20d"] / implied).fillna(1.0)
    else:
        df["realized_vs_implied_vol"] = 1.0

    # ---- Multi-horizon target variables ----
    if include_target:
        for h in horizons:
            df[f"target_return_{h}d"] = df["close"].pct_change(h).shift(-h)

        # Backward compat: primary target for direction
        primary = f"target_return_{horizons[0]}d"
        df["target_direction"] = np.sign(df[primary])

        # Drop rows with NaN targets (need all horizons)
        target_cols = [f"target_return_{h}d" for h in horizons]
        df = df.dropna(subset=target_cols)

    # Fill NaN features with 0
    feature_cols = get_feature_names(df)
    df[feature_cols] = df[feature_cols].fillna(0)

    logger.info("Feature matrix built", ticker=ticker, rows=len(df),
                cols=len(df.columns), horizons=horizons)
    return df


def _add_cross_sectional_features(
    ticker: str,
    price_df: pd.DataFrame,
    db: Session,
    start_date: date,
    end_date: date,
) -> None:
    """
    Add cross-sectional percentile rank features vs all tracked stocks.
    Ranks momentum and volatility vs the market on each date.
    Modifies price_df in-place.
    """
    active_stocks = db.query(DimStock).filter(DimStock.is_active == True).all()
    if len(active_stocks) < 3:
        price_df["rank_momentum_20d"] = 0.5
        price_df["rank_volatility_20d"] = 0.5
        return

    # Collect 20d momentum and vol for all stocks
    all_momentum = {}
    all_volatility = {}
    for s in active_stocks:
        rows = (
            db.query(FactStockPrice.trade_date, FactStockPrice.close_adj, FactStockPrice.daily_return)
            .filter(
                FactStockPrice.stock_id == s.stock_id,
                FactStockPrice.trade_date >= start_date,
                FactStockPrice.trade_date <= end_date,
            )
            .order_by(FactStockPrice.trade_date)
            .all()
        )
        if len(rows) < 21:
            continue
        sdf = pd.DataFrame(rows, columns=["date", "close", "daily_return"]).set_index("date")
        sdf["close"] = sdf["close"].astype(float)
        sdf["daily_return"] = sdf["daily_return"].astype(float)
        all_momentum[s.ticker] = sdf["close"].pct_change(20)
        all_volatility[s.ticker] = sdf["daily_return"].rolling(20).std() * np.sqrt(252)

    if ticker not in all_momentum:
        price_df["rank_momentum_20d"] = 0.5
        price_df["rank_volatility_20d"] = 0.5
        return

    mom_panel = pd.DataFrame(all_momentum)
    vol_panel = pd.DataFrame(all_volatility)

    # Percentile rank per date row
    def pct_rank_row(row):
        valid = row.dropna()
        if len(valid) < 2:
            return row * 0 + 0.5
        ranks = rankdata(valid, method="average") / len(valid)
        return pd.Series(ranks, index=valid.index).reindex(row.index)

    mom_ranks = mom_panel.apply(pct_rank_row, axis=1)
    vol_ranks = vol_panel.apply(pct_rank_row, axis=1)

    price_df["rank_momentum_20d"] = mom_ranks[ticker].reindex(price_df.index).fillna(0.5)
    price_df["rank_volatility_20d"] = vol_ranks[ticker].reindex(price_df.index).fillna(0.5)


def get_feature_names(df: pd.DataFrame) -> list[str]:
    """Return list of feature column names (excludes target and raw OHLC columns)."""
    exclude = {"close", "open", "high", "low", "target_direction"}
    return [c for c in df.columns if c not in exclude and not c.startswith("target_return_")]
