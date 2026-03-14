"""
Reminders Pipeline — iCloud CalDAV VTODO (Reminders) reader and writer.
"""
import logging
from datetime import datetime, timedelta

import caldav
import pytz
from icalendar import Calendar, Todo, vText, vDatetime

from app.config import Config

logger = logging.getLogger(__name__)


class RemindersPipeline:

    def get_reminders(self, include_completed: bool = False) -> dict:
        """Fetch all iCloud Reminders (VTODO) items."""
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return {"error": "iCloud credentials not configured", "reminders": []}

        reminders = []
        try:
            client = caldav.DAVClient(
                url=Config.CALDAV_URL,
                username=Config.ICLOUD_EMAIL,
                password=Config.ICLOUD_APP_PASSWORD,
            )
            principal = client.principal()

            # iCloud Reminders live in todo-capable calendars
            for cal in principal.calendars():
                try:
                    todos = cal.todos(include_completed=include_completed)
                    for todo in todos:
                        parsed = self._parse_todo(todo, cal.name)
                        if parsed:
                            reminders.append(parsed)
                except Exception as e:
                    logger.debug("Cal %s has no todos: %s", cal.name, e)

        except Exception as e:
            logger.error("Reminders CalDAV error: %s", e)
            return {"error": str(e), "reminders": []}

        reminders.sort(key=lambda r: (r.get("due") or "9999", r.get("priority", 5)))

        return {
            "reminders": reminders,
            "total": len(reminders),
            "overdue": [r for r in reminders if r.get("is_overdue")],
            "due_today": [r for r in reminders if r.get("due_today")],
        }

    def add_reminder(self, title: str, notes: str = "", due_date: str = "",
                     priority: int = 5, list_name: str = "Reminders") -> dict:
        """
        Create a new iCloud Reminder (VTODO).

        priority: 1=High, 5=Medium, 9=Low (iCalendar standard).
        due_date: ISO date string (YYYY-MM-DD) or empty.
        """
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return {"error": "iCloud credentials not configured"}

        try:
            client = caldav.DAVClient(
                url=Config.CALDAV_URL,
                username=Config.ICLOUD_EMAIL,
                password=Config.ICLOUD_APP_PASSWORD,
            )
            principal = client.principal()
            calendars = principal.calendars()

            target_cal = None
            for cal in calendars:
                if cal.name.lower() == list_name.lower():
                    target_cal = cal
                    break
            if target_cal is None:
                target_cal = calendars[0]

            todo = Todo()
            todo.add("SUMMARY", title)
            todo.add("PRIORITY", priority)
            todo.add("STATUS", "NEEDS-ACTION")
            if notes:
                todo.add("DESCRIPTION", notes)
            if due_date:
                try:
                    dt = datetime.strptime(due_date, "%Y-%m-%d")
                    todo.add("DUE", dt)
                except ValueError:
                    pass

            cal_obj = Calendar()
            cal_obj.add("PRODID", "-//CoastCapital Assistant//EN")
            cal_obj.add("VERSION", "2.0")
            cal_obj.add_component(todo)

            target_cal.add_todo(cal_obj.to_ical().decode())
            logger.info("Reminder created: %s", title)
            return {"success": True, "title": title, "list": target_cal.name}

        except Exception as e:
            logger.error("Add reminder error: %s", e)
            return {"error": str(e)}

    def complete_reminder(self, reminder_url: str) -> dict:
        """Mark a reminder as completed by its CalDAV URL."""
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return {"error": "iCloud credentials not configured"}
        try:
            client = caldav.DAVClient(
                url=Config.CALDAV_URL,
                username=Config.ICLOUD_EMAIL,
                password=Config.ICLOUD_APP_PASSWORD,
            )
            todo = client.object_by_url(reminder_url)
            todo.complete()
            return {"success": True}
        except Exception as e:
            logger.error("Complete reminder error: %s", e)
            return {"error": str(e)}

    # ── Private ───────────────────────────────────────────────────────────────

    def _parse_todo(self, caldav_todo, cal_name: str) -> dict | None:
        try:
            cal = Calendar.from_ical(caldav_todo.data)
            now = datetime.now(pytz.utc)
            today_str = datetime.now().date().isoformat()

            for component in cal.walk():
                if component.name != "VTODO":
                    continue

                summary = str(component.get("SUMMARY", ""))
                status = str(component.get("STATUS", "NEEDS-ACTION"))
                priority = int(component.get("PRIORITY", 5))
                notes = str(component.get("DESCRIPTION", ""))

                due = component.get("DUE")
                due_str = None
                is_overdue = False
                due_today = False

                if due:
                    due_dt = due.dt
                    if hasattr(due_dt, "date"):
                        due_str = due_dt.date().isoformat()
                    else:
                        due_str = due_dt.isoformat()
                    is_overdue = due_str < today_str and status != "COMPLETED"
                    due_today = due_str == today_str

                return {
                    "title": summary,
                    "notes": notes[:200],
                    "status": status,
                    "priority": priority,
                    "due": due_str,
                    "is_overdue": is_overdue,
                    "due_today": due_today,
                    "list": cal_name,
                    "url": str(caldav_todo.url),
                }
        except Exception as e:
            logger.warning("VTODO parse error: %s", e)
        return None
