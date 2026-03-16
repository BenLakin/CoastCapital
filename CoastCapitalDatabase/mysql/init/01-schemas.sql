-- ═══════════════════════════════════════════════════════════════════════════════
-- CoastCapital Multi-Schema Initialization
-- ═══════════════════════════════════════════════════════════════════════════════

SET NAMES utf8mb4;
SET character_set_client = utf8mb4;

-- ─── CREATE SCHEMAS ────────────────────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS `n8n_db`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `maintenance_db`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── FINANCE DATABASES ──────────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS `finance_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `finance_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `finance_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── HOMELAB DATABASES ─────────────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS `homelab_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `homelab_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `homelab_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── ASSISTANT DATABASES ───────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS `assistant_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `assistant_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `assistant_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── SPORTS DATABASES (NFL — active) ───────────────────────────────────
CREATE DATABASE IF NOT EXISTS `nfl_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `nfl_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `nfl_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── SPORTS DATABASES (NCAA MBB — active) ────────────────────────────
CREATE DATABASE IF NOT EXISTS `ncaa_mbb_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `ncaa_mbb_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `ncaa_mbb_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── SPORTS CROSS-CUTTING (modeling / ML features) ────────────────────
CREATE DATABASE IF NOT EXISTS `modeling_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `modeling_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── SPORTS DATABASES (Future sports — placeholder) ───────────────────
CREATE DATABASE IF NOT EXISTS `nba_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `nba_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `nba_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `mlb_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `mlb_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `mlb_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS `nhl_silver`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `nhl_internal`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE DATABASE IF NOT EXISTS `nhl_gold`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- ─── USERS ─────────────────────────────────────────────────────────────────────
-- App user: full access to application schemas
CREATE USER IF NOT EXISTS 'dbadmin'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}';

-- Read-only reporting user
CREATE USER IF NOT EXISTS 'reporting'@'%' IDENTIFIED BY 'reporting_pass';

-- Maintenance user: needs broader access for OPTIMIZE/ANALYZE
CREATE USER IF NOT EXISTS 'maintenance'@'%' IDENTIFIED BY 'maintenance_pass';

-- ─── GRANT PRIVILEGES ──────────────────────────────────────────────────────────
GRANT ALL PRIVILEGES ON `n8n_db`.*       TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `maintenance_db`.* TO 'dbadmin'@'%';

-- Finance
GRANT ALL PRIVILEGES ON `finance_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `finance_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `finance_gold`.*      TO 'dbadmin'@'%';

-- HomeLab
GRANT ALL PRIVILEGES ON `homelab_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `homelab_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `homelab_gold`.*      TO 'dbadmin'@'%';

-- Assistant
GRANT ALL PRIVILEGES ON `assistant_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `assistant_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `assistant_gold`.*      TO 'dbadmin'@'%';

-- Sports (NFL — active)
GRANT ALL PRIVILEGES ON `nfl_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `nfl_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `nfl_gold`.*      TO 'dbadmin'@'%';

-- Sports (NCAA MBB)
GRANT ALL PRIVILEGES ON `ncaa_mbb_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `ncaa_mbb_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `ncaa_mbb_gold`.*      TO 'dbadmin'@'%';

-- Sports (Modeling / ML)
GRANT ALL PRIVILEGES ON `modeling_silver`.*    TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `modeling_internal`.*  TO 'dbadmin'@'%';

-- Sports (Future — placeholder grants)
GRANT ALL PRIVILEGES ON `nba_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `nba_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `nba_gold`.*      TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `mlb_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `mlb_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `mlb_gold`.*      TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `nhl_silver`.*   TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `nhl_internal`.*  TO 'dbadmin'@'%';
GRANT ALL PRIVILEGES ON `nhl_gold`.*      TO 'dbadmin'@'%';

-- Reporting: read-only across all domains
GRANT SELECT ON `finance_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `finance_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `finance_gold`.*      TO 'reporting'@'%';

GRANT SELECT ON `homelab_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `homelab_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `homelab_gold`.*      TO 'reporting'@'%';

GRANT SELECT ON `assistant_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `assistant_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `assistant_gold`.*      TO 'reporting'@'%';

GRANT SELECT ON `nfl_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `nfl_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `nfl_gold`.*      TO 'reporting'@'%';

GRANT SELECT ON `ncaa_mbb_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `ncaa_mbb_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `ncaa_mbb_gold`.*      TO 'reporting'@'%';
GRANT SELECT ON `modeling_silver`.*    TO 'reporting'@'%';
GRANT SELECT ON `modeling_internal`.*  TO 'reporting'@'%';

GRANT SELECT ON `nba_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `nba_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `nba_gold`.*      TO 'reporting'@'%';
GRANT SELECT ON `mlb_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `mlb_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `mlb_gold`.*      TO 'reporting'@'%';
GRANT SELECT ON `nhl_silver`.*   TO 'reporting'@'%';
GRANT SELECT ON `nhl_internal`.*  TO 'reporting'@'%';
GRANT SELECT ON `nhl_gold`.*      TO 'reporting'@'%';

-- Maintenance: operational access across all domains
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `finance_silver`.*   TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `finance_internal`.*  TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `finance_gold`.*      TO 'maintenance'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `homelab_silver`.*   TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `homelab_internal`.*  TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `homelab_gold`.*      TO 'maintenance'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `assistant_silver`.*   TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `assistant_internal`.*  TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `assistant_gold`.*      TO 'maintenance'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `nfl_silver`.*   TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `nfl_internal`.*  TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `nfl_gold`.*      TO 'maintenance'@'%';

GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `ncaa_mbb_silver`.*   TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `ncaa_mbb_internal`.*  TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `ncaa_mbb_gold`.*      TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `modeling_silver`.*   TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `modeling_internal`.*  TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `mlb_silver`.*   TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `mlb_internal`.*  TO 'maintenance'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER,
      EXECUTE, REFERENCES, TRIGGER
  ON `mlb_gold`.*      TO 'maintenance'@'%';

GRANT ALL PRIVILEGES ON `maintenance_db`.* TO 'maintenance'@'%';
GRANT RELOAD, PROCESS, SHOW DATABASES, SUPER ON *.* TO 'maintenance'@'%';

FLUSH PRIVILEGES;


-- ═══════════════════════════════════════════════════════════════════════════════
-- NCAA MBB — Reference Tables (static lookup data)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `ncaa_mbb_silver`;

-- Historical NCAA tournament win rates by seed (1985-2024)
CREATE TABLE IF NOT EXISTS `fact_seed_history` (
  `seed`            TINYINT UNSIGNED NOT NULL PRIMARY KEY,
  `win_pct`         DECIMAL(5,4) NOT NULL COMMENT 'Overall tournament win percentage',
  `upset_win_pct`   DECIMAL(5,4) NOT NULL COMMENT 'Win pct when lower seed (upset wins)'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO `fact_seed_history` (seed, win_pct, upset_win_pct) VALUES
  ( 1, 0.8500, 0.0000),
  ( 2, 0.7200, 0.5200),
  ( 3, 0.6400, 0.4600),
  ( 4, 0.5800, 0.4100),
  ( 5, 0.4700, 0.3500),
  ( 6, 0.4400, 0.3700),
  ( 7, 0.3900, 0.3600),
  ( 8, 0.3600, 0.4900),
  ( 9, 0.3400, 0.5100),
  (10, 0.3500, 0.6300),
  (11, 0.3400, 0.6100),
  (12, 0.3500, 0.6500),
  (13, 0.2100, 0.7900),
  (14, 0.1500, 0.8500),
  (15, 0.0700, 0.9300),
  (16, 0.0100, 0.9900)
ON DUPLICATE KEY UPDATE
  win_pct = VALUES(win_pct),
  upset_win_pct = VALUES(upset_win_pct);


-- ═══════════════════════════════════════════════════════════════════════════════
-- NFL — Silver Layer (Sports module tables)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `nfl_silver`;

CREATE TABLE IF NOT EXISTS `fact_game_results` (
  `id`                     INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`                VARCHAR(50) NOT NULL,
  `game_date`              DATETIME,
  `home_team`              VARCHAR(100),
  `away_team`              VARCHAR(100),
  `home_score`             INT,
  `away_score`             INT,
  `margin`                 INT,
  `is_postseason_game`     TINYINT DEFAULT 0,
  `round_name`             VARCHAR(100),
  `playoff_experience_home` DOUBLE DEFAULT 0,
  `playoff_experience_away` DOUBLE DEFAULT 0,
  `updated_at`             TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_game_results_game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_market_odds` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`           VARCHAR(50) NOT NULL,
  `sportsbook`        VARCHAR(100),
  `spread`            DECIMAL(6,2),
  `moneyline_home`    INT,
  `moneyline_away`    INT,
  `total_line`        DECIMAL(6,2),
  `market_timestamp`  DATETIME,
  INDEX `idx_market_odds_game_id` (`game_id`),
  INDEX `idx_market_odds_timestamp` (`market_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_game_context` (
  `id`           INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`      VARCHAR(50) NOT NULL,
  `week_number`  INT,
  `season`       INT,
  `venue_name`   VARCHAR(150),
  `venue_city`   VARCHAR(100),
  `surface`      ENUM('grass','turf'),
  `indoor`       TINYINT DEFAULT 0,
  `attendance`   INT,
  `updated_at`   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_game_context_game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_team_game_stats` (
  `id`                     INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`                VARCHAR(50) NOT NULL,
  `team`                   VARCHAR(100) NOT NULL,
  `side`                   ENUM('home','away') NOT NULL,
  `total_yards`            INT,
  `passing_yards`          INT,
  `rushing_yards`          INT,
  `turnovers`              INT,
  `third_down_att`         INT,
  `third_down_conv`        INT,
  `red_zone_att`           INT,
  `red_zone_conv`          INT,
  `time_of_possession_secs` INT,
  `sacks_allowed`          INT,
  `penalty_yards`          INT,
  `updated_at`             TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_team_game_stats` (`game_id`, `team`),
  INDEX `idx_team_game_stats_team` (`team`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_team_standing` (
  `id`             INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`        VARCHAR(50) NOT NULL,
  `team`           VARCHAR(100) NOT NULL,
  `side`           ENUM('home','away') NOT NULL,
  `season`         INT,
  `week`           INT,
  `wins`           INT,
  `losses`         INT,
  `win_pct`        DOUBLE,
  `home_wins`      INT,
  `home_losses`    INT,
  `away_wins`      INT,
  `away_losses`    INT,
  `current_streak` INT,
  `updated_at`     TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_team_standing` (`game_id`, `team`),
  INDEX `idx_team_standing_team` (`team`, `season`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_game_weather` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`           VARCHAR(50) NOT NULL,
  `temperature_f`     DECIMAL(5,1),
  `wind_speed_mph`    DECIMAL(5,1),
  `wind_direction`    VARCHAR(20),
  `precipitation_in`  DECIMAL(5,2),
  `humidity_pct`      INT,
  `conditions`        VARCHAR(50),
  UNIQUE KEY `uq_game_weather_game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- NCAA MBB — Silver Layer (Sports module tables)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `ncaa_mbb_silver`;

CREATE TABLE IF NOT EXISTS `fact_game_results` (
  `id`                  INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`             VARCHAR(50) NOT NULL,
  `game_date`           DATETIME,
  `home_team`           VARCHAR(100),
  `away_team`           VARCHAR(100),
  `home_score`          INT,
  `away_score`          INT,
  `margin`              INT,
  `is_tournament_game`  TINYINT DEFAULT 0,
  `round_name`          VARCHAR(100),
  `seed_home`           INT,
  `seed_away`           INT,
  `updated_at`          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_game_results_game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_market_odds` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`           VARCHAR(50) NOT NULL,
  `sportsbook`        VARCHAR(100),
  `spread`            DECIMAL(6,2),
  `moneyline_home`    INT,
  `moneyline_away`    INT,
  `total_line`        DECIMAL(6,2),
  `market_timestamp`  DATETIME,
  INDEX `idx_market_odds_game_id` (`game_id`),
  INDEX `idx_market_odds_timestamp` (`market_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_mbb_game_context` (
  `id`                  INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`             VARCHAR(50) NOT NULL,
  `neutral_site`        TINYINT DEFAULT 0,
  `is_conference_game`  TINYINT DEFAULT 0,
  `venue_name`          VARCHAR(150),
  `venue_city`          VARCHAR(100),
  `attendance`          INT,
  `season`              INT,
  `updated_at`          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_mbb_game_context_game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_mbb_game_stats` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`           VARCHAR(50) NOT NULL,
  `team`              VARCHAR(100) NOT NULL,
  `side`              ENUM('home','away') NOT NULL,
  `fg_made`           INT,
  `fg_att`            INT,
  `fg_pct`            FLOAT,
  `three_pt_made`     INT,
  `three_pt_att`      INT,
  `three_pt_pct`      FLOAT,
  `ft_made`           INT,
  `ft_att`            INT,
  `ft_pct`            FLOAT,
  `total_rebounds`    INT,
  `off_rebounds`      INT,
  `def_rebounds`      INT,
  `assists`           INT,
  `steals`            INT,
  `blocks`            INT,
  `turnovers`         INT,
  `turnover_points`   INT,
  `fast_break_points` INT,
  `points_in_paint`   INT,
  `largest_lead`      INT,
  `fouls`             INT,
  `updated_at`        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_mbb_game_stats` (`game_id`, `side`),
  INDEX `idx_mbb_game_stats_team` (`team`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_mbb_team_standing` (
  `id`           INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`      VARCHAR(50) NOT NULL,
  `team`         VARCHAR(100) NOT NULL,
  `side`         ENUM('home','away') NOT NULL,
  `wins`         INT,
  `losses`       INT,
  `win_pct`      DOUBLE,
  `home_wins`    INT,
  `home_losses`  INT,
  `road_wins`    INT,
  `road_losses`  INT,
  `conf_wins`    INT,
  `conf_losses`  INT,
  `updated_at`   TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_mbb_team_standing` (`game_id`, `side`),
  INDEX `idx_mbb_team_standing_team` (`team`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_mbb_poll_ranking` (
  `id`                 INT AUTO_INCREMENT PRIMARY KEY,
  `team_name`          VARCHAR(100) NOT NULL,
  `team_espn_id`       VARCHAR(20) NOT NULL,
  `poll_type`          ENUM('ap','coaches') NOT NULL,
  `rank`               TINYINT,
  `previous_rank`      TINYINT,
  `trend`              INT,
  `poll_points`        FLOAT,
  `first_place_votes`  INT,
  `snapshot_date`      DATE NOT NULL,
  UNIQUE KEY `uq_mbb_poll_ranking` (`team_espn_id`, `poll_type`, `snapshot_date`),
  INDEX `idx_mbb_poll_ranking_team` (`team_name`, `poll_type`, `snapshot_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_mbb_bpi` (
  `id`                    INT AUTO_INCREMENT PRIMARY KEY,
  `team_espn_id`          VARCHAR(20) NOT NULL,
  `team_name`             VARCHAR(100),
  `season`                YEAR NOT NULL,
  `snapshot_date`         DATE NOT NULL,
  `bpi`                   FLOAT,
  `bpi_rank`              SMALLINT,
  `bpi_offense`           FLOAT,
  `bpi_defense`           FLOAT,
  `sor`                   FLOAT,
  `sor_rank`              SMALLINT,
  `sos_past`              FLOAT,
  `sos_past_rank`         SMALLINT,
  `proj_tournament_seed`  TINYINT,
  `chance_sweet16`        FLOAT,
  `chance_elite8`         FLOAT,
  `chance_final4`         FLOAT,
  `chance_champion`       FLOAT,
  UNIQUE KEY `uq_mbb_bpi` (`team_espn_id`, `season`, `snapshot_date`),
  INDEX `idx_mbb_bpi_team` (`team_name`, `season`, `snapshot_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_mbb_game_predictor` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`           VARCHAR(50) NOT NULL,
  `home_pred_win_pct` FLOAT,
  `away_pred_win_pct` FLOAT,
  `home_pred_mov`     FLOAT,
  `matchup_quality`   FLOAT,
  `updated_at`        TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_mbb_game_predictor_game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- MLB — Silver Layer (Sports module tables)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `mlb_silver`;

CREATE TABLE IF NOT EXISTS `fact_game_results` (
  `id`                     INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`                VARCHAR(50) NOT NULL,
  `game_date`              DATETIME,
  `home_team`              VARCHAR(100),
  `away_team`              VARCHAR(100),
  `home_score`             INT,
  `away_score`             INT,
  `margin`                 INT,
  `is_postseason_game`     TINYINT DEFAULT 0,
  `round_name`             VARCHAR(100),
  `playoff_experience_home` DOUBLE DEFAULT 0,
  `playoff_experience_away` DOUBLE DEFAULT 0,
  `updated_at`             TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_game_results_game_id` (`game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_market_odds` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`           VARCHAR(50) NOT NULL,
  `sportsbook`        VARCHAR(100),
  `spread`            DECIMAL(6,2),
  `moneyline_home`    INT,
  `moneyline_away`    INT,
  `total_line`        DECIMAL(6,2),
  `market_timestamp`  DATETIME,
  INDEX `idx_market_odds_game_id` (`game_id`),
  INDEX `idx_market_odds_timestamp` (`market_timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- MODELING — Silver Layer (cross-sport ML features)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `modeling_silver`;

CREATE TABLE IF NOT EXISTS `fact_training_features` (
  `id`                  INT AUTO_INCREMENT PRIMARY KEY,
  `sport`               VARCHAR(20) NOT NULL,
  `game_id`             VARCHAR(50) NOT NULL,
  `game_date`           DATETIME,
  `home_team`           VARCHAR(100),
  `away_team`           VARCHAR(100),
  `target_home_win`     TINYINT,
  `target_cover_home`   TINYINT,
  `target_total_over`   TINYINT,
  `feature_version`     VARCHAR(50) NOT NULL,
  `feature_payload`     JSON NOT NULL,
  `training_timestamp`  DATETIME,
  UNIQUE KEY `uq_training_features_sport_game` (`sport`, `game_id`),
  INDEX `idx_training_features_sport_date` (`sport`, `game_date`),
  INDEX `idx_training_features_feature_version` (`feature_version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- MODELING — Internal Layer (models, predictions, bracket simulations)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `modeling_internal`;

CREATE TABLE IF NOT EXISTS `fact_model_registry` (
  `id`               INT AUTO_INCREMENT PRIMARY KEY,
  `sport`            VARCHAR(20) NOT NULL,
  `target`           VARCHAR(30) NOT NULL,
  `model_version`    VARCHAR(100) NOT NULL,
  `status`           ENUM('candidate','production','retired') NOT NULL DEFAULT 'candidate',
  `hidden_dim`       INT,
  `dropout`          DECIMAL(5,3),
  `learning_rate`    DECIMAL(10,8),
  `batch_size`       INT,
  `epochs`           INT,
  `cv_folds`         INT,
  `cv_avg_loss`      DECIMAL(10,6),
  `cv_avg_accuracy`  DECIMAL(6,4),
  `cv_avg_auc`       DECIMAL(6,4),
  `cv_fold_losses`   JSON,
  `cv_fold_accuracies` JSON,
  `cv_fold_aucs`     JSON,
  `train_rows`       INT,
  `train_final_loss` DECIMAL(10,6),
  `feature_version`  VARCHAR(50),
  `feature_count`    INT,
  `model_path`       VARCHAR(500),
  `metadata_path`    VARCHAR(500),
  `trained_at`       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `promoted_at`      TIMESTAMP NULL,
  `retired_at`       TIMESTAMP NULL,
  INDEX `idx_model_registry_sport_target` (`sport`, `target`, `status`),
  INDEX `idx_model_registry_version` (`model_version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_model_predictions` (
  `id`                 INT AUTO_INCREMENT PRIMARY KEY,
  `sport`              VARCHAR(20) NOT NULL,
  `game_id`            VARCHAR(50) NOT NULL,
  `predicted_win_prob` DECIMAL(6,4),
  `predicted_margin`   DECIMAL(6,2),
  `model_version`      VARCHAR(50),
  `created_at`         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_model_predictions_sport_game` (`sport`, `game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_trading_signals` (
  `id`               INT AUTO_INCREMENT PRIMARY KEY,
  `sport`            VARCHAR(20) NOT NULL,
  `game_id`          VARCHAR(50) NOT NULL,
  `signal_strength`  DECIMAL(6,4),
  `expected_value`   DECIMAL(6,4),
  `risk_score`       DECIMAL(6,4),
  `allocation`       DECIMAL(12,2),
  `created_at`       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_trading_signals_sport_game` (`sport`, `game_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_portfolio_simulations` (
  `id`              INT AUTO_INCREMENT PRIMARY KEY,
  `simulation_id`   VARCHAR(50) NOT NULL,
  `sport`           VARCHAR(20),
  `bankroll`        DECIMAL(12,2),
  `max_drawdown`    DECIMAL(8,4),
  `sharpe_ratio`    DECIMAL(8,4),
  `created_at`      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_portfolio_simulations_simulation_id` (`simulation_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_bracket_fields` (
  `id`                 INT AUTO_INCREMENT PRIMARY KEY,
  `season`             INT NOT NULL,
  `team_name`          VARCHAR(100) NOT NULL,
  `team_espn_id`       VARCHAR(20),
  `seed`               INT NOT NULL,
  `region`             VARCHAR(50) NOT NULL,
  `is_play_in`         TINYINT DEFAULT 0,
  `play_in_matchup_id` VARCHAR(50),
  `fetched_at`         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_bracket_fields_season_team` (`season`, `team_name`),
  INDEX `idx_bracket_fields_season` (`season`),
  INDEX `idx_bracket_fields_region_seed` (`region`, `seed`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_bracket_simulations` (
  `id`                  INT AUTO_INCREMENT PRIMARY KEY,
  `simulation_id`       VARCHAR(100) NOT NULL,
  `season`              INT NOT NULL,
  `num_simulations`     INT NOT NULL,
  `pool_size`           INT,
  `scoring_system`      VARCHAR(50) DEFAULT 'espn_standard',
  `risk_tolerance`      DECIMAL(4,3),
  `model_version`       VARCHAR(100),
  `simulation_counter`  INT NOT NULL DEFAULT 1,
  `priority_ranking`    INT NOT NULL DEFAULT 1,
  `is_default`          TINYINT(1) NOT NULL DEFAULT 0,
  `run_batch_id`        VARCHAR(36),
  `expected_score`      DOUBLE,
  `champion_pick`       VARCHAR(100),
  `created_at`          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_bracket_simulations_id` (`simulation_id`),
  INDEX `idx_bracket_simulations_season` (`season`),
  INDEX `idx_bracket_simulations_batch` (`run_batch_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_bet_tracking` (
  `id`                INT AUTO_INCREMENT PRIMARY KEY,
  `game_id`           VARCHAR(50) NOT NULL,
  `sport`             VARCHAR(20) NOT NULL,
  `game_date`         DATE NOT NULL,
  `home_team`         VARCHAR(100),
  `away_team`         VARCHAR(100),
  `bet_type`          VARCHAR(20) NOT NULL,
  `pick`              VARCHAR(200) NOT NULL,
  `odds_american`     INT,
  `model_probability` DOUBLE,
  `edge`              DOUBLE,
  `expected_value`    DOUBLE,
  `wager_amount`      DOUBLE,
  `recommended_at`    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `actual_outcome`    TINYINT(1),
  `resolved_at`       TIMESTAMP NULL,
  `profit_loss`       DOUBLE,
  `week_number`       INT,
  `year`              INT,
  INDEX `idx_bet_tracking_game` (`game_id`, `bet_type`),
  INDEX `idx_bet_tracking_week` (`year`, `week_number`),
  INDEX `idx_bet_tracking_sport` (`sport`, `game_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_bracket_picks` (
  `id`                       INT AUTO_INCREMENT PRIMARY KEY,
  `simulation_id`            VARCHAR(100) NOT NULL,
  `round_number`             INT NOT NULL,
  `game_number`              INT NOT NULL,
  `region`                   VARCHAR(50),
  `higher_seed_team`         VARCHAR(100),
  `lower_seed_team`          VARCHAR(100),
  `predicted_winner`         VARCHAR(100) NOT NULL,
  `win_probability`          DECIMAL(6,4),
  `is_upset`                 TINYINT DEFAULT 0,
  `is_contrarian`            TINYINT DEFAULT 0,
  `advancement_probability`  DECIMAL(6,4),
  `pick_leverage`            DECIMAL(8,4),
  `actual_winner`            VARCHAR(100),
  `is_correct`               TINYINT,
  INDEX `idx_bracket_picks_sim` (`simulation_id`),
  INDEX `idx_bracket_picks_round` (`simulation_id`, `round_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_bracket_team_profiles` (
  `id`                  INT AUTO_INCREMENT PRIMARY KEY,
  `season`              INT NOT NULL,
  `team_name`           VARCHAR(100) NOT NULL,
  `team_espn_id`        VARCHAR(20),
  `seed`                INT,
  `feature_payload`     JSON NOT NULL,
  `profile_timestamp`   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_bracket_team_profiles` (`season`, `team_name`),
  INDEX `idx_bracket_team_profiles_season` (`season`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS `fact_sports_news` (
  `id`             INT AUTO_INCREMENT PRIMARY KEY,
  `sport`          VARCHAR(20) NOT NULL,
  `headline`       VARCHAR(500) NOT NULL,
  `description`    TEXT,
  `article_url`    VARCHAR(1000),
  `source`         VARCHAR(100) DEFAULT 'espn',
  `published_at`   DATETIME,
  `llm_summary`    TEXT,
  `llm_model`      VARCHAR(100),
  `focus_team`     VARCHAR(100),
  `fetched_at`     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY `uq_sports_news_url` (`article_url`(500)),
  INDEX `idx_sports_news_sport_date` (`sport`, `published_at`),
  INDEX `idx_sports_news_focus_team` (`focus_team`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- FINANCE — Silver Layer
-- All finance tables live in finance_silver. SQLAlchemy models are the source
-- of truth; these DDL statements match schema.py exactly.
-- ═══════════════════════════════════════════════════════════════════════════════
USE `finance_silver`;

-- ─── dim_stock ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_stock` (
  `stock_id`            INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `ticker`              VARCHAR(20)    NOT NULL,
  `company_name`        VARCHAR(255)   NOT NULL,
  `exchange`            VARCHAR(50)    NULL,
  `sector`              VARCHAR(100)   NULL,
  `industry`            VARCHAR(200)   NULL,
  `country`             VARCHAR(50)    DEFAULT 'USA',
  `currency`            VARCHAR(10)    DEFAULT 'USD',
  `market_cap_category` ENUM('Nano','Micro','Small','Mid','Large','Mega') NULL,
  `stock_tier`          ENUM('watchlist','universe') NOT NULL DEFAULT 'universe',
  `cik`                 VARCHAR(20)    NULL,
  `is_active`           TINYINT(1)     NOT NULL DEFAULT 1,
  `is_etf`              TINYINT(1)     NOT NULL DEFAULT 0,
  `ipo_date`            DATE           NULL,
  `description`         TEXT           NULL,
  `created_at`          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_ticker` (`ticker`),
  INDEX `ix_sector` (`sector`),
  INDEX `ix_active` (`is_active`),
  INDEX `ix_stock_tier` (`stock_tier`, `is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── dim_date ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_date` (
  `date_id`           INT            NOT NULL PRIMARY KEY COMMENT 'YYYYMMDD format',
  `date`              DATE           NOT NULL,
  `year`              SMALLINT       NOT NULL,
  `quarter`           SMALLINT       NOT NULL,
  `month`             SMALLINT       NOT NULL,
  `month_name`        VARCHAR(10)    NOT NULL,
  `week_of_year`      SMALLINT       NOT NULL,
  `day_of_month`      SMALLINT       NOT NULL,
  `day_of_week`       SMALLINT       NOT NULL COMMENT '0=Mon, 6=Sun',
  `day_name`          VARCHAR(10)    NOT NULL,
  `is_weekend`        TINYINT(1)     NOT NULL DEFAULT 0,
  `is_trading_day`    TINYINT(1)     NOT NULL DEFAULT 1,
  `is_quarter_end`    TINYINT(1)     NOT NULL DEFAULT 0,
  `is_year_end`       TINYINT(1)     NOT NULL DEFAULT 0,
  `fiscal_quarter`    SMALLINT       NULL,
  UNIQUE INDEX `uq_date` (`date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_stock_price ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_stock_price` (
  `price_id`            BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `stock_id`            INT            NOT NULL,
  `trade_date`          DATE           NOT NULL,
  `open_raw`            DECIMAL(18,6)  NULL,
  `high_raw`            DECIMAL(18,6)  NULL,
  `low_raw`             DECIMAL(18,6)  NULL,
  `close_raw`           DECIMAL(18,6)  NULL,
  `volume_raw`          BIGINT         NULL,
  `open_adj`            DECIMAL(18,6)  NULL,
  `high_adj`            DECIMAL(18,6)  NULL,
  `low_adj`             DECIMAL(18,6)  NULL,
  `close_adj`           DECIMAL(18,6)  NOT NULL,
  `volume_adj`          BIGINT         NULL,
  `daily_return`        DOUBLE         NULL,
  `log_return`          DOUBLE         NULL,
  `dollar_volume`       DECIMAL(22,2)  NULL,
  `vwap`                DECIMAL(18,6)  NULL,
  `intraday_range_pct`  DOUBLE         NULL,
  `gap_pct`             DOUBLE         NULL,
  `market_cap`          DECIMAL(22,2)  NULL,
  `shares_outstanding`  BIGINT         NULL,
  `split_coefficient`   DOUBLE         DEFAULT 1.0,
  `data_source`         VARCHAR(50)    DEFAULT 'yfinance',
  `is_restated`         TINYINT(1)     DEFAULT 0,
  `created_at`          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_stock_date` (`stock_id`, `trade_date`),
  INDEX `ix_fact_stock_price_date` (`trade_date`),
  INDEX `ix_fact_stock_price_stock_date` (`stock_id`, `trade_date`),
  FOREIGN KEY (`stock_id`) REFERENCES `dim_stock` (`stock_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_technical_indicator ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_technical_indicator` (
  `indicator_id`        BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `stock_id`            INT            NOT NULL,
  `trade_date`          DATE           NOT NULL,
  -- Trend
  `sma_5` DOUBLE NULL, `sma_10` DOUBLE NULL, `sma_20` DOUBLE NULL,
  `sma_50` DOUBLE NULL, `sma_200` DOUBLE NULL,
  `ema_9` DOUBLE NULL, `ema_12` DOUBLE NULL, `ema_26` DOUBLE NULL,
  -- Momentum
  `rsi_14` DOUBLE NULL, `macd` DOUBLE NULL, `macd_signal` DOUBLE NULL,
  `macd_histogram` DOUBLE NULL, `stoch_k` DOUBLE NULL, `stoch_d` DOUBLE NULL,
  `williams_r` DOUBLE NULL, `roc_10` DOUBLE NULL, `roc_20` DOUBLE NULL,
  -- Volatility
  `bb_upper` DOUBLE NULL, `bb_middle` DOUBLE NULL, `bb_lower` DOUBLE NULL,
  `bb_pct_b` DOUBLE NULL, `bb_bandwidth` DOUBLE NULL,
  `atr_14` DOUBLE NULL, `volatility_20d` DOUBLE NULL, `volatility_5d` DOUBLE NULL,
  -- Volume
  `obv` DOUBLE NULL, `volume_sma_20` DOUBLE NULL, `volume_ratio` DOUBLE NULL,
  `mfi_14` DOUBLE NULL, `cmf_20` DOUBLE NULL,
  -- Price position
  `price_vs_sma50` DOUBLE NULL, `price_vs_sma200` DOUBLE NULL,
  `price_vs_52w_high` DOUBLE NULL, `price_vs_52w_low` DOUBLE NULL,
  `distance_to_support` DOUBLE NULL, `distance_to_resistance` DOUBLE NULL,
  -- Cross signals
  `golden_cross` TINYINT(1) NULL, `macd_bullish` TINYINT(1) NULL,
  `rsi_oversold` TINYINT(1) NULL, `rsi_overbought` TINYINT(1) NULL,
  `created_at`          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_tech_stock_date` (`stock_id`, `trade_date`),
  INDEX `ix_fact_tech_date` (`trade_date`),
  FOREIGN KEY (`stock_id`) REFERENCES `dim_stock` (`stock_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_stock_news ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_stock_news` (
  `news_id`           BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `stock_id`          INT            NOT NULL,
  `ticker`            VARCHAR(20)    NOT NULL,
  `headline`          VARCHAR(1000)  NOT NULL,
  `source`            VARCHAR(200)   NULL,
  `url`               VARCHAR(2000)  NULL,
  `published_at`      DATETIME       NOT NULL,
  `author`            VARCHAR(200)   NULL,
  `full_text`         TEXT           NULL,
  `llm_summary`       TEXT           NULL,
  `llm_key_points`    JSON           NULL,
  `llm_catalysts`     TEXT           NULL,
  `llm_risks`         TEXT           NULL,
  `sentiment_score`   DOUBLE         NULL,
  `sentiment_label`   ENUM('very_negative','negative','neutral','positive','very_positive') NULL,
  `relevance_score`   DOUBLE         NULL,
  `llm_model`         VARCHAR(100)   NULL,
  `llm_processed_at`  DATETIME       NULL,
  `data_source`       VARCHAR(50)    NULL,
  `created_at`        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_news_stock_date` (`stock_id`, `published_at`),
  INDEX `ix_news_published` (`published_at`),
  FOREIGN KEY (`stock_id`) REFERENCES `dim_stock` (`stock_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_earnings ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_earnings` (
  `earnings_id`             BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `stock_id`                INT            NOT NULL,
  `ticker`                  VARCHAR(20)    NOT NULL,
  `fiscal_year`             SMALLINT       NOT NULL,
  `fiscal_quarter`          SMALLINT       NOT NULL,
  `report_date`             DATE           NULL,
  `period_ending`           DATE           NULL,
  `eps_actual`              DOUBLE         NULL,
  `eps_estimate`            DOUBLE         NULL,
  `eps_surprise`            DOUBLE         NULL,
  `eps_surprise_pct`        DOUBLE         NULL,
  `revenue_actual`          DECIMAL(22,2)  NULL,
  `revenue_estimate`        DECIMAL(22,2)  NULL,
  `revenue_surprise_pct`    DOUBLE         NULL,
  `eps_guidance_low`        DOUBLE         NULL,
  `eps_guidance_high`       DOUBLE         NULL,
  `revenue_guidance_low`    DECIMAL(22,2)  NULL,
  `revenue_guidance_high`   DECIMAL(22,2)  NULL,
  `gross_margin`            DOUBLE         NULL,
  `operating_margin`        DOUBLE         NULL,
  `net_margin`              DOUBLE         NULL,
  `roe`                     DOUBLE         NULL,
  `debt_to_equity`          DOUBLE         NULL,
  `free_cash_flow`          DECIMAL(22,2)  NULL,
  `pe_ratio`                DOUBLE         NULL,
  `peg_ratio`               DOUBLE         NULL,
  `price_to_book`           DOUBLE         NULL,
  `price_to_sales`          DOUBLE         NULL,
  `enterprise_value`        DECIMAL(22,2)  NULL,
  `ev_to_ebitda`            DOUBLE         NULL,
  `llm_summary`             TEXT           NULL,
  `llm_bull_case`           TEXT           NULL,
  `llm_bear_case`           TEXT           NULL,
  `llm_key_metrics`         JSON           NULL,
  `llm_model`               VARCHAR(100)   NULL,
  `llm_processed_at`        DATETIME       NULL,
  `price_reaction_1d`       DOUBLE         NULL,
  `price_reaction_5d`       DOUBLE         NULL,
  `data_source`             VARCHAR(50)    NULL,
  `created_at`              DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_earnings_period` (`stock_id`, `fiscal_quarter`, `fiscal_year`),
  INDEX `ix_earnings_stock` (`stock_id`),
  FOREIGN KEY (`stock_id`) REFERENCES `dim_stock` (`stock_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_macro_indicator ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_macro_indicator` (
  `macro_id`                BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `indicator_date`          DATE           NOT NULL,
  `vix` DOUBLE NULL, `vix_term_structure` DOUBLE NULL,
  `treasury_2y` DOUBLE NULL, `treasury_5y` DOUBLE NULL,
  `treasury_10y` DOUBLE NULL, `treasury_30y` DOUBLE NULL,
  `yield_curve_2_10` DOUBLE NULL, `yield_curve_3m_10y` DOUBLE NULL,
  `fed_funds_rate` DOUBLE NULL, `breakeven_inflation_10y` DOUBLE NULL,
  `sp500_advance_decline` DOUBLE NULL,
  `sp500_new_highs` INT NULL, `sp500_new_lows` INT NULL,
  `pct_above_sma200` DOUBLE NULL, `pct_above_sma50` DOUBLE NULL,
  `spy_close` DOUBLE NULL, `qqq_close` DOUBLE NULL,
  `iwm_close` DOUBLE NULL, `dia_close` DOUBLE NULL,
  `sp500_return_1d` DOUBLE NULL,
  `gold_close` DOUBLE NULL, `oil_wti` DOUBLE NULL,
  `dollar_index` DOUBLE NULL,
  `high_yield_spread` DOUBLE NULL, `investment_grade_spread` DOUBLE NULL,
  `put_call_ratio` DOUBLE NULL, `aaii_bull_pct` DOUBLE NULL,
  `fear_greed_index` DOUBLE NULL,
  `data_source`             VARCHAR(100)   NULL,
  `created_at`              DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_macro_date` (`indicator_date`),
  INDEX `ix_macro_date` (`indicator_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_forecast ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_forecast` (
  `forecast_id`         BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `stock_id`            INT            NOT NULL,
  `ticker`              VARCHAR(20)    NOT NULL,
  `forecast_date`       DATE           NOT NULL,
  `target_date`         DATE           NOT NULL,
  `forecast_horizon`    INT            DEFAULT 1,
  `model_name`          VARCHAR(100)   NOT NULL,
  `model_version`       VARCHAR(50)    NULL,
  `predicted_open` DOUBLE NULL, `predicted_high` DOUBLE NULL,
  `predicted_low` DOUBLE NULL, `predicted_close` DOUBLE NULL,
  `predicted_return` DOUBLE NULL,
  `predicted_direction` INT            NULL,
  `confidence_score`    DOUBLE         NULL,
  `opportunity_score`   DOUBLE         NULL,
  `lower_bound_95` DOUBLE NULL, `upper_bound_95` DOUBLE NULL,
  `lower_bound_80` DOUBLE NULL, `upper_bound_80` DOUBLE NULL,
  `top_features`        JSON           NULL,
  `actual_open` DOUBLE NULL, `actual_close` DOUBLE NULL,
  `actual_return` DOUBLE NULL, `actual_direction` INT NULL,
  `was_correct`         TINYINT(1)     NULL,
  `llm_rationale`       TEXT           NULL,
  `llm_model`           VARCHAR(100)   NULL,
  `created_at`          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_forecast_stock_date` (`stock_id`, `forecast_date`),
  INDEX `ix_forecast_target_date` (`target_date`),
  FOREIGN KEY (`stock_id`) REFERENCES `dim_stock` (`stock_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_backtest_result ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_backtest_result` (
  `backtest_id`                 BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `run_date`                    DATE           NOT NULL,
  `model_name`                  VARCHAR(100)   NOT NULL,
  `model_version`               VARCHAR(50)    NULL,
  `tickers_tested`              JSON           NULL,
  `train_start` DATE NULL, `train_end` DATE NULL,
  `test_start` DATE NULL, `test_end` DATE NULL,
  `n_folds`                     INT            NULL,
  `directional_accuracy` DOUBLE NULL, `precision_long` DOUBLE NULL,
  `recall_long` DOUBLE NULL, `f1_long` DOUBLE NULL,
  `strategy_return_total` DOUBLE NULL, `strategy_return_annualized` DOUBLE NULL,
  `benchmark_return_total` DOUBLE NULL,
  `alpha` DOUBLE NULL, `beta` DOUBLE NULL,
  `sharpe_ratio` DOUBLE NULL, `sortino_ratio` DOUBLE NULL,
  `max_drawdown` DOUBLE NULL, `calmar_ratio` DOUBLE NULL,
  `win_rate` DOUBLE NULL, `avg_win` DOUBLE NULL,
  `avg_loss` DOUBLE NULL, `profit_factor` DOUBLE NULL,
  `rmse` DOUBLE NULL, `mae` DOUBLE NULL, `mape` DOUBLE NULL,
  `per_ticker_metrics`          JSON           NULL,
  `notes`                       TEXT           NULL,
  `created_at`                  DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_backtest_model` (`model_name`, `run_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_model_registry ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_model_registry` (
  `model_id`          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `stock_id`          INT            NULL,
  `ticker`            VARCHAR(20)    NOT NULL,
  `model_version`     VARCHAR(50)    DEFAULT 'v3.0',
  `sequence_num`      INT            NOT NULL,
  `status`            ENUM('candidate','champion','archived') NOT NULL DEFAULT 'candidate',
  `trained_at`        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `training_duration_sec` DOUBLE     NULL,
  `train_rows`        INT            NULL,
  `n_features`        INT            NULL,
  `horizons`          JSON           NULL,
  `hpo_method`        VARCHAR(20)    DEFAULT 'none',
  `hyperparams`       JSON           NULL,
  `train_metrics`     JSON           NULL,
  `backtest_id`       BIGINT         NULL,
  `backtest_metrics`  JSON           NULL,
  `feature_importance` JSON          NULL,
  `model_path`        VARCHAR(500)   NULL,
  `promoted_at`       DATETIME       NULL,
  `promoted_from_id`  BIGINT         NULL,
  `notes`             TEXT           NULL,
  `created_at`        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_model_registry_ticker` (`ticker`),
  INDEX `ix_model_registry_status` (`status`),
  INDEX `ix_model_registry_ticker_status` (`ticker`, `status`),
  FOREIGN KEY (`stock_id`) REFERENCES `dim_stock` (`stock_id`),
  FOREIGN KEY (`backtest_id`) REFERENCES `fact_backtest_result` (`backtest_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_stock_split ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_stock_split` (
  `split_id`          BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `stock_id`          INT            NOT NULL,
  `ticker`            VARCHAR(20)    NOT NULL,
  `split_date`        DATE           NOT NULL,
  `split_ratio`       DOUBLE         NOT NULL,
  `numerator`         INT            NULL,
  `denominator`       INT            NULL,
  `history_restated`  TINYINT(1)     DEFAULT 0,
  `restated_at`       DATETIME       NULL,
  `data_source`       VARCHAR(50)    NULL,
  `created_at`        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_split_stock_date` (`stock_id`, `split_date`),
  FOREIGN KEY (`stock_id`) REFERENCES `dim_stock` (`stock_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_bulk_load_log ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_bulk_load_log` (
  `load_id`           BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `source`            VARCHAR(100)   NOT NULL,
  `file_name`         VARCHAR(500)   NULL,
  `tickers_loaded`    INT            DEFAULT 0,
  `rows_loaded`       INT            DEFAULT 0,
  `rows_skipped`      INT            DEFAULT 0,
  `rows_errored`      INT            DEFAULT 0,
  `start_date`        DATE           NULL,
  `end_date`          DATE           NULL,
  `duration_sec`      DOUBLE         NULL,
  `status`            ENUM('running','success','error') DEFAULT 'running',
  `error_message`     TEXT           NULL,
  `created_at`        DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `completed_at`      DATETIME       NULL,
  INDEX `ix_bulk_load_source` (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- HOMELAB — Silver Layer (raw device/service metrics)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `homelab_silver`;

-- ─── dim_host ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_host` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `hostname`        VARCHAR(255)   NOT NULL,
  `ip_address`      VARCHAR(45)    NULL COMMENT 'IPv4 or IPv6',
  `mac_address`     VARCHAR(17)    NULL,
  `os`              VARCHAR(100)   NULL,
  `os_version`      VARCHAR(50)    NULL,
  `cpu_cores`       TINYINT UNSIGNED NULL,
  `ram_gb`          DECIMAL(6,2)   NULL,
  `disk_total_gb`   DECIMAL(10,2)  NULL,
  `location`        VARCHAR(100)   NULL COMMENT 'e.g. rack, room, site',
  `role`            VARCHAR(100)   NULL COMMENT 'e.g. docker-host, nas, router',
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_hostname` (`hostname`),
  INDEX `ix_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── dim_service ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_service` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `service_name`    VARCHAR(200)   NOT NULL,
  `service_type`    VARCHAR(100)   NULL COMMENT 'web, api, database, cache, proxy',
  `host_id`         BIGINT UNSIGNED NULL COMMENT 'FK to dim_host',
  `port`            INT UNSIGNED   NULL,
  `protocol`        VARCHAR(20)    DEFAULT 'http',
  `health_endpoint` VARCHAR(500)   NULL,
  `expected_status` INT            DEFAULT 200,
  `is_critical`     TINYINT(1)     NOT NULL DEFAULT 0,
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_service_host` (`host_id`),
  INDEX `ix_service_type` (`service_type`),
  INDEX `ix_service_active` (`is_active`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── dim_docker_container ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_docker_container` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `container_id`    VARCHAR(64)    NOT NULL COMMENT 'Docker short ID',
  `container_name`  VARCHAR(255)   NOT NULL,
  `image_name`      VARCHAR(500)   NOT NULL,
  `image_tag`       VARCHAR(128)   DEFAULT 'latest',
  `host_id`         BIGINT UNSIGNED NULL COMMENT 'FK to dim_host',
  `service_id`      BIGINT UNSIGNED NULL COMMENT 'FK to dim_service',
  `status`          VARCHAR(50)    NULL COMMENT 'running, stopped, exited',
  `restart_policy`  VARCHAR(50)    NULL,
  `ports_mapped`    JSON           NULL,
  `volumes_mapped`  JSON           NULL,
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_container_id` (`container_id`),
  INDEX `ix_container_host` (`host_id`),
  INDEX `ix_container_name` (`container_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_metric ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_metric` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `host_id`         BIGINT UNSIGNED NOT NULL,
  `service_id`      BIGINT UNSIGNED NULL,
  `collected_at`    DATETIME       NOT NULL,
  `metric_name`     VARCHAR(100)   NOT NULL COMMENT 'cpu_pct, mem_pct, disk_pct, net_in_bytes, etc.',
  `metric_value`    DOUBLE         NOT NULL,
  `metric_unit`     VARCHAR(20)    NULL COMMENT 'percent, bytes, ms, count',
  `tags`            JSON           NULL COMMENT 'Additional labels/dimensions',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_metric_host_time` (`host_id`, `collected_at`),
  INDEX `ix_metric_name_time` (`metric_name`, `collected_at`),
  INDEX `ix_metric_collected` (`collected_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_docker_event ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_docker_event` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `container_id`    BIGINT UNSIGNED NOT NULL COMMENT 'FK to dim_docker_container',
  `host_id`         BIGINT UNSIGNED NOT NULL,
  `event_time`      DATETIME       NOT NULL,
  `event_type`      VARCHAR(50)    NOT NULL COMMENT 'start, stop, die, restart, oom, health_status',
  `event_action`    VARCHAR(100)   NULL,
  `event_detail`    TEXT           NULL,
  `exit_code`       INT            NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_docker_event_container` (`container_id`, `event_time`),
  INDEX `ix_docker_event_time` (`event_time`),
  INDEX `ix_docker_event_type` (`event_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_log_entry ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_log_entry` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `host_id`         BIGINT UNSIGNED NOT NULL,
  `service_id`      BIGINT UNSIGNED NULL,
  `log_time`        DATETIME       NOT NULL,
  `log_level`       ENUM('DEBUG','INFO','WARNING','ERROR','CRITICAL') NOT NULL DEFAULT 'INFO',
  `logger_name`     VARCHAR(200)   NULL,
  `message`         TEXT           NOT NULL,
  `stack_trace`     TEXT           NULL,
  `source_file`     VARCHAR(500)   NULL,
  `tags`            JSON           NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_log_host_time` (`host_id`, `log_time`),
  INDEX `ix_log_level` (`log_level`, `log_time`),
  INDEX `ix_log_time` (`log_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- HOMELAB — Internal Layer (computed health scores, anomaly flags)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `homelab_internal`;

-- ─── fact_health_score ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_health_score` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `host_id`         BIGINT UNSIGNED NOT NULL,
  `service_id`      BIGINT UNSIGNED NULL,
  `evaluated_at`    DATETIME       NOT NULL,
  `overall_score`   DOUBLE         NOT NULL COMMENT '0=down, 100=perfect',
  `cpu_score`       DOUBLE         NULL,
  `memory_score`    DOUBLE         NULL,
  `disk_score`      DOUBLE         NULL,
  `network_score`   DOUBLE         NULL,
  `response_time_ms` INT UNSIGNED  NULL,
  `is_healthy`      TINYINT(1)     NOT NULL DEFAULT 1,
  `degradation_reason` TEXT        NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_health_host_time` (`host_id`, `evaluated_at`),
  INDEX `ix_health_service` (`service_id`, `evaluated_at`),
  INDEX `ix_health_score` (`overall_score`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_anomaly_detection ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_anomaly_detection` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `host_id`         BIGINT UNSIGNED NOT NULL,
  `service_id`      BIGINT UNSIGNED NULL,
  `detected_at`     DATETIME       NOT NULL,
  `metric_name`     VARCHAR(100)   NOT NULL,
  `metric_value`    DOUBLE         NOT NULL,
  `expected_value`  DOUBLE         NULL,
  `deviation_sigma` DOUBLE         NULL COMMENT 'Standard deviations from mean',
  `anomaly_type`    VARCHAR(50)    NULL COMMENT 'spike, drop, trend_break, flatline',
  `severity`        ENUM('low','medium','high','critical') NOT NULL DEFAULT 'medium',
  `is_acknowledged` TINYINT(1)     NOT NULL DEFAULT 0,
  `acknowledged_by` VARCHAR(100)   NULL,
  `acknowledged_at` DATETIME       NULL,
  `notes`           TEXT           NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_anomaly_host_time` (`host_id`, `detected_at`),
  INDEX `ix_anomaly_severity` (`severity`, `detected_at`),
  INDEX `ix_anomaly_metric` (`metric_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_alert_trigger ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_alert_trigger` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `host_id`         BIGINT UNSIGNED NOT NULL,
  `service_id`      BIGINT UNSIGNED NULL,
  `triggered_at`    DATETIME       NOT NULL,
  `alert_name`      VARCHAR(200)   NOT NULL,
  `alert_type`      VARCHAR(50)    NOT NULL COMMENT 'threshold, anomaly, heartbeat',
  `severity`        ENUM('info','warning','critical','emergency') NOT NULL DEFAULT 'warning',
  `condition_expr`  VARCHAR(500)   NULL COMMENT 'e.g. cpu_pct > 90 for 5m',
  `current_value`   DOUBLE         NULL,
  `threshold_value` DOUBLE         NULL,
  `message`         TEXT           NOT NULL,
  `notification_channel` VARCHAR(50) NULL COMMENT 'slack, email, pagerduty',
  `notification_sent` TINYINT(1)   NOT NULL DEFAULT 0,
  `resolved_at`     DATETIME       NULL,
  `resolution_notes` TEXT          NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_alert_host_time` (`host_id`, `triggered_at`),
  INDEX `ix_alert_severity` (`severity`, `triggered_at`),
  INDEX `ix_alert_resolved` (`resolved_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- HOMELAB — Gold Layer (dashboards, alerts, SLA summaries)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `homelab_gold`;

-- ─── fact_sla_summary ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_sla_summary` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `service_id`      BIGINT UNSIGNED NOT NULL,
  `period_start`    DATE           NOT NULL,
  `period_end`      DATE           NOT NULL,
  `period_type`     ENUM('daily','weekly','monthly') NOT NULL DEFAULT 'daily',
  `total_minutes`   INT UNSIGNED   NOT NULL,
  `uptime_minutes`  INT UNSIGNED   NOT NULL,
  `downtime_minutes` INT UNSIGNED  NOT NULL DEFAULT 0,
  `uptime_pct`      DECIMAL(6,3)   NOT NULL COMMENT '99.999 = five nines',
  `incidents_count` INT UNSIGNED   NOT NULL DEFAULT 0,
  `avg_response_ms` INT UNSIGNED   NULL,
  `p95_response_ms` INT UNSIGNED   NULL,
  `p99_response_ms` INT UNSIGNED   NULL,
  `sla_target_pct`  DECIMAL(6,3)   DEFAULT 99.900,
  `sla_met`         TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_sla_service_period` (`service_id`, `period_start`, `period_type`),
  INDEX `ix_sla_period` (`period_start`, `period_end`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_capacity_trend ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_capacity_trend` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `host_id`         BIGINT UNSIGNED NOT NULL,
  `trend_date`      DATE           NOT NULL,
  `resource_type`   VARCHAR(50)    NOT NULL COMMENT 'cpu, memory, disk, network',
  `avg_usage_pct`   DOUBLE         NOT NULL,
  `peak_usage_pct`  DOUBLE         NOT NULL,
  `min_usage_pct`   DOUBLE         NULL,
  `growth_rate_daily` DOUBLE       NULL COMMENT 'Pct change per day',
  `days_to_capacity` INT           NULL COMMENT 'Projected days until 100%',
  `recommendation`  TEXT           NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_capacity_host_date` (`host_id`, `trend_date`, `resource_type`),
  INDEX `ix_capacity_date` (`trend_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── vw_current_health (view) ────────────────────────────────────────────────
CREATE OR REPLACE VIEW `vw_current_health` AS
SELECT
  h.`host_id`,
  h.`service_id`,
  h.`evaluated_at`,
  h.`overall_score`,
  h.`cpu_score`,
  h.`memory_score`,
  h.`disk_score`,
  h.`network_score`,
  h.`response_time_ms`,
  h.`is_healthy`,
  h.`degradation_reason`
FROM `homelab_internal`.`fact_health_score` h
INNER JOIN (
  SELECT `host_id`, COALESCE(`service_id`, 0) AS `sid`, MAX(`evaluated_at`) AS `latest`
  FROM `homelab_internal`.`fact_health_score`
  GROUP BY `host_id`, COALESCE(`service_id`, 0)
) latest ON h.`host_id` = latest.`host_id`
  AND COALESCE(h.`service_id`, 0) = latest.`sid`
  AND h.`evaluated_at` = latest.`latest`;


-- ═══════════════════════════════════════════════════════════════════════════════
-- ASSISTANT — Silver Layer (raw conversations, calendar, tasks)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `assistant_silver`;

-- ─── dim_person ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_person` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `full_name`       VARCHAR(255)   NOT NULL,
  `email`           VARCHAR(320)   NULL,
  `phone`           VARCHAR(50)    NULL,
  `relationship`    VARCHAR(100)   NULL COMMENT 'self, family, friend, colleague, client',
  `organization`    VARCHAR(255)   NULL,
  `notes`           TEXT           NULL,
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_person_name` (`full_name`),
  INDEX `ix_person_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── dim_topic ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_topic` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `topic_name`      VARCHAR(200)   NOT NULL,
  `category`        VARCHAR(100)   NULL COMMENT 'work, personal, finance, health, learning',
  `parent_topic_id` BIGINT UNSIGNED NULL COMMENT 'Self-referencing FK for hierarchy',
  `description`     TEXT           NULL,
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_topic_name` (`topic_name`),
  INDEX `ix_topic_category` (`category`),
  INDEX `ix_topic_parent` (`parent_topic_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_conversation ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_conversation` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `session_id`      CHAR(36)       NOT NULL COMMENT 'Groups messages in a conversation',
  `role`            ENUM('user','assistant','system') NOT NULL,
  `content`         TEXT           NOT NULL,
  `token_count`     INT UNSIGNED   NULL,
  `model_used`      VARCHAR(100)   NULL,
  `topic_id`        BIGINT UNSIGNED NULL,
  `person_id`       BIGINT UNSIGNED NULL COMMENT 'Who initiated this conversation',
  `channel`         VARCHAR(50)    NULL COMMENT 'web, slack, api, sms',
  `response_time_ms` INT UNSIGNED  NULL,
  `feedback_score`  TINYINT        NULL COMMENT '1-5 user rating',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_convo_session` (`session_id`, `created_at`),
  INDEX `ix_convo_topic` (`topic_id`),
  INDEX `ix_convo_time` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_calendar_event ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_calendar_event` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `external_id`     VARCHAR(500)   NULL COMMENT 'Google/Outlook calendar event ID',
  `title`           VARCHAR(500)   NOT NULL,
  `description`     TEXT           NULL,
  `location`        VARCHAR(500)   NULL,
  `start_time`      DATETIME       NOT NULL,
  `end_time`        DATETIME       NULL,
  `all_day`         TINYINT(1)     NOT NULL DEFAULT 0,
  `calendar_name`   VARCHAR(200)   NULL,
  `organizer`       VARCHAR(320)   NULL,
  `attendees`       JSON           NULL,
  `recurrence_rule` VARCHAR(500)   NULL,
  `status`          ENUM('confirmed','tentative','cancelled') DEFAULT 'confirmed',
  `reminder_minutes` INT           NULL,
  `topic_id`        BIGINT UNSIGNED NULL,
  `source`          VARCHAR(50)    NULL COMMENT 'google, outlook, manual',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_cal_start` (`start_time`),
  INDEX `ix_cal_external` (`external_id`(255)),
  INDEX `ix_cal_calendar` (`calendar_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_task ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_task` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `external_id`     VARCHAR(500)   NULL COMMENT 'Todoist/Notion/Jira task ID',
  `title`           VARCHAR(500)   NOT NULL,
  `description`     TEXT           NULL,
  `status`          ENUM('backlog','todo','in_progress','blocked','done','cancelled') NOT NULL DEFAULT 'todo',
  `priority`        ENUM('low','medium','high','urgent') DEFAULT 'medium',
  `due_date`        DATETIME       NULL,
  `completed_at`    DATETIME       NULL,
  `assigned_to`     BIGINT UNSIGNED NULL COMMENT 'FK to dim_person',
  `project`         VARCHAR(200)   NULL,
  `tags`            JSON           NULL,
  `topic_id`        BIGINT UNSIGNED NULL,
  `parent_task_id`  BIGINT UNSIGNED NULL COMMENT 'Subtask relationship',
  `source`          VARCHAR(50)    NULL COMMENT 'todoist, notion, manual',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_task_status` (`status`),
  INDEX `ix_task_due` (`due_date`),
  INDEX `ix_task_priority` (`priority`, `status`),
  INDEX `ix_task_external` (`external_id`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_document ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_document` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `title`           VARCHAR(500)   NOT NULL,
  `file_path`       VARCHAR(1000)  NULL,
  `file_type`       VARCHAR(50)    NULL COMMENT 'pdf, md, docx, txt, url',
  `file_size_bytes` BIGINT UNSIGNED NULL,
  `content_text`    LONGTEXT       NULL COMMENT 'Extracted plain text',
  `content_hash`    CHAR(64)       NULL COMMENT 'SHA-256 for dedup',
  `topic_id`        BIGINT UNSIGNED NULL,
  `source`          VARCHAR(100)   NULL COMMENT 'gdrive, local, notion, web',
  `source_url`      VARCHAR(2000)  NULL,
  `is_indexed`      TINYINT(1)     NOT NULL DEFAULT 0,
  `indexed_at`      DATETIME       NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_doc_type` (`file_type`),
  INDEX `ix_doc_topic` (`topic_id`),
  INDEX `ix_doc_hash` (`content_hash`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- ASSISTANT — Internal Layer (embeddings, entity extraction, memory)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `assistant_internal`;

-- ─── fact_entity ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_entity` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `entity_text`     VARCHAR(500)   NOT NULL,
  `entity_type`     VARCHAR(50)    NOT NULL COMMENT 'person, org, location, date, concept, product',
  `canonical_name`  VARCHAR(500)   NULL COMMENT 'Normalized/resolved name',
  `source_type`     VARCHAR(50)    NOT NULL COMMENT 'conversation, document, calendar, task',
  `source_id`       BIGINT UNSIGNED NOT NULL COMMENT 'FK to the source table id',
  `confidence`      DOUBLE         NULL COMMENT '0 to 1',
  `person_id`       BIGINT UNSIGNED NULL COMMENT 'FK to assistant_silver.dim_person if resolved',
  `topic_id`        BIGINT UNSIGNED NULL,
  `extraction_model` VARCHAR(100)  NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_entity_type` (`entity_type`),
  INDEX `ix_entity_text` (`entity_text`(255)),
  INDEX `ix_entity_source` (`source_type`, `source_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_memory_chunk ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_memory_chunk` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `content`         TEXT           NOT NULL,
  `memory_type`     VARCHAR(50)    NOT NULL COMMENT 'fact, preference, instruction, episode',
  `importance`      DOUBLE         NULL COMMENT '0 to 1, for retrieval ranking',
  `source_type`     VARCHAR(50)    NOT NULL,
  `source_id`       BIGINT UNSIGNED NOT NULL,
  `topic_id`        BIGINT UNSIGNED NULL,
  `person_id`       BIGINT UNSIGNED NULL,
  `valid_from`      DATETIME       NULL COMMENT 'Temporal validity start',
  `valid_until`     DATETIME       NULL COMMENT 'Temporal validity end',
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `access_count`    INT UNSIGNED   NOT NULL DEFAULT 0,
  `last_accessed_at` DATETIME      NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_memory_type` (`memory_type`),
  INDEX `ix_memory_importance` (`importance`),
  INDEX `ix_memory_active` (`is_active`, `importance`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_embedding_ref ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_embedding_ref` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `source_type`     VARCHAR(50)    NOT NULL COMMENT 'conversation, document, memory_chunk',
  `source_id`       BIGINT UNSIGNED NOT NULL,
  `chunk_index`     INT UNSIGNED   NOT NULL DEFAULT 0 COMMENT 'For multi-chunk documents',
  `chunk_text`      TEXT           NOT NULL,
  `embedding_model` VARCHAR(100)   NOT NULL COMMENT 'e.g. text-embedding-3-small',
  `embedding_dim`   INT UNSIGNED   NOT NULL COMMENT 'e.g. 1536',
  `vector_store`    VARCHAR(100)   NOT NULL COMMENT 'e.g. pgvector, pinecone, chromadb',
  `vector_id`       VARCHAR(500)   NOT NULL COMMENT 'ID in the vector store',
  `metadata`        JSON           NULL COMMENT 'Extra metadata stored alongside vector',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_embed_source` (`source_type`, `source_id`),
  INDEX `ix_embed_vector` (`vector_store`, `vector_id`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_action_log ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_action_log` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `action_type`     VARCHAR(100)   NOT NULL COMMENT 'email_sent, task_created, reminder_set, search, api_call',
  `action_detail`   TEXT           NULL,
  `conversation_id` BIGINT UNSIGNED NULL COMMENT 'FK to fact_conversation if triggered by chat',
  `person_id`       BIGINT UNSIGNED NULL,
  `status`          ENUM('pending','success','failed','cancelled') NOT NULL DEFAULT 'pending',
  `error_message`   TEXT           NULL,
  `duration_ms`     INT UNSIGNED   NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_action_type` (`action_type`, `created_at`),
  INDEX `ix_action_status` (`status`),
  INDEX `ix_action_time` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- ASSISTANT — Gold Layer (summaries, reminders, knowledge graph)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `assistant_gold`;

-- ─── fact_daily_summary ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_daily_summary` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `summary_date`    DATE           NOT NULL,
  `conversations_count` INT UNSIGNED NOT NULL DEFAULT 0,
  `tasks_completed` INT UNSIGNED   NOT NULL DEFAULT 0,
  `tasks_created`   INT UNSIGNED   NOT NULL DEFAULT 0,
  `events_count`    INT UNSIGNED   NOT NULL DEFAULT 0,
  `key_topics`      JSON           NULL COMMENT 'Top topics discussed',
  `key_decisions`   JSON           NULL COMMENT 'Important decisions made',
  `action_items`    JSON           NULL COMMENT 'Open action items',
  `llm_summary`     TEXT           NULL COMMENT 'AI-generated daily recap',
  `llm_model`       VARCHAR(100)   NULL,
  `mood_score`      DOUBLE         NULL COMMENT 'Inferred from conversation tone, 0-1',
  `productivity_score` DOUBLE      NULL COMMENT 'Task completion rate, 0-1',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_summary_date` (`summary_date`),
  INDEX `ix_summary_date` (`summary_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_reminder ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_reminder` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `title`           VARCHAR(500)   NOT NULL,
  `description`     TEXT           NULL,
  `remind_at`       DATETIME       NOT NULL,
  `recurrence_rule` VARCHAR(200)   NULL COMMENT 'RRULE or simple pattern',
  `person_id`       BIGINT UNSIGNED NULL,
  `topic_id`        BIGINT UNSIGNED NULL,
  `source_type`     VARCHAR(50)    NULL COMMENT 'conversation, task, manual',
  `source_id`       BIGINT UNSIGNED NULL,
  `channel`         VARCHAR(50)    DEFAULT 'push' COMMENT 'push, email, slack, sms',
  `status`          ENUM('pending','sent','snoozed','dismissed','cancelled') NOT NULL DEFAULT 'pending',
  `sent_at`         DATETIME       NULL,
  `snoozed_until`   DATETIME       NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_reminder_time` (`remind_at`),
  INDEX `ix_reminder_status` (`status`, `remind_at`),
  INDEX `ix_reminder_person` (`person_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_relationship_edge ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_relationship_edge` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `from_entity_type` VARCHAR(50)   NOT NULL COMMENT 'person, topic, document, task',
  `from_entity_id`  BIGINT UNSIGNED NOT NULL,
  `to_entity_type`  VARCHAR(50)    NOT NULL,
  `to_entity_id`    BIGINT UNSIGNED NOT NULL,
  `relationship`    VARCHAR(100)   NOT NULL COMMENT 'mentions, works_with, related_to, depends_on',
  `strength`        DOUBLE         NULL COMMENT '0 to 1, edge weight',
  `evidence_count`  INT UNSIGNED   NOT NULL DEFAULT 1 COMMENT 'How many times this edge was observed',
  `first_seen_at`   DATETIME       NOT NULL,
  `last_seen_at`    DATETIME       NOT NULL,
  `metadata`        JSON           NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_edge` (`from_entity_type`, `from_entity_id`, `to_entity_type`, `to_entity_id`, `relationship`),
  INDEX `ix_edge_from` (`from_entity_type`, `from_entity_id`),
  INDEX `ix_edge_to` (`to_entity_type`, `to_entity_id`),
  INDEX `ix_edge_relationship` (`relationship`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- SPORTS NFL — Silver Layer (raw game/player data)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `nfl_silver`;

-- ─── dim_team ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_team` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `team_abbr`       VARCHAR(10)    NOT NULL COMMENT 'e.g. KC, BUF, SF',
  `team_name`       VARCHAR(100)   NOT NULL COMMENT 'e.g. Kansas City Chiefs',
  `city`            VARCHAR(100)   NULL,
  `conference`      ENUM('AFC','NFC') NOT NULL,
  `division`        VARCHAR(20)    NOT NULL COMMENT 'e.g. West, East, North, South',
  `stadium`         VARCHAR(200)   NULL,
  `head_coach`      VARCHAR(200)   NULL,
  `primary_color`   VARCHAR(7)     NULL COMMENT 'Hex color code',
  `secondary_color` VARCHAR(7)     NULL,
  `logo_url`        VARCHAR(500)   NULL,
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_team_abbr` (`team_abbr`),
  INDEX `ix_team_conference` (`conference`, `division`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── dim_player ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_player` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `external_id`     VARCHAR(100)   NULL COMMENT 'NFL.com or ESPN player ID',
  `full_name`       VARCHAR(200)   NOT NULL,
  `position`        VARCHAR(10)    NOT NULL COMMENT 'QB, RB, WR, TE, K, DEF, etc.',
  `team_id`         BIGINT UNSIGNED NULL COMMENT 'FK to dim_team; NULL if free agent',
  `jersey_number`   TINYINT UNSIGNED NULL,
  `height_inches`   TINYINT UNSIGNED NULL,
  `weight_lbs`      SMALLINT UNSIGNED NULL,
  `birth_date`      DATE           NULL,
  `college`         VARCHAR(200)   NULL,
  `draft_year`      SMALLINT       NULL,
  `draft_round`     TINYINT        NULL,
  `draft_pick`      SMALLINT       NULL,
  `years_exp`       TINYINT UNSIGNED NULL,
  `status`          ENUM('active','injured_reserve','practice_squad','free_agent','retired') DEFAULT 'active',
  `is_active`       TINYINT(1)     NOT NULL DEFAULT 1,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_player_name` (`full_name`),
  INDEX `ix_player_team` (`team_id`),
  INDEX `ix_player_position` (`position`),
  INDEX `ix_player_external` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── dim_game ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `dim_game` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `external_id`     VARCHAR(100)   NULL COMMENT 'NFL.com game ID',
  `season`          SMALLINT       NOT NULL,
  `season_type`     ENUM('preseason','regular','postseason') NOT NULL DEFAULT 'regular',
  `week`            TINYINT        NOT NULL,
  `game_date`       DATE           NOT NULL,
  `game_time`       TIME           NULL,
  `home_team_id`    BIGINT UNSIGNED NOT NULL,
  `away_team_id`    BIGINT UNSIGNED NOT NULL,
  `venue`           VARCHAR(200)   NULL,
  `surface`         VARCHAR(50)    NULL COMMENT 'grass, turf',
  `roof_type`       VARCHAR(50)    NULL COMMENT 'dome, open, retractable',
  `weather_temp_f`  TINYINT        NULL,
  `weather_wind_mph` TINYINT UNSIGNED NULL,
  `weather_condition` VARCHAR(50)  NULL,
  `home_score`      SMALLINT UNSIGNED NULL,
  `away_score`      SMALLINT UNSIGNED NULL,
  `home_spread`     DECIMAL(4,1)   NULL COMMENT 'Vegas spread',
  `over_under`      DECIMAL(5,1)   NULL COMMENT 'Total points line',
  `status`          ENUM('scheduled','in_progress','final','postponed','cancelled') DEFAULT 'scheduled',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_game_season_week` (`season`, `season_type`, `week`),
  INDEX `ix_game_date` (`game_date`),
  INDEX `ix_game_home` (`home_team_id`),
  INDEX `ix_game_away` (`away_team_id`),
  INDEX `ix_game_external` (`external_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_game_stat ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_game_stat` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `game_id`         BIGINT UNSIGNED NOT NULL,
  `team_id`         BIGINT UNSIGNED NOT NULL,
  `is_home`         TINYINT(1)     NOT NULL,
  `points_scored`   SMALLINT UNSIGNED NULL,
  `points_allowed`  SMALLINT UNSIGNED NULL,
  -- Offense
  `total_yards`     SMALLINT       NULL,
  `passing_yards`   SMALLINT       NULL,
  `rushing_yards`   SMALLINT       NULL,
  `turnovers`       TINYINT UNSIGNED NULL,
  `time_of_possession_sec` SMALLINT UNSIGNED NULL,
  `first_downs`     TINYINT UNSIGNED NULL,
  `third_down_conv` TINYINT UNSIGNED NULL,
  `third_down_att`  TINYINT UNSIGNED NULL,
  `fourth_down_conv` TINYINT UNSIGNED NULL,
  `fourth_down_att` TINYINT UNSIGNED NULL,
  `penalties`       TINYINT UNSIGNED NULL,
  `penalty_yards`   SMALLINT UNSIGNED NULL,
  `sacks_allowed`   TINYINT UNSIGNED NULL,
  -- Defense
  `sacks`           TINYINT UNSIGNED NULL,
  `interceptions`   TINYINT UNSIGNED NULL,
  `fumbles_recovered` TINYINT UNSIGNED NULL,
  `defensive_tds`   TINYINT UNSIGNED NULL,
  -- Special teams
  `punt_return_yards` SMALLINT     NULL,
  `kick_return_yards` SMALLINT     NULL,
  `field_goals_made` TINYINT UNSIGNED NULL,
  `field_goals_att` TINYINT UNSIGNED NULL,
  -- Derived
  `spread_result`   DECIMAL(5,1)   NULL COMMENT 'Actual margin vs spread',
  `ats_result`      ENUM('cover','push','fail') NULL COMMENT 'Against the spread',
  `over_under_result` ENUM('over','push','under') NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_game_team` (`game_id`, `team_id`),
  INDEX `ix_gamestat_game` (`game_id`),
  INDEX `ix_gamestat_team` (`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_player_game_stat ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_player_game_stat` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `game_id`         BIGINT UNSIGNED NOT NULL,
  `player_id`       BIGINT UNSIGNED NOT NULL,
  `team_id`         BIGINT UNSIGNED NOT NULL,
  -- Passing
  `pass_completions` TINYINT UNSIGNED NULL,
  `pass_attempts`   TINYINT UNSIGNED NULL,
  `pass_yards`      SMALLINT       NULL,
  `pass_tds`        TINYINT UNSIGNED NULL,
  `interceptions_thrown` TINYINT UNSIGNED NULL,
  `passer_rating`   DECIMAL(5,1)   NULL,
  `sacks_taken`     TINYINT UNSIGNED NULL,
  -- Rushing
  `rush_attempts`   TINYINT UNSIGNED NULL,
  `rush_yards`      SMALLINT       NULL,
  `rush_tds`        TINYINT UNSIGNED NULL,
  `yards_per_carry` DECIMAL(4,1)   NULL,
  -- Receiving
  `targets`         TINYINT UNSIGNED NULL,
  `receptions`      TINYINT UNSIGNED NULL,
  `receiving_yards` SMALLINT       NULL,
  `receiving_tds`   TINYINT UNSIGNED NULL,
  -- Defense
  `tackles_total`   TINYINT UNSIGNED NULL,
  `tackles_solo`    TINYINT UNSIGNED NULL,
  `sacks_made`      DECIMAL(3,1)   NULL,
  `ints_made`       TINYINT UNSIGNED NULL,
  `passes_defended` TINYINT UNSIGNED NULL,
  `forced_fumbles`  TINYINT UNSIGNED NULL,
  -- Kicking
  `fg_made`         TINYINT UNSIGNED NULL,
  `fg_attempted`    TINYINT UNSIGNED NULL,
  `fg_long`         TINYINT UNSIGNED NULL,
  `xp_made`         TINYINT UNSIGNED NULL,
  `xp_attempted`    TINYINT UNSIGNED NULL,
  -- Fantasy
  `fantasy_points_std` DECIMAL(6,2) NULL COMMENT 'Standard scoring',
  `fantasy_points_ppr` DECIMAL(6,2) NULL COMMENT 'PPR scoring',
  `fantasy_points_half` DECIMAL(6,2) NULL COMMENT 'Half-PPR',
  `snaps_played`    TINYINT UNSIGNED NULL,
  `snap_pct`        DECIMAL(4,1)   NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_player_game` (`game_id`, `player_id`),
  INDEX `ix_playerstat_player` (`player_id`),
  INDEX `ix_playerstat_game` (`game_id`),
  INDEX `ix_playerstat_team` (`team_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_injury_report ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_injury_report` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `player_id`       BIGINT UNSIGNED NOT NULL,
  `team_id`         BIGINT UNSIGNED NOT NULL,
  `report_date`     DATE           NOT NULL,
  `season`          SMALLINT       NOT NULL,
  `week`            TINYINT        NOT NULL,
  `injury_type`     VARCHAR(200)   NULL COMMENT 'knee, hamstring, concussion, etc.',
  `practice_status` ENUM('full','limited','dnp') NULL COMMENT 'Did Not Practice',
  `game_status`     ENUM('active','questionable','doubtful','out','ir','pup') NULL,
  `notes`           TEXT           NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_injury_player` (`player_id`, `report_date`),
  INDEX `ix_injury_week` (`season`, `week`),
  INDEX `ix_injury_status` (`game_status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- SPORTS NFL — Internal Layer (ratings, projections, predictions)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `nfl_internal`;

-- ─── fact_team_rating ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_team_rating` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `team_id`         BIGINT UNSIGNED NOT NULL,
  `season`          SMALLINT       NOT NULL,
  `week`            TINYINT        NOT NULL,
  `rated_at`        DATETIME       NOT NULL,
  `overall_rating`  DOUBLE         NOT NULL COMMENT 'Composite power rating',
  `offense_rating`  DOUBLE         NULL,
  `defense_rating`  DOUBLE         NULL,
  `special_teams_rating` DOUBLE    NULL,
  `elo_rating`      DOUBLE         NULL COMMENT 'ELO-style rating',
  `strength_of_schedule` DOUBLE    NULL,
  `point_differential` INT         NULL,
  `model_name`      VARCHAR(100)   NULL,
  `model_version`   VARCHAR(50)    NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_team_rating_week` (`team_id`, `season`, `week`),
  INDEX `ix_rating_season` (`season`, `week`),
  INDEX `ix_rating_overall` (`overall_rating`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_player_projection ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_player_projection` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `player_id`       BIGINT UNSIGNED NOT NULL,
  `game_id`         BIGINT UNSIGNED NULL,
  `season`          SMALLINT       NOT NULL,
  `week`            TINYINT        NOT NULL,
  `projected_at`    DATETIME       NOT NULL,
  -- Projected stats
  `proj_pass_yards` DOUBLE NULL, `proj_pass_tds` DOUBLE NULL,
  `proj_rush_yards` DOUBLE NULL, `proj_rush_tds` DOUBLE NULL,
  `proj_receptions` DOUBLE NULL, `proj_rec_yards` DOUBLE NULL, `proj_rec_tds` DOUBLE NULL,
  `proj_fantasy_std` DOUBLE NULL, `proj_fantasy_ppr` DOUBLE NULL,
  -- Confidence
  `confidence`      DOUBLE         NULL COMMENT '0 to 1',
  `floor`           DOUBLE         NULL COMMENT 'Low-end projection',
  `ceiling`         DOUBLE         NULL COMMENT 'High-end projection',
  `model_name`      VARCHAR(100)   NULL,
  `model_version`   VARCHAR(50)    NULL,
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_projection_player` (`player_id`, `season`, `week`),
  INDEX `ix_projection_week` (`season`, `week`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_game_prediction ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_game_prediction` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `game_id`         BIGINT UNSIGNED NOT NULL,
  `predicted_at`    DATETIME       NOT NULL,
  `predicted_winner_id` BIGINT UNSIGNED NOT NULL COMMENT 'FK to dim_team',
  `predicted_spread` DECIMAL(4,1)  NULL,
  `predicted_total` DECIMAL(5,1)   NULL,
  `home_win_prob`   DOUBLE         NULL COMMENT '0 to 1',
  `predicted_home_score` DOUBLE    NULL,
  `predicted_away_score` DOUBLE    NULL,
  `confidence`      DOUBLE         NULL,
  `model_name`      VARCHAR(100)   NOT NULL,
  `model_version`   VARCHAR(50)    NULL,
  -- Actuals (filled after game)
  `actual_winner_id` BIGINT UNSIGNED NULL,
  `actual_spread`   DECIMAL(4,1)   NULL,
  `actual_total`    SMALLINT UNSIGNED NULL,
  `was_correct`     TINYINT(1)     NULL,
  `ats_correct`     TINYINT(1)     NULL COMMENT 'Against the spread',
  `total_correct`   TINYINT(1)     NULL COMMENT 'Over/under',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `ix_prediction_game` (`game_id`),
  INDEX `ix_prediction_model` (`model_name`, `predicted_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- SPORTS NFL — Gold Layer (picks, standings, power rankings)
-- ═══════════════════════════════════════════════════════════════════════════════
USE `nfl_gold`;

-- ─── fact_weekly_picks ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_weekly_picks` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `season`          SMALLINT       NOT NULL,
  `week`            TINYINT        NOT NULL,
  `game_id`         BIGINT UNSIGNED NOT NULL,
  `pick_type`       ENUM('straight_up','ats','over_under') NOT NULL,
  `picked_team_id`  BIGINT UNSIGNED NULL COMMENT 'NULL for over/under picks',
  `pick_value`      VARCHAR(20)    NULL COMMENT 'team_abbr, over, under',
  `confidence_rank` TINYINT UNSIGNED NULL COMMENT 'Confidence pool ranking',
  `reasoning`       TEXT           NULL,
  `result`          ENUM('win','loss','push','pending') DEFAULT 'pending',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `ix_picks_season_week` (`season`, `week`),
  INDEX `ix_picks_game` (`game_id`),
  INDEX `ix_picks_result` (`result`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── fact_season_standing ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS `fact_season_standing` (
  `id`              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `season`          SMALLINT       NOT NULL,
  `week`            TINYINT        NOT NULL,
  `team_id`         BIGINT UNSIGNED NOT NULL,
  `wins`            TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `losses`          TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `ties`            TINYINT UNSIGNED NOT NULL DEFAULT 0,
  `win_pct`         DECIMAL(4,3)   NULL,
  `division_rank`   TINYINT UNSIGNED NULL,
  `conference_rank` TINYINT UNSIGNED NULL,
  `playoff_seed`    TINYINT UNSIGNED NULL,
  `points_for`      SMALLINT UNSIGNED NULL,
  `points_against`  SMALLINT UNSIGNED NULL,
  `point_diff`      SMALLINT       NULL,
  `streak`          VARCHAR(10)    NULL COMMENT 'W3, L1, etc.',
  `clinched`        VARCHAR(20)    NULL COMMENT 'division, wildcard, bye, eliminated',
  `created_at`      DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE INDEX `uq_standing_team_week` (`season`, `week`, `team_id`),
  INDEX `ix_standing_season` (`season`, `week`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ─── vw_power_rankings (view) ────────────────────────────────────────────────
CREATE OR REPLACE VIEW `vw_power_rankings` AS
SELECT
  r.`team_id`,
  r.`season`,
  r.`week`,
  r.`overall_rating`,
  r.`offense_rating`,
  r.`defense_rating`,
  r.`special_teams_rating`,
  r.`elo_rating`,
  r.`strength_of_schedule`,
  r.`point_differential`,
  r.`model_name`,
  RANK() OVER (PARTITION BY r.`season`, r.`week` ORDER BY r.`overall_rating` DESC) AS `power_rank`
FROM `nfl_internal`.`fact_team_rating` r
WHERE (r.`season`, r.`week`) = (
  SELECT `season`, `week`
  FROM `nfl_internal`.`fact_team_rating`
  ORDER BY `season` DESC, `week` DESC
  LIMIT 1
);


-- ─── MAINTENANCE DATABASE OBJECTS ──────────────────────────────────────────────
USE maintenance_db;

CREATE TABLE IF NOT EXISTS maintenance_log (
  id             BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_id         CHAR(36)     NOT NULL DEFAULT (UUID()),
  job_type       VARCHAR(64)  NOT NULL,
  schema_name    VARCHAR(64)  NOT NULL,
  table_name     VARCHAR(128) NOT NULL DEFAULT '*',
  status         ENUM('started','completed','failed','skipped') NOT NULL DEFAULT 'started',
  rows_affected  BIGINT       NULL,
  duration_ms    INT UNSIGNED NULL,
  message        TEXT         NULL,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_job_type  (job_type),
  INDEX idx_status    (status),
  INDEX idx_created   (created_at),
  INDEX idx_schema    (schema_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS table_health_snapshot (
  id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  captured_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  schema_name     VARCHAR(64)  NOT NULL,
  table_name      VARCHAR(128) NOT NULL,
  engine          VARCHAR(32)  NULL,
  row_count       BIGINT       NULL,
  data_length_mb  DECIMAL(12,2) NULL,
  index_length_mb DECIMAL(12,2) NULL,
  data_free_mb    DECIMAL(12,2) NULL,
  fragmentation_pct DECIMAL(5,2) NULL,
  INDEX idx_captured  (captured_at),
  INDEX idx_schema_table (schema_name, table_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS slow_query_summary (
  id            BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  captured_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  query_digest  TEXT         NOT NULL,
  exec_count    INT UNSIGNED NULL,
  avg_time_sec  DECIMAL(10,4) NULL,
  max_time_sec  DECIMAL(10,4) NULL,
  total_time_sec DECIMAL(14,4) NULL,
  schema_name   VARCHAR(64)  NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS settings_recommendations (
  id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  evaluated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  setting_name    VARCHAR(128) NOT NULL,
  current_value   TEXT         NULL,
  recommended_value TEXT       NULL,
  reason          TEXT         NULL,
  severity        ENUM('info','warning','critical') NOT NULL DEFAULT 'info',
  applied         TINYINT(1)   NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ═══════════════════════════════════════════════════════════════════════════════
-- UTILITY — Stored Procedures
-- ═══════════════════════════════════════════════════════════════════════════════

-- Idempotent column addition — safe to call multiple times.
-- Usage: CALL add_column_if_not_exists('schema', 'table', 'column', 'TYPE DEFAULT ...');
DELIMITER //

DROP PROCEDURE IF EXISTS add_column_if_not_exists//

CREATE PROCEDURE add_column_if_not_exists(
    IN p_schema VARCHAR(100),
    IN p_table VARCHAR(100),
    IN p_column VARCHAR(100),
    IN p_definition VARCHAR(500)
)
BEGIN
    DECLARE col_count INT;

    SELECT COUNT(*)
    INTO col_count
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = p_schema
      AND TABLE_NAME = p_table
      AND COLUMN_NAME = p_column;

    IF col_count = 0 THEN
        SET @sql = CONCAT(
            'ALTER TABLE `', p_schema, '`.`', p_table,
            '` ADD COLUMN `', p_column, '` ', p_definition
        );
        PREPARE stmt FROM @sql;
        EXECUTE stmt;
        DEALLOCATE PREPARE stmt;
    END IF;
END//

DELIMITER ;
