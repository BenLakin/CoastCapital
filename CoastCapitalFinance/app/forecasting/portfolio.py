"""
Portfolio Optimizer — Markowitz MVO with Monte Carlo simulation.

Given ML forecasts for multiple tickers, allocates a $100 portfolio with:
  - Max 20% in any single position (configurable)
  - Long-only, fully invested
  - Ledoit-Wolf shrinkage for stable covariance estimation
  - Monte Carlo simulation (1000 paths) over 21 trading day horizon
  - Optimal exit day detection and probability of profit

Usage:
    result = run_portfolio_optimization(tickers, db)
    # result.allocations = [{"ticker": "AAPL", "weight": 0.15, "dollars": 15.0}, ...]
    # result.monte_carlo = {"mean_return": ..., "p10": ..., "p90": ..., "prob_profit": ...}
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf
from sqlalchemy.orm import Session

from app.models.schema import DimStock, FactStockPrice, FactForecast
from app.models.database import get_db
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class PortfolioAllocation:
    ticker: str
    weight: float
    dollars: float
    predicted_return_1d: float
    predicted_return_5d: float
    confidence: float
    opportunity_score: float


@dataclass
class MonteCarloResult:
    mean_final_value: float
    median_final_value: float
    p10_final_value: float
    p25_final_value: float
    p75_final_value: float
    p90_final_value: float
    prob_profit: float
    expected_return_pct: float
    max_drawdown_mean: float
    optimal_exit_day: int
    optimal_exit_value: float
    daily_mean_path: list[float]
    daily_p10_path: list[float]
    daily_p90_path: list[float]


@dataclass
class PortfolioResult:
    initial_capital: float
    allocations: list[PortfolioAllocation]
    monte_carlo: MonteCarloResult
    risk_metrics: dict
    optimization_method: str = "markowitz_mvo"


def compute_covariance_matrix(
    tickers: list[str],
    db: Session,
    lookback_days: int = 252,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute Ledoit-Wolf shrinkage covariance matrix from historical returns.

    Returns:
        (returns_df, cov_matrix) — daily returns DataFrame and covariance matrix
    """
    end_date = date.today()
    start_date = end_date - timedelta(days=int(lookback_days * 1.5))

    all_returns = {}
    for ticker in tickers:
        stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
        if not stock:
            continue

        prices = (
            db.query(FactStockPrice.trade_date, FactStockPrice.close_adj)
            .filter(
                FactStockPrice.stock_id == stock.stock_id,
                FactStockPrice.trade_date >= start_date,
                FactStockPrice.trade_date <= end_date,
            )
            .order_by(FactStockPrice.trade_date)
            .all()
        )
        if len(prices) < 60:
            continue

        ser = pd.Series(
            [float(p.close_adj) for p in prices],
            index=[p.trade_date for p in prices],
        )
        all_returns[ticker] = ser.pct_change().dropna()

    if not all_returns:
        raise ValueError("No sufficient price data for covariance estimation")

    returns_df = pd.DataFrame(all_returns).dropna()

    if len(returns_df) < 30:
        raise ValueError(f"Only {len(returns_df)} overlapping return days, need >= 30")

    # Ledoit-Wolf shrinkage for stable estimation
    lw = LedoitWolf()
    lw.fit(returns_df.values)
    cov_matrix = pd.DataFrame(
        lw.covariance_,
        index=returns_df.columns,
        columns=returns_df.columns,
    )

    return returns_df, cov_matrix


