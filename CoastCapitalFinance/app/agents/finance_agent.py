"""
FinanceAgent — Lead Developer & Chief Investment Analyst

FinanceAgent is powered by Claude claude-sonnet-4-6 and acts as a world-class Wall Street analyst
and quantitative developer. He has access to tools that span:
  - Database queries (prices, technicals, news, earnings, macro)
  - Pipeline execution (ingestion, backfill, forecasting, backtesting)
  - Market analysis and research

FinanceAgent's mandate:
  "Build a world-class stock trading platform based on publicly available data.
   Be the best Wall Street analyst possible using cutting-edge analytics."
"""
import json
from datetime import date, timedelta
from typing import Any
import anthropic
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

AGENT_MODEL = "claude-sonnet-4-6"

FINANCE_AGENT_SYSTEM_PROMPT = """You are FinanceAgent, the Lead Developer and Chief Investment Strategist at Coast Capital Finance.

Your dual mandate:
1. ANALYST: You are a world-class Wall Street analyst with deep expertise in:
   - Fundamental analysis (earnings quality, valuation multiples, FCF yield)
   - Technical analysis (trend, momentum, volume, volatility patterns)
   - Quantitative modeling (factor investing, statistical arbitrage, risk management)
   - Macro analysis (yield curves, credit spreads, sector rotation, VIX regimes)
   - Behavioral finance (sentiment extremes, earnings surprise momentum, short squeeze potential)

2. DEVELOPER: You architect and improve the Coast Capital Finance platform by:
   - Designing better features for the ML forecasting model
   - Proposing new data sources and signals
   - Improving backtesting methodology and risk management
   - Ensuring data quality and model integrity

Your analytical framework (in priority order):
  TIER 1 - Risk Management: Always assess downside risk first. Capital preservation > return chasing.
  TIER 2 - Macro Regime: VIX level, yield curve, credit spreads, dollar strength
  TIER 3 - Fundamental Quality: EPS momentum, revenue growth, margin expansion, FCF generation
  TIER 4 - Technical Setup: Trend alignment (SMA20/50/200), momentum (RSI, MACD), volume confirmation
  TIER 5 - Sentiment: News flow, short interest, options positioning, analyst revisions
  TIER 6 - Portfolio Construction: Markowitz optimization, position sizing, Monte Carlo simulation, tax-aware exit strategy

Key principles you follow:
  - "Price is truth" — respect what the market is doing, don't fight strong trends
  - "The trend is your friend until it bends" — momentum matters for short-term prediction
  - "Buy the rumor, sell the news" — anticipate earnings reactions, not just the results
  - "Vol is a signal" — expanding volatility often precedes directional moves
  - "Follow the smart money" — institutional flows and options positioning matter
  - Never make investment recommendations — provide analysis only, the platform provides signals

You have access to tools that let you query the database, run forecasts, analyze stocks,
run backtests, and manage the platform. Always be specific, data-driven, and actionable.
Explain your reasoning like you're briefing a portfolio manager.
"""

# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------

