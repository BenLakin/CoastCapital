"""
Holdings Analyzer — tax-aware sell/hold assessment for existing positions.

Given a user's current holdings (ticker, shares, cost_basis, purchase_date),
analyzes each position and recommends:
  - SELL: model is bearish + high confidence, or after-tax analysis favors selling
  - HOLD: no strong signal or position is underwater and expected to recover
  - STRONG HOLD: position is approaching long-term capital gains threshold (within 45 days)

Tax computation:
  - Short-term capital gains: 37% (held < 365 days)
  - Long-term capital gains: 20% (held >= 365 days)
  - Losses generate tax benefit at the applicable rate

This module provides computational analysis only, not investment advice.
"""
import numpy as np
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional
import yfinance as yf
from sqlalchemy.orm import Session

from app.models.schema import DimStock, FactForecast
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class HoldingInput:
    """User-provided holding information."""
    ticker: str
    shares: float
    cost_basis: float  # per-share cost basis
    purchase_date: date


@dataclass
class TaxImpact:
    """Tax computation result."""
    gain_loss: float              # total gain/loss in dollars
    gain_loss_pct: float          # gain/loss as percentage
    is_long_term: bool            # held >= 365 days
    tax_rate: float               # applicable tax rate
    tax_liability: float          # positive = tax owed, negative = tax benefit
    after_tax_proceeds: float     # what you keep after selling & paying tax
    days_held: int
    days_to_long_term: int        # days until long-term threshold (0 if already long-term)


@dataclass
class HoldingAnalysis:
    """Complete analysis result for a single holding."""
    ticker: str
    shares: float
    cost_basis: float
    current_price: float
    market_value: float
    tax_impact: TaxImpact
    recommendation: str           # SELL, HOLD, STRONG_HOLD
    recommendation_reason: str
    predicted_return_1d: float
    predicted_return_5d: float
    confidence: float
    expected_value_if_hold_1m: float  # estimated after-tax value if held 1 month
    after_tax_sell_now: float         # after-tax proceeds if sold now
    net_advantage_of_holding: float   # expected value if hold - sell now proceeds


def compute_tax_impact(
    shares: float,
    cost_basis: float,
    current_price: float,
    purchase_date: date,
    sell_date: date | None = None,
    short_term_rate: float | None = None,
    long_term_rate: float | None = None,
    holding_period_days: int | None = None,
) -> TaxImpact:
    """
    Compute capital gains tax impact for selling a position.

    Handles:
      - Short-term vs long-term classification
      - Gains (tax owed) and losses (tax benefit)
    """
    sell_date = sell_date or date.today()
    short_term_rate = short_term_rate or settings.TAX_RATE_SHORT_TERM
    long_term_rate = long_term_rate or settings.TAX_RATE_LONG_TERM
    holding_period_days = holding_period_days or settings.TAX_HOLDING_PERIOD_DAYS

    days_held = (sell_date - purchase_date).days
    is_long_term = days_held >= holding_period_days
    days_to_long_term = max(0, holding_period_days - days_held)

    tax_rate = long_term_rate if is_long_term else short_term_rate

    total_cost = shares * cost_basis
    total_proceeds = shares * current_price
    gain_loss = total_proceeds - total_cost
    gain_loss_pct = (current_price / cost_basis - 1) * 100 if cost_basis > 0 else 0

    # Tax: positive gain -> tax owed; loss -> tax benefit (negative liability)
    tax_liability = gain_loss * tax_rate

    after_tax_proceeds = total_proceeds - tax_liability

    return TaxImpact(
        gain_loss=round(gain_loss, 2),
        gain_loss_pct=round(gain_loss_pct, 2),
        is_long_term=is_long_term,
        tax_rate=tax_rate,
        tax_liability=round(tax_liability, 2),
        after_tax_proceeds=round(after_tax_proceeds, 2),
        days_held=days_held,
        days_to_long_term=days_to_long_term,
    )


