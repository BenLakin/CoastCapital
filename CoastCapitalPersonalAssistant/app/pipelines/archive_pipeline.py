"""
Archive Pipeline — learns email patterns, applies archiving rules,
and over time automatically moves emails to appropriate folders.
"""
import imaplib
import json
import logging
from datetime import datetime
from collections import Counter

import anthropic

from app.config import Config
from app.db import get_conn, log_daily_activity
from app.pipelines.email_pipeline import EmailPipeline

logger = logging.getLogger(__name__)

DEFAULT_RULES = [
    {"rule_type": "sender", "match_field": "from", "match_value": "noreply",
     "target_folder": "Archive/Newsletters", "auto_apply": True},
    {"rule_type": "sender", "match_field": "from", "match_value": "no-reply",
     "target_folder": "Archive/Newsletters", "auto_apply": True},
    {"rule_type": "subject", "match_field": "subject", "match_value": "unsubscribe",
     "target_folder": "Archive/Newsletters", "auto_apply": True},
    {"rule_type": "sender", "match_field": "from", "match_value": "newsletter",
     "target_folder": "Archive/Newsletters", "auto_apply": True},
    {"rule_type": "subject", "match_field": "subject", "match_value": "receipt",
     "target_folder": "Archive/Receipts", "auto_apply": True},
    {"rule_type": "subject", "match_field": "subject", "match_value": "invoice",
     "target_folder": "Archive/Receipts", "auto_apply": True},
    {"rule_type": "subject", "match_field": "subject", "match_value": "order confirmation",
     "target_folder": "Archive/Receipts", "auto_apply": True},
]


class ArchivePipeline:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)

    def run(self, dry_run: bool = True, learn_new_rules: bool = True) -> dict:
        """Main entry: apply rules, optionally learn new ones."""
        self._seed_default_rules()
        rules = self._load_rules()

        emails = EmailPipeline()._fetch_emails(days=30, limit=200)
        matched = []
        unmatched = []

        for msg in emails:
            rule = self._match_rule(msg, rules)
            if rule:
                matched.append({"email": msg, "rule": rule})
            else:
                unmatched.append(msg)

        archived_count = 0
        if not dry_run:
            archived_count = self._apply_rules(matched)

        new_rules = []
        if learn_new_rules and unmatched:
            new_rules = self._learn_rules(unmatched)
            self._save_learned_rules(new_rules)

        log_daily_activity(
            "archive-emails",
            emails_processed=len(emails),
            rules_applied=archived_count,
            note=f"dry_run={dry_run}, new_rules={len(new_rules)}",
        )
        return {
            "dry_run": dry_run,
            "emails_scanned": len(emails),
            "emails_matched": len(matched),
            "emails_archived": archived_count,
            "rules_applied": len(rules),
            "new_rules_learned": new_rules,
            "matches": [
                {"subject": m["email"]["subject"], "from": m["email"]["from"],
                 "target": m["rule"]["target_folder"]}
                for m in matched[:20]
            ],
        }

    # ── Private ───────────────────────────────────────────────────────────────

    def _seed_default_rules(self):
        """Insert default rules on first run if none exist."""
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM archive_rules")
            count = cur.fetchone()[0]
            if count == 0:
                for rule in DEFAULT_RULES:
                    cur.execute(
                        "INSERT INTO archive_rules (rule_type, match_field, match_value, "
                        "target_folder, auto_apply) VALUES (%s, %s, %s, %s, %s)",
                        (rule["rule_type"], rule["match_field"], rule["match_value"],
                         rule["target_folder"], 1 if rule["auto_apply"] else 0),
                    )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Seed rules failed: %s", e)

    def _load_rules(self) -> list[dict]:
        try:
            conn = get_conn()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM archive_rules ORDER BY auto_apply DESC, times_applied DESC")
            rules = cur.fetchall()
            cur.close()
            conn.close()
            return rules
        except Exception as e:
            logger.warning("Load rules failed: %s", e)
            return []

    def _match_rule(self, email: dict, rules: list[dict]) -> dict | None:
        for rule in rules:
            field_val = email.get(rule.get("match_field", ""), "").lower()
            match_val = rule.get("match_value", "").lower()
            if match_val in field_val:
                return rule
        return None

    def _apply_rules(self, matched: list[dict]) -> int:
        """Move matched emails on IMAP server."""
        if not Config.ICLOUD_EMAIL or not Config.ICLOUD_APP_PASSWORD:
            return 0

        count = 0
        try:
            with imaplib.IMAP4_SSL(Config.ICLOUD_IMAP_HOST, Config.ICLOUD_IMAP_PORT) as imap:
                imap.login(Config.ICLOUD_EMAIL, Config.ICLOUD_APP_PASSWORD)
                imap.select("INBOX")

                for item in matched:
                    uid = item["email"]["uid"]
                    target = item["rule"]["target_folder"]
                    rule_id = item["rule"].get("id")
                    try:
                        # Create folder if needed
                        imap.create(target)
                        imap.uid("COPY", uid, target)
                        imap.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                        self._log_archive(item["email"], target, rule_id)
                        self._bump_rule_count(rule_id)
                        count += 1
                    except Exception as e:
                        logger.warning("Archive uid %s failed: %s", uid, e)
                imap.expunge()
        except Exception as e:
            logger.error("IMAP archive error: %s", e)
        return count

    def _learn_rules(self, unmatched: list[dict]) -> list[dict]:
        """Use Claude to suggest new archiving rules based on unmatched emails."""
        if not unmatched:
            return []

        sample = unmatched[:40]
        email_list = "\n".join(
            f"- From: {m['from']} | Subject: {m['subject']}"
            for m in sample
        )

        prompt = (
            "Analyze these unarchived emails and suggest 3-5 new archiving rules. "
            "Return a JSON array of objects with keys: "
            '{"rule_type": str, "match_field": "from|subject", '
            '"match_value": str, "target_folder": str, "auto_apply": bool}. '
            "target_folder should follow the pattern Archive/Category. "
            "Only return the JSON array.\n\n" + email_list
        )

        try:
            resp = self.client.messages.create(
                model=Config.CLAUDE_MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            logger.warning("Rule learning failed: %s", e)
            return []

    def _save_learned_rules(self, rules: list[dict]):
        for rule in rules:
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    "INSERT IGNORE INTO archive_rules "
                    "(rule_type, match_field, match_value, target_folder, auto_apply) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (rule.get("rule_type", "subject"),
                     rule.get("match_field", "subject"),
                     rule.get("match_value", ""),
                     rule.get("target_folder", "Archive/General"),
                     0),  # learned rules require manual approval by default
                )
                cur.close()
                conn.close()
            except Exception as e:
                logger.warning("Save learned rule failed: %s", e)

    def _log_archive(self, email: dict, folder: str, rule_id):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO email_archive (original_uid, from_addr, subject, folder, rule_id, snippet) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (email.get("uid"), email.get("from"), email.get("subject"),
                 folder, rule_id, email.get("body", "")[:200]),
            )
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning("Archive log failed: %s", e)

    def _bump_rule_count(self, rule_id):
        if not rule_id:
            return
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("UPDATE archive_rules SET times_applied=times_applied+1 WHERE id=%s", (rule_id,))
            cur.close()
            conn.close()
        except Exception:
            pass
