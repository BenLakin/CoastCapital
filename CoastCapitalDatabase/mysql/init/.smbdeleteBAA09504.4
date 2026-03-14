-- ═══════════════════════════════════════════════════════════════════════════════
-- Maintenance Stored Procedures & Events
-- ═══════════════════════════════════════════════════════════════════════════════

USE maintenance_db;
DELIMITER $$

-- ─── HELPER: LOG MAINTENANCE ENTRY ─────────────────────────────────────────────
CREATE PROCEDURE IF NOT EXISTS log_maintenance_start(
  IN  p_run_id      CHAR(36),
  IN  p_job_type    VARCHAR(64),
  IN  p_schema      VARCHAR(64),
  IN  p_table       VARCHAR(128)
)
BEGIN
  INSERT INTO maintenance_log (run_id, job_type, schema_name, table_name, status)
  VALUES (p_run_id, p_job_type, p_schema, p_table, 'started');
END$$

CREATE PROCEDURE IF NOT EXISTS log_maintenance_end(
  IN p_run_id    CHAR(36),
  IN p_status    VARCHAR(16),
  IN p_rows      BIGINT,
  IN p_duration  INT,
  IN p_message   TEXT
)
BEGIN
  UPDATE maintenance_log
  SET status       = p_status,
      rows_affected = p_rows,
      duration_ms  = p_duration,
      message      = p_message
  WHERE run_id = p_run_id;
END$$

-- ─── PROCEDURE: OPTIMIZE ALL TABLES IN A SCHEMA ────────────────────────────────
DROP PROCEDURE IF EXISTS optimize_schema$$
CREATE PROCEDURE optimize_schema(IN p_schema_name VARCHAR(64))
BEGIN
  DECLARE done        INT DEFAULT FALSE;
  DECLARE v_table     VARCHAR(128);
  DECLARE v_run_id    CHAR(36) DEFAULT UUID();
  DECLARE v_start     BIGINT;
  DECLARE v_sql       TEXT;
  DECLARE v_err       TEXT DEFAULT NULL;

  DECLARE cur CURSOR FOR
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = p_schema_name
      AND table_type   = 'BASE TABLE'
      AND engine       = 'InnoDB';

  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
  BEGIN
    GET DIAGNOSTICS CONDITION 1 v_err = MESSAGE_TEXT;
  END;

  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO v_table;
    IF done THEN LEAVE read_loop; END IF;

    SET v_run_id  = UUID();
    SET v_start   = UNIX_TIMESTAMP(NOW(3)) * 1000;
    SET v_err     = NULL;

    CALL log_maintenance_start(v_run_id, 'OPTIMIZE', p_schema_name, v_table);

    SET v_sql = CONCAT('OPTIMIZE TABLE `', p_schema_name, '`.`', v_table, '`');
    SET @sql  = v_sql;
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    CALL log_maintenance_end(
      v_run_id,
      IF(v_err IS NULL, 'completed', 'failed'),
      ROW_COUNT(),
      CAST(UNIX_TIMESTAMP(NOW(3)) * 1000 - v_start AS SIGNED),
      v_err
    );
  END LOOP;
  CLOSE cur;
END$$

-- ─── PROCEDURE: ANALYZE ALL TABLES IN A SCHEMA ─────────────────────────────────
DROP PROCEDURE IF EXISTS analyze_schema$$
CREATE PROCEDURE analyze_schema(IN p_schema_name VARCHAR(64))
BEGIN
  DECLARE done     INT DEFAULT FALSE;
  DECLARE v_table  VARCHAR(128);
  DECLARE v_run_id CHAR(36);
  DECLARE v_start  BIGINT;
  DECLARE v_err    TEXT DEFAULT NULL;

  DECLARE cur CURSOR FOR
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = p_schema_name
      AND table_type   = 'BASE TABLE';

  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
  BEGIN
    GET DIAGNOSTICS CONDITION 1 v_err = MESSAGE_TEXT;
  END;

  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO v_table;
    IF done THEN LEAVE read_loop; END IF;

    SET v_run_id  = UUID();
    SET v_start   = UNIX_TIMESTAMP(NOW(3)) * 1000;
    SET v_err     = NULL;

    CALL log_maintenance_start(v_run_id, 'ANALYZE', p_schema_name, v_table);

    SET @sql = CONCAT('ANALYZE TABLE `', p_schema_name, '`.`', v_table, '`');
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    CALL log_maintenance_end(
      v_run_id,
      IF(v_err IS NULL, 'completed', 'failed'),
      ROW_COUNT(),
      CAST(UNIX_TIMESTAMP(NOW(3)) * 1000 - v_start AS SIGNED),
      v_err
    );
  END LOOP;
  CLOSE cur;
