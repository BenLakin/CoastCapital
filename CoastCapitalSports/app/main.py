"""
main.py — Flask application entry point for CoastCapitalAnalytics.

All routes are designed to be called by n8n workflows via HTTP POST.
Every endpoint returns a JSON body and a meaningful HTTP status code:
  200  success
  400  bad request (missing/invalid parameters)
  500  internal error (pipeline/model failure)
"""

import os
import threading
import traceback
import uuid
from datetime import datetime

from flask import Flask, g, jsonify, request, render_template

from models.cross_validate_torch_model import cross_validate_model
from models.modeling_data import materialize_features_to_modeling_silver
from models.score_torch_model import score_model
from models.train_torch_model import train_model
from models.tune_torch_model import tune_model
from models.promote_model import promote_model, refit_model, get_model_status
from pipelines.backfill_pipeline import run_backfill_pipeline
from pipelines.update_pipeline import run_update_pipeline
from utils.logging_config import get_logger
from utils.metrics import init_metrics

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Background job tracker (for long-running backfills)
# ---------------------------------------------------------------------------

_jobs: dict = {}  # job_id -> {"status": str, "result": dict | None, "error": str | None}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Flask(__name__)
init_metrics(app, module="sports")

API_KEY = os.environ.get("API_KEY", "")

@app.before_request
def _check_api_key():
    """Require X-API-Key header on all non-health endpoints."""
    if request.path in ("/health", "/metrics", "/favicon.ico"):
        return None
    if request.path.startswith("/static"):
        return None
    key = request.headers.get("X-API-Key") or request.args.get("api_key")
    if not API_KEY or key != API_KEY:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

# X-Request-ID header
@app.after_request
def _add_request_id(response):
    rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:8])
    response.headers["X-Request-ID"] = rid
    return response

logger.info("Starting analytics-engine")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error(message: str, status: int = 500):
    """Return a JSON error response."""
    logger.error(message)
    return jsonify({"success": False, "error": message}), status


def _safe_int(value, default: int):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default: float):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    """Liveness probe."""
    return jsonify({"status": "ok", "service": "coastcapital-sports", "ts": datetime.now().isoformat()})


@app.route("/update", methods=["POST"])
def update():
    """Ingest the latest game data for one or all sports.

    Body (JSON, all optional):
      sport  — "nfl" | "ncaa_mbb" | "mlb" | "all"  (default: "all")
      date   — "YYYY-MM-DD"  (default: today UTC)

    Returns the pipeline result or a 500 on failure.
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "all")
    date_str = payload.get("date")
    logger.info("POST /update  sport=%s  date=%s", sport, date_str)
    try:
        result = run_update_pipeline(sport=sport, date_str=date_str)
        return jsonify(result)
    except Exception as exc:
        logger.error("Update pipeline failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Update pipeline failed: {exc}")


@app.route("/backfill", methods=["POST"])
def backfill():
    """Backfill historical data for one or all sports.

    Body (JSON):
      sport       — "nfl" | "ncaa_mbb" | "mlb" | "all"  (default: "all")
      start_date  — "YYYY-MM-DD"  (required unless season is provided)
      end_date    — "YYYY-MM-DD"  (required unless season is provided)
      season      — int year, e.g. 2023 (used to derive start/end if omitted)

    Returns aggregated pipeline results or a 500 on failure.
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "all")
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    season = payload.get("season")
    logger.info(
        "POST /backfill  sport=%s  start=%s  end=%s  season=%s",
        sport, start_date, end_date, season,
    )
    try:
        result = run_backfill_pipeline(
            sport=sport,
            start_date=start_date,
            end_date=end_date,
            season=season,
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Backfill pipeline failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Backfill pipeline failed: {exc}")


@app.route("/materialize-features", methods=["POST"])
def materialize_features():
    """Build feature vectors from silver-layer data and write to modeling_silver.

    Body (JSON, all optional):
      sport — "nfl" | "ncaa_mbb" | "mlb"  (default: "nfl")
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "nfl")
    logger.info("POST /materialize-features  sport=%s", sport)
    try:
        result = materialize_features_to_modeling_silver(sport)
        return jsonify(result)
    except Exception as exc:
        logger.error("Materialize features failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Materialize features failed: {exc}")


@app.route("/train-model", methods=["POST"])
def train_model_endpoint():
    """Train a PyTorch binary classifier for the given sport and target.

    Body (JSON, all optional):
      sport         — "nfl" | "ncaa_mbb" | "mlb"  (default: "nfl")
      target        — "home_win" | "cover_home" | "total_over"  (default: "home_win")
      epochs        — int  (default: 5)
      batch_size    — int  (default: 32)
      learning_rate — float  (default: 0.001)
      hidden_dim    — int  (default: 128)
      dropout       — float  (default: 0.1)
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "nfl")
    target = payload.get("target", "home_win")
    logger.info("POST /train-model  sport=%s  target=%s", sport, target)
    try:
        result = train_model(
            sport=sport,
            target=target,
            epochs=_safe_int(payload.get("epochs"), 5),
            batch_size=_safe_int(payload.get("batch_size"), 32),
            learning_rate=_safe_float(payload.get("learning_rate"), 0.001),
            hidden_dim=_safe_int(payload.get("hidden_dim"), 128),
            dropout=_safe_float(payload.get("dropout"), 0.1),
            n_layers=_safe_int(payload.get("n_layers"), 3),
            batch_norm=bool(payload.get("batch_norm", True)),
            weight_decay=_safe_float(payload.get("weight_decay"), 0.0),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Train model failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Train model failed: {exc}")


@app.route("/score-model", methods=["POST"])
def score_model_endpoint():
    """Score recent games using a trained model.

    Body (JSON, all optional):
      sport  — "nfl" | "ncaa_mbb" | "mlb"  (default: "nfl")
      target — "home_win" | "cover_home" | "total_over"  (default: "home_win")
      limit  — int, number of most-recent rows to score  (default: 100)
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "nfl")
    target = payload.get("target", "home_win")
    logger.info("POST /score-model  sport=%s  target=%s", sport, target)
    try:
        result = score_model(
            sport=sport,
            target=target,
            limit=_safe_int(payload.get("limit"), 100),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Score model failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Score model failed: {exc}")


@app.route("/cross-validate-model", methods=["POST"])
def cross_validate_model_endpoint():
    """Time-series cross-validate a model without saving artifacts.

    Body (JSON, all optional):
      sport         — "nfl" | "ncaa_mbb" | "mlb"  (default: "nfl")
      target        — "home_win" | "cover_home" | "total_over"  (default: "home_win")
      folds         — int  (default: 5)
      epochs        — int  (default: 5)
      batch_size    — int  (default: 32)
      learning_rate — float  (default: 0.001)
      hidden_dim    — int  (default: 128)
      dropout       — float  (default: 0.1)
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "nfl")
    target = payload.get("target", "home_win")
    logger.info("POST /cross-validate-model  sport=%s  target=%s", sport, target)
    try:
        result = cross_validate_model(
            sport=sport,
            target=target,
            epochs=_safe_int(payload.get("epochs"), 5),
            batch_size=_safe_int(payload.get("batch_size"), 32),
            learning_rate=_safe_float(payload.get("learning_rate"), 0.001),
            folds=_safe_int(payload.get("folds"), 5),
            hidden_dim=_safe_int(payload.get("hidden_dim"), 128),
            dropout=_safe_float(payload.get("dropout"), 0.1),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Cross-validate model failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Cross-validate model failed: {exc}")


@app.route("/tune-model", methods=["POST"])
def tune_model_endpoint():
    """Optuna Bayesian hyperparameter optimization.

    Body (JSON, all optional):
      sport     — "nfl" | "ncaa_mbb" | "mlb"  (default: "nfl")
      target    — "home_win" | "cover_home" | "total_over"  (default: "home_win")
      folds     — int  (default: 3)
      n_trials  — int  (default: 50, from SPORTS_OPTUNA_N_TRIALS env)
      timeout   — int seconds  (default: 600, from SPORTS_OPTUNA_TIMEOUT env)
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "nfl")
    target = payload.get("target", "home_win")
    logger.info("POST /tune-model  sport=%s  target=%s", sport, target)
    try:
        result = tune_model(
            sport=sport,
            target=target,
            folds=_safe_int(payload.get("folds"), 3),
            n_trials=_safe_int(payload.get("n_trials"), None),
            timeout=_safe_int(payload.get("timeout"), None),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Tune model failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Tune model failed: {exc}")


@app.route("/promote-model", methods=["POST"])
def promote_model_endpoint():
    """Cross-validate the current candidate model and promote it to production.

    Body (JSON, all optional):
      sport    — "nfl" | "ncaa_mbb" | "mlb"  (default: "nfl")
      target   — "home_win" | "cover_home" | "total_over"  (default: "home_win")
      cv_folds — int, number of CV folds to validate before promotion  (default: 5)
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "nfl")
    target = payload.get("target", "home_win")
    logger.info("POST /promote-model  sport=%s  target=%s", sport, target)
    try:
        result = promote_model(
            sport=sport,
            target=target,
            cv_folds=_safe_int(payload.get("cv_folds"), 5),
        )
        result["promoted"] = True
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.warning("Promote model did not pass validation (continuing with existing model): %s", exc)
        return jsonify({
            "success": True,
            "warning": f"Promotion skipped — continuing with existing model: {exc}",
            "promoted": False,
            "sport": sport,
            "target": target,
        })


