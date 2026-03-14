"""
AssistantAgent — Claude-powered personal assistant with tool use.

Primary mission: make the owner's life easier with a strong focus on
communications with Kim Lakin and family members.
"""
import json
import logging
from datetime import datetime

import anthropic

from app.config import Config
from app.pipelines.email_pipeline import EmailPipeline
from app.pipelines.news_pipeline import NewsPipeline
from app.pipelines.calendar_pipeline import CalendarPipeline
from app.pipelines.reminders_pipeline import RemindersPipeline
from app.pipelines.deliveries_pipeline import DeliveriesPipeline
from app.pipelines.communications_pipeline import CommunicationsPipeline
from app.pipelines.morning_briefing_pipeline import MorningBriefingPipeline
from app.pipelines.followup_pipeline import FollowupPipeline
from app.pipelines.travel_pipeline import TravelPipeline
from app.pipelines.birthday_pipeline import BirthdayPipeline

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are AssistantAgent, the personal AI assistant for {owner_name}.

Your core mission is to make {owner_name}'s life easier. You are organized, proactive,
warm, and focused on what matters most.

PRIMARY RESPONSIBILITIES:
1. Email management — monitor, summarize, and draft responses. ALWAYS prioritize
   messages from Kim Lakin and other family members. Flag anything that needs a reply.
2. Calendar awareness — keep track of upcoming events, birthdays, holidays, and
   remind {owner_name} of important dates in advance.
3. Communications planning — proactively suggest who to reach out to, what to say,
   and when to say it. Keep family relationships strong.
4. News & intelligence — surface relevant technology, AI, and B2B news.
5. Deliveries & logistics — track packages and upcoming events.
6. Reminders — create, update, and surface iCloud Reminders.
7. Archiving — maintain a clean inbox through smart email organization.

STYLE:
- Be concise and direct. Lead with the most important information.
- When family is involved (especially Kim Lakin), be warm and relationship-focused.
- Always suggest specific next actions when possible.
- If you can draft an email for the owner, do so proactively.

