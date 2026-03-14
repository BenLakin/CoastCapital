"""
MySQL connection pool + schema bootstrap for homelab_db.
"""
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
            pool_name="homelab_pool",
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
    """Bootstrap homelab_db schema and tables."""
    # First connect without selecting a database to create it if needed
    raw = mysql.connector.connect(
        host=Config.MYSQL_HOST,
        port=Config.MYSQL_PORT,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
    )
    cur = raw.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{Config.MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.close()
    raw.close()

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS system_snapshots (
            id               BIGINT AUTO_INCREMENT PRIMARY KEY,
            captured_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            machine_name     VARCHAR(128) NOT NULL DEFAULT 'unknown',
            machine_type     VARCHAR(32)  NOT NULL DEFAULT 'unknown',
            machine_desc     VARCHAR(255),
            cpu_pct          FLOAT,
            mem_pct          FLOAT,
            disk_pct         FLOAT,
            load_1           FLOAT,
            load_5           FLOAT,
            load_15          FLOAT,
            gpu_name         VARCHAR(128),
            gpu_util         FLOAT,
            gpu_mem_used_mb  INT,
            gpu_mem_total_mb INT,
            gpu_temp         FLOAT,
            raw_top          MEDIUMTEXT,
            raw_nvidia       MEDIUMTEXT,
            INDEX idx_captured    (captured_at),
            INDEX idx_machine     (machine_name),
            INDEX idx_mach_time   (machine_name, captured_at)
        ) ENGINE=InnoDB
    """)

    # Migrate existing tables that pre-date machine columns
    for col, definition in [
        ("machine_name", "VARCHAR(128) NOT NULL DEFAULT 'unknown'"),
        ("machine_type", "VARCHAR(32)  NOT NULL DEFAULT 'unknown'"),
        ("machine_desc", "VARCHAR(255)"),
    ]:
        try:
            cur.execute(
                f"ALTER TABLE system_snapshots ADD COLUMN IF NOT EXISTS {col} {definition}"
            )
        except Exception:
            pass  # column already exists or DB doesn't support IF NOT EXISTS

    cur.execute("""
        CREATE TABLE IF NOT EXISTS unifi_snapshots (
            id           BIGINT AUTO_INCREMENT PRIMARY KEY,
            captured_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            wan_rx_bytes BIGINT,
            wan_tx_bytes BIGINT,
            wan_speed_mbps FLOAT,
            clients_wifi INT,
            clients_wired INT,
            alerts_count INT,
            uptime_sec   BIGINT,
            wan_ip       VARCHAR(64),
            isp_name     VARCHAR(128),
            raw_json     MEDIUMTEXT,
            INDEX idx_captured (captured_at)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS plex_snapshots (
            id            BIGINT AUTO_INCREMENT PRIMARY KEY,
            captured_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            active_streams INT,
            total_movies  INT,
            total_shows   INT,
            total_music   INT,
            now_playing   MEDIUMTEXT,
            raw_json      MEDIUMTEXT,
            INDEX idx_captured (captured_at)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS homeassistant_snapshots (
            id             BIGINT AUTO_INCREMENT PRIMARY KEY,
            captured_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            entity_count   INT,
            alert_count    INT,
            automations_on INT,
            alerts_json    MEDIUMTEXT,
            raw_json       MEDIUMTEXT,
            INDEX idx_captured (captured_at)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS portainer_snapshots (
            id              BIGINT AUTO_INCREMENT PRIMARY KEY,
            captured_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            running_count   INT,
            stopped_count   INT,
            total_count     INT,
            unhealthy_count INT,
            containers_json MEDIUMTEXT,
            INDEX idx_captured (captured_at)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ollama_snapshots (
            id           BIGINT AUTO_INCREMENT PRIMARY KEY,
            captured_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            models_count INT,
            models_json  MEDIUMTEXT,
            INDEX idx_captured (captured_at)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS dns_snapshots (
            id           BIGINT AUTO_INCREMENT PRIMARY KEY,
            captured_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source       VARCHAR(32) DEFAULT 'coredns',
            queries_24h  INT,
            blocked_24h  INT,
            block_pct    FLOAT,
            top_blocked  MEDIUMTEXT,
            top_clients  MEDIUMTEXT,
            raw_json     MEDIUMTEXT,
            INDEX idx_captured (captured_at)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS homelab_events (
            id          BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source      VARCHAR(64) NOT NULL,
            severity    ENUM('info','warn','error','critical') DEFAULT 'info',
            title       VARCHAR(255) NOT NULL,
            details     MEDIUMTEXT,
            resolved    TINYINT(1) DEFAULT 0,
            INDEX idx_source (source),
            INDEX idx_severity (severity),
            INDEX idx_event_at (event_at)
        ) ENGINE=InnoDB
    """)

    cur.close()
    conn.close()
    logger.info("homelab_db schema bootstrapped")


def log_event(source: str, title: str, details: str = "", severity: str = "info"):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO homelab_events (source, severity, title, details) VALUES (%s, %s, %s, %s)",
            (source, severity, title, details),
        )
        cur.close()
        conn.close()
    except Exception as e:
        logger.error("log_event failed: %s", e)