@app.route("/refit-model", methods=["POST"])
def refit_model_endpoint():
    """End-to-end pipeline: train candidate -> cross-validate -> promote to production.

    Designed as a single n8n job for periodic model retraining.

    Body (JSON, all optional):
      sport         — "nfl" | "ncaa_mbb" | "mlb"  (default: "nfl")
      target        — "home_win" | "cover_home" | "total_over"  (default: "home_win")
      cv_folds      — int  (default: 5)
      epochs        — int  (default: 5)
      batch_size    — int  (default: 32)
      learning_rate — float  (default: 0.001)
      hidden_dim    — int  (default: 128)
      dropout       — float  (default: 0.1)
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "nfl")
    target = payload.get("target", "home_win")
    logger.info("POST /refit-model  sport=%s  target=%s", sport, target)
    try:
        result = refit_model(
            sport=sport,
            target=target,
            cv_folds=_safe_int(payload.get("cv_folds"), 5),
            epochs=_safe_int(payload.get("epochs"), 5),
            batch_size=_safe_int(payload.get("batch_size"), 32),
            learning_rate=_safe_float(payload.get("learning_rate"), 0.001),
            hidden_dim=_safe_int(payload.get("hidden_dim"), 128),
            dropout=_safe_float(payload.get("dropout"), 0.1),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Refit model failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Refit model failed: {exc}")


@app.route("/model-status", methods=["GET"])
def model_status_endpoint():
    """Return the current production model(s) from the registry.

    Query params (all optional):
      sport  — filter to a single sport
      target — filter to a single target
    """
    sport = request.args.get("sport")
    target = request.args.get("target")
    logger.info("GET /model-status  sport=%s  target=%s", sport, target)
    try:
        result = get_model_status(sport=sport, target=target)
        return jsonify(result)
    except Exception as exc:
        logger.error("Model status failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Model status failed: {exc}")


@app.route("/simulate-bracket", methods=["POST"])
def simulate_bracket_endpoint():
    """Run Monte Carlo bracket simulation and optimize picks.

    Body (JSON):
      season             — int, tournament year (required)
      n_runs             — int, number of independent runs  (default: 10)
      n_simulations      — int, simulations per run  (default: 10000)
      pool_size          — int  (default: 100)
      risk_tolerance     — float 0-1  (default: 0.5)
      output_html        — bool  (default: true)
      output_pdf         — bool  (default: true)
      refresh_field      — bool, re-fetch field from ESPN  (default: false)
    """
    payload = request.get_json(silent=True) or {}
    season = payload.get("season")
    if not season:
        return _error("season is required", status=400)
    season = _safe_int(season, 0)
    if season < 2000:
        return _error("season must be a valid year (e.g. 2025)", status=400)

    n_runs = _safe_int(payload.get("n_runs"), 10)
    n_sims = _safe_int(payload.get("n_simulations"), 10000)
    logger.info("POST /simulate-bracket  season=%d  n_runs=%d  n_sims=%d", season, n_runs, n_sims)

    try:
        from bracket.bracket_data import (
            build_bracket_structure, fetch_tournament_field,
            load_bracket_field, save_bracket_field,
        )
        from bracket.bracket_html import generate_bracket_html, save_bracket_html
        from bracket.bracket_pdf import generate_summary_pdf
        from bracket.matchup_predictor import load_ncaa_model
        from bracket.optimizer import optimize_bracket
        from bracket.simulation import TournamentSimulator
        from bracket.team_profile import build_team_profiles, save_team_profiles

        refresh = payload.get("refresh_field", False)
        pool_size = _safe_int(payload.get("pool_size"), 100)
        risk_tolerance = _safe_float(payload.get("risk_tolerance"), 0.5)
        output_html = payload.get("output_html", True)
        output_pdf = payload.get("output_pdf", True)

        # 1. Get bracket field
        field_df = load_bracket_field(season)
        if field_df.empty or refresh:
            field = fetch_tournament_field(season)
            if not field:
                return _error(f"No bracket data found for season {season}", status=400)
            save_bracket_field(season, field)
            field_df = load_bracket_field(season)

        bracket = build_bracket_structure(field_df.to_dict("records"))

        # 2. Build team profiles
        profiles = build_team_profiles(season)
        team_seeds = {r["team_name"]: r["seed"] for _, r in field_df.iterrows()}
        save_team_profiles(season, profiles, team_seeds)

        # 3. Load model
        model, metadata = load_ncaa_model()

        from models.modeling_data import build_feature_frame
        _, team_to_id = build_feature_frame("ncaa_mbb")

        # 4. Run N independent simulations
        all_runs = []
        best_run = None
        best_expected = -1

        for run_idx in range(n_runs):
            logger.info("simulate-bracket: run %d/%d (%d sims)", run_idx + 1, n_runs, n_sims)
            simulator = TournamentSimulator(bracket, profiles, team_to_id, model)
            sim_results = simulator.run_monte_carlo(n_sims)

            picks = optimize_bracket(sim_results, bracket, pool_size, risk_tolerance)

            picks_data = [
                {
                    "round": p.round_number,
                    "game": p.game_number,
                    "region": p.region,
                    "winner": p.predicted_winner,
                    "win_prob": p.win_probability,
                    "is_upset": p.is_upset,
                    "is_contrarian": p.is_contrarian,
                    "expected_points": getattr(p, "expected_points", 0),
                }
                for p in picks
            ]

            champion = ""
            for p in picks_data:
                if p["round"] == 6:
                    champion = p["winner"]
                    break

            total_expected = sum(p.get("expected_points", 0) for p in picks_data)

            run_result = {
                "run": run_idx + 1,
                "simulation_id": sim_results["simulation_id"],
                "n_simulations": n_sims,
                "champion": champion,
                "picks": picks_data,
                "total_expected_points": total_expected,
                "top_champions": dict(
                    sorted(sim_results["champion_rates"].items(), key=lambda x: -x[1])[:10]
                ),
            }
            all_runs.append(run_result)

            if total_expected > best_expected:
                best_expected = total_expected
                best_run = run_result

            # Save HTML for each run
            if output_html:
                html_file = f"/app/bracket_output/{season}_bracket_run{run_idx + 1}.html"
                html = generate_bracket_html(
                    picks, sim_results, bracket, season,
                    metadata.get("model_version", "unknown"),
                    pool_size,
                )
                save_bracket_html(html, html_file)

        # 5. Generate summary PDF across all runs
        pdf_path = None
        if output_pdf:
            try:
                pdf_path = generate_summary_pdf(
                    all_runs, season,
                    metadata.get("model_version", "unknown"),
                )
            except Exception as pdf_exc:
                logger.warning("PDF generation failed (non-fatal): %s", pdf_exc)

        return jsonify({
            "status": "ok",
            "season": season,
            "n_runs": n_runs,
            "n_simulations_per_run": n_sims,
            "best_run": best_run,
            "champion": best_run["champion"] if best_run else "",
            "all_champions": [r["champion"] for r in all_runs],
            "pdf_path": pdf_path,
            "model_version": metadata.get("model_version"),
        })
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Simulate bracket failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Simulate bracket failed: {exc}")


@app.route("/bracket-history", methods=["POST"])
def bracket_history_endpoint():
    """Run historical bracket pipeline for backtesting.

    Body (JSON):
      season         — int, tournament year (required)
      n_simulations  — int  (default: 10000)
      pool_size      — int  (default: 100)
      risk_tolerance — float 0-1  (default: 0.5)
    """
    payload = request.get_json(silent=True) or {}
    season = payload.get("season")
    if not season:
        return _error("season is required", status=400)
    season = _safe_int(season, 0)
    if season < 2000:
        return _error("season must be a valid year (e.g. 2024)", status=400)
    logger.info("POST /bracket-history  season=%d", season)
    try:
        from bracket.historical import run_historical_bracket
        result = run_historical_bracket(
            season=season,
            n_simulations=_safe_int(payload.get("n_simulations"), 10000),
            pool_size=_safe_int(payload.get("pool_size"), 100),
            risk_tolerance=_safe_float(payload.get("risk_tolerance"), 0.5),
        )
        return jsonify(result)
    except ValueError as exc:
        return _error(str(exc), status=400)
    except Exception as exc:
        logger.error("Bracket history failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Bracket history failed: {exc}")


@app.route("/bracket-status", methods=["GET"])
def bracket_status_endpoint():
    """Return current bracket field and latest simulation summary.

    Query params (all optional):
      season — int, filter to a specific season (default: current year)
    """
    season = _safe_int(request.args.get("season"), 0)
    logger.info("GET /bracket-status  season=%s", season or "latest")
    try:
        from bracket.bracket_data import load_bracket_field
        from database import get_connection

        if not season:
            # Find the most recent season in the DB
            conn = get_connection("modeling_internal")
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(season) FROM fact_bracket_fields")
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            season = row[0] if row and row[0] else 0

        if not season:
            return jsonify({"status": "ok", "message": "No bracket data found", "field": [], "simulation": None})

        field_df = load_bracket_field(season)
        field_data = field_df.to_dict("records") if not field_df.empty else []

        # Latest simulation
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT simulation_id, season, num_simulations, pool_size,
                   risk_tolerance, model_version, created_at
            FROM fact_bracket_simulations
            WHERE season = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (season,),
        )
        sim = cursor.fetchone()
        cursor.close()
        conn.close()

        if sim and sim.get("created_at"):
            sim["created_at"] = str(sim["created_at"])

        return jsonify({
            "status": "ok",
            "season": season,
            "field_count": len(field_data),
            "field": field_data,
            "simulation": sim,
        })
    except Exception as exc:
        logger.error("Bracket status failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Bracket status failed: {exc}")


@app.route("/migrate-db", methods=["POST"])
def migrate_db():
    """Apply incremental column migrations to all schemas.

    Runs the add_column_if_not_exists stored procedure for each pending
    column migration. Safe to call multiple times (idempotent).
    """
    logger.info("POST /migrate-db")
    try:
        from scripts.migrate_columns import run_migrations
        result = run_migrations()
        return jsonify(result)
    except Exception as exc:
        logger.error("DB migration failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"DB migration failed: {exc}")


# ---------------------------------------------------------------------------
# Historical odds backfill
# ---------------------------------------------------------------------------

@app.route("/backfill-odds", methods=["POST"])
def backfill_odds():
    """Backfill historical odds from external free datasets.

    Body (JSON):
      sport      — "nfl" or "mlb" (required)
      start_year — int, optional filter
      end_year   — int, optional filter

    Downloads Excel files, matches to existing game_results rows by
    (game_date, home_team, away_team), and inserts into fact_market_odds.
    """
    logger.info("POST /backfill-odds")
    try:
        data = request.get_json(force=True) or {}
        sport = data.get("sport")
        if not sport:
            return _error("'sport' is required (nfl or mlb)")

        from pipelines.odds_backfill import backfill_historical_odds
        result = backfill_historical_odds(
            sport=sport,
            start_year=data.get("start_year"),
            end_year=data.get("end_year"),
        )
        return jsonify(result)
    except Exception as exc:
        logger.error("Odds backfill failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Odds backfill failed: {exc}")


# ---------------------------------------------------------------------------
# Daily pipeline
# ---------------------------------------------------------------------------

@app.route("/daily-pipeline", methods=["POST"])
def daily_pipeline_endpoint():
    """Run the daily ingest + score + betting pipeline.

    Body (JSON, all optional):
      sports       — list of sport keys  (default: ["mlb", "ncaa_mbb"])
      date         — "YYYY-MM-DD"  (default: today UTC)
      skip_news    — bool  (default: false)
      skip_betting — bool  (default: false)
      bankroll     — float (default: 50)
      max_pct      — float 0-1 (default: 0.5)
    """
    payload = request.get_json(silent=True) or {}
    sports = payload.get("sports", ["mlb", "ncaa_mbb"])
    date_str = payload.get("date")
    logger.info("POST /daily-pipeline  sports=%s  date=%s", sports, date_str)
    try:
        from pipelines.daily_sport_pipeline import run_daily_pipeline
        result = run_daily_pipeline(
            sports=sports,
            date_str=date_str,
            skip_news=payload.get("skip_news", False),
            skip_betting=payload.get("skip_betting", False),
            bankroll=_safe_float(payload.get("bankroll"), 50.0),
            max_pct=_safe_float(payload.get("max_pct"), 0.50),
        )
        return jsonify(result)
    except Exception as exc:
        logger.error("Daily pipeline failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Daily pipeline failed: {exc}")


@app.route("/weekly-optimization", methods=["POST"])
def weekly_optimization_endpoint():
    """Run the weekly model optimization and betting plan generation.

    Body (JSON, all optional):
      sports       — list of sport keys  (default: ["mlb", "ncaa_mbb"])
      bankroll     — float  (default: 50)
      max_pct      — float 0-1  (default: 0.5)
      force_refit  — bool  (default: false)
    """
    payload = request.get_json(silent=True) or {}
    sports = payload.get("sports", ["mlb", "ncaa_mbb"])
    logger.info("POST /weekly-optimization  sports=%s", sports)
    try:
        from pipelines.weekly_optimization import run_weekly_optimization
        result = run_weekly_optimization(
            bankroll=_safe_float(payload.get("bankroll"), 50.0),
            max_pct=_safe_float(payload.get("max_pct"), 0.50),
            force_refit=payload.get("force_refit", False),
            sports=sports,
        )
        return jsonify(result)
    except Exception as exc:
        logger.error("Weekly optimization failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Weekly optimization failed: {exc}")


@app.route("/api/weekly-plan", methods=["GET"])
def api_weekly_plan():
    """Return the most recent weekly betting plan."""
    from database import get_connection
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        # Table may not exist if weekly pipeline has never run
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = 'modeling_internal'
              AND table_name = 'fact_weekly_betting_plans'
        """)
        if cursor.fetchone()["cnt"] == 0:
            cursor.close()
            conn.close()
            return jsonify({"status": "ok", "plan": None, "message": "No weekly plan generated yet. Run POST /weekly-optimization first."})

        cursor.execute("""
            SELECT id, week_start, bankroll, max_per_game,
                   total_wagered, bet_count, plan_json, created_at
            FROM fact_weekly_betting_plans
            ORDER BY created_at DESC
            LIMIT 1
        """)
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return jsonify({"status": "ok", "plan": None, "message": "No weekly plan generated yet"})

        for k in ("week_start", "created_at"):
            if row.get(k):
                row[k] = str(row[k])
        if row.get("plan_json"):
            if isinstance(row["plan_json"], str):
                import json as _json
                row["plan_json"] = _json.loads(row["plan_json"])

        return jsonify({"status": "ok", "plan": row})
    except Exception as exc:
        logger.error("API weekly-plan failed: %s", exc)
        return _error(f"API weekly-plan failed: {exc}")


