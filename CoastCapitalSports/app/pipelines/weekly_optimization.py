"""
weekly_optimization.py — Weekly model optimization and betting plan.

Runs once per week (e.g. Monday morning) to:
  1. Backfill any missed days from the past week
  2. Materialize features for all active sports
  3. Check model staleness — REPORT only (no auto-refit)
  4. Generate the weekly $50 betting plan with optimized allocations
  5. Store the weekly plan in the database for dashboard consumption

Model refitting is user-triggered via the /refit-model endpoint and
the Model Diagnostics dashboard.

Public entry point: ``run_weekly_optimization(bankroll, max_pct, force_refit)``
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from database import get_connection
from ingestion import mlb_ingest, ncaa_mbb_ingest
from models.modeling_data import materialize_features_to_modeling_silver

logger = logging.getLogger(__name__)

# Sports to include in the weekly optimization
ACTIVE_SPORTS = ["mlb", "ncaa_mbb"]

# Targets to train/evaluate
TARGETS = ["home_win", "cover_home", "total_over"]

# Staleness threshold — for REPORTING only (no auto-refit)
STALE_MODEL_DAYS = 14


def _backfill_week(sports: list[str], end_date: str | None = None) -> dict:
    """Backfill the past 7 days for each sport (catch up on any missed days).

    Returns dict of sport -> {processed, failed}.
    """
    if not end_date:
        end_date = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    start_dt = end_dt - timedelta(days=7)

    results = {}
    for sport in sports:
        processed = 0
        failed = []
        current = start_dt
        while current <= end_dt:
            date_str = current.isoformat()
            try:
                if sport == "mlb":
                    mlb_ingest.insert_mlb_data(date_str)
                elif sport == "ncaa_mbb":
                    ncaa_mbb_ingest.insert_ncaa_mbb_data(date_str)
                processed += 1
            except Exception as exc:
                logger.warning("Weekly backfill %s %s failed: %s", sport, date_str, exc)
                failed.append(date_str)
            current += timedelta(days=1)

        results[sport] = {"processed": processed, "failed": failed}
        logger.info(
            "Weekly backfill %s: %d processed, %d failed",
            sport, processed, len(failed),
        )

    return results


def _check_model_staleness(sport: str, target: str) -> dict:
    """Check if the production model needs refitting.

    Returns dict with 'stale' bool, 'days_old', 'model_version'.
    NOTE: This is for REPORTING only — the weekly pipeline no longer auto-refits.
    """
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT model_version, trained_at, cv_avg_accuracy, cv_avg_auc
            FROM fact_model_registry
            WHERE sport = %s AND target = %s AND status = 'production'
            ORDER BY promoted_at DESC
            LIMIT 1
            """,
            (sport, target),
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            return {
                "stale": True,
                "days_old": None,
                "model_version": None,
                "reason": "no production model",
                "action_needed": "refit",
            }

        trained_at = row["trained_at"]
        if trained_at:
            days_old = (datetime.now(tz=timezone.utc) - trained_at.replace(tzinfo=timezone.utc)).days
        else:
            days_old = 999

        stale = days_old > STALE_MODEL_DAYS
        return {
            "stale": stale,
            "days_old": days_old,
            "model_version": row["model_version"],
            "cv_avg_accuracy": float(row["cv_avg_accuracy"]) if row.get("cv_avg_accuracy") else None,
            "cv_avg_auc": float(row["cv_avg_auc"]) if row.get("cv_avg_auc") else None,
            "reason": f"model is {days_old} days old (threshold: {STALE_MODEL_DAYS})" if stale else "model is current",
            "action_needed": "refit" if stale else "none",
        }
    except Exception as exc:
        logger.warning("Staleness check failed for %s/%s: %s", sport, target, exc)
        return {
            "stale": True,
            "days_old": None,
            "model_version": None,
            "reason": f"check failed: {exc}",
            "action_needed": "investigate",
        }


def _generate_weekly_plan(bankroll: float, max_pct: float) -> dict:
    """Generate the optimized weekly betting plan."""
    try:
        from betting.recommender import get_betting_recommendations
        return get_betting_recommendations(bankroll=bankroll, max_pct=max_pct)
    except Exception as exc:
        logger.error("Weekly betting plan generation failed: %s", exc, exc_info=True)
        return {"bets": [], "error": str(exc)}


def _store_weekly_plan(plan: dict) -> int | None:
    """Store the weekly betting plan in the database for dashboard access.

    Returns the inserted row id, or None on failure.
    """
    if not plan.get("bets"):
        return None

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_weekly_betting_plans (
                id INT AUTO_INCREMENT PRIMARY KEY,
                week_start DATE NOT NULL,
                bankroll DOUBLE NOT NULL,
                max_per_game DOUBLE NOT NULL,
                total_wagered DOUBLE,
                bet_count INT,
                plan_json JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_week_start (week_start)
            )
        """)

        # Calculate week start (Monday)
        today = datetime.now(tz=timezone.utc).date()
        week_start = today - timedelta(days=today.weekday())

        cursor.execute(
            """
            INSERT INTO fact_weekly_betting_plans
                (week_start, bankroll, max_per_game, total_wagered, bet_count, plan_json)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                week_start,
                plan.get("bankroll", 50),
                plan.get("max_per_game", 25),
                plan.get("total_wagered", 0),
                plan.get("bet_count", 0),
                json.dumps(plan),
            ),
        )
        row_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        logger.info("Stored weekly betting plan id=%d for week=%s", row_id, week_start)
        return row_id

    except Exception as exc:
        logger.warning("Failed to store weekly plan: %s", exc)
        return None


