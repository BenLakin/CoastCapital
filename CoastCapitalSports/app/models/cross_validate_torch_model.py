"""
cross_validate_torch_model.py — Time-series cross-validation with accuracy and AUC.

Evaluates model hyperparameters without saving artifacts.  Returns per-fold
and averaged loss, accuracy, and AUC so that n8n / tune / promote workflows
can make data-driven decisions about model quality.

Uses expanding-window time-series splits to prevent data leakage: training
data always precedes validation data chronologically.
"""

import logging

import numpy as np
import torch
from sklearn.metrics import roc_auc_score
from torch import nn
from torch.utils.data import DataLoader, Subset

from features.feature_registry import FEATURE_COLUMNS, TARGET_COLUMNS
from models.dataset import TabularSportsDataset
from models.modeling_data import load_modeling_frame, materialize_features_to_modeling_silver, FEATURE_VERSION
from models.pytorch_model import SportsBinaryClassifier

logger = logging.getLogger(__name__)


def timeseries_split_indices(n_rows: int, folds: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate expanding-window time-series splits.

    Returns a list of ``(train_indices, val_indices)`` tuples where training
    data always precedes validation data chronologically.

    Split strategy (for *folds* = 4):
      Fold 1: train=[0 .. n/5),       val=[n/5   .. 2n/5)
      Fold 2: train=[0 .. 2n/5),      val=[2n/5  .. 3n/5)
      Fold 3: train=[0 .. 3n/5),      val=[3n/5  .. 4n/5)
      Fold 4: train=[0 .. 4n/5),      val=[4n/5  .. n)

    The data is divided into ``folds + 1`` equal segments.  Each fold uses all
    segments up to segment *k* for training and segment *k* for validation.
    """
    indices = np.arange(n_rows)
    n_segments = folds + 1
    boundaries = np.linspace(0, n_rows, n_segments + 1, dtype=int)
    splits = []
    for k in range(1, n_segments):
        train_idx = indices[: boundaries[k]]
        val_idx = indices[boundaries[k]: boundaries[k + 1]]
        if len(train_idx) > 0 and len(val_idx) > 0:
            splits.append((train_idx, val_idx))
    return splits


def _evaluate_fold(model, loader, criterion):
    """Run evaluation on a DataLoader and return (loss, accuracy, auc).

    Returns
    -------
    (avg_loss, accuracy, auc) — all floats.  AUC is ``None`` if there is
    only a single class in the fold labels.
    """
    model.eval()
    all_preds = []
    all_labels = []
    total_loss = 0.0
    n_batches = 0

    with torch.no_grad():
        for features, labels in loader:
            preds = model(features)
            loss = criterion(preds, labels)
            total_loss += float(loss.item())
            n_batches += 1
            all_preds.append(preds.view(-1).numpy())
            all_labels.append(labels.view(-1).numpy())

    avg_loss = total_loss / max(1, n_batches)
    preds_arr = np.concatenate(all_preds)
    labels_arr = np.concatenate(all_labels)

    accuracy = float(np.mean((preds_arr >= 0.5) == (labels_arr >= 0.5)))

    try:
        auc = float(roc_auc_score(labels_arr, preds_arr))
    except ValueError:
        # Only one class present in fold — AUC undefined
        auc = None

    return avg_loss, accuracy, auc


def cross_validate_model(
    sport: str,
    target: str = "home_win",
    epochs: int = 5,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    folds: int = 5,
    hidden_dim: int = 128,
    dropout: float = 0.1,
    n_layers: int = 3,
    batch_norm: bool = True,
    weight_decay: float = 0.0,
    *,
    skip_materialize: bool = False,
    preloaded_df=None,
) -> dict:
    """Time-series cross-validate a SportsBinaryClassifier.

    Parameters
    ----------
    sport, target:
        Sport key and target name (see ``TARGET_COLUMNS``).
    epochs, batch_size, learning_rate, hidden_dim, dropout:
        Model / training hyperparameters.
    folds:
        Number of CV folds.
    skip_materialize:
        When ``True``, skip the ``materialize_features_to_modeling_silver``
        call.  Used by the tune loop to avoid redundant work.
    preloaded_df:
        If supplied, use this DataFrame instead of loading from the DB.

    Returns
    -------
    dict with keys ``sport``, ``target``, ``folds``, ``fold_losses``,
    ``fold_accuracies``, ``fold_aucs``, ``average_validation_loss``,
    ``average_accuracy``, ``average_auc``, ``params``, ``train_rows``.
    """
    logger.info(
        "cross_validate_model: sport=%s target=%s folds=%d epochs=%d "
        "hidden_dim=%d dropout=%.3f lr=%.6f bs=%d n_layers=%d batch_norm=%s wd=%.8f",
        sport, target, folds, epochs, hidden_dim, dropout, learning_rate, batch_size,
        n_layers, batch_norm, weight_decay,
    )

    if not skip_materialize:
        materialize_features_to_modeling_silver(sport)

    df = preloaded_df if preloaded_df is not None else load_modeling_frame(sport)
    if df.empty:
        raise ValueError(f"No modeling data available for {sport}.")

    if target not in TARGET_COLUMNS:
        raise ValueError(f"Unknown target '{target}'. Choose from: {list(TARGET_COLUMNS)}")

    target_column = TARGET_COLUMNS[target]
    dataset = TabularSportsDataset(df, FEATURE_COLUMNS, target_column)
    ts_splits = timeseries_split_indices(len(dataset), folds)

    criterion = nn.BCELoss()
    fold_losses = []
    fold_accuracies = []
    fold_aucs = []

    for fold_idx, (train_idx, valid_idx) in enumerate(ts_splits):
        train_loader = DataLoader(Subset(dataset, train_idx.tolist()), batch_size=batch_size, shuffle=True)
        valid_loader = DataLoader(Subset(dataset, valid_idx.tolist()), batch_size=batch_size, shuffle=False)

        model = SportsBinaryClassifier(
            input_dim=len(FEATURE_COLUMNS), hidden_dim=hidden_dim, dropout=dropout,
            n_layers=n_layers, batch_norm=batch_norm,
        )
        optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

        model.train()
        for _ in range(epochs):
            for features, labels in train_loader:
                optimizer.zero_grad()
                preds = model(features)
                loss = criterion(preds, labels)
                loss.backward()
                optimizer.step()

        avg_loss, accuracy, auc = _evaluate_fold(model, valid_loader, criterion)
        fold_losses.append(avg_loss)
        fold_accuracies.append(accuracy)
        fold_aucs.append(auc)
        logger.info(
            "cross_validate_model: fold %d/%d — loss=%.4f  acc=%.4f  auc=%s",
            fold_idx + 1, len(ts_splits), avg_loss, accuracy,
            f"{auc:.4f}" if auc is not None else "N/A",
        )

    valid_aucs = [x for x in fold_aucs if x is not None]
    avg_loss = float(np.mean(fold_losses)) if fold_losses else None
    avg_accuracy = float(np.mean(fold_accuracies)) if fold_accuracies else None
    avg_auc = float(np.mean(valid_aucs)) if valid_aucs else None

    logger.info(
        "cross_validate_model: DONE — avg_loss=%.4f  avg_acc=%.4f  avg_auc=%s",
        avg_loss or 0, avg_accuracy or 0,
        f"{avg_auc:.4f}" if avg_auc is not None else "N/A",
    )

    return {
        "sport": sport,
        "target": target,
        "folds": folds,
        "fold_losses": fold_losses,
        "fold_accuracies": fold_accuracies,
        "fold_aucs": fold_aucs,
        "average_validation_loss": avg_loss,
        "average_accuracy": avg_accuracy,
        "average_auc": avg_auc,
        "train_rows": len(df),
        "feature_version": FEATURE_VERSION,
        "feature_count": len(FEATURE_COLUMNS),
        "input_dim": len(FEATURE_COLUMNS),
        "params": {
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "hidden_dim": hidden_dim,
            "dropout": dropout,
            "n_layers": n_layers,
            "batch_norm": batch_norm,
            "weight_decay": weight_decay,
        },
    }
