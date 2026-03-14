"""
Unit tests for AssistantAgent._execute_tool dispatch.

Verifies that every named tool routes to the correct pipeline method
with the correct arguments. Uses fully mocked pipelines — no real
API, iCloud, or DB connections.
"""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def agent():
    """
    AssistantAgent with all pipelines replaced by MagicMock objects.
    Bypasses __init__ to avoid creating real Anthropic / DB connections.
    """
    with patch("anthropic.Anthropic"):
        from app.agents.assistant_agent import AssistantAgent
        a = AssistantAgent.__new__(AssistantAgent)

    a.client = MagicMock()
    a.email_pipeline = MagicMock()
    a.news_pipeline = MagicMock()
    a.calendar_pipeline = MagicMock()
    a.reminders_pipeline = MagicMock()
    a.deliveries_pipeline = MagicMock()
    a.briefing_pipeline = MagicMock()
    a.followup_pipeline = MagicMock()
    a.travel_pipeline = MagicMock()
    a.birthday_pipeline = MagicMock()
    a.comms_pipeline = MagicMock()
    return a


# ── Original 10 tools ─────────────────────────────────────────────────────────

class TestOriginalToolDispatch:
    def test_get_recent_emails_calls_fetch_and_summarize(self, agent):
        agent.email_pipeline.fetch_and_summarize.return_value = {"emails": []}
        agent._execute_tool("get_recent_emails", {"days": 7, "limit": 20})
        agent.email_pipeline.fetch_and_summarize.assert_called_once_with(days=7, limit=20)

    def test_get_recent_emails_default_args(self, agent):
        agent.email_pipeline.fetch_and_summarize.return_value = {}
        agent._execute_tool("get_recent_emails", {})
        agent.email_pipeline.fetch_and_summarize.assert_called_once_with(days=7, limit=20)

    def test_get_family_emails_returns_emails_and_total(self, agent):
        agent.email_pipeline.get_family_emails.return_value = [{"from": "kim"}]
        result = agent._execute_tool("get_family_emails", {"days": 14})
        assert "emails" in result
        assert "total" in result
        assert result["total"] == 1

    def test_send_email_calls_pipeline(self, agent):
        result = agent._execute_tool("send_email", {
            "to": "kim@example.com",
            "subject": "Hello",
            "body": "Hope you are well.",
        })
        agent.email_pipeline.send_email.assert_called_once_with(
            to="kim@example.com",
            subject="Hello",
            body="Hope you are well.",
            cc="",
        )
        assert result["success"] is True
        assert result["sent_to"] == "kim@example.com"

    def test_send_email_with_cc(self, agent):
        agent._execute_tool("send_email", {
            "to": "a@example.com",
            "subject": "Re: Project",
            "body": "See attached.",
            "cc": "b@example.com",
        })
        agent.email_pipeline.send_email.assert_called_once_with(
            to="a@example.com", subject="Re: Project",
            body="See attached.", cc="b@example.com",
        )

    def test_get_calendar_events_default_days(self, agent):
        agent.calendar_pipeline.get_upcoming_events.return_value = {}
        agent._execute_tool("get_calendar_events", {})
        agent.calendar_pipeline.get_upcoming_events.assert_called_once_with(days_ahead=14)

    def test_get_calendar_events_custom_days(self, agent):
        agent._execute_tool("get_calendar_events", {"days_ahead": 30})
        agent.calendar_pipeline.get_upcoming_events.assert_called_once_with(days_ahead=30)

    def test_get_reminders_default(self, agent):
        agent.reminders_pipeline.get_reminders.return_value = {}
        agent._execute_tool("get_reminders", {})
        agent.reminders_pipeline.get_reminders.assert_called_once_with(include_completed=False)

    def test_get_reminders_include_completed(self, agent):
        agent._execute_tool("get_reminders", {"include_completed": True})
        agent.reminders_pipeline.get_reminders.assert_called_once_with(include_completed=True)

    def test_add_reminder_required_title(self, agent):
        agent.reminders_pipeline.add_reminder.return_value = {"success": True}
        agent._execute_tool("add_reminder", {"title": "Call Kim"})
        agent.reminders_pipeline.add_reminder.assert_called_once()
        call_kwargs = agent.reminders_pipeline.add_reminder.call_args[1]
        assert call_kwargs["title"] == "Call Kim"

    def test_get_news_default_categories(self, agent):
        agent.news_pipeline.fetch_and_summarize.return_value = {}
        agent._execute_tool("get_news", {})
        agent.news_pipeline.fetch_and_summarize.assert_called_once_with(
            categories=["technology", "ai"]
        )

    def test_get_news_custom_categories(self, agent):
        agent._execute_tool("get_news", {"categories": ["world", "b2b"]})
        agent.news_pipeline.fetch_and_summarize.assert_called_once_with(
            categories=["world", "b2b"]
        )

    def test_get_deliveries(self, agent):
        agent.deliveries_pipeline.fetch_all.return_value = {}
        agent._execute_tool("get_deliveries", {})
        agent.deliveries_pipeline.fetch_all.assert_called_once()

    def test_build_communications_plan_default(self, agent):
        agent.comms_pipeline.build_plan.return_value = {}
        agent._execute_tool("build_communications_plan", {})
        agent.comms_pipeline.build_plan.assert_called_once_with(force_refresh=False)

    def test_build_communications_plan_force_refresh(self, agent):
        agent._execute_tool("build_communications_plan", {"force_refresh": True})
        agent.comms_pipeline.build_plan.assert_called_once_with(force_refresh=True)

    def test_get_family_contacts_returns_contacts(self, agent, monkeypatch):
        monkeypatch.setattr("app.config.Config.KIM_LAKIN_EMAIL", "kim@example.com")
        monkeypatch.setattr("app.config.Config.FAMILY_EMAILS_RAW", "sibling@example.com")
        result = agent._execute_tool("get_family_contacts", {})
        assert "contacts" in result
        assert "kim_lakin_email" in result
        assert result["kim_lakin_email"] == "kim@example.com"


