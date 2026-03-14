"""MySQL connection helper and schema bootstrap."""
import logging
import mysql.connector
from mysql.connector import pooling
from app.config import Config

logger = logging.getLogger(__name__)

_pool: pooling.MySQLConnectionPool | None = None


def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="assistant_pool",
            pool_size=5,
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
            database=Config.MYSQL_DATABASE,
            autocommit=True,
        )
    return _pool


def get_conn():
    return get_pool().get_connection()


def init_db():
    """Create database and tables if they don't exist."""
    # First connect without a database to create it
    try:
        tmp = mysql.connector.connect(
            host=Config.MYSQL_HOST,
            port=Config.MYSQL_PORT,
            user=Config.MYSQL_USER,
            password=Config.MYSQL_PASSWORD,
        )
        cur = tmp.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{Config.MYSQL_DATABASE}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cur.close()
        tmp.close()
    except Exception as e:
        logger.error("Could not create database: %s", e)
        return

    ddl_statements = [
        """CREATE TABLE IF NOT EXISTS email_cache (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            fetched_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            folder        VARCHAR(100) DEFAULT 'INBOX',
            uid           VARCHAR(50),
            from_addr     TEXT,
            subject       TEXT,
            date_sent     DATETIME,
            summary       TEXT,
            is_family     TINYINT(1) DEFAULT 0,
            INDEX idx_fetched (fetched_at),
            INDEX idx_uid (uid(50))
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS news_cache (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            fetched_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            category      VARCHAR(50),
            title         TEXT,
            source        VARCHAR(200),
            url           TEXT,
            summary       TEXT,
            INDEX idx_fetched (fetched_at),
            INDEX idx_category (category)
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS action_items (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            priority      TINYINT DEFAULT 5,
            title         VARCHAR(500),
            detail        TEXT,
            action_type   VARCHAR(50),
            recipient     VARCHAR(200),
            email_subject VARCHAR(500),
            email_body    TEXT,
            status        VARCHAR(20) DEFAULT 'pending',
            INDEX idx_status (status),
            INDEX idx_created (created_at)
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS archive_rules (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            rule_type     VARCHAR(50),
            match_field   VARCHAR(50),
            match_value   VARCHAR(200),
            target_folder VARCHAR(200),
            auto_apply    TINYINT(1) DEFAULT 0,
            times_applied INT DEFAULT 0
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS email_archive (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            archived_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            original_uid  VARCHAR(50),
            from_addr     TEXT,
            subject       TEXT,
            date_sent     DATETIME,
            folder        VARCHAR(200),
            rule_id       INT,
            snippet       TEXT
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS deliveries (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            detected_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            carrier       VARCHAR(50),
            tracking_num  VARCHAR(200),
            description   TEXT,
            status        VARCHAR(100),
            expected_date DATE,
            email_uid     VARCHAR(50)
        ) ENGINE=InnoDB""",

        # ── Relationships ──────────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS relationships (
            id                INT AUTO_INCREMENT PRIMARY KEY,
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at        DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            name              VARCHAR(200) NOT NULL,
            email             VARCHAR(200),
            phone             VARCHAR(50),
            birthday          DATE,
            relationship_type VARCHAR(50) DEFAULT 'family',
            notes             TEXT,
            is_family         TINYINT(1) DEFAULT 0,
            last_contacted    DATETIME,
            contact_frequency_days INT DEFAULT 30,
            UNIQUE KEY idx_email (email),
            INDEX idx_birthday (birthday),
            INDEX idx_name (name)
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS relationship_preferences (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            relationship_id  INT NOT NULL,
            recorded_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            category         VARCHAR(100),
            preference       TEXT,
            source           VARCHAR(100) DEFAULT 'manual',
            confidence       TINYINT DEFAULT 5,
            is_active        TINYINT(1) DEFAULT 1,
            INDEX idx_rel (relationship_id),
            INDEX idx_category (category),
            FOREIGN KEY (relationship_id) REFERENCES relationships(id) ON DELETE CASCADE
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS relationship_interactions (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            relationship_id  INT NOT NULL,
            interaction_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
            type             VARCHAR(50),
            summary          TEXT,
            sentiment        VARCHAR(20) DEFAULT 'neutral',
            INDEX idx_rel (relationship_id),
            INDEX idx_type (type),
            FOREIGN KEY (relationship_id) REFERENCES relationships(id) ON DELETE CASCADE
        ) ENGINE=InnoDB""",

        """CREATE TABLE IF NOT EXISTS gifts (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            relationship_id  INT NOT NULL,
            created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
            occasion         VARCHAR(100),
            occasion_date    DATE,
            gift_description TEXT,
            status           VARCHAR(50) DEFAULT 'idea',
            price            DECIMAL(10,2),
            reaction         TEXT,
            purchase_url     TEXT,
            INDEX idx_rel (relationship_id),
            INDEX idx_occasion_date (occasion_date),
            INDEX idx_status (status),
            FOREIGN KEY (relationship_id) REFERENCES relationships(id) ON DELETE CASCADE
        ) ENGINE=InnoDB""",

        # ── Follow-up Tracker ──────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS followup_tracker (
            id           INT AUTO_INCREMENT PRIMARY KEY,
            detected_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            email_uid    VARCHAR(100) UNIQUE,
            sent_at      DATETIME,
            to_addr      TEXT,
            subject      TEXT,
            snippet      TEXT,
            days_waiting INT DEFAULT 0,
            status       VARCHAR(50) DEFAULT 'waiting',
            dismissed_at DATETIME,
            INDEX idx_status (status),
            INDEX idx_sent (sent_at)
        ) ENGINE=InnoDB""",

        # ── Travel Itineraries ─────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS travel_itineraries (
            id               INT AUTO_INCREMENT PRIMARY KEY,
            detected_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
            trip_name        VARCHAR(200),
            destination      VARCHAR(200),
            depart_date      DATE,
            return_date      DATE,
            carrier          VARCHAR(100),
            confirmation_num VARCHAR(100),
            booking_type     VARCHAR(50),
            status           VARCHAR(50) DEFAULT 'upcoming',
            details          TEXT,
            email_uid        VARCHAR(100),
            INDEX idx_depart (depart_date),
            INDEX idx_status (status)
        ) ENGINE=InnoDB""",

        # ── Morning Briefings ──────────────────────────────────────────────
        """CREATE TABLE IF NOT EXISTS morning_briefings (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
            briefing_date DATE,
            content       TEXT,
            emailed       TINYINT(1) DEFAULT 0,
            UNIQUE KEY idx_date (briefing_date)
        ) ENGINE=InnoDB""",

        # ── Daily Activity Log ─────────────────────────────────────────────
        # Records pipeline activity counts per day. Never stores email content.
        # Email bodies stay in iCloud — only AI-generated summaries and
        # metadata (from, subject, date) are stored in assistant_db.
        """CREATE TABLE IF NOT EXISTS daily_activity_log (
            id                   INT AUTO_INCREMENT PRIMARY KEY,
            log_date             DATE NOT NULL,
            logged_at            DATETIME DEFAULT CURRENT_TIMESTAMP,
            pipeline             VARCHAR(100) NOT NULL,
            emails_processed     INT DEFAULT 0,
            emails_summarized    INT DEFAULT 0,
            family_emails_found  INT DEFAULT 0,
            action_items_created INT DEFAULT 0,
            news_articles        INT DEFAULT 0,
            reminders_checked    INT DEFAULT 0,
            followups_detected   INT DEFAULT 0,
            rules_applied        INT DEFAULT 0,
            deliveries_found     INT DEFAULT 0,
            briefing_emailed     TINYINT(1) DEFAULT 0,
            status               VARCHAR(50) DEFAULT 'success',
            note                 VARCHAR(500),
            UNIQUE KEY idx_date_pipeline (log_date, pipeline),
            INDEX idx_log_date (log_date)
        ) ENGINE=InnoDB""",
    ]

    try:
        conn = get_conn()
        cur = conn.cursor()
        for stmt in ddl_statements:
            cur.execute(stmt)
        cur.close()
        conn.close()
        logger.info("Database schema initialized successfully")
    except Exception as e:
        logger.error("Schema init failed: %s", e)


def log_daily_activity(pipeline: str, **counts) -> None:
    """
    Record what a pipeline did today. Counts only — no email content ever stored here.
    Email bodies remain in iCloud; MySQL holds only AI-generated summaries and metadata.

    Usage:
        log_daily_activity("email-summary", emails_processed=12, family_emails_found=2)
        log_daily_activity("news-summary", news_articles=20)
        log_daily_activity("archive-emails", rules_applied=5, status="success")
    """
    from datetime import date
    today = date.today().isoformat()
    allowed_cols = {
        "emails_processed", "emails_summarized", "family_emails_found",
        "action_items_created", "news_articles", "reminders_checked",
        "followups_detected", "rules_applied", "deliveries_found",
        "briefing_emailed", "status", "note",
    }
    filtered = {k: v for k, v in counts.items() if k in allowed_cols}

    try:
        conn = get_conn()
        cur = conn.cursor()
        cols = ", ".join(filtered.keys())
        vals = ", ".join(["%s"] * len(filtered))
        updates = ", ".join(f"{k}=VALUES({k})" for k in filtered)
        sql = (
            f"INSERT INTO daily_activity_log (log_date, pipeline, {cols}) "
            f"VALUES (%s, %s, {vals}) "
            f"ON DUPLICATE KEY UPDATE logged_at=NOW(), {updates}"
        )
        cur.execute(sql, [today, pipeline] + list(filtered.values()))
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning("log_daily_activity failed for %s: %s", pipeline, e)
