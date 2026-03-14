"""
backfill_pipeline.py — Historical data backfill for one or all sports.

Iterates over a date range (or derives one from a season year) and calls
each sport's ingest function for every date.  Each sport is processed
independently so a failure in one does not block the others.
"""

import logging

from ingestion import mlb_ingest, ncaa_mbb_ingest, nfl_ingest
from pipelines.date_utils import default_season_window, iter_dates

logger = logging.getLogger(__name__)

SUPPORTED_SPORTS = ("nfl", "ncaa_mbb", "mlb")


def backfill_sport(sport: str, start_date: str, end_date: str) -> dict:
    """Backfill *sport* data for every date in [*start_date*, *end_date*].

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, or ``"mlb"``.
    start_date, end_date:
        ISO date strings ``"YYYY-MM-DD"`` (inclusive).

    Returns
    -------
    dict with keys ``sport``, ``start_date``, ``end_date``, ``processed_dates``,
    ``failed_dates``, ``status``.

    Raises
    ------
    ValueError
        If *sport* is not supported.
    """
    if sport not in SUPPORTED_SPORTS:
        raise ValueError(f"Unsupported sport: {sport}")

    logger.info("backfill_sport: sport=%s  %s → %s", sport, start_date, end_date)

    processed_dates = 0
    failed_dates = []

    for date_str in iter_dates(start_date, end_date):
        try:
            if sport == "nfl":
                nfl_ingest.insert_nfl_data(date_str)
            elif sport == "ncaa_mbb":
                ncaa_mbb_ingest.insert_ncaa_mbb_data(date_str)
            elif sport == "mlb":
                mlb_ingest.insert_mlb_data(date_str)
            processed_dates += 1
        except Exception as exc:
            logger.error(
                "backfill_sport: %s  %s failed — %s", sport, date_str, exc, exc_info=True
            )
            failed_dates.append(date_str)

    status = "ok" if not failed_dates else "partial_error"
    return {
        "sport": sport,
        "start_date": start_date,
        "end_date": end_date,
        "processed_dates": processed_dates,
        "failed_dates": failed_dates,
        "status": status,
    }


def run_backfill_pipeline(
    sport: str = "all",
    start_date: str | None = None,
    end_date: str | None = None,
    season: int | None = None,
) -> dict:
    """Run the backfill pipeline for one or all sports.

    Parameters
    ----------
    sport:
        ``"all"`` or one of the supported sport keys.
    start_date, end_date:
        Override the date window (ISO strings).
    season:
        Integer year.  Used to derive *start_date* / *end_date* if they are
        not provided.

    Returns
    -------
    dict with ``results`` list and top-level ``status``.

    Raises
    ------
    ValueError
        When neither a date range nor a season is supplied.
    """
    sports_to_run = list(SUPPORTED_SPORTS) if sport == "all" else [sport]
    logger.info(
        "run_backfill_pipeline: sports=%s  start=%s  end=%s  season=%s",
        sports_to_run, start_date, end_date, season,
    )

    outputs = []
    had_error = False

    for current_sport in sports_to_run:
        current_start = start_date
        current_end = end_date

        if season is not None and (not current_start or not current_end):
            current_start, current_end = default_season_window(current_sport, int(season))

        if not current_start or not current_end:
            raise ValueError(
                f"Provide start_date and end_date, or provide season. "
                f"(sport={current_sport})"
            )

        result = backfill_sport(current_sport, current_start, current_end)
        outputs.append(result)
        if result["status"] != "ok":
            had_error = True

    return {
        "results": outputs,
        "status": "partial_error" if had_error else "ok",
    }
