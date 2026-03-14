"""
MySQL connection pool + prediction logging for the Platform service.

Stores every intent classification so users can upvote/downvote accuracy.
Ground truth data feeds back into the Ollama system prompt.
"""

import logging
from contextlib import contextmanager
from datetime import datetime

import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool

from app.config import Config

logger = logging.getLogger(__name__)

_pool: MySQLConnectionPool | None = None

# ── Table DDL ────────────────────────────────────────────────────────────────

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS `dispatch_predictions` (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source          VARCHAR(50)   NOT NULL DEFAULT 'slack',
    user_text       TEXT          NOT NULL,
    predicted_intent VARCHAR(100) NOT NULL,
    predicted_params JSON,
    confidence      FLOAT         NOT NULL DEFAULT 0.0,
    ollama_model    VARCHAR(100)  NOT NULL DEFAULT '',
    response_time_ms INT          NOT NULL DEFAULT 0,
    webhook_path    VARCHAR(255)  DEFAULT NULL,
    -- Feedback
    vote            ENUM('up', 'down') DEFAULT NULL,
    correct_intent  VARCHAR(100)  DEFAULT NULL,
    feedback_note   TEXT          DEFAULT NULL,
    voted_at        TIMESTAMP     NULL DEFAULT NULL,
    INDEX idx_vote (vote),
    INDEX idx_created (created_at),
    INDEX idx_intent (predicted_intent)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""


# ── Pool Management ──────────────────────────────────────────────────────────

def _get_pool() -> MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = MySQLConnectionPool(
            pool_name="platform",
            pool_size=5,
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DATABASE,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
            autocommit=True,
        )
        logger.info("MySQL pool created — host=%s db=%s", Config.MYSQL_HOST, Config.MYSQL_DATABASE)
    return _pool


@contextmanager
def get_conn():
    """Yield a pooled MySQL connection (auto-returned on exit)."""
    conn = _get_pool().get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Create the dispatch_predictions table if it doesn't exist."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(_CREATE_TABLE)
            cur.close()
        logger.info("dispatch_predictions table ready")
    except Exception as exc:
        logger.warning("Could not init DB (will retry on first use): %s", exc)


# ── Prediction Logging ───────────────────────────────────────────────────────

def log_prediction(
    source: str,
    user_text: str,
    predicted_intent: str,
    predicted_params: dict,
    confidence: float,
    ollama_model: str,
    response_time_ms: int,
    webhook_path: str | None,
) -> int | None:
    """Insert a prediction row and return its ID."""
    import json
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO dispatch_predictions
                   (source, user_text, predicted_intent, predicted_params,
                    confidence, ollama_model, response_time_ms, webhook_path)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    source, user_text, predicted_intent,
                    json.dumps(predicted_params), confidence,
                    ollama_model, response_time_ms, webhook_path,
                ),
            )
            row_id = cur.lastrowid
            cur.close()
            return row_id
    except Exception as exc:
        logger.error("Failed to log prediction: %s", exc)
        return None


# ── Feedback ─────────────────────────────────────────────────────────────────

def submit_vote(prediction_id: int, vote: str, correct_intent: str | None = None, note: str | None = None) -> bool:
    """Record an upvote or downvote on a prediction."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """UPDATE dispatch_predictions
                   SET vote = %s, correct_intent = %s, feedback_note = %s, voted_at = NOW()
                   WHERE id = %s""",
                (vote, correct_intent, note, prediction_id),
            )
            affected = cur.rowcount
            cur.close()
            return affected > 0
    except Exception as exc:
        logger.error("Failed to submit vote: %s", exc)
        return False


# ── Ground Truth Queries ─────────────────────────────────────────────────────

def get_good_examples(limit: int = 100) -> list[dict]:
    """Get upvoted predictions as positive examples for the Ollama prompt."""
    try:
        with get_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT user_text, predicted_intent, predicted_params
                   FROM dispatch_predictions
                   WHERE vote = 'up'
                   ORDER BY voted_at DESC
                   LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
            cur.close()
            return rows
    except Exception as exc:
        logger.error("Failed to fetch good examples: %s", exc)
        return []


def get_bad_examples(limit: int = 100) -> list[dict]:
    """Get downvoted predictions as negative examples for the Ollama prompt."""
    try:
        with get_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute(
                """SELECT user_text, predicted_intent, correct_intent, feedback_note
                   FROM dispatch_predictions
                   WHERE vote = 'down'
                   ORDER BY voted_at DESC
                   LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
            cur.close()
            return rows
    except Exception as exc:
        logger.error("Failed to fetch bad examples: %s", exc)
        return []


# ── Dashboard Queries ────────────────────────────────────────────────────────

def get_predictions(limit: int = 50, offset: int = 0, vote_filter: str | None = None) -> list[dict]:
    """Get recent predictions for the feedback dashboard."""
    try:
        with get_conn() as conn:
            cur = conn.cursor(dictionary=True)
            sql = "SELECT * FROM dispatch_predictions"
            params = []
            if vote_filter == "pending":
                sql += " WHERE vote IS NULL"
            elif vote_filter in ("up", "down"):
                sql += " WHERE vote = %s"
                params.append(vote_filter)
            sql += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            cur.execute(sql, tuple(params))
            rows = cur.fetchall()
            cur.close()
            return rows
    except Exception as exc:
        logger.error("Failed to fetch predictions: %s", exc)
        return []


def get_stats() -> dict:
    """Get aggregate stats for the feedback dashboard."""
    try:
        with get_conn() as conn:
            cur = conn.cursor(dictionary=True)
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    SUM(vote = 'up') AS upvotes,
                    SUM(vote = 'down') AS downvotes,
                    SUM(vote IS NULL) AS pending,
                    ROUND(AVG(confidence), 3) AS avg_confidence,
                    ROUND(AVG(response_time_ms)) AS avg_response_ms,
                    ROUND(
                        SUM(vote = 'up') * 100.0 /
                        NULLIF(SUM(vote IS NOT NULL), 0),
                        1
                    ) AS accuracy_pct
                FROM dispatch_predictions
            """)
            row = cur.fetchone()
            cur.close()
            return row or {}
    except Exception as exc:
        logger.error("Failed to fetch stats: %s", exc)
        return {}
