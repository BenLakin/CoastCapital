"""
tune_torch_model.py — Optuna Bayesian hyperparameter optimization.

Uses Optuna's TPE sampler with median pruning to efficiently search the
hyperparameter space via cross-validation.  Materialises features once,
then evaluates each trial using the same in-memory DataFrame.

Public entry point: ``tune_model(sport, target, folds, n_trials, timeout)``
"""

import logging
import os

import optuna

from models.cross_validate_torch_model import cross_validate_model
from models.modeling_data import load_modeling_frame, materialize_features_to_modeling_silver

logger = logging.getLogger(__name__)

OPTUNA_N_TRIALS = int(os.getenv("SPORTS_OPTUNA_N_TRIALS", "50"))
OPTUNA_TIMEOUT = int(os.getenv("SPORTS_OPTUNA_TIMEOUT", "600"))


def tune_model(
    sport: str,
    target: str = "home_win",
    folds: int = 3,
    n_trials: int | None = None,
    timeout: int | None = None,
) -> dict:
    """Run Optuna Bayesian HPO and return a ranked leaderboard.

    Features are materialised and loaded once; every trial samples from the
    hyperparameter space and is cross-validated using the same DataFrame.

    Parameters
    ----------
    sport:
        Sport key (``"nfl"``, ``"ncaa_mbb"``, ``"mlb"``).
    target:
        Target column key.
    folds:
        Number of CV folds per trial.
    n_trials:
        Maximum number of Optuna trials.  Defaults to ``OPTUNA_N_TRIALS``.
    timeout:
        Maximum wall-clock seconds for the study.  Defaults to ``OPTUNA_TIMEOUT``.

    Returns
    -------
    dict with ``best_result`` (the best trial) and ``leaderboard`` (top-20
    trials sorted by descending accuracy).
    """
    n_trials = n_trials or OPTUNA_N_TRIALS
    timeout = timeout or OPTUNA_TIMEOUT

    logger.info(
        "tune_model: sport=%s target=%s folds=%d n_trials=%d timeout=%ds",
        sport, target, folds, n_trials, timeout,
    )

    # Materialise once and preload the DataFrame
    materialize_features_to_modeling_silver(sport)
    df = load_modeling_frame(sport)

    all_results: list[dict] = []

    def objective(trial: optuna.Trial) -> float:
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 1e-4, 1e-2, log=True),
            "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128]),
            "hidden_dim": trial.suggest_categorical("hidden_dim", [64, 128, 256]),
            "n_layers": trial.suggest_int("n_layers", 2, 4),
            "dropout": trial.suggest_float("dropout", 0.05, 0.4),
            "batch_norm": trial.suggest_categorical("batch_norm", [True, False]),
            "weight_decay": trial.suggest_float("weight_decay", 1e-6, 1e-2, log=True),
            "epochs": trial.suggest_int("epochs", 5, 20),
        }

        logger.info("tune_model: trial %d — %s", trial.number, params)

        try:
            result = cross_validate_model(
                sport=sport,
                target=target,
                folds=folds,
                epochs=params["epochs"],
                batch_size=params["batch_size"],
                learning_rate=params["learning_rate"],
                hidden_dim=params["hidden_dim"],
                dropout=params["dropout"],
                n_layers=params["n_layers"],
                batch_norm=params["batch_norm"],
                weight_decay=params["weight_decay"],
                skip_materialize=True,
                preloaded_df=df,
            )
            accuracy = result["average_accuracy"] or 0.0
            all_results.append({
                "params": params,
                "average_validation_loss": result["average_validation_loss"],
                "average_accuracy": result["average_accuracy"],
                "average_auc": result["average_auc"],
                "fold_losses": result["fold_losses"],
                "fold_accuracies": result["fold_accuracies"],
                "fold_aucs": result["fold_aucs"],
            })
            return accuracy
        except Exception as exc:
            logger.error("tune_model: trial %d failed — %s", trial.number, exc, exc_info=True)
            all_results.append({
                "params": params,
                "average_validation_loss": None,
                "average_accuracy": None,
                "average_auc": None,
                "error": str(exc),
            })
            return 0.0

    # Suppress Optuna's verbose trial logging
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        pruner=optuna.pruners.MedianPruner(n_startup_trials=5),
    )
    study.optimize(objective, n_trials=n_trials, timeout=timeout)

    # Build leaderboard sorted by accuracy (descending)
    leaderboard = sorted(
        [r for r in all_results if r.get("average_accuracy") is not None],
        key=lambda x: x["average_accuracy"],
        reverse=True,
    )
    # Include failed trials at the end
    failed = [r for r in all_results if r.get("average_accuracy") is None]
    leaderboard.extend(failed)

    # Cap leaderboard at top 20
    leaderboard = leaderboard[:20]

    best = leaderboard[0] if leaderboard and leaderboard[0].get("average_accuracy") is not None else None

    logger.info(
        "tune_model: DONE — %d trials completed  best_acc=%s best_auc=%s params=%s",
        len(study.trials),
        f"{best['average_accuracy']:.4f}" if best and best.get("average_accuracy") else "N/A",
        f"{best['average_auc']:.4f}" if best and best.get("average_auc") else "N/A",
        best["params"] if best else "N/A",
    )

    return {
        "sport": sport,
        "target": target,
        "folds": folds,
        "n_trials": len(study.trials),
        "timeout": timeout,
        "best_result": best,
        "leaderboard": leaderboard,
    }
