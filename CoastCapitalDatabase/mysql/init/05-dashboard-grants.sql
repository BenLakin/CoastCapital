-- ═══════════════════════════════════════════════════════════════════════════════
-- Dashboard Grants — reporting user read access to maintenance_db
-- ═══════════════════════════════════════════════════════════════════════════════

GRANT SELECT ON `maintenance_db`.* TO 'reporting'@'%';

FLUSH PRIVILEGES;