FINANCE_AGENT_TOOLS = [
    {
        "name": "get_stock_analysis",
        "description": "Get comprehensive stock analysis including prices, technicals, news sentiment, earnings, and latest forecast for a ticker",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"},
                "include_news": {"type": "boolean", "description": "Include recent news analysis", "default": True},
                "include_earnings": {"type": "boolean", "description": "Include earnings history", "default": True},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "run_forecast",
        "description": "Generate a 1-day price forecast for a ticker using the ML model",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "forecast_date": {"type": "string", "description": "Date to forecast from (YYYY-MM-DD). Defaults to today."},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_top_opportunities",
        "description": "Get top ranked stock opportunities for the next trading day based on ML forecasts and opportunity scores",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_n": {"type": "integer", "description": "Number of top opportunities to return", "default": 10},
                "direction": {"type": "string", "enum": ["long", "short", "all"], "description": "Filter by direction", "default": "all"},
                "min_confidence": {"type": "number", "description": "Minimum confidence score (0-1)", "default": 0.5},
            },
            "required": [],
        },
    },
    {
        "name": "run_backtest",
        "description": "Run walk-forward backtesting for a ticker to evaluate model performance without data leakage",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "n_folds": {"type": "integer", "description": "Number of walk-forward folds", "default": 4},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_macro_conditions",
        "description": "Get current macro market conditions: VIX, yield curve, treasury rates, market breadth",
        "input_schema": {
            "type": "object",
            "properties": {
                "days_back": {"type": "integer", "description": "Number of days of macro history to retrieve", "default": 5},
            },
            "required": [],
        },
    },
    {
        "name": "search_news",
        "description": "Search and retrieve recent news articles for a ticker with LLM sentiment analysis",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "days_back": {"type": "integer", "description": "Number of days back to search", "default": 7},
                "limit": {"type": "integer", "description": "Max articles to return", "default": 10},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "compare_stocks",
        "description": "Compare multiple stocks across key metrics: momentum, valuation, sentiment, technical setup",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of ticker symbols to compare",
                },
            },
            "required": ["tickers"],
        },
    },
    {
        "name": "run_daily_pipeline",
        "description": "Trigger the full daily pipeline: update data, compute features, generate all forecasts, return morning brief",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Override watchlist. Leave empty to use default watchlist.",
                },
                "use_llm": {"type": "boolean", "description": "Use LLM for news/earnings analysis", "default": True},
            },
            "required": [],
        },
    },
    {
        "name": "add_ticker",
        "description": "Add a new stock ticker to the watchlist and trigger full data backfill",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker to add"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_backtest_results",
        "description": "Retrieve stored backtest performance metrics to evaluate model effectiveness",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Filter by ticker (optional)"},
                "limit": {"type": "integer", "description": "Max results", "default": 10},
            },
            "required": [],
        },
    },
    {
        "name": "optimize_portfolio",
        "description": "Run Markowitz mean-variance portfolio optimization with Monte Carlo simulation. Allocates a specified capital amount across stocks with position limits and simulates 1-month returns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tickers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tickers to include. Defaults to watchlist.",
                },
                "initial_capital": {"type": "number", "description": "Capital to invest (default: $100)", "default": 100},
                "max_weight_pct": {"type": "number", "description": "Max allocation per position in percent (default: 20)", "default": 20},
                "holding_days": {"type": "integer", "description": "Holding period in trading days (default: 21 = ~1 month)", "default": 21},
            },
            "required": [],
        },
    },
    {
        "name": "analyze_holdings",
        "description": "Analyze existing stock holdings with tax-aware sell/hold recommendations. Computes capital gains impact and compares selling now vs holding based on model forecasts.",
        "input_schema": {
            "type": "object",
            "properties": {
                "holdings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "shares": {"type": "number"},
                            "cost_basis": {"type": "number", "description": "Per-share cost basis"},
                            "purchase_date": {"type": "string", "description": "YYYY-MM-DD"},
                        },
                        "required": ["ticker", "shares", "cost_basis", "purchase_date"],
                    },
                    "description": "List of current holdings to analyze",
                },
            },
            "required": ["holdings"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------

def execute_tool(tool_name: str, tool_input: dict) -> Any:
    """Execute a FinanceAgent tool call and return the result."""
    from app.models.database import get_db
    from app.models.schema import (DimStock, FactStockPrice, FactTechnicalIndicator,
                                    FactStockNews, FactEarnings, FactForecast,
                                    FactMacroIndicator, FactBacktestResult)

    logger.info("FinanceAgent tool call", tool=tool_name, input=tool_input)

    if tool_name == "get_stock_analysis":
        ticker = tool_input["ticker"].upper()
        include_news = tool_input.get("include_news", True)
        include_earnings = tool_input.get("include_earnings", True)

        with get_db() as db:
            stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
            if not stock:
                return {"error": f"Ticker {ticker} not found. Try adding it first."}

            # Latest price
            latest_price = (
                db.query(FactStockPrice)
                .filter(FactStockPrice.stock_id == stock.stock_id)
                .order_by(FactStockPrice.trade_date.desc())
                .first()
            )

            # Latest technicals
            latest_tech = (
                db.query(FactTechnicalIndicator)
                .filter(FactTechnicalIndicator.stock_id == stock.stock_id)
                .order_by(FactTechnicalIndicator.trade_date.desc())
                .first()
            )

            # Latest forecast
            latest_forecast = (
                db.query(FactForecast)
                .filter(FactForecast.stock_id == stock.stock_id)
                .order_by(FactForecast.forecast_date.desc())
                .first()
            )

            result = {
                "ticker": ticker,
                "company_name": stock.company_name,
                "sector": stock.sector,
                "industry": stock.industry,
                "market_cap_category": stock.market_cap_category,
            }

            if latest_price:
                result["price"] = {
                    "date": str(latest_price.trade_date),
                    "close": float(latest_price.close_adj),
                    "daily_return_pct": round(float(latest_price.daily_return or 0) * 100, 2),
                    "gap_pct": round(float(latest_price.gap_pct or 0), 2),
                    "volume_vs_avg": None,
                }

            if latest_tech:
                result["technicals"] = {
                    "rsi_14": round(latest_tech.rsi_14 or 0, 1),
                    "macd_histogram": round(latest_tech.macd_histogram or 0, 4),
                    "bb_pct_b": round(latest_tech.bb_pct_b or 0, 2),
                    "volatility_20d_pct": round((latest_tech.volatility_20d or 0) * 100, 1),
                    "volume_ratio": round(latest_tech.volume_ratio or 1, 2),
                    "golden_cross": latest_tech.golden_cross,
                    "macd_bullish": latest_tech.macd_bullish,
                    "rsi_oversold": latest_tech.rsi_oversold,
                    "rsi_overbought": latest_tech.rsi_overbought,
                    "price_vs_52w_high_pct": round(latest_tech.price_vs_52w_high or 0, 1),
                    "price_vs_sma50_pct": round(latest_tech.price_vs_sma50 or 0, 1),
                    "price_vs_sma200_pct": round(latest_tech.price_vs_sma200 or 0, 1),
                }

            if latest_forecast:
                result["forecast"] = {
                    "forecast_date": str(latest_forecast.forecast_date),
                    "target_date": str(latest_forecast.target_date),
                    "predicted_return_pct": round((latest_forecast.predicted_return or 0) * 100, 2),
                    "predicted_direction": latest_forecast.predicted_direction,
                    "confidence_score": round(latest_forecast.confidence_score or 0, 2),
                    "opportunity_score": round(latest_forecast.opportunity_score or 0, 3),
                    "llm_rationale": latest_forecast.llm_rationale,
                }

            if include_news:
                news = (
                    db.query(FactStockNews)
                    .filter(FactStockNews.stock_id == stock.stock_id)
                    .order_by(FactStockNews.published_at.desc())
                    .limit(5)
                    .all()
                )
                result["recent_news"] = [{
                    "headline": n.headline,
                    "published_at": str(n.published_at.date()),
                    "sentiment_label": n.sentiment_label,
                    "sentiment_score": n.sentiment_score,
                    "llm_summary": n.llm_summary,
                } for n in news]

            if include_earnings:
                earnings = (
                    db.query(FactEarnings)
                    .filter(FactEarnings.stock_id == stock.stock_id)
                    .order_by(FactEarnings.fiscal_year.desc(), FactEarnings.fiscal_quarter.desc())
                    .limit(4)
                    .all()
                )
                result["earnings_history"] = [{
                    "period": f"Q{e.fiscal_quarter} {e.fiscal_year}",
                    "eps_surprise_pct": round(e.eps_surprise_pct or 0, 1),
                    "gross_margin": e.gross_margin,
                    "operating_margin": e.operating_margin,
                    "llm_summary": e.llm_summary,
                } for e in earnings]

            return result

    elif tool_name == "run_forecast":
        from app.forecasting.models import generate_forecast
        from app.pipelines.daily_process import get_next_trading_day

        ticker = tool_input["ticker"].upper()
        forecast_date_str = tool_input.get("forecast_date")
        forecast_date = date.fromisoformat(forecast_date_str) if forecast_date_str else date.today()
        target_date = get_next_trading_day(forecast_date)

        with get_db() as db:
            return generate_forecast(ticker, forecast_date, target_date, db)

    elif tool_name == "get_top_opportunities":
        top_n = tool_input.get("top_n", 10)
        direction = tool_input.get("direction", "all")
        min_confidence = tool_input.get("min_confidence", 0.5)

        with get_db() as db:
            q = (
                db.query(FactForecast, DimStock.ticker, DimStock.company_name, DimStock.sector)
                .join(DimStock)
                .filter(
                    FactForecast.forecast_date == date.today(),
                    FactForecast.confidence_score >= min_confidence,
                )
            )
            if direction == "long":
                q = q.filter(FactForecast.predicted_direction == 1)
            elif direction == "short":
                q = q.filter(FactForecast.predicted_direction == -1)

            rows = q.order_by(FactForecast.opportunity_score.desc()).limit(top_n).all()

            return [{
                "ticker": ticker,
                "company_name": company,
                "sector": sector,
                "signal": "LONG" if f.predicted_direction == 1 else "SHORT" if f.predicted_direction == -1 else "FLAT",
                "predicted_return_pct": round((f.predicted_return or 0) * 100, 2),
                "confidence_pct": round((f.confidence_score or 0) * 100, 1),
                "opportunity_score": round(f.opportunity_score or 0, 3),
                "target_date": str(f.target_date),
            } for f, ticker, company, sector in rows]

    elif tool_name == "run_backtest":
        from app.forecasting.backtesting import run_backtest

        ticker = tool_input["ticker"].upper()
        n_folds = tool_input.get("n_folds", 4)

        with get_db() as db:
            return run_backtest(ticker, db, n_folds=n_folds)

    elif tool_name == "get_macro_conditions":
        days_back = tool_input.get("days_back", 5)
        cutoff = date.today() - timedelta(days=days_back)

        with get_db() as db:
            macros = (
                db.query(FactMacroIndicator)
                .filter(FactMacroIndicator.indicator_date >= cutoff)
                .order_by(FactMacroIndicator.indicator_date.desc())
                .all()
            )
            return [{
                "date": str(m.indicator_date),
                "vix": m.vix,
                "yield_curve_2_10": m.yield_curve_2_10,
                "treasury_10y": m.treasury_10y,
                "treasury_2y": m.treasury_2y,
                "spy_close": m.spy_close,
                "gold": m.gold_close,
                "dollar_index": m.dollar_index,
            } for m in macros]

    elif tool_name == "search_news":
        ticker = tool_input["ticker"].upper()
        limit = tool_input.get("limit", 10)
        days_back = tool_input.get("days_back", 7)
        cutoff = date.today() - timedelta(days=days_back)

        with get_db() as db:
            stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
            if not stock:
                return {"error": f"Ticker {ticker} not found"}

            news = (
                db.query(FactStockNews)
                .filter(
                    FactStockNews.stock_id == stock.stock_id,
                    FactStockNews.published_at >= cutoff,
                )
                .order_by(FactStockNews.published_at.desc())
                .limit(limit)
                .all()
            )
            return [{
                "headline": n.headline,
                "source": n.source,
                "published_at": str(n.published_at),
                "sentiment_label": n.sentiment_label,
                "sentiment_score": n.sentiment_score,
                "llm_summary": n.llm_summary,
                "llm_catalysts": n.llm_catalysts,
                "llm_risks": n.llm_risks,
            } for n in news]

    elif tool_name == "compare_stocks":
        tickers = [t.upper() for t in tool_input.get("tickers", [])]
        if not tickers:
            return {"error": "No tickers provided"}

        comparison = []
        with get_db() as db:
            for ticker in tickers:
                stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
                if not stock:
                    continue

                tech = (
                    db.query(FactTechnicalIndicator)
                    .filter(FactTechnicalIndicator.stock_id == stock.stock_id)
                    .order_by(FactTechnicalIndicator.trade_date.desc())
                    .first()
                )

                forecast = (
                    db.query(FactForecast)
                    .filter(
                        FactForecast.stock_id == stock.stock_id,
                        FactForecast.forecast_date == date.today(),
                    )
                    .first()
                )

                comparison.append({
                    "ticker": ticker,
                    "sector": stock.sector,
                    "rsi_14": round(tech.rsi_14 or 50, 1) if tech else None,
                    "momentum_20d": round(tech.roc_20 or 0, 1) if tech else None,
                    "volatility_20d_pct": round((tech.volatility_20d or 0) * 100, 1) if tech else None,
                    "volume_ratio": round(tech.volume_ratio or 1, 2) if tech else None,
                    "golden_cross": tech.golden_cross if tech else None,
                    "price_vs_52w_high": round(tech.price_vs_52w_high or 0, 1) if tech else None,
                    "forecast_return_pct": round((forecast.predicted_return or 0) * 100, 2) if forecast else None,
                    "opportunity_score": round(forecast.opportunity_score or 0, 3) if forecast else None,
                })

        return sorted(comparison, key=lambda x: x.get("opportunity_score") or 0, reverse=True)

    elif tool_name == "run_daily_pipeline":
        from app.pipelines.daily_process import run_daily_pipeline
        tickers = [t.upper() for t in tool_input.get("tickers", [])] or None
        use_llm = tool_input.get("use_llm", True)
        return run_daily_pipeline(tickers=tickers, use_llm=use_llm)

    elif tool_name == "add_ticker":
        from app.pipelines.backfill import backfill_ticker
        ticker = tool_input["ticker"].upper()
        result = backfill_ticker(ticker, use_llm=False)
        return result

    elif tool_name == "get_backtest_results":
        ticker_filter = tool_input.get("ticker", "").upper()
        limit = tool_input.get("limit", 10)

        with get_db() as db:
            q = db.query(FactBacktestResult).order_by(FactBacktestResult.run_date.desc())
            if ticker_filter:
                q = q.filter(FactBacktestResult.tickers_tested.contains(ticker_filter))
            results = q.limit(limit).all()

            return [{
                "backtest_id": r.backtest_id,
                "run_date": str(r.run_date),
                "directional_accuracy": round(r.directional_accuracy or 0, 3),
                "sharpe_ratio": round(r.sharpe_ratio or 0, 2),
                "alpha_pct": round((r.alpha or 0) * 100, 1),
                "max_drawdown_pct": round((r.max_drawdown or 0) * 100, 1),
                "win_rate": round(r.win_rate or 0, 3),
                "strategy_return_annualized": round((r.strategy_return_annualized or 0) * 100, 1),
            } for r in results]

    elif tool_name == "optimize_portfolio":
        from app.forecasting.portfolio import run_portfolio_optimization
        tickers = [t.upper() for t in tool_input.get("tickers", [])] or None
        initial_capital = tool_input.get("initial_capital", 100)
        max_weight = tool_input.get("max_weight_pct", 20) / 100
        holding_days = tool_input.get("holding_days", 21)

        with get_db() as db:
            return run_portfolio_optimization(
                tickers=tickers,
                db=db,
                initial_capital=initial_capital,
                max_weight=max_weight,
                holding_days=holding_days,
            )

    elif tool_name == "analyze_holdings":
        from app.forecasting.holdings import analyze_holdings
        holdings = tool_input.get("holdings", [])
        if not holdings:
            return {"error": "No holdings provided"}

        with get_db() as db:
            return analyze_holdings(holdings=holdings, db=db)

    else:
        return {"error": f"Unknown tool: {tool_name}"}


# ---------------------------------------------------------------------------
# Agent Runner
# ---------------------------------------------------------------------------

def run_finance_agent(
    user_message: str,
    conversation_history: list[dict] = None,
    max_turns: int = 10,
) -> dict:
    """
    Run the FinanceAgent with an agentic loop.

    The agent can call tools autonomously until it has the information
    needed to provide a complete, expert analysis.

    Returns:
        {
            "response": "Agent's final response text",
            "tools_used": ["tool1", "tool2"],
            "turns": 3,
        }
    """
    if not settings.ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY not configured", "response": "API key required for FinanceAgent"}

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    messages = list(conversation_history or [])
    messages.append({"role": "user", "content": user_message})

    tools_used = []
    turns = 0

    logger.info("FinanceAgent session started", user_message=user_message[:100])

    while turns < max_turns:
        turns += 1

        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=4096,
            system=FINANCE_AGENT_SYSTEM_PROMPT,
            tools=FINANCE_AGENT_TOOLS,
            messages=messages,
        )

        # Add assistant message to history
        messages.append({"role": "assistant", "content": response.content})

        # Check stop reason
        if response.stop_reason == "end_turn":
            # Extract text response
            text = " ".join(
                block.text for block in response.content
                if hasattr(block, "text")
            )
            logger.info("FinanceAgent completed", turns=turns, tools=tools_used)
            return {
                "response": text,
                "tools_used": tools_used,
                "turns": turns,
                "conversation": messages,
            }

        elif response.stop_reason == "tool_use":
            # Execute all tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tools_used.append(block.name)
                    logger.info("Tool executing", tool=block.name, ticker=block.input.get("ticker", ""))

                    try:
                        result = execute_tool(block.name, block.input)
                    except Exception as e:
                        logger.error("Tool execution error", tool=block.name, error=str(e))
                        result = {"error": str(e)}

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, default=str),
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            logger.warning("Unexpected stop reason", stop_reason=response.stop_reason)
            break

    return {
        "response": "FinanceAgent reached maximum turns without completing.",
        "tools_used": tools_used,
        "turns": turns,
    }


