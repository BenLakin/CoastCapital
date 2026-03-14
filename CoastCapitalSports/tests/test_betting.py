"""
Tests for betting/recommender.py — odds conversion, Kelly allocation, and
recommendation generation.

Tests math functions directly and mocks DB/model dependencies for integration.
"""

from unittest.mock import MagicMock, patch

import pytest

from betting.recommender import (
    KELLY_FRACTION,
    MIN_EDGE,
    STANDARD_SPREAD_TOTAL_ML,
    _allocate_bankroll,
    _moneyline_to_decimal_odds,
    _moneyline_to_implied_prob,
)


# ── Moneyline → Implied Probability ──────────────────────────────────────────

class TestMoneylineToImpliedProb:
    def test_favorite_negative_odds(self):
        """−150 → 60%"""
        assert _moneyline_to_implied_prob(-150) == pytest.approx(0.6, abs=1e-4)

    def test_underdog_positive_odds(self):
        """+200 → 33.3%"""
        assert _moneyline_to_implied_prob(200) == pytest.approx(1 / 3, abs=1e-4)

    def test_even_odds(self):
        """+100 → 50%"""
        assert _moneyline_to_implied_prob(100) == pytest.approx(0.5)

    def test_heavy_favorite(self):
        """−300 → 75%"""
        assert _moneyline_to_implied_prob(-300) == pytest.approx(0.75)

    def test_none_returns_half(self):
        assert _moneyline_to_implied_prob(None) == 0.5

    def test_zero_returns_half(self):
        assert _moneyline_to_implied_prob(0) == 0.5

    def test_standard_vig_line(self):
        """−110 each side is the industry standard."""
        prob = _moneyline_to_implied_prob(-110)
        assert prob == pytest.approx(110 / 210, abs=1e-4)


# ── Moneyline → Decimal Odds ─────────────────────────────────────────────────

class TestMoneylineToDecimalOdds:
    def test_favorite(self):
        """−150 → 1.667"""
        assert _moneyline_to_decimal_odds(-150) == pytest.approx(100 / 150 + 1, abs=1e-3)

    def test_underdog(self):
        """+200 → 3.0"""
        assert _moneyline_to_decimal_odds(200) == pytest.approx(3.0)

    def test_even(self):
        """+100 → 2.0"""
        assert _moneyline_to_decimal_odds(100) == pytest.approx(2.0)

    def test_none_returns_2(self):
        assert _moneyline_to_decimal_odds(None) == 2.0

    def test_zero_returns_2(self):
        assert _moneyline_to_decimal_odds(0) == 2.0

    def test_heavy_underdog(self):
        """+500 → 6.0"""
        assert _moneyline_to_decimal_odds(500) == pytest.approx(6.0)

    def test_heavy_favorite(self):
        """−500 → 1.2"""
        assert _moneyline_to_decimal_odds(-500) == pytest.approx(1.2)


# ── Kelly Bankroll Allocation ─────────────────────────────────────────────────

