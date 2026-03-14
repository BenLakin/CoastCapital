# CoastCapital Finance

## What
A stock analysis and ML forecasting platform that tracks daily price movements, computes 40+ technical indicators, analyzes news sentiment with Claude, and generates next-day directional forecasts using a LightGBM + XGBoost ensemble. Exposes a Bloomberg-style dark-theme dashboard and a full REST API for n8n automation.

## Why
Publicly available financial data is rich enough to build institutional-grade analytics without Bloomberg Terminal costs. This module turns free data sources (yfinance, NewsAPI, FRED) into actionable daily signals by combining quantitative models with LLM-powered qualitative analysis. The goal is to surface the highest-opportunity stocks each morning before market open.

## How

### Data Pipeline
1. **Ingestion** (`app/pipelines/ingestion.py`) — Fetches OHLCV from yfinance, news from NewsAPI + yfinance, quarterly earnings, and 14 macro indicators (VIX, yields, SPY, gold, oil, DXY). Handles stock splits by restating historical prices.
2. **Technicals** (`app/pipelines/technicals.py`) — Computes SMA/EMA, RSI, MACD, Bollinger Bands, ATR, OBV, MFI, CMF, and golden/death cross signals using the `ta` library.
3. **Feature Engineering** (`app/forecasting/features.py`) — Builds 40+ features across 7 categories: Price/Return, Technical, Volatility, Sentiment, Earnings, Macro, Calendar.
4. **ML Forecasting** (`app/forecasting/models.py`) — 60/40 LightGBM + XGBoost ensemble predicts 1-day forward return and direction. Walk-forward cross-validation with 4 folds ensures no data leakage.
5. **Daily Process** (`app/pipelines/daily_process.py`) — Orchestrates: update macro -> per-ticker (splits, prices, technicals, news, forecast) -> rank by opportunity score -> LLM morning brief.

### Database (Silver / Internal / Gold)
- **coast_finance_silver**: `dim_stock`, `dim_date`, `fact_stock_price`, `fact_technical_indicator`, `fact_stock_news`, `fact_earnings`, `fact_macro_indicator`
- **coast_finance_internal**: `fact_forecast`, `fact_backtest_result`, `fact_model_registry`, `fact_feature_importance`
- **coast_finance_gold**: `fact_portfolio_snapshot`, `fact_signal_performance`, `vw_daily_signals`

### Web Dashboard
Bloomberg-inspired single-page app (`app/static/dashboard.html`) with: market overview bar (SPY/QQQ/VIX/yields), Big Noise alerts, top gainers/losers from Fortune 500, watchlist sparkline cards, and scrolling ticker tape. Auto-refreshes every 5 minutes.

### Agent
**FinanceAgent** — Claude-powered agentic loop with 10 tools (stock analysis, forecast, backtest, macro, news search, compare, pipeline control). Endpoints: `/agent/chat`, `/agent/analyze/<ticker>`, `/agent/morning-brief`.

### Stack
Flask 3.0 + SQLAlchemy + PyMySQL + yfinance + LightGBM + XGBoost + Anthropic SDK. Gunicorn with 4 workers on port 5000. Uses centralized `../.env` for all configuration. Connects to shared `coastcapital-mysql` (no separate MySQL container). Source volume mounts (`./app:/app/app`, `./wsgi.py:/app/wsgi.py`) enable dev iteration without container rebuilds. Includes Prometheus `/metrics` endpoint and MySQL web analytics in `maintenance_db`.

### Testing
Tests require Docker (dependencies on numpy, pandas, pydantic_settings are not easily stubbed). Run tests inside the container.

---

## Rebuild Prompt

> Create an agent called **FinanceAgent** (see `../agents/FINANCE_AGENT.md`) that is the lead developer and chief investment analyst for the Coast Capital Finance Platform. FinanceAgent is powered by `claude-sonnet-4-6` and owns this module end to end — building, maintaining, and evolving the codebase.
>
> Build a Docker container with a Flask app and pipelines callable by n8n that:
>
> 1. Connects to the shared central MySQL instance (`coastcapital-mysql`) using three schema layers: `coast_finance_silver` (raw market data), `coast_finance_internal` (ML outputs), and `coast_finance_gold` (aggregated views). Use dim/fact star schema modeling. Uses centralized `../.env` for all environment variables.
> 2. Ingests daily OHLCV prices, stock splits, quarterly earnings, news articles, and macro indicators (VIX, yields, SPY, gold, oil) from yfinance, NewsAPI, and Alpha Vantage. Use Claude to summarize news and earnings into structured JSON.
> 3. Computes 40+ technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands, ATR, OBV, MFI, CMF) using the `ta` library.
> 4. Builds a LightGBM + XGBoost ensemble (60/40 weighted) that predicts 1-day forward return and direction using 40+ features across 7 categories (price, technical, volatility, sentiment, earnings, macro, calendar). Use walk-forward cross-validation with expanding training windows and no data leakage.
> 5. Creates an idempotent backfill pipeline that handles split restatement and rate limiting.
> 6. Creates a daily process triggered by n8n at 6:30 AM ET weekdays that: updates macro, runs per-ticker pipeline, ranks forecasts by opportunity score, and generates an LLM morning brief.
> 7. Exposes a Bloomberg-style dark-theme single-page dashboard with market overview, Fortune 500 gainers/losers, Big Noise alerts, watchlist sparkline cards, and auto-refresh.
> 8. Implements FinanceAgent as a Claude agentic loop with 10 tools covering stock analysis, forecasting, backtesting, macro conditions, and pipeline control.
> 9. Uses shared brand assets from `CoastCapitalBrand/` (CSS variables, SVG logos, favicon).
> 10. Includes comprehensive pytest suite, structured JSON logging, Prometheus metrics, and MySQL web analytics in `maintenance_db`.
> 11. N8N workflows post to 4 consolidated Slack channels: `#coast-jobs-fyi`, `#coast-action-needed`, `#coast-recent-summaries`, `#coast-current-status`. All messages prefixed with `[Finance]`.
>
> FinanceAgent's analytical framework prioritizes: Risk Management > Macro Regime > Fundamentals > Technicals > Sentiment. Guiding principles: "Price is truth", "Vol is a signal", "Follow the smart money". Never provide investment advice — analytical signals only.
