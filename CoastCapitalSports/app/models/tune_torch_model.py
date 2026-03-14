"""
tune_torch_model.py — Grid search over hyperparameters via cross-validation.

Materialises features once, then runs cross-validation for each combination
in the search space.  The best result (lowest avg validation loss) is
returned at the top of the leaderboard.

Public entry point: ``tune_model(sport, target, folds, search_space)``
"""

import logging
from itertools import product

from models.cross_validate_torch_model import cross_validate_model
from models.modeling_data import load_modeling_frame, materialize_features_to_modeling_silver

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_SPACE = {
    "learning_rate": [0.001, 0.0005],
    "batch_size": [32, 64],
    "hidden_dim": [64, 128],
    "dropout": [0.1, 0.2],
    "epochs": [3],
}


def normalize_search_space(search_space):
    """Return *search_space* with defaults applied for missing keys."""
    return search_space or DEFAULT_SEARCH_SPACE


def tune_model(
    sport: str,
    target: str = "home_win",
    folds: int = 3,
    search_space: dict | None = None,
) -> dict:
    """Run grid search over hyperparameters and return a ranked leaderboard.

    Features are materialised and loaded once; every combination in the
    search space is cross-validated using the same in-memory DataFrame.

    Parameters
    ----------
    sport:
        Sport key (``"nfl"``, ``"ncaa_mbb"``, ``"mlb"``).
    target:
        Target column key.
    folds:
        Number of CV folds per combination.
    search_space:
        Dict mapping hyperparameter names to lists of values to try.
        Falls back to ``DEFAULT_SEARCH_SPACE`` if ``None``.

    Returns
    -------
    dict with ``best_result`` (the best combo) and ``leaderboard`` (all
    combos sorted by ascending validation loss).
    """
    space = normalize_search_space(search_space)
    keys = list(space.keys())
    combinations = list(product(*[space[k] for k in keys]))

    logger.info(
        "tune_model: sport=%s target=%s folds=%d combos=%d",
        sport, target, folds, len(combinations),
    )

    # Materialise once and preload the DataFrame
    materialize_features_to_modeling_silver(sport)
    df = load_modeling_frame(sport)

    leaderboard = []

    for idx, combo in enumerate(combinations, 1):
        params = dict(zip(keys, combo))
        logger.info("tune_model: combo %d/%d — %s", idx, len(combinations), params)
        try:
            result = cross_validate_model(
                sport=sport,
                target=target,
                folds=folds,
                epochs=int(params.get("epochs", 3)),
                batch_size=int(params.get("batch_size", 32)),
                learning_rate=float(params.get("learning_rate", 0.001)),
                hidden_dim=int(params.get("hidden_dim", 128)),
                dropout=float(params.get("dropout", 0.1)),
                skip_materialize=True,
                preloaded_df=df,
            )
            leaderboard.append({
                "params": params,
                "average_validation_loss": result["average_validation_loss"],
                "average_accuracy": result["average_accuracy"],
                "average_auc": result["average_auc"],
                "fold_losses": result["fold_losses"],
                "fold_accuracies": result["fold_accuracies"],
                "fold_aucs": result["fold_aucs"],
            })
        except Exception as exc:
            logger.error("tune_model: combo %s failed — %s", params, exc, exc_info=True)
            leaderboard.append({
                "params": params,
                "average_validation_loss": None,
                "average_accuracy": None,
                "average_auc": None,
                "error": str(exc),
            })

    leaderboard = sorted(
        leaderboard,
        key=lambda x: x["average_validation_loss"] if x["average_validation_loss"] is not None else 1e9,
    )

    best = leaderboard[0] if leaderboard else None
    logger.info(
        "tune_model: DONE — best_loss=%s best_acc=%s best_auc=%s params=%s",
        f"{best['average_validation_loss']:.4f}" if best and best["average_validation_loss"] else "N/A",
        f"{best['average_accuracy']:.4f}" if best and best.get("average_accuracy") else "N/A",
        f"{best['average_auc']:.4f}" if best and best.get("average_auc") else "N/A",
        best["params"] if best else "N/A",
    )

    return {
        "sport": sport,
        "target": target,
        "folds": folds,
        "best_result": best,
        "leaderboard": leaderboard,
    }
