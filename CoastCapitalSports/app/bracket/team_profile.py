"""
team_profile.py — Build team statistical profiles for hypothetical matchup prediction.

The trained model expects 137 FEATURE_COLUMNS for each game.  For hypothetical
tournament matchups (Team A vs Team B where no game row exists), we build
team-level profiles from recent games and then combine two profiles into a
synthetic feature vector that the model can consume.

Strategy:
  1. For each team, compute rolling stats from their recent regular-season games
  2. Pull current BPI, standings, poll rankings from silver tables
  3. Store team-level "half-vectors"
  4. To predict Team A vs Team B: combine A's home-side profile with B's away-side
  5. Fill tournament-specific features from bracket data
  6. Default market features to 0 / neutral values
"""

import json
import logging

import numpy as np
import pandas as pd

from database import get_connection
from features.feature_engineering import (
    ROUND_ORDER_MAP,
    _seed_matchup_bucket,
    _upset_band,
)
from features.feature_registry import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

# Index lookup for fast feature vector assignment
_FEATURE_INDEX = {name: idx for idx, name in enumerate(FEATURE_COLUMNS)}


def build_team_profiles(season: int) -> dict[str, dict]:
    """Build statistical profiles for all teams in a season.

    For each team, queries silver tables for rolling stats, BPI, standings,
    and poll rankings.

    Parameters
    ----------
    season:
        Academic year for the season.

    Returns
    -------
    dict mapping team_name -> profile dict with the team's statistics.
    """
    conn = get_connection("ncaa_mbb_silver")
    cursor = conn.cursor(dictionary=True)

    # 1. Get all teams that played this season
    cursor.execute(
        """
        SELECT DISTINCT team_name FROM (
            SELECT home_team AS team_name FROM fact_game_results
            WHERE YEAR(game_date) = %s OR (YEAR(game_date) = %s AND MONTH(game_date) <= 4)
            UNION
            SELECT away_team AS team_name FROM fact_game_results
            WHERE YEAR(game_date) = %s OR (YEAR(game_date) = %s AND MONTH(game_date) <= 4)
        ) t
        """,
        (season, season, season, season),
    )
    all_teams = [r["team_name"] for r in cursor.fetchall()]

    profiles = {}
    for team_name in all_teams:
        profile = {}

        # Rolling game stats
        rolling = _compute_rolling_stats(cursor, team_name, season)
        profile.update(rolling)

        # BPI
        bpi = _get_latest_bpi(cursor, team_name, season)
        profile.update(bpi)

        # Standings
        standings = _get_latest_standings(cursor, team_name, season)
        profile.update(standings)

        # Poll ranking
        profile["ap_rank"] = _get_latest_poll_rank(cursor, team_name)

        profiles[team_name] = profile

    cursor.close()
    conn.close()
    logger.info("build_team_profiles: built profiles for %d teams (season %d)", len(profiles), season)
    return profiles