END$$

-- ─── PROCEDURE: CHECK ALL TABLES IN A SCHEMA ───────────────────────────────────
DROP PROCEDURE IF EXISTS check_schema$$
CREATE PROCEDURE check_schema(IN p_schema_name VARCHAR(64))
BEGIN
  DECLARE done     INT DEFAULT FALSE;
  DECLARE v_table  VARCHAR(128);
  DECLARE v_run_id CHAR(36);
  DECLARE v_start  BIGINT;
  DECLARE v_err    TEXT DEFAULT NULL;

  DECLARE cur CURSOR FOR
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = p_schema_name
      AND table_type   = 'BASE TABLE';

  DECLARE CONTINUE HANDLER FOR NOT FOUND SET done = TRUE;
  DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
  BEGIN
    GET DIAGNOSTICS CONDITION 1 v_err = MESSAGE_TEXT;
  END;

  OPEN cur;
  read_loop: LOOP
    FETCH cur INTO v_table;
    IF done THEN LEAVE read_loop; END IF;

    SET v_run_id  = UUID();
    SET v_start   = UNIX_TIMESTAMP(NOW(3)) * 1000;
    SET v_err     = NULL;

    CALL log_maintenance_start(v_run_id, 'CHECK', p_schema_name, v_table);

    SET @sql = CONCAT('CHECK TABLE `', p_schema_name, '`.`', v_table, '` EXTENDED');
    PREPARE stmt FROM @sql;
    EXECUTE stmt;
    DEALLOCATE PREPARE stmt;

    CALL log_maintenance_end(
      v_run_id,
      IF(v_err IS NULL, 'completed', 'failed'),
      ROW_COUNT(),
      CAST(UNIX_TIMESTAMP(NOW(3)) * 1000 - v_start AS SIGNED),
      v_err
    );
  END LOOP;
  CLOSE cur;
END$$

-- ─── PROCEDURE: CAPTURE TABLE HEALTH SNAPSHOT ──────────────────────────────────
DROP PROCEDURE IF EXISTS capture_table_health$$
CREATE PROCEDURE capture_table_health()
BEGIN
  INSERT INTO table_health_snapshot
    (schema_name, table_name, engine, row_count,
     data_length_mb, index_length_mb, data_free_mb, fragmentation_pct)
  SELECT
    t.table_schema,
    t.table_name,
    t.engine,
    t.table_rows,
    ROUND(t.data_length  / 1024 / 1024, 2),
    ROUND(t.index_length / 1024 / 1024, 2),
    ROUND(t.data_free    / 1024 / 1024, 2),
    CASE
      WHEN (t.data_length + t.index_length) = 0 THEN 0
      ELSE ROUND(t.data_free / (t.data_length + t.index_length) * 100, 2)
    END
  FROM information_schema.tables t
  WHERE t.table_schema NOT IN ('information_schema','performance_schema','mysql','sys')
    AND t.table_type = 'BASE TABLE';
END$$

-- ─── PROCEDURE: CAPTURE SLOW QUERY SUMMARY ────────────────────────────────────
DROP PROCEDURE IF EXISTS capture_slow_query_summary$$
CREATE PROCEDURE capture_slow_query_summary()
BEGIN
  INSERT INTO slow_query_summary
    (query_digest, exec_count, avg_time_sec, max_time_sec, total_time_sec, schema_name)
  SELECT
    DIGEST_TEXT,
    COUNT_STAR,
    ROUND(AVG_TIMER_WAIT / 1000000000000, 4),
    ROUND(MAX_TIMER_WAIT / 1000000000000, 4),
    ROUND(SUM_TIMER_WAIT / 1000000000000, 4),
    SCHEMA_NAME
  FROM performance_schema.events_statements_summary_by_digest
  WHERE AVG_TIMER_WAIT > 1000000000000  -- > 1 second average
    AND SCHEMA_NAME NOT IN ('mysql','sys','performance_schema','information_schema')
  ORDER BY AVG_TIMER_WAIT DESC
  LIMIT 50;
END$$

