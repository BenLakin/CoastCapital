"""
Morning Briefing Pipeline — compiles a daily digest from all data sources
and optionally emails it to the owner.

Sources: calendar, reminders, email (family priority), action items,
         deliveries, upcoming travel, birthdays, weather.
"""
import logging
from datetime import datetime, date, timedelta

import anthropic
import requests

from app.config import Config
from app.db import get_conn, log_daily_activity
from app.pipelines.email_pipeline import EmailPipeline

logger = logging.getLogger(__name__)

WEATHER_URL = "https://wttr.in/{city}?format=j1"


class MorningBriefingPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def generate(self, send_email: bool = False, city: str = "") -> dict:
        """Build the morning briefing. Optionally email it to the owner."""
        today = date.today()

        sections = {}
        sections["calendar"]    = self._get_todays_events()
        sections["reminders"]   = self._get_due_reminders()
        sections["emails"]      = self._get_priority_emails()
        sections["action_items"] = self._get_top_actions()
        sections["deliveries"]  = self._get_active_deliveries()
        sections["travel"]      = self._get_upcoming_travel()
        sections["birthdays"]   = self._get_upcoming_birthdays()
        sections["followups"]   = self._get_stale_followups()
        sections["weather"]     = self._get_weather(city or Config.OWNER_CITY)

        briefing_text = self._compose_briefing(sections, today)
        html_text = self._to_html(briefing_text)

        self._cache_briefing(today, briefing_text)

        if send_email and Config.ICLOUD_EMAIL:
            try:
                EmailPipeline().send_email(
                    to=Config.ICLOUD_EMAIL,
                    subject=f"☀️ Morning Briefing — {today.strftime('%A, %B %d')}",
                    body=briefing_text,
                )
                self._mark_emailed(today)
            except Exception as e:
                logger.error("Briefing email failed: %s", e)

        log_daily_activity(
            "morning-briefing",
            briefing_emailed=1 if send_email else 0,
            reminders_checked=len(sections.get("reminders", [])),
            followups_detected=len(sections.get("followups", [])),
            deliveries_found=len(sections.get("deliveries", [])),
        )
        return {
            "date": today.isoformat(),
            "briefing": briefing_text,
            "html": html_text,
            "sections": sections,
            "emailed": send_email,
        }

    # ── Section Fetchers ──────────────────────────────────────────────────────

    def _get_todays_events(self) -> list[dict]:
        today_str = date.today().isoformat()
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            # Pull from calendar cache if available; otherwise return empty
            # (CalendarPipeline is called separately by n8n)
            cur.execute(
                "SELECT summary, start, location, is_birthday, is_holiday "
                "FROM (SELECT * FROM morning_briefings LIMIT 0) t "  # placeholder
            )
            cur.close()
            conn.close()
        except Exception:
            pass

        # Live fetch from CalDAV
        try:
            from app.pipelines.calendar_pipeline import CalendarPipeline
            data = CalendarPipeline().get_upcoming_events(days_ahead=1)
            return data.get("events", [])
        except Exception as e:
            logger.warning("Calendar fetch for briefing: %s", e)
            return []

    def _get_due_reminders(self) -> list[dict]:
        try:
            from app.pipelines.reminders_pipeline import RemindersPipeline
            data = RemindersPipeline().get_reminders()
            overdue = data.get("overdue", [])
            due_today = data.get("due_today", [])
            return overdue + due_today
        except Exception as e:
            logger.warning("Reminders fetch for briefing: %s", e)
            return []

    def _get_priority_emails(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT from_addr, subject, summary, is_family "
                "FROM email_cache "
                "WHERE fetched_at >= NOW() - INTERVAL 24 HOUR "
                "ORDER BY is_family DESC, fetched_at DESC LIMIT 10"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Email cache fetch for briefing: %s", e)
            return []

    def _get_top_actions(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT title, detail, action_type, recipient "
                "FROM action_items WHERE status='pending' "
                "ORDER BY priority, created_at DESC LIMIT 5"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Action items fetch for briefing: %s", e)
            return []

    def _get_active_deliveries(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT carrier, description, status, expected_date "
                "FROM deliveries "
                "WHERE status NOT IN ('Delivered') "
                "ORDER BY expected_date ASC LIMIT 5"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Deliveries fetch for briefing: %s", e)
            return []

    def _get_upcoming_travel(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT trip_name, destination, depart_date, return_date, "
                "carrier, booking_type, confirmation_num "
                "FROM travel_itineraries "
                "WHERE depart_date >= CURDATE() AND status='upcoming' "
                "ORDER BY depart_date ASC LIMIT 5"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Travel fetch for briefing: %s", e)
            return []

    def _get_upcoming_birthdays(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            # Find birthdays in the next 30 days (month/day only)
            cur.execute(
                """SELECT name, birthday, email,
                          DATEDIFF(
                            DATE(CONCAT(YEAR(CURDATE()), '-',
                                 LPAD(MONTH(birthday),2,'0'), '-',
                                 LPAD(DAY(birthday),2,'0'))),
                            CURDATE()
                          ) AS days_away
                   FROM relationships
                   WHERE birthday IS NOT NULL
                     AND DATEDIFF(
                           DATE(CONCAT(YEAR(CURDATE()), '-',
                                LPAD(MONTH(birthday),2,'0'), '-',
                                LPAD(DAY(birthday),2,'0'))),
                           CURDATE()
                         ) BETWEEN 0 AND 30
                   ORDER BY days_away ASC"""
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Birthday fetch for briefing: %s", e)
            return []

    def _get_stale_followups(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT to_addr, subject, days_waiting "
                "FROM followup_tracker "
                "WHERE status='waiting' AND days_waiting >= 3 "
                "ORDER BY days_waiting DESC LIMIT 5"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Followup fetch for briefing: %s", e)
            return []

    def _get_weather(self, city: str) -> dict:
        if not city:
            return {}
        try:
            resp = requests.get(
                WEATHER_URL.format(city=city.replace(" ", "+")),
                timeout=5,
            )
            data = resp.json()
            current = data["current_condition"][0]
            return {
                "temp_f": current.get("temp_F", "?"),
                "desc": current["weatherDesc"][0]["value"],
                "feels_like_f": current.get("FeelsLikeF", "?"),
                "city": city,
            }
        except Exception as e:
            logger.warning("Weather fetch failed: %s", e)
            return {}

    # ── Compose ───────────────────────────────────────────────────────────────

    def _compose_briefing(self, sections: dict, today: date) -> str:
        parts = [
            f"☀️ MORNING BRIEFING — {today.strftime('%A, %B %d, %Y')}",
            f"Good morning, {Config.OWNER_NAME}!\n",
        ]

        # Weather
        w = sections.get("weather", {})
        if w:
            parts.append(f"🌤 WEATHER — {w.get('city', '')}: {w.get('temp_f')}°F, {w.get('desc')} (feels {w.get('feels_like_f')}°F)")

        # Birthdays (critical — always first after weather)
        birthdays = sections.get("birthdays", [])
        if birthdays:
            parts.append("\n🎂 UPCOMING BIRTHDAYS")
            for b in birthdays:
                days = b.get("days_away", "?")
                label = "TODAY!" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
                parts.append(f"  • {b['name']} — {label} ({b.get('birthday', '?')})")

        # Today's calendar
        events = sections.get("calendar", [])
        if events:
            parts.append("\n📅 TODAY'S CALENDAR")
            for e in events:
                start = str(e.get("start", ""))[:16].replace("T", " ")
                parts.append(f"  • {start} — {e.get('summary', '')}" +
                              (f" @ {e['location']}" if e.get("location") else ""))
        else:
            parts.append("\n📅 CALENDAR — No events today")

        # Due reminders
        reminders = sections.get("reminders", [])
        if reminders:
            parts.append("\n✅ DUE REMINDERS")
            for r in reminders[:5]:
                tag = " ⚠️ OVERDUE" if r.get("is_overdue") else ""
                parts.append(f"  • {r.get('title', '')}{tag} [{r.get('list', '')}]")

        # Priority emails
        emails = sections.get("emails", [])
        family = [e for e in emails if e.get("is_family")]
        other = [e for e in emails if not e.get("is_family")]
        if family:
            parts.append("\n👨‍👩‍👧 FAMILY EMAILS")
            for e in family:
                parts.append(f"  • From {e['from_addr']}: {e['subject']}")
                if e.get("summary"):
                    parts.append(f"    → {e['summary'][:120]}")
        if other:
            parts.append("\n📧 OTHER EMAILS")
            for e in other[:4]:
                parts.append(f"  • From {e['from_addr']}: {e['subject']}")

        # Top action items
        actions = sections.get("action_items", [])
        if actions:
            parts.append("\n🗺️ TOP ACTION ITEMS")
            for i, a in enumerate(actions, 1):
                parts.append(f"  {i}. {a.get('title', '')}" +
                              (f" → {a['recipient']}" if a.get("recipient") else ""))

        # Follow-ups awaiting reply
        followups = sections.get("followups", [])
        if followups:
            parts.append("\n⏳ WAITING FOR REPLIES")
            for f in followups:
                parts.append(f"  • {f['to_addr']}: \"{f['subject']}\" — {f['days_waiting']} days")

        # Deliveries
        deliveries = sections.get("deliveries", [])
        if deliveries:
            parts.append("\n📦 ACTIVE DELIVERIES")
            for d in deliveries:
                eta = f" (ETA {d['expected_date']})" if d.get("expected_date") else ""
                parts.append(f"  • {d['carrier']}: {d['description'][:60]} — {d['status']}{eta}")

        # Upcoming travel
        travel = sections.get("travel", [])
        if travel:
            parts.append("\n✈️ UPCOMING TRAVEL")
            for t in travel:
                parts.append(
                    f"  • {t.get('trip_name') or t.get('destination', 'Trip')} — "
                    f"departs {t.get('depart_date', '?')} "
                    f"({t.get('booking_type', '?')} · {t.get('carrier', '')} "
                    f"#{t.get('confirmation_num', '?')})"
                )

        parts.append("\n— AssistantAgent")
        return "\n".join(parts)

    def _to_html(self, text: str) -> str:
        """Convert plain text briefing to simple HTML."""
        lines = text.split("\n")
        html_parts = ["<div style='font-family:Inter,sans-serif;max-width:640px;margin:0 auto;padding:20px'>"]
        for line in lines:
            if line.startswith("☀️"):
                html_parts.append(f"<h1 style='color:#1e293b;font-size:20px'>{line}</h1>")
            elif line.startswith(("📅","✅","👨","📧","🗺️","⏳","📦","✈️","🎂","🌤")):
                html_parts.append(f"<h3 style='color:#334155;margin-top:20px;font-size:14px;text-transform:uppercase;letter-spacing:0.05em'>{line}</h3>")
            elif line.startswith("  •") or line.startswith("  →") or line.startswith("  "):
                html_parts.append(f"<p style='margin:4px 0 4px 16px;font-size:14px;color:#475569'>{line.strip()}</p>")
            elif line:
                html_parts.append(f"<p style='color:#64748b;font-size:14px'>{line}</p>")
        html_parts.append("</div>")
        return "\n".join(html_parts)

    def _cache_briefing(self, today: date, content: str):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO morning_briefings (briefing_date, content) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE content=%s",
                (today.isoformat(), content, content),
            )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Briefing cache failed: %s", e)

    def _mark_emailed(self, today: date):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE morning_briefings SET emailed=1 WHERE briefing_date=%s",
                (today.isoformat(),),
            )
            cur.close()
            conn.close()
        except Exception:
            pass
