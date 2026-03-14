"""
Forecasting models v3.0 — best-in-class multi-horizon prediction.

Architecture:
  - 4-model stacking ensemble per horizon:
      Base: LightGBM, XGBoost, CatBoost, HistGradientBoosting
      Meta: Ridge regression on out-of-fold predictions (TimeSeriesSplit)
  - Conformal prediction intervals (calibrated from OOF residuals)
  - Kelly-inspired opportunity scoring
  - Multi-horizon: 1-day and 5-day forward returns
  - HPO: None (defaults) / Grid (fast ~30s) / Bayesian (Optuna ~3-5 min)
  - Model registry: versioned save/load, champion/challenger promotion
"""
import os
import json
import time as _time
import joblib
import numpy as np
import pandas as pd
from datetime import date, datetime
from typing import Optional
from dataclasses import dataclass, field
from itertools import product as itertools_product

import lightgbm as lgb
import xgboost as xgb
from catboost import CatBoostRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import RobustScaler
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error

from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from app.models.schema import DimStock, FactForecast
from app.models.database import get_db
from app.forecasting.features import build_feature_matrix, get_feature_names
from app.config import settings
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

MODELS_DIR = os.path.join(os.path.dirname(__file__), "../../models_cache")
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_VERSION = "v3.0"
MODEL_NAME = "stacked_ensemble_v3"

N_CV_SPLITS = 5

# ---------------------------------------------------------------------------
# Default hyperparameters
# ---------------------------------------------------------------------------

LGBM_PARAMS = {
    "objective": "regression",
    "metric": "rmse",
    "n_estimators": 500,
    "learning_rate": 0.03,
    "num_leaves": 63,
    "max_depth": 7,
    "min_child_samples": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "n_jobs": -1,
    "verbose": -1,
    "random_state": 42,
}

XGB_PARAMS = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 6,
    "subsample": 0.8,
    "colsample_bytree": 0.7,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "n_jobs": -1,
    "verbosity": 0,
    "random_state": 42,
}

CATBOOST_PARAMS = {
    "iterations": 400,
    "learning_rate": 0.05,
    "depth": 6,
    "l2_leaf_reg": 3.0,
    "random_seed": 42,
    "verbose": 0,
}

HISTGBR_PARAMS = {
    "max_iter": 400,
    "learning_rate": 0.05,
    "max_depth": 6,
    "min_samples_leaf": 20,
    "l2_regularization": 1.0,
    "random_state": 42,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def direction_label(ret: float) -> int:
    """Map return to 3-class direction: 0=down, 1=flat, 2=up."""
    if ret > 0.003:
        return 2
    elif ret < -0.003:
        return 0
    else:
        return 1


def kelly_opportunity_score(
    predicted_return: float,
    confidence: float,
    volatility: float,
    sentiment: float = 0.0,
) -> float:
    """
    Kelly-inspired opportunity score.

    Uses half-Kelly fraction (conservative) blended with sentiment.
    f* = (p * b - q) / b  where b = win/loss ratio, p = win prob.
    We approximate from predicted_return and confidence.
    """
    if volatility <= 0:
        volatility = 0.2

    daily_vol = volatility / np.sqrt(252) if volatility > 0 else 0.015

    # Information ratio component
    ir = predicted_return / daily_vol if daily_vol > 0 else 0

    # Half-Kelly fraction: edge / odds
    edge = abs(predicted_return)
    odds = daily_vol  # approximate loss size
    if odds > 0:
        kelly_f = 0.5 * (edge / odds) * np.sign(predicted_return)
    else:
        kelly_f = 0.0

    # Blend: Kelly (40%) + IR (30%) + confidence (20%) + sentiment (10%)
    score = (kelly_f * 0.4) + (ir * 0.3) + (confidence * 0.2) + (sentiment * 0.1)
    return float(np.clip(score, -3.0, 3.0))


# Keep backward compat alias
opportunity_score = kelly_opportunity_score


# ---------------------------------------------------------------------------
# Grid Search (fast, deterministic ~30s)
# ---------------------------------------------------------------------------

def _grid_search_cv(model_cls, param_grid: dict, X: np.ndarray, y: np.ndarray,
                    fixed_params: dict = None) -> dict:
    """Run grid search with TimeSeriesSplit CV. Returns best params."""
    fixed_params = fixed_params or {}
    keys = list(param_grid.keys())
    combos = list(itertools_product(*param_grid.values()))

    tscv = TimeSeriesSplit(n_splits=3)
    best_score = float("inf")
    best_params = {}

    for combo in combos:
        params = {**fixed_params, **dict(zip(keys, combo))}
        scores = []
        for train_idx, val_idx in tscv.split(X):
            model = model_cls(**params)
            if hasattr(model, "fit"):
                if isinstance(model, lgb.LGBMRegressor):
                    model.fit(X[train_idx], y[train_idx],
                              eval_set=[(X[val_idx], y[val_idx])],
                              callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)])
                elif isinstance(model, xgb.XGBRegressor):
                    model.fit(X[train_idx], y[train_idx], verbose=False)
                elif isinstance(model, CatBoostRegressor):
                    model.fit(X[train_idx], y[train_idx], eval_set=(X[val_idx], y[val_idx]), verbose=0)
                else:
                    model.fit(X[train_idx], y[train_idx])
            pred = model.predict(X[val_idx])
            scores.append(mean_squared_error(y[val_idx], pred, squared=False))

        avg = np.mean(scores)
        if avg < best_score:
            best_score = avg
            best_params = params

    logger.info("Grid search complete", model=model_cls.__name__, best_rmse=f"{best_score:.6f}",
                combos=len(combos))
    return best_params