def _compute_rolling_stats(cursor, team_name: str, season: int) -> dict:
    """Compute rolling game statistics from a team's recent games."""
    cursor.execute(
        """
        SELECT g.game_date, g.home_team, g.away_team, g.home_score, g.away_score, g.margin,
               s.fg_pct, s.three_pt_pct, s.ft_pct,
               s.total_rebounds, s.off_rebounds, s.assists,
               s.turnovers AS turnovers_mbb, s.fast_break_points, s.points_in_paint
        FROM fact_game_results g
        JOIN fact_mbb_game_stats s ON g.game_id = s.game_id
        WHERE s.team = %s
          AND (YEAR(g.game_date) = %s OR (YEAR(g.game_date) = %s AND MONTH(g.game_date) <= 4))
          AND g.is_tournament_game = 0
        ORDER BY g.game_date DESC
        LIMIT 10
        """,
        (team_name, season, season),
    )
    rows = cursor.fetchall()

    if not rows:
        return {
            "score_lag_1": 0, "margin_lag_1": 0,
            "score_roll_3": 0, "margin_roll_3": 0, "rest_days": 3,
            "fg_pct_roll3": 0, "three_pt_pct_roll3": 0, "ft_pct_roll3": 0,
            "total_rebounds_roll3": 0, "off_rebounds_roll3": 0, "assists_roll3": 0,
            "turnovers_mbb_roll3": 0, "fast_break_points_roll3": 0, "points_in_paint_roll3": 0,
        }

    # Rows are newest-first; the model uses shift(1) so lag_1 is the 2nd game
    scores = []
    margins = []
    for r in rows:
        if r["home_team"] == team_name:
            scores.append(r["home_score"] or 0)
            margins.append(r["margin"] or 0)
        else:
            scores.append(r["away_score"] or 0)
            margins.append(-(r["margin"] or 0))

    # lag_1 = most recent completed game (index 0 is newest but shift(1) means prior)
    score_lag_1 = scores[1] if len(scores) > 1 else scores[0] if scores else 0
    margin_lag_1 = margins[1] if len(margins) > 1 else margins[0] if margins else 0

    # 3-game rolling average (shifted by 1 to avoid leakage, so games 1-3)
    roll_scores = scores[1:4] if len(scores) > 1 else scores[:3]
    roll_margins = margins[1:4] if len(margins) > 1 else margins[:3]
    score_roll_3 = np.mean(roll_scores) if roll_scores else 0
    margin_roll_3 = np.mean(roll_margins) if roll_margins else 0

    # Rest days
    if len(rows) >= 2:
        d0 = rows[0]["game_date"]
        d1 = rows[1]["game_date"]
        rest_days = (d0 - d1).days if hasattr(d0, "days") or hasattr(d0, "day") else 3
        try:
            rest_days = abs((d0 - d1).days)
        except Exception:
            rest_days = 3
    else:
        rest_days = 3

    # Rolling stat averages (shifted by 1)
    stat_fields = [
        "fg_pct", "three_pt_pct", "ft_pct",
        "total_rebounds", "off_rebounds", "assists",
        "turnovers_mbb", "fast_break_points", "points_in_paint",
    ]
    stat_avgs = {}
    for field in stat_fields:
        vals = [float(r.get(field, 0) or 0) for r in rows[1:4]]
        stat_avgs[f"{field}_roll3"] = np.mean(vals) if vals else 0

    return {
        "score_lag_1": score_lag_1,
        "margin_lag_1": margin_lag_1,
        "score_roll_3": score_roll_3,
        "margin_roll_3": margin_roll_3,
        "rest_days": rest_days,
        **stat_avgs,
    }


def _get_latest_bpi(cursor, team_name: str, season: int) -> dict:
    """Fetch the most recent BPI snapshot for a team."""
    cursor.execute(
        """
        SELECT bpi, bpi_offense, bpi_defense, sor, proj_tournament_seed
        FROM fact_mbb_bpi
        WHERE team_name = %s AND season = %s
        ORDER BY snapshot_date DESC
        LIMIT 1
        """,
        (team_name, season),
    )
    row = cursor.fetchone()
    if not row:
        return {"bpi": 0, "bpi_offense": 0, "bpi_defense": 0, "sor": 0, "proj_tournament_seed": 0}
    return {
        "bpi": float(row["bpi"] or 0),
        "bpi_offense": float(row["bpi_offense"] or 0),
        "bpi_defense": float(row["bpi_defense"] or 0),
        "sor": float(row["sor"] or 0),
        "proj_tournament_seed": int(row["proj_tournament_seed"] or 0),
    }


def _get_latest_standings(cursor, team_name: str, season: int) -> dict:
    """Fetch the most recent standings snapshot for a team."""
    cursor.execute(
        """
        SELECT s.wins, s.losses, s.win_pct,
               s.home_wins, s.home_losses, s.road_wins, s.road_losses,
               s.conf_wins, s.conf_losses
        FROM fact_mbb_team_standing s
        JOIN fact_game_results g ON s.game_id = g.game_id
        WHERE s.team = %s
          AND (YEAR(g.game_date) = %s OR (YEAR(g.game_date) = %s AND MONTH(g.game_date) <= 4))
        ORDER BY g.game_date DESC
        LIMIT 1
        """,
        (team_name, season, season),
    )
    row = cursor.fetchone()
    if not row:
        return {
            "wins": 0, "losses": 0, "win_pct": 0,
            "home_wins": 0, "home_losses": 0,
            "road_wins": 0, "road_losses": 0,
            "conf_wins": 0, "conf_losses": 0,
        }
    return {k: (float(v) if v is not None else 0) for k, v in row.items()}


def _get_latest_poll_rank(cursor, team_name: str) -> int:
    """Fetch the most recent AP poll rank (99 if unranked)."""
    cursor.execute(
        """
        SELECT rank FROM fact_mbb_poll_ranking
        WHERE team_name = %s AND poll_type = 'ap'
        ORDER BY snapshot_date DESC
        LIMIT 1
        """,
        (team_name,),
    )
    row = cursor.fetchone()
    return int(row["rank"]) if row and row["rank"] else 99