Today's date: {today}
"""


class AssistantAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.CLAUDE_MODEL
        self.email_pipeline = EmailPipeline()
        self.news_pipeline = NewsPipeline()
        self.calendar_pipeline = CalendarPipeline()
        self.reminders_pipeline = RemindersPipeline()
        self.deliveries_pipeline = DeliveriesPipeline()
        self.briefing_pipeline = MorningBriefingPipeline()
        self.followup_pipeline = FollowupPipeline()
        self.travel_pipeline = TravelPipeline()
        self.birthday_pipeline = BirthdayPipeline()
        self.comms_pipeline = CommunicationsPipeline()

    # ── Public ────────────────────────────────────────────────────────────────

    def chat(self, message: str, history: list[dict] = None) -> str:
        """
        Send a message to AssistantAgent and get a response.
        Supports multi-turn conversations via `history`.
        """
        if history is None:
            history = []

        messages = list(history) + [{"role": "user", "content": message}]
        system = SYSTEM_PROMPT.format(
            owner_name=Config.OWNER_NAME,
            today=datetime.now().strftime("%A, %B %d, %Y"),
        )

        # Agentic loop — keep going until no more tool calls
        while True:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system,
                tools=self._get_tools(),
                messages=messages,
            )

            if resp.stop_reason == "end_turn":
                return self._extract_text(resp)

            if resp.stop_reason == "tool_use":
                # Execute all requested tool calls
                tool_results = []
                for block in resp.content:
                    if block.type == "tool_use":
                        result = self._execute_tool(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, default=str),
                        })

                # Add assistant turn + tool results to message history
                messages.append({"role": "assistant", "content": resp.content})
                messages.append({"role": "user", "content": tool_results})
            else:
                # Unexpected stop reason — return whatever text we have
                return self._extract_text(resp)

    # ── Tool Definitions ──────────────────────────────────────────────────────

    def _get_tools(self) -> list[dict]:
        return [
            {
                "name": "get_recent_emails",
                "description": (
                    "Fetch and summarize recent emails from iCloud INBOX. "
                    "Returns list of emails with AI summaries. Family emails are flagged."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "description": "Days to look back", "default": 7},
                        "limit": {"type": "integer", "description": "Max emails to fetch", "default": 20},
                    },
                },
            },
            {
                "name": "get_family_emails",
                "description": "Get recent emails specifically from family contacts (Kim Lakin, etc.).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 30},
                    },
                },
            },
            {
                "name": "send_email",
                "description": "Send an email on behalf of the owner via iCloud SMTP.",
                "input_schema": {
                    "type": "object",
                    "required": ["to", "subject", "body"],
                    "properties": {
                        "to": {"type": "string", "description": "Recipient email address"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                        "cc": {"type": "string", "description": "CC addresses, comma-separated"},
                    },
                },
            },
            {
                "name": "get_calendar_events",
                "description": "Get upcoming iCloud calendar events.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days_ahead": {"type": "integer", "default": 14},
                    },
                },
            },
            {
                "name": "get_reminders",
                "description": "Get iCloud Reminders (VTODO items). Returns pending and overdue items.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "include_completed": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "add_reminder",
                "description": "Create a new iCloud Reminder.",
                "input_schema": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {
                        "title": {"type": "string"},
                        "notes": {"type": "string"},
                        "due_date": {"type": "string", "description": "YYYY-MM-DD format"},
                        "priority": {"type": "integer", "description": "1=High, 5=Medium, 9=Low"},
                        "list_name": {"type": "string", "default": "Reminders"},
                    },
                },
            },
            {
                "name": "get_news",
                "description": "Get summarized news for specified categories.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "categories": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["world", "technology", "ai", "b2b"]},
                            "default": ["technology", "ai"],
                        },
                    },
                },
            },
            {
                "name": "get_deliveries",
                "description": "Get package delivery status and upcoming events (birthdays, holidays).",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "build_communications_plan",
                "description": (
                    "Build a full personalized communications and action plan based on "
                    "current email, calendar, and news context."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "force_refresh": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "get_family_contacts",
                "description": "Get the list of family contacts configured for the owner.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_morning_briefing",
                "description": "Generate today's morning briefing covering calendar, reminders, emails, travel, birthdays, and news. Optionally email it.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "send_email": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "check_followups",
                "description": "Scan sent emails for messages that have not received a reply after 3+ days.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "wait_days": {"type": "integer", "default": 3},
                    },
                },
            },
            {
                "name": "scan_travel",
                "description": "Scan email for flight, hotel, car, or cruise booking confirmations and extract itinerary details.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "days": {"type": "integer", "default": 60, "description": "Days of email history to scan"},
                    },
                },
            },
            {
                "name": "get_upcoming_birthdays",
                "description": "Get upcoming birthdays from the relationships table with preference profiles and gift suggestions.",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "get_relationship_profile",
                "description": "Get full relationship profile for a person: preferences, gifts, and interaction history.",
                "input_schema": {
                    "type": "object",
                    "required": ["relationship_id"],
                    "properties": {
                        "relationship_id": {"type": "integer"},
                    },
                },
            },
            {
                "name": "log_relationship_preference",
                "description": "Log a new preference or taste for a person in the relationships database.",
                "input_schema": {
                    "type": "object",
                    "required": ["relationship_id", "category", "preference"],
                    "properties": {
                        "relationship_id": {"type": "integer"},
                        "category": {"type": "string", "description": "e.g. food, hobbies, books, fashion"},
                        "preference": {"type": "string"},
                    },
                },
            },
            {
                "name": "get_gift_suggestions",
                "description": "Get Claude-generated gift suggestions for a person based on their logged preferences and past gifts.",
                "input_schema": {
                    "type": "object",
                    "required": ["relationship_id"],
                    "properties": {
                        "relationship_id": {"type": "integer"},
                        "budget": {"type": "string", "default": "any"},
                    },
                },
            },
        ]

    # ── Tool Execution ────────────────────────────────────────────────────────

    def _execute_tool(self, name: str, inputs: dict) -> dict:
        logger.info("Tool call: %s(%s)", name, inputs)
        try:
            if name == "get_recent_emails":
                return self.email_pipeline.fetch_and_summarize(
                    days=inputs.get("days", 7),
                    limit=inputs.get("limit", 20),
                )
            elif name == "get_family_emails":
                emails = self.email_pipeline.get_family_emails(days=inputs.get("days", 30))
                return {"emails": emails, "total": len(emails)}
            elif name == "send_email":
                self.email_pipeline.send_email(
                    to=inputs["to"],
                    subject=inputs["subject"],
                    body=inputs["body"],
                    cc=inputs.get("cc", ""),
                )
                return {"success": True, "sent_to": inputs["to"]}
            elif name == "get_calendar_events":
                return self.calendar_pipeline.get_upcoming_events(
                    days_ahead=inputs.get("days_ahead", 14)
                )
            elif name == "get_reminders":
                return self.reminders_pipeline.get_reminders(
                    include_completed=inputs.get("include_completed", False)
                )
            elif name == "add_reminder":
                return self.reminders_pipeline.add_reminder(
                    title=inputs["title"],
                    notes=inputs.get("notes", ""),
                    due_date=inputs.get("due_date", ""),
                    priority=inputs.get("priority", 5),
                    list_name=inputs.get("list_name", "Reminders"),
                )
            elif name == "get_news":
                return self.news_pipeline.fetch_and_summarize(
                    categories=inputs.get("categories", ["technology", "ai"])
                )
            elif name == "get_deliveries":
                return self.deliveries_pipeline.fetch_all()
            elif name == "build_communications_plan":
                return self.comms_pipeline.build_plan(
                    force_refresh=inputs.get("force_refresh", False)
                )
            elif name == "get_family_contacts":
                return {
                    "contacts": Config.family_contacts(),
                    "kim_lakin_email": Config.KIM_LAKIN_EMAIL,
                }
            elif name == "get_morning_briefing":
                return self.briefing_pipeline.generate(
                    send_email=inputs.get("send_email", False)
                )
            elif name == "check_followups":
                return self.followup_pipeline.scan(
                    wait_days=inputs.get("wait_days", 3)
                )
            elif name == "scan_travel":
                return self.travel_pipeline.scan(
                    days=inputs.get("days", 60)
                )
            elif name == "get_upcoming_birthdays":
                return self.birthday_pipeline.get_upcoming_birthdays()
            elif name == "get_relationship_profile":
                return self.birthday_pipeline.get_full_profile(
                    inputs["relationship_id"]
                )
            elif name == "log_relationship_preference":
                return self.birthday_pipeline.log_preference(
                    relationship_id=inputs["relationship_id"],
                    category=inputs["category"],
                    preference=inputs["preference"],
                    source=inputs.get("source", "agent"),
                )
            elif name == "get_gift_suggestions":
                return self.birthday_pipeline.get_gift_suggestions(
                    relationship_id=inputs["relationship_id"],
                    budget=inputs.get("budget", "any"),
                )
            else:
                return {"error": f"Unknown tool: {name}"}
        except Exception as e:
            logger.error("Tool %s error: %s", name, e)
            return {"error": str(e)}

    def _extract_text(self, resp) -> str:
        for block in resp.content:
            if hasattr(block, "text"):
                return block.text
        return ""
