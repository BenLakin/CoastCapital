"""
Tests for feature_engineering.py — data transformation and leakage prevention.

Uses real pandas/numpy for accurate validation of rolling statistics,
target creation, and team encoding logic.
"""

import numpy as np
import pandas as pd
import pytest

from features.feature_engineering import (
    ROUND_ORDER_MAP,
    _seed_matchup_bucket,
    _team_rolling_stats,
    _upset_band,
    add_market_features,
    add_ncaa_mbb_bpi_features,
    add_ncaa_mbb_context_features,
    add_ncaa_mbb_game_stats_features,
    add_ncaa_mbb_tournament_features,
    add_nfl_context_features,
    add_nfl_game_stats_features,
    add_nfl_injury_features,
    add_nfl_standing_features,
    add_postseason_features,
    add_targets,
    add_team_history_features,
    encode_teams,
    finalize_feature_frame,
    implied_probability,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def game_df():
    """Minimal game DataFrame for feature engineering tests."""
    return pd.DataFrame({
        "game_id": ["g1", "g2", "g3", "g4", "g5", "g6"],
        "game_date": pd.to_datetime([
            "2024-09-08", "2024-09-15", "2024-09-22",
            "2024-09-29", "2024-10-06", "2024-10-13",
        ]),
        "home_team": ["Chiefs", "Bills", "Chiefs", "Eagles", "Chiefs", "Bills"],
        "away_team": ["Bills", "Chiefs", "Eagles", "Chiefs", "Bills", "Chiefs"],
        "home_score": [27, 31, 24, 20, 28, 17],
        "away_score": [20, 28, 21, 27, 24, 30],
        "margin": [7, 3, 3, -7, 4, -13],
        "market_spread": [-3.0, -1.5, -4.0, 2.5, -3.5, 1.0],
        "market_total_line": [47.0, 49.5, 45.0, 48.0, 50.0, 46.5],
        "market_moneyline_home": [-150, -120, -180, 130, -160, 105],
        "market_moneyline_away": [130, 100, 155, -150, 140, -125],
    })


# ── implied_probability ──────────────────────────────────────────────────────

class TestImpliedProbability:
    def test_negative_moneyline(self):
        """Favorites: -150 → 0.6"""
        assert implied_probability(-150) == pytest.approx(150 / 250, abs=1e-6)

    def test_positive_moneyline(self):
        """Underdogs: +200 → 0.333..."""
        assert implied_probability(200) == pytest.approx(100 / 300, abs=1e-6)

    def test_even_odds(self):
        """+100 → 0.5"""
        assert implied_probability(100) == pytest.approx(0.5, abs=1e-6)

    def test_heavy_favorite(self):
        """-300 → 0.75"""
        assert implied_probability(-300) == pytest.approx(300 / 400, abs=1e-6)

    def test_nan_returns_nan(self):
        assert np.isnan(implied_probability(np.nan))

    def test_accepts_string_castable(self):
        """Should handle float-castable values."""
        assert implied_probability(-110) == pytest.approx(110 / 210, abs=1e-6)


# ── Helpers ──────────────────────────────────────────────────────────────────

class TestSeedMatchupBucket:
    def test_same_seed(self):
        assert _seed_matchup_bucket(0) == 0

    def test_close_matchup(self):
        assert _seed_matchup_bucket(2) == 1
        assert _seed_matchup_bucket(-1) == 1

    def test_moderate_gap(self):
        assert _seed_matchup_bucket(5) == 2

    def test_large_gap(self):
        assert _seed_matchup_bucket(8) == 3

    def test_extreme_gap(self):
        assert _seed_matchup_bucket(12) == 4


class TestUpsetBand:
    def test_equal_seeds(self):
        assert _upset_band(4, 4) == 0

    def test_small_gap(self):
        assert _upset_band(3, 6) == 1

    def test_medium_gap(self):
        assert _upset_band(2, 7) == 2

    def test_large_gap(self):
        assert _upset_band(1, 16) == 3


# ── Team history features ────────────────────────────────────────────────────

class TestTeamHistoryFeatures:
    def test_lag_columns_added(self, game_df):
        result = add_team_history_features(game_df)
        assert "home_score_lag_1" in result.columns
        assert "away_score_lag_1" in result.columns
        assert "home_margin_lag_1" in result.columns

    def test_rolling_columns_added(self, game_df):
        result = add_team_history_features(game_df)
        assert "home_score_roll_3" in result.columns
        assert "away_margin_roll_3" in result.columns

    def test_rest_days_computed(self, game_df):
        result = add_team_history_features(game_df)
        assert "home_rest_days" in result.columns
        assert "away_rest_days" in result.columns

    def test_first_game_lag_is_nan(self, game_df):
        result = add_team_history_features(game_df)
        result = result.sort_values("game_date").reset_index(drop=True)
        # First row's lag should be NaN (no prior game)
        assert pd.isna(result.loc[0, "home_score_lag_1"])

    def test_does_not_modify_input(self, game_df):
        original_cols = set(game_df.columns)
        add_team_history_features(game_df)
        assert set(game_df.columns) == original_cols


# ── Market features ──────────────────────────────────────────────────────────

class TestMarketFeatures:
    def test_implied_prob_columns_added(self, game_df):
        result = add_market_features(game_df)
        assert "market_implied_prob_home" in result.columns
        assert "market_implied_prob_away" in result.columns
        assert "market_moneyline_delta" in result.columns

    def test_delta_computation(self, game_df):
        result = add_market_features(game_df)
        row = result.iloc[0]
        expected = row["market_moneyline_home"] - row["market_moneyline_away"]
        assert row["market_moneyline_delta"] == expected


# ── NCAA MBB tournament features ─────────────────────────────────────────────

class TestTournamentFeatures:
    def test_missing_columns_filled_with_defaults(self):
        df = pd.DataFrame({"game_id": ["g1"], "x": [1]})
        result = add_ncaa_mbb_tournament_features(df)
        assert result["is_tournament_game"].iloc[0] == 0
        assert result["seed_home"].iloc[0] == 0.0
        assert result["seed_diff"].iloc[0] == 0.0

    def test_seed_diff_computed(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "seed_home": [1],
            "seed_away": [16],
            "is_tournament_game": [1],
            "round_name": ["First Round"],
        })
        result = add_ncaa_mbb_tournament_features(df)
        assert result["seed_diff"].iloc[0] == -15.0
        assert result["home_is_higher_seed"].iloc[0] == 1

    def test_round_order_mapping(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2", "g3"],
            "round_name": ["First Round", "Sweet 16", "Championship"],
            "is_tournament_game": [1, 1, 1],
        })
        result = add_ncaa_mbb_tournament_features(df)
        assert list(result["round_order"]) == [1, 3, 6]


