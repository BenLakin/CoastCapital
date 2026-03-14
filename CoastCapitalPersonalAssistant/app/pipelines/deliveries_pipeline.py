"""
Deliveries Pipeline — scans email for shipping notifications and calendar
for upcoming birthdays, holidays, and personal events.
"""
import logging
import re
from datetime import datetime, timedelta

import anthropic

from app.config import Config
from app.db import get_conn
from app.pipelines.email_pipeline import EmailPipeline
from app.pipelines.calendar_pipeline import CalendarPipeline

logger = logging.getLogger(__name__)

CARRIER_PATTERNS = {
    "UPS": [r"ups\.com", r"1Z[A-Z0-9]{16}", r"United Parcel Service"],
    "FedEx": [r"fedex\.com", r"\b\d{12}\b|\b\d{15}\b", r"Federal Express"],
    "USPS": [r"usps\.com", r"9[2345]\d{20}", r"United States Postal"],
    "Amazon": [r"amazon\.com", r"TBA\d+", r"Amazon Logistics"],
    "DHL": [r"dhl\.com", r"\b\d{10,11}\b", r"DHL Express"],
}

SHIPPING_KEYWORDS = [
    "shipped", "tracking", "delivery", "package", "order", "out for delivery",
    "delivered", "shipment", "dispatch", "expected delivery",
]

TRACKING_REGEX = re.compile(
    r"\b(1Z[A-Z0-9]{16}|9[2345]\d{20}|\d{12}|\d{15}|TBA\d{12,})\b"
)


class DeliveriesPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def fetch_all(self) -> dict:
        deliveries = self._scan_email_deliveries()
        upcoming_events = self._get_upcoming_events()
        return {
            "deliveries": deliveries,
            "upcoming_events": upcoming_events,
            "birthdays": [e for e in upcoming_events if e.get("is_birthday")],
            "holidays": [e for e in upcoming_events if e.get("is_holiday")],
            "fetched_at": datetime.now().isoformat(),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _scan_email_deliveries(self) -> list[dict]:
        """Find shipping-related emails in the last 30 days."""
        if not Config.ICLOUD_EMAIL:
            return []

        raw_emails = EmailPipeline()._fetch_emails(days=30, limit=100)
        deliveries = []

        for msg in raw_emails:
            subject = msg.get("subject", "").lower()
            body = msg.get("body", "").lower()
            combined = subject + " " + body

            if not any(kw in combined for kw in SHIPPING_KEYWORDS):
                continue

            carrier = self._detect_carrier(combined)
            tracking = self._extract_tracking(msg.get("body", ""))
            expected = self._extract_expected_date(msg.get("body", ""))
            status = self._extract_status(combined)

            delivery = {
                "carrier": carrier,
                "tracking_num": tracking or "N/A",
                "description": msg.get("subject", ""),
                "status": status,
                "expected_date": expected,
                "email_uid": msg.get("uid"),
            }
            deliveries.append(delivery)
            self._cache_delivery(delivery)

        return deliveries

    def _detect_carrier(self, text: str) -> str:
        for carrier, patterns in CARRIER_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    return carrier
        return "Unknown"

    def _extract_tracking(self, text: str) -> str | None:
        match = TRACKING_REGEX.search(text)
        return match.group(0) if match else None

    def _extract_expected_date(self, text: str) -> str | None:
        date_patterns = [
            r"(?:expected|delivery|arriving|estimated)[^\n]*?(\w+ \d{1,2},? \d{4})",
            r"(?:by|on) (\w+ \d{1,2},? \d{4})",
        ]
        for pattern in date_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    from dateutil import parser as dateparser
                    return dateparser.parse(m.group(1)).strftime("%Y-%m-%d")
                except Exception:
                    return m.group(1)
        return None

    def _extract_status(self, text: str) -> str:
        if "delivered" in text:
            return "Delivered"
        if "out for delivery" in text:
            return "Out for Delivery"
        if "in transit" in text or "on its way" in text:
            return "In Transit"
        if "shipped" in text or "dispatch" in text:
            return "Shipped"
        return "Processing"

    def _cache_delivery(self, delivery: dict):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO deliveries (carrier, tracking_num, description, status, "
                "expected_date, email_uid) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE status=%s",
                (
                    delivery["carrier"],
                    delivery["tracking_num"],
                    delivery["description"],
                    delivery["status"],
                    delivery.get("expected_date"),
                    delivery.get("email_uid"),
                    delivery["status"],
                ),
            )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Delivery cache write failed: %s", e)

    def _get_upcoming_events(self) -> list[dict]:
        try:
            data = CalendarPipeline().get_upcoming_events(days_ahead=30)
            return data.get("events", [])
        except Exception as e:
            logger.warning("Calendar fetch for deliveries failed: %s", e)
            return []
