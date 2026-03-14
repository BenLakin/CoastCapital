"""
promote_model.py — Validate, promote, and log models to the registry.

Provides two public functions:

- ``promote_model(sport, target, cv_folds)``
    Cross-validates the current candidate, logs it to the DB registry,
    copies candidate artifacts to production, and retires the previous
    production model.

- ``refit_model(sport, target, folds, ...)``
    End-to-end pipeline: train a candidate, cross-validate it, log it,
    and promote it.  Designed for a single n8n "refit" job.

- ``get_model_status(sport, target)``
    Returns the current production model details from the DB registry.
"""

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from database import get_connection
from models.cross_validate_torch_model import cross_validate_model
from models.modeling_data import FEATURE_VERSION
from models.train_torch_model import train_model

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/model_artifacts"))


# ---------------------------------------------------------------------------
# DB registry helpers
# ---------------------------------------------------------------------------

def _log_to_registry(
    sport: str,
    target: str,
    model_version: str,
    status: str,
    params: dict,
    cv_result: dict | None,
    train_result: dict | None,
) -> int:
    """Insert a row into ``research_gold.fact_model_registry``.

    Returns the inserted row id.
    """
    conn = get_connection("modeling_internal")
    cursor = conn.cursor()

    cv_folds = cv_result.get("folds") if cv_result else None
    cv_avg_loss = cv_result.get("average_validation_loss") if cv_result else None
    cv_avg_accuracy = cv_result.get("average_accuracy") if cv_result else None
    cv_avg_auc = cv_result.get("average_auc") if cv_result else None
    cv_fold_losses = json.dumps(cv_result.get("fold_losses")) if cv_result else None
    cv_fold_accuracies = json.dumps(cv_result.get("fold_accuracies")) if cv_result else None
    cv_fold_aucs = json.dumps(cv_result.get("fold_aucs")) if cv_result else None

    train_rows = train_result.get("train_rows") if train_result else (cv_result.get("train_rows") if cv_result else None)
    train_final_loss = train_result.get("final_loss") if train_result else None
    model_path = train_result.get("model_path") if train_result else None
    metadata_path = train_result.get("metadata_path") if train_result else None

    promoted_at = datetime.now(tz=timezone.utc) if status == "production" else None

    cursor.execute(
        """
        INSERT INTO fact_model_registry (
            sport, target, model_version, status,
            hidden_dim, dropout, learning_rate, batch_size, epochs,
            cv_folds, cv_avg_loss, cv_avg_accuracy, cv_avg_auc,
            cv_fold_losses, cv_fold_accuracies, cv_fold_aucs,
            train_rows, train_final_loss, feature_version, feature_count,
            model_path, metadata_path, promoted_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s
        )
        """,
        (
            sport, target, model_version, status,
            params.get("hidden_dim"), params.get("dropout"),
            params.get("learning_rate"), params.get("batch_size"), params.get("epochs"),
            cv_folds, cv_avg_loss, cv_avg_accuracy, cv_avg_auc,
            cv_fold_losses, cv_fold_accuracies, cv_fold_aucs,
            train_rows, train_final_loss, FEATURE_VERSION,
            len(__import__("features.feature_registry", fromlist=["FEATURE_COLUMNS"]).FEATURE_COLUMNS),
            model_path, metadata_path, promoted_at,
        ),
    )
    row_id = cursor.lastrowid
    conn.commit()
    cursor.close()
    conn.close()
    logger.info(
        "Registry: logged model id=%d version=%s status=%s sport=%s target=%s "
        "cv_acc=%s cv_auc=%s",
        row_id, model_version, status, sport, target,
        f"{cv_avg_accuracy:.4f}" if cv_avg_accuracy is not None else "N/A",
        f"{cv_avg_auc:.4f}" if cv_avg_auc is not None else "N/A",
    )
    return row_id


