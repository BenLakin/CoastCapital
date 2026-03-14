"""
nfl_ingest.py — ESPN data ingestion for the NFL silver layer.

Fetches scoreboard, game stats, weather context, team standings, and injury
reports from the ESPN public APIs and upserts them into the nfl_silver schema.

Public entry point: ``insert_nfl_data(date_str)``
"""

import logging
from datetime import datetime

import requests

from database import get_connection
from ingestion.schema_sync import dynamic_upsert

logger = logging.getLogger(__name__)

SCHEMA = "nfl_silver"

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"
ESPN_INJURIES_URL = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/teams/{team_id}/injuries"

# ---------------------------------------------------------------------------
# Scoreboard helpers
# ---------------------------------------------------------------------------

def _parse_record(records, record_type="total"):
    """Extract wins and losses from a competitor's records list.

    Parameters
    ----------
    records:   list of record dicts from the ESPN API.
    record_type: ``"total"``, ``"home"``, or ``"road"``.

    Returns
    -------
    (wins, losses) as ints, or (0, 0) if not found.
    """
    for r in records:
        if r.get("type", "").lower() == record_type.lower() or r.get("name", "").lower() == record_type.lower():
            summary = r.get("summary", "0-0")
            parts = summary.split("-")
            if len(parts) >= 2:
                try:
                    return int(parts[0]), int(parts[1])
                except ValueError:
                    pass
    return 0, 0


def _compute_streak(cursor, team, before_date):
    """Compute the current win/loss streak for *team* before *before_date*.

    A positive integer means a win streak; negative means a losing streak.

    Parameters
    ----------
    cursor:      Active MySQL cursor connected to nfl_silver.
    team:        Team display name.
    before_date: ISO datetime string; only games strictly before this date count.

    Returns
    -------
    int streak value (0 if no history found).
    """
    cursor.execute(
        """
        SELECT home_team, away_team, margin FROM fact_game_results
        WHERE (home_team = %s OR away_team = %s) AND game_date < %s
        ORDER BY game_date DESC LIMIT 10
        """,
        (team, team, before_date),
    )
    rows = cursor.fetchall()
    if not rows:
        return 0
    streak = 0
    for home_team, away_team, margin in rows:
        is_win = (home_team == team and margin > 0) or (away_team == team and margin < 0)
        if streak == 0:
            streak = 1 if is_win else -1
        elif (streak > 0 and is_win) or (streak < 0 and not is_win):
            streak += 1 if is_win else -1
        else:
            break
    return streak


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
        "wild card", "divisional", "conference championship",
        "afc championship", "nfc championship", "super bowl", "playoff",
    ]))


# ---------------------------------------------------------------------------
# Game stats helpers (boxscore from /summary)
# ---------------------------------------------------------------------------

def _safe_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _parse_stat(stats, name):
    for s in stats:
        if s.get("name") == name:
            return s.get("displayValue")
    return None


def _parse_fraction(val):
    """Parse a fraction string like ``"4-16"`` → ``(first=4, second=16)``."""
    if not val:
        return None, None
    parts = str(val).split("-")
    if len(parts) == 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return None, None


def _parse_possession(val):
    """Parse a possession string like ``"33:11"`` → seconds as int."""
    if not val:
        return None
    parts = str(val).split(":")
    if len(parts) == 2:
        try:
            return int(parts[0]) * 60 + int(parts[1])
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# Injury helpers
# ---------------------------------------------------------------------------

def _normalize_status(raw):
    """Normalise a raw injury status string to a short canonical code."""
    s = str(raw).lower().replace("injury_status_", "")
    for code in ("out", "ir", "doubtful", "questionable", "probable", "active"):
        if code in s:
            return code
    return s[:30] if s else "unknown"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------

def fetch_nfl_data(date_str=None):
    """Fetch NFL scoreboard events from the ESPN API.

    Parameters
    ----------
    date_str:
        ISO date string ``"YYYY-MM-DD"``.  Omit to get today's games.

    Returns
    -------
    list of event dicts from the ESPN ``events`` array.

    Raises
    ------
    requests.HTTPError
        If the ESPN API returns a non-2xx status.
    """
    params = {}
    if date_str:
        params["dates"] = date_str.replace("-", "")
    logger.debug("fetch_nfl_data: GET %s  params=%s", ESPN_SCOREBOARD_URL, params)
    response = requests.get(ESPN_SCOREBOARD_URL, params=params, timeout=30)
    response.raise_for_status()
    events = response.json().get("events", [])
    logger.info("fetch_nfl_data: %d events for date=%s", len(events), date_str)
    return events


