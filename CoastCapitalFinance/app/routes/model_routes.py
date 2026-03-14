"""
Model management API routes.

Endpoints for training, backtesting, comparing, and promoting models.
Powers the /models dashboard page.
"""
from datetime import datetime
from flask import Blueprint, jsonify, request, send_from_directory, current_app
from sqlalchemy import func as sql_func
from app.models.database import get_db
from app.models.schema import DimStock, FactModelRegistry, FactBacktestResult
from app.utils.logging_config import get_logger

logger = get_logger(__name__)

model_bp = Blueprint("models", __name__)


# ---------------------------------------------------------------------------
# Serve models page
# ---------------------------------------------------------------------------

@model_bp.route("/models")
def models_page():
    import os
    static_dir = os.path.join(current_app.root_path, "static")
    return send_from_directory(static_dir, "models.html")


# ---------------------------------------------------------------------------
# GET /api/v1/models/tickers — list tickers that have models or watchlist
# ---------------------------------------------------------------------------

@model_bp.route("/api/v1/models/tickers")
def list_model_tickers():
    """Return tickers that have models in the registry + watchlist tickers."""
    try:
        db = next(get_db())
        # Tickers with registry entries
        registry_tickers = (
            db.query(FactModelRegistry.ticker)
            .distinct()
            .all()
        )
        registry_set = {r[0] for r in registry_tickers}

        # Watchlist tickers (always show)
        from app.routes.market_routes import DEFAULT_WATCHLIST
        all_tickers = sorted(registry_set | set(DEFAULT_WATCHLIST))

        # Get champion info per ticker
        ticker_info = []
        for t in all_tickers:
            champion = (
                db.query(FactModelRegistry)
                .filter(FactModelRegistry.ticker == t, FactModelRegistry.status == "champion")
                .first()
            )
            n_models = (
                db.query(sql_func.count(FactModelRegistry.model_id))
                .filter(FactModelRegistry.ticker == t)
                .scalar()
            ) or 0

            ticker_info.append({
                "ticker": t,
                "has_champion": champion is not None,
                "champion_seq": champion.sequence_num if champion else None,
                "n_models": n_models,
            })

        return jsonify({"tickers": ticker_info})
    except Exception as e:
        logger.error("List model tickers error", error=str(e))
        return jsonify({"tickers": [], "error": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /api/v1/models/<ticker>/train — Train a candidate model
# ---------------------------------------------------------------------------

@model_bp.route("/api/v1/models/<ticker>/train", methods=["POST"])
def train_model_endpoint(ticker: str):
    """
    Train a new candidate model for a ticker.

    Body (JSON, all optional):
        hpo_method: "none" | "grid" | "bayesian" (default: "none")
        lookback_days: int (default: settings value)
        notes: str
    """
    try:
        data = request.get_json(silent=True) or {}
        hpo_method = data.get("hpo_method", "none")
        lookback_days = data.get("lookback_days")
        notes = data.get("notes", "")

        if hpo_method not in ("none", "grid", "bayesian"):
            return jsonify({"error": f"Invalid hpo_method: {hpo_method}"}), 400

        db = next(get_db())
        from app.forecasting.models import train_model
        result = train_model(
            ticker=ticker.upper(),
            db=db,
            lookback_days=lookback_days,
            hpo_method=hpo_method,
            notes=notes,
        )
        db.commit()

        return jsonify({"success": True, **result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Train model error", ticker=ticker, error=str(e), exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /api/v1/models/<ticker>/backtest/<model_id> — Backtest a model version
# ---------------------------------------------------------------------------

@model_bp.route("/api/v1/models/<ticker>/backtest/<int:model_id>", methods=["POST"])
def backtest_model_endpoint(ticker: str, model_id: int):
    """
    Run walk-forward backtest for a specific model version.
    Updates the registry entry with backtest_id + metrics.
    """
    try:
        db = next(get_db())

        # Verify model exists
        entry = db.query(FactModelRegistry).filter(
            FactModelRegistry.model_id == model_id,
            FactModelRegistry.ticker == ticker.upper(),
        ).first()

        if not entry:
            return jsonify({"error": f"Model {model_id} not found for {ticker}"}), 404

        from app.forecasting.backtesting import run_backtest
        result = run_backtest(
            ticker=ticker.upper(),
            db=db,
            hpo_method=entry.hpo_method or "none",
            model_id=model_id,
        )
        db.commit()

        return jsonify({"success": True, "model_id": model_id, **result})

    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        logger.error("Backtest model error", ticker=ticker, model_id=model_id,
                      error=str(e), exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# GET /api/v1/models/<ticker>/versions — List all model versions
# ---------------------------------------------------------------------------

@model_bp.route("/api/v1/models/<ticker>/versions")
def list_model_versions(ticker: str):
    """List all model versions for a ticker, ordered by created_at desc."""
    try:
        db = next(get_db())
        entries = (
            db.query(FactModelRegistry)
            .filter(FactModelRegistry.ticker == ticker.upper())
            .order_by(FactModelRegistry.created_at.desc())
            .all()
        )

        versions = []
        for e in entries:
            versions.append({
                "model_id": e.model_id,
                "ticker": e.ticker,
                "sequence_num": e.sequence_num,
                "status": e.status,
                "model_version": e.model_version,
                "hpo_method": e.hpo_method,
                "training_duration_sec": e.training_duration_sec,
                "train_rows": e.train_rows,
                "n_features": e.n_features,
                "horizons": e.horizons,
                "train_metrics": e.train_metrics,
                "backtest_id": e.backtest_id,
                "backtest_metrics": e.backtest_metrics,
                "feature_importance": e.feature_importance,
                "notes": e.notes,
                "trained_at": e.trained_at.isoformat() if e.trained_at else None,
                "promoted_at": e.promoted_at.isoformat() if e.promoted_at else None,
            })

        return jsonify({"ticker": ticker.upper(), "versions": versions})

    except Exception as e:
        logger.error("List versions error", ticker=ticker, error=str(e))
        return jsonify({"ticker": ticker.upper(), "versions": [], "error": str(e)}), 500


# ---------------------------------------------------------------------------
# GET /api/v1/models/<ticker>/compare — Compare champion vs best candidate
# ---------------------------------------------------------------------------

@model_bp.route("/api/v1/models/<ticker>/compare")
def compare_models(ticker: str):
    """
    Compare champion vs the best candidate.
    Returns metric deltas + recommendation: "promote" / "keep" / "needs_backtest".
    """
    try:
        db = next(get_db())
        ticker = ticker.upper()

        champion = (
            db.query(FactModelRegistry)
            .filter(FactModelRegistry.ticker == ticker, FactModelRegistry.status == "champion")
            .first()
        )

        # Best candidate = most recent candidate with backtest
        candidate = (
            db.query(FactModelRegistry)
            .filter(
                FactModelRegistry.ticker == ticker,
                FactModelRegistry.status == "candidate",
                FactModelRegistry.backtest_metrics.isnot(None),
            )
            .order_by(FactModelRegistry.created_at.desc())
            .first()
        )

        # Also check if there's an un-backtested candidate
        unbacetsted = (
            db.query(FactModelRegistry)
            .filter(
                FactModelRegistry.ticker == ticker,
                FactModelRegistry.status == "candidate",
                FactModelRegistry.backtest_metrics.is_(None),
            )
            .order_by(FactModelRegistry.created_at.desc())
            .first()
        )

        result = {
            "ticker": ticker,
            "champion": _registry_to_dict(champion) if champion else None,
            "candidate": _registry_to_dict(candidate) if candidate else None,
            "recommendation": "no_models",
            "metric_deltas": {},
        }

        if not champion and not candidate:
            if unbacetsted:
                result["recommendation"] = "needs_backtest"
                result["candidate"] = _registry_to_dict(unbacetsted)
            return jsonify(result)

        if not champion and candidate:
            result["recommendation"] = "promote"
            return jsonify(result)

        if champion and not candidate:
            if unbacetsted:
                result["recommendation"] = "needs_backtest"
                result["candidate"] = _registry_to_dict(unbacetsted)
            else:
                result["recommendation"] = "keep"
            return jsonify(result)

        # Both exist: compare on key metrics
        champ_m = champion.backtest_metrics or {}
        cand_m = candidate.backtest_metrics or {}

        compare_keys = ["directional_accuracy", "sharpe_ratio", "alpha"]
        wins = 0
        deltas = {}
        for key in compare_keys:
            c_val = champ_m.get(key, 0) or 0
            n_val = cand_m.get(key, 0) or 0
            delta = n_val - c_val
            deltas[key] = {"champion": c_val, "candidate": n_val, "delta": delta}
            if delta > 0:
                wins += 1

        result["metric_deltas"] = deltas
        result["recommendation"] = "promote" if wins >= 2 else "keep"

        return jsonify(result)

    except Exception as e:
        logger.error("Compare models error", ticker=ticker, error=str(e))
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# POST /api/v1/models/<ticker>/promote/<model_id> — Promote candidate
# ---------------------------------------------------------------------------

@model_bp.route("/api/v1/models/<ticker>/promote/<int:model_id>", methods=["POST"])
def promote_model(ticker: str, model_id: int):
    """
    Promote a candidate model to champion.
    Archives the current champion. Requires backtest first.
    """
    try:
        db = next(get_db())
        ticker = ticker.upper()

        candidate = db.query(FactModelRegistry).filter(
            FactModelRegistry.model_id == model_id,
            FactModelRegistry.ticker == ticker,
            FactModelRegistry.status == "candidate",
        ).first()

        if not candidate:
            return jsonify({"error": "Candidate model not found or not in 'candidate' status"}), 404

        if not candidate.backtest_metrics:
            return jsonify({"error": "Model must be backtested before promotion"}), 400

        # Archive current champion
        current_champion = db.query(FactModelRegistry).filter(
            FactModelRegistry.ticker == ticker,
            FactModelRegistry.status == "champion",
        ).first()

        old_champion_id = None
        if current_champion:
            current_champion.status = "archived"
            old_champion_id = current_champion.model_id

        # Promote candidate
        candidate.status = "champion"
        candidate.promoted_at = datetime.utcnow()
        candidate.promoted_from_id = old_champion_id

        db.commit()

        # Also update the unversioned .pkl to point to this model
        try:
            import os
            import shutil
            from app.forecasting.models import MODELS_DIR, MODEL_VERSION
            versioned = os.path.join(MODELS_DIR, candidate.model_path)
            unversioned = os.path.join(MODELS_DIR, f"{ticker}_{MODEL_VERSION}.pkl")
            if os.path.exists(versioned):
                shutil.copy2(versioned, unversioned)
                logger.info("Updated unversioned model file", ticker=ticker)
        except Exception as e:
            logger.warning("Failed to update unversioned model file", error=str(e))

        logger.info("Model promoted", ticker=ticker, model_id=model_id,
                     old_champion_id=old_champion_id)

        return jsonify({
            "success": True,
            "ticker": ticker,
            "promoted_model_id": model_id,
            "archived_model_id": old_champion_id,
        })

    except Exception as e:
        logger.error("Promote model error", ticker=ticker, model_id=model_id,
                      error=str(e), exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# GET /api/v1/models/performance — Aggregate performance across tickers
# ---------------------------------------------------------------------------

@model_bp.route("/api/v1/models/performance")
def aggregate_performance():
    """Aggregate performance summary across all tickers with champion models."""
    try:
        db = next(get_db())
        champions = (
            db.query(FactModelRegistry)
            .filter(FactModelRegistry.status == "champion")
            .all()
        )

        summaries = []
        for c in champions:
            metrics = c.backtest_metrics or {}
            summaries.append({
                "ticker": c.ticker,
                "model_id": c.model_id,
                "sequence_num": c.sequence_num,
                "hpo_method": c.hpo_method,
                "directional_accuracy": metrics.get("directional_accuracy"),
                "sharpe_ratio": metrics.get("sharpe_ratio"),
                "alpha": metrics.get("alpha"),
                "max_drawdown": metrics.get("max_drawdown"),
                "win_rate": metrics.get("win_rate"),
                "trained_at": c.trained_at.isoformat() if c.trained_at else None,
            })

        # Aggregate
        if summaries:
            avg_da = sum(s["directional_accuracy"] or 0 for s in summaries) / len(summaries)
            avg_sharpe = sum(s["sharpe_ratio"] or 0 for s in summaries) / len(summaries)
            avg_alpha = sum(s["alpha"] or 0 for s in summaries) / len(summaries)
        else:
            avg_da = avg_sharpe = avg_alpha = 0

        return jsonify({
            "n_champions": len(summaries),
            "avg_directional_accuracy": round(avg_da, 4),
            "avg_sharpe_ratio": round(avg_sharpe, 4),
            "avg_alpha": round(avg_alpha, 4),
            "champions": summaries,
        })

    except Exception as e:
        logger.error("Aggregate performance error", error=str(e))
        return jsonify({"n_champions": 0, "champions": [], "error": str(e)}), 500


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _registry_to_dict(entry: FactModelRegistry) -> dict:
    """Convert a FactModelRegistry row to a serializable dict."""
    if not entry:
        return {}
    return {
        "model_id": entry.model_id,
        "ticker": entry.ticker,
        "sequence_num": entry.sequence_num,
        "status": entry.status,
        "model_version": entry.model_version,
        "hpo_method": entry.hpo_method,
        "training_duration_sec": entry.training_duration_sec,
        "train_rows": entry.train_rows,
        "n_features": entry.n_features,
        "horizons": entry.horizons,
        "train_metrics": entry.train_metrics,
        "backtest_id": entry.backtest_id,
        "backtest_metrics": entry.backtest_metrics,
        "feature_importance": entry.feature_importance,
        "notes": entry.notes,
        "trained_at": entry.trained_at.isoformat() if entry.trained_at else None,
        "promoted_at": entry.promoted_at.isoformat() if entry.promoted_at else None,
    }
