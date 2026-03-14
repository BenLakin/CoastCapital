"""
Communications Pipeline — builds a personalized action plan from email,
calendar, and news using Claude.
"""
import logging
from datetime import datetime

import anthropic

from app.config import Config
from app.db import get_conn, log_daily_activity
from app.pipelines.email_pipeline import EmailPipeline
from app.pipelines.calendar_pipeline import CalendarPipeline
from app.pipelines.news_pipeline import NewsPipeline

logger = logging.getLogger(__name__)


class CommunicationsPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def build_plan(self, force_refresh: bool = False) -> dict:
        """Aggregate context, build AI action plan, persist action items."""

        # Gather context
        email_data = EmailPipeline().fetch_and_summarize(days=7, limit=20)
        cal_data = CalendarPipeline().get_upcoming_events(days_ahead=14)
        news_data = NewsPipeline().fetch_and_summarize(["world", "technology", "ai", "b2b"])

        context = self._build_context(email_data, cal_data, news_data)
        action_plan = self._generate_plan(context)
        action_items = self._parse_action_items(action_plan)

        self._save_action_items(action_items, force_refresh)
        log_daily_activity(
            "comms-plan",
            emails_processed=email_data.get("total", 0),
            family_emails_found=email_data.get("family_count", 0),
            action_items_created=len(action_items),
        )
        return {
            "plan_summary": action_plan,
            "action_items": action_items,
            "context_snapshot": {
                "emails_analyzed": email_data.get("total", 0),
                "family_emails": email_data.get("family_count", 0),
                "upcoming_events": cal_data.get("total", 0),
                "news_categories": list(news_data.get("summaries", {}).keys()),
            },
            "generated_at": datetime.now().isoformat(),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_context(self, email_data: dict, cal_data: dict, news_data: dict) -> str:
        sections = []

        # Emails
        emails = email_data.get("emails", [])
        if emails:
            email_lines = []
            for e in emails[:10]:
                flag = " [FAMILY]" if e.get("is_family") else ""
                email_lines.append(
                    f"  - From: {e.get('from_name', e.get('from_addr', ''))} | "
                    f"Subject: {e.get('subject', '')} | {e.get('summary', '')[:100]}{flag}"
                )
            sections.append("RECENT EMAILS:\n" + "\n".join(email_lines))

        # Calendar
        events = cal_data.get("events", [])
        if events:
            event_lines = [
                f"  - {e.get('start', '')[:10]}: {e.get('summary', '')}"
                + (" [BIRTHDAY]" if e.get("is_birthday") else "")
                + (" [HOLIDAY]" if e.get("is_holiday") else "")
                for e in events[:10]
            ]
            sections.append("UPCOMING CALENDAR EVENTS:\n" + "\n".join(event_lines))

        # News summaries
        news_summaries = news_data.get("summaries", {})
        if news_summaries:
            news_lines = [f"  [{cat.upper()}]: {summary[:200]}"
                          for cat, summary in news_summaries.items()]
            sections.append("NEWS HIGHLIGHTS:\n" + "\n".join(news_lines))

        # Family contacts emphasis
        family = Config.family_contacts()
        if family:
            family_str = ", ".join(f"{name} ({email})" for name, email in family.items())
            sections.append(f"KEY FAMILY CONTACTS TO PRIORITIZE: {family_str}")

        return "\n\n".join(sections)

    def _generate_plan(self, context: str) -> str:
        system_prompt = (
            f"You are the personal assistant for {Config.OWNER_NAME}. "
            "Your job is to review their recent emails, calendar, and news, then produce "
            "a clear, prioritized communication and action plan. "
            "ALWAYS prioritize communications with Kim Lakin and other family members. "
            "Be concise, specific, and actionable. Format each action item clearly."
        )

        user_prompt = (
            f"Based on the following context, create a prioritized communication plan "
            f"and recommended action items for today. For each email action, "
            f"provide a suggested email subject and draft body.\n\n{context}"
        )

        try:
            resp = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=1500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return resp.content[0].text
        except Exception as e:
            logger.error("Plan generation failed: %s", e)
            return "Could not generate plan — check Claude API key and connectivity."

    def _parse_action_items(self, plan_text: str) -> list[dict]:
        """Ask Claude to extract structured action items from the plan."""
        if not plan_text:
            return []

        extraction_prompt = (
            "Extract all action items from the following plan. "
            "Return a JSON array where each object has: "
            '{"title": str, "detail": str, "action_type": "email|call|task", '
            '"recipient": str, "email_subject": str, "email_body": str, "priority": 1-5}. '
            "Return ONLY the JSON array, no other text.\n\n" + plan_text
        )

        try:
            resp = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=1000,
                messages=[{"role": "user", "content": extraction_prompt}],
            )
            import json
            text = resp.content[0].text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.warning("Action item extraction failed: %s", e)
            return []

    def _save_action_items(self, items: list[dict], force_refresh: bool):
        if not items:
            return
        try:
            conn = get_conn()
            cur = conn.cursor()
            if force_refresh:
                cur.execute("DELETE FROM action_items WHERE status='pending'")
            for item in items:
                cur.execute(
                    "INSERT INTO action_items "
                    "(priority, title, detail, action_type, recipient, email_subject, email_body) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        item.get("priority", 5),
                        item.get("title", ""),
                        item.get("detail", ""),
                        item.get("action_type", "task"),
                        item.get("recipient", ""),
                        item.get("email_subject", ""),
                        item.get("email_body", ""),
                    ),
                )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Action items save failed: %s", e)
