CREATE SCHEMA IF NOT EXISTS nfl_silver;
CREATE SCHEMA IF NOT EXISTS ncaa_mbb_silver;
CREATE SCHEMA IF NOT EXISTS mlb_silver;
CREATE SCHEMA IF NOT EXISTS modeling_silver;
CREATE SCHEMA IF NOT EXISTS research_gold;
CREATE SCHEMA IF NOT EXISTS modeling_internal;

USE nfl_silver;
CREATE TABLE IF NOT EXISTS fact_game_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    game_date DATETIME,
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    home_score INT,
    away_score INT,
    margin INT,
    is_postseason_game TINYINT DEFAULT 0,
    round_name VARCHAR(100),
    playoff_experience_home DOUBLE DEFAULT 0,
    playoff_experience_away DOUBLE DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_game_results_game_id (game_id)
);
CREATE TABLE IF NOT EXISTS fact_market_odds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    sportsbook VARCHAR(100),
    spread DECIMAL(6,2),
    moneyline_home INT,
    moneyline_away INT,
    total_line DECIMAL(6,2),
    market_timestamp DATETIME,
    INDEX idx_market_odds_game_id (game_id),
    INDEX idx_market_odds_timestamp (market_timestamp)
);

CREATE TABLE IF NOT EXISTS fact_game_context (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    week_number INT,
    season INT,
    venue_name VARCHAR(150),
    venue_city VARCHAR(100),
    surface ENUM('grass','turf'),
    indoor TINYINT DEFAULT 0,
    attendance INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_game_context_game_id (game_id)
);
CREATE TABLE IF NOT EXISTS fact_team_game_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    team VARCHAR(100) NOT NULL,
    side ENUM('home','away') NOT NULL,
    total_yards INT,
    passing_yards INT,
    rushing_yards INT,
    turnovers INT,
    third_down_att INT,
    third_down_conv INT,
    red_zone_att INT,
    red_zone_conv INT,
    time_of_possession_secs INT,
    sacks_allowed INT,
    penalty_yards INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_team_game_stats (game_id, team),
    INDEX idx_team_game_stats_team (team)
);
CREATE TABLE IF NOT EXISTS fact_team_standing (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    team VARCHAR(100) NOT NULL,
    side ENUM('home','away') NOT NULL,
    season INT,
    week INT,
    wins INT,
    losses INT,
    win_pct DOUBLE,
    home_wins INT,
    home_losses INT,
    away_wins INT,
    away_losses INT,
    current_streak INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_team_standing (game_id, team),
    INDEX idx_team_standing_team (team, season)
);
CREATE TABLE IF NOT EXISTS fact_injury_report (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    team VARCHAR(100) NOT NULL,
    athlete_id VARCHAR(50) NOT NULL,
    athlete_name VARCHAR(150),
    position VARCHAR(20),
    injury_status VARCHAR(30),
    injury_detail VARCHAR(200),
    report_date DATE,
    UNIQUE KEY uq_injury_report (game_id, athlete_id),
    INDEX idx_injury_report_game (game_id),
    INDEX idx_injury_report_team (team),
    INDEX idx_injury_report_position (position)
);
CREATE TABLE IF NOT EXISTS fact_game_weather (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    temperature_f DECIMAL(5,1),
    wind_speed_mph DECIMAL(5,1),
    wind_direction VARCHAR(20),
    precipitation_in DECIMAL(5,2),
    humidity_pct INT,
    conditions VARCHAR(50),
    UNIQUE KEY uq_game_weather_game_id (game_id)
);