# ── 7 new tools added in the latest sprint ───────────────────────────────────

class TestNewToolDispatch:
    def test_get_morning_briefing_default(self, agent):
        agent.briefing_pipeline.generate.return_value = {"briefing": "Good morning!"}
        result = agent._execute_tool("get_morning_briefing", {})
        agent.briefing_pipeline.generate.assert_called_once_with(send_email=False)

    def test_get_morning_briefing_send_email_true(self, agent):
        agent.briefing_pipeline.generate.return_value = {}
        agent._execute_tool("get_morning_briefing", {"send_email": True})
        agent.briefing_pipeline.generate.assert_called_once_with(send_email=True)

    def test_check_followups_default_wait_days(self, agent):
        agent.followup_pipeline.scan.return_value = {"followups": []}
        agent._execute_tool("check_followups", {})
        agent.followup_pipeline.scan.assert_called_once_with(wait_days=3)

    def test_check_followups_custom_wait_days(self, agent):
        agent._execute_tool("check_followups", {"wait_days": 7})
        agent.followup_pipeline.scan.assert_called_once_with(wait_days=7)

    def test_scan_travel_default_days(self, agent):
        agent.travel_pipeline.scan.return_value = {}
        agent._execute_tool("scan_travel", {})
        agent.travel_pipeline.scan.assert_called_once_with(days=60)

    def test_scan_travel_custom_days(self, agent):
        agent._execute_tool("scan_travel", {"days": 90})
        agent.travel_pipeline.scan.assert_called_once_with(days=90)

    def test_get_upcoming_birthdays(self, agent):
        agent.birthday_pipeline.get_upcoming_birthdays.return_value = {"total": 0}
        result = agent._execute_tool("get_upcoming_birthdays", {})
        agent.birthday_pipeline.get_upcoming_birthdays.assert_called_once()

    def test_get_relationship_profile(self, agent):
        agent.birthday_pipeline.get_full_profile.return_value = {"person": {}}
        agent._execute_tool("get_relationship_profile", {"relationship_id": 42})
        agent.birthday_pipeline.get_full_profile.assert_called_once_with(42)

    def test_log_relationship_preference_all_args(self, agent):
        agent.birthday_pipeline.log_preference.return_value = {"success": True}
        agent._execute_tool("log_relationship_preference", {
            "relationship_id": 5,
            "category": "food & restaurants",
            "preference": "Italian cuisine",
        })
        agent.birthday_pipeline.log_preference.assert_called_once_with(
            relationship_id=5,
            category="food & restaurants",
            preference="Italian cuisine",
            source="agent",
        )

    def test_log_relationship_preference_default_source(self, agent):
        """When no 'source' key is provided, it defaults to 'agent'."""
        agent.birthday_pipeline.log_preference.return_value = {}
        agent._execute_tool("log_relationship_preference", {
            "relationship_id": 1,
            "category": "hobbies & activities",
            "preference": "Rock climbing",
        })
        kwargs = agent.birthday_pipeline.log_preference.call_args[1]
        assert kwargs["source"] == "agent"

    def test_get_gift_suggestions_default_budget(self, agent):
        agent.birthday_pipeline.get_gift_suggestions.return_value = {}
        agent._execute_tool("get_gift_suggestions", {"relationship_id": 3})
        agent.birthday_pipeline.get_gift_suggestions.assert_called_once_with(
            relationship_id=3, budget="any"
        )

    def test_get_gift_suggestions_custom_budget(self, agent):
        agent._execute_tool("get_gift_suggestions", {
            "relationship_id": 3, "budget": "under $100",
        })
        agent.birthday_pipeline.get_gift_suggestions.assert_called_once_with(
            relationship_id=3, budget="under $100"
        )


# ── Error handling ────────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_unknown_tool_returns_error_dict(self, agent):
        result = agent._execute_tool("nonexistent_tool_xyz", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_unknown_tool_includes_tool_name(self, agent):
        result = agent._execute_tool("mystery_tool", {})
        assert "mystery_tool" in result["error"]

    def test_pipeline_exception_returns_error_not_raise(self, agent):
        """Exceptions from pipeline calls must be caught and returned as error dicts."""
        agent.email_pipeline.fetch_and_summarize.side_effect = Exception("IMAP timeout")
        result = agent._execute_tool("get_recent_emails", {})
        assert "error" in result
        assert "IMAP timeout" in result["error"]

    def test_briefing_pipeline_exception_caught(self, agent):
        agent.briefing_pipeline.generate.side_effect = RuntimeError("Weather API down")
        result = agent._execute_tool("get_morning_briefing", {})
        assert "error" in result

    def test_birthday_pipeline_exception_caught(self, agent):
        agent.birthday_pipeline.get_upcoming_birthdays.side_effect = Exception("DB error")
        result = agent._execute_tool("get_upcoming_birthdays", {})
        assert "error" in result