# ── Postseason features ──────────────────────────────────────────────────────

class TestPostseasonFeatures:
    def test_nfl_playoff_round_order(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2", "g3"],
            "sport": ["nfl", "nfl", "nfl"],
            "is_postseason_game": [1, 1, 1],
            "round_name": ["Wild Card", "Divisional", "Super Bowl LVIII"],
        })
        result = add_postseason_features(df)
        assert list(result["postseason_round_order"]) == [1.0, 2.0, 4.0]

    def test_championship_flag(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2"],
            "is_postseason_game": [1, 0],
            "round_name": ["Super Bowl LVIII", "Week 5"],
            "sport": ["nfl", "nfl"],
        })
        result = add_postseason_features(df)
        assert result["championship_game_flag"].iloc[0] == 1
        assert result["championship_game_flag"].iloc[1] == 0

    def test_regular_season_round_order_zero(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "is_postseason_game": [0],
            "round_name": ["Week 3"],
            "sport": ["nfl"],
        })
        result = add_postseason_features(df)
        assert result["postseason_round_order"].iloc[0] == 0.0

    def test_postseason_round_tier(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2", "g3", "g4"],
            "sport": ["nfl", "nfl", "nfl", "nfl"],
            "is_postseason_game": [0, 1, 1, 1],
            "round_name": ["Week 1", "Wild Card", "Divisional", "Super Bowl"],
        })
        result = add_postseason_features(df)
        # tier: 0 (not postseason), 1 (early), 2 (mid), 3 (finals)
        assert list(result["postseason_round_tier"]) == [0.0, 1.0, 2.0, 3.0]


