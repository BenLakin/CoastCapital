"""
train_torch_model.py — Train a SportsBinaryClassifier and save as a candidate.

Artifacts are written to ``MODEL_DIR`` with the naming convention:
  {sport}_{target}_candidate.pt
  {sport}_{target}_candidate_metadata.json

The candidate model is NOT automatically promoted to production.  Use
``promote_model`` (via POST /promote-model) to validate and promote it.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Subset

from features.feature_registry import FEATURE_COLUMNS, TARGET_COLUMNS
from models.dataset import TabularSportsDataset
from models.modeling_data import load_modeling_frame, materialize_features_to_modeling_silver, FEATURE_VERSION
from models.pytorch_model import SportsBinaryClassifier

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/model_artifacts"))


def train_model(
    sport: str,
    target: str = "home_win",
    epochs: int = 5,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    hidden_dim: int = 128,
    dropout: float = 0.1,
) -> dict:
    """Train a binary classifier on the full dataset and save as a candidate.

    Workflow designed for n8n:
      1. n8n calls POST /train-model  →  candidate saved
      2. n8n calls POST /promote-model →  candidate validated & promoted

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, or ``"mlb"``.
    target:
        Target column key — ``"home_win"``, ``"cover_home"``, or ``"total_over"``.
    epochs, batch_size, learning_rate, hidden_dim, dropout:
        Training hyperparameters.

    Returns
    -------
    dict with training results, file paths, and model version string.

    Raises
    ------
    ValueError
        If no data is available or an invalid target is provided.
    """
    if target not in TARGET_COLUMNS:
        raise ValueError(f"Unknown target '{target}'. Choose from: {list(TARGET_COLUMNS)}")

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model_version = f"{sport}_{target}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    logger.info(
        "train_model: sport=%s target=%s version=%s  epochs=%d hidden_dim=%d "
        "dropout=%.3f lr=%.6f bs=%d",
        sport, target, model_version, epochs, hidden_dim, dropout, learning_rate, batch_size,
    )

    materialize_features_to_modeling_silver(sport)
    df = load_modeling_frame(sport)
    if df.empty:
        raise ValueError(f"No modeling data available for {sport}.")

    # --- Temporal holdout: reserve most-recent 20% for evaluation ---
    if "game_date" in df.columns:
        df = df.sort_values("game_date").reset_index(drop=True)
    n = len(df)
    split_idx = int(n * 0.8)
    df_train = df.iloc[:split_idx]
    df_holdout = df.iloc[split_idx:]
    logger.info(
        "train_model: temporal holdout — train=%d rows, holdout=%d rows",
        len(df_train), len(df_holdout),
    )

    target_column = TARGET_COLUMNS[target]
    train_dataset = TabularSportsDataset(df_train, FEATURE_COLUMNS, target_column)
    loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)

    model = SportsBinaryClassifier(input_dim=len(FEATURE_COLUMNS), hidden_dim=hidden_dim, dropout=dropout)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    criterion = nn.BCELoss()

    model.train()
    epoch_losses = []
    for epoch in range(epochs):
        total_loss = 0.0
        for features, labels in loader:
            optimizer.zero_grad()
            preds = model(features)
            loss = criterion(preds, labels)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
        avg = total_loss / max(1, len(loader))
        epoch_losses.append(avg)
        logger.info("train_model: epoch %d/%d — loss=%.6f", epoch + 1, epochs, avg)

    # --- Evaluate on temporal holdout ---
    holdout_metrics = {}
    if len(df_holdout) > 0:
        holdout_dataset = TabularSportsDataset(df_holdout, FEATURE_COLUMNS, target_column)
        holdout_loader = DataLoader(holdout_dataset, batch_size=batch_size, shuffle=False)
        model.eval()
        holdout_preds = []
        holdout_labels = []
        holdout_loss_total = 0.0
        n_batches = 0
        with torch.no_grad():
            for features, labels in holdout_loader:
                preds = model(features)
                loss = criterion(preds, labels)
                holdout_loss_total += float(loss.item())
                n_batches += 1
                holdout_preds.append(preds.view(-1).numpy())
                holdout_labels.append(labels.view(-1).numpy())
        holdout_preds_arr = np.concatenate(holdout_preds)
        holdout_labels_arr = np.concatenate(holdout_labels)
        holdout_loss = holdout_loss_total / max(1, n_batches)
        holdout_accuracy = float(np.mean(
            (holdout_preds_arr >= 0.5) == (holdout_labels_arr >= 0.5)
        ))
        holdout_metrics = {
            "holdout_loss": holdout_loss,
            "holdout_accuracy": holdout_accuracy,
            "holdout_rows": len(df_holdout),
        }
        logger.info(
            "train_model: holdout evaluation — loss=%.6f  accuracy=%.4f  rows=%d",
            holdout_loss, holdout_accuracy, len(df_holdout),
        )

    # --- Save as candidate ---
    model_path = MODEL_DIR / f"{sport}_{target}_candidate.pt"
    metadata_path = MODEL_DIR / f"{sport}_{target}_candidate_metadata.json"

    torch.save(model.state_dict(), model_path)

    metadata = {
        "sport": sport,
        "target": target,
        "model_version": model_version,
        "feature_columns": FEATURE_COLUMNS,
        "feature_version": FEATURE_VERSION,
        "feature_count": len(FEATURE_COLUMNS),
        "train_rows": len(df_train),
        "total_rows": len(df),
        "epoch_losses": epoch_losses,
        "hidden_dim": hidden_dim,
        "dropout": dropout,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "epochs": epochs,
        "trained_at": datetime.now(tz=timezone.utc).isoformat(),
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        **holdout_metrics,
    }
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    logger.info(
        "train_model: candidate saved — version=%s  final_loss=%.6f  train_rows=%d  total_rows=%d",
        model_version, epoch_losses[-1] if epoch_losses else 0, len(df_train), len(df),
    )

    return {
        "sport": sport,
        "target": target,
        "model_version": model_version,
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "hidden_dim": hidden_dim,
        "dropout": dropout,
        "train_rows": len(df_train),
        "total_rows": len(df),
        "feature_version": FEATURE_VERSION,
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "final_loss": epoch_losses[-1] if epoch_losses else None,
        **holdout_metrics,
    }