USE ncaa_mbb_silver;
CREATE TABLE IF NOT EXISTS fact_game_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    game_date DATETIME,
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    home_score INT,
    away_score INT,
    margin INT,
    is_tournament_game TINYINT DEFAULT 0,
    round_name VARCHAR(100),
    seed_home INT,
    seed_away INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_game_results_game_id (game_id)
);
CREATE TABLE IF NOT EXISTS fact_market_odds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    sportsbook VARCHAR(100),
    spread DECIMAL(6,2),
    moneyline_home INT,
    moneyline_away INT,
    total_line DECIMAL(6,2),
    market_timestamp DATETIME,
    INDEX idx_market_odds_game_id (game_id),
    INDEX idx_market_odds_timestamp (market_timestamp)
);
CREATE TABLE IF NOT EXISTS fact_seed_history (
    seed INT PRIMARY KEY,
    win_pct DOUBLE,
    upset_win_pct DOUBLE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS fact_mbb_game_context (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    neutral_site TINYINT DEFAULT 0,
    is_conference_game TINYINT DEFAULT 0,
    venue_name VARCHAR(150),
    venue_city VARCHAR(100),
    attendance INT,
    season INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_mbb_game_context_game_id (game_id)
);
CREATE TABLE IF NOT EXISTS fact_mbb_game_stats (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    team VARCHAR(100) NOT NULL,
    side ENUM('home','away') NOT NULL,
    fg_made INT,
    fg_att INT,
    fg_pct FLOAT,
    three_pt_made INT,
    three_pt_att INT,
    three_pt_pct FLOAT,
    ft_made INT,
    ft_att INT,
    ft_pct FLOAT,
    total_rebounds INT,
    off_rebounds INT,
    def_rebounds INT,
    assists INT,
    steals INT,
    blocks INT,
    turnovers INT,
    turnover_points INT,
    fast_break_points INT,
    points_in_paint INT,
    largest_lead INT,
    fouls INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_mbb_game_stats (game_id, side),
    INDEX idx_mbb_game_stats_team (team)
);
CREATE TABLE IF NOT EXISTS fact_mbb_team_standing (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    team VARCHAR(100) NOT NULL,
    side ENUM('home','away') NOT NULL,
    wins INT,
    losses INT,
    win_pct DOUBLE,
    home_wins INT,
    home_losses INT,
    road_wins INT,
    road_losses INT,
    conf_wins INT,
    conf_losses INT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_mbb_team_standing (game_id, side),
    INDEX idx_mbb_team_standing_team (team)
);
CREATE TABLE IF NOT EXISTS fact_mbb_poll_ranking (
    id INT AUTO_INCREMENT PRIMARY KEY,
    team_name VARCHAR(100) NOT NULL,
    team_espn_id VARCHAR(20) NOT NULL,
    poll_type ENUM('ap','coaches') NOT NULL,
    rank TINYINT,
    previous_rank TINYINT,
    trend INT,
    poll_points FLOAT,
    first_place_votes INT,
    snapshot_date DATE NOT NULL,
    UNIQUE KEY uq_mbb_poll_ranking (team_espn_id, poll_type, snapshot_date),
    INDEX idx_mbb_poll_ranking_team (team_name, poll_type, snapshot_date)
);
CREATE TABLE IF NOT EXISTS fact_mbb_bpi (
    id INT AUTO_INCREMENT PRIMARY KEY,
    team_espn_id VARCHAR(20) NOT NULL,
    team_name VARCHAR(100),
    season YEAR NOT NULL,
    snapshot_date DATE NOT NULL,
    bpi FLOAT,
    bpi_rank SMALLINT,
    bpi_offense FLOAT,
    bpi_defense FLOAT,
    sor FLOAT,
    sor_rank SMALLINT,
    sos_past FLOAT,
    sos_past_rank SMALLINT,
    proj_tournament_seed TINYINT,
    chance_sweet16 FLOAT,
    chance_elite8 FLOAT,
    chance_final4 FLOAT,
    chance_champion FLOAT,
    UNIQUE KEY uq_mbb_bpi (team_espn_id, season, snapshot_date),
    INDEX idx_mbb_bpi_team (team_name, season, snapshot_date)
);
CREATE TABLE IF NOT EXISTS fact_mbb_game_predictor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    home_pred_win_pct FLOAT,
    away_pred_win_pct FLOAT,
    home_pred_mov FLOAT,
    matchup_quality FLOAT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_mbb_game_predictor_game_id (game_id)
);

USE mlb_silver;
CREATE TABLE IF NOT EXISTS fact_game_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    game_date DATETIME,
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    home_score INT,
    away_score INT,
    margin INT,
    is_postseason_game TINYINT DEFAULT 0,
    round_name VARCHAR(100),
    playoff_experience_home DOUBLE DEFAULT 0,
    playoff_experience_away DOUBLE DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_game_results_game_id (game_id)
);
CREATE TABLE IF NOT EXISTS fact_market_odds (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    sportsbook VARCHAR(100),
    spread DECIMAL(6,2),
    moneyline_home INT,
    moneyline_away INT,
    total_line DECIMAL(6,2),
    market_timestamp DATETIME,
    INDEX idx_market_odds_game_id (game_id),
    INDEX idx_market_odds_timestamp (market_timestamp)
);

