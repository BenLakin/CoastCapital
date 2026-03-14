"""
Unit tests for app/db.py helper functions.

Focuses on log_daily_activity() — the pipeline activity logger that
records counts per day while enforcing an allowlist that prevents
any email body content from reaching the database.
"""
from unittest.mock import MagicMock, patch, call


# ── log_daily_activity ────────────────────────────────────────────────────────

def _make_mock_conn():
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn, cur


def test_log_allowed_columns_are_included():
    """Allowed count columns must appear in the SQL INSERT."""
    conn, cur = _make_mock_conn()
    with patch("app.db.get_conn", return_value=conn):
        from app.db import log_daily_activity
        log_daily_activity(
            "email-summary",
            emails_processed=10,
            emails_summarized=8,
            family_emails_found=2,
        )

    sql = cur.execute.call_args[0][0]
    assert "emails_processed" in sql
    assert "emails_summarized" in sql
    assert "family_emails_found" in sql


def test_log_disallowed_columns_are_filtered():
    """Columns not in the allowlist must never reach the database."""
    conn, cur = _make_mock_conn()
    with patch("app.db.get_conn", return_value=conn):
        from app.db import log_daily_activity
        log_daily_activity(
            "email-summary",
            emails_processed=5,
            # The following must be silently ignored:
            raw_body="Here is the full email body — should never be stored",
            email_content="More sensitive content",
            subject_text="Also not allowed",
        )

    sql = cur.execute.call_args[0][0]
    params = str(cur.execute.call_args[0][1])

    assert "raw_body" not in sql
    assert "email_content" not in sql
    assert "subject_text" not in sql
    assert "sensitive content" not in params
    assert "Here is the full" not in params


def test_log_pipeline_name_is_recorded():
    """The pipeline column should always be set to the provided name."""
    conn, cur = _make_mock_conn()
    with patch("app.db.get_conn", return_value=conn):
        from app.db import log_daily_activity
        log_daily_activity("morning-briefing", briefing_emailed=1)

    params = cur.execute.call_args[0][1]
    assert "morning-briefing" in params


def test_log_does_not_raise_on_db_error():
    """A database failure must not propagate as an exception."""
    with patch("app.db.get_conn", side_effect=Exception("Connection refused")):
        from app.db import log_daily_activity
        # Must not raise
        log_daily_activity("test-pipeline", emails_processed=3)


def test_log_status_and_note_are_allowed():
    """The 'status' and 'note' columns are in the allowlist."""
    conn, cur = _make_mock_conn()
    with patch("app.db.get_conn", return_value=conn):
        from app.db import log_daily_activity
        log_daily_activity("archive", status="success", note="5 rules applied")

    sql = cur.execute.call_args[0][0]
    assert "status" in sql
    assert "note" in sql


def test_log_empty_counts_still_inserts():
    """Calling with only the pipeline name (no counts) should still run."""
    conn, cur = _make_mock_conn()
    with patch("app.db.get_conn", return_value=conn):
        from app.db import log_daily_activity
        log_daily_activity("calendar")

    cur.execute.assert_called_once()


def test_log_upsert_uses_on_duplicate_key():
    """SQL must include ON DUPLICATE KEY UPDATE so re-running is idempotent."""
    conn, cur = _make_mock_conn()
    with patch("app.db.get_conn", return_value=conn):
        from app.db import log_daily_activity
        log_daily_activity("news-summary", news_articles=20)

    sql = cur.execute.call_args[0][0].upper()
    assert "ON DUPLICATE KEY UPDATE" in sql
