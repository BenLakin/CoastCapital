#!/bin/bash
# ─── Fix user passwords from env vars ────────────────────────────────────────
# 01-schemas.sql creates reporting & maintenance users with default passwords.
# This script overrides them with env-var values if set.
# ──────────────────────────────────────────────────────────────────────────────

REPORTING_PASS="${MYSQL_REPORTING_PASSWORD:-reporting_pass}"
MAINTENANCE_PASS="${MYSQL_MAINTENANCE_PASSWORD:-maintenance_pass}"
SOCK="${SOCKET:-/var/run/mysqld/mysqld.sock}"

export MYSQL_PWD="${MYSQL_ROOT_PASSWORD}"

mysql --protocol=socket -uroot -hlocalhost --socket="$SOCK" --comments \
  -e "ALTER USER 'reporting'@'%' IDENTIFIED BY '$REPORTING_PASS'; ALTER USER 'maintenance'@'%' IDENTIFIED BY '$MAINTENANCE_PASS'; FLUSH PRIVILEGES;"

echo "[init] reporting and maintenance user passwords set from environment."
