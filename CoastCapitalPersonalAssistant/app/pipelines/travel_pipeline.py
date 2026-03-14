"""
Travel Pipeline — detects flight, hotel, car rental, and cruise
booking confirmations in email and builds structured itineraries.
"""
import logging
import re
from datetime import datetime

import anthropic

from app.config import Config
from app.db import get_conn
from app.pipelines.email_pipeline import EmailPipeline

logger = logging.getLogger(__name__)

TRAVEL_SENDERS = [
    "aa.com", "delta.com", "united.com", "southwest.com", "jetblue.com",
    "alaskaair.com", "spirit.com", "frontier.com", "americanairlines",
    "booking.com", "expedia.com", "hotels.com", "airbnb.com", "vrbo.com",
    "marriott.com", "hilton.com", "hyatt.com", "ihg.com", "starwood",
    "hertz.com", "enterprise.com", "avis.com", "budget.com", "national.com",
    "carnival.com", "royalcaribbean.com", "ncl.com", "princess.com",
    "travelport", "sabre", "amadeus", "kayak.com", "priceline.com",
    "tripadvisor.com", "hotwire.com", "orbitz.com", "travelocity.com",
    "confirmation", "itinerary", "reservation", "booking",
]

BOOKING_KEYWORDS = [
    "confirmation", "booking confirmed", "reservation confirmed",
    "your flight", "your hotel", "check-in", "check-out",
    "e-ticket", "itinerary", "reservation number", "confirmation number",
    "your trip", "departs", "arrives",
]

BOOKING_TYPES = {
    "flight": ["flight", "airline", "departs", "arrives", "boarding", "e-ticket", "seat"],
    "hotel": ["hotel", "check-in", "check-out", "resort", "inn", "suite", "room"],
    "car": ["rental car", "vehicle", "pickup", "drop-off", "hertz", "enterprise", "avis"],
    "cruise": ["cruise", "embarkation", "disembarkation", "cabin", "port", "sailing"],
    "airbnb": ["airbnb", "vrbo", "check-in", "check-out", "host"],
}


class TravelPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def scan(self, days: int = 60) -> dict:
        """Scan email for travel bookings, extract structured itineraries."""
        raw_emails = EmailPipeline()._fetch_emails(days=days, limit=150)
        travel_emails = self._filter_travel_emails(raw_emails)

        itineraries = []
        for msg in travel_emails:
            itinerary = self._extract_itinerary(msg)
            if itinerary:
                itineraries.append(itinerary)
                self._save_itinerary(itinerary, msg.get("uid", ""))

        upcoming = self._load_upcoming()
        return {
            "itineraries": upcoming,
            "newly_detected": len(itineraries),
            "emails_scanned": len(raw_emails),
            "travel_emails_found": len(travel_emails),
        }

    def get_upcoming(self) -> dict:
        """Return stored upcoming travel from DB."""
        return {"itineraries": self._load_upcoming()}

    # ── Private ───────────────────────────────────────────────────────────────

    def _filter_travel_emails(self, emails: list[dict]) -> list[dict]:
        result = []
        for msg in emails:
            from_lower = msg.get("from", "").lower()
            subject_lower = msg.get("subject", "").lower()
            body_lower = msg.get("body", "").lower()
            combined = from_lower + " " + subject_lower + " " + body_lower

            if any(s in combined for s in TRAVEL_SENDERS):
                result.append(msg)
                continue
            if any(kw in combined for kw in BOOKING_KEYWORDS):
                result.append(msg)
        return result

    def _extract_itinerary(self, msg: dict) -> dict | None:
        prompt = f"""Extract travel booking details from this email. Return a JSON object with:
{{
  "trip_name": "descriptive name like 'NYC Trip' or 'LA Flight'",
  "destination": "city or location",
  "depart_date": "YYYY-MM-DD or null",
  "return_date": "YYYY-MM-DD or null",
  "carrier": "airline/hotel/car company name",
  "confirmation_num": "confirmation or reservation number",
  "booking_type": "flight|hotel|car|cruise|airbnb",
  "details": "brief summary of the booking"
}}

If this is NOT a travel booking confirmation, return null.
Return ONLY the JSON object or null.

From: {msg.get('from', '')}
Subject: {msg.get('subject', '')}
Body:
{msg.get('body', '')[:2000]}"""

        try:
            resp = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.lower() == "null" or not text:
                return None
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            import json
            return json.loads(text)
        except Exception as e:
            logger.warning("Itinerary extraction failed: %s", e)
            return None

    def _save_itinerary(self, data: dict, email_uid: str):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO travel_itineraries "
                "(trip_name, destination, depart_date, return_date, carrier, "
                "confirmation_num, booking_type, details, email_uid) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE status=status",
                (
                    data.get("trip_name"),
                    data.get("destination"),
                    data.get("depart_date"),
                    data.get("return_date"),
                    data.get("carrier"),
                    data.get("confirmation_num"),
                    data.get("booking_type"),
                    data.get("details"),
                    email_uid,
                ),
            )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Save itinerary failed: %s", e)

    def _load_upcoming(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT * FROM travel_itineraries "
                "WHERE (depart_date >= CURDATE() OR depart_date IS NULL) "
                "AND status='upcoming' "
                "ORDER BY depart_date ASC LIMIT 20"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Load travel failed: %s", e)
            return []