def _grid_search_lgbm(X: np.ndarray, y: np.ndarray) -> dict:
    """Fast grid search for LightGBM (~8 combos)."""
    grid = {
        "n_estimators": [300, 500],
        "learning_rate": [0.03, 0.05],
        "num_leaves": [31, 63],
    }
    fixed = {"objective": "regression", "metric": "rmse", "max_depth": 7,
             "min_child_samples": 20, "subsample": 0.8, "colsample_bytree": 0.7,
             "reg_alpha": 0.1, "reg_lambda": 0.1, "verbose": -1, "n_jobs": -1, "random_state": 42}
    return _grid_search_cv(lgb.LGBMRegressor, grid, X, y, fixed)


def _grid_search_xgb(X: np.ndarray, y: np.ndarray) -> dict:
    """Fast grid search for XGBoost (~8 combos)."""
    grid = {
        "n_estimators": [200, 400],
        "learning_rate": [0.03, 0.05],
        "max_depth": [5, 7],
    }
    fixed = {"subsample": 0.8, "colsample_bytree": 0.7, "reg_alpha": 0.1,
             "reg_lambda": 1.0, "verbosity": 0, "n_jobs": -1, "random_state": 42}
    return _grid_search_cv(xgb.XGBRegressor, grid, X, y, fixed)


def _grid_search_catboost(X: np.ndarray, y: np.ndarray) -> dict:
    """Fast grid search for CatBoost (~8 combos)."""
    grid = {
        "iterations": [300, 500],
        "learning_rate": [0.03, 0.05],
        "depth": [5, 7],
    }
    fixed = {"l2_leaf_reg": 3.0, "random_seed": 42, "verbose": 0}
    return _grid_search_cv(CatBoostRegressor, grid, X, y, fixed)


def _grid_search_histgbr(X: np.ndarray, y: np.ndarray) -> dict:
    """Fast grid search for HistGradientBoosting (~8 combos)."""
    grid = {
        "max_iter": [300, 500],
        "learning_rate": [0.03, 0.05],
        "max_depth": [5, 7],
    }
    fixed = {"min_samples_leaf": 20, "l2_regularization": 1.0, "random_state": 42}
    return _grid_search_cv(HistGradientBoostingRegressor, grid, X, y, fixed)


# ---------------------------------------------------------------------------
# Bayesian HPO (Optuna, thorough ~3-5 min)
# ---------------------------------------------------------------------------