def build_matchup_feature_vector(
    team_a: str,
    team_b: str,
    team_profiles: dict[str, dict],
    seed_a: int,
    seed_b: int,
    team_to_id: dict[str, int],
    round_name: str = "",
    neutral_site: int = 1,
) -> np.ndarray:
    """Construct a 137-feature vector for a hypothetical Team A vs Team B matchup.

    Team A is placed in the "home" feature positions and Team B in "away".
    All tournament games use neutral_site=1.

    Returns
    -------
    np.ndarray of shape (137,) matching FEATURE_COLUMNS order.
    """
    vec = np.zeros(len(FEATURE_COLUMNS), dtype=np.float32)
    pa = team_profiles.get(team_a, {})
    pb = team_profiles.get(team_b, {})

    def _set(name, val):
        idx = _FEATURE_INDEX.get(name)
        if idx is not None:
            vec[idx] = float(val)

    # --- Team history features ---
    _set("home_score_lag_1", pa.get("score_lag_1", 0))
    _set("away_score_lag_1", pb.get("score_lag_1", 0))
    _set("home_margin_lag_1", pa.get("margin_lag_1", 0))
    _set("away_margin_lag_1", pb.get("margin_lag_1", 0))
    _set("home_score_roll_3", pa.get("score_roll_3", 0))
    _set("away_score_roll_3", pb.get("score_roll_3", 0))
    _set("home_margin_roll_3", pa.get("margin_roll_3", 0))
    _set("away_margin_roll_3", pb.get("margin_roll_3", 0))
    _set("home_rest_days", pa.get("rest_days", 3))
    _set("away_rest_days", pb.get("rest_days", 3))

    # --- Market features (unavailable for hypothetical matchups) ---
    _set("market_spread", 0)
    _set("market_total_line", 0)
    _set("market_moneyline_home", 0)
    _set("market_moneyline_away", 0)
    _set("market_implied_prob_home", 0.5)
    _set("market_implied_prob_away", 0.5)
    _set("market_moneyline_delta", 0)

    # --- Team encoding ---
    _set("home_team_encoded", team_to_id.get(team_a, 0))
    _set("away_team_encoded", team_to_id.get(team_b, 0))

    # --- Tournament features ---
    _set("is_tournament_game", 1)
    round_order = ROUND_ORDER_MAP.get(round_name, 0)
    _set("round_order", round_order)
    _set("seed_home", seed_a)
    _set("seed_away", seed_b)
    seed_diff = seed_a - seed_b
    _set("seed_diff", seed_diff)
    _set("home_is_higher_seed", int(seed_a > 0 and seed_b > 0 and seed_a < seed_b))
    _set("seed_matchup_bucket", _seed_matchup_bucket(seed_diff))
    _set("upset_band", _upset_band(seed_a, seed_b))

    # Seed history win rates from DB
    seed_history = _load_seed_history()
    _set("home_seed_hist_win_pct", seed_history.get(seed_a, {}).get("win_pct", 0))
    _set("away_seed_hist_win_pct", seed_history.get(seed_b, {}).get("win_pct", 0))
    _set("home_seed_hist_upset_win_pct", seed_history.get(seed_a, {}).get("upset_win_pct", 0))
    _set("away_seed_hist_upset_win_pct", seed_history.get(seed_b, {}).get("upset_win_pct", 0))

    # --- Postseason features ---
    _set("is_postseason_game", 1)
    _set("postseason_round_order", round_order)
    if round_order <= 0:
        tier = 0
    elif round_order == 1:
        tier = 1
    elif round_order in (2, 3):
        tier = 2
    else:
        tier = 3
    _set("postseason_round_tier", tier)
    _set("playoff_experience_home", 0)
    _set("playoff_experience_away", 0)
    championship = 1 if round_name and "championship" in round_name.lower() else 0
    _set("championship_game_flag", championship)

    # --- NFL features (all zeroed for MBB) ---
    # week_number, is_indoor, surface_is_grass, rest_advantage, is_short_week
    # NFL game stats, standings, injuries — all default to 0

    # --- NCAA MBB context ---
    _set("neutral_site", neutral_site)
    _set("is_conference_game", 0)
    conf_total_a = pa.get("conf_wins", 0) + pa.get("conf_losses", 0)
    conf_pct_a = pa.get("conf_wins", 0) / conf_total_a if conf_total_a > 0 else 0
    conf_total_b = pb.get("conf_wins", 0) + pb.get("conf_losses", 0)
    conf_pct_b = pb.get("conf_wins", 0) / conf_total_b if conf_total_b > 0 else 0
    _set("home_conf_win_pct", conf_pct_a)
    _set("away_conf_win_pct", conf_pct_b)
    _set("conf_win_pct_diff", conf_pct_a - conf_pct_b)
    road_total_b = pb.get("road_wins", 0) + pb.get("road_losses", 0)
    _set("away_road_win_pct", pb.get("road_wins", 0) / road_total_b if road_total_b > 0 else 0)

    # --- NCAA MBB rolling game stats ---
    for stat in [
        "fg_pct_roll3", "three_pt_pct_roll3", "ft_pct_roll3",
        "total_rebounds_roll3", "off_rebounds_roll3", "assists_roll3",
        "turnovers_mbb_roll3", "fast_break_points_roll3", "points_in_paint_roll3",
    ]:
        _set(f"home_{stat}", pa.get(stat, 0))
        _set(f"away_{stat}", pb.get(stat, 0))

    reb_margin = pa.get("total_rebounds_roll3", 0) - pb.get("total_rebounds_roll3", 0)
    _set("rebound_margin_mbb_roll3", reb_margin)
    to_margin = pb.get("turnovers_mbb_roll3", 0) - pa.get("turnovers_mbb_roll3", 0)
    _set("turnover_margin_mbb_roll3", to_margin)

    # --- NCAA MBB BPI & ratings ---
    _set("home_bpi", pa.get("bpi", 0))
    _set("away_bpi", pb.get("bpi", 0))
    _set("bpi_diff", pa.get("bpi", 0) - pb.get("bpi", 0))
    _set("home_bpi_offense", pa.get("bpi_offense", 0))
    _set("away_bpi_defense", pb.get("bpi_defense", 0))
    _set("bpi_offense_vs_defense", pa.get("bpi_offense", 0) - pb.get("bpi_defense", 0))
    _set("home_sor", pa.get("sor", 0))
    _set("away_sor", pb.get("sor", 0))
    _set("sor_diff", pa.get("sor", 0) - pb.get("sor", 0))

    # --- Poll rankings ---
    home_rank = pa.get("ap_rank", 99)
    away_rank = pb.get("ap_rank", 99)
    _set("home_ap_rank", home_rank)
    _set("away_ap_rank", away_rank)
    _set("rank_advantage", away_rank - home_rank)
    _set("home_is_ranked", int(home_rank < 99))
    _set("away_is_ranked", int(away_rank < 99))

    # --- Game predictor (not available for hypothetical) ---
    _set("home_pred_win_pct", 0)
    _set("home_pred_mov", 0)
    _set("matchup_quality", 0)

    # --- NFL standings (zeroed for MBB) ---
    _set("home_win_pct", pa.get("win_pct", 0))
    _set("away_win_pct", pb.get("win_pct", 0))
    _set("win_pct_diff", pa.get("win_pct", 0) - pb.get("win_pct", 0))
    home_home_total = pa.get("home_wins", 0) + pa.get("home_losses", 0)
    _set("home_home_win_pct", pa.get("home_wins", 0) / home_home_total if home_home_total > 0 else 0)
    away_away_total = pb.get("road_wins", 0) + pb.get("road_losses", 0)
    _set("away_away_win_pct", pb.get("road_wins", 0) / away_away_total if away_away_total > 0 else 0)

    return vec