# ---------------------------------------------------------------------------
# Per-game enrichment: boxscore stats
# ---------------------------------------------------------------------------

def _insert_game_stats(cursor, game_id):
    """Fetch and upsert team-level boxscore stats for *game_id*.

    Silently skips if the summary API call fails (game may not be final yet).
    """
    try:
        resp = requests.get(ESPN_SUMMARY_URL, params={"event": game_id}, timeout=30)
        resp.raise_for_status()
        teams = resp.json().get("boxscore", {}).get("teams", [])
    except Exception as exc:
        logger.warning("_insert_game_stats: skipping game_id=%s — %s", game_id, exc)
        return

    for entry in teams:
        team_name = entry.get("team", {}).get("displayName", "")
        side = entry.get("homeAway", "home")
        stats = entry.get("statistics", [])

        total_yards = _safe_int(_parse_stat(stats, "totalYards"))
        passing_yards = _safe_int(_parse_stat(stats, "netPassingYards"))
        rushing_yards = _safe_int(_parse_stat(stats, "rushingYards"))
        turnovers = _safe_int(_parse_stat(stats, "turnovers"))
        third_conv, third_att = _parse_fraction(_parse_stat(stats, "thirdDownEff"))
        rz_conv, rz_att = _parse_fraction(_parse_stat(stats, "redZoneAttempts"))
        poss_secs = _parse_possession(_parse_stat(stats, "possessionTime"))
        sacks, _ = _parse_fraction(_parse_stat(stats, "sacksYardsLost"))
        _, pen_yards = _parse_fraction(_parse_stat(stats, "totalPenaltiesYards"))

        dynamic_upsert(cursor, SCHEMA, "fact_team_game_stats", {
            "game_id": game_id,
            "team": team_name,
            "side": side,
            "total_yards": total_yards,
            "passing_yards": passing_yards,
            "rushing_yards": rushing_yards,
            "turnovers": turnovers,
            "third_down_att": third_att,
            "third_down_conv": third_conv,
            "red_zone_att": rz_att,
            "red_zone_conv": rz_conv,
            "time_of_possession_secs": poss_secs,
            "sacks_allowed": sacks,
            "penalty_yards": pen_yards,
        })


# ---------------------------------------------------------------------------
# Per-game enrichment: injury reports
# ---------------------------------------------------------------------------

def _insert_injury_reports(cursor, game_id, home_team_id, home_team_name, away_team_id, away_team_name):
    """Fetch and upsert injury reports for both teams in *game_id*.

    Each team's injuries are fetched from the ESPN injuries API.  Individual
    failures are logged and skipped so a bad response doesn't abort the game.
    """
    for team_id, team_name in [(home_team_id, home_team_name), (away_team_id, away_team_name)]:
        url = ESPN_INJURIES_URL.format(team_id=team_id)
        try:
            resp = requests.get(url, params={"limit": 100}, timeout=30)
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as exc:
            logger.warning(
                "_insert_injury_reports: skipping team=%s game=%s — %s",
                team_name, game_id, exc,
            )
            continue

        for item in items:
            ref_url = item.get("$ref")
            if not ref_url:
                continue
            try:
                ref_resp = requests.get(ref_url, timeout=15)
                ref_resp.raise_for_status()
                injury = ref_resp.json()
            except Exception as exc:
                logger.debug("_insert_injury_reports: ref fetch failed — %s", exc)
                continue

            status_obj = injury.get("type", injury.get("status", {}))
            if isinstance(status_obj, dict):
                raw_status = status_obj.get("name", status_obj.get("description", ""))
            else:
                raw_status = str(status_obj)
            status = _normalize_status(raw_status)

            if status == "active" and "release" in str(injury).lower():
                continue

            athlete_data = injury.get("athlete", {})
            athlete_id, athlete_name, position = "", "", ""
            if isinstance(athlete_data, dict):
                athlete_id = str(athlete_data.get("id", ""))
                athlete_name = athlete_data.get("displayName") or athlete_data.get("fullName", "")
                pos_obj = athlete_data.get("position", {})
                if isinstance(pos_obj, dict):
                    position = pos_obj.get("abbreviation", "")
            if not athlete_id and "/athletes/" in ref_url:
                athlete_id = ref_url.split("/athletes/")[1].split("/")[0]
            if not athlete_id:
                continue

            detail_obj = injury.get("details", {})
            if isinstance(detail_obj, dict):
                detail = detail_obj.get("detail") or detail_obj.get("type", "")
            else:
                detail = str(detail_obj) if detail_obj else ""

            raw_date = injury.get("date") or injury.get("dateCreated")
            report_date = str(raw_date)[:10] if raw_date else None

            dynamic_upsert(cursor, SCHEMA, "fact_injury_report", {
                "game_id": game_id,
                "team": team_name,
                "athlete_id": athlete_id,
                "athlete_name": athlete_name,
                "position": position,
                "injury_status": status,
                "injury_detail": detail[:200],
                "report_date": report_date,
            })


# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------

def insert_nfl_data(date_str=None):
    """Ingest all NFL data for *date_str* into nfl_silver.

    Fetches scoreboard events and, for each game, upserts:
      - game results and market odds
      - game context (venue, week, season)
      - team standings snapshot
      - boxscore stats (from ESPN summary API)
      - injury reports

    Parameters
    ----------
    date_str:
        ISO date string ``"YYYY-MM-DD"``.  Defaults to today (UTC) when omitted.

    Raises
    ------
    Exception
        Re-raised if the scoreboard fetch or DB connection fails.  Per-game
        errors are logged and skipped.
    """
    logger.info("insert_nfl_data: date=%s", date_str)
    conn = get_connection(SCHEMA)
    cursor = conn.cursor()

    events = fetch_nfl_data(date_str)
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
                spread = odds.get("spread")
                ml_home = (odds.get("homeTeamOdds") or {}).get("moneyLine")
                ml_away = (odds.get("awayTeamOdds") or {}).get("moneyLine")
                total_line = odds.get("overUnder")

                dynamic_upsert(cursor, SCHEMA, "fact_market_odds", {
                    "game_id": game_id,
                    "sportsbook": provider,
                    "spread": spread,
                    "moneyline_home": ml_home,
                    "moneyline_away": ml_away,
                    "total_line": total_line,
                    "market_timestamp": datetime.now(),
                }, on_duplicate_update=False)

            # --- game context ---
            venue = comp.get("venue", {})
            venue_name = venue.get("fullName") or venue.get("name", "")
            venue_city = (venue.get("address") or {}).get("city", "")
            indoor = int(bool(venue.get("indoor", False)))
            surface = "grass" if venue.get("grass") else "turf"
            attendance = comp.get("attendance")
            week_number = (event.get("week") or {}).get("number")
            season = (event.get("season") or {}).get("year")

            dynamic_upsert(cursor, SCHEMA, "fact_game_context", {
                "game_id": game_id,
                "week_number": week_number,
                "season": season,
                "venue_name": venue_name,
                "venue_city": venue_city,
                "surface": surface,
                "indoor": indoor,
                "attendance": attendance,
            })

            # --- team standing snapshot ---
            game_date_str = comp.get("date", "")
            for competitor, side in [(home, "home"), (away, "away")]:
                team_name = competitor["team"]["displayName"]
                records = competitor.get("records", [])
                wins, losses = _parse_record(records, "total")
                hw, hl = _parse_record(records, "home")
                aw, al = _parse_record(records, "road")
                total = wins + losses
                win_pct = wins / total if total > 0 else 0.0
                streak = _compute_streak(cursor, team_name, game_date_str)

                dynamic_upsert(cursor, SCHEMA, "fact_team_standing", {
                    "game_id": game_id,
                    "team": team_name,
                    "side": side,
                    "season": season,
                    "week": week_number,
                    "wins": wins,
                    "losses": losses,
                    "win_pct": win_pct,
                    "home_wins": hw,
                    "home_losses": hl,
                    "away_wins": aw,
                    "away_losses": al,
                    "current_streak": streak,
                })

            # --- boxscore stats (summary API) ---
            _insert_game_stats(cursor, game_id)

            # --- injury reports ---
            _insert_injury_reports(
                cursor, game_id,
                home["team"]["id"], home["team"]["displayName"],
                away["team"]["id"], away["team"]["displayName"],
            )

            games_processed += 1

        except Exception as exc:
            logger.error(
                "insert_nfl_data: failed on game_id=%s — %s", game_id, exc, exc_info=True
            )

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("insert_nfl_data: committed %d/%d games", games_processed, len(events))
