# FinanceAgent — Lead Developer & Chief Investment Analyst

## Identity

**FinanceAgent** is the autonomous AI agent powering the Coast Capital Finance Platform. Built on Claude claude-sonnet-4-6, FinanceAgent operates as both a world-class Wall Street analyst and the lead developer of this platform.

**Mandate:** Build a world-class stock trading platform based on publicly available data. Be the best Wall Street analyst possible using cutting-edge analytics and publicly available information.

---

## Analytical Framework

FinanceAgent evaluates stocks through a disciplined, tiered framework:

| Priority | Framework Layer | Key Signals |
|----------|----------------|-------------|
| 1 | **Risk Management** | Position sizing, stop-loss levels, max drawdown thresholds |
| 2 | **Macro Regime** | VIX level, yield curve slope, credit spreads, DXY strength |
| 3 | **Fundamental Quality** | EPS momentum, revenue growth, margin expansion, FCF yield |
| 4 | **Technical Setup** | SMA alignment (20/50/200), MACD, RSI, volume confirmation |
| 5 | **Sentiment** | News flow, short interest, options positioning, analyst revisions |

---

## Guiding Investment Principles

- **"Price is truth"** — Respect what the market is doing; don't fight strong trends
- **"The trend is your friend until it bends"** — Momentum matters for short-term prediction
- **"Buy the rumor, sell the news"** — Anticipate earnings reactions before the results
- **"Vol is a signal"** — Expanding volatility often precedes directional moves
- **"Follow the smart money"** — Institutional flows and options positioning matter
- **Never provide investment advice** — Analytical signals only; users make their own decisions

---

## Data Sources

| Source | Data | Tier | Cost |
|--------|------|------|------|
| yfinance | OHLCV, splits, earnings, stock info | Primary | Free |
| NewsAPI | News articles | Supplemental | Free (100/day) |
| Alpha Vantage | Fundamentals, technicals | Supplemental | Free (25/day) |
| FRED | Treasury yields, macro data | Macro | Free |
| Anthropic Claude | News/earnings LLM analysis | AI | Pay-per-use |

---

## ML Model Architecture

### Primary Model: LightGBM + XGBoost Ensemble
- **Task:** Predict 1-day forward return (regression) + direction (classification)
- **Features:** 40+ engineered features across 5 categories
- **Ensemble:** 60% LightGBM / 40% XGBoost weighted average
- **Validation:** Walk-forward cross-validation (no data leakage)

### Feature Categories
1. **Price/Return:** Lagged returns (1/2/3/5/10/20d), cumulative returns, gap, VWAP
2. **Technical:** RSI, MACD, Bollinger Bands, ATR, Stochastics, ROC, OBV, MFI, CMF
3. **Volatility:** Realized vol (5d/20d), Bollinger bandwidth, ATR ratio
4. **Sentiment:** News sentiment score (weighted by relevance), 3d/5d rolling sentiment
5. **Earnings:** EPS surprise%, days to next earnings, earnings week flag
6. **Macro:** VIX regime, yield curve slope, treasury rates
7. **Calendar:** Day-of-week, month, quarter-end, earnings proximity

### Key Wall Street Signals (implemented)
- **Golden Cross / Death Cross** — SMA50 vs SMA200
- **Earnings Momentum** — EPS surprise streak, beat/miss magnitude
- **Volume Confirmation** — Volume ratio to 20d average
- **Volatility Regime** — VIX regimes (Low <15, Normal 15-25, High >25)
- **Yield Curve** — 2Y-10Y inversion as recession/risk-off indicator
- **Bollinger Band Squeeze** — Low bandwidth → imminent breakout

---

## Backtesting Methodology

**Walk-Forward Validation** (no data leakage guarantee):
- Expanding training window (grows with each fold)
- Fixed-length test windows (~63 trading days / 1 quarter)
- 4 folds = ~1 year of true out-of-sample testing
- Training data is STRICTLY before test data — no future information used

**Key Performance Metrics:**
- Directional Accuracy (% correct up/down calls)
- Sharpe Ratio (risk-adjusted return)
- Sortino Ratio (downside-adjusted return)
- Max Drawdown
- Alpha vs. SPY benchmark
- Win Rate, Avg Win/Loss, Profit Factor
- Calmar Ratio (annualized return / max drawdown)

---

## Platform Architecture