def optimize_portfolio(
    expected_returns: dict[str, float],
    cov_matrix: pd.DataFrame,
    max_weight: float = None,
    initial_capital: float = None,
) -> list[PortfolioAllocation]:
    """
    Markowitz mean-variance optimization with constraints.

    Constraints:
        - Weights sum to 1
        - 0 <= w_i <= max_weight (default 20%)
        - Long-only
    """
    max_weight = max_weight or settings.PORTFOLIO_MAX_WEIGHT
    initial_capital = initial_capital or settings.PORTFOLIO_INITIAL_CAPITAL

    tickers = list(cov_matrix.columns)
    n = len(tickers)

    # Expected returns vector (aligned to covariance columns)
    mu = np.array([expected_returns.get(t, 0.0) for t in tickers])

    # Objective: minimize -Sharpe ~ minimize (w'Σw) / (w'μ) -> maximize w'μ - λ * w'Σw
    # Use risk_aversion parameter lambda to balance return vs risk
    risk_aversion = 2.0  # moderate risk aversion
    sigma = cov_matrix.values

    def neg_utility(w):
        port_return = w @ mu
        port_var = w @ sigma @ w
        return -(port_return - risk_aversion * port_var)

    # Constraints
    constraints = [
        {"type": "eq", "fun": lambda w: np.sum(w) - 1.0},  # fully invested
    ]

    bounds = [(0.0, max_weight) for _ in range(n)]

    # Initial guess: equal weight (capped at max_weight)
    w0 = np.full(n, 1.0 / n)
    w0 = np.clip(w0, 0, max_weight)
    w0 /= w0.sum()

    result = minimize(
        neg_utility,
        w0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"maxiter": 1000, "ftol": 1e-12},
    )

    if not result.success:
        logger.warning("Portfolio optimization did not converge, using equal weights",
                       message=result.message)
        weights = np.full(n, 1.0 / n)
    else:
        weights = result.x

    # Clean up near-zero weights
    weights[weights < 0.001] = 0
    if weights.sum() > 0:
        weights /= weights.sum()

    allocations = []
    for i, ticker in enumerate(tickers):
        if weights[i] < 0.001:
            continue
        allocations.append(PortfolioAllocation(
            ticker=ticker,
            weight=float(weights[i]),
            dollars=float(weights[i] * initial_capital),
            predicted_return_1d=float(expected_returns.get(ticker, 0)),
            predicted_return_5d=0.0,  # filled by caller
            confidence=0.0,
            opportunity_score=0.0,
        ))

    allocations.sort(key=lambda a: a.weight, reverse=True)
    return allocations


def monte_carlo_simulation(
    allocations: list[PortfolioAllocation],
    cov_matrix: pd.DataFrame,
    returns_df: pd.DataFrame,
    holding_days: int = None,
    n_paths: int = None,
    initial_capital: float = None,
) -> MonteCarloResult:
    """
    Monte Carlo simulation of portfolio over holding period.

    Generates correlated multivariate-normal daily returns for n_paths
    and tracks portfolio value over holding_days.
    """
    holding_days = holding_days or settings.PORTFOLIO_HOLDING_HORIZON
    n_paths = n_paths or settings.MONTE_CARLO_PATHS
    initial_capital = initial_capital or settings.PORTFOLIO_INITIAL_CAPITAL

    tickers = [a.ticker for a in allocations]
    weights = np.array([a.weight for a in allocations])

    # Use tickers present in cov matrix
    valid = [t for t in tickers if t in cov_matrix.columns]
    if not valid:
        raise ValueError("No valid tickers for Monte Carlo simulation")

    # Align weights to valid tickers
    valid_weights = np.array([
        allocations[tickers.index(t)].weight for t in valid
    ])
    valid_weights /= valid_weights.sum()

    # Historical mean and covariance for valid tickers
    sub_returns = returns_df[valid].dropna()
    mean_daily = sub_returns.mean().values
    cov_daily = cov_matrix.loc[valid, valid].values

    # Simulate paths
    np.random.seed(42)
    # shape: (n_paths, holding_days, n_assets)
    simulated_returns = np.random.multivariate_normal(
        mean_daily, cov_daily, size=(n_paths, holding_days)
    )

    # Portfolio daily returns: weighted sum across assets
    port_daily_returns = simulated_returns @ valid_weights  # (n_paths, holding_days)

    # Cumulative portfolio value
    port_values = initial_capital * np.cumprod(1 + port_daily_returns, axis=1)

    # Add initial capital as day 0
    port_values = np.column_stack([
        np.full(n_paths, initial_capital),
        port_values,
    ])

    # Statistics per day
    daily_mean = port_values.mean(axis=0)
    daily_p10 = np.percentile(port_values, 10, axis=0)
    daily_p90 = np.percentile(port_values, 90, axis=0)

    # Final values
    final_values = port_values[:, -1]

    # Max drawdown per path
    running_max = np.maximum.accumulate(port_values, axis=1)
    drawdowns = (port_values - running_max) / running_max
    max_dd_per_path = drawdowns.min(axis=1)

    # Optimal exit day: day with highest mean portfolio value
    optimal_day = int(np.argmax(daily_mean))
    optimal_value = float(daily_mean[optimal_day])

    return MonteCarloResult(
        mean_final_value=float(np.mean(final_values)),
        median_final_value=float(np.median(final_values)),
        p10_final_value=float(np.percentile(final_values, 10)),
        p25_final_value=float(np.percentile(final_values, 25)),
        p75_final_value=float(np.percentile(final_values, 75)),
        p90_final_value=float(np.percentile(final_values, 90)),
        prob_profit=float(np.mean(final_values > initial_capital)),
        expected_return_pct=float((np.mean(final_values) / initial_capital - 1) * 100),
        max_drawdown_mean=float(np.mean(max_dd_per_path)),
        optimal_exit_day=optimal_day,
        optimal_exit_value=optimal_value,
        daily_mean_path=daily_mean.tolist(),
        daily_p10_path=daily_p10.tolist(),
        daily_p90_path=daily_p90.tolist(),
    )


