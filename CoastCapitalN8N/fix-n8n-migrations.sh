#!/bin/bash
# Fix known N8N MySQL migration bugs (n8n-io/n8n#12836)
# Run this after a fresh n8n_db is created and N8N fails on migrations.
# Usage: ./fix-n8n-migrations.sh

set -e

MYSQL_CONTAINER="coastcapital-mysql"
N8N_CONTAINER="coastcapital-n8n"
DB="n8n_db"

echo "=== Fix 1: test_definition primary key ==="
echo "Waiting for test_definition table to exist..."
for i in $(seq 1 30); do
  EXISTS=$(docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -sNe \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB' AND table_name='test_definition';\"" 2>/dev/null)
  if [ "$EXISTS" = "1" ]; then break; fi
  sleep 2
done

# Check if tmp_id still exists (meaning migration left it broken)
HAS_TMP=$(docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -sNe \"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='$DB' AND table_name='test_definition' AND column_name='tmp_id';\"" 2>/dev/null)

if [ "$HAS_TMP" = "1" ]; then
  echo "Fixing test_definition: making 'id' the primary key, dropping 'tmp_id'..."
  docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -e \"
    ALTER TABLE test_definition MODIFY tmp_id int NOT NULL;
    ALTER TABLE test_definition DROP PRIMARY KEY, ADD PRIMARY KEY (id);
    ALTER TABLE test_definition DROP COLUMN tmp_id;
    ALTER TABLE test_definition DROP INDEX TMP_idx_test_definition_id;
  \"" 2>&1 | grep -v Warning
  echo "Fix 1 applied. Restarting N8N..."
  docker restart "$N8N_CONTAINER"
  sleep 20
else
  echo "Fix 1 not needed (tmp_id already gone)."
fi

echo ""
echo "=== Fix 2: AddStatsColumnsToTestRun (CHECK constraint bug) ==="
echo "Waiting for test_run table to exist..."
for i in $(seq 1 30); do
  EXISTS=$(docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -sNe \"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB' AND table_name='test_run';\"" 2>/dev/null)
  if [ "$EXISTS" = "1" ]; then break; fi
  sleep 2
done

# Check if the migration was already applied
ALREADY_DONE=$(docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -sNe \"SELECT COUNT(*) FROM migrations WHERE name='AddStatsColumnsToTestRun1736172058779';\"" 2>/dev/null)

if [ "$ALREADY_DONE" = "1" ]; then
  echo "Fix 2 not needed (migration already recorded)."
else
  # Check if columns already exist
  HAS_COL=$(docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -sNe \"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema='$DB' AND table_name='test_run' AND column_name='totalCases';\"" 2>/dev/null)

  if [ "$HAS_COL" = "0" ]; then
    echo "Adding stats columns without CHECK constraints..."
    docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -e \"
      ALTER TABLE test_run ADD COLUMN totalCases INT DEFAULT NULL;
      ALTER TABLE test_run ADD COLUMN passedCases INT DEFAULT NULL;
      ALTER TABLE test_run ADD COLUMN failedCases INT DEFAULT NULL;
    \"" 2>&1 | grep -v Warning
  fi

  echo "Recording migration as complete..."
  docker exec "$MYSQL_CONTAINER" sh -c "mysql --no-defaults -uroot -p\"\$MYSQL_ROOT_PASSWORD\" $DB -e \"
    INSERT INTO migrations (timestamp, name) VALUES (1736172058779, 'AddStatsColumnsToTestRun1736172058779');
  \"" 2>&1 | grep -v Warning

  echo "Fix 2 applied. Restarting N8N..."
  docker restart "$N8N_CONTAINER"
  sleep 15
fi

echo ""
echo "=== Checking N8N status ==="
docker ps --format "{{.Names}}\t{{.Status}}" | grep n8n
echo ""
docker logs "$N8N_CONTAINER" 2>&1 | tail -10
