"""
Walk-forward backtesting engine v3.0 — multi-horizon, no data leakage.

Methodology:
  - Walk-forward validation with expanding windows (no peeking at future data)
  - Train on historical window -> test on next N days -> roll forward
  - Computes directional accuracy, Sharpe, max drawdown, alpha vs SPY
  - Multi-horizon: evaluates each forecast horizon independently
  - Stores per-run results in fact_backtest_result
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta
from typing import Optional
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    mean_squared_error, mean_absolute_error, mean_absolute_percentage_error
)
from sqlalchemy.orm import Session
from app.models.schema import DimStock, FactBacktestResult, FactMacroIndicator
from app.forecasting.features import build_feature_matrix, get_feature_names
from app.forecasting.models import StockForecaster, direction_label, MODEL_VERSION
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

MIN_TRAIN_DAYS = 252         # 1 year minimum training window
TEST_DAYS_PER_FOLD = 63      # ~1 quarter of testing per fold
N_FOLDS = 4                  # 4 folds = ~1 year of out-of-sample testing
RISK_FREE_RATE = 0.05        # 5% annual (approximate Fed Funds)


def _compute_strategy_metrics(
    pred_returns: np.ndarray,
    actual_returns: np.ndarray,
    pred_dirs: np.ndarray,
) -> dict:
    """Compute comprehensive strategy performance metrics."""
    actual_dirs = np.array([np.sign(r) if abs(r) > 0.003 else 0 for r in actual_returns])

    # Strategy: go long when pred_direction=1, short when -1, flat when 0
    strategy_daily_returns = np.where(
        pred_dirs == 1, actual_returns,
        np.where(pred_dirs == -1, -actual_returns, 0)
    )
    benchmark_returns = actual_returns

    # Directional accuracy
    dir_acc = float(accuracy_score(actual_dirs, pred_dirs))

    # Long call metrics
    long_mask = pred_dirs == 1
    prec_long = float(precision_score(actual_dirs == 1, long_mask, zero_division=0))
    rec_long = float(recall_score(actual_dirs == 1, long_mask, zero_division=0))
    f1_long = float(f1_score(actual_dirs == 1, long_mask, zero_division=0))

    # Returns performance
    strategy_cum = float(np.prod(1 + strategy_daily_returns) - 1)
    benchmark_cum = float(np.prod(1 + benchmark_returns) - 1)
    n_days = len(strategy_daily_returns)
    ann_factor = 252 / max(n_days, 1)

    strategy_ann = float((1 + strategy_cum) ** ann_factor - 1)
    benchmark_ann = float((1 + benchmark_cum) ** ann_factor - 1)
    alpha = strategy_ann - benchmark_ann

    # Beta
    if len(strategy_daily_returns) > 1:
        cov = np.cov(strategy_daily_returns, benchmark_returns)
        beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] != 0 else 1.0
    else:
        beta = 1.0

    # Sharpe ratio
    rf_daily = RISK_FREE_RATE / 252
    excess_daily = strategy_daily_returns - rf_daily
    sharpe = float(np.mean(excess_daily) / np.std(excess_daily) * np.sqrt(252)) if np.std(excess_daily) > 0 else 0.0

    # Sortino ratio
    downside = excess_daily[excess_daily < 0]
    sortino = float(np.mean(excess_daily) / np.std(downside) * np.sqrt(252)) if len(downside) > 0 and np.std(downside) > 0 else 0.0

    # Max drawdown
    cumulative = np.cumprod(1 + strategy_daily_returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_dd = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0

    # Calmar ratio
    calmar = float(strategy_ann / abs(max_dd)) if max_dd != 0 else 0.0

    # Win rate
    winning_trades = strategy_daily_returns[pred_dirs != 0]
    win_rate = float(np.mean(winning_trades > 0)) if len(winning_trades) > 0 else 0.0
    avg_win = float(np.mean(winning_trades[winning_trades > 0])) if np.any(winning_trades > 0) else 0.0
    avg_loss = float(np.mean(winning_trades[winning_trades < 0])) if np.any(winning_trades < 0) else 0.0
    profit_factor = float(abs(avg_win / avg_loss)) if avg_loss != 0 else 0.0

    # Error metrics
    rmse = float(np.sqrt(mean_squared_error(actual_returns, pred_returns)))
    mae = float(mean_absolute_error(actual_returns, pred_returns))
    mape = float(mean_absolute_percentage_error(actual_returns + 1e-8, pred_returns + 1e-8))

    return {
        "directional_accuracy": dir_acc,
        "precision_long": prec_long,
        "recall_long": rec_long,
        "f1_long": f1_long,
        "strategy_return_total": strategy_cum,
        "strategy_return_annualized": strategy_ann,
        "benchmark_return_total": benchmark_cum,
        "alpha": alpha,
        "beta": beta,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_dd,
        "calmar_ratio": calmar,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "rmse": rmse,
        "mae": mae,
        "mape": mape,
    }


def run_backtest(
    ticker: str,
    db: Session,
    n_folds: int = N_FOLDS,
    test_days: int = TEST_DAYS_PER_FOLD,
    min_train_days: int = MIN_TRAIN_DAYS,
    horizons: list[int] | None = None,
    save_results: bool = True,
    hpo_method: str = "none",
    model_id: int | None = None,
) -> dict:
    """
    Run walk-forward backtest for a ticker across all horizons.

    Args:
        hpo_method: HPO method to use for each fold ("none"/"grid"/"bayesian").
        model_id: If provided, links the backtest to a FactModelRegistry entry.

    Returns comprehensive performance metrics with per-horizon breakdown.
    Top-level metrics use the primary horizon (1d) for backward compatibility.
    """
    horizons = horizons or settings.forecast_horizons
    logger.info("Starting backtest", ticker=ticker, n_folds=n_folds, horizons=horizons)

    # Load full feature matrix with all horizons
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=min_train_days + test_days * n_folds + 100)

    df = build_feature_matrix(ticker, db, start_date, end_date, include_target=True, horizons=horizons)

    if len(df) < min_train_days + test_days:
        raise ValueError(f"Insufficient data for backtest: {len(df)} rows")

    total_days = len(df)

    # Compute fold boundaries
    fold_boundaries = []
    test_end_idx = total_days - 1
    for fold_i in range(n_folds):
        test_start_idx = test_end_idx - test_days + 1
        train_end_idx = test_start_idx - 1
        if train_end_idx < min_train_days:
            break
        fold_boundaries.insert(0, (0, train_end_idx, test_start_idx, test_end_idx))
        test_end_idx = test_start_idx - 1

    if not fold_boundaries:
        raise ValueError("Could not create any backtest folds with the available data")

    # ---- Walk-forward loops (multi-horizon) ----
    # Collect predictions per horizon
    horizon_predictions: dict[int, list] = {h: [] for h in horizons}
    fold_results = []

    for fold_num, (train_start, train_end, test_start, test_end) in enumerate(fold_boundaries):
        train_df = df.iloc[train_start:train_end + 1]
        test_df = df.iloc[test_start:test_end + 1]

        if len(train_df) < min_train_days or len(test_df) == 0:
            continue

        logger.info("Fold training", ticker=ticker, fold=fold_num + 1,
                    train_rows=len(train_df), test_rows=len(test_df))

        model = StockForecaster(ticker)
        model.fit(train_df, horizons=horizons, hpo_method=hpo_method)

        # Predict on test window
        all_preds = model.predict(test_df)

        fold_info = {
            "fold": fold_num + 1,
            "train_start": str(train_df.index[0]),
            "train_end": str(train_df.index[-1]),
            "test_start": str(test_df.index[0]),
            "test_end": str(test_df.index[-1]),
            "n_test_days": len(test_df),
        }

        for h in horizons:
            if h not in all_preds:
                continue
            preds_h = all_preds[h]
            target_col = f"target_return_{h}d"
            if target_col not in test_df.columns:
                continue

            for idx in range(len(test_df)):
                actual_return = float(test_df[target_col].iloc[idx])
                pred_return = float(preds_h["predicted_return"].iloc[idx])
                pred_dir = int(np.sign(pred_return)) if abs(pred_return) > 0.003 else 0

                horizon_predictions[h].append({
                    "date": test_df.index[idx],
                    "pred_return": pred_return,
                    "actual_return": actual_return,
                    "pred_direction": pred_dir,
                    "confidence": float(preds_h["confidence_score"].iloc[idx]),
                })

        fold_results.append(fold_info)

    # ---- Compute per-horizon metrics ----
    horizon_metrics = {}
    for h in horizons:
        preds_h = horizon_predictions[h]
        if not preds_h:
            continue

        pred_rets = np.array([p["pred_return"] for p in preds_h])
        actual_rets = np.array([p["actual_return"] for p in preds_h])
        pred_dirs = np.array([p["pred_direction"] for p in preds_h])

        metrics_h = _compute_strategy_metrics(pred_rets, actual_rets, pred_dirs)
        metrics_h["total_test_days"] = len(preds_h)
        metrics_h["test_start"] = str(preds_h[0]["date"])
        metrics_h["test_end"] = str(preds_h[-1]["date"])
        horizon_metrics[h] = metrics_h

    # ---- Top-level metrics from primary horizon (1d) for backward compat ----
    primary_h = horizons[0] if horizons else 1
    if primary_h not in horizon_metrics:
        raise ValueError("No predictions generated for primary horizon")

    primary = horizon_metrics[primary_h]
    metrics = {
        "ticker": ticker,
        "n_folds": len(fold_results),
        "total_test_days": primary["total_test_days"],
        **{k: v for k, v in primary.items() if k not in ("total_test_days", "test_start", "test_end")},
        "fold_results": fold_results,
        "test_start": primary["test_start"],
        "test_end": primary["test_end"],
        # Multi-horizon breakdown
        "horizons": {f"{h}d": m for h, m in horizon_metrics.items()},
    }

    # Store in DB
    if save_results:
        stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
        backtest = FactBacktestResult(
            run_date=date.today(),
            model_name="stacked_ensemble_v3",
            model_version=MODEL_VERSION,
            tickers_tested=[ticker],
            train_start=date.fromisoformat(fold_results[0]["train_start"]) if fold_results else None,
            train_end=date.fromisoformat(fold_results[-1]["train_end"]) if fold_results else None,
            test_start=date.fromisoformat(metrics["test_start"]),
            test_end=date.fromisoformat(metrics["test_end"]),
            n_folds=len(fold_results),
            directional_accuracy=primary["directional_accuracy"],
            precision_long=primary["precision_long"],
            recall_long=primary["recall_long"],
            f1_long=primary["f1_long"],
            strategy_return_total=primary["strategy_return_total"],
            strategy_return_annualized=primary["strategy_return_annualized"],
            benchmark_return_total=primary["benchmark_return_total"],
            alpha=primary["alpha"],
            beta=primary["beta"],
            sharpe_ratio=primary["sharpe_ratio"],
            sortino_ratio=primary["sortino_ratio"],
            max_drawdown=primary["max_drawdown"],
            calmar_ratio=primary["calmar_ratio"],
            win_rate=primary["win_rate"],
            avg_win=primary["avg_win"],
            avg_loss=primary["avg_loss"],
            profit_factor=primary["profit_factor"],
            rmse=primary["rmse"],
            mae=primary["mae"],
            mape=primary["mape"],
            per_ticker_metrics={
                ticker: {
                    "fold_results": fold_results,
                    "horizons": {f"{h}d": m for h, m in horizon_metrics.items()},
                }
            },
        )
        db.add(backtest)
        db.flush()
        metrics["backtest_id"] = backtest.backtest_id

        # Link backtest to model registry entry if model_id provided
        if model_id is not None:
            try:
                from app.models.schema import FactModelRegistry
                reg_entry = db.query(FactModelRegistry).filter(
                    FactModelRegistry.model_id == model_id
                ).first()
                if reg_entry:
                    reg_entry.backtest_id = backtest.backtest_id
                    reg_entry.backtest_metrics = {
                        "directional_accuracy": primary["directional_accuracy"],
                        "sharpe_ratio": primary["sharpe_ratio"],
                        "alpha": primary["alpha"],
                        "max_drawdown": primary["max_drawdown"],
                        "sortino_ratio": primary["sortino_ratio"],
                        "win_rate": primary["win_rate"],
                        "profit_factor": primary["profit_factor"],
                    }
                    db.flush()
                    logger.info("Backtest linked to model registry",
                                model_id=model_id, backtest_id=backtest.backtest_id)
            except Exception as e:
                logger.warning("Failed to link backtest to registry", error=str(e))

        logger.info("Backtest results saved", ticker=ticker, backtest_id=backtest.backtest_id)

    logger.info("Backtest complete", ticker=ticker,
                directional_accuracy=f"{primary['directional_accuracy']:.1%}",
                sharpe=f"{primary['sharpe_ratio']:.2f}",
                max_drawdown=f"{primary['max_drawdown']:.1%}",
                alpha=f"{primary['alpha']:.1%}",
                horizons=list(horizon_metrics.keys()))

    return metrics