class TestAllocateBankroll:
    def test_empty_bets_returns_empty(self):
        assert _allocate_bankroll([], bankroll=100, max_pct=0.5) == []

    def test_wager_does_not_exceed_max(self):
        bets = [{
            "edge": 0.10,
            "decimal_odds": 2.0,
            "model_prob": 0.60,
            "ev": 0.20,
        }]
        result = _allocate_bankroll(bets, bankroll=100, max_pct=0.25)
        assert result[0]["wager"] <= 25.0

    def test_kelly_fraction_computed(self):
        bets = [{
            "edge": 0.05,
            "decimal_odds": 2.0,
            "model_prob": 0.55,
            "ev": 0.10,
        }]
        result = _allocate_bankroll(bets, bankroll=100, max_pct=0.50)
        assert result[0]["kelly_fraction"] > 0
        assert result[0]["kelly_fraction"] <= 1.0

    def test_uses_quarter_kelly(self):
        """Kelly should be multiplied by KELLY_FRACTION (0.25)."""
        bets = [{
            "edge": 0.10,
            "decimal_odds": 2.0,
            "model_prob": 0.60,
            "ev": 0.20,
        }]
        result = _allocate_bankroll(bets, bankroll=1000, max_pct=1.0)
        # Full Kelly = (1*0.6 - 0.4)/1 = 0.2
        # Quarter Kelly = 0.05
        assert result[0]["kelly_fraction"] == pytest.approx(0.05, abs=0.01)

    def test_zero_edge_filtered_out(self):
        """Bets with zero edge → zero Kelly → zero wager → filtered."""
        bets = [{
            "edge": 0.0,
            "decimal_odds": 2.0,
            "model_prob": 0.50,
            "ev": 0.0,
        }]
        result = _allocate_bankroll(bets, bankroll=100, max_pct=0.50)
        assert len(result) == 0

    def test_negative_kelly_filtered(self):
        """Negative edge should produce zero Kelly fraction."""
        bets = [{
            "edge": -0.10,
            "decimal_odds": 2.0,
            "model_prob": 0.40,
            "ev": -0.20,
        }]
        result = _allocate_bankroll(bets, bankroll=100, max_pct=0.50)
        assert len(result) == 0

    def test_potential_profit_calculated(self):
        bets = [{
            "edge": 0.10,
            "decimal_odds": 3.0,
            "model_prob": 0.60,
            "ev": 0.80,
        }]
        result = _allocate_bankroll(bets, bankroll=100, max_pct=1.0)
        if result:
            wager = result[0]["wager"]
            expected_profit = round(wager * (3.0 - 1), 2)
            assert result[0]["potential_profit"] == expected_profit

    def test_sorted_by_ev_descending(self):
        bets = [
            {"edge": 0.05, "decimal_odds": 2.0, "model_prob": 0.55, "ev": 0.10},
            {"edge": 0.15, "decimal_odds": 2.5, "model_prob": 0.65, "ev": 0.50},
            {"edge": 0.10, "decimal_odds": 2.0, "model_prob": 0.60, "ev": 0.20},
        ]
        result = _allocate_bankroll(bets, bankroll=100, max_pct=0.50)
        evs = [b["ev"] for b in result]
        assert evs == sorted(evs, reverse=True)

    def test_bankroll_not_exceeded(self):
        """Total wagered should not exceed bankroll."""
        bets = [
            {"edge": 0.20, "decimal_odds": 2.0, "model_prob": 0.70, "ev": 0.40},
            {"edge": 0.20, "decimal_odds": 2.0, "model_prob": 0.70, "ev": 0.40},
            {"edge": 0.20, "decimal_odds": 2.0, "model_prob": 0.70, "ev": 0.40},
            {"edge": 0.20, "decimal_odds": 2.0, "model_prob": 0.70, "ev": 0.40},
        ]
        result = _allocate_bankroll(bets, bankroll=50, max_pct=0.50)
        total_wagered = sum(b["wager"] for b in result)
        assert total_wagered <= 50.0


# ── get_betting_recommendations (integration) ────────────────────────────────

class TestGetBettingRecommendations:
    @patch("betting.recommender._store_bets_to_tracking")
    @patch("betting.recommender._score_games_with_model", return_value=[])
    def test_no_games_returns_empty(self, mock_score, mock_store):
        from betting.recommender import get_betting_recommendations
        result = get_betting_recommendations(bankroll=50.0)
        assert result["bet_count"] == 0
        assert result["bets"] == []
        assert result["bankroll"] == 50.0

    @patch("betting.recommender._store_bets_to_tracking")
    @patch("betting.recommender._score_games_with_model")
    def test_deduplicates_by_game_and_target(self, mock_score, mock_store):
        from betting.recommender import get_betting_recommendations
        mock_score.return_value = [
            {
                "game_id": "g1", "target": "home_win", "edge": 0.10,
                "decimal_odds": 2.0, "model_prob": 0.60, "ev": 0.20,
                "sport": "nfl",
            },
            {
                "game_id": "g1", "target": "home_win", "edge": 0.05,
                "decimal_odds": 2.0, "model_prob": 0.55, "ev": 0.10,
                "sport": "nfl",
            },
        ]
        result = get_betting_recommendations(bankroll=50.0)
        # Should keep the one with higher edge
        game_target_pairs = [(b["game_id"], b["target"]) for b in result.get("bets", [])]
        # At most one bet per (game_id, target)
        assert len(game_target_pairs) == len(set(game_target_pairs))

    @patch("betting.recommender._store_bets_to_tracking")
    @patch("betting.recommender._score_games_with_model", return_value=[])
    def test_response_structure(self, mock_score, mock_store):
        from betting.recommender import get_betting_recommendations
        result = get_betting_recommendations(bankroll=100.0, max_pct=0.25)
        assert "bankroll" in result
        assert "max_per_game" in result
        assert result["max_per_game"] == 25.0
        assert "bets" in result
        assert "total_wagered" in result
        assert "remaining_bankroll" in result
        assert "generated_at" in result