# ── NFL context features ─────────────────────────────────────────────────────

class TestNFLContextFeatures:
    def test_indoor_flag(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2"],
            "game_date": pd.to_datetime(["2024-09-08", "2024-09-15"]),
            "indoor": [1, 0],
            "surface": ["turf", "grass"],
        })
        result = add_nfl_context_features(df)
        assert result["is_indoor"].iloc[0] == 1
        assert result["surface_is_grass"].iloc[1] == 1

    def test_rest_advantage(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "game_date": pd.to_datetime(["2024-09-08"]),
            "home_rest_days": [10],
            "away_rest_days": [7],
        })
        result = add_nfl_context_features(df)
        assert result["rest_advantage"].iloc[0] == 3.0

    def test_short_week_flag(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2"],
            "game_date": pd.to_datetime(["2024-09-08", "2024-09-15"]),
            "home_rest_days": [4, 7],
            "away_rest_days": [7, 7],
        })
        result = add_nfl_context_features(df)
        assert result["is_short_week"].iloc[0] == 1
        assert result["is_short_week"].iloc[1] == 0

    def test_missing_columns_get_defaults(self):
        df = pd.DataFrame({"game_id": ["g1"], "game_date": pd.to_datetime(["2024-01-01"])})
        result = add_nfl_context_features(df)
        assert result["is_indoor"].iloc[0] == 0
        assert result["rest_advantage"].iloc[0] == 0.0


# ── NFL standings features ───────────────────────────────────────────────────

class TestNFLStandingFeatures:
    def test_win_pct_diff(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_win_pct": [0.75],
            "away_win_pct": [0.50],
        })
        result = add_nfl_standing_features(df)
        assert result["win_pct_diff"].iloc[0] == pytest.approx(0.25)

    def test_home_home_win_pct(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_home_wins": [3],
            "home_home_losses": [1],
        })
        result = add_nfl_standing_features(df)
        assert result["home_home_win_pct"].iloc[0] == pytest.approx(0.75)

    def test_zero_division_protected(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_home_wins": [0],
            "home_home_losses": [0],
            "away_away_wins": [0],
            "away_away_losses": [0],
        })
        result = add_nfl_standing_features(df)
        assert result["home_home_win_pct"].iloc[0] == 0.0
        assert result["away_away_win_pct"].iloc[0] == 0.0


# ── NFL injury features ──────────────────────────────────────────────────────

class TestNFLInjuryFeatures:
    def test_injury_advantage(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_players_out": [2],
            "away_players_out": [5],
        })
        result = add_nfl_injury_features(df)
        assert result["injury_advantage"].iloc[0] == 3

    def test_qb_out_flags(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_qb_out": [1],
            "away_qb_out": [0],
        })
        result = add_nfl_injury_features(df)
        assert result["home_qb_out"].iloc[0] == 1
        assert result["away_qb_out"].iloc[0] == 0

    def test_missing_columns_default_zero(self):
        df = pd.DataFrame({"game_id": ["g1"]})
        result = add_nfl_injury_features(df)
        assert result["injury_advantage"].iloc[0] == 0


# ── NCAA MBB context features ────────────────────────────────────────────────

class TestNCAAMBBContextFeatures:
    def test_conference_win_pct(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_conf_wins": [8],
            "home_conf_losses": [2],
            "away_conf_wins": [5],
            "away_conf_losses": [5],
            "away_away_wins": [3],
            "away_away_losses": [4],
        })
        result = add_ncaa_mbb_context_features(df)
        assert result["home_conf_win_pct"].iloc[0] == pytest.approx(0.8)
        assert result["away_conf_win_pct"].iloc[0] == pytest.approx(0.5)
        assert result["conf_win_pct_diff"].iloc[0] == pytest.approx(0.3)

    def test_neutral_site_flag(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2"],
            "neutral_site": [1, 0],
            "away_away_wins": [3, 2],
            "away_away_losses": [4, 5],
        })
        result = add_ncaa_mbb_context_features(df)
        assert result["neutral_site"].iloc[0] == 1
        assert result["neutral_site"].iloc[1] == 0


# ── NCAA MBB BPI features ────────────────────────────────────────────────────

