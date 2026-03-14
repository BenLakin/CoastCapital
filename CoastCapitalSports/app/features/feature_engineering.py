"""
feature_engineering.py — Transforms raw game data into model-ready features.

Applies sport-specific rolling stats, market features, tournament/postseason
features, team encoding, and target variable creation.  The pipeline runs
in a fixed order via ``finalize_feature_frame()``.
"""

import numpy as np
import pandas as pd

ROUND_ORDER_MAP = {
    "First Four": 0,
    "First Round": 1,
    "Round of 64": 1,
    "Second Round": 2,
    "Round of 32": 2,
    "Sweet 16": 3,
    "Elite 8": 4,
    "Final Four": 5,
    "National Semifinals": 5,
    "Championship": 6,
    "National Championship": 6,
}

def implied_probability(moneyline):
    if pd.isna(moneyline):
        return np.nan
    moneyline = float(moneyline)
    if moneyline > 0:
        return 100.0 / (moneyline + 100.0)
    return abs(moneyline) / (abs(moneyline) + 100.0)

def add_team_history_features(df):
    df = df.sort_values("game_date").copy()
    for side in ["home", "away"]:
        team_col = f"{side}_team"
        score_col = f"{side}_score"
        margin_col = "margin" if side == "home" else "away_margin"
        if side == "away":
            df["away_margin"] = -df["margin"]
        df[f"{side}_score_lag_1"] = df.groupby(team_col)[score_col].shift(1)
        df[f"{side}_margin_lag_1"] = df.groupby(team_col)[margin_col].shift(1)
        df[f"{side}_score_roll_3"] = (
            df.groupby(team_col)[score_col]
            .rolling(3, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        df[f"{side}_margin_roll_3"] = (
            df.groupby(team_col)[margin_col]
            .rolling(3, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        last_game_date = df.groupby(team_col)["game_date"].shift(1)
        df[f"{side}_rest_days"] = (df["game_date"] - last_game_date).dt.days
    return df

def add_market_features(df):
    df = df.copy()
    df["market_implied_prob_home"] = df["market_moneyline_home"].apply(implied_probability)
    df["market_implied_prob_away"] = df["market_moneyline_away"].apply(implied_probability)
    df["market_moneyline_delta"] = df["market_moneyline_home"] - df["market_moneyline_away"]
    return df

def _round_order(series):
    def convert(x):
        if pd.isna(x):
            return 0
        x = str(x).strip()
        return ROUND_ORDER_MAP.get(x, 0)
    return series.apply(convert)

def _seed_matchup_bucket(seed_diff):
    seed_diff = abs(seed_diff)
    if seed_diff == 0:
        return 0
    if seed_diff <= 2:
        return 1
    if seed_diff <= 5:
        return 2
    if seed_diff <= 8:
        return 3
    return 4

def _upset_band(seed_home, seed_away):
    favored_seed = min(seed_home, seed_away)
    dog_seed = max(seed_home, seed_away)
    gap = dog_seed - favored_seed
    if gap >= 8:
        return 3
    if gap >= 4:
        return 2
    if gap >= 1:
        return 1
    return 0

def add_ncaa_mbb_tournament_features(df):
    df = df.copy()

    for col, default in [
        ("is_tournament_game", 0),
        ("round_name", ""),
        ("seed_home", 0),
        ("seed_away", 0),
        ("home_seed_hist_win_pct", 0.0),
        ("away_seed_hist_win_pct", 0.0),
        ("home_seed_hist_upset_win_pct", 0.0),
        ("away_seed_hist_upset_win_pct", 0.0),
    ]:
        if col not in df.columns:
            df[col] = default

    df["is_tournament_game"] = df["is_tournament_game"].fillna(0).astype(int)
    df["round_order"] = _round_order(df["round_name"])
    df["seed_home"] = df["seed_home"].fillna(0).astype(float)
    df["seed_away"] = df["seed_away"].fillna(0).astype(float)
    df["seed_diff"] = df["seed_home"] - df["seed_away"]
    df["home_is_higher_seed"] = (
        (df["seed_home"] > 0) &
        (df["seed_away"] > 0) &
        (df["seed_home"] < df["seed_away"])
    ).astype(int)
    df["seed_matchup_bucket"] = df["seed_diff"].apply(_seed_matchup_bucket).astype(float)
    df["upset_band"] = [
        _upset_band(h, a) for h, a in zip(df["seed_home"], df["seed_away"])
    ]
    return df

def _infer_postseason_round_order(row):
    if not int(row.get("is_postseason_game", 0)):
        return 0
    text = str(row.get("round_name", "")).lower()
    sport = str(row.get("sport", "")).lower()

    if sport == "nfl":
        if "wild card" in text:
            return 1
        if "divisional" in text:
            return 2
        if "conference" in text or "afc championship" in text or "nfc championship" in text:
            return 3
        if "super bowl" in text:
            return 4
        return 1

    if sport == "mlb":
        if "wild card" in text:
            return 1
        if "division series" in text or "alds" in text or "nlds" in text:
            return 2
        if "championship series" in text or "alcs" in text or "nlcs" in text:
            return 3
        if "world series" in text:
            return 4
        return 1

    if sport == "ncaa_mbb":
        return row.get("round_order", 0)

    return 0

def add_postseason_features(df):
    df = df.copy()

    for col, default in [
        ("sport", ""),
        ("is_postseason_game", 0),
        ("round_name", ""),
        ("playoff_experience_home", 0.0),
        ("playoff_experience_away", 0.0),
    ]:
        if col not in df.columns:
            df[col] = default

    df["is_postseason_game"] = df["is_postseason_game"].fillna(0).astype(int)
    df["postseason_round_order"] = df.apply(_infer_postseason_round_order, axis=1).astype(float)
    df["postseason_round_tier"] = np.select(
        [
            df["postseason_round_order"] <= 0,
            df["postseason_round_order"] == 1,
            df["postseason_round_order"].isin([2, 3]),
            df["postseason_round_order"] >= 4,
        ],
        [0, 1, 2, 3],
        default=0
    ).astype(float)

    round_text = df["round_name"].fillna("").astype(str).str.lower()
    df["championship_game_flag"] = (
        round_text.str.contains("championship") |
        round_text.str.contains("super bowl") |
        round_text.str.contains("world series")
    ).astype(int)

    df["playoff_experience_home"] = df["playoff_experience_home"].fillna(0).astype(float)
    df["playoff_experience_away"] = df["playoff_experience_away"].fillna(0).astype(float)
    return df

def add_targets(df):
    df = df.copy()
    df["target_home_win"] = (df["margin"] > 0).astype(int)
    df["target_cover_home"] = ((df["margin"] + df["market_spread"].fillna(0)) > 0).astype(int)
    total_score = df["home_score"] + df["away_score"]
    # Use expanding median (only past games) to avoid future-data leakage
    expanding_median = total_score.expanding(min_periods=1).median().shift(1)
    fallback_line = expanding_median.fillna(
        total_score.iloc[:10].median() if len(total_score) >= 10 else 45.0
    )
    df["target_total_over"] = (total_score > df["market_total_line"].fillna(fallback_line)).astype(int)
    return df

def encode_teams(df):
    df = df.copy()
    all_teams = pd.Index(sorted(pd.concat([df["home_team"], df["away_team"]]).dropna().unique()))
    team_to_id = {team: idx for idx, team in enumerate(all_teams)}
    df["home_team_encoded"] = df["home_team"].map(team_to_id).fillna(0).astype(int)
    df["away_team_encoded"] = df["away_team"].map(team_to_id).fillna(0).astype(int)
    return df, team_to_id

def add_nfl_context_features(df):
    df = df.copy()

    for col, default in [
        ("week_number", 0),
        ("indoor", 0),
        ("surface", "turf"),
        ("home_rest_days", np.nan),
        ("away_rest_days", np.nan),
    ]:
        if col not in df.columns:
            df[col] = default

    df["is_indoor"] = df["indoor"].fillna(0).astype(int)
    df["surface_is_grass"] = (df["surface"].fillna("turf") == "grass").astype(int)
    df["rest_advantage"] = df["home_rest_days"].fillna(7) - df["away_rest_days"].fillna(7)
    df["is_short_week"] = (
        (df["home_rest_days"].fillna(7) < 6) | (df["away_rest_days"].fillna(7) < 6)
    ).astype(int)
    return df


def _team_rolling_stats(df, stat_cols, game_id_col="game_id", window=3):
    """Compute rolling averages across ALL games for each team (home + away).

    Steps:
      1. Stack home and away rows into a single team-centric view.
      2. Sort by game_date and compute shift(1).rolling(window).mean() per team.
      3. Merge rolling values back to the original frame on (game_id, team).

    Returns the original ``df`` with ``{side}_{stat}_roll{window}`` columns added.
    """
    df = df.copy()

    # Ensure a game_id column exists for merging back
    has_game_id = game_id_col in df.columns
    if not has_game_id:
        df[game_id_col] = np.arange(len(df))

    # Build home rows and away rows with unified column names
    home_records = []
    away_records = []
    for col in stat_cols:
        home_src = f"home_{col}"
        away_src = f"away_{col}"
        if home_src not in df.columns:
            df[home_src] = 0.0
        if away_src not in df.columns:
            df[away_src] = 0.0
        home_records.append(home_src)
        away_records.append(away_src)

    # Stack: one row per team per game
    home_part = df[[game_id_col, "game_date", "home_team"] + home_records].copy()
    home_part = home_part.rename(
        columns={"home_team": "team", **{f"home_{c}": c for c in stat_cols}}
    )
    home_part["_side"] = "home"

    away_part = df[[game_id_col, "game_date", "away_team"] + away_records].copy()
    away_part = away_part.rename(
        columns={"away_team": "team", **{f"away_{c}": c for c in stat_cols}}
    )
    away_part["_side"] = "away"

    stacked = pd.concat([home_part, away_part], ignore_index=True)
    stacked = stacked.sort_values(["team", "game_date"]).reset_index(drop=True)

    # Compute rolling stats on the continuous per-team series
    for col in stat_cols:
        stacked[f"{col}_roll{window}"] = (
            stacked.groupby("team")[col]
            .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
        )

    # Split back into home and away, merge onto original df
    home_rolled = stacked[stacked["_side"] == "home"][
        [game_id_col] + [f"{c}_roll{window}" for c in stat_cols]
    ]
    home_rolled = home_rolled.rename(
        columns={f"{c}_roll{window}": f"home_{c}_roll{window}" for c in stat_cols}
    )
    away_rolled = stacked[stacked["_side"] == "away"][
        [game_id_col] + [f"{c}_roll{window}" for c in stat_cols]
    ]
    away_rolled = away_rolled.rename(
        columns={f"{c}_roll{window}": f"away_{c}_roll{window}" for c in stat_cols}
    )

    df = df.merge(home_rolled, on=game_id_col, how="left")
    df = df.merge(away_rolled, on=game_id_col, how="left")

    if not has_game_id:
        df = df.drop(columns=[game_id_col])

    return df


def add_nfl_game_stats_features(df):
    df = df.sort_values("game_date").copy()

    stat_cols = [
        "total_yards", "passing_yards", "rushing_yards", "turnovers",
        "third_down_att", "third_down_conv", "red_zone_att", "red_zone_conv",
        "possession_secs", "sacks_allowed", "penalty_yards",
    ]

    df = _team_rolling_stats(df, stat_cols, window=3)

    for side in ["home", "away"]:
        att_col = f"{side}_third_down_att_roll3"
        conv_col = f"{side}_third_down_conv_roll3"
        df[f"{side}_third_down_pct_roll3"] = np.where(
            df[att_col] > 0, df[conv_col] / df[att_col], 0.0
        )
        rz_att_col = f"{side}_red_zone_att_roll3"
        rz_conv_col = f"{side}_red_zone_conv_roll3"
        df[f"{side}_red_zone_pct_roll3"] = np.where(
            df[rz_att_col] > 0, df[rz_conv_col] / df[rz_att_col], 0.0
        )

    df["turnover_margin_roll3"] = (
        df["away_turnovers_roll3"] - df["home_turnovers_roll3"]
    )
    df["yards_advantage_roll3"] = (
        df["home_total_yards_roll3"] - df["away_total_yards_roll3"]
    )
    return df


def add_nfl_standing_features(df):
    df = df.copy()

    for col, default in [
        ("home_wins", 0), ("home_losses", 0), ("home_win_pct", 0.0),
        ("home_home_wins", 0), ("home_home_losses", 0),
        ("home_away_wins", 0), ("home_away_losses", 0),
        ("home_streak", 0),
        ("away_wins", 0), ("away_losses", 0), ("away_win_pct", 0.0),
        ("away_home_wins", 0), ("away_home_losses", 0),
        ("away_away_wins", 0), ("away_away_losses", 0),
        ("away_streak", 0),
    ]:
        if col not in df.columns:
            df[col] = default

    df["win_pct_diff"] = df["home_win_pct"].fillna(0) - df["away_win_pct"].fillna(0)

    home_home_total = df["home_home_wins"] + df["home_home_losses"]
    df["home_home_win_pct"] = np.where(
        home_home_total > 0, df["home_home_wins"] / home_home_total, 0.0
    )
    away_away_total = df["away_away_wins"] + df["away_away_losses"]
    df["away_away_win_pct"] = np.where(
        away_away_total > 0, df["away_away_wins"] / away_away_total, 0.0
    )
    df["home_streak"] = df["home_streak"].fillna(0).astype(float)
    df["away_streak"] = df["away_streak"].fillna(0).astype(float)
    return df


def add_nfl_injury_features(df):
    df = df.copy()

    for col, default in [
        ("home_players_out", 0), ("home_skill_out", 0),
        ("home_qb_out", 0), ("home_players_doubtful", 0),
        ("away_players_out", 0), ("away_skill_out", 0),
        ("away_qb_out", 0), ("away_players_doubtful", 0),
    ]:
        if col not in df.columns:
            df[col] = default

    df["injury_advantage"] = (
        df["away_players_out"].fillna(0) - df["home_players_out"].fillna(0)
    )
    df["home_qb_out"] = df["home_qb_out"].fillna(0).astype(int)
    df["away_qb_out"] = df["away_qb_out"].fillna(0).astype(int)
    return df


def add_ncaa_mbb_context_features(df):
    df = df.copy()

    for col, default in [
        ("neutral_site", 0),
        ("is_conference_game", 0),
        ("home_conf_wins", 0), ("home_conf_losses", 0),
        ("away_conf_wins", 0), ("away_conf_losses", 0),
    ]:
        if col not in df.columns:
            df[col] = default

    df["neutral_site"] = df["neutral_site"].fillna(0).astype(int)
    df["is_conference_game"] = df["is_conference_game"].fillna(0).astype(int)

    home_conf_total = df["home_conf_wins"] + df["home_conf_losses"]
    df["home_conf_win_pct"] = np.where(home_conf_total > 0, df["home_conf_wins"] / home_conf_total, 0.0)
    away_conf_total = df["away_conf_wins"] + df["away_conf_losses"]
    df["away_conf_win_pct"] = np.where(away_conf_total > 0, df["away_conf_wins"] / away_conf_total, 0.0)
    df["conf_win_pct_diff"] = df["home_conf_win_pct"] - df["away_conf_win_pct"]

    away_road_total = df["away_away_wins"] + df["away_away_losses"]
    df["away_road_win_pct"] = np.where(away_road_total > 0, df["away_away_wins"] / away_road_total, 0.0)

    return df


def add_ncaa_mbb_game_stats_features(df):
    df = df.sort_values("game_date").copy()

    stat_cols = [
        "fg_pct", "three_pt_pct", "ft_pct",
        "total_rebounds", "off_rebounds", "assists",
        "turnovers_mbb", "fast_break_points", "points_in_paint",
    ]

    df = _team_rolling_stats(df, stat_cols, window=3)

    df["rebound_margin_mbb_roll3"] = (
        df["home_total_rebounds_roll3"] - df["away_total_rebounds_roll3"]
    )
    df["turnover_margin_mbb_roll3"] = (
        df["away_turnovers_mbb_roll3"] - df["home_turnovers_mbb_roll3"]
    )
    return df


def add_ncaa_mbb_bpi_features(df):
    df = df.copy()

    for col, default in [
        ("home_bpi", 0.0), ("away_bpi", 0.0),
        ("home_bpi_offense", 0.0), ("away_bpi_offense", 0.0),
        ("home_bpi_defense", 0.0), ("away_bpi_defense", 0.0),
        ("home_sor", 0.0), ("away_sor", 0.0),
        ("home_ap_rank", 99), ("away_ap_rank", 99),
        ("home_pred_win_pct", 0.0), ("home_pred_mov", 0.0),
        ("matchup_quality", 0.0),
    ]:
        if col not in df.columns:
            df[col] = default

    df["bpi_diff"] = df["home_bpi"].fillna(0) - df["away_bpi"].fillna(0)
    df["bpi_offense_vs_defense"] = df["home_bpi_offense"].fillna(0) - df["away_bpi_defense"].fillna(0)
    df["sor_diff"] = df["home_sor"].fillna(0) - df["away_sor"].fillna(0)

    df["home_is_ranked"] = (df["home_ap_rank"].fillna(99) < 99).astype(int)
    df["away_is_ranked"] = (df["away_ap_rank"].fillna(99) < 99).astype(int)
    # Positive = home team has better (lower) rank
    df["rank_advantage"] = df["away_ap_rank"].fillna(99) - df["home_ap_rank"].fillna(99)

    df["home_pred_win_pct"] = df["home_pred_win_pct"].fillna(0).astype(float)
    df["home_pred_mov"] = df["home_pred_mov"].fillna(0).astype(float)
    df["matchup_quality"] = df["matchup_quality"].fillna(0).astype(float)

    return df


def finalize_feature_frame(df):
    df = add_team_history_features(df)
    df = add_market_features(df)
    df = add_ncaa_mbb_tournament_features(df)
    df = add_postseason_features(df)
    df = add_nfl_context_features(df)
    df = add_nfl_game_stats_features(df)
    df = add_nfl_standing_features(df)
    df = add_nfl_injury_features(df)
    df = add_ncaa_mbb_context_features(df)
    df = add_ncaa_mbb_game_stats_features(df)
    df = add_ncaa_mbb_bpi_features(df)
    df = add_targets(df)
    df, team_to_id = encode_teams(df)
    df = df.fillna(0)
    return df, team_to_id
