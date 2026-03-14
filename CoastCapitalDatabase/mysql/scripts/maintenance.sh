#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# maintenance.sh — Entrypoint called by the maintenance-api container or N8N
# Usage: maintenance.sh <job_type> [schema_name]
#   job_types: optimize | analyze | check | health | slow_queries | full | flush | recommendations
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

JOB_TYPE="${1:-health}"
SCHEMA="${2:-coastcapital}"

MYSQL_HOST="${MYSQL_HOST:-mysql}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_ROOT_PASSWORD:-}"
LOG_DIR="${LOG_DIR:-/tmp/maintenance-logs}"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="$LOG_DIR/${JOB_TYPE}_${TIMESTAMP}.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

mysql_exec() {
  mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" \
        -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
        --batch --silent "$@"
}

log "Starting maintenance job: $JOB_TYPE (schema: $SCHEMA)"

case "$JOB_TYPE" in
  optimize)
    log "Running OPTIMIZE on schema: $SCHEMA"
    mysql_exec -e "CALL maintenance_db.optimize_schema('$SCHEMA');"
    ;;
  analyze)
    log "Running ANALYZE on schema: $SCHEMA"
    mysql_exec -e "CALL maintenance_db.analyze_schema('$SCHEMA');"
    ;;
  check)
    log "Running CHECK on schema: $SCHEMA"
    mysql_exec -e "CALL maintenance_db.check_schema('$SCHEMA');"
    ;;
  health)
    log "Capturing table health snapshot"
    mysql_exec -e "CALL maintenance_db.capture_table_health();"
    ;;
  slow_queries)
    log "Capturing slow query summary"
    mysql_exec -e "CALL maintenance_db.capture_slow_query_summary();"
    ;;
  full)
    log "Running full maintenance on schema: $SCHEMA"
    mysql_exec -e "CALL maintenance_db.run_full_maintenance('$SCHEMA');"
    ;;
  flush)
    log "Flushing status and resetting counters"
    mysql_exec -e "CALL maintenance_db.flush_status_and_caches();"
    ;;
  recommendations)
    log "Generating settings recommendations"
    mysql_exec -e "CALL maintenance_db.generate_settings_recommendations();"
    # Output recommendations as JSON for N8N consumption
    mysql_exec --vertical maintenance_db -e \
      "SELECT setting_name, current_value, recommended_value, reason, severity
       FROM settings_recommendations WHERE applied = 0 ORDER BY severity DESC;"
    ;;
  report)
    log "Generating maintenance summary report"
    mysql_exec maintenance_db -e "
      SELECT 'Recent Maintenance Runs' AS section;
      SELECT job_type, schema_name, table_name, status, duration_ms, created_at
      FROM maintenance_log
      WHERE created_at >= NOW() - INTERVAL 24 HOUR
      ORDER BY created_at DESC LIMIT 50;

      SELECT '--- Most Fragmented Tables ---' AS section;
      SELECT schema_name, table_name, fragmentation_pct, data_free_mb, data_length_mb
      FROM table_health_snapshot
      WHERE captured_at >= NOW() - INTERVAL 25 HOUR
        AND fragmentation_pct > 10
      ORDER BY fragmentation_pct DESC LIMIT 20;

      SELECT '--- Slow Query Summary ---' AS section;
      SELECT query_digest, exec_count, avg_time_sec, max_time_sec
      FROM slow_query_summary
      WHERE captured_at >= NOW() - INTERVAL 25 HOUR
      ORDER BY avg_time_sec DESC LIMIT 20;
    "
    ;;
  *)
    log "ERROR: Unknown job type '$JOB_TYPE'"
    log "Valid types: optimize | analyze | check | health | slow_queries | full | flush | recommendations | report"
    exit 1
    ;;
esac

log "Maintenance job '$JOB_TYPE' completed successfully."
exit 0
