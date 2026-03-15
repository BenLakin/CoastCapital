"""
finance_silver schema - Star schema for stock market data.

Dimensions:
  - dim_stock        : Stock metadata (ticker, name, sector, industry, exchange)
  - dim_date         : Date dimension with calendar attributes

Facts:
  - fact_stock_price         : Daily OHLCV + adjusted prices
  - fact_technical_indicators: RSI, MACD, Bollinger Bands, etc.
  - fact_stock_news          : News articles with LLM summaries + sentiment
  - fact_earnings            : Quarterly earnings with LLM summaries
  - fact_macro_indicators    : Macro data (VIX, treasury yields, market breadth)
  - fact_forecasts           : Model price forecasts
  - fact_backtest_results    : Model backtest performance by run
  - fact_stock_splits        : Split history for audit trail
"""
from sqlalchemy import (
    Column, Integer, BigInteger, String, Float, Boolean, Date, DateTime,
    Text, Enum, ForeignKey, Index, UniqueConstraint, SmallInteger,
    Numeric, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
from app.models.database import Base


# ---------------------------------------------------------------------------
# DIMENSIONS
# ---------------------------------------------------------------------------

class DimStock(Base):
    __tablename__ = "dim_stock"
    __table_args__ = (
        {"schema": None},  # uses default DB schema (finance_silver)
    )

    stock_id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(20), nullable=False, unique=True, index=True)
    company_name = Column(String(255), nullable=False)
    exchange = Column(String(50))
    sector = Column(String(100))
    industry = Column(String(200))
    country = Column(String(50), default="USA")
    currency = Column(String(10), default="USD")
    market_cap_category = Column(Enum("Nano", "Micro", "Small", "Mid", "Large", "Mega"), nullable=True)
    stock_tier = Column(
        Enum("watchlist", "universe", name="stock_tier"),
        nullable=False, default="universe", index=True,
    )
    cik = Column(String(20), nullable=True)  # SEC EDGAR Central Index Key
    is_active = Column(Boolean, default=True, nullable=False)
    is_etf = Column(Boolean, default=False, nullable=False)
    ipo_date = Column(Date, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    prices = relationship("FactStockPrice", back_populates="stock", lazy="dynamic")
    technicals = relationship("FactTechnicalIndicator", back_populates="stock", lazy="dynamic")
    news = relationship("FactStockNews", back_populates="stock", lazy="dynamic")
    earnings = relationship("FactEarnings", back_populates="stock", lazy="dynamic")
    forecasts = relationship("FactForecast", back_populates="stock", lazy="dynamic")
    splits = relationship("FactStockSplit", back_populates="stock", lazy="dynamic")

    def __repr__(self):
        return f"<DimStock {self.ticker}>"


class DimDate(Base):
    __tablename__ = "dim_date"

    date_id = Column(Integer, primary_key=True)  # YYYYMMDD format
    date = Column(Date, nullable=False, unique=True, index=True)
    year = Column(SmallInteger, nullable=False)
    quarter = Column(SmallInteger, nullable=False)
    month = Column(SmallInteger, nullable=False)
    month_name = Column(String(10), nullable=False)
    week_of_year = Column(SmallInteger, nullable=False)
    day_of_month = Column(SmallInteger, nullable=False)
    day_of_week = Column(SmallInteger, nullable=False)  # 0=Mon, 6=Sun
    day_name = Column(String(10), nullable=False)
    is_weekend = Column(Boolean, nullable=False)
    is_trading_day = Column(Boolean, default=True, nullable=False)
    is_quarter_end = Column(Boolean, default=False, nullable=False)
    is_year_end = Column(Boolean, default=False, nullable=False)
    fiscal_quarter = Column(SmallInteger, nullable=True)


# ---------------------------------------------------------------------------
# FACTS
# ---------------------------------------------------------------------------

class FactStockPrice(Base):
    __tablename__ = "fact_stock_price"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_stock_date"),
        Index("ix_fact_stock_price_date", "trade_date"),
        Index("ix_fact_stock_price_stock_date", "stock_id", "trade_date"),
    )

    price_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("dim_stock.stock_id"), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)

    # OHLCV (raw, unadjusted)
    open_raw = Column(Numeric(18, 6))
    high_raw = Column(Numeric(18, 6))
    low_raw = Column(Numeric(18, 6))
    close_raw = Column(Numeric(18, 6))
    volume_raw = Column(BigInteger)

    # Adjusted (split + dividend adjusted — apples-to-apples)
    open_adj = Column(Numeric(18, 6))
    high_adj = Column(Numeric(18, 6))
    low_adj = Column(Numeric(18, 6))
    close_adj = Column(Numeric(18, 6), nullable=False)
    volume_adj = Column(BigInteger)

    # Derived daily metrics
    daily_return = Column(Float)            # (close_adj - prev_close_adj) / prev_close_adj
    log_return = Column(Float)             # log(close_adj / prev_close_adj)
    dollar_volume = Column(Numeric(22, 2)) # close_adj * volume_adj
    vwap = Column(Numeric(18, 6))          # Volume-weighted average price
    intraday_range_pct = Column(Float)     # (high-low)/open * 100
    gap_pct = Column(Float)               # (open - prev_close) / prev_close * 100

    # Market data
    market_cap = Column(Numeric(22, 2))
    shares_outstanding = Column(BigInteger)
    split_coefficient = Column(Float, default=1.0)  # cumulative split factor

    # Data quality
    data_source = Column(String(50), default="yfinance")
    is_restated = Column(Boolean, default=False)  # True if recomputed after split
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)

    stock = relationship("DimStock", back_populates="prices")

    def __repr__(self):
        return f"<FactStockPrice {self.stock_id} {self.trade_date}>"