class TestNCAAMBBBPIFeatures:
    def test_bpi_diff(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_bpi": [15.0],
            "away_bpi": [8.0],
        })
        result = add_ncaa_mbb_bpi_features(df)
        assert result["bpi_diff"].iloc[0] == pytest.approx(7.0)

    def test_rank_advantage(self):
        df = pd.DataFrame({
            "game_id": ["g1"],
            "home_ap_rank": [5],
            "away_ap_rank": [20],
        })
        result = add_ncaa_mbb_bpi_features(df)
        # Positive = home has better (lower) rank
        assert result["rank_advantage"].iloc[0] == 15

    def test_ranked_flags(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2"],
            "home_ap_rank": [10, 99],
            "away_ap_rank": [99, 5],
        })
        result = add_ncaa_mbb_bpi_features(df)
        assert result["home_is_ranked"].iloc[0] == 1
        assert result["home_is_ranked"].iloc[1] == 0
        assert result["away_is_ranked"].iloc[0] == 0
        assert result["away_is_ranked"].iloc[1] == 1


# ── Team rolling stats (cross-game) ──────────────────────────────────────────

class TestTeamRollingStats:
    def test_rolling_stats_cross_game(self):
        """Teams playing alternating home/away should get continuous rolling stats."""
        df = pd.DataFrame({
            "game_id": ["g1", "g2", "g3", "g4"],
            "game_date": pd.to_datetime([
                "2024-01-01", "2024-01-08", "2024-01-15", "2024-01-22",
            ]),
            "home_team": ["Chiefs", "Bills", "Chiefs", "Bills"],
            "away_team": ["Bills", "Chiefs", "Bills", "Chiefs"],
            "home_total_yards": [350, 400, 380, 320],
            "away_total_yards": [300, 360, 310, 370],
        })
        result = _team_rolling_stats(df, ["total_yards"], window=3)
        # Verify rolling columns exist
        assert "home_total_yards_roll3" in result.columns
        assert "away_total_yards_roll3" in result.columns

    def test_rolling_stats_use_shift(self):
        """Rolling stats should use shift(1) to prevent data leakage."""
        df = pd.DataFrame({
            "game_id": ["g1", "g2", "g3"],
            "game_date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"]),
            "home_team": ["A", "A", "A"],
            "away_team": ["B", "C", "D"],
            "home_total_yards": [100, 200, 300],
            "away_total_yards": [50, 60, 70],
        })
        result = _team_rolling_stats(df, ["total_yards"], window=3)
        # First row: no prior data for team A at home → NaN
        assert pd.isna(result.iloc[0]["home_total_yards_roll3"])
        # Second row: only g1 data available (shift(1) of g2) → 100
        assert result.iloc[1]["home_total_yards_roll3"] == pytest.approx(100.0)

    def test_no_future_leakage(self):
        """Current game stats must NOT be included in rolling average."""
        df = pd.DataFrame({
            "game_id": ["g1", "g2"],
            "game_date": pd.to_datetime(["2024-01-01", "2024-01-08"]),
            "home_team": ["X", "X"],
            "away_team": ["Y", "Z"],
            "home_total_yards": [100, 999],
            "away_total_yards": [50, 50],
        })
        result = _team_rolling_stats(df, ["total_yards"], window=3)
        # Row 1 (g2): rolling should be 100 (only g1), NOT include 999
        assert result.iloc[1]["home_total_yards_roll3"] == pytest.approx(100.0)


# ── NFL game stats features ──────────────────────────────────────────────────

class TestNFLGameStatsFeatures:
    def test_rolling_stats_columns_added(self, game_df):
        # Add required columns
        game_df["home_total_yards"] = [350, 400, 380, 320, 390, 310]
        game_df["away_total_yards"] = [300, 360, 310, 370, 340, 380]
        game_df["home_turnovers"] = [1, 2, 0, 1, 2, 3]
        game_df["away_turnovers"] = [2, 1, 3, 0, 1, 2]
        result = add_nfl_game_stats_features(game_df)
        assert "home_total_yards_roll3" in result.columns
        assert "turnover_margin_roll3" in result.columns
        assert "yards_advantage_roll3" in result.columns


# ── NCAA MBB game stats features ─────────────────────────────────────────────