def analyze_holding(
    holding: HoldingInput,
    current_price: float,
    predicted_return_1d: float = 0.0,
    predicted_return_5d: float = 0.0,
    confidence: float = 0.0,
) -> HoldingAnalysis:
    """
    Analyze a single holding and produce sell/hold recommendation.

    Decision logic:
      1. STRONG_HOLD if within 45 days of long-term threshold and not deeply bearish
      2. SELL if bearish (negative predicted return) with high confidence (>65%)
      3. SELL if after-tax comparison favors selling (expected hold value < sell-now proceeds)
      4. HOLD otherwise (no strong signal)
    """
    market_value = holding.shares * current_price

    tax_impact = compute_tax_impact(
        shares=holding.shares,
        cost_basis=holding.cost_basis,
        current_price=current_price,
        purchase_date=holding.purchase_date,
    )

    after_tax_sell_now = tax_impact.after_tax_proceeds

    # Estimate expected value if held for 1 month (21 trading days ~ 30 calendar days)
    # Use 5d predicted return extrapolated to ~4 weeks
    if predicted_return_5d != 0:
        expected_monthly_return = predicted_return_5d * (21 / 5)
    else:
        expected_monthly_return = predicted_return_1d * 21

    expected_price_1m = current_price * (1 + expected_monthly_return)

    # Tax impact if sold after 1 month
    sell_date_1m = date.today() + timedelta(days=30)
    tax_1m = compute_tax_impact(
        shares=holding.shares,
        cost_basis=holding.cost_basis,
        current_price=expected_price_1m,
        purchase_date=holding.purchase_date,
        sell_date=sell_date_1m,
    )

    expected_value_if_hold_1m = tax_1m.after_tax_proceeds
    net_advantage = expected_value_if_hold_1m - after_tax_sell_now

    # ---- Decision logic ----
    recommendation = "HOLD"
    reason = ""

    # Check proximity to long-term threshold
    approaching_long_term = 0 < tax_impact.days_to_long_term <= 45
    deeply_bearish = predicted_return_5d < -0.03 and confidence > 0.7

    if approaching_long_term and not deeply_bearish:
        recommendation = "STRONG_HOLD"
        days_left = tax_impact.days_to_long_term
        tax_savings = (settings.TAX_RATE_SHORT_TERM - settings.TAX_RATE_LONG_TERM)
        reason = (
            f"Position is {days_left} days from long-term capital gains threshold. "
            f"Holding saves {tax_savings*100:.0f}% in tax rate on gains. "
            f"No strongly bearish signal detected."
        )

    elif predicted_return_5d < -0.005 and confidence > 0.65:
        recommendation = "SELL"
        reason = (
            f"Model predicts {predicted_return_5d*100:.2f}% 5-day return "
            f"with {confidence*100:.0f}% confidence. "
            f"After-tax proceeds if sold now: ${after_tax_sell_now:.2f}."
        )

    elif net_advantage < -0.5:
        # After-tax analysis favors selling (expected hold value meaningfully lower)
        recommendation = "SELL"
        reason = (
            f"After-tax analysis: selling now yields ${after_tax_sell_now:.2f}, "
            f"expected 1-month hold value ${expected_value_if_hold_1m:.2f} "
            f"(net disadvantage of holding: ${abs(net_advantage):.2f})."
        )

    else:
        recommendation = "HOLD"
        if predicted_return_5d > 0.005:
            reason = (
                f"Model predicts {predicted_return_5d*100:.2f}% 5-day return. "
                f"Expected 1-month after-tax value: ${expected_value_if_hold_1m:.2f} "
                f"vs sell now: ${after_tax_sell_now:.2f}."
            )
        else:
            reason = (
                f"No strong directional signal. "
                f"Current after-tax value: ${after_tax_sell_now:.2f}."
            )

    return HoldingAnalysis(
        ticker=holding.ticker,
        shares=holding.shares,
        cost_basis=holding.cost_basis,
        current_price=round(current_price, 2),
        market_value=round(market_value, 2),
        tax_impact=tax_impact,
        recommendation=recommendation,
        recommendation_reason=reason,
        predicted_return_1d=predicted_return_1d,
        predicted_return_5d=predicted_return_5d,
        confidence=confidence,
        expected_value_if_hold_1m=round(expected_value_if_hold_1m, 2),
        after_tax_sell_now=round(after_tax_sell_now, 2),
        net_advantage_of_holding=round(net_advantage, 2),
    )