class FactTechnicalIndicator(Base):
    __tablename__ = "fact_technical_indicator"
    __table_args__ = (
        UniqueConstraint("stock_id", "trade_date", name="uq_tech_stock_date"),
        Index("ix_fact_tech_date", "trade_date"),
    )

    indicator_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("dim_stock.stock_id"), nullable=False)
    trade_date = Column(Date, nullable=False, index=True)

    # Trend indicators
    sma_5 = Column(Float)
    sma_10 = Column(Float)
    sma_20 = Column(Float)
    sma_50 = Column(Float)
    sma_200 = Column(Float)
    ema_9 = Column(Float)
    ema_12 = Column(Float)
    ema_26 = Column(Float)

    # Momentum
    rsi_14 = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    stoch_k = Column(Float)
    stoch_d = Column(Float)
    williams_r = Column(Float)
    roc_10 = Column(Float)   # Rate of change 10d
    roc_20 = Column(Float)

    # Volatility
    bb_upper = Column(Float)   # Bollinger Band upper
    bb_middle = Column(Float)  # Bollinger Band middle
    bb_lower = Column(Float)   # Bollinger Band lower
    bb_pct_b = Column(Float)   # %B position within bands
    bb_bandwidth = Column(Float)
    atr_14 = Column(Float)     # Average True Range
    volatility_20d = Column(Float)  # 20d realized vol (annualized)
    volatility_5d = Column(Float)

    # Volume indicators
    obv = Column(Float)           # On-Balance Volume
    volume_sma_20 = Column(Float)
    volume_ratio = Column(Float)  # volume / volume_sma_20
    mfi_14 = Column(Float)        # Money Flow Index
    cmf_20 = Column(Float)        # Chaikin Money Flow

    # Price position
    price_vs_sma50 = Column(Float)   # (price - sma50) / sma50 * 100
    price_vs_sma200 = Column(Float)
    price_vs_52w_high = Column(Float)
    price_vs_52w_low = Column(Float)
    distance_to_support = Column(Float)
    distance_to_resistance = Column(Float)

    # Cross signals (boolean-like: 1, 0, -1)
    golden_cross = Column(Boolean)   # SMA50 > SMA200
    macd_bullish = Column(Boolean)   # MACD > Signal
    rsi_oversold = Column(Boolean)   # RSI < 30
    rsi_overbought = Column(Boolean) # RSI > 70

    created_at = Column(DateTime, default=func.now(), nullable=False)

    stock = relationship("DimStock", back_populates="technicals")