def run_weekly_optimization(
    bankroll: float = 50.0,
    max_pct: float = 0.50,
    force_refit: bool = False,
    sports: list[str] | None = None,
) -> dict:
    """Run the full weekly optimization cycle.

    Steps:
      1. Backfill any missed days from the past week
      2. Materialize features
      3. Check model staleness (REPORT ONLY — no auto-refit)
      4. Generate optimized weekly betting plan
      5. Store the plan for dashboard consumption

    Parameters
    ----------
    bankroll : float
        Total weekly bankroll (default: $50).
    max_pct : float
        Max fraction on any single game (default: 50%).
    force_refit : bool
        Ignored — model refit is now user-triggered via the dashboard.
        Kept for API backwards compatibility.
    sports : list of str
        Sports to optimize. Defaults to ["mlb", "ncaa_mbb"].

    Returns
    -------
    dict with results for each step and the final betting plan.
    """
    if sports is None:
        sports = ACTIVE_SPORTS

    pipeline_start = datetime.now(tz=timezone.utc)
    logger.info(
        "weekly_optimization: START sports=%s bankroll=%.2f max_pct=%.2f",
        sports, bankroll, max_pct,
    )

    if force_refit:
        logger.info(
            "weekly_optimization: force_refit=True is ignored — "
            "model refit is now user-triggered via /refit-model endpoint"
        )

    # Step 1: Backfill the past week
    logger.info("weekly_optimization: Step 1 — Backfill past week")
    backfill_results = _backfill_week(sports)

    # Step 2: Materialize features
    logger.info("weekly_optimization: Step 2 — Materialize features")
    materialize_results = {}
    for sport in sports:
        try:
            result = materialize_features_to_modeling_silver(sport)
            materialize_results[sport] = {
                "status": "ok",
                "rows_written": result.get("rows_written", 0),
            }
        except Exception as exc:
            logger.error("Materialize failed for %s: %s", sport, exc)
            materialize_results[sport] = {"status": "error", "message": str(exc)}

    # Step 3: Model staleness check (REPORT ONLY — no auto-refit)
    logger.info("weekly_optimization: Step 3 — Model staleness report")
    staleness_report = {}
    stale_models = []
    for sport in sports:
        staleness_report[sport] = {}
        for target in TARGETS:
            check = _check_model_staleness(sport, target)
            staleness_report[sport][target] = check
            if check.get("stale"):
                stale_models.append({
                    "sport": sport,
                    "target": target,
                    "days_old": check.get("days_old"),
                    "reason": check.get("reason"),
                })

    if stale_models:
        logger.warning(
            "weekly_optimization: %d stale models detected — "
            "use POST /refit-model to refit manually",
            len(stale_models),
        )

    # Step 4: Generate weekly betting plan
    logger.info("weekly_optimization: Step 4 — Generate betting plan")
    betting_plan = _generate_weekly_plan(bankroll, max_pct)

    # Step 5: Store the plan
    logger.info("weekly_optimization: Step 5 — Store plan")
    plan_id = _store_weekly_plan(betting_plan)

    elapsed = (datetime.now(tz=timezone.utc) - pipeline_start).total_seconds()

    # Build summary
    total_bets = betting_plan.get("bet_count", 0)
    total_wagered = betting_plan.get("total_wagered", 0)

    logger.info(
        "weekly_optimization: DONE in %.1fs — %d bets, $%.2f wagered, %d stale models",
        elapsed, total_bets, total_wagered, len(stale_models),
    )

    return {
        "status": "ok",
        "sports": sports,
        "backfill": backfill_results,
        "materialize": materialize_results,
        "model_staleness": staleness_report,
        "stale_models": stale_models,
        "betting_plan": {
            "plan_id": plan_id,
            "bankroll": bankroll,
            "max_per_game": round(bankroll * max_pct, 2),
            "bet_count": total_bets,
            "total_wagered": total_wagered,
            "remaining_bankroll": betting_plan.get("remaining_bankroll", 0),
            "bets": betting_plan.get("bets", []),
            "generated_at": betting_plan.get("generated_at"),
        },
        "summary": {
            "stale_models_count": len(stale_models),
            "total_bets": total_bets,
            "total_wagered": total_wagered,
            "elapsed_seconds": round(elapsed, 2),
            "refit_note": (
                "Model refit is user-triggered. Visit /dashboard/model-diagnostics to review and refit."
                if stale_models else "All models are current."
            ),
        },
    }