def run_portfolio_optimization(
    tickers: list[str] | None = None,
    db: Session | None = None,
    initial_capital: float | None = None,
    max_weight: float | None = None,
    holding_days: int | None = None,
) -> dict:
    """
    Full portfolio optimization pipeline:
      1. Fetch latest forecasts for tickers
      2. Compute covariance matrix
      3. Run Markowitz MVO
      4. Run Monte Carlo simulation
      5. Return PortfolioResult as dict

    Returns JSON-serializable dict for API consumption.
    """
    initial_capital = initial_capital or settings.PORTFOLIO_INITIAL_CAPITAL
    max_weight = max_weight or settings.PORTFOLIO_MAX_WEIGHT
    holding_days = holding_days or settings.PORTFOLIO_HOLDING_HORIZON

    close_db = False
    if db is None:
        from app.models.database import get_db as _get_db
        db_ctx = _get_db()
        db = db_ctx.__enter__()
        close_db = True

    try:
        tickers = tickers or settings.watchlist

        # Fetch latest forecasts
        expected_returns_1d = {}
        expected_returns_5d = {}
        forecast_meta = {}

        for ticker in tickers:
            stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
            if not stock:
                continue

            # Get latest 1d forecast
            forecast_1d = (
                db.query(FactForecast)
                .filter(
                    FactForecast.stock_id == stock.stock_id,
                    FactForecast.forecast_horizon == 1,
                )
                .order_by(FactForecast.forecast_date.desc())
                .first()
            )

            forecast_5d = (
                db.query(FactForecast)
                .filter(
                    FactForecast.stock_id == stock.stock_id,
                    FactForecast.forecast_horizon == 5,
                )
                .order_by(FactForecast.forecast_date.desc())
                .first()
            )

            if forecast_1d:
                expected_returns_1d[ticker] = float(forecast_1d.predicted_return or 0)
                forecast_meta[ticker] = {
                    "confidence": float(forecast_1d.confidence_score or 0),
                    "opportunity_score": float(forecast_1d.opportunity_score or 0),
                    "predicted_return_1d": float(forecast_1d.predicted_return or 0),
                    "predicted_return_5d": float(forecast_5d.predicted_return or 0) if forecast_5d else 0,
                }
            if forecast_5d:
                expected_returns_5d[ticker] = float(forecast_5d.predicted_return or 0)

        if not expected_returns_1d:
            raise ValueError("No forecasts available. Run forecasts first.")

        # Use 5d returns for optimization (1-month horizon is closer to weekly)
        # Annualize 5d returns for optimization, fallback to 1d
        opt_returns = {}
        for t in expected_returns_1d:
            if t in expected_returns_5d and expected_returns_5d[t] != 0:
                opt_returns[t] = expected_returns_5d[t]
            else:
                opt_returns[t] = expected_returns_1d[t] * 5  # rough 5d estimate

        valid_tickers = list(opt_returns.keys())

        # Compute covariance
        returns_df, cov_matrix = compute_covariance_matrix(valid_tickers, db)

        # Filter to tickers present in covariance matrix
        final_tickers = [t for t in valid_tickers if t in cov_matrix.columns]
        if not final_tickers:
            raise ValueError("No tickers with sufficient price history for optimization")

        final_returns = {t: opt_returns[t] for t in final_tickers}

        # Optimize
        allocations = optimize_portfolio(
            expected_returns=final_returns,
            cov_matrix=cov_matrix.loc[final_tickers, final_tickers],
            max_weight=max_weight,
            initial_capital=initial_capital,
        )

        # Enrich allocations with forecast metadata
        for a in allocations:
            meta = forecast_meta.get(a.ticker, {})
            a.predicted_return_5d = meta.get("predicted_return_5d", 0)
            a.confidence = meta.get("confidence", 0)
            a.opportunity_score = meta.get("opportunity_score", 0)

        # Monte Carlo
        mc = monte_carlo_simulation(
            allocations=allocations,
            cov_matrix=cov_matrix,
            returns_df=returns_df,
            holding_days=holding_days,
            initial_capital=initial_capital,
        )

        # Risk metrics
        port_weights = np.array([a.weight for a in allocations])
        port_tickers = [a.ticker for a in allocations]
        sub_cov = cov_matrix.loc[port_tickers, port_tickers].values
        port_vol_daily = float(np.sqrt(port_weights @ sub_cov @ port_weights))
        port_vol_annual = port_vol_daily * np.sqrt(252)

        port_return = sum(a.weight * opt_returns.get(a.ticker, 0) for a in allocations)
        sharpe_est = (port_return * 252/5 - 0.05) / port_vol_annual if port_vol_annual > 0 else 0

        risk_metrics = {
            "portfolio_volatility_annual_pct": round(port_vol_annual * 100, 2),
            "portfolio_volatility_daily_pct": round(port_vol_daily * 100, 4),
            "estimated_sharpe_ratio": round(sharpe_est, 2),
            "max_position_weight_pct": round(max(a.weight for a in allocations) * 100, 1) if allocations else 0,
            "num_positions": len(allocations),
            "concentration_hhi": round(float(np.sum(port_weights**2)), 4),
        }

        # Serialize
        return {
            "initial_capital": initial_capital,
            "holding_days": holding_days,
            "max_weight_pct": max_weight * 100,
            "optimization_method": "markowitz_mvo",
            "allocations": [
                {
                    "ticker": a.ticker,
                    "weight_pct": round(a.weight * 100, 2),
                    "dollars": round(a.dollars, 2),
                    "predicted_return_1d_pct": round(a.predicted_return_1d * 100, 3),
                    "predicted_return_5d_pct": round(a.predicted_return_5d * 100, 3),
                    "confidence_pct": round(a.confidence * 100, 1),
                    "opportunity_score": round(a.opportunity_score, 3),
                }
                for a in allocations
            ],
            "monte_carlo": {
                "n_paths": settings.MONTE_CARLO_PATHS,
                "holding_days": holding_days,
                "mean_final_value": round(mc.mean_final_value, 2),
                "median_final_value": round(mc.median_final_value, 2),
                "p10_final_value": round(mc.p10_final_value, 2),
                "p25_final_value": round(mc.p25_final_value, 2),
                "p75_final_value": round(mc.p75_final_value, 2),
                "p90_final_value": round(mc.p90_final_value, 2),
                "prob_profit_pct": round(mc.prob_profit * 100, 1),
                "expected_return_pct": round(mc.expected_return_pct, 2),
                "max_drawdown_mean_pct": round(mc.max_drawdown_mean * 100, 2),
                "optimal_exit_day": mc.optimal_exit_day,
                "optimal_exit_value": round(mc.optimal_exit_value, 2),
            },
            "risk_metrics": risk_metrics,
        }

    finally:
        if close_db:
            db_ctx.__exit__(None, None, None)
