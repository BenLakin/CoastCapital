"""
ncaa_mbb_ingest.py — ESPN data ingestion for the NCAA Men's Basketball silver layer.

Fetches scoreboard events, boxscore stats, team standings, BPI ratings,
poll rankings, and game predictor data from ESPN public APIs and upserts
them into the ncaa_mbb_silver schema.

Public entry point: ``insert_ncaa_mbb_data(date_str)``
"""

import logging
import requests
from datetime import date, datetime
from database import get_connection
from ingestion.schema_sync import dynamic_upsert

logger = logging.getLogger(__name__)

SCHEMA = "ncaa_mbb_silver"

ESPN_SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard"
ESPN_SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary"
ESPN_RANKINGS_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/rankings"
ESPN_BPI_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/seasons/{season}/powerindex/{team_id}"
ESPN_PREDICTOR_URL = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/events/{event_id}/competitions/{event_id}/predictor"

ROUND_CANDIDATE_KEYS = ["shortName", "name", "abbreviation", "displayName"]

# ---------------------------------------------------------------------------
# Scoreboard helpers
# ---------------------------------------------------------------------------

def fetch_ncaa_mbb_data(date_str=None):
    """Fetch NCAA MBB scoreboard events from the ESPN API.

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
    logger.debug("fetch_ncaa_mbb_data: GET %s  params=%s", ESPN_SCOREBOARD_URL, params)
    response = requests.get(ESPN_SCOREBOARD_URL, params=params, timeout=30)
    response.raise_for_status()
    events = response.json().get("events", [])
    logger.info("fetch_ncaa_mbb_data: %d events for date=%s", len(events), date_str)
    return events

def _extract_seed(team_payload):
    for key in ["tournamentSeed", "seed"]:
        value = team_payload.get(key)
        if value not in (None, ""):
            try:
                return int(value)
            except Exception:
                pass
    try:
        curated = team_payload.get("curatedRank", {}).get("current")
        if curated:
            return int(curated)
    except Exception:
        pass
    return 0

def _extract_round_name(event_payload, competition_payload):
    for obj in [competition_payload.get("status", {}).get("type", {}), event_payload.get("seasonType", {}), event_payload.get("week", {})]:
        for key in ROUND_CANDIDATE_KEYS:
            val = obj.get(key)
            if val:
                return str(val)
    return ""

def _is_tournament_game(event_payload, competition_payload):
    text = " ".join([
        str(event_payload.get("name", "")),
        str(event_payload.get("shortName", "")),
        str(_extract_round_name(event_payload, competition_payload)),
    ]).lower()
    return int(any(token in text for token in ["tournament", "march madness", "sweet 16", "elite 8", "final four", "championship", "round of 64", "round of 32", "first four"]))

def _parse_record(records, record_type):
    for r in records:
        t = r.get("type", "").lower()
        n = r.get("name", "").lower()
        if record_type.lower() in (t, n):
            parts = r.get("summary", "0-0").split("-")
            if len(parts) >= 2:
                try:
                    return int(parts[0]), int(parts[1])
                except ValueError:
                    pass
    return 0, 0

# ---------------------------------------------------------------------------
# Boxscore stat helpers
# ---------------------------------------------------------------------------

def _safe_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return None

def _safe_float(val):
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

def _parse_stat(stats, name):
    for s in stats:
        if s.get("name") == name:
            return s.get("displayValue")
    return None

def _parse_fraction(val):
    """'29-56' → (29, 56)"""
    if not val:
        return None, None
    parts = str(val).split("-")
    if len(parts) == 2:
        try:
            return int(parts[0]), int(parts[1])
        except ValueError:
            pass
    return None, None

# ---------------------------------------------------------------------------
# BPI stat helper
# ---------------------------------------------------------------------------

def _get_bpi_stat(data, name):
    for s in data.get("statistics", []):
        if s.get("name", "").lower() == name.lower():
            v = s.get("value")
            if v is not None:
                return v
            dv = str(s.get("displayValue", ""))
            if dv:
                try:
                    return int("".join(c for c in dv if c.isdigit()))
                except ValueError:
                    pass
    return None

# ---------------------------------------------------------------------------
# Game context insertion
# ---------------------------------------------------------------------------

def _insert_mbb_game_context(cursor, game_id, comp, event):
    neutral_site = int(bool(comp.get("neutralSite", False)))
    is_conf = int(bool(comp.get("conferenceCompetition", False)))
    venue = comp.get("venue", {})
    venue_name = venue.get("fullName") or venue.get("name", "")
    venue_city = (venue.get("address") or {}).get("city", "")
    attendance = comp.get("attendance")
    season = (event.get("season") or {}).get("year")

    dynamic_upsert(cursor, SCHEMA, "fact_mbb_game_context", {
        "game_id": game_id,
        "neutral_site": neutral_site,
        "is_conference_game": is_conf,
        "venue_name": venue_name,
        "venue_city": venue_city,
        "attendance": attendance,
        "season": season,
    })

# ---------------------------------------------------------------------------
# Team standing insertion
# ---------------------------------------------------------------------------

def _insert_mbb_team_standing(cursor, game_id, competitor, side):
    team_name = competitor["team"]["displayName"]
    records = competitor.get("records", [])
    wins, losses = _parse_record(records, "total")
    hw, hl = _parse_record(records, "home")
    rw, rl = _parse_record(records, "road")
    cw, cl = _parse_record(records, "vsconf")
    total = wins + losses
    win_pct = wins / total if total > 0 else 0.0

    dynamic_upsert(cursor, SCHEMA, "fact_mbb_team_standing", {
        "game_id": game_id,
        "team": team_name,
        "side": side,
        "wins": wins,
        "losses": losses,
        "win_pct": win_pct,
        "home_wins": hw,
        "home_losses": hl,
        "road_wins": rw,
        "road_losses": rl,
        "conf_wins": cw,
        "conf_losses": cl,
    })

# ---------------------------------------------------------------------------
# Boxscore stats insertion (from /summary)
# ---------------------------------------------------------------------------

def _insert_mbb_game_stats(cursor, game_id):
    try:
        resp = requests.get(ESPN_SUMMARY_URL, params={"event": game_id}, timeout=30)
        resp.raise_for_status()
        teams = resp.json().get("boxscore", {}).get("teams", [])
    except Exception as exc:
        logger.warning("_insert_mbb_game_stats: skipping game_id=%s — %s", game_id, exc)
        return

    for entry in teams:
        team_name = entry.get("team", {}).get("displayName", "")
        side = entry.get("homeAway", "home")
        stats = entry.get("statistics", [])

        fg_made, fg_att = _parse_fraction(_parse_stat(stats, "fieldGoalsMade-fieldGoalsAttempted"))
        fg_pct = _safe_float(_parse_stat(stats, "fieldGoalPct"))
        tp_made, tp_att = _parse_fraction(_parse_stat(stats, "threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
        tp_pct = _safe_float(_parse_stat(stats, "threePointFieldGoalPct"))
        ft_made, ft_att = _parse_fraction(_parse_stat(stats, "freeThrowsMade-freeThrowsAttempted"))
        ft_pct = _safe_float(_parse_stat(stats, "freeThrowPct"))
        total_reb = _safe_int(_parse_stat(stats, "totalRebounds"))
        off_reb = _safe_int(_parse_stat(stats, "offensiveRebounds"))
        def_reb = _safe_int(_parse_stat(stats, "defensiveRebounds"))
        assists = _safe_int(_parse_stat(stats, "assists"))
        steals = _safe_int(_parse_stat(stats, "steals"))
        blocks = _safe_int(_parse_stat(stats, "blocks"))
        turnovers = _safe_int(_parse_stat(stats, "turnovers"))
        to_pts = _safe_int(_parse_stat(stats, "turnoverPoints"))
        fb_pts = _safe_int(_parse_stat(stats, "fastBreakPoints"))
        pip = _safe_int(_parse_stat(stats, "pointsInPaint"))
        largest_lead = _safe_int(_parse_stat(stats, "largestLead"))
        fouls = _safe_int(_parse_stat(stats, "fouls"))

        dynamic_upsert(cursor, SCHEMA, "fact_mbb_game_stats", {
            "game_id": game_id,
            "team": team_name,
            "side": side,
            "fg_made": fg_made,
            "fg_att": fg_att,
            "fg_pct": fg_pct,
            "three_pt_made": tp_made,
            "three_pt_att": tp_att,
            "three_pt_pct": tp_pct,
            "ft_made": ft_made,
            "ft_att": ft_att,
            "ft_pct": ft_pct,
            "total_rebounds": total_reb,
            "off_rebounds": off_reb,
            "def_rebounds": def_reb,
            "assists": assists,
            "steals": steals,
            "blocks": blocks,
            "turnovers": turnovers,
            "turnover_points": to_pts,
            "fast_break_points": fb_pts,
            "points_in_paint": pip,
            "largest_lead": largest_lead,
            "fouls": fouls,
        })

# ---------------------------------------------------------------------------
# Game predictor insertion (pre-game BPI win probability)
# ---------------------------------------------------------------------------

def _insert_mbb_game_predictor(cursor, game_id):
    """Fetch and upsert BPI pre-game win probability for *game_id*.

    Silently skips if the predictor API call fails (data may not be available).
    """
    url = ESPN_PREDICTOR_URL.format(event_id=game_id)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug("_insert_mbb_game_predictor: skipping game_id=%s — %s", game_id, exc)
        return

    def _get_pred_stat(team_data, name):
        for s in team_data.get("statistics", []):
            if s.get("name", "").lower() == name.lower():
                return s.get("value")
        return None

    home_data = data.get("homeTeam", {})
    away_data = data.get("awayTeam", {})

    home_pred_win_pct = _safe_float(_get_pred_stat(home_data, "teampredwinpct"))
    away_pred_win_pct = _safe_float(_get_pred_stat(away_data, "teampredwinpct"))
    home_pred_mov = _safe_float(_get_pred_stat(home_data, "teampredmov"))
    matchup_quality = _safe_float(_get_pred_stat(home_data, "matchupquality"))

    # Fallback: summary predictor format (gameProjection)
    if home_pred_win_pct is None:
        home_pred_win_pct = _safe_float(home_data.get("gameProjection"))
    if away_pred_win_pct is None:
        away_pred_win_pct = _safe_float(away_data.get("gameProjection"))

    if home_pred_win_pct is None and away_pred_win_pct is None:
        return

    dynamic_upsert(cursor, SCHEMA, "fact_mbb_game_predictor", {
        "game_id": game_id,
        "home_pred_win_pct": home_pred_win_pct,
        "away_pred_win_pct": away_pred_win_pct,
        "home_pred_mov": home_pred_mov,
        "matchup_quality": matchup_quality,
    })

# ---------------------------------------------------------------------------
# BPI insertion (season-level team ratings snapshot)
# ---------------------------------------------------------------------------

def _insert_mbb_bpi(cursor, team_espn_id, team_name, season, snapshot_date):
    """Fetch and upsert BPI season snapshot for a team.

    Silently skips if BPI data is unavailable for the team/season.
    """
    if not season or not team_espn_id:
        return
    url = ESPN_BPI_URL.format(season=season, team_id=team_espn_id)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.debug(
            "_insert_mbb_bpi: skipping team=%s season=%s — %s", team_name, season, exc
        )
        return

    bpi = _safe_float(_get_bpi_stat(data, "bpi"))
    bpi_rank = _safe_int(_get_bpi_stat(data, "bpirank"))
    bpi_off = _safe_float(_get_bpi_stat(data, "bpioffense"))
    bpi_def = _safe_float(_get_bpi_stat(data, "bpidefense"))
    sor = _safe_float(_get_bpi_stat(data, "sor"))
    sor_rank = _safe_int(_get_bpi_stat(data, "sorrank"))
    sos = _safe_float(_get_bpi_stat(data, "sospast"))
    sos_rank = _safe_int(_get_bpi_stat(data, "sospastrank"))
    proj_seed = _safe_int(_get_bpi_stat(data, "projectedtournamentseed"))
    sweet16 = _safe_float(_get_bpi_stat(data, "chancesweet16"))
    elite8 = _safe_float(_get_bpi_stat(data, "chanceelite8"))
    final4 = _safe_float(_get_bpi_stat(data, "chancefinal4"))
    champion = _safe_float(_get_bpi_stat(data, "chancencaachampion"))

    if bpi is None:
        return

    dynamic_upsert(cursor, SCHEMA, "fact_mbb_bpi", {
        "team_espn_id": str(team_espn_id),
        "team_name": team_name,
        "season": season,
        "snapshot_date": snapshot_date,
        "bpi": bpi,
        "bpi_rank": bpi_rank,
        "bpi_offense": bpi_off,
        "bpi_defense": bpi_def,
        "sor": sor,
        "sor_rank": sor_rank,
        "sos_past": sos,
        "sos_past_rank": sos_rank,
        "proj_tournament_seed": proj_seed,
        "chance_sweet16": sweet16,
        "chance_elite8": elite8,
        "chance_final4": final4,
        "chance_champion": champion,
    })

# ---------------------------------------------------------------------------
# Poll rankings insertion (AP + Coaches)
# ---------------------------------------------------------------------------

def _parse_trend(trend_str):
    if not trend_str or str(trend_str).strip() in ("-", "–", "—", ""):
        return 0
    s = str(trend_str).replace("+", "")
    try:
        return int(s)
    except ValueError:
        return 0

def _insert_mbb_poll_rankings(cursor, snapshot_date):
    """Fetch and upsert AP and Coaches poll rankings for *snapshot_date*.

    Silently skips if the rankings API call fails.
    """
    try:
        resp = requests.get(ESPN_RANKINGS_URL, timeout=30)
        resp.raise_for_status()
        rankings = resp.json().get("rankings", [])
    except Exception as exc:
        logger.warning("_insert_mbb_poll_rankings: failed — %s", exc)
        return

    poll_map = {"ap": "ap", "usa": "coaches"}

    for poll in rankings:
        raw_type = poll.get("type", "").lower()
        poll_type = poll_map.get(raw_type)
        if not poll_type:
            continue

        for entry in poll.get("ranks", []):
            team = entry.get("team", {})
            team_espn_id = str(team.get("id", ""))
            team_name = team.get("displayName", "")
            if not team_espn_id:
                continue

            rank = _safe_int(entry.get("current"))
            prev_rank = _safe_int(entry.get("previous"))
            trend = _parse_trend(entry.get("trend"))
            poll_points = _safe_float(entry.get("points"))
            first_place = _safe_int(entry.get("firstPlaceVotes"))

            dynamic_upsert(cursor, SCHEMA, "fact_mbb_poll_ranking", {
                "team_name": team_name,
                "team_espn_id": team_espn_id,
                "poll_type": poll_type,
                "rank": rank,
                "previous_rank": prev_rank,
                "trend": trend,
                "poll_points": poll_points,
                "first_place_votes": first_place,
                "snapshot_date": snapshot_date,
            })

# ---------------------------------------------------------------------------
# Main ingest
# ---------------------------------------------------------------------------

def insert_ncaa_mbb_data(date_str=None):
    """Ingest all NCAA MBB data for *date_str* into ncaa_mbb_silver.

    Fetches scoreboard events and, for each game, upserts:
      - game results and market odds
      - game context (venue, neutral site, conference flags)
      - team standings snapshots
      - boxscore stats (from ESPN summary API)
      - game predictor (BPI pre-game win probability)
      - BPI season snapshots (once per team per run)
      - Poll rankings (AP and Coaches, once per run)

    Parameters
    ----------
    date_str:
        ISO date string ``"YYYY-MM-DD"``.  Defaults to today when omitted.

    Raises
    ------
    Exception
        Re-raised if the DB connection fails.  Per-game errors are logged
        and skipped.
    """
    logger.info("insert_ncaa_mbb_data: date=%s", date_str)
    conn = get_connection(SCHEMA)
    cursor = conn.cursor()

    today = date.today()
    seen_bpi_teams = set()  # avoid duplicate BPI calls per team per run

    # Pull poll rankings once per ingest run
    _insert_mbb_poll_rankings(cursor, today)

    events = fetch_ncaa_mbb_data(date_str)
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
            is_tournament_game = _is_tournament_game(event, comp)
            seed_home = _extract_seed(home)
            seed_away = _extract_seed(away)

            dynamic_upsert(cursor, SCHEMA, "fact_game_results", {
                "game_id": game_id,
                "game_date": comp.get("date"),
                "home_team": home["team"]["displayName"],
                "away_team": away["team"]["displayName"],
                "home_score": home_score,
                "away_score": away_score,
                "margin": margin,
                "is_tournament_game": is_tournament_game,
                "round_name": round_name,
                "seed_home": seed_home,
                "seed_away": seed_away,
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
            _insert_mbb_game_context(cursor, game_id, comp, event)

            # --- team standings ---
            _insert_mbb_team_standing(cursor, game_id, home, "home")
            _insert_mbb_team_standing(cursor, game_id, away, "away")

            # --- boxscore stats ---
            _insert_mbb_game_stats(cursor, game_id)

            # --- game predictor (BPI pre-game win probability) ---
            _insert_mbb_game_predictor(cursor, game_id)

            # --- BPI per team (season snapshot) ---
            season = (event.get("season") or {}).get("year")
            for competitor in [home, away]:
                team_id = str(competitor["team"].get("id", ""))
                team_name = competitor["team"]["displayName"]
                bpi_key = (team_id, season)
                if team_id and bpi_key not in seen_bpi_teams:
                    seen_bpi_teams.add(bpi_key)
                    _insert_mbb_bpi(cursor, team_id, team_name, season, today)

            games_processed += 1

        except Exception as exc:
            logger.error(
                "insert_ncaa_mbb_data: failed on game_id=%s — %s", game_id, exc, exc_info=True
            )

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("insert_ncaa_mbb_data: committed %d/%d games", games_processed, len(events))