class FactStockNews(Base):
    __tablename__ = "fact_stock_news"
    __table_args__ = (
        Index("ix_news_stock_date", "stock_id", "published_at"),
        Index("ix_news_published", "published_at"),
    )

    news_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("dim_stock.stock_id"), nullable=False)
    ticker = Column(String(20), nullable=False)

    # Article metadata
    headline = Column(String(1000), nullable=False)
    source = Column(String(200))
    url = Column(String(2000))
    published_at = Column(DateTime, nullable=False, index=True)
    author = Column(String(200))

    # Content
    full_text = Column(Text)
    llm_summary = Column(Text)           # Claude summary of the article
    llm_key_points = Column(JSON)        # List of key bullet points
    llm_catalysts = Column(Text)         # Price catalysts identified
    llm_risks = Column(Text)             # Risks identified

    # Sentiment
    sentiment_score = Column(Float)      # -1.0 (negative) to 1.0 (positive)
    sentiment_label = Column(Enum("very_negative", "negative", "neutral", "positive", "very_positive"))
    relevance_score = Column(Float)      # 0-1, how relevant to stock price movement

    # LLM metadata
    llm_model = Column(String(100))
    llm_processed_at = Column(DateTime)

    data_source = Column(String(50))
    created_at = Column(DateTime, default=func.now(), nullable=False)

    stock = relationship("DimStock", back_populates="news")


class FactEarnings(Base):
    __tablename__ = "fact_earnings"
    __table_args__ = (
        UniqueConstraint("stock_id", "fiscal_quarter", "fiscal_year", name="uq_earnings_period"),
        Index("ix_earnings_stock", "stock_id"),
    )

    earnings_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("dim_stock.stock_id"), nullable=False)
    ticker = Column(String(20), nullable=False)

    # Period
    fiscal_year = Column(SmallInteger, nullable=False)
    fiscal_quarter = Column(SmallInteger, nullable=False)  # 1-4
    report_date = Column(Date)
    period_ending = Column(Date)

    # EPS
    eps_actual = Column(Float)
    eps_estimate = Column(Float)
    eps_surprise = Column(Float)     # actual - estimate
    eps_surprise_pct = Column(Float) # surprise / |estimate| * 100

    # Revenue
    revenue_actual = Column(Numeric(22, 2))
    revenue_estimate = Column(Numeric(22, 2))
    revenue_surprise_pct = Column(Float)

    # Guidance
    eps_guidance_low = Column(Float)
    eps_guidance_high = Column(Float)
    revenue_guidance_low = Column(Numeric(22, 2))
    revenue_guidance_high = Column(Numeric(22, 2))

    # Key financial metrics
    gross_margin = Column(Float)
    operating_margin = Column(Float)
    net_margin = Column(Float)
    roe = Column(Float)
    debt_to_equity = Column(Float)
    free_cash_flow = Column(Numeric(22, 2))
    pe_ratio = Column(Float)
    peg_ratio = Column(Float)
    price_to_book = Column(Float)
    price_to_sales = Column(Float)
    enterprise_value = Column(Numeric(22, 2))
    ev_to_ebitda = Column(Float)

    # LLM analysis
    llm_summary = Column(Text)
    llm_bull_case = Column(Text)
    llm_bear_case = Column(Text)
    llm_key_metrics = Column(JSON)
    llm_model = Column(String(100))
    llm_processed_at = Column(DateTime)

    # Market reaction
    price_reaction_1d = Column(Float)  # % change day of/after earnings
    price_reaction_5d = Column(Float)  # % change 5d after

    data_source = Column(String(50))
    created_at = Column(DateTime, default=func.now(), nullable=False)

    stock = relationship("DimStock", back_populates="earnings")


