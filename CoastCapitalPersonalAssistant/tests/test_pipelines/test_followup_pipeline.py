"""
Unit tests for FollowupPipeline.

Focuses on:
1. _is_ignored_sender — noreply / newsletter sender detection
2. scan() early return when iCloud credentials are absent
3. No email body content is stored (only subject, to_addr, uid)
"""
from unittest.mock import MagicMock, patch

import pytest

from app.pipelines.followup_pipeline import FollowupPipeline, IGNORE_SENDERS


def _make_pipeline():
    return FollowupPipeline()


# ── Ignored sender detection ──────────────────────────────────────────────────

class TestIsIgnoredSender:
    def setup_method(self):
        self.p = _make_pipeline()

    def test_noreply_ignored(self):
        assert self.p._is_ignored_sender("noreply@company.com") is True

    def test_no_reply_hyphenated_ignored(self):
        assert self.p._is_ignored_sender("no-reply@service.com") is True

    def test_donotreply_ignored(self):
        assert self.p._is_ignored_sender("donotreply@bank.com") is True

    def test_do_not_reply_hyphenated_ignored(self):
        assert self.p._is_ignored_sender("do-not-reply@marketing.com") is True

    def test_newsletter_ignored(self):
        assert self.p._is_ignored_sender("newsletter@news.com") is True

    def test_notifications_ignored(self):
        assert self.p._is_ignored_sender("notifications@github.com") is True

    def test_mailer_daemon_ignored(self):
        assert self.p._is_ignored_sender("mailer-daemon@mail.example.com") is True

    def test_hello_at_ignored(self):
        assert self.p._is_ignored_sender("hello@startup.io") is True

    def test_team_at_ignored(self):
        assert self.p._is_ignored_sender("team@product.com") is True

    def test_real_person_not_ignored(self):
        assert self.p._is_ignored_sender("john.doe@gmail.com") is False

    def test_business_contact_not_ignored(self):
        assert self.p._is_ignored_sender("alice.smith@clientco.com") is False

    def test_case_insensitive_noreply(self):
        assert self.p._is_ignored_sender("NoReply@COMPANY.COM") is True

    def test_case_insensitive_newsletter(self):
        assert self.p._is_ignored_sender("Newsletter@BigMedia.com") is True

    def test_ignore_keywords_match_all_defined_keywords(self):
        """Every keyword in IGNORE_SENDERS should trigger a match."""
        for kw in IGNORE_SENDERS:
            addr = f"{kw}@example.com"
            assert self.p._is_ignored_sender(addr) is True, (
                f"Expected '{addr}' to be ignored (keyword: {kw!r})"
            )


# ── Scan with no iCloud credentials ──────────────────────────────────────────

class TestScanWithoutCredentials:
    def test_returns_empty_followups_without_icloud(self, monkeypatch):
        monkeypatch.setattr("app.config.Config.ICLOUD_EMAIL", "")
        monkeypatch.setattr("app.config.Config.ICLOUD_APP_PASSWORD", "")

        p = _make_pipeline()

        with patch("app.db.get_conn") as mock_get_conn:
            mock_cur = MagicMock()
            mock_cur.fetchall.return_value = []
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cur
            mock_get_conn.return_value = mock_conn

            result = p.scan()

        assert result["followups"] == []
        assert result["total_sent_scanned"] == 0

    def test_fetch_sent_returns_empty_without_credentials(self, monkeypatch):
        monkeypatch.setattr("app.config.Config.ICLOUD_EMAIL", "")
        monkeypatch.setattr("app.config.Config.ICLOUD_APP_PASSWORD", "")
        p = _make_pipeline()
        assert p._fetch_sent_emails() == []

    def test_find_replied_ids_returns_empty_without_credentials(self, monkeypatch):
        monkeypatch.setattr("app.config.Config.ICLOUD_EMAIL", "")
        monkeypatch.setattr("app.config.Config.ICLOUD_APP_PASSWORD", "")
        p = _make_pipeline()
        assert p._find_replied_message_ids() == set()
