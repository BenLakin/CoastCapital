"""
daily_sport_pipeline.py — Daily automated pipeline for MLB and NCAA MBB.

Orchestrates the full daily workflow:
  1. Ingest latest game data and market odds
  2. Materialize features to modeling_silver
  3. Score recent games with production model
  4. Ingest sports news
  5. Generate betting recommendations

Designed to run via cron, n8n, or the /daily-pipeline API endpoint.

Public entry points:
  - ``run_daily_pipeline(sports, date_str, skip_news, skip_betting)``
  - ``run_daily_mlb(date_str)``
  - ``run_daily_ncaa_mbb(date_str)``
"""

import logging
from datetime import datetime, timezone

from ingestion import mlb_ingest, ncaa_mbb_ingest, nfl_ingest
from models.modeling_data import materialize_features_to_modeling_silver
from models.score_torch_model import score_model

logger = logging.getLogger(__name__)


def _ingest_sport(sport: str, date_str: str) -> dict:
    """Ingest game data for a single sport/date."""
    try:
        if sport == "mlb":
            mlb_ingest.insert_mlb_data(date_str)
        elif sport == "ncaa_mbb":
            ncaa_mbb_ingest.insert_ncaa_mbb_data(date_str)
        elif sport == "nfl":
            nfl_ingest.insert_nfl_data(date_str)
        else:
            return {"status": "error", "message": f"Unsupported sport: {sport}"}
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Ingest failed for %s on %s: %s", sport, date_str, exc, exc_info=True)
        return {"status": "error", "message": str(exc)}


def _materialize_sport(sport: str) -> dict:
    """Materialize features for a single sport."""
    try:
        result = materialize_features_to_modeling_silver(sport)
        return {"status": "ok", "rows_written": result.get("rows_written", 0)}
    except Exception as exc:
        logger.error("Materialize failed for %s: %s", sport, exc, exc_info=True)
        return {"status": "error", "message": str(exc)}


def _score_sport(sport: str, targets: list[str] | None = None) -> dict:
    """Score recent games for a sport across all targets."""
    if targets is None:
        targets = ["home_win", "cover_home", "total_over"]

    scores = {}
    for target in targets:
        try:
            result = score_model(sport=sport, target=target, limit=50)
            scores[target] = {
                "status": "ok",
                "rows_scored": result.get("rows_scored", 0),
                "model_stage": result.get("model_stage"),
            }
        except ValueError:
            # No model available — skip silently
            scores[target] = {"status": "skipped", "message": "no model available"}
        except Exception as exc:
            logger.warning("Score failed for %s/%s: %s", sport, target, exc)
            scores[target] = {"status": "error", "message": str(exc)}

    return scores


def _ingest_news(sport: str) -> dict:
    """Ingest news for a sport."""
    try:
        from ingestion.news_ingest import ingest_news
        result = ingest_news(sport=sport, summarize=True)
        return {"status": "ok", "articles": result.get("total_articles", 0)}
    except Exception as exc:
        logger.warning("News ingest failed for %s (non-fatal): %s", sport, exc)
        return {"status": "skipped", "message": str(exc)}


def _resolve_bets() -> dict:
    """Resolve pending bets from previous days."""
    try:
        from betting.bet_resolver import resolve_pending_bets
        result = resolve_pending_bets()
        return {"status": "ok", "resolved": result.get("resolved_count", 0)}
    except Exception as exc:
        logger.warning("Bet resolution failed (non-fatal): %s", exc)
        return {"status": "skipped", "message": str(exc)}


def _generate_betting_recs(bankroll: float = 50.0, max_pct: float = 0.50) -> dict:
    """Generate betting recommendations."""
    try:
        from betting.recommender import get_betting_recommendations
        result = get_betting_recommendations(bankroll=bankroll, max_pct=max_pct)
        return {
            "status": "ok",
            "bet_count": result.get("bet_count", 0),
            "total_wagered": result.get("total_wagered", 0),
            "sports_covered": result.get("sports_covered", []),
        }
    except Exception as exc:
        logger.warning("Betting recommendations failed (non-fatal): %s", exc)
        return {"status": "skipped", "message": str(exc)}


def run_daily_pipeline(
    sports: list[str] | None = None,
    date_str: str | None = None,
    skip_news: bool = False,
    skip_betting: bool = False,
    bankroll: float = 50.0,
    max_pct: float = 0.50,
) -> dict:
    """Run the full daily pipeline for specified sports.

    Parameters
    ----------
    sports : list of str
        Sports to process. Defaults to ["mlb", "ncaa_mbb"].
    date_str : str
        ISO date string. Defaults to today UTC.
    skip_news : bool
        Skip news ingestion step.
    skip_betting : bool
        Skip betting recommendation step.
    bankroll : float
        Bankroll for betting recommendations.
    max_pct : float
        Max fraction per game for betting.

    Returns
    -------
    dict with per-sport results and overall status.
    """
    if sports is None:
        sports = ["mlb", "ncaa_mbb"]
    if not date_str:
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    logger.info(
        "daily_pipeline: sports=%s date=%s skip_news=%s skip_betting=%s",
        sports, date_str, skip_news, skip_betting,
    )

    pipeline_start = datetime.now(tz=timezone.utc)
    sport_results = {}
    had_error = False

    # Step 0: Resolve pending bets from previous days
    logger.info("daily_pipeline: Step 0 — Resolve pending bets")
    resolve_result = _resolve_bets()

    for sport in sports:
        logger.info("daily_pipeline: === %s ===", sport.upper())
        sport_result = {}

        # Step 1: Ingest
        logger.info("daily_pipeline: [%s] Step 1 — Ingest", sport)
        sport_result["ingest"] = _ingest_sport(sport, date_str)
        if sport_result["ingest"]["status"] == "error":
            had_error = True

        # Step 2: Materialize features
        logger.info("daily_pipeline: [%s] Step 2 — Materialize features", sport)
        sport_result["materialize"] = _materialize_sport(sport)
        if sport_result["materialize"]["status"] == "error":
            had_error = True

        # Step 3: Score with production models
        logger.info("daily_pipeline: [%s] Step 3 — Score games", sport)
        sport_result["scores"] = _score_sport(sport)

        # Step 4: News
        if not skip_news:
            logger.info("daily_pipeline: [%s] Step 4 — News ingest", sport)
            sport_result["news"] = _ingest_news(sport)

        sport_results[sport] = sport_result

    # Step 5: Betting recommendations (cross-sport)
    betting_result = None
    if not skip_betting:
        logger.info("daily_pipeline: Step 5 — Betting recommendations")
        betting_result = _generate_betting_recs(bankroll, max_pct)

    elapsed = (datetime.now(tz=timezone.utc) - pipeline_start).total_seconds()

    return {
        "date": date_str,
        "sports": sports,
        "bet_resolution": resolve_result,
        "sport_results": sport_results,
        "betting": betting_result,
        "elapsed_seconds": round(elapsed, 2),
        "status": "partial_error" if had_error else "ok",
    }


def run_daily_mlb(date_str: str | None = None) -> dict:
    """Convenience: daily pipeline for MLB only."""
    return run_daily_pipeline(sports=["mlb"], date_str=date_str)


def run_daily_ncaa_mbb(date_str: str | None = None) -> dict:
    """Convenience: daily pipeline for NCAA MBB only."""
    return run_daily_pipeline(sports=["ncaa_mbb"], date_str=date_str)