class FactMacroIndicator(Base):
    __tablename__ = "fact_macro_indicator"
    __table_args__ = (
        UniqueConstraint("indicator_date", name="uq_macro_date"),
        Index("ix_macro_date", "indicator_date"),
    )

    macro_id = Column(BigInteger, primary_key=True, autoincrement=True)
    indicator_date = Column(Date, nullable=False, unique=True)

    # Volatility / Fear
    vix = Column(Float)            # CBOE Volatility Index
    vix_term_structure = Column(Float)  # VIX3M / VIX ratio

    # Interest Rates / Bonds
    treasury_2y = Column(Float)
    treasury_5y = Column(Float)
    treasury_10y = Column(Float)
    treasury_30y = Column(Float)
    yield_curve_2_10 = Column(Float)  # 10Y - 2Y spread (recession indicator)
    yield_curve_3m_10y = Column(Float)
    fed_funds_rate = Column(Float)
    breakeven_inflation_10y = Column(Float)  # TIPS spread

    # Market Breadth
    sp500_advance_decline = Column(Float)  # A/D line
    sp500_new_highs = Column(Integer)
    sp500_new_lows = Column(Integer)
    pct_above_sma200 = Column(Float)      # % of S&P500 stocks above 200d SMA
    pct_above_sma50 = Column(Float)

    # Indices
    spy_close = Column(Float)
    qqq_close = Column(Float)
    iwm_close = Column(Float)    # Russell 2000 (small cap)
    dia_close = Column(Float)    # Dow Jones
    sp500_return_1d = Column(Float)

    # Commodities
    gold_close = Column(Float)
    oil_wti = Column(Float)
    dollar_index = Column(Float)  # DXY

    # Credit
    high_yield_spread = Column(Float)  # HYG spread
    investment_grade_spread = Column(Float)

    # Sentiment
    put_call_ratio = Column(Float)
    aaii_bull_pct = Column(Float)   # American Association of Individual Investors survey
    fear_greed_index = Column(Float)  # CNN Fear & Greed

    data_source = Column(String(100))
    created_at = Column(DateTime, default=func.now(), nullable=False)


class FactForecast(Base):
    __tablename__ = "fact_forecast"
    __table_args__ = (
        Index("ix_forecast_stock_date", "stock_id", "forecast_date"),
        Index("ix_forecast_target_date", "target_date"),
    )

    forecast_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("dim_stock.stock_id"), nullable=False)
    ticker = Column(String(20), nullable=False)

    # Forecast metadata
    forecast_date = Column(Date, nullable=False)   # Date forecast was made
    target_date = Column(Date, nullable=False)      # Date being predicted
    forecast_horizon = Column(Integer, default=1)   # 1 = 1-day, 5 = 1-week
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50))

    # Predictions
    predicted_open = Column(Float)
    predicted_high = Column(Float)
    predicted_low = Column(Float)
    predicted_close = Column(Float)
    predicted_return = Column(Float)          # % expected return
    predicted_direction = Column(Integer)     # 1=up, -1=down, 0=flat
    confidence_score = Column(Float)          # 0-1 model confidence
    opportunity_score = Column(Float)         # composite score for ranking

    # Prediction intervals
    lower_bound_95 = Column(Float)
    upper_bound_95 = Column(Float)
    lower_bound_80 = Column(Float)
    upper_bound_80 = Column(Float)

    # Feature importance snapshot
    top_features = Column(JSON)

    # Actual outcome (filled after target_date passes)
    actual_open = Column(Float)
    actual_close = Column(Float)
    actual_return = Column(Float)
    actual_direction = Column(Integer)
    was_correct = Column(Boolean)       # Directional accuracy

    # LLM narrative
    llm_rationale = Column(Text)
    llm_model = Column(String(100))

    created_at = Column(DateTime, default=func.now(), nullable=False)

    stock = relationship("DimStock", back_populates="forecasts")


class FactBacktestResult(Base):
    __tablename__ = "fact_backtest_result"
    __table_args__ = (
        Index("ix_backtest_model", "model_name", "run_date"),
    )

    backtest_id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50))
    tickers_tested = Column(JSON)   # list of tickers in this backtest

    # Backtest configuration
    train_start = Column(Date)
    train_end = Column(Date)
    test_start = Column(Date)
    test_end = Column(Date)
    n_folds = Column(Integer)       # Walk-forward validation folds

    # Performance metrics - Directional
    directional_accuracy = Column(Float)  # % correct up/down calls
    precision_long = Column(Float)
    recall_long = Column(Float)
    f1_long = Column(Float)

    # Performance metrics - Returns
    strategy_return_total = Column(Float)
    strategy_return_annualized = Column(Float)
    benchmark_return_total = Column(Float)  # Buy-and-hold SPY
    alpha = Column(Float)
    beta = Column(Float)
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    max_drawdown = Column(Float)
    calmar_ratio = Column(Float)
    win_rate = Column(Float)
    avg_win = Column(Float)
    avg_loss = Column(Float)
    profit_factor = Column(Float)  # gross_profit / gross_loss

    # Error metrics
    rmse = Column(Float)
    mae = Column(Float)
    mape = Column(Float)

    # Per-ticker breakdown
    per_ticker_metrics = Column(JSON)

    notes = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)


