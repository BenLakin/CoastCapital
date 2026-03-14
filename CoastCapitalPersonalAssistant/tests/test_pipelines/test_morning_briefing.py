"""
Unit tests for MorningBriefingPipeline.

Focuses on:
1. _compose_briefing — correct sections rendered from data
2. _to_html — correct HTML structure
3. Weather, birthdays, follow-ups, calendar sections
"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest


def _make_pipeline():
    with patch("anthropic.Anthropic"):
        from app.pipelines.morning_briefing_pipeline import MorningBriefingPipeline
        return MorningBriefingPipeline()


TODAY = date(2026, 3, 8)


# ── _compose_briefing ─────────────────────────────────────────────────────────

class TestComposeBriefing:
    def setup_method(self):
        self.p = _make_pipeline()

    def test_header_contains_date(self):
        text = self.p._compose_briefing({}, TODAY)
        assert "March 08, 2026" in text

    def test_header_contains_owner_name(self, monkeypatch):
        monkeypatch.setattr("app.config.Config.OWNER_NAME", "Blake")
        text = self.p._compose_briefing({}, TODAY)
        assert "Blake" in text

    def test_no_calendar_shows_no_events(self):
        text = self.p._compose_briefing({}, TODAY)
        assert "No events today" in text

    def test_calendar_event_appears(self):
        sections = {
            "calendar": [
                {"start": "2026-03-08T09:00", "summary": "Board Meeting", "location": ""},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "Board Meeting" in text
        assert "CALENDAR" in text

    def test_calendar_event_with_location(self):
        sections = {
            "calendar": [
                {"start": "2026-03-08T14:00", "summary": "Lunch", "location": "Bistro 42"},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "Bistro 42" in text

    def test_birthday_section_appears(self):
        sections = {
            "birthdays": [
                {"name": "Kim Lakin", "days_away": 5, "birthday": "1970-05-01"},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "Kim Lakin" in text
        assert "UPCOMING BIRTHDAYS" in text

    def test_birthday_today_shows_today_label(self):
        sections = {
            "birthdays": [
                {"name": "Alice", "days_away": 0, "birthday": "1980-03-08"},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "TODAY!" in text

    def test_birthday_days_away_shown(self):
        sections = {
            "birthdays": [
                {"name": "Bob", "days_away": 7, "birthday": "1985-03-15"},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "7 day" in text

    def test_weather_section_appears(self):
        sections = {
            "weather": {
                "city": "Denver", "temp_f": "55", "desc": "Sunny",
                "feels_like_f": "52",
            }
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "Denver" in text
        assert "55" in text
        assert "Sunny" in text

    def test_weather_section_absent_when_empty(self):
        text = self.p._compose_briefing({"weather": {}}, TODAY)
        assert "WEATHER" not in text

    def test_followup_section_appears(self):
        sections = {
            "followups": [
                {"to_addr": "client@corp.com", "subject": "Proposal", "days_waiting": 5},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "client@corp.com" in text
        assert "5 days" in text

    def test_reminders_section_appears(self):
        sections = {
            "reminders": [
                {"title": "Call dentist", "is_overdue": False, "list": "Personal"},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "Call dentist" in text
        assert "DUE REMINDERS" in text

    def test_overdue_reminder_shows_warning(self):
        sections = {
            "reminders": [
                {"title": "File taxes", "is_overdue": True, "list": "Finance"},
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "OVERDUE" in text

    def test_family_email_section(self):
        sections = {
            "emails": [
                {
                    "from_addr": "kim@example.com",
                    "subject": "How are you?",
                    "summary": "Checking in.",
                    "is_family": 1,
                }
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "FAMILY EMAILS" in text
        assert "kim@example.com" in text

    def test_delivery_section_appears(self):
        sections = {
            "deliveries": [
                {
                    "carrier": "UPS",
                    "description": "Laptop Stand",
                    "status": "In Transit",
                    "expected_date": "2026-03-10",
                }
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "Laptop Stand" in text
        assert "DELIVERIES" in text

    def test_travel_section_appears(self):
        sections = {
            "travel": [
                {
                    "trip_name": "NYC Trip",
                    "destination": "New York",
                    "depart_date": "2026-03-20",
                    "booking_type": "flight",
                    "carrier": "Delta",
                    "confirmation_num": "ABC123",
                }
            ]
        }
        text = self.p._compose_briefing(sections, TODAY)
        assert "NYC Trip" in text or "New York" in text
        assert "TRAVEL" in text

    def test_sign_off_present(self):
        text = self.p._compose_briefing({}, TODAY)
        assert "AssistantAgent" in text


# ── _to_html ──────────────────────────────────────────────────────────────────

class TestToHtml:
    def setup_method(self):
        self.p = _make_pipeline()

    def test_output_starts_with_div(self):
        html = self.p._to_html("Hello")
        assert html.startswith("<div")

    def test_output_ends_with_div(self):
        html = self.p._to_html("Hello")
        assert html.strip().endswith("</div>")

    def test_briefing_header_renders_h1(self):
        html = self.p._to_html("☀️ MORNING BRIEFING — March 08, 2026")
        assert "<h1" in html
        assert "March 08, 2026" in html

    def test_section_header_renders_h3(self):
        for emoji in ("📅", "✅", "📧", "🎂", "🌤", "⏳", "📦", "✈️"):
            html = self.p._to_html(f"{emoji} SECTION TITLE")
            assert "<h3" in html, f"Expected <h3> for emoji {emoji}"

    def test_bullet_items_render_as_p(self):
        html = self.p._to_html("  • Some item here")
        assert "<p" in html
        assert "Some item here" in html

    def test_plain_lines_render_as_p(self):
        html = self.p._to_html("Good morning, Test Owner!")
        assert "<p" in html
        assert "Good morning" in html

    def test_empty_string_still_produces_div(self):
        html = self.p._to_html("")
        assert "<div" in html
        assert "</div>" in html