# ---------------------------------------------------------------------------
# Dashboard pages
# ---------------------------------------------------------------------------

@app.route("/dashboard")
def dashboard_page():
    """Sports Summary Dashboard page."""
    return render_template("dashboard.html", active_page="dashboard")


@app.route("/dashboard/betting")
def betting_page():
    """Betting Recommendations page."""
    return render_template("betting.html", active_page="betting")


@app.route("/dashboard/model-performance")
def model_performance_page():
    """Model Performance Dashboard page."""
    return render_template("model_performance.html", active_page="model_performance")


@app.route("/dashboard/model-diagnostics")
def model_diagnostics_page():
    """Model Diagnostics Dashboard page."""
    return render_template("model_diagnostics.html", active_page="model_diagnostics")


@app.route("/dashboard/bracket")
def bracket_page():
    """NCAA Bracket Simulation page."""
    return render_template("bracket.html", active_page="bracket")


@app.route("/dashboard/bet-history")
def bet_history_page():
    """Bet Tracking & Performance page."""
    return render_template("bet_history.html", active_page="bet-history")


# ---------------------------------------------------------------------------
# News endpoints
# ---------------------------------------------------------------------------

@app.route("/ingest-news", methods=["POST"])
def ingest_news_endpoint():
    """Fetch and store sports news with optional LLM summaries.

    Body (JSON, all optional):
      sport     — "nfl" | "ncaa_mbb" | "mlb" | "ncaa_fbs" | "all" (default: "all")
      summarize — bool (default: true)
    """
    payload = request.get_json(silent=True) or {}
    sport = payload.get("sport", "all")
    summarize = payload.get("summarize", True)
    logger.info("POST /ingest-news  sport=%s  summarize=%s", sport, summarize)
    try:
        from ingestion.news_ingest import ingest_news
        result = ingest_news(sport=sport, summarize=summarize)
        return jsonify(result)
    except Exception as exc:
        logger.error("News ingest failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"News ingest failed: {exc}")


@app.route("/api/news", methods=["GET"])
def api_news():
    """Return recent sports news for dashboard consumption."""
    from database import get_connection
    sport = request.args.get("sport")
    team = request.args.get("team")
    limit = _safe_int(request.args.get("limit"), 20)

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        sql = "SELECT * FROM fact_sports_news WHERE 1=1"
        params: list = []
        if sport:
            sql += " AND sport = %s"
            params.append(sport)
        if team:
            sql += " AND focus_team = %s"
            params.append(team)
        sql += " ORDER BY published_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Serialise datetime fields
        for r in rows:
            for k in ("published_at", "fetched_at"):
                if r.get(k):
                    r[k] = str(r[k])

        return jsonify({"status": "ok", "articles": rows})
    except Exception as exc:
        logger.error("API news failed: %s", exc)
        return _error(f"API news failed: {exc}")


# ---------------------------------------------------------------------------
# Betting recommendations
# ---------------------------------------------------------------------------

@app.route("/api/betting-recommendations", methods=["GET"])
def api_betting_recommendations():
    """Weekly betting recommendations with bankroll allocation.

    Query params (all optional):
      bankroll — float, total bankroll (default: 50)
      max_pct  — float 0-1, max fraction per game (default: 0.5)
    """
    bankroll = _safe_float(request.args.get("bankroll"), 50.0)
    max_pct = _safe_float(request.args.get("max_pct"), 0.50)
    max_pct = min(max(max_pct, 0.05), 0.50)  # clamp to 5%-50%

    try:
        from betting.recommender import get_betting_recommendations
        result = get_betting_recommendations(bankroll=bankroll, max_pct=max_pct)
        return jsonify({"status": "ok", **result})
    except Exception as exc:
        logger.error("Betting recommendations failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Betting recommendations failed: {exc}")


# ---------------------------------------------------------------------------
# Dashboard API endpoints
# ---------------------------------------------------------------------------

@app.route("/api/quick-stats", methods=["GET"])
def api_quick_stats():
    """Aggregate counts and latest dates per sport."""
    from database import get_connection
    try:
        schemas = {
            "nfl": "nfl_silver",
            "ncaa_mbb": "ncaa_mbb_silver",
            "mlb": "mlb_silver",
        }
        stats = {}
        for sport, schema in schemas.items():
            try:
                conn = get_connection(schema)
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*), MAX(game_date) FROM fact_game_results")
                row = cursor.fetchone()
                stats[sport] = {
                    "game_count": row[0] if row else 0,
                    "latest_date": str(row[1]) if row and row[1] else None,
                }
                cursor.close()
                conn.close()
            except Exception:
                stats[sport] = {"game_count": 0, "latest_date": None}

        return jsonify({"status": "ok", "stats": stats})
    except Exception as exc:
        logger.error("API quick-stats failed: %s", exc)
        return _error(f"API quick-stats failed: {exc}")