USE modeling_silver;
CREATE TABLE IF NOT EXISTS fact_training_features (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sport VARCHAR(20) NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    game_date DATETIME,
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    target_home_win TINYINT,
    target_cover_home TINYINT,
    target_total_over TINYINT,
    feature_version VARCHAR(50) NOT NULL,
    feature_payload JSON NOT NULL,
    training_timestamp DATETIME,
    UNIQUE KEY uq_training_features_sport_game (sport, game_id),
    INDEX idx_training_features_sport_date (sport, game_date),
    INDEX idx_training_features_feature_version (feature_version)
);

USE modeling_internal;

-- Tracks every model trained and promoted.  Each sport+target combination has
-- at most ONE row with status='production' at any time.  The /promote-model
-- endpoint demotes the prior production row and inserts a new one.
CREATE TABLE IF NOT EXISTS fact_model_registry (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sport VARCHAR(20) NOT NULL,
    target VARCHAR(30) NOT NULL,
    model_version VARCHAR(100) NOT NULL,
    status ENUM('candidate','production','retired') NOT NULL DEFAULT 'candidate',

    -- Hyperparameters
    hidden_dim INT,
    dropout DECIMAL(5,3),
    learning_rate DECIMAL(10,8),
    batch_size INT,
    epochs INT,

    -- Cross-validation metrics (computed before promotion)
    cv_folds INT,
    cv_avg_loss DECIMAL(10,6),
    cv_avg_accuracy DECIMAL(6,4),
    cv_avg_auc DECIMAL(6,4),
    cv_fold_losses JSON,
    cv_fold_accuracies JSON,
    cv_fold_aucs JSON,

    -- Training results (full-data refit)
    train_rows INT,
    train_final_loss DECIMAL(10,6),
    feature_version VARCHAR(50),
    feature_count INT,

    -- File paths
    model_path VARCHAR(500),
    metadata_path VARCHAR(500),

    -- Timestamps
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    promoted_at TIMESTAMP NULL,
    retired_at TIMESTAMP NULL,

    INDEX idx_model_registry_sport_target (sport, target, status),
    INDEX idx_model_registry_version (model_version)
);

CREATE TABLE IF NOT EXISTS fact_model_predictions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sport VARCHAR(20) NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    predicted_win_prob DECIMAL(6,4),
    predicted_margin DECIMAL(6,2),
    model_version VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_model_predictions_sport_game (sport, game_id)
);
CREATE TABLE IF NOT EXISTS fact_trading_signals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sport VARCHAR(20) NOT NULL,
    game_id VARCHAR(50) NOT NULL,
    signal_strength DECIMAL(6,4),
    expected_value DECIMAL(6,4),
    risk_score DECIMAL(6,4),
    allocation DECIMAL(12,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_trading_signals_sport_game (sport, game_id)
);
CREATE TABLE IF NOT EXISTS fact_portfolio_simulations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    simulation_id VARCHAR(50) NOT NULL,
    sport VARCHAR(20),
    bankroll DECIMAL(12,2),
    max_drawdown DECIMAL(8,4),
    sharpe_ratio DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_portfolio_simulations_simulation_id (simulation_id)
);

-- =====================================================================
-- Bracket simulation tables
-- =====================================================================

CREATE TABLE IF NOT EXISTS fact_bracket_fields (
    id INT AUTO_INCREMENT PRIMARY KEY,
    season INT NOT NULL,
    team_name VARCHAR(100) NOT NULL,
    team_espn_id VARCHAR(20),
    seed INT NOT NULL,
    region VARCHAR(50) NOT NULL,
    is_play_in TINYINT DEFAULT 0,
    play_in_matchup_id VARCHAR(50),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_bracket_fields_season_team (season, team_name),
    INDEX idx_bracket_fields_season (season),
    INDEX idx_bracket_fields_region_seed (region, seed)
);