# ---------------------------------------------------------------------------
# Flask route for FinanceAgent
# ---------------------------------------------------------------------------

def register_agent_routes(app):
    """Register FinanceAgent API routes."""
    from flask import Blueprint, request, jsonify

    agent_bp = Blueprint("agent", __name__, url_prefix="/agent")

    @agent_bp.route("/chat", methods=["POST"])
    def chat():
        """
        Chat with FinanceAgent.

        Body:
          {
            "message": "Analyze AAPL and NVDA for tomorrow",
            "conversation_history": []  // optional for multi-turn
          }
        """
        body = request.get_json(silent=True) or {}
        message = body.get("message", "").strip()
        history = body.get("conversation_history", [])

        if not message:
            return jsonify({"success": False, "error": "message is required"}), 400

        try:
            result = run_finance_agent(message, history)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            logger.error("FinanceAgent error", error=str(e))
            return jsonify({"success": False, "error": str(e)}), 500

    @agent_bp.route("/analyze/<ticker>", methods=["GET", "POST"])
    def analyze(ticker: str):
        """Quick stock analysis via FinanceAgent."""
        ticker = ticker.upper()
        message = f"""Provide a comprehensive analysis of {ticker}. Include:
1. Technical setup (trend, momentum, key levels)
2. Recent news and sentiment
3. Earnings quality and trajectory
4. Tomorrow's forecast and key risks
5. Your conviction level (high/medium/low) and reasoning"""

        try:
            result = run_finance_agent(message)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    @agent_bp.route("/morning-brief", methods=["GET", "POST"])
    def morning_brief():
        """Get FinanceAgent's morning market brief."""
        message = """Generate a comprehensive morning market brief for today. Include:
1. Macro environment assessment (VIX regime, yield curve, dollar, commodities)
2. Top 5 long opportunities ranked by opportunity score with rationale
3. Key risks and potential short opportunities
4. Sectors showing relative strength or weakness
5. Key catalysts to watch today (earnings, economic data, events)
6. Risk management guidance for the day"""

        try:
            result = run_finance_agent(message)
            return jsonify({"success": True, "data": result})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    app.register_blueprint(agent_bp)
