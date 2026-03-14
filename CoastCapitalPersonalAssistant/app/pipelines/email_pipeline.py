"""
Email Pipeline — iCloud IMAP reader and SMTP sender with Claude summaries.
"""
import email
import imaplib
import logging
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parseaddr, parsedate_to_datetime

import anthropic

from app.config import Config
from app.db import get_conn, log_daily_activity

logger = logging.getLogger(__name__)

DELIVERY_SENDERS = [
    "ups", "fedex", "usps", "amazon", "dhl", "shipment", "tracking",
    "delivery", "shipped", "order", "package",
]

FAMILY_KEYWORDS = ["kim", "lakin", "family", "mom", "dad", "sister", "brother"]


class EmailPipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    # ── Public Methods ────────────────────────────────────────────────────────

    def fetch_and_summarize(self, days: int = 7, folder: str = "INBOX", limit: int = 30) -> dict:
        """
        Fetch recent emails from iCloud, summarize with Claude, cache metadata in DB.

        DATA POLICY: Full email bodies are NEVER stored in MySQL.
        iCloud IMAP is the system of record for all messages.
        MySQL stores only: from_addr, subject, date_sent, AI-generated summary, is_family flag.
        """
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return {"error": "iCloud credentials not configured", "emails": []}

        raw_emails = self._fetch_emails(days=days, folder=folder, limit=limit)
        if not raw_emails:
            return {"emails": [], "total": 0}

        summaries = []
        for msg_data in raw_emails:
            summary = self._summarize_email(msg_data)
            summaries.append(summary)
            self._cache_email(summary)   # caches metadata + AI summary only

        family_count = sum(1 for s in summaries if s.get("is_family"))
        log_daily_activity(
            "email-summary",
            emails_processed=len(raw_emails),
            emails_summarized=len(summaries),
            family_emails_found=family_count,
        )
        return {
            "emails": summaries,
            "total": len(summaries),
            "family_count": family_count,
        }

    def send_email(self, to: str, subject: str, body: str, cc: str = "") -> bool:
        """Send email via iCloud SMTP."""
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            raise ValueError("iCloud credentials not configured")

        msg = MIMEMultipart("alternative")
        msg["From"] = Config.ICLOUD_EMAIL
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc

        msg.attach(MIMEText(body, "plain"))

        context = ssl.create_default_context()
        with smtplib.SMTP(Config.ICLOUD_SMTP_HOST, Config.ICLOUD_SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(Config.ICLOUD_EMAIL, Config.ICLOUD_APP_PASSWORD)
            recipients = [to] + ([cc] if cc else [])
            server.sendmail(Config.ICLOUD_EMAIL, recipients, msg.as_string())

        logger.info("Email sent to %s — %s", to, subject)
        return True

    def get_family_emails(self, days: int = 30) -> list[dict]:
        """Return recent emails from family contacts."""
        family_emails = Config.family_email_list()
        if not family_emails:
            return []
        raw = self._fetch_emails(days=days, limit=100)
        result = []
        for msg in raw:
            from_addr = msg.get("from", "").lower()
            if any(fe.lower() in from_addr for fe in family_emails):
                result.append(msg)
        return result

    # ── Private Methods ───────────────────────────────────────────────────────

    def _fetch_emails(self, days: int = 7, folder: str = "INBOX", limit: int = 30) -> list[dict]:
        since_date = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
        messages = []

        try:
            with imaplib.IMAP4_SSL(Config.ICLOUD_IMAP_HOST, Config.ICLOUD_IMAP_PORT) as imap:
                imap.login(Config.ICLOUD_EMAIL, Config.ICLOUD_APP_PASSWORD)
                imap.select(folder)

                _, uids = imap.search(None, f"SINCE {since_date}")
                uid_list = uids[0].split()

                # Fetch most recent up to limit
                for uid in reversed(uid_list[-limit:]):
                    _, data = imap.fetch(uid, "(RFC822)")
                    raw = data[0][1]
                    parsed = email.message_from_bytes(raw)
                    body = self._extract_body(parsed)
                    messages.append({
                        "uid": uid.decode(),
                        "from": parsed.get("From", ""),
                        "subject": parsed.get("Subject", "(no subject)"),
                        "date": parsed.get("Date", ""),
                        "body": body[:3000],  # truncate for AI
                    })
        except imaplib.IMAP4.error as e:
            logger.error("IMAP error: %s", e)

        return messages

    def _extract_body(self, msg) -> str:
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                cd = str(part.get("Content-Disposition", ""))
                if ct == "text/plain" and "attachment" not in cd:
                    try:
                        body += part.get_payload(decode=True).decode(errors="replace")
                    except Exception:
                        pass
        else:
            try:
                body = msg.get_payload(decode=True).decode(errors="replace")
            except Exception:
                body = str(msg.get_payload())
        return body.strip()

    def _is_family_email(self, from_addr: str) -> bool:
        family = Config.family_email_list()
        from_lower = from_addr.lower()
        if any(fe.lower() in from_lower for fe in family):
            return True
        return any(kw in from_lower for kw in FAMILY_KEYWORDS)

    def _summarize_email(self, msg_data: dict) -> dict:
        from_name, from_email = parseaddr(msg_data["from"])
        is_family = self._is_family_email(msg_data["from"])

        try:
            date_sent = parsedate_to_datetime(msg_data["date"])
        except Exception:
            date_sent = datetime.now()

        prompt = (
            f"Summarize this email in 2-3 sentences. "
            f"Note any required action or follow-up needed.\n\n"
            f"From: {msg_data['from']}\n"
            f"Subject: {msg_data['subject']}\n"
            f"Body:\n{msg_data['body']}"
        )

        try:
            resp = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            summary_text = resp.content[0].text
        except Exception as e:
            logger.warning("Claude summarize failed: %s", e)
            # Fallback: never store raw body. Use a neutral placeholder.
            summary_text = "(Summary unavailable — Claude API error)"

        # Return metadata + AI summary ONLY.
        # Email body is intentionally excluded; iCloud is the system of record.
        return {
            "uid": msg_data["uid"],
            "from_addr": msg_data["from"],
            "from_name": from_name or from_email,
            "subject": msg_data["subject"],
            "date_sent": date_sent.isoformat(),
            "summary": summary_text,
            "is_family": is_family,
        }

    def _cache_email(self, summary: dict):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO email_cache (uid, from_addr, subject, date_sent, summary, is_family) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE summary=%s, fetched_at=NOW()",
                (
                    summary["uid"],
                    summary["from_addr"],
                    summary["subject"],
                    summary["date_sent"],
                    summary["summary"],
                    1 if summary["is_family"] else 0,
                    summary["summary"],
                ),
            )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Email cache write failed: %s", e)