def _tune_lgbm(X: np.ndarray, y: np.ndarray) -> dict:
    """Bayesian HPO for LightGBM via Optuna."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "objective": "regression",
            "metric": "rmse",
            "n_estimators": trial.suggest_int("n_estimators", 200, 800),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 31, 127),
            "max_depth": trial.suggest_int("max_depth", 4, 10),
            "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            "verbose": -1, "n_jobs": -1, "random_state": 42,
        }
        tscv = TimeSeriesSplit(n_splits=3)
        scores = []
        for train_idx, val_idx in tscv.split(X):
            model = lgb.LGBMRegressor(**params)
            model.fit(
                X[train_idx], y[train_idx],
                eval_set=[(X[val_idx], y[val_idx])],
                callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)],
            )
            pred = model.predict(X[val_idx])
            scores.append(mean_squared_error(y[val_idx], pred, squared=False))
        return np.mean(scores)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=settings.OPTUNA_N_TRIALS, timeout=settings.OPTUNA_TIMEOUT)

    best = {**LGBM_PARAMS, **study.best_params}
    logger.info("Optuna LGBM tuning complete", best_rmse=study.best_value, n_trials=len(study.trials))
    return best


def _tune_xgb(X: np.ndarray, y: np.ndarray) -> dict:
    """Bayesian HPO for XGBoost via Optuna."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 200, 600),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "max_depth": trial.suggest_int("max_depth", 4, 10),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            "verbosity": 0, "n_jobs": -1, "random_state": 42,
        }
        tscv = TimeSeriesSplit(n_splits=3)
        scores = []
        for train_idx, val_idx in tscv.split(X):
            model = xgb.XGBRegressor(**params)
            model.fit(X[train_idx], y[train_idx], verbose=False)
            pred = model.predict(X[val_idx])
            scores.append(mean_squared_error(y[val_idx], pred, squared=False))
        return np.mean(scores)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=settings.OPTUNA_N_TRIALS, timeout=settings.OPTUNA_TIMEOUT)

    best = {**XGB_PARAMS, **study.best_params}
    logger.info("Optuna XGB tuning complete", best_rmse=study.best_value)
    return best


