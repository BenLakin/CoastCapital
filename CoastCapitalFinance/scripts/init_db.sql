-- =============================================================
-- Coast Capital Finance Platform — MySQL Initialization
-- Creates the finance_silver schema and sets permissions
-- =============================================================

CREATE DATABASE IF NOT EXISTS finance_silver
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE finance_silver;

-- Grant privileges to application user
GRANT ALL PRIVILEGES ON finance_silver.* TO 'finance_user'@'%';
FLUSH PRIVILEGES;

-- The SQLAlchemy models will create tables via Base.metadata.create_all()
-- This file only handles schema creation and permissions.

-- Optional: Create a read-only reporting user for dashboards
-- CREATE USER IF NOT EXISTS 'finance_reader'@'%' IDENTIFIED BY 'readonly_password';
-- GRANT SELECT ON finance_silver.* TO 'finance_reader'@'%';
-- FLUSH PRIVILEGES;
