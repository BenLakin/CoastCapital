"""
Calendar Pipeline — iCloud CalDAV events (VEVENT components).
"""
import logging
from datetime import datetime, timedelta, date

import caldav
import pytz
from icalendar import Calendar

from app.config import Config

logger = logging.getLogger(__name__)

HOLIDAY_KEYWORDS = ["holiday", "christmas", "thanksgiving", "easter", "hanukkah",
                    "new year", "independence", "memorial", "labor day", "halloween"]
BIRTHDAY_KEYWORDS = ["birthday", "bday", "born", "anniversary"]


class CalendarPipeline:

    def get_upcoming_events(self, days_ahead: int = 14) -> dict:
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return {"error": "iCloud credentials not configured", "events": []}

        now = datetime.now(pytz.utc)
        end = now + timedelta(days=days_ahead)
        events = []

        try:
            client = caldav.DAVClient(
                url=Config.CALDAV_URL,
                username=Config.ICLOUD_EMAIL,
                password=Config.ICLOUD_APP_PASSWORD,
            )
            principal = client.principal()
            calendars = principal.calendars()

            for cal in calendars:
                try:
                    cal_events = cal.date_search(start=now, end=end, expand=True)
                    for ev in cal_events:
                        parsed = self._parse_event(ev)
                        if parsed:
                            events.append(parsed)
                except Exception as e:
                    logger.warning("Calendar %s parse error: %s", cal.name, e)

        except Exception as e:
            logger.error("CalDAV connect error: %s", e)
            return {"error": str(e), "events": []}

        events.sort(key=lambda x: x.get("start", ""))

        return {
            "events": events,
            "total": len(events),
            "birthdays": [e for e in events if e.get("is_birthday")],
            "holidays": [e for e in events if e.get("is_holiday")],
            "days_ahead": days_ahead,
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _parse_event(self, caldav_event) -> dict | None:
        try:
            cal = Calendar.from_ical(caldav_event.data)
            for component in cal.walk():
                if component.name != "VEVENT":
                    continue

                summary = str(component.get("SUMMARY", ""))
                desc = str(component.get("DESCRIPTION", ""))
                location = str(component.get("LOCATION", ""))

                dtstart = component.get("DTSTART")
                if dtstart is None:
                    continue

                start_val = dtstart.dt
                if isinstance(start_val, date) and not isinstance(start_val, datetime):
                    start_str = start_val.isoformat()
                    all_day = True
                else:
                    start_str = start_val.isoformat()
                    all_day = False

                summary_lower = summary.lower()
                is_birthday = any(kw in summary_lower for kw in BIRTHDAY_KEYWORDS)
                is_holiday = any(kw in summary_lower for kw in HOLIDAY_KEYWORDS)

                return {
                    "summary": summary,
                    "start": start_str,
                    "description": desc[:300],
                    "location": location,
                    "all_day": all_day,
                    "is_birthday": is_birthday,
                    "is_holiday": is_holiday,
                }
        except Exception as e:
            logger.warning("Event parse error: %s", e)
        return None
