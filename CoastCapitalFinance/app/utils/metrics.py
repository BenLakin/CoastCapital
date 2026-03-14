"""
Prometheus metrics + centralized MySQL web analytics logging.

Exposes a /metrics endpoint for Prometheus scraping and logs page views,
errors, and actions to the shared maintenance_db.web_analytics table.
Each row includes a `module` column identifying the originating service.

Usage (auto-hook):
    from app.utils.metrics import init_metrics
    init_metrics(app, module="homelab")

Usage (standalone):
    from app.utils.metrics import log_pageview, log_error, metrics_response, ensure_table
"""

import logging
import os
import time
import threading
import traceback as _tb

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

_log = logging.getLogger("metrics")

# ── Prometheus metrics ──────────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["module", "method", "path", "status"],
)
REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["module", "method", "path"],
)
ERROR_COUNT = Counter(
    "http_errors_total",
    "Total HTTP errors",
    ["module", "error_type"],
)

# ── MySQL analytics logging (fire-and-forget) ──────────────────────────────

_MYSQL_HOST = os.environ.get("MYSQL_HOST", "coastcapital-mysql")
_MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
_MYSQL_USER = os.environ.get("MYSQL_USER", "dbadmin")
_MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")
_ANALYTICS_DB = "maintenance_db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS web_analytics (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    module VARCHAR(32) NOT NULL COMMENT 'finance, homelab, sports, assistant',
    event_type ENUM('pageview','error','action') NOT NULL,
    path VARCHAR(512) DEFAULT '',
    method VARCHAR(10) DEFAULT '',
    status_code SMALLINT DEFAULT 0,
    duration_ms INT DEFAULT 0,
    error_type VARCHAR(128) DEFAULT '',
    error_message TEXT,
    action_name VARCHAR(256) DEFAULT '',
    success TINYINT(1) DEFAULT 1,
    INDEX idx_ts (ts),
    INDEX idx_module (module),
    INDEX idx_event_type (event_type),
    INDEX idx_module_path (module, path)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def ensure_table() -> None:
    """Create web_analytics table in maintenance_db if it doesn't exist."""
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=_MYSQL_HOST, port=_MYSQL_PORT,
            user=_MYSQL_USER, password=_MYSQL_PASSWORD,
            database=_ANALYTICS_DB,
        )
        cur = conn.cursor()
        cur.execute(_CREATE_TABLE_SQL)
        conn.commit()
        cur.close()
        conn.close()
        _log.info("web_analytics table ensured in %s", _ANALYTICS_DB)
    except Exception as exc:
        _log.debug("web_analytics table setup skipped: %s", exc)


def _log_to_mysql(module: str, event_type: str, **kwargs) -> None:
    """Fire-and-forget INSERT into maintenance_db.web_analytics."""
    def _insert():
        try:
            import mysql.connector
            conn = mysql.connector.connect(
                host=_MYSQL_HOST, port=_MYSQL_PORT,
                user=_MYSQL_USER, password=_MYSQL_PASSWORD,
                database=_ANALYTICS_DB, connect_timeout=3,
            )
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO web_analytics "
                "(module, event_type, path, method, status_code, duration_ms, "
                " error_type, error_message, action_name, success) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    module,
                    event_type,
                    kwargs.get("path", ""),
                    kwargs.get("method", ""),
                    kwargs.get("status_code", 0),
                    kwargs.get("duration_ms", 0),
                    kwargs.get("error_type", ""),
                    kwargs.get("error_message", ""),
                    kwargs.get("action_name", ""),
                    1 if kwargs.get("success", True) else 0,
                ),
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as exc:
            _log.debug("mysql analytics insert failed: %s", exc)
    threading.Thread(target=_insert, daemon=True).start()


# ── Public API ──────────────────────────────────────────────────────────────

def log_pageview(module: str = "", path: str = "", method: str = "GET",
                 status_code: int = 200, duration_ms: int = 0) -> None:
    REQUEST_COUNT.labels(module=module, method=method, path=path,
                         status=str(status_code)).inc()
    REQUEST_DURATION.labels(module=module, method=method,
                            path=path).observe(duration_ms / 1000)
    _log_to_mysql(module, "pageview", path=path, method=method,
                  status_code=status_code, duration_ms=duration_ms)


def log_error(module: str = "", message: str = "", severity: str = "error",
              error_type: str = "", path: str = "", stack_trace: str = "") -> None:
    ERROR_COUNT.labels(module=module, error_type=error_type).inc()
    _log_to_mysql(module, "error", path=path, error_type=error_type,
                  error_message=message[:4096])


def log_action(module: str = "", action_type: str = "", action_name: str = "",
               path: str = "", success: bool = True, duration_ms: int = 0) -> None:
    _log_to_mysql(module, "action", path=path, action_name=action_name,
                  success=success, duration_ms=duration_ms)


def metrics_response():
    """Generate Prometheus metrics response — call from a Flask route."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


def init_metrics(app, module: str = "") -> None:
    """Register Flask hooks for Prometheus metrics + MySQL logging."""
    from flask import request, g

    ensure_table()

    @app.route("/metrics")
    def prometheus_metrics():
        from flask import Response
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    @app.before_request
    def _start_timer():
        g._metrics_start = time.time()

    @app.after_request
    def _track_request(response):
        elapsed = int((time.time() - getattr(g, "_metrics_start", time.time())) * 1000)
        log_pageview(
            module=module,
            path=request.path,
            method=request.method,
            status_code=response.status_code,
            duration_ms=elapsed,
        )
        return response

    @app.errorhandler(Exception)
    def _handle_error(exc):
        log_error(
            module=module,
            message=str(exc),
            severity="error",
            error_type=type(exc).__name__,
            path=request.path,
            stack_trace=_tb.format_exc(),
        )
        return {"success": False, "error": "Internal server error"}, 500