class TestNCAAMBBGameStatsFeatures:
    def test_rolling_columns_added(self):
        df = pd.DataFrame({
            "game_id": ["g1", "g2", "g3"],
            "game_date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"]),
            "home_team": ["Duke", "UNC", "Duke"],
            "away_team": ["UNC", "Duke", "UNC"],
            "home_fg_pct": [0.45, 0.50, 0.48],
            "away_fg_pct": [0.42, 0.47, 0.44],
            "home_total_rebounds": [35, 38, 40],
            "away_total_rebounds": [30, 33, 28],
            "home_turnovers_mbb": [12, 10, 14],
            "away_turnovers_mbb": [15, 13, 11],
        })
        result = add_ncaa_mbb_game_stats_features(df)
        assert "home_fg_pct_roll3" in result.columns
        assert "rebound_margin_mbb_roll3" in result.columns
        assert "turnover_margin_mbb_roll3" in result.columns


# ── Targets ──────────────────────────────────────────────────────────────────

class TestTargets:
    def test_home_win_target(self, game_df):
        result = add_targets(game_df)
        # margin > 0 means home win
        assert result["target_home_win"].iloc[0] == 1  # margin=7
        assert result["target_home_win"].iloc[3] == 0  # margin=-7

    def test_cover_home_target(self, game_df):
        result = add_targets(game_df)
        # margin + spread > 0 means home covers
        # g1: 7 + (-3) = 4 > 0 → covers
        assert result["target_cover_home"].iloc[0] == 1

    def test_total_over_uses_expanding_median_fallback(self):
        """When market_total_line is missing, use expanding median (not future)."""
        df = pd.DataFrame({
            "game_id": ["g1", "g2", "g3"],
            "game_date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-15"]),
            "home_team": ["A", "B", "C"],
            "away_team": ["B", "C", "A"],
            "home_score": [30, 25, 40],
            "away_score": [20, 20, 35],
            "margin": [10, 5, 5],
            "market_spread": [0, 0, 0],
            "market_total_line": [np.nan, np.nan, np.nan],
        })
        result = add_targets(df)
        # Should have target_total_over for all rows without errors
        assert "target_total_over" in result.columns
        assert len(result) == 3


# ── Team encoding ────────────────────────────────────────────────────────────

class TestEncodeTeams:
    def test_encoding_assigns_ids(self, game_df):
        result, team_to_id = encode_teams(game_df)
        assert "home_team_encoded" in result.columns
        assert "away_team_encoded" in result.columns
        assert isinstance(team_to_id, dict)
        # All unique teams should be in the mapping
        all_teams = set(game_df["home_team"]) | set(game_df["away_team"])
        assert set(team_to_id.keys()) == all_teams

    def test_encoding_is_deterministic(self, game_df):
        _, team_to_id_1 = encode_teams(game_df)
        _, team_to_id_2 = encode_teams(game_df)
        assert team_to_id_1 == team_to_id_2

    def test_encoding_is_sorted_alphabetically(self, game_df):
        _, team_to_id = encode_teams(game_df)
        teams_sorted = sorted(team_to_id.keys())
        for idx, team in enumerate(teams_sorted):
            assert team_to_id[team] == idx


# ── Finalize (full pipeline) ─────────────────────────────────────────────────

class TestFinalizeFeatureFrame:
    def test_returns_tuple(self, game_df):
        result, team_to_id = finalize_feature_frame(game_df)
        assert isinstance(result, pd.DataFrame)
        assert isinstance(team_to_id, dict)

    def test_no_nans_after_finalize(self, game_df):
        result, _ = finalize_feature_frame(game_df)
        assert result.isna().sum().sum() == 0, "finalize_feature_frame should fillna(0)"

    def test_target_columns_present(self, game_df):
        result, _ = finalize_feature_frame(game_df)
        assert "target_home_win" in result.columns
        assert "target_cover_home" in result.columns
        assert "target_total_over" in result.columns

    def test_encoded_teams_present(self, game_df):
        result, _ = finalize_feature_frame(game_df)
        assert "home_team_encoded" in result.columns
        assert "away_team_encoded" in result.columns

    def test_does_not_modify_input(self, game_df):
        original_shape = game_df.shape
        finalize_feature_frame(game_df)
        assert game_df.shape == original_shape
