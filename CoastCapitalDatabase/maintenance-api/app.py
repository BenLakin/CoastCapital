"""
CoastCapital MySQL Maintenance API
Exposes HTTP endpoints that N8N can call to trigger database maintenance jobs.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

import mysql.connector
from fastapi import FastAPI, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

# ─── LOGGING ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/app/logs/maintenance-api.log"),
    ],
)
log = logging.getLogger("maintenance-api")

# ─── CONFIG ────────────────────────────────────────────────────────────────────
API_KEY        = os.environ["API_KEY"]
MYSQL_HOST     = os.getenv("MYSQL_HOST", "mysql")
MYSQL_PORT     = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER     = os.getenv("MYSQL_USER", "maintenance")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")

VALID_JOB_TYPES = {
    "optimize", "analyze", "check", "health",
    "slow_queries", "full", "flush", "recommendations", "report",
}

# ─── APP ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CoastCapital DB Maintenance API",
    description="Webhook-compatible API for triggering MySQL maintenance via N8N",
    version="1.0.0",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


def require_api_key(key: str = Security(api_key_header)) -> str:
    if key != API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return key


def get_db_connection() -> mysql.connector.MySQLConnection:
    return mysql.connector.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database="maintenance_db",
        connection_timeout=10,
    )


# ─── SCHEMAS ───────────────────────────────────────────────────────────────────
class MaintenanceRequest(BaseModel):
    job_type: str
    schema_name: str = "finance_silver"


class MaintenanceResponse(BaseModel):
    success: bool
    job_type: str
    schema_name: str
    started_at: str
    duration_ms: int
    message: str


class HealthResponse(BaseModel):
    status: str
    mysql_connected: bool
    timestamp: str


# ─── ENDPOINTS ─────────────────────────────────────────────────────────────────
@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    """Quick liveness check — also verifies MySQL connectivity."""
    mysql_ok = False
    try:
        conn = get_db_connection()
        conn.close()
        mysql_ok = True
    except Exception as exc:
        log.warning("MySQL health check failed: %s", exc)

    return HealthResponse(
        status="ok" if mysql_ok else "degraded",
        mysql_connected=mysql_ok,
        timestamp=datetime.now(timezone.utc).isoformat() + "Z",
    )


@app.post("/maintenance/run", response_model=MaintenanceResponse, tags=["Maintenance"])
def run_maintenance(
    req: MaintenanceRequest,
    _key: str = Security(require_api_key),
):
    """
    Trigger a maintenance job. Called by N8N HTTP node.

    job_type options:
    - optimize       → OPTIMIZE TABLE on all InnoDB tables
    - analyze        → ANALYZE TABLE to refresh statistics
    - check          → CHECK TABLE for corruption
    - health         → Capture table size / fragmentation snapshot
    - slow_queries   → Capture slow query digest from performance_schema
    - full           → All of the above in sequence
    - flush          → FLUSH STATUS + reset counters
    - recommendations → Generate tuning recommendations
    - report         → Summary report of last 24h
    """
    if req.job_type not in VALID_JOB_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid job_type '{req.job_type}'. Valid: {sorted(VALID_JOB_TYPES)}",
        )

    log.info("Running maintenance job: %s on schema: %s", req.job_type, req.schema_name)
    start_ms = int(time.time() * 1000)

    try:
        conn   = get_db_connection()
        cursor = conn.cursor()

        proc_map = {
            "optimize":        ("optimize_schema",              [req.schema_name]),
            "analyze":         ("analyze_schema",               [req.schema_name]),
            "check":           ("check_schema",                 [req.schema_name]),
            "health":          ("capture_table_health",         []),
            "slow_queries":    ("capture_slow_query_summary",   []),
            "full":            ("run_full_maintenance",         [req.schema_name]),
            "flush":           ("flush_status_and_caches",      []),
            "recommendations": ("generate_settings_recommendations", []),
        }

        if req.job_type == "report":
            # Return raw report data
            cursor.execute("""
                SELECT job_type, schema_name, table_name, status, duration_ms, created_at
                FROM maintenance_log
                WHERE created_at >= NOW() - INTERVAL 24 HOUR
                ORDER BY created_at DESC LIMIT 50
            """)
            rows = cursor.fetchall()
            message = f"Report: {len(rows)} maintenance entries in last 24h"
        else:
            proc_name, args = proc_map[req.job_type]
            cursor.callproc(proc_name, args)
            conn.commit()
            message = f"Procedure {proc_name} completed successfully"

        cursor.close()
        conn.close()

    except mysql.connector.Error as exc:
        log.error("MySQL error running %s: %s", req.job_type, exc)
        raise HTTPException(status_code=500, detail=f"MySQL error: {exc}")

    duration_ms = int(time.time() * 1000) - start_ms
    log.info("Job %s completed in %dms", req.job_type, duration_ms)

    return MaintenanceResponse(
        success=True,
        job_type=req.job_type,
        schema_name=req.schema_name,
        started_at=datetime.now(timezone.utc).isoformat() + "Z",
        duration_ms=duration_ms,
        message=message,
    )


@app.get("/maintenance/status", tags=["Maintenance"])
def maintenance_status(_key: str = Security(require_api_key)):
    """Return recent maintenance log entries."""
    try:
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT job_type, schema_name, table_name, status, duration_ms,
                   rows_affected, message, created_at
            FROM maintenance_log
            WHERE created_at >= NOW() - INTERVAL 7 DAY
            ORDER BY created_at DESC
            LIMIT 100
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        # Convert datetime objects for JSON serialisation
        for row in rows:
            if row.get("created_at"):
                row["created_at"] = str(row["created_at"])
        return {"success": True, "count": len(rows), "entries": rows}
    except mysql.connector.Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/maintenance/recommendations", tags=["Maintenance"])
def get_recommendations(_key: str = Security(require_api_key)):
    """Return pending tuning recommendations."""
    try:
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT setting_name, current_value, recommended_value,
                   reason, severity, evaluated_at
            FROM settings_recommendations
            WHERE applied = 0
            ORDER BY
              FIELD(severity,'critical','warning','info'),
              evaluated_at DESC
            LIMIT 50
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        for row in rows:
            if row.get("evaluated_at"):
                row["evaluated_at"] = str(row["evaluated_at"])
        return {"success": True, "count": len(rows), "recommendations": rows}
    except mysql.connector.Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/maintenance/health-snapshot", tags=["Maintenance"])
def get_health_snapshot(_key: str = Security(require_api_key)):
    """Return the latest table health snapshot."""
    try:
        conn   = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT schema_name, table_name, engine, row_count,
                   data_length_mb, index_length_mb, data_free_mb,
                   fragmentation_pct, captured_at
            FROM table_health_snapshot
            WHERE captured_at = (SELECT MAX(captured_at) FROM table_health_snapshot)
            ORDER BY fragmentation_pct DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        for row in rows:
            if row.get("captured_at"):
                row["captured_at"] = str(row["captured_at"])
            for k in ("data_length_mb", "index_length_mb", "data_free_mb", "fragmentation_pct"):
                if row.get(k) is not None:
                    row[k] = float(row[k])
        return {"success": True, "count": len(rows), "snapshot": rows}
    except mysql.connector.Error as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8080, reload=False)