@app.route("/api/focus-team-scores", methods=["GET"])
def api_focus_team_scores():
    """Return recent game scores for focus teams."""
    from database import get_connection

    focus = [
        {"team_name": "Indianapolis Colts", "team_key": "Colts", "sport": "NFL", "schema": "nfl_silver"},
        {"team_name": "Chicago Cubs", "team_key": "Cubs", "sport": "MLB", "schema": "mlb_silver"},
        {"team_name": "Iowa Hawkeyes", "team_key": "Hawkeyes", "sport": "NCAA MBB", "schema": "ncaa_mbb_silver"},
    ]
    results = []

    for team in focus:
        try:
            conn = get_connection(team["schema"])
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT game_id, game_date, home_team, away_team, home_score, away_score, margin
                FROM fact_game_results
                WHERE home_team LIKE %s OR away_team LIKE %s
                ORDER BY game_date DESC
                LIMIT 5
                """,
                (f"%{team['team_key']}%", f"%{team['team_key']}%"),
            )
            games = cursor.fetchall()
            cursor.close()
            conn.close()
            for g in games:
                if g.get("game_date"):
                    g["game_date"] = str(g["game_date"])[:10]
            results.append({**team, "games": games})
        except Exception as exc:
            logger.warning("Focus team scores failed for %s: %s", team["team_name"], exc)
            results.append({**team, "games": []})

    return jsonify({"status": "ok", "teams": results})


@app.route("/api/model-performance", methods=["GET"])
def api_model_performance():
    """Production model metrics from the registry."""
    from database import get_connection
    sport_filter = request.args.get("sport")

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        sql = """
            SELECT id, sport, target, model_version, status,
                   cv_folds, cv_avg_loss, cv_avg_accuracy, cv_avg_auc,
                   train_rows, feature_version, feature_count,
                   hidden_dim, dropout, learning_rate, batch_size, epochs,
                   trained_at, promoted_at
            FROM fact_model_registry
            WHERE status = 'production'
        """
        params: list = []
        if sport_filter:
            sql += " AND sport = %s"
            params.append(sport_filter)
        sql += " ORDER BY sport, target"

        cursor.execute(sql, params)
        models = cursor.fetchall()
        cursor.close()
        conn.close()

        for m in models:
            for k in ("trained_at", "promoted_at"):
                if m.get(k):
                    m[k] = str(m[k])
            for k in ("cv_avg_loss", "cv_avg_accuracy", "cv_avg_auc", "dropout", "learning_rate"):
                if m.get(k) is not None:
                    m[k] = float(m[k])

        return jsonify({"status": "ok", "models": models})
    except Exception as exc:
        logger.error("API model-performance failed: %s", exc)
        return _error(f"API model-performance failed: {exc}")


@app.route("/api/model-registry", methods=["GET"])
def api_model_registry():
    """All models (candidate + production + retired) for comparison."""
    from database import get_connection
    sport = request.args.get("sport")
    target = request.args.get("target")

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        sql = "SELECT * FROM fact_model_registry WHERE 1=1"
        params: list = []
        if sport:
            sql += " AND sport = %s"
            params.append(sport)
        if target:
            sql += " AND target = %s"
            params.append(target)
        sql += " ORDER BY trained_at DESC LIMIT 20"

        cursor.execute(sql, params)
        models = cursor.fetchall()
        cursor.close()
        conn.close()

        for m in models:
            for k in ("trained_at", "promoted_at", "retired_at"):
                if m.get(k):
                    m[k] = str(m[k])
            for k in ("cv_avg_loss", "cv_avg_accuracy", "cv_avg_auc",
                       "train_final_loss", "dropout", "learning_rate"):
                if m.get(k) is not None:
                    m[k] = float(m[k])
            # JSON fields
            for k in ("cv_fold_losses", "cv_fold_accuracies", "cv_fold_aucs"):
                if m.get(k) and isinstance(m[k], str):
                    import json
                    try:
                        m[k] = json.loads(m[k])
                    except Exception:
                        pass

        return jsonify({"status": "ok", "models": models})
    except Exception as exc:
        logger.error("API model-registry failed: %s", exc)
        return _error(f"API model-registry failed: {exc}")


@app.route("/api/model-diagnostics", methods=["GET"])
def api_model_diagnostics():
    """Detailed diagnostics: ROC curve, confusion matrix, year segments.

    Query params (required):
      sport  — "nfl" | "ncaa_mbb" | "mlb"
      target — "home_win" | "cover_home" | "total_over"
    """
    sport = request.args.get("sport", "nfl")
    target = request.args.get("target", "home_win")

    try:
        import json as _json
        import os
        import numpy as np
        import torch
        from sklearn.metrics import roc_curve, roc_auc_score, confusion_matrix

        from models.pytorch_model import SportsBinaryClassifier
        from models.modeling_data import materialize_features_to_modeling_silver, load_modeling_frame
        from features.feature_registry import FEATURE_COLUMNS, TARGET_COLUMNS
        from database import get_connection

        model_dir = os.getenv("MODEL_DIR", "/app/model_artifacts")
        target_col = TARGET_COLUMNS.get(target, f"target_{target}")

        # Try production, then candidate
        stage = "production"
        meta_path = os.path.join(model_dir, f"{sport}_{target}_{stage}_metadata.json")
        if not os.path.exists(meta_path):
            stage = "candidate"
            meta_path = os.path.join(model_dir, f"{sport}_{target}_{stage}_metadata.json")
        if not os.path.exists(meta_path):
            return jsonify({
                "status": "ok",
                "message": f"No model found for {sport}/{target}",
                "roc_fpr": [], "roc_tpr": [], "auc": None,
                "confusion_matrix": None, "year_segments": [],
                "recommendation": None,
            })

        with open(meta_path) as f:
            metadata = _json.load(f)

        model_path = os.path.join(model_dir, f"{sport}_{target}_{stage}.pt")
        feature_cols = metadata.get("feature_columns", FEATURE_COLUMNS)
        input_dim = len(feature_cols)
        hidden_dim = metadata.get("hidden_dim", 128)
        dropout = metadata.get("dropout", 0.1)

        # Load model
        model = SportsBinaryClassifier(input_dim, hidden_dim, dropout)
        model.load_state_dict(torch.load(model_path, map_location="cpu", weights_only=True))
        model.eval()

        # Load data
        materialize_features_to_modeling_silver(sport)
        df = load_modeling_frame(sport)

        if df.empty or target_col not in df.columns:
            return jsonify({
                "status": "ok", "message": "No data for diagnostics",
                "roc_fpr": [], "roc_tpr": [], "auc": None,
                "confusion_matrix": None, "year_segments": [],
                "recommendation": None,
            })

        df = df.dropna(subset=[target_col])
        if df.empty:
            return jsonify({
                "status": "ok", "message": "No labelled data",
                "roc_fpr": [], "roc_tpr": [], "auc": None,
                "confusion_matrix": None, "year_segments": [],
                "recommendation": None,
            })

        # Build feature matrix
        X = df[feature_cols].fillna(0).values.astype(np.float32)
        y_true = df[target_col].values.astype(int)

        with torch.no_grad():
            y_proba = model(torch.tensor(X)).squeeze().numpy()

        # ROC
        fpr, tpr, _ = roc_curve(y_true, y_proba)
        auc_val = float(roc_auc_score(y_true, y_proba)) if len(set(y_true)) > 1 else None

        # Confusion matrix
        y_pred = (y_proba >= 0.5).astype(int)
        cm = confusion_matrix(y_true, y_pred, labels=[1, 0])
        cm_dict = {
            "tp": int(cm[0, 0]), "fp": int(cm[1, 0]),
            "fn": int(cm[0, 1]), "tn": int(cm[1, 1]),
        }

        # Year segments
        year_segments = []
        if "game_date" in df.columns:
            df["_year"] = df["game_date"].apply(
                lambda x: x.year if hasattr(x, "year") else None
            )
            for yr, grp in df.dropna(subset=["_year"]).groupby("_year"):
                idx = grp.index
                yr_true = y_true[df.index.get_indexer(idx)]
                yr_proba = y_proba[df.index.get_indexer(idx)]
                yr_pred = (yr_proba >= 0.5).astype(int)
                yr_acc = float((yr_pred == yr_true).mean())
                try:
                    yr_auc = float(roc_auc_score(yr_true, yr_proba)) if len(set(yr_true)) > 1 else None
                except Exception:
                    yr_auc = None
                year_segments.append({
                    "year": int(yr),
                    "game_count": len(grp),
                    "accuracy": yr_acc,
                    "auc": yr_auc,
                })

        # Recommendation: compare candidate vs production
        recommendation = None
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT status, cv_avg_auc, cv_avg_accuracy, model_version
            FROM fact_model_registry
            WHERE sport = %s AND target = %s AND status IN ('production', 'candidate')
            ORDER BY trained_at DESC
            """,
            (sport, target),
        )
        reg_models = cursor.fetchall()
        cursor.close()
        conn.close()

        prod = next((m for m in reg_models if m["status"] == "production"), None)
        cand = next((m for m in reg_models if m["status"] == "candidate"), None)
        if cand and prod:
            cand_auc = float(cand["cv_avg_auc"]) if cand["cv_avg_auc"] else 0
            prod_auc = float(prod["cv_avg_auc"]) if prod["cv_avg_auc"] else 0
            if cand_auc > prod_auc + 0.005:
                recommendation = {
                    "action": "promote",
                    "reason": f"Candidate AUC ({cand_auc:.3f}) exceeds production ({prod_auc:.3f}) by {cand_auc - prod_auc:.3f}",
                }
            else:
                recommendation = {
                    "action": "keep",
                    "reason": f"Current production AUC ({prod_auc:.3f}) is comparable to candidate ({cand_auc:.3f}). No promotion needed.",
                }
        elif cand and not prod:
            recommendation = {
                "action": "promote",
                "reason": "No production model exists. Promote the candidate.",
            }

        # Downsample ROC curve points for JSON (max 200 points)
        step = max(1, len(fpr) // 200)
        fpr_list = [float(x) for x in fpr[::step]]
        tpr_list = [float(x) for x in tpr[::step]]

        return jsonify({
            "status": "ok",
            "sport": sport,
            "target": target,
            "model_stage": stage,
            "roc_fpr": fpr_list,
            "roc_tpr": tpr_list,
            "auc": auc_val,
            "confusion_matrix": cm_dict,
            "year_segments": sorted(year_segments, key=lambda x: x["year"]),
            "recommendation": recommendation,
        })
    except Exception as exc:
        logger.error("API model-diagnostics failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"API model-diagnostics failed: {exc}")


# ---------------------------------------------------------------------------
# Bracket API endpoints
# ---------------------------------------------------------------------------

@app.route("/api/bracket/simulations", methods=["GET"])
def api_bracket_simulations():
    """Return bracket simulation runs for a season.

    Query params:
      year — int, season year. Use 'all' to get list of distinct years.
    """
    from database import get_connection
    year_param = request.args.get("year", "")

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = 'modeling_internal'
              AND table_name = 'fact_bracket_simulations'
        """)
        if cursor.fetchone()["cnt"] == 0:
            cursor.close()
            conn.close()
            if year_param == "all":
                return jsonify({"status": "ok", "years": []})
            return jsonify({"status": "ok", "simulations": [], "years": []})

        if year_param == "all":
            # Return list of distinct years
            cursor.execute("SELECT DISTINCT season FROM fact_bracket_simulations ORDER BY season DESC")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            years = [r["season"] for r in rows]
            return jsonify({"status": "ok", "years": years})

        season = _safe_int(year_param, 0)
        if not season:
            cursor.close()
            conn.close()
            return jsonify({"status": "ok", "simulations": [], "years": []})

        cursor.execute("""
            SELECT simulation_id, season, num_simulations, pool_size,
                   risk_tolerance, model_version,
                   simulation_counter, priority_ranking, is_default,
                   run_batch_id, expected_score, champion_pick,
                   created_at
            FROM fact_bracket_simulations
            WHERE season = %s
            ORDER BY priority_ranking ASC, simulation_counter ASC
        """, (season,))
        rows = cursor.fetchall()

        # Also fetch distinct years for the dropdown
        cursor.execute("SELECT DISTINCT season FROM fact_bracket_simulations ORDER BY season DESC")
        year_rows = cursor.fetchall()
        cursor.close()
        conn.close()

        for r in rows:
            if r.get("created_at"):
                r["created_at"] = str(r["created_at"])
            # Map fields to what the JS expects
            r["champion"] = r.pop("champion_pick", None)
            r["expected_points"] = r.pop("expected_score", None)
            r["actual_score"] = None  # Populated by resolver in future
            r["run_time_seconds"] = None

        years = [r["season"] for r in year_rows]

        return jsonify({
            "status": "ok",
            "season": season,
            "simulations": rows,
            "years": years,
        })
    except Exception as exc:
        logger.error("API bracket/simulations failed: %s", exc)
        return _error(f"API bracket/simulations failed: {exc}")


@app.route("/api/bracket/run", methods=["POST"])
def api_bracket_run():
    """Trigger multi-run bracket simulation.

    Body (JSON):
      year     — int, tournament year (required)
      n_runs   — int, number of optimization runs (default: 10)
      mc_sims  — int, Monte Carlo sims per run (default: 10000)
    """
    payload = request.get_json(silent=True) or {}
    year = _safe_int(payload.get("year"), 0)
    if not year or year < 2000:
        return _error("Valid year is required (e.g. 2025)", status=400)

    n_runs = _safe_int(payload.get("n_runs"), 10)
    mc_sims = _safe_int(payload.get("mc_sims"), 10000)

    logger.info("POST /api/bracket/run  year=%d  n_runs=%d  mc_sims=%d", year, n_runs, mc_sims)
    try:
        from bracket.historical import run_historical_bracket
        result = run_historical_bracket(
            season=year,
            n_simulations=mc_sims,
            pool_size=_safe_int(payload.get("pool_size"), 100),
            risk_tolerance=_safe_float(payload.get("risk_tolerance"), 0.3),
            n_runs=n_runs,
            overwrite=True,
        )
        return jsonify(result)
    except Exception as exc:
        logger.error("Bracket run failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Bracket run failed: {exc}")


@app.route("/api/bracket/set-default", methods=["POST"])
def api_bracket_set_default():
    """Set a simulation as the default for its season.

    Body (JSON):
      simulation_id — int (required)
    """
    from database import get_connection
    payload = request.get_json(silent=True) or {}
    sim_id = _safe_int(payload.get("simulation_id"), 0)
    if not sim_id:
        return _error("simulation_id is required", status=400)

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        # Get the season for this simulation
        cursor.execute(
            "SELECT season FROM fact_bracket_simulations WHERE simulation_id = %s",
            (sim_id,),
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return _error("Simulation not found", status=404)

        season = row["season"]

        # Clear all defaults for this season
        cursor.execute(
            "UPDATE fact_bracket_simulations SET is_default = 0 WHERE season = %s",
            (season,),
        )
        # Set the requested one
        cursor.execute(
            "UPDATE fact_bracket_simulations SET is_default = 1 WHERE simulation_id = %s",
            (sim_id,),
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "ok", "simulation_id": sim_id, "season": season})
    except Exception as exc:
        logger.error("Set default failed: %s", exc)
        return _error(f"Set default failed: {exc}")


@app.route("/api/bracket/picks", methods=["GET"])
def api_bracket_picks():
    """Return all picks for a specific bracket simulation.

    Query params:
      simulation_id — int (required)
    """
    from database import get_connection
    sim_id = _safe_int(request.args.get("simulation_id"), 0)
    if not sim_id:
        return _error("simulation_id is required", status=400)

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        # Check if picks table exists
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = 'modeling_internal'
              AND table_name = 'fact_bracket_picks'
        """)
        if cursor.fetchone()["cnt"] == 0:
            cursor.close()
            conn.close()
            return jsonify({"status": "ok", "picks": [], "message": "No picks table"})

        cursor.execute("""
            SELECT round_number, game_number, region,
                   team_seed, team_name, opponent_seed, opponent_name,
                   win_probability, is_upset, is_contrarian,
                   actual_winner, is_correct
            FROM fact_bracket_picks
            WHERE simulation_id = %s
            ORDER BY round_number, game_number
        """, (sim_id,))
        picks = cursor.fetchall()
        cursor.close()
        conn.close()

        # Map field names
        for p in picks:
            p["round"] = p.pop("round_number", None)
            if p.get("win_probability") is not None:
                p["win_probability"] = float(p["win_probability"])
            if p.get("is_upset") is not None:
                p["is_upset"] = bool(p["is_upset"])
            if p.get("is_contrarian") is not None:
                p["is_contrarian"] = bool(p["is_contrarian"])
            if p.get("is_correct") is not None:
                p["is_correct"] = bool(p["is_correct"])

        return jsonify({"status": "ok", "simulation_id": sim_id, "picks": picks})
    except Exception as exc:
        logger.error("API bracket/picks failed: %s", exc)
        return _error(f"API bracket/picks failed: {exc}")


# ---------------------------------------------------------------------------
# Bet History API endpoints
# ---------------------------------------------------------------------------

@app.route("/api/bet-history", methods=["GET"])
def api_bet_history():
    """Return tracked bets with optional sport/week filters.

    Query params:
      sport — filter by sport (optional)
      weeks — number of weeks to look back (default: 52)
    """
    from database import get_connection
    sport = request.args.get("sport")
    weeks = _safe_int(request.args.get("weeks"), 52)

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = 'modeling_internal'
              AND table_name = 'fact_bet_tracking'
        """)
        if cursor.fetchone()["cnt"] == 0:
            cursor.close()
            conn.close()
            return jsonify({"status": "ok", "bets": []})

        sql = """
            SELECT id, game_id, sport, game_date, home_team, away_team,
                   bet_type, pick, odds_american, model_probability,
                   edge, expected_value, wager_amount,
                   actual_outcome, resolved_at, profit_loss,
                   week_number, year
            FROM fact_bet_tracking
            WHERE game_date >= DATE_SUB(CURDATE(), INTERVAL %s WEEK)
        """
        params: list = [weeks]

        if sport:
            sql += " AND sport = %s"
            params.append(sport)

        sql += " ORDER BY game_date DESC, recommended_at DESC"
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        bets = []
        for r in rows:
            # Map to what JS expects
            outcome = None
            if r.get("actual_outcome") is not None:
                outcome = "win" if r["actual_outcome"] == 1 else "loss"
            else:
                outcome = "pending"

            bets.append({
                "id": r["id"],
                "game_id": r["game_id"],
                "sport": r["sport"],
                "game_date": str(r["game_date"]) if r.get("game_date") else None,
                "home_team": r["home_team"],
                "away_team": r["away_team"],
                "target": r["bet_type"],
                "pick": r["pick"],
                "moneyline": r.get("odds_american"),
                "model_prob": float(r["model_probability"]) if r.get("model_probability") is not None else None,
                "edge": float(r["edge"]) if r.get("edge") is not None else None,
                "wager": float(r["wager_amount"]) if r.get("wager_amount") is not None else 0,
                "outcome": outcome,
                "pl": float(r["profit_loss"]) if r.get("profit_loss") is not None else None,
            })

        return jsonify({"status": "ok", "bets": bets})
    except Exception as exc:
        logger.error("API bet-history failed: %s", exc)
        return _error(f"API bet-history failed: {exc}")


@app.route("/api/bet-history/summary", methods=["GET"])
def api_bet_history_summary():
    """Return high-level bet tracking stats."""
    from database import get_connection

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = 'modeling_internal'
              AND table_name = 'fact_bet_tracking'
        """)
        if cursor.fetchone()["cnt"] == 0:
            cursor.close()
            conn.close()
            return jsonify({
                "status": "ok",
                "summary": {
                    "total_bets": 0, "win_rate": None,
                    "total_pl": 0, "best_week_pl": 0,
                },
            })

        # Overall stats
        cursor.execute("""
            SELECT
                COUNT(*) AS total_bets,
                SUM(CASE WHEN actual_outcome = 1 THEN 1 ELSE 0 END) AS wins,
                SUM(CASE WHEN actual_outcome = 0 THEN 1 ELSE 0 END) AS losses,
                SUM(CASE WHEN actual_outcome IS NOT NULL THEN 1 ELSE 0 END) AS resolved,
                COALESCE(SUM(profit_loss), 0) AS total_pl,
                COALESCE(SUM(wager_amount), 0) AS total_wagered
            FROM fact_bet_tracking
        """)
        stats = cursor.fetchone()

        resolved = int(stats["resolved"] or 0)
        wins = int(stats["wins"] or 0)
        win_rate = wins / resolved if resolved > 0 else None

        # Best/worst week
        cursor.execute("""
            SELECT year, week_number, SUM(profit_loss) AS week_pl
            FROM fact_bet_tracking
            WHERE actual_outcome IS NOT NULL AND week_number IS NOT NULL
            GROUP BY year, week_number
            ORDER BY week_pl DESC
        """)
        week_rows = cursor.fetchall()
        cursor.close()
        conn.close()

        best_week_pl = float(week_rows[0]["week_pl"]) if week_rows else 0
        worst_week_pl = float(week_rows[-1]["week_pl"]) if week_rows else 0

        return jsonify({
            "status": "ok",
            "summary": {
                "total_bets": int(stats["total_bets"] or 0),
                "resolved_bets": resolved,
                "wins": wins,
                "losses": int(stats["losses"] or 0),
                "pending": int(stats["total_bets"] or 0) - resolved,
                "win_rate": round(win_rate, 4) if win_rate is not None else None,
                "total_pl": round(float(stats["total_pl"]), 2),
                "total_wagered": round(float(stats["total_wagered"]), 2),
                "roi": round(float(stats["total_pl"]) / float(stats["total_wagered"]), 4) if float(stats["total_wagered"]) > 0 else 0,
                "best_week_pl": round(best_week_pl, 2),
                "worst_week_pl": round(worst_week_pl, 2),
            },
        })
    except Exception as exc:
        logger.error("API bet-history/summary failed: %s", exc)
        return _error(f"API bet-history/summary failed: {exc}")


# ---------------------------------------------------------------------------
# Backtest API endpoint
# ---------------------------------------------------------------------------

@app.route("/api/backtest", methods=["GET"])
def api_backtest():
    """Run historical backtest for a sport/target combination.

    Query params:
      sport   — "nfl" | "ncaa_mbb" | "mlb" (required)
      target  — "home_win" | "cover_home" | "total_over" (required)
      months  — int, lookback months (default: 24)
    """
    sport = request.args.get("sport", "nfl")
    target = request.args.get("target", "home_win")
    months = _safe_int(request.args.get("months"), 24)

    logger.info("GET /api/backtest  sport=%s  target=%s  months=%d", sport, target, months)
    try:
        from models.backtest import run_backtest
        result = run_backtest(
            sport=sport,
            target=target,
            months=months,
            weekly_bankroll=100.0,
            max_pct=0.50,
        )
        return jsonify(result)
    except Exception as exc:
        logger.error("Backtest failed: %s\n%s", exc, traceback.format_exc())
        return _error(f"Backtest failed: {exc}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
