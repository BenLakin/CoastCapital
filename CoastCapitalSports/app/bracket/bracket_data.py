"""
bracket_data.py — Fetch and parse NCAA tournament bracket structure from ESPN.

Retrieves the 68-team field, seeds, regions, and play-in matchups for a given
season.  Uses the same ESPN API patterns as ncaa_mbb_ingest.py.
"""

import logging
from datetime import datetime

import pandas as pd
import requests

from database import get_connection

logger = logging.getLogger(__name__)

ESPN_SCOREBOARD_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/"
    "mens-college-basketball/scoreboard"
)

# Standard bracket seeding order within a region (by game position)
BRACKET_SEED_ORDER = [1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]

# Final Four pairings: region index pairs (varies by year, but this is the
# standard NCAA layout — regions 0 & 1 play each other, regions 2 & 3 play)
FF_PAIRINGS = [(0, 1), (2, 3)]


def fetch_tournament_field(season: int) -> list[dict]:
    """Fetch the NCAA tournament field for a given season year.

    Queries the ESPN scoreboard API for tournament games in March/April of the
    given season and extracts the 68-team field with seeds and regions.

    Parameters
    ----------
    season:
        The academic year (e.g. 2025 for the March 2025 tournament).

    Returns
    -------
    List of dicts with keys: team_name, team_espn_id, seed, region,
    is_play_in, play_in_matchup_id.
    """
    teams = {}
    tournament_dates = _generate_tournament_dates(season)

    for date_str in tournament_dates:
        try:
            resp = requests.get(
                ESPN_SCOREBOARD_URL,
                params={"dates": date_str, "groups": "100", "limit": 100},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("fetch_tournament_field: failed for date %s — %s", date_str, exc)
            continue

        for event in data.get("events", []):
            notes = " ".join(
                n.get("headline", "") for n in event.get("notes", [])
            ).lower()

            is_tournament = any(
                kw in notes
                for kw in [
                    "ncaa tournament", "march madness", "first four",
                    "first round", "second round", "sweet 16", "elite 8",
                    "final four", "championship", "round of 64", "round of 32",
                    "national semifinal", "national championship",
                ]
            )
            if not is_tournament:
                continue

            is_play_in = "first four" in notes
            region = _extract_region(notes)
            round_name = _extract_round_name(notes)

            for comp in event.get("competitions", [{}])[0].get("competitors", []):
                team_obj = comp.get("team", {})
                team_name = team_obj.get("displayName", "")
                team_espn_id = str(team_obj.get("id", ""))
                seed = int(comp.get("curatedRank", {}).get("current", 0))
                if seed == 0:
                    seed = int(comp.get("tournamentSeed", 0) or 0)
                if seed == 0:
                    seed = int(comp.get("seed", 0) or 0)

                if team_name and team_name not in teams:
                    teams[team_name] = {
                        "team_name": team_name,
                        "team_espn_id": team_espn_id,
                        "seed": seed,
                        "region": region,
                        "is_play_in": int(is_play_in),
                        "play_in_matchup_id": event.get("id", "") if is_play_in else None,
                    }
                elif team_name in teams:
                    # Update with better data if available
                    if seed > 0 and teams[team_name]["seed"] == 0:
                        teams[team_name]["seed"] = seed
                    if region and not teams[team_name]["region"]:
                        teams[team_name]["region"] = region

    field = list(teams.values())
    logger.info("fetch_tournament_field: found %d teams for season %d", len(field), season)
    return field


def fetch_tournament_games(season: int) -> list[dict]:
    """Fetch completed tournament games for a season from the database.

    Used for historical bracket reconstruction and backtesting.

    Returns
    -------
    List of dicts with game_id, round_name, home_team, away_team,
    seed_home, seed_away, home_score, away_score, winner.
    """
    conn = get_connection("ncaa_mbb_silver")
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT game_id, game_date, round_name,
               home_team, away_team, seed_home, seed_away,
               home_score, away_score, margin
        FROM fact_game_results
        WHERE is_tournament_game = 1
          AND YEAR(game_date) = %s
        ORDER BY game_date, game_id
        """,
        (season,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    games = []
    for r in rows:
        winner = r["home_team"] if r["margin"] > 0 else r["away_team"]
        games.append({
            "game_id": r["game_id"],
            "game_date": r["game_date"],
            "round_name": r["round_name"],
            "home_team": r["home_team"],
            "away_team": r["away_team"],
            "seed_home": r["seed_home"] or 0,
            "seed_away": r["seed_away"] or 0,
            "home_score": r["home_score"],
            "away_score": r["away_score"],
            "winner": winner,
        })

    logger.info("fetch_tournament_games: found %d games for season %d", len(games), season)
    return games


def build_bracket_structure(field: list[dict]) -> dict:
    """Organize the tournament field into the standard bracket structure.

    Parameters
    ----------
    field:
        List of team dicts from fetch_tournament_field or load_bracket_field.

    Returns
    -------
    dict with keys for each region and 'play_in'. Each region contains a list
    of 16 team dicts ordered by bracket position (1v16, 8v9, 5v12, ...).
    Also includes 'regions' list of region names and 'ff_pairings'.
    """
    regions = {}
    play_in_teams = []

    for team in field:
        if team.get("is_play_in"):
            play_in_teams.append(team)
            continue
        region = team.get("region", "Unknown")
        if region not in regions:
            regions[region] = []
        regions[region].append(team)

    # Sort each region by bracket seed order
    for region_name in regions:
        seed_map = {t["seed"]: t for t in regions[region_name]}
        ordered = []
        for seed in BRACKET_SEED_ORDER:
            if seed in seed_map:
                ordered.append(seed_map[seed])
            else:
                ordered.append({"team_name": f"TBD (#{seed})", "seed": seed, "region": region_name})
        regions[region_name] = ordered

    region_names = sorted(regions.keys())

    return {
        **regions,
        "play_in": play_in_teams,
        "regions": region_names,
        "ff_pairings": FF_PAIRINGS,
    }


def save_bracket_field(season: int, field: list[dict]) -> int:
    """Persist the bracket field to modeling_internal.fact_bracket_fields.

    Returns the number of rows written.
    """
    conn = get_connection("modeling_internal")
    cursor = conn.cursor()

    count = 0
    for team in field:
        try:
            cursor.execute(
                """
                INSERT INTO fact_bracket_fields
                    (season, team_name, team_espn_id, seed, region, is_play_in, play_in_matchup_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    seed = VALUES(seed),
                    region = VALUES(region),
                    team_espn_id = VALUES(team_espn_id),
                    is_play_in = VALUES(is_play_in),
                    play_in_matchup_id = VALUES(play_in_matchup_id)
                """,
                (
                    season,
                    team["team_name"],
                    team.get("team_espn_id"),
                    team["seed"],
                    team.get("region", ""),
                    team.get("is_play_in", 0),
                    team.get("play_in_matchup_id"),
                ),
            )
            count += 1
        except Exception as exc:
            logger.warning("save_bracket_field: failed for %s — %s", team.get("team_name"), exc)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("save_bracket_field: wrote %d teams for season %d", count, season)
    return count


def load_bracket_field(season: int) -> pd.DataFrame:
    """Load the bracket field from DB for a given season.

    Returns DataFrame with columns: team_name, team_espn_id, seed, region, is_play_in.
    """
    conn = get_connection("modeling_internal")
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """
        SELECT team_name, team_espn_id, seed, region, is_play_in, play_in_matchup_id
        FROM fact_bracket_fields
        WHERE season = %s
        ORDER BY region, seed
        """,
        (season,),
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _generate_tournament_dates(season: int) -> list[str]:
    """Generate date strings covering the tournament window (mid-March to early April)."""
    dates = []
    for month, start, end in [(3, 14, 31), (4, 1, 10)]:
        for day in range(start, end + 1):
            try:
                d = datetime(season, month, day)
                dates.append(d.strftime("%Y%m%d"))
            except ValueError:
                continue
    return dates


def _extract_region(notes: str) -> str:
    """Extract the tournament region from game notes."""
    for region in ["east", "west", "south", "midwest"]:
        if region in notes:
            return region.capitalize()
    return ""


def _extract_round_name(notes: str) -> str:
    """Extract the tournament round from game notes."""
    round_keywords = [
        ("national championship", "Championship"),
        ("championship", "Championship"),
        ("national semifinal", "Final Four"),
        ("final four", "Final Four"),
        ("elite 8", "Elite 8"),
        ("elite eight", "Elite 8"),
        ("sweet 16", "Sweet 16"),
        ("sweet sixteen", "Sweet 16"),
        ("second round", "Round of 32"),
        ("round of 32", "Round of 32"),
        ("first round", "Round of 64"),
        ("round of 64", "Round of 64"),
        ("first four", "First Four"),
    ]
    for keyword, name in round_keywords:
        if keyword in notes:
            return name
    return ""