def _retire_current_production(sport: str, target: str):
    """Set the current production model to ``retired``."""
    conn = get_connection("modeling_internal")
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE fact_model_registry
        SET status = 'retired', retired_at = NOW()
        WHERE sport = %s AND target = %s AND status = 'production'
        """,
        (sport, target),
    )
    retired = cursor.rowcount
    conn.commit()
    cursor.close()
    conn.close()
    if retired:
        logger.info("Registry: retired %d previous production model(s) for %s/%s", retired, sport, target)


def _copy_candidate_to_production(sport: str, target: str):
    """Copy candidate .pt and _metadata.json to production filenames."""
    for suffix in (".pt", "_metadata.json"):
        src = MODEL_DIR / f"{sport}_{target}_candidate{suffix}"
        dst = MODEL_DIR / f"{sport}_{target}_production{suffix}"
        if src.exists():
            shutil.copy2(src, dst)
            logger.info("Copied %s → %s", src.name, dst.name)
        else:
            logger.warning("Candidate artifact not found: %s", src)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def promote_model(
    sport: str,
    target: str = "home_win",
    cv_folds: int = 5,
) -> dict:
    """Cross-validate the current candidate and promote it to production.

    Steps:
      1. Read candidate metadata for hyperparameters.
      2. Run K-fold cross-validation to compute CV metrics.
      3. Log the candidate to ``fact_model_registry`` as **production**.
      4. Retire the previous production model.
      5. Copy candidate files to production filenames.

    Parameters
    ----------
    sport:
        Sport key.
    target:
        Target column key.
    cv_folds:
        Number of cross-validation folds to run before promotion.

    Returns
    -------
    dict with promotion details, CV metrics, and registry row id.

    Raises
    ------
    ValueError
        If the candidate metadata is missing.
    """
    metadata_path = MODEL_DIR / f"{sport}_{target}_candidate_metadata.json"
    if not metadata_path.exists():
        raise ValueError(
            f"No candidate model found for {sport}/{target}. "
            f"Run /train-model first."
        )

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    model_version = metadata.get("model_version", f"{sport}_{target}_unknown")
    params = {
        "hidden_dim": int(metadata.get("hidden_dim", 128)),
        "dropout": float(metadata.get("dropout", 0.1)),
        "learning_rate": float(metadata.get("learning_rate", 0.001)),
        "batch_size": int(metadata.get("batch_size", 32)),
        "epochs": int(metadata.get("epochs", 5)),
    }

    logger.info(
        "promote_model: validating candidate version=%s  sport=%s target=%s  cv_folds=%d",
        model_version, sport, target, cv_folds,
    )

    # --- Cross-validate ---
    cv_result = cross_validate_model(
        sport=sport,
        target=target,
        folds=cv_folds,
        **params,
    )

    # --- Log candidate as production & retire old ---
    _retire_current_production(sport, target)

    train_result = {
        "train_rows": metadata.get("train_rows"),
        "final_loss": metadata.get("epoch_losses", [None])[-1],
        "model_path": metadata.get("model_path"),
        "metadata_path": str(metadata_path),
    }
    registry_id = _log_to_registry(
        sport, target, model_version, "production", params, cv_result, train_result,
    )

    # --- Copy files ---
    _copy_candidate_to_production(sport, target)

    logger.info(
        "promote_model: DONE — version=%s promoted to production  "
        "cv_acc=%.4f cv_auc=%s registry_id=%d",
        model_version,
        cv_result.get("average_accuracy") or 0,
        f"{cv_result.get('average_auc'):.4f}" if cv_result.get("average_auc") is not None else "N/A",
        registry_id,
    )

    return {
        "sport": sport,
        "target": target,
        "model_version": model_version,
        "status": "production",
        "registry_id": registry_id,
        "cv_folds": cv_folds,
        "cv_average_loss": cv_result.get("average_validation_loss"),
        "cv_average_accuracy": cv_result.get("average_accuracy"),
        "cv_average_auc": cv_result.get("average_auc"),
        "cv_fold_losses": cv_result.get("fold_losses"),
        "cv_fold_accuracies": cv_result.get("fold_accuracies"),
        "cv_fold_aucs": cv_result.get("fold_aucs"),
        "train_rows": metadata.get("train_rows"),
        "params": params,
    }


def refit_model(
    sport: str,
    target: str = "home_win",
    cv_folds: int = 5,
    epochs: int = 5,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    hidden_dim: int = 128,
    dropout: float = 0.1,
) -> dict:
    """End-to-end pipeline: train → cross-validate → log → promote.

    Designed for a single n8n job that refits and productionises a model.

    Steps:
      1. Train candidate on full data.
      2. Cross-validate with the same hyperparameters.
      3. Log as **candidate** in the registry (with CV metrics).
      4. Retire previous production model.
      5. Promote candidate to production.

    Returns
    -------
    dict with combined train + CV + promotion results.
    """
    logger.info(
        "refit_model: sport=%s target=%s cv_folds=%d epochs=%d "
        "hidden_dim=%d dropout=%.3f lr=%.6f bs=%d",
        sport, target, cv_folds, epochs, hidden_dim, dropout, learning_rate, batch_size,
    )

    # 1) Train candidate
    train_result = train_model(
        sport=sport,
        target=target,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        hidden_dim=hidden_dim,
        dropout=dropout,
    )

    # 2) Cross-validate
    cv_result = cross_validate_model(
        sport=sport,
        target=target,
        folds=cv_folds,
        epochs=epochs,
        batch_size=batch_size,
        learning_rate=learning_rate,
        hidden_dim=hidden_dim,
        dropout=dropout,
    )

    model_version = train_result["model_version"]
    params = {
        "hidden_dim": hidden_dim,
        "dropout": dropout,
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "epochs": epochs,
    }

    # 3) Log candidate to registry (even before promotion, for audit trail)
    _log_to_registry(
        sport, target, model_version, "candidate", params, cv_result, train_result,
    )

    # 4) Retire previous production & promote
    _retire_current_production(sport, target)
    registry_id = _log_to_registry(
        sport, target, model_version, "production", params, cv_result, train_result,
    )
    _copy_candidate_to_production(sport, target)

    logger.info(
        "refit_model: DONE — version=%s  cv_acc=%.4f  cv_auc=%s  "
        "train_loss=%.6f  registry_id=%d",
        model_version,
        cv_result.get("average_accuracy") or 0,
        f"{cv_result.get('average_auc'):.4f}" if cv_result.get("average_auc") is not None else "N/A",
        train_result.get("final_loss") or 0,
        registry_id,
    )

    return {
        "sport": sport,
        "target": target,
        "model_version": model_version,
        "status": "production",
        "registry_id": registry_id,
        "train": {
            "train_rows": train_result.get("train_rows"),
            "final_loss": train_result.get("final_loss"),
            "model_path": train_result.get("model_path"),
            "feature_version": train_result.get("feature_version"),
        },
        "cv": {
            "folds": cv_folds,
            "average_loss": cv_result.get("average_validation_loss"),
            "average_accuracy": cv_result.get("average_accuracy"),
            "average_auc": cv_result.get("average_auc"),
            "fold_losses": cv_result.get("fold_losses"),
            "fold_accuracies": cv_result.get("fold_accuracies"),
            "fold_aucs": cv_result.get("fold_aucs"),
        },
        "params": params,
    }


def get_model_status(sport: str | None = None, target: str | None = None) -> dict:
    """Return the current production model(s) from the registry.

    Parameters
    ----------
    sport:
        Filter to a single sport.  ``None`` returns all sports.
    target:
        Filter to a single target.  ``None`` returns all targets.

    Returns
    -------
    dict with a ``models`` list of production model records.
    """
    conn = get_connection("modeling_internal")
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT sport, target, model_version, status,
           hidden_dim, dropout, learning_rate, batch_size, epochs,
           cv_folds, cv_avg_loss, cv_avg_accuracy, cv_avg_auc,
           train_rows, train_final_loss, feature_version, feature_count,
           model_path, metadata_path,
           trained_at, promoted_at
    FROM fact_model_registry
    WHERE status = 'production'
    """
    params = []
    if sport:
        query += " AND sport = %s"
        params.append(sport)
    if target:
        query += " AND target = %s"
        params.append(target)
    query += " ORDER BY sport, target"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    # Convert Decimal / datetime to JSON-safe types
    models = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif hasattr(v, "__float__"):
                clean[k] = float(v)
            else:
                clean[k] = v
        models.append(clean)

    return {"models": models}