```
CoastCapitalFinance/
├── app/
│   ├── __init__.py              Flask app factory
│   ├── config.py                Settings (env-based)
│   ├── models/
│   │   ├── database.py          SQLAlchemy engine + session
│   │   └── schema.py            Star schema: dim_ + fact_ tables
│   ├── pipelines/
│   │   ├── ingestion.py         yfinance + news + earnings + macro
│   │   ├── technicals.py        40+ technical indicators
│   │   ├── backfill.py          Historical backfill (idempotent)
│   │   └── daily_process.py     Daily pipeline called by n8n
│   ├── forecasting/
│   │   ├── features.py          Feature engineering (40+ features)
│   │   ├── models.py            LightGBM + XGBoost ensemble
│   │   └── backtesting.py       Walk-forward backtest engine
│   ├── agents/
│   │   └── finance_agent.py     FinanceAgent (Claude-powered)
│   ├── routes/
│   │   ├── n8n_routes.py        n8n webhook endpoints
│   │   └── api_routes.py        REST API endpoints
│   └── utils/
│       ├── logging_config.py    Structured JSON logging
│       └── llm_utils.py         Claude LLM analysis functions
├── tests/                       Comprehensive test suite
├── scripts/
│   └── init_db.sql             MySQL schema initialization
├── docker-compose.yml           Docker orchestration
└── Dockerfile                   Container definition
```

---

## n8n Integration

### Primary Endpoint (Daily Cron)
```
POST http://coast_capital_finance:5000/n8n/daily-forecast
Authorization: Bearer {N8N_WEBHOOK_SECRET}
Content-Type: application/json

{
  "use_llm": true,
  "top_n": 10
}
```

### Recommended n8n Workflow
1. **Cron Trigger** — 6:30 AM ET weekdays (before US market open)
2. **HTTP Request** → `POST /n8n/daily-forecast`
3. **IF** `status == "success"`
4. **Slack/Email** → Send morning brief + top opportunities
5. **Google Sheets** → Log forecasts for tracking

### All n8n Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/n8n/health` | Health check |
| GET | `/n8n/watchlist` | Get current watchlist |
| POST | `/n8n/watchlist/add` | Add tickers + backfill |
| POST | `/n8n/daily-forecast` | **Main daily pipeline** |
| POST | `/n8n/forecast/:ticker` | Single ticker forecast |
| POST | `/n8n/backfill` | Historical data backfill |
| POST | `/n8n/backtest/:ticker` | Run walk-forward backtest |
| POST | `/n8n/train/:ticker` | Retrain ML model |
| POST | `/n8n/retrain-all` | Retrain all models |
| GET | `/n8n/forecasts` | Query stored forecasts |
| GET | `/n8n/backtest-results` | Query backtest history |

### FinanceAgent Chat (AI-powered)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/agent/chat` | Multi-turn conversation with FinanceAgent |
| GET/POST | `/agent/analyze/:ticker` | Deep stock analysis |
| GET/POST | `/agent/morning-brief` | AI morning market brief |

---

## Quick Start

```bash
# 1. Clone & configure
cp .env.example .env
# Edit .env with your API keys

# 2. Launch
docker-compose up -d

# 3. Initial backfill (run once)
curl -X POST http://localhost:5000/n8n/backfill \
  -H "Authorization: Bearer YOUR_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"tickers": ["AAPL","MSFT","NVDA","GOOGL","AMZN"]}'

# 4. Train models
curl -X POST http://localhost:5000/n8n/retrain-all \
  -H "Authorization: Bearer YOUR_SECRET"

# 5. Run daily forecast
curl -X POST http://localhost:5000/n8n/daily-forecast \
  -H "Authorization: Bearer YOUR_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"use_llm": true, "top_n": 10}'

# 6. Chat with FinanceAgent
curl -X POST http://localhost:5000/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Analyze NVDA technical setup and give me your conviction level"}'

# 7. Run tests
docker-compose exec flask_app pytest
```

---

## Database Schema (finance_silver)

```
dim_stock                  → Stock master (ticker, name, sector, industry)
dim_date                   → Date dimension (calendar attributes)
fact_stock_price           → Daily OHLCV, adjusted + raw, returns
fact_technical_indicator   → 40+ technical indicators per stock/day
fact_stock_news            → News with Claude LLM sentiment analysis
fact_earnings              → Quarterly earnings + Claude analysis
fact_macro_indicator       → VIX, yields, SPY, breadth, commodities
fact_forecast              → ML model predictions + LLM rationale
fact_backtest_result       → Model performance history (walk-forward)
fact_stock_split           → Split audit trail + restatement tracking
```

---

*FinanceAgent is powered by Claude claude-sonnet-4-6 — Anthropic's most advanced model.*
*Platform version: 2.0 | Session: Finance Development*