def analyze_holdings(
    holdings: list[dict],
    db: Session | None = None,
) -> dict:
    """
    Batch analyze user's holdings.

    Parameters:
        holdings: list of dicts with keys:
            ticker, shares, cost_basis, purchase_date (YYYY-MM-DD string or date)
        db: SQLAlchemy session (optional, will create if needed)

    Returns JSON-serializable dict with per-holding analysis and portfolio summary.
    """
    close_db = False
    if db is None:
        from app.models.database import get_db as _get_db
        db_ctx = _get_db()
        db = db_ctx.__enter__()
        close_db = True

    try:
        # Parse holdings
        parsed = []
        for h in holdings:
            pdate = h["purchase_date"]
            if isinstance(pdate, str):
                pdate = date.fromisoformat(pdate)
            parsed.append(HoldingInput(
                ticker=h["ticker"].upper(),
                shares=float(h["shares"]),
                cost_basis=float(h["cost_basis"]),
                purchase_date=pdate,
            ))

        # Fetch current prices via yfinance
        tickers = list(set(h.ticker for h in parsed))
        current_prices = {}
        try:
            data = yf.download(tickers, period="1d", progress=False)
            if not data.empty:
                if len(tickers) == 1:
                    current_prices[tickers[0]] = float(data["Close"].iloc[-1])
                else:
                    for t in tickers:
                        try:
                            current_prices[t] = float(data["Close"][t].iloc[-1])
                        except (KeyError, IndexError):
                            pass
        except Exception as e:
            logger.warning("yfinance price fetch failed", error=str(e))

        # Fetch forecasts from DB
        forecasts = {}
        for t in tickers:
            stock = db.query(DimStock).filter(DimStock.ticker == t).first()
            if not stock:
                continue

            f1d = (
                db.query(FactForecast)
                .filter(FactForecast.stock_id == stock.stock_id, FactForecast.forecast_horizon == 1)
                .order_by(FactForecast.forecast_date.desc())
                .first()
            )
            f5d = (
                db.query(FactForecast)
                .filter(FactForecast.stock_id == stock.stock_id, FactForecast.forecast_horizon == 5)
                .order_by(FactForecast.forecast_date.desc())
                .first()
            )
            forecasts[t] = {
                "predicted_return_1d": float(f1d.predicted_return or 0) if f1d else 0,
                "predicted_return_5d": float(f5d.predicted_return or 0) if f5d else 0,
                "confidence": float(f1d.confidence_score or 0) if f1d else 0,
            }

        # Analyze each holding
        analyses = []
        total_market_value = 0
        total_cost_basis = 0
        total_gain_loss = 0
        total_tax_liability = 0

        for h in parsed:
            price = current_prices.get(h.ticker)
            if price is None:
                logger.warning("No price for ticker", ticker=h.ticker)
                continue

            fc = forecasts.get(h.ticker, {})
            analysis = analyze_holding(
                holding=h,
                current_price=price,
                predicted_return_1d=fc.get("predicted_return_1d", 0),
                predicted_return_5d=fc.get("predicted_return_5d", 0),
                confidence=fc.get("confidence", 0),
            )
            analyses.append(analysis)

            total_market_value += analysis.market_value
            total_cost_basis += h.shares * h.cost_basis
            total_gain_loss += analysis.tax_impact.gain_loss
            total_tax_liability += analysis.tax_impact.tax_liability

        # Serialize
        result_holdings = []
        for a in analyses:
            result_holdings.append({
                "ticker": a.ticker,
                "shares": a.shares,
                "cost_basis": a.cost_basis,
                "current_price": a.current_price,
                "market_value": a.market_value,
                "recommendation": a.recommendation,
                "recommendation_reason": a.recommendation_reason,
                "predicted_return_1d_pct": round(a.predicted_return_1d * 100, 3),
                "predicted_return_5d_pct": round(a.predicted_return_5d * 100, 3),
                "confidence_pct": round(a.confidence * 100, 1),
                "tax_impact": {
                    "gain_loss": a.tax_impact.gain_loss,
                    "gain_loss_pct": a.tax_impact.gain_loss_pct,
                    "is_long_term": a.tax_impact.is_long_term,
                    "tax_rate_pct": round(a.tax_impact.tax_rate * 100, 0),
                    "tax_liability": a.tax_impact.tax_liability,
                    "after_tax_proceeds": a.tax_impact.after_tax_proceeds,
                    "days_held": a.tax_impact.days_held,
                    "days_to_long_term": a.tax_impact.days_to_long_term,
                },
                "expected_value_if_hold_1m": a.expected_value_if_hold_1m,
                "after_tax_sell_now": a.after_tax_sell_now,
                "net_advantage_of_holding": a.net_advantage_of_holding,
            })

        return {
            "analysis_date": str(date.today()),
            "holdings": result_holdings,
            "portfolio_summary": {
                "total_market_value": round(total_market_value, 2),
                "total_cost_basis": round(total_cost_basis, 2),
                "total_gain_loss": round(total_gain_loss, 2),
                "total_gain_loss_pct": round(
                    (total_gain_loss / total_cost_basis * 100) if total_cost_basis > 0 else 0, 2
                ),
                "total_tax_liability": round(total_tax_liability, 2),
                "positions_to_sell": sum(1 for a in analyses if a.recommendation == "SELL"),
                "positions_to_hold": sum(1 for a in analyses if a.recommendation == "HOLD"),
                "positions_strong_hold": sum(1 for a in analyses if a.recommendation == "STRONG_HOLD"),
            },
            "tax_rates_used": {
                "short_term_pct": settings.TAX_RATE_SHORT_TERM * 100,
                "long_term_pct": settings.TAX_RATE_LONG_TERM * 100,
                "holding_period_days": settings.TAX_HOLDING_PERIOD_DAYS,
            },
            "disclaimer": (
                "This analysis is for informational and computational purposes only. "
                "It does not constitute investment, tax, or financial advice. "
                "Consult a qualified tax professional for personalized guidance."
            ),
        }

    finally:
        if close_db:
            db_ctx.__exit__(None, None, None)