-- ─── PROCEDURE: GENERATE SETTINGS RECOMMENDATIONS ─────────────────────────────
DROP PROCEDURE IF EXISTS generate_settings_recommendations$$
CREATE PROCEDURE generate_settings_recommendations()
BEGIN
  DECLARE v_buffer_pool_size   BIGINT;
  DECLARE v_total_ram          BIGINT;
  DECLARE v_connections        INT;
  DECLARE v_max_connections    INT;
  DECLARE v_uptime             INT;

  -- Clear previous recommendations
  DELETE FROM settings_recommendations WHERE applied = 0;

  -- Check InnoDB buffer pool vs data size
  SELECT variable_value INTO v_buffer_pool_size
  FROM performance_schema.global_variables
  WHERE variable_name = 'innodb_buffer_pool_size';

  SELECT variable_value INTO v_max_connections
  FROM performance_schema.global_variables
  WHERE variable_name = 'max_connections';

  SELECT variable_value INTO v_connections
  FROM performance_schema.global_status
  WHERE variable_name = 'Max_used_connections';

  SELECT variable_value INTO v_uptime
  FROM performance_schema.global_status
  WHERE variable_name = 'Uptime';

  -- Recommend increasing max_connections if hitting 80% of max
  IF v_connections >= v_max_connections * 0.80 THEN
    INSERT INTO settings_recommendations
      (setting_name, current_value, recommended_value, reason, severity)
    VALUES (
      'max_connections',
      v_max_connections,
      GREATEST(v_max_connections * 1.5, 500),
      CONCAT('Peak connections (', v_connections, ') reached 80%+ of max_connections (', v_max_connections, ')'),
      'warning'
    );
  END IF;

  -- Flag tables with high fragmentation
  INSERT INTO settings_recommendations
    (setting_name, current_value, recommended_value, reason, severity)
  SELECT
    CONCAT('table.', schema_name, '.', table_name),
    CONCAT(fragmentation_pct, '% fragmented'),
    'Run OPTIMIZE TABLE',
    CONCAT('Table ', schema_name, '.', table_name, ' has ', fragmentation_pct, '% fragmentation (', data_free_mb, 'MB free space)'),
    IF(fragmentation_pct > 30, 'critical', 'warning')
  FROM table_health_snapshot
  WHERE captured_at >= NOW() - INTERVAL 1 HOUR
    AND fragmentation_pct > 15
  ORDER BY fragmentation_pct DESC
  LIMIT 20;
END$$

-- ─── PROCEDURE: FULL MAINTENANCE RUN ───────────────────────────────────────────
DROP PROCEDURE IF EXISTS run_full_maintenance$$
CREATE PROCEDURE run_full_maintenance(IN p_schema_name VARCHAR(64))
BEGIN
  CALL capture_table_health();
  CALL analyze_schema(p_schema_name);
  CALL optimize_schema(p_schema_name);
  CALL capture_slow_query_summary();
  CALL generate_settings_recommendations();
END$$

-- ─── PROCEDURE: FLUSH & RESET STATUS COUNTERS ─────────────────────────────────
DROP PROCEDURE IF EXISTS flush_status_and_caches$$
CREATE PROCEDURE flush_status_and_caches()
BEGIN
  FLUSH STATUS;
  -- Note: FLUSH TABLES is intentionally NOT called here to avoid disrupting connections
  SET GLOBAL innodb_stats_auto_recalc = ON;
END$$

DELIMITER ;

-- ─── SCHEDULED EVENT: NIGHTLY HEALTH CAPTURE ──────────────────────────────────
-- Note: event_scheduler must be ON. Set via SET GLOBAL event_scheduler = ON;
SET GLOBAL event_scheduler = ON;

DROP EVENT IF EXISTS evt_nightly_health_capture;
CREATE EVENT evt_nightly_health_capture
  ON SCHEDULE EVERY 1 DAY
  STARTS (TIMESTAMP(CURDATE()) + INTERVAL 1 DAY + INTERVAL '02:00' HOUR_MINUTE)
  ON COMPLETION PRESERVE
  ENABLE
  COMMENT 'Nightly table health and slow query snapshot'
  DO
    BEGIN
      CALL capture_table_health();
      CALL capture_slow_query_summary();
      CALL generate_settings_recommendations();
    END;

-- Purge old maintenance logs > 90 days
DROP EVENT IF EXISTS evt_purge_old_logs;
CREATE EVENT evt_purge_old_logs
  ON SCHEDULE EVERY 1 WEEK
  STARTS (TIMESTAMP(CURDATE()) + INTERVAL 1 DAY + INTERVAL '03:00' HOUR_MINUTE)
  ON COMPLETION PRESERVE
  ENABLE
  DO
    BEGIN
      DELETE FROM maintenance_log      WHERE created_at < NOW() - INTERVAL 90 DAY;
      DELETE FROM table_health_snapshot WHERE captured_at < NOW() - INTERVAL 90 DAY;
      DELETE FROM slow_query_summary   WHERE captured_at < NOW() - INTERVAL 90 DAY;
      DELETE FROM settings_recommendations WHERE evaluated_at < NOW() - INTERVAL 30 DAY AND applied = 1;
    END;
