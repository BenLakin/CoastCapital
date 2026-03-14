"""
Follow-up Tracker Pipeline — scans the Sent folder for emails that have
not received a reply after a configurable number of days.
Excludes newsletters, no-reply addresses, and automated senders.
"""
import email
import imaplib
import logging
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime, parseaddr

from app.config import Config
from app.db import get_conn, log_daily_activity

logger = logging.getLogger(__name__)

IGNORE_SENDERS = [
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "newsletter", "notifications", "updates", "mailer-daemon",
    "support", "billing", "hello@", "team@",
]

SENT_FOLDERS = ["Sent Messages", "Sent", "[Gmail]/Sent Mail", "INBOX.Sent"]
WAIT_DAYS = 3   # Surface as follow-up after this many days without reply


class FollowupPipeline:

    def scan(self, wait_days: int = WAIT_DAYS, limit: int = 100) -> dict:
        """Scan Sent folder, detect unanswered emails, update DB."""
        sent = self._fetch_sent_emails(limit=limit)
        if not sent:
            return {"followups": [], "total_sent_scanned": 0}

        # Load existing UIDs we're already tracking
        tracked = self._load_tracked_uids()
        replied_ids = self._find_replied_message_ids()

        new_followups = []
        for msg in sent:
            uid = msg["uid"]
            msg_id = msg.get("message_id", "")
            sent_at = msg.get("sent_at")

            if not sent_at:
                continue

            days_waiting = (datetime.now() - sent_at).days
            if days_waiting < wait_days:
                continue

            if self._is_ignored_sender(msg.get("from", "")):
                continue

            # Check if the sent Message-ID got a reply (appears in In-Reply-To anywhere)
            if msg_id and msg_id in replied_ids:
                self._mark_replied(uid)
                continue

            if uid not in tracked:
                new_followups.append(msg)
                self._upsert_followup(msg, days_waiting)
            else:
                self._update_days_waiting(uid, days_waiting)

        # Return all active follow-ups from DB.
        # NOTE: Only subject/to/date stored — no email bodies in MySQL.
        active = self._load_active_followups()
        log_daily_activity(
            "followup",
            emails_processed=len(sent),
            followups_detected=len(new_followups),
        )
        return {
            "followups": active,
            "total_sent_scanned": len(sent),
            "new_flagged": len(new_followups),
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _fetch_sent_emails(self, limit: int = 100) -> list[dict]:
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return []

        messages = []
        cutoff = (datetime.now() - timedelta(days=60)).strftime("%d-%b-%Y")

        try:
            with imaplib.IMAP4_SSL(Config.ICLOUD_IMAP_HOST, Config.ICLOUD_IMAP_PORT) as imap:
                imap.login(Config.ICLOUD_EMAIL, Config.ICLOUD_APP_PASSWORD)

                sent_folder = self._find_sent_folder(imap)
                if not sent_folder:
                    logger.warning("Could not find Sent folder")
                    return []

                imap.select(sent_folder)
                _, uids = imap.search(None, f"SINCE {cutoff}")
                uid_list = uids[0].split()

                for uid in reversed(uid_list[-limit:]):
                    _, data = imap.fetch(uid, "(RFC822.HEADER)")
                    raw = data[0][1]
                    parsed = email.message_from_bytes(raw)

                    date_str = parsed.get("Date", "")
                    try:
                        sent_at = parsedate_to_datetime(date_str)
                        sent_at = sent_at.replace(tzinfo=None)
                    except Exception:
                        continue

                    to_addr = parsed.get("To", "")
                    # Skip if To: is ourselves
                    if Config.ICLOUD_EMAIL.lower() in to_addr.lower():
                        continue

                    messages.append({
                        "uid": uid.decode(),
                        "from": parsed.get("From", ""),
                        "to": to_addr,
                        "subject": parsed.get("Subject", "(no subject)"),
                        "message_id": parsed.get("Message-ID", "").strip(),
                        "sent_at": sent_at,
                    })
        except Exception as e:
            logger.error("IMAP Sent fetch error: %s", e)

        return messages

    def _find_sent_folder(self, imap) -> str | None:
        _, folders = imap.list()
        folder_names = []
        for f in folders:
            parts = f.decode().split('"')
            if len(parts) >= 3:
                folder_names.append(parts[-2])

        for candidate in SENT_FOLDERS:
            for name in folder_names:
                if candidate.lower() in name.lower():
                    return name
        return None

    def _find_replied_message_ids(self) -> set[str]:
        """Scan INBOX for In-Reply-To headers to detect which sent emails got replies."""
        replied = set()
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return replied

        cutoff = (datetime.now() - timedelta(days=60)).strftime("%d-%b-%Y")
        try:
            with imaplib.IMAP4_SSL(Config.ICLOUD_IMAP_HOST, Config.ICLOUD_IMAP_PORT) as imap:
                imap.login(Config.ICLOUD_EMAIL, Config.ICLOUD_APP_PASSWORD)
                imap.select("INBOX")
                _, uids = imap.search(None, f"SINCE {cutoff}")
                uid_list = uids[0].split()

                for uid in uid_list[-300:]:
                    _, data = imap.fetch(uid, "(RFC822.HEADER)")
                    raw = data[0][1]
                    parsed = email.message_from_bytes(raw)
                    irt = parsed.get("In-Reply-To", "").strip()
                    if irt:
                        replied.add(irt)
                    refs = parsed.get("References", "")
                    for ref in refs.split():
                        replied.add(ref.strip())
        except Exception as e:
            logger.warning("Reply detection error: %s", e)

        return replied

    def _is_ignored_sender(self, from_addr: str) -> bool:
        lower = from_addr.lower()
        return any(kw in lower for kw in IGNORE_SENDERS)

    def _load_tracked_uids(self) -> set[str]:
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT email_uid FROM followup_tracker WHERE status='waiting'")
            uids = {row[0] for row in cur.fetchall()}
            cur.close()
            conn.close()
            return uids
        except Exception:
            return set()

    def _load_active_followups(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute(
                "SELECT id, to_addr, subject, sent_at, days_waiting, snippet "
                "FROM followup_tracker WHERE status='waiting' "
                "ORDER BY days_waiting DESC LIMIT 30"
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            logger.warning("Load followups failed: %s", e)
            return []

    def _upsert_followup(self, msg: dict, days_waiting: int):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO followup_tracker "
                "(email_uid, sent_at, to_addr, subject, snippet, days_waiting) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE days_waiting=%s",
                (
                    msg["uid"],
                    msg["sent_at"],
                    msg["to"],
                    msg["subject"],
                    msg.get("snippet", "")[:300],
                    days_waiting,
                    days_waiting,
                ),
            )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Upsert followup failed: %s", e)

    def _update_days_waiting(self, uid: str, days: int):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE followup_tracker SET days_waiting=%s WHERE email_uid=%s",
                (days, uid),
            )
            cur.close()
            conn.close()
        except Exception:
            pass

    def _mark_replied(self, uid: str):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "UPDATE followup_tracker SET status='replied' WHERE email_uid=%s",
                (uid,),
            )
            cur.close()
            conn.close()
        except Exception:
            pass