def save_team_profiles(season: int, profiles: dict[str, dict], team_seeds: dict[str, int]):
    """Persist team profiles to modeling_internal.fact_bracket_team_profiles."""
    conn = get_connection("modeling_internal")
    cursor = conn.cursor()

    for team_name, profile in profiles.items():
        seed = team_seeds.get(team_name, 0)
        try:
            cursor.execute(
                """
                INSERT INTO fact_bracket_team_profiles
                    (season, team_name, seed, feature_payload)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    seed = VALUES(seed),
                    feature_payload = VALUES(feature_payload),
                    profile_timestamp = CURRENT_TIMESTAMP
                """,
                (season, team_name, seed, json.dumps(profile)),
            )
        except Exception as exc:
            logger.warning("save_team_profiles: failed for %s — %s", team_name, exc)

    conn.commit()
    cursor.close()
    conn.close()
    logger.info("save_team_profiles: saved %d profiles for season %d", len(profiles), season)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_seed_history_cache = None


def _load_seed_history() -> dict[int, dict]:
    """Load historical seed win rates (cached after first call)."""
    global _seed_history_cache
    if _seed_history_cache is not None:
        return _seed_history_cache

    try:
        conn = get_connection("ncaa_mbb_silver")
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT seed, win_pct, upset_win_pct FROM fact_seed_history")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        _seed_history_cache = {
            int(r["seed"]): {
                "win_pct": float(r["win_pct"] or 0),
                "upset_win_pct": float(r["upset_win_pct"] or 0),
            }
            for r in rows
        }
    except Exception:
        _seed_history_cache = {}

    return _seed_history_cache
