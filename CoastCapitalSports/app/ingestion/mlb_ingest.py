"""
mlb_ingest.py — ESPN data ingestion for the MLB silver layer.

Public entry point: ``insert_mlb_data(date_str)``
"""

import logging
from datetime import datetime, timezone

import requests

from database import get_connection
from ingestion.schema_sync import dynamic_upsert

logger = logging.getLogger(__name__)

SCHEMA = "mlb_silver"

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/baseball/mlb/summary"


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def fetch_espn_scoreboard(date_str=None):
    """Fetch MLB scoreboard events from the ESPN API.

    Parameters
    ----------
    date_str:
        ISO date string ``"YYYY-MM-DD"``.  Omit to get today's games.

    Returns
    -------
    list of event dicts.

    Raises
    ------
    requests.HTTPError
        If the ESPN API returns a non-2xx status.
    """
    params = {}
    if date_str:
        params["dates"] = date_str.replace("-", "")
    logger.debug("fetch_espn_scoreboard: GET %s  params=%s", ESPN_SCOREBOARD_URL, params)
    response = requests.get(ESPN_SCOREBOARD_URL, params=params, timeout=30)
    response.raise_for_status()
    events = response.json().get("events", [])
    logger.info("fetch_espn_scoreboard: %d events for date=%s", len(events), date_str)
    return events


def fetch_espn_summary(event_id):
    """Fetch the boxscore summary for a single event.

    Parameters
    ----------
    event_id: ESPN event ID string.

    Returns
    -------
    dict of summary data.

    Raises
    ------
    requests.HTTPError
    """
    response = requests.get(ESPN_SUMMARY_URL, params={"event": event_id}, timeout=30)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

def _extract_round_name(event, comp):
    """Return the best available round/week label for a game."""
    candidates = [
        comp.get("status", {}).get("type", {}).get("name"),
        comp.get("status", {}).get("type", {}).get("shortName"),
        event.get("week", {}).get("text"),
        event.get("seasonType", {}).get("name"),
        event.get("name"),
        event.get("shortName"),
    ]
    for c in candidates:
        if c:
            return str(c)
    return ""


def _is_postseason(round_name):
    """Return 1 if *round_name* indicates a postseason game, else 0."""
    text = str(round_name).lower()
    return int(any(x in text for x in [
        "wild card", "division series", "championship series", "world series",
        "postseason", "playoff", "alds", "nlds", "alcs", "nlcs",
    ]))


# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------

def insert_mlb_data(date_str=None):
    """Ingest all MLB data for *date_str* into mlb_silver.

    Fetches ESPN scoreboard events and upserts game results and market odds.

    Parameters
    ----------
    date_str:
        ISO date string ``"YYYY-MM-DD"``.  Defaults to today (UTC) when omitted.

    Raises
    ------
    Exception
        Re-raised if the DB connection fails.  Per-game errors are logged
        and skipped.
    """
    if not date_str:
        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

    logger.info("insert_mlb_data: date=%s", date_str)
    conn = get_connection(SCHEMA)
    cursor = conn.cursor()

    events = fetch_espn_scoreboard(date_str)
    games_processed = 0

    for event in events:
        game_id = event.get("id", "unknown")
        try:
            comp = event["competitions"][0]
            home = next(t for t in comp["competitors"] if t["homeAway"] == "home")
            away = next(t for t in comp["competitors"] if t["homeAway"] == "away")

            home_score = int(home.get("score", 0))
            away_score = int(away.get("score", 0))
            margin = home_score - away_score
            round_name = _extract_round_name(event, comp)
            is_postseason_game = _is_postseason(round_name)

            dynamic_upsert(cursor, SCHEMA, "fact_game_results", {
                "game_id": game_id,
                "game_date": comp.get("date"),
                "home_team": home["team"]["displayName"],
                "away_team": away["team"]["displayName"],
                "home_score": home_score,
                "away_score": away_score,
                "margin": margin,
                "is_postseason_game": is_postseason_game,
                "round_name": round_name,
                "playoff_experience_home": 0.0,
                "playoff_experience_away": 0.0,
            })

            for odds in comp.get("odds", []):
                provider = (odds.get("provider") or {}).get("name", "Unknown")
                ml_home = (odds.get("homeTeamOdds") or {}).get("moneyLine")
                ml_away = (odds.get("awayTeamOdds") or {}).get("moneyLine")
                total_line = odds.get("overUnder")

                dynamic_upsert(cursor, SCHEMA, "fact_market_odds", {
                    "game_id": game_id,
                    "sportsbook": provider,
                    "moneyline_home": ml_home,
                    "moneyline_away": ml_away,
                    "total_line": total_line,
                    "market_timestamp": datetime.now(),
                }, on_duplicate_update=False)

            # Fetch summary for potential future enrichment; errors are non-fatal
            try:
                fetch_espn_summary(game_id)
            except Exception as exc:
                logger.debug("insert_mlb_data: summary fetch skipped for game=%s — %s", game_id, exc)

            games_processed += 1

        except Exception as exc:
            logger.error(
                "insert_mlb_data: failed on game_id=%s — %s", game_id, exc, exc_info=True
            )

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("insert_mlb_data: committed %d games for date=%s", games_processed, date_str)