CREATE TABLE IF NOT EXISTS fact_bracket_simulations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    simulation_id VARCHAR(100) NOT NULL,
    season INT NOT NULL,
    num_simulations INT NOT NULL,
    pool_size INT,
    scoring_system VARCHAR(50) DEFAULT 'espn_standard',
    risk_tolerance DECIMAL(4,3),
    model_version VARCHAR(100),
    simulation_counter INT NOT NULL DEFAULT 1,
    priority_ranking INT NOT NULL DEFAULT 1,
    is_default TINYINT(1) NOT NULL DEFAULT 0,
    run_batch_id VARCHAR(36),
    expected_score DOUBLE,
    champion_pick VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_bracket_simulations_id (simulation_id),
    INDEX idx_bracket_simulations_season (season),
    INDEX idx_bracket_simulations_batch (run_batch_id)
);

-- Bet tracking for go-forward accuracy monitoring
CREATE TABLE IF NOT EXISTS fact_bet_tracking (
    id INT AUTO_INCREMENT PRIMARY KEY,
    game_id VARCHAR(50) NOT NULL,
    sport VARCHAR(20) NOT NULL,
    game_date DATE NOT NULL,
    home_team VARCHAR(100),
    away_team VARCHAR(100),
    bet_type VARCHAR(20) NOT NULL,
    pick VARCHAR(200) NOT NULL,
    odds_american INT,
    model_probability DOUBLE,
    edge DOUBLE,
    expected_value DOUBLE,
    wager_amount DOUBLE,
    recommended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actual_outcome TINYINT(1),
    resolved_at TIMESTAMP NULL,
    profit_loss DOUBLE,
    week_number INT,
    year INT,
    INDEX idx_bet_tracking_game (game_id, bet_type),
    INDEX idx_bet_tracking_week (year, week_number),
    INDEX idx_bet_tracking_sport (sport, game_date)
);

CREATE TABLE IF NOT EXISTS fact_bracket_picks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    simulation_id VARCHAR(100) NOT NULL,
    round_number INT NOT NULL,
    game_number INT NOT NULL,
    region VARCHAR(50),
    higher_seed_team VARCHAR(100),
    lower_seed_team VARCHAR(100),
    predicted_winner VARCHAR(100) NOT NULL,
    win_probability DECIMAL(6,4),
    is_upset TINYINT DEFAULT 0,
    is_contrarian TINYINT DEFAULT 0,
    advancement_probability DECIMAL(6,4),
    pick_leverage DECIMAL(8,4),
    actual_winner VARCHAR(100),
    is_correct TINYINT,
    INDEX idx_bracket_picks_sim (simulation_id),
    INDEX idx_bracket_picks_round (simulation_id, round_number)
);

CREATE TABLE IF NOT EXISTS fact_bracket_team_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    season INT NOT NULL,
    team_name VARCHAR(100) NOT NULL,
    team_espn_id VARCHAR(20),
    seed INT,
    feature_payload JSON NOT NULL,
    profile_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_bracket_team_profiles (season, team_name),
    INDEX idx_bracket_team_profiles_season (season)
);


-- =====================================================================
-- Incremental column management (dbt-style)
-- =====================================================================
-- This procedure safely adds a column to a table if it does not already
-- exist.  It is idempotent — calling it multiple times is safe.
--
-- Usage:
--   CALL add_column_if_not_exists('schema', 'table', 'column', 'TYPE DEFAULT ...');
-- =====================================================================

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


-- =====================================================================
-- Sports news table (LLM-summarised headlines)
-- =====================================================================

USE modeling_internal;

CREATE TABLE IF NOT EXISTS fact_sports_news (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sport VARCHAR(20) NOT NULL,
    headline VARCHAR(500) NOT NULL,
    description TEXT,
    article_url VARCHAR(1000),
    source VARCHAR(100) DEFAULT 'espn',
    published_at DATETIME,
    llm_summary TEXT,
    llm_model VARCHAR(100),
    focus_team VARCHAR(100),
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_sports_news_url (article_url(500)),
    INDEX idx_sports_news_sport_date (sport, published_at),
    INDEX idx_sports_news_focus_team (focus_team)
);

-- =====================================================================
-- Column migrations
-- =====================================================================
-- Add new CALL statements below as the schema evolves.  Each call is
-- idempotent — safe to run on every container restart or via /migrate-db.
--
-- Format:
--   CALL add_column_if_not_exists('schema', 'table', 'column', 'TYPE DEFAULT val');
-- =====================================================================

-- (add future column migrations here)
