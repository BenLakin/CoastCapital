"""
update_pipeline.py — Daily incremental ingest for one or all sports.

Designed to be triggered by n8n on a schedule (e.g. nightly).  Each sport
is ingested independently so a failure in one does not block the others.
"""

import logging
from datetime import datetime, timezone

from ingestion import mlb_ingest, ncaa_mbb_ingest, nfl_ingest

logger = logging.getLogger(__name__)

SUPPORTED_SPORTS = ("nfl", "ncaa_mbb", "mlb")


def run_update_pipeline(sport: str = "all", date_str: str | None = None) -> dict:
    """Ingest the latest game data for *sport* on *date_str*.

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, ``"mlb"``, or ``"all"``.
    date_str:
        ISO date string ``"YYYY-MM-DD"``.  Defaults to today (UTC) when omitted.

    Returns
    -------
    dict
        ``{"sport": ..., "date": ..., "results": {...}, "status": "ok"|"partial_error"}``
    """
    if not date_str:
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    sports_to_run = SUPPORTED_SPORTS if sport == "all" else [sport]
    logger.info("update_pipeline: sport=%s  date=%s", sport, date_str)

    results = {}
    had_error = False

    for current_sport in sports_to_run:
        try:
            if current_sport == "nfl":
                nfl_ingest.insert_nfl_data(date_str)
            elif current_sport == "ncaa_mbb":
                ncaa_mbb_ingest.insert_ncaa_mbb_data(date_str)
            elif current_sport == "mlb":
                mlb_ingest.insert_mlb_data(date_str)
            else:
                raise ValueError(f"Unsupported sport: {current_sport}")
            results[current_sport] = "ok"
            logger.info("update_pipeline: %s — done", current_sport)
        except Exception as exc:
            logger.error("update_pipeline: %s failed — %s", current_sport, exc, exc_info=True)
            results[current_sport] = f"error: {exc}"
            had_error = True

    # --- News ingest (non-fatal) ---
    try:
        from ingestion.news_ingest import ingest_news
        news_result = ingest_news(sport=sport, summarize=True)
        results["news"] = news_result.get("results", "ok")
    except Exception as exc:
        logger.warning("update_pipeline: news ingest failed (non-fatal) — %s", exc)
        results["news"] = f"skipped: {exc}"

    return {
        "sport": sport,
        "date": date_str,
        "results": results,
        "status": "partial_error" if had_error else "ok",
    }
