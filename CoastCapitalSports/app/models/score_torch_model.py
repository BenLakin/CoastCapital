"""
score_torch_model.py — Score games using the production (or candidate) model.

Loads the **production** model by default.  Falls back to the **candidate**
model when no production artifact exists (e.g. before the first promotion).

Public entry point: ``score_model(sport, target, limit)``
"""

import json
import logging
import os
from pathlib import Path

import torch

from features.feature_registry import FEATURE_COLUMNS
from models.modeling_data import load_modeling_frame, materialize_features_to_modeling_silver
from models.pytorch_model import SportsBinaryClassifier

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/model_artifacts"))


def _resolve_model_paths(sport: str, target: str):
    """Return (model_path, metadata_path, stage) for the best available model.

    Prefers production artifacts; falls back to candidate.

    Returns
    -------
    (Path, Path, str) where the third element is ``"production"`` or ``"candidate"``.

    Raises
    ------
    ValueError
        If neither production nor candidate artifacts exist.
    """
    for stage in ("production", "candidate"):
        model_path = MODEL_DIR / f"{sport}_{target}_{stage}.pt"
        metadata_path = MODEL_DIR / f"{sport}_{target}_{stage}_metadata.json"
        if model_path.exists() and metadata_path.exists():
            return model_path, metadata_path, stage

    raise ValueError(
        f"No model artifacts found for {sport}/{target}. "
        f"Run /train-model first to create a candidate."
    )


def score_model(sport: str, target: str = "home_win", limit: int = 100) -> dict:
    """Score the most recent *limit* games using the active model.

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, or ``"mlb"``.
    target:
        Target column key — ``"home_win"``, ``"cover_home"``, or ``"total_over"``.
    limit:
        Number of most-recent rows to score.

    Returns
    -------
    dict with ``sport``, ``target``, ``model_stage``, ``model_version``,
    ``rows_scored``, and ``predictions`` list.

    Raises
    ------
    ValueError
        If no model artifacts exist or no scoring data is available.
    """
    model_path, metadata_path, stage = _resolve_model_paths(sport, target)
    logger.info(
        "score_model: sport=%s target=%s stage=%s path=%s",
        sport, target, stage, model_path,
    )

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    materialize_features_to_modeling_silver(sport)
    df = load_modeling_frame(sport)
    if df.empty:
        raise ValueError(f"No scoring data available for {sport}.")

    df = df.tail(limit).copy()

    model = SportsBinaryClassifier(
        input_dim=len(FEATURE_COLUMNS),
        hidden_dim=int(metadata.get("hidden_dim", 128)),
        dropout=float(metadata.get("dropout", 0.1)),
    )
    model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
    model.eval()

    x = torch.tensor(df[FEATURE_COLUMNS].values, dtype=torch.float32)
    with torch.no_grad():
        preds = model(x).view(-1).numpy()

    results = []
    for game_id, pred in zip(df["game_id"].tolist(), preds.tolist()):
        results.append({"game_id": game_id, "predicted_probability": float(pred)})

    logger.info("score_model: scored %d rows for %s/%s (stage=%s)", len(results), sport, target, stage)

    return {
        "sport": sport,
        "target": target,
        "model_stage": stage,
        "model_version": metadata.get("model_version", "unknown"),
        "rows_scored": len(results),
        "predictions": results,
        "metadata_path": str(metadata_path),
    }