def _tune_catboost(X: np.ndarray, y: np.ndarray) -> dict:
    """Bayesian HPO for CatBoost via Optuna."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "iterations": trial.suggest_int("iterations", 200, 600),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "depth": trial.suggest_int("depth", 4, 8),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 0.1, 10.0, log=True),
            "random_seed": 42,
            "verbose": 0,
        }
        tscv = TimeSeriesSplit(n_splits=3)
        scores = []
        for train_idx, val_idx in tscv.split(X):
            model = CatBoostRegressor(**params)
            model.fit(X[train_idx], y[train_idx], eval_set=(X[val_idx], y[val_idx]), verbose=0)
            pred = model.predict(X[val_idx])
            scores.append(mean_squared_error(y[val_idx], pred, squared=False))
        return np.mean(scores)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=settings.OPTUNA_N_TRIALS, timeout=settings.OPTUNA_TIMEOUT)

    best = {**CATBOOST_PARAMS, **study.best_params}
    logger.info("Optuna CatBoost tuning complete", best_rmse=study.best_value)
    return best


def _tune_histgbr(X: np.ndarray, y: np.ndarray) -> dict:
    """Bayesian HPO for HistGradientBoosting via Optuna."""
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial):
        params = {
            "max_iter": trial.suggest_int("max_iter", 200, 600),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "max_depth": trial.suggest_int("max_depth", 4, 8),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 10, 50),
            "l2_regularization": trial.suggest_float("l2_regularization", 0.1, 10.0, log=True),
            "random_state": 42,
        }
        tscv = TimeSeriesSplit(n_splits=3)
        scores = []
        for train_idx, val_idx in tscv.split(X):
            model = HistGradientBoostingRegressor(**params)
            model.fit(X[train_idx], y[train_idx])
            pred = model.predict(X[val_idx])
            scores.append(mean_squared_error(y[val_idx], pred, squared=False))
        return np.mean(scores)

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=settings.OPTUNA_N_TRIALS, timeout=settings.OPTUNA_TIMEOUT)

    best = {**HISTGBR_PARAMS, **study.best_params}
    logger.info("Optuna HistGBR tuning complete", best_rmse=study.best_value)
    return best


# ---------------------------------------------------------------------------
# Unified HPO dispatcher
# ---------------------------------------------------------------------------

def _resolve_hyperparams(
    X: np.ndarray, y: np.ndarray, hpo_method: str = "none",
) -> tuple[dict, dict, dict, dict]:
    """
    Resolve hyperparameters for all 4 base models based on HPO method.

    Args:
        hpo_method: "none" (defaults), "grid" (fast ~30s), "bayesian" (Optuna ~3-5 min)

    Returns:
        (lgbm_params, xgb_params, catboost_params, histgbr_params)
    """
    if hpo_method == "bayesian":
        logger.info("Running Bayesian HPO (Optuna) for all 4 base models...")
        return (_tune_lgbm(X, y), _tune_xgb(X, y),
                _tune_catboost(X, y), _tune_histgbr(X, y))
    elif hpo_method == "grid":
        logger.info("Running Grid Search for all 4 base models...")
        return (_grid_search_lgbm(X, y), _grid_search_xgb(X, y),
                _grid_search_catboost(X, y), _grid_search_histgbr(X, y))
    else:
        return (LGBM_PARAMS.copy(), XGB_PARAMS.copy(),
                CATBOOST_PARAMS.copy(), HISTGBR_PARAMS.copy())


# ---------------------------------------------------------------------------
# Stacking Ensemble Forecaster v3.0
# ---------------------------------------------------------------------------

class StockForecaster:
    """
    Multi-horizon stacking ensemble forecaster.

    Base models: LightGBM, XGBoost, CatBoost, HistGradientBoosting
    Meta-learner: Ridge regression on OOF predictions (TimeSeriesSplit)
    Conformal prediction intervals from OOF calibration residuals.
    """

    def __init__(self, ticker: str):
        self.ticker = ticker
        self.feature_names: list[str] = []
        self.horizons: list[int] = list(settings.forecast_horizons)
        self.scaler: Optional[RobustScaler] = None
        # Per-horizon models: {horizon: {"base": [models], "meta": Ridge, "calibration_residuals": array}}
        self.models: dict[int, dict] = {}
        self.train_metrics: dict = {}
        self.hyperparams_used: dict = {}  # track params for registry
        self.feature_importance: dict = {}  # top features per horizon

    def fit(
        self,
        df: pd.DataFrame,
        tune_hyperparams: bool = False,
        hpo_method: str = "none",
        horizons: list[int] | None = None,
    ) -> dict:
        """
        Train the stacking ensemble for all horizons.

        Args:
            df: Feature DataFrame with target columns.
            tune_hyperparams: Legacy flag — if True, sets hpo_method="bayesian".
            hpo_method: "none" (defaults), "grid" (fast), "bayesian" (Optuna).
            horizons: Override forecast horizons.

        Uses TimeSeriesSplit for OOF predictions to feed the meta-learner.
        Stores calibration residuals for conformal prediction intervals.
        """
        # Backward compat: tune_hyperparams=True maps to bayesian
        if tune_hyperparams and hpo_method == "none":
            hpo_method = "bayesian"

        horizons = horizons or self.horizons
        self.horizons = horizons
        self.feature_names = get_feature_names(df)

        X = df[self.feature_names].values
        self.scaler = RobustScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Resolve hyperparameters for all 4 base models
        lgbm_params, xgb_params, cat_params, hist_params = _resolve_hyperparams(
            X_scaled, df[f"target_return_{horizons[0]}d"].values if f"target_return_{horizons[0]}d" in df.columns else np.zeros(len(df)),
            hpo_method,
        )

        self.hyperparams_used = {
            "lgbm": lgbm_params,
            "xgb": xgb_params,
            "catboost": cat_params,
            "histgbr": hist_params,
            "hpo_method": hpo_method,
        }

        all_metrics = {}

        for h in horizons:
            target_col = f"target_return_{h}d"
            if target_col not in df.columns:
                logger.warning(f"Target column {target_col} not found, skipping horizon {h}")
                continue

            y = df[target_col].values
            logger.info("Training horizon", ticker=self.ticker, horizon=h, samples=len(y))

            # --- OOF stacking via TimeSeriesSplit ---
            tscv = TimeSeriesSplit(n_splits=N_CV_SPLITS)
            oof_preds = np.zeros((len(X_scaled), 4))  # 4 base models
            oof_mask = np.zeros(len(X_scaled), dtype=bool)

            # Train final base models on full data
            lgbm_model = lgb.LGBMRegressor(**lgbm_params)
            xgb_model = xgb.XGBRegressor(**xgb_params)
            cat_model = CatBoostRegressor(**cat_params)
            hist_model = HistGradientBoostingRegressor(**hist_params)

            base_models = [lgbm_model, xgb_model, cat_model, hist_model]

            # Generate OOF predictions for meta-learner training
            for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X_scaled)):
                X_tr, X_val = X_scaled[train_idx], X_scaled[val_idx]
                y_tr, y_val = y[train_idx], y[val_idx]

                # LightGBM
                fold_lgbm = lgb.LGBMRegressor(**lgbm_params)
                fold_lgbm.fit(X_tr, y_tr,
                              eval_set=[(X_val, y_val)],
                              callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)])
                oof_preds[val_idx, 0] = fold_lgbm.predict(X_val)

                # XGBoost
                fold_xgb = xgb.XGBRegressor(**xgb_params)
                fold_xgb.fit(X_tr, y_tr, verbose=False)
                oof_preds[val_idx, 1] = fold_xgb.predict(X_val)

                # CatBoost
                fold_cat = CatBoostRegressor(**cat_params)
                fold_cat.fit(X_tr, y_tr, eval_set=(X_val, y_val), verbose=0)
                oof_preds[val_idx, 2] = fold_cat.predict(X_val)

                # HistGBR
                fold_hist = HistGradientBoostingRegressor(**hist_params)
                fold_hist.fit(X_tr, y_tr)
                oof_preds[val_idx, 3] = fold_hist.predict(X_val)

                oof_mask[val_idx] = True

            # Train meta-learner on OOF predictions
            oof_X = oof_preds[oof_mask]
            oof_y = y[oof_mask]

            meta_model = Ridge(alpha=1.0)
            meta_model.fit(oof_X, oof_y)

            # Conformal calibration residuals from OOF
            meta_pred = meta_model.predict(oof_X)
            calibration_residuals = np.abs(oof_y - meta_pred)

            # Train final base models on ALL data
            lgbm_model.fit(X_scaled, y,
                           eval_set=[(X_scaled, y)],
                           callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(-1)])
            xgb_model.fit(X_scaled, y, verbose=False)
            cat_model.fit(X_scaled, y, verbose=0)
            hist_model.fit(X_scaled, y)

            # Store
            self.models[h] = {
                "base": [lgbm_model, xgb_model, cat_model, hist_model],
                "meta": meta_model,
                "calibration_residuals": calibration_residuals,
            }

            # Extract aggregated feature importance (top 20)
            feat_imp = lgbm_model.feature_importances_.copy()
            # Add XGBoost importance (normalized to same scale)
            xgb_imp = xgb_model.feature_importances_
            if xgb_imp.sum() > 0:
                feat_imp += xgb_imp / xgb_imp.max() * feat_imp.max()
            top_idx = np.argsort(feat_imp)[-20:][::-1]
            self.feature_importance[f"{h}d"] = {
                self.feature_names[j]: round(float(feat_imp[j]), 2) for j in top_idx
            }

            # Metrics
            final_pred = self._stacked_predict_horizon(X_scaled, h)
            rmse = float(np.sqrt(mean_squared_error(y, final_pred)))
            dir_acc = float(np.mean(np.sign(final_pred) == np.sign(y)))
            oof_rmse = float(np.sqrt(mean_squared_error(oof_y, meta_pred)))

            all_metrics[f"{h}d"] = {
                "train_rmse": rmse,
                "oof_rmse": oof_rmse,
                "train_directional_accuracy": dir_acc,
                "n_samples": len(X_scaled),
                "n_features": len(self.feature_names),
                "meta_weights": meta_model.coef_.tolist(),
            }

            logger.info("Horizon trained", ticker=self.ticker, horizon=h,
                         oof_rmse=f"{oof_rmse:.6f}", dir_acc=f"{dir_acc:.1%}")

        self.train_metrics = all_metrics
        return all_metrics

    def _stacked_predict_horizon(self, X_scaled: np.ndarray, horizon: int) -> np.ndarray:
        """Get stacked ensemble prediction for a single horizon."""
        if horizon not in self.models:
            raise ValueError(f"No model trained for horizon {horizon}")

        m = self.models[horizon]
        base_preds = np.column_stack([
            model.predict(X_scaled) for model in m["base"]
        ])
        return m["meta"].predict(base_preds)

    def predict(self, df: pd.DataFrame) -> dict[int, pd.DataFrame]:
        """
        Generate predictions for all horizons.

        Returns dict[horizon -> DataFrame] with columns:
          predicted_return, predicted_direction, confidence_score,
          opportunity_score, lower_bound_95, upper_bound_95,
          lower_bound_80, upper_bound_80, top_features
        """
        if self.scaler is None or not self.models:
            raise RuntimeError("Model not trained. Call fit() first.")

        X = df[self.feature_names].reindex(columns=self.feature_names, fill_value=0).values
        X_scaled = self.scaler.transform(X)

        results = {}

        for h in self.horizons:
            if h not in self.models:
                continue

            pred_returns = self._stacked_predict_horizon(X_scaled, h)
            cal_residuals = self.models[h]["calibration_residuals"]

            # Conformal prediction intervals
            q95 = float(np.quantile(cal_residuals, 0.95))
            q80 = float(np.quantile(cal_residuals, 0.80))

            # Direction classification from base LightGBM feature importance
            lgbm_model = self.models[h]["base"][0]
            feat_imp = lgbm_model.feature_importances_
            top_idx = np.argsort(feat_imp)[-5:][::-1]

            rows = []
            for i in range(len(df)):
                pr = float(pred_returns[i])

                # Direction
                direction = int(np.sign(pr)) if abs(pr) > 0.003 else 0

                # Confidence: use base model agreement
                base_preds_i = np.array([
                    float(m.predict(X_scaled[i:i+1])[0])
                    for m in self.models[h]["base"]
                ])
                agreement = np.mean(np.sign(base_preds_i) == np.sign(pr))
                # Scale confidence: agreement 0.5-1.0 maps to 0.3-0.95
                conf = float(np.clip(0.3 + (agreement - 0.5) * 1.3, 0.2, 0.95))

                # Conformal intervals
                lower_95 = pr - q95
                upper_95 = pr + q95
                lower_80 = pr - q80
                upper_80 = pr + q80

                # Top features
                top_feats = {self.feature_names[j]: float(feat_imp[j]) for j in top_idx}

                # Sentiment for opportunity score
                sentiment = float(df.get("sentiment_score_wavg", pd.Series([0])).iloc[min(i, len(df)-1)] or 0)

                vol_est = float(df["volatility_5d"].iloc[i]) if "volatility_5d" in df.columns else 0.2
                opp = kelly_opportunity_score(pr, conf, vol_est, sentiment)

                rows.append({
                    "predicted_return": pr,
                    "predicted_direction": direction,
                    "confidence_score": conf,
                    "opportunity_score": opp,
                    "lower_bound_95": lower_95,
                    "upper_bound_95": upper_95,
                    "lower_bound_80": lower_80,
                    "upper_bound_80": upper_80,
                    "top_features": top_feats,
                })

            results[h] = pd.DataFrame(rows, index=df.index)

        return results

    def predict_1d(self, df: pd.DataFrame) -> pd.DataFrame:
        """Backward-compatible single-horizon predict (1-day)."""
        all_preds = self.predict(df)
        primary_h = self.horizons[0] if self.horizons else 1
        if primary_h in all_preds:
            return all_preds[primary_h]
        return all_preds[list(all_preds.keys())[0]]

    # ── Versioned save/load ────────────────────────────────────────────────

    def save(self, sequence_num: int | None = None) -> str:
        """
        Persist the model to disk.

        If sequence_num is given, saves as {ticker}_v3.0_seq{N}.pkl (versioned).
        Otherwise, saves as {ticker}_v3.0.pkl (backward-compat overwrite).
        """
        if sequence_num is not None:
            filename = f"{self.ticker}_{MODEL_VERSION}_seq{sequence_num}.pkl"
        else:
            filename = f"{self.ticker}_{MODEL_VERSION}.pkl"

        path = os.path.join(MODELS_DIR, filename)
        joblib.dump({
            "ticker": self.ticker,
            "feature_names": self.feature_names,
            "horizons": self.horizons,
            "models": self.models,
            "scaler": self.scaler,
            "train_metrics": self.train_metrics,
            "hyperparams_used": self.hyperparams_used,
            "feature_importance": self.feature_importance,
            "model_version": MODEL_VERSION,
            "saved_at": datetime.utcnow().isoformat(),
        }, path)
        logger.info("Model saved", ticker=self.ticker, path=path)
        return path

    @classmethod
    def load(cls, ticker: str, model_path: str | None = None, db: Session | None = None) -> "StockForecaster":
        """
        Load a persisted model.

        Priority:
          1. model_path — load exact file
          2. db — look up champion from FactModelRegistry
          3. fallback — {ticker}_v3.0.pkl (backward compat)
        """
        path = None

        if model_path:
            # Absolute or relative path
            if os.path.isabs(model_path):
                path = model_path
            else:
                path = os.path.join(MODELS_DIR, model_path)
        elif db is not None:
            # Look up champion from registry
            try:
                from app.models.schema import FactModelRegistry
                champion = (
                    db.query(FactModelRegistry)
                    .filter(FactModelRegistry.ticker == ticker, FactModelRegistry.status == "champion")
                    .first()
                )
                if champion and champion.model_path:
                    candidate_path = champion.model_path
                    if not os.path.isabs(candidate_path):
                        candidate_path = os.path.join(MODELS_DIR, candidate_path)
                    if os.path.exists(candidate_path):
                        path = candidate_path
            except Exception:
                pass  # registry table may not exist yet

        if path is None:
            # Fallback to unversioned path
            path = os.path.join(MODELS_DIR, f"{ticker}_{MODEL_VERSION}.pkl")

        if not os.path.exists(path):
            raise FileNotFoundError(f"No model found for {ticker} at {path}")

        data = joblib.load(path)
        obj = cls(ticker)
        obj.feature_names = data["feature_names"]
        obj.horizons = data.get("horizons", [1])
        obj.models = data["models"]
        obj.scaler = data["scaler"]
        obj.train_metrics = data["train_metrics"]
        obj.hyperparams_used = data.get("hyperparams_used", {})
        obj.feature_importance = data.get("feature_importance", {})
        return obj


# ---------------------------------------------------------------------------
# Train & forecast pipelines
# ---------------------------------------------------------------------------

def train_model(
    ticker: str,
    db: Session,
    lookback_days: int = None,
    tune_hyperparams: bool = False,
    hpo_method: str = "none",
    notes: str = "",
) -> dict:
    """
    Train a multi-horizon forecasting model for a ticker.

    Creates a FactModelRegistry entry with status="candidate".
    Returns model_id + metrics.
    """
    # Backward compat
    if tune_hyperparams and hpo_method == "none":
        hpo_method = "bayesian"

    lookback_days = lookback_days or settings.DEFAULT_LOOKBACK_DAYS
    end_date = date.today()
    start_date = end_date - pd.Timedelta(days=lookback_days)
    start_date = start_date.date() if hasattr(start_date, 'date') else start_date

    df = build_feature_matrix(ticker, db, start_date, end_date, include_target=True)

    if len(df) < settings.MIN_TRAINING_DAYS:
        raise ValueError(f"Insufficient data for {ticker}: {len(df)} rows (need {settings.MIN_TRAINING_DAYS})")

    # Get next sequence number
    seq_num = _next_sequence_num(ticker, db)

    t0 = _time.time()
    model = StockForecaster(ticker)
    metrics = model.fit(df, hpo_method=hpo_method)
    training_duration = _time.time() - t0

    # Save versioned + unversioned (backward compat)
    versioned_path = model.save(sequence_num=seq_num)
    model.save()  # also save unversioned for backward compat

    # Register in model registry
    model_id = _register_model(
        ticker=ticker,
        db=db,
        sequence_num=seq_num,
        hpo_method=hpo_method,
        training_duration=training_duration,
        train_rows=len(df),
        n_features=len(model.feature_names),
        horizons=model.horizons,
        hyperparams=model.hyperparams_used,
        train_metrics=metrics,
        feature_importance=model.feature_importance,
        model_path=os.path.basename(versioned_path),
        notes=notes,
    )

    return {
        "ticker": ticker,
        "model_id": model_id,
        "model_version": MODEL_VERSION,
        "sequence_num": seq_num,
        "train_rows": len(df),
        "training_duration_sec": round(training_duration, 1),
        "hpo_method": hpo_method,
        "metrics": metrics,
    }


def _next_sequence_num(ticker: str, db: Session) -> int:
    """Get the next sequence number for a ticker in the model registry."""
    try:
        from app.models.schema import FactModelRegistry
        max_seq = (
            db.query(sql_func.max(FactModelRegistry.sequence_num))
            .filter(FactModelRegistry.ticker == ticker)
            .scalar()
        )
        return (max_seq or 0) + 1
    except Exception:
        return 1


def _register_model(
    ticker: str,
    db: Session,
    sequence_num: int,
    hpo_method: str,
    training_duration: float,
    train_rows: int,
    n_features: int,
    horizons: list[int],
    hyperparams: dict,
    train_metrics: dict,
    feature_importance: dict,
    model_path: str,
    notes: str = "",
) -> int | None:
    """Insert a FactModelRegistry row. Returns model_id."""
    try:
        from app.models.schema import FactModelRegistry

        stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()

        entry = FactModelRegistry(
            stock_id=stock.stock_id if stock else None,
            ticker=ticker,
            model_version=MODEL_VERSION,
            sequence_num=sequence_num,
            status="candidate",
            training_duration_sec=round(training_duration, 1),
            train_rows=train_rows,
            n_features=n_features,
            horizons=horizons,
            hpo_method=hpo_method,
            hyperparams=_make_json_safe(hyperparams),
            train_metrics=_make_json_safe(train_metrics),
            feature_importance=_make_json_safe(feature_importance),
            model_path=model_path,
            notes=notes,
        )
        db.add(entry)
        db.flush()
        logger.info("Model registered", ticker=ticker, model_id=entry.model_id,
                    sequence_num=sequence_num, status="candidate")
        return entry.model_id
    except Exception as e:
        logger.warning("Model registry insert failed (table may not exist yet)", error=str(e))
        return None


def _make_json_safe(obj):
    """Convert numpy types to native Python for JSON serialization."""
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_safe(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def generate_forecast(
    ticker: str,
    forecast_date: date,
    target_date: date,
    db: Session,
    horizon: int = 1,
) -> dict:
    """
    Generate a forecast for a ticker at a specific horizon.
    Stores result in fact_forecast and returns forecast dict.
    Uses registry-aware load: picks champion model when available.
    """
    stock = db.query(DimStock).filter(DimStock.ticker == ticker).first()
    if not stock:
        raise ValueError(f"Ticker {ticker} not found")

    try:
        model = StockForecaster.load(ticker, db=db)
    except FileNotFoundError:
        logger.info("No saved model, training fresh", ticker=ticker)
        train_model(ticker, db)
        model = StockForecaster.load(ticker, db=db)

    # Build features for forecast_date
    start = forecast_date - pd.Timedelta(days=300)
    start = start.date() if hasattr(start, 'date') else start
    df = build_feature_matrix(ticker, db, start, forecast_date, include_target=False)

    if df.empty:
        raise ValueError(f"No feature data for {ticker} on {forecast_date}")

    df_last = df.iloc[[-1]]
    all_preds = model.predict(df_last)

    # Use the requested horizon, fallback to first available
    if horizon in all_preds:
        preds = all_preds[horizon]
    else:
        horizon = list(all_preds.keys())[0]
        preds = all_preds[horizon]

    if preds.empty:
        raise ValueError("Prediction failed")

    pred_row = preds.iloc[0]

    # Persist forecast
    existing = db.query(FactForecast).filter(
        FactForecast.stock_id == stock.stock_id,
        FactForecast.forecast_date == forecast_date,
        FactForecast.target_date == target_date,
        FactForecast.model_name == MODEL_NAME,
        FactForecast.forecast_horizon == horizon,
    ).first()

    forecast_data = dict(
        stock_id=stock.stock_id,
        ticker=ticker,
        forecast_date=forecast_date,
        target_date=target_date,
        forecast_horizon=horizon,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        predicted_return=pred_row["predicted_return"],
        predicted_direction=pred_row["predicted_direction"],
        confidence_score=pred_row["confidence_score"],
        opportunity_score=pred_row["opportunity_score"],
        lower_bound_95=pred_row["lower_bound_95"],
        upper_bound_95=pred_row["upper_bound_95"],
        lower_bound_80=pred_row["lower_bound_80"],
        upper_bound_80=pred_row["upper_bound_80"],
        top_features=pred_row["top_features"],
    )

    if existing:
        for k, v in forecast_data.items():
            setattr(existing, k, v)
    else:
        db.add(FactForecast(**forecast_data))

    db.flush()

    result = {
        "ticker": ticker,
        "company_name": stock.company_name,
        "forecast_date": str(forecast_date),
        "target_date": str(target_date),
        "forecast_horizon": horizon,
        **{k: v for k, v in forecast_data.items() if k not in ("stock_id",)},
    }

    logger.info("Forecast generated", ticker=ticker, horizon=horizon,
                return_pct=f"{pred_row['predicted_return']*100:.2f}%",
                direction=pred_row["predicted_direction"],
                opportunity=pred_row["opportunity_score"])

    return result


def generate_multi_horizon_forecast(
    ticker: str,
    forecast_date: date,
    db: Session,
) -> dict:
    """
    Generate forecasts for ALL horizons (1d + 5d).
    Returns combined result dict with per-horizon data.
    """
    from app.pipelines.daily_process import get_next_trading_day

    results = {}
    for h in settings.forecast_horizons:
        # Target date is h trading days ahead
        target = forecast_date
        for _ in range(h):
            target = get_next_trading_day(target)

        try:
            result = generate_forecast(ticker, forecast_date, target, db, horizon=h)
            results[f"{h}d"] = result
        except Exception as e:
            logger.error("Horizon forecast failed", ticker=ticker, horizon=h, error=str(e))
            results[f"{h}d"] = {"error": str(e)}

    return {
        "ticker": ticker,
        "forecast_date": str(forecast_date),
        "horizons": results,
    }
