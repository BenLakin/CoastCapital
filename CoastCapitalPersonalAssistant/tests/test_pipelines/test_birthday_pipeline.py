"""
Unit tests for BirthdayPipeline.

Focuses on:
1. _needs_update — preference update trigger logic
2. _next_birthday — correct year calculation
3. _days_until_birthday — correct countdown
4. log_preference — DB write (with mock)
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from freezegun import freeze_time


def _make_pipeline():
    with patch("anthropic.Anthropic"):
        from app.pipelines.birthday_pipeline import BirthdayPipeline
        p = BirthdayPipeline()
        p.client = MagicMock()
        return p


# Frozen to a stable reference date for all birthday tests
FROZEN_DATE = "2026-03-08"


# ── _needs_update ─────────────────────────────────────────────────────────────

class TestNeedsUpdate:
    def setup_method(self):
        self.p = _make_pipeline()

    def test_far_birthday_never_needs_update(self):
        """Birthday > PROMPT_DAYS (21) away → no update needed regardless of prefs."""
        person = {"days_away": 25}
        assert self.p._needs_update(person, []) is False

    def test_far_birthday_even_with_no_prefs(self):
        person = {"days_away": 30}
        assert self.p._needs_update(person, []) is False

    def test_soon_birthday_no_prefs_needs_update(self):
        person = {"days_away": 10}
        assert self.p._needs_update(person, []) is True

    def test_soon_birthday_sparse_prefs_needs_update(self):
        """Fewer than 3 active preferences → always prompt."""
        person = {"days_away": 7}
        prefs = [{"category": "food", "recorded_at": "2026-01-01"}]
        assert self.p._needs_update(person, prefs) is True

    @freeze_time(FROZEN_DATE)
    def test_soon_birthday_stale_prefs_needs_update(self):
        """3+ prefs but recorded 7+ months ago → prompt for refresh."""
        person = {"days_away": 5}
        old = "2025-07-01"  # ~8 months before 2026-03-08
        prefs = [
            {"category": "food",    "recorded_at": old},
            {"category": "hobbies", "recorded_at": old},
            {"category": "books",   "recorded_at": old},
        ]
        assert self.p._needs_update(person, prefs) is True

    @freeze_time(FROZEN_DATE)
    def test_soon_birthday_fresh_prefs_no_update(self):
        """3+ prefs recorded recently → no update needed."""
        person = {"days_away": 5}
        recent = "2026-03-01"  # 7 days ago
        prefs = [
            {"category": "food",    "recorded_at": recent},
            {"category": "hobbies", "recorded_at": recent},
            {"category": "books",   "recorded_at": recent},
        ]
        assert self.p._needs_update(person, prefs) is False

    def test_today_birthday_no_prefs_needs_update(self):
        person = {"days_away": 0}
        assert self.p._needs_update(person, []) is True

    def test_exactly_prompt_days_boundary(self):
        """days_away == PROMPT_DAYS (21) is still ≤ threshold → evaluate prefs."""
        person = {"days_away": 21}
        assert self.p._needs_update(person, []) is True

    def test_one_over_prompt_days_no_update(self):
        person = {"days_away": 22}
        assert self.p._needs_update(person, []) is False


# ── _next_birthday ────────────────────────────────────────────────────────────

class TestNextBirthday:
    def setup_method(self):
        self.p = _make_pipeline()

    def test_none_returns_none(self):
        assert self.p._next_birthday(None) is None

    def test_empty_string_returns_none(self):
        assert self.p._next_birthday("") is None

    @freeze_time(FROZEN_DATE)
    def test_future_birthday_this_year(self):
        """Dec 25 birthday hasn't happened yet in March → stays this year."""
        result = self.p._next_birthday("1990-12-25")
        assert result == "2026-12-25"

    @freeze_time(FROZEN_DATE)
    def test_past_birthday_advances_to_next_year(self):
        """Jan 1 birthday has already passed by March → next year."""
        result = self.p._next_birthday("1990-01-01")
        assert result == "2027-01-01"

    @freeze_time(FROZEN_DATE)
    def test_birthday_today_returns_today(self):
        """Birthday on the frozen date itself → today (not next year)."""
        result = self.p._next_birthday("1985-03-08")
        assert result == "2026-03-08"

    @freeze_time(FROZEN_DATE)
    def test_birthday_tomorrow_returns_tomorrow(self):
        result = self.p._next_birthday("2000-03-09")
        assert result == "2026-03-09"

    @freeze_time(FROZEN_DATE)
    def test_birthday_yesterday_advances_year(self):
        result = self.p._next_birthday("2000-03-07")
        assert result == "2027-03-07"

    def test_invalid_string_returns_none(self):
        assert self.p._next_birthday("not-a-date") is None


# ── _days_until_birthday ──────────────────────────────────────────────────────

class TestDaysUntilBirthday:
    def setup_method(self):
        self.p = _make_pipeline()

    def test_none_returns_none(self):
        assert self.p._days_until_birthday(None) is None

    @freeze_time(FROZEN_DATE)
    def test_future_birthday_correct_count(self):
        # Dec 25 → 2026-12-25; from 2026-03-08 that's 292 days
        result = self.p._days_until_birthday("1990-12-25")
        assert result == (date(2026, 12, 25) - date(2026, 3, 8)).days

    @freeze_time(FROZEN_DATE)
    def test_birthday_today_returns_zero(self):
        result = self.p._days_until_birthday("1990-03-08")
        assert result == 0

    @freeze_time(FROZEN_DATE)
    def test_result_is_never_negative(self):
        """Next birthday is always in the future or today → non-negative."""
        for bday in ("1990-01-01", "1990-03-07", "1990-12-31"):
            result = self.p._days_until_birthday(bday)
            assert result is None or result >= 0


# ── log_preference (DB interaction) ──────────────────────────────────────────

class TestLogPreference:
    def setup_method(self):
        self.p = _make_pipeline()

    def test_log_preference_calls_db_insert(self):
        mock_cur = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        # Patch the reference inside the birthday_pipeline module (already imported)
        with patch("app.pipelines.birthday_pipeline.get_conn", return_value=mock_conn):
            result = self.p.log_preference(
                relationship_id=1,
                category="food & restaurants",
                preference="Italian cuisine",
                source="manual",
            )

        assert result["success"] is True
        assert mock_cur.execute.call_count >= 1  # INSERT + UPDATE

    def test_log_preference_returns_error_on_db_failure(self):
        with patch("app.pipelines.birthday_pipeline.get_conn",
                   side_effect=Exception("DB down")):
            result = self.p.log_preference(
                relationship_id=1,
                category="food",
                preference="Pizza",
            )
        assert "error" in result

    def test_log_preference_includes_relationship_id_and_category(self):
        mock_cur = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur

        with patch("app.pipelines.birthday_pipeline.get_conn", return_value=mock_conn):
            result = self.p.log_preference(
                relationship_id=42,
                category="hobbies & activities",
                preference="Rock climbing",
            )

        assert result.get("relationship_id") == 42
        assert result.get("category") == "hobbies & activities"