class FactModelRegistry(Base):
    """Model registry for champion/challenger model management.

    Lifecycle: candidate → champion → archived
    One champion per ticker at a time; promotion archives the old champion.
    """
    __tablename__ = "fact_model_registry"
    __table_args__ = (
        Index("ix_model_registry_ticker", "ticker"),
        Index("ix_model_registry_status", "status"),
        Index("ix_model_registry_ticker_status", "ticker", "status"),
    )

    model_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("dim_stock.stock_id"), nullable=True)
    ticker = Column(String(20), nullable=False, index=True)
    model_version = Column(String(50), default="v3.0")
    sequence_num = Column(Integer, nullable=False)  # auto-increment per ticker

    # Status lifecycle
    status = Column(
        Enum("candidate", "champion", "archived", name="model_status"),
        nullable=False,
        default="candidate",
    )

    # Training metadata
    trained_at = Column(DateTime, default=func.now(), nullable=False)
    training_duration_sec = Column(Float)
    train_rows = Column(Integer)
    n_features = Column(Integer)
    horizons = Column(JSON)  # e.g. [1, 5]

    # Hyperparameter optimization
    hpo_method = Column(String(20), default="none")  # "none", "bayesian", "grid"
    hyperparams = Column(JSON)  # full param dicts for all 4 base models

    # Training metrics
    train_metrics = Column(JSON)  # per-horizon OOF RMSE, dir accuracy, meta weights

    # Backtest linkage
    backtest_id = Column(BigInteger, ForeignKey("fact_backtest_result.backtest_id"), nullable=True)
    backtest_metrics = Column(JSON)  # snapshot: {directional_accuracy, sharpe, alpha, max_drawdown}

    # Feature importance
    feature_importance = Column(JSON)  # top 20 features per horizon

    # File path
    model_path = Column(String(500))  # relative path in models_cache/

    # Promotion tracking
    promoted_at = Column(DateTime, nullable=True)
    promoted_from_id = Column(BigInteger, nullable=True)  # model_id of predecessor champion

    notes = Column(Text)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)


class FactStockSplit(Base):
    """Audit trail of stock splits for history restatement tracking."""
    __tablename__ = "fact_stock_split"
    __table_args__ = (
        Index("ix_split_stock_date", "stock_id", "split_date"),
    )

    split_id = Column(BigInteger, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("dim_stock.stock_id"), nullable=False)
    ticker = Column(String(20), nullable=False)
    split_date = Column(Date, nullable=False)
    split_ratio = Column(Float, nullable=False)  # e.g. 4.0 for 4:1 split
    numerator = Column(Integer)    # e.g. 4 for 4:1
    denominator = Column(Integer)  # e.g. 1 for 4:1
    history_restated = Column(Boolean, default=False)
    restated_at = Column(DateTime)
    data_source = Column(String(50))
    created_at = Column(DateTime, default=func.now(), nullable=False)

    stock = relationship("DimStock", back_populates="splits")


class FactBulkLoadLog(Base):
    """Tracks bulk data import jobs (Kaggle CSV, SEC EDGAR, NASDAQ Trader, etc.)."""
    __tablename__ = "fact_bulk_load_log"
    __table_args__ = (
        Index("ix_bulk_load_source", "source"),
    )

    load_id = Column(BigInteger, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)       # "kaggle_csv", "sec_edgar", "nasdaq_trader", "yf_batch"
    file_name = Column(String(500), nullable=True)     # CSV file path if applicable
    tickers_loaded = Column(Integer, default=0)
    rows_loaded = Column(Integer, default=0)
    rows_skipped = Column(Integer, default=0)
    rows_errored = Column(Integer, default=0)
    start_date = Column(Date, nullable=True)           # date range of data loaded
    end_date = Column(Date, nullable=True)
    duration_sec = Column(Float, nullable=True)
    status = Column(Enum("running", "success", "error", name="bulk_load_status"), default="running")
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
