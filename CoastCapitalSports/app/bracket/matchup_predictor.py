"""
matchup_predictor.py — Predict win probabilities for hypothetical matchups
using the trained ncaa_mbb production model.
"""

import json
import logging
import os
from pathlib import Path

import numpy as np
import torch

from features.feature_registry import FEATURE_COLUMNS
from models.pytorch_model import SportsBinaryClassifier

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/model_artifacts"))


def load_ncaa_model() -> tuple:
    """Load the production ncaa_mbb_home_win model.

    Returns
    -------
    (model, metadata) where model is a loaded SportsBinaryClassifier
    in eval mode and metadata is the model's metadata dict.

    Raises
    ------
    ValueError
        If no production or candidate model exists.
    """
    for stage in ("production", "candidate"):
        model_path = MODEL_DIR / f"ncaa_mbb_home_win_{stage}.pt"
        metadata_path = MODEL_DIR / f"ncaa_mbb_home_win_{stage}_metadata.json"
        if model_path.exists() and metadata_path.exists():
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            model = SportsBinaryClassifier(
                input_dim=len(FEATURE_COLUMNS),
                hidden_dim=int(metadata.get("hidden_dim", 128)),
                dropout=float(metadata.get("dropout", 0.1)),
            )
            model.load_state_dict(
                torch.load(model_path, map_location="cpu", weights_only=True)
            )
            model.eval()
            logger.info(
                "load_ncaa_model: loaded %s model version=%s",
                stage, metadata.get("model_version", "unknown"),
            )
            return model, metadata

    raise ValueError(
        "No ncaa_mbb_home_win model found. "
        "Train and promote one first via /train-model and /promote-model."
    )


def predict_matchup(model: torch.nn.Module, feature_vector: np.ndarray) -> float:
    """Predict win probability for Team A (home position) given a feature vector.

    Parameters
    ----------
    model:
        Loaded SportsBinaryClassifier in eval mode.
    feature_vector:
        numpy array of shape (137,) matching FEATURE_COLUMNS.

    Returns
    -------
    float in [0, 1] — probability that Team A wins.
    """
    x = torch.tensor(feature_vector, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        prob = model(x).item()
    return prob


def predict_matchup_symmetric(
    model: torch.nn.Module,
    team_a: str,
    team_b: str,
    team_profiles: dict,
    seed_a: int,
    seed_b: int,
    team_to_id: dict,
    round_name: str = "",
) -> float:
    """Predict win probability with symmetry correction.

    Since tournament games are on neutral courts, we average the model's
    predictions when Team A is in the home position and when Team B is in the
    home position.  This removes any residual home-field bias.

    Returns
    -------
    float — probability that Team A wins (averaged over both orderings).
    """
    from bracket.team_profile import build_matchup_feature_vector

    # A as home, B as away
    vec_ab = build_matchup_feature_vector(
        team_a, team_b, team_profiles, seed_a, seed_b, team_to_id, round_name,
    )
    prob_ab = predict_matchup(model, vec_ab)

    # B as home, A as away (swap)
    vec_ba = build_matchup_feature_vector(
        team_b, team_a, team_profiles, seed_b, seed_a, team_to_id, round_name,
    )
    prob_ba = predict_matchup(model, vec_ba)

    # Average: P(A wins) = mean of (prob_A_home, 1 - prob_B_home)
    return (prob_ab + (1.0 - prob_ba)) / 2.0
