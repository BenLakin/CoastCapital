"""
modeling_data.py — Feature materialisation and modeling frame loading.

Provides four public functions:

- ``load_base_frame(sport)``       — raw SQL join into a flat DataFrame
- ``build_feature_frame(sport)``   — applies all feature engineering transforms
- ``materialize_features_to_modeling_silver(sport)``
                                   — writes engineered features to modeling_silver
- ``load_modeling_frame(sport)``   — reads from modeling_silver for training/scoring
"""

import json
import logging

import pandas as pd

from database import get_connection
from features.feature_engineering import finalize_feature_frame
from features.feature_registry import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

SPORT_TO_SCHEMA = {
    "nfl": "nfl_silver",
    "ncaa_mbb": "ncaa_mbb_silver",
    "mlb": "mlb_silver",
}

FEATURE_VERSION = "v1"

def load_base_frame(sport: str) -> pd.DataFrame:
    """Load the raw feature base frame for *sport* directly from silver tables.

    Executes a sport-specific SQL query that joins game results with market
    odds, team standings, boxscore stats, and sport-specific enrichments.

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, or ``"mlb"``.

    Returns
    -------
    pandas.DataFrame with one row per game, or an empty DataFrame if the
    schema is not recognised or the query returns no rows.

    Raises
    ------
    KeyError
        If *sport* is not in SPORT_TO_SCHEMA.
    """
    if sport not in SPORT_TO_SCHEMA:
        raise KeyError(f"Unsupported sport '{sport}'. Choose from: {list(SPORT_TO_SCHEMA)}")

    schema = SPORT_TO_SCHEMA[sport]
    logger.info("load_base_frame: sport=%s  schema=%s", sport, schema)
    conn = get_connection(schema)

    if sport == "ncaa_mbb":
        query = '''
        SELECT
            'ncaa_mbb' AS sport,
            g.game_id,
            g.game_date,
            g.home_team,
            g.away_team,
            g.home_score,
            g.away_score,
            g.margin,
            COALESCE(g.is_tournament_game, 0) AS is_tournament_game,
            COALESCE(g.is_tournament_game, 0) AS is_postseason_game,
            COALESCE(g.round_name, '') AS round_name,
            COALESCE(g.seed_home, 0) AS seed_home,
            COALESCE(g.seed_away, 0) AS seed_away,
            0.0 AS playoff_experience_home,
            0.0 AS playoff_experience_away,
            COALESCE(hh.win_pct, 0) AS home_seed_hist_win_pct,
            COALESCE(ah.win_pct, 0) AS away_seed_hist_win_pct,
            COALESCE(hh.upset_win_pct, 0) AS home_seed_hist_upset_win_pct,
            COALESCE(ah.upset_win_pct, 0) AS away_seed_hist_upset_win_pct,
            o.spread AS market_spread,
            o.total_line AS market_total_line,
            o.moneyline_home AS market_moneyline_home,
            o.moneyline_away AS market_moneyline_away,
            -- game context
            COALESCE(gc.neutral_site, 0) AS neutral_site,
            COALESCE(gc.is_conference_game, 0) AS is_conference_game,
            COALESCE(gc.attendance, 0) AS attendance,
            COALESCE(gc.season, 0) AS season,
            -- home boxscore
            COALESCE(hgs.fg_pct, 0) AS home_fg_pct,
            COALESCE(hgs.three_pt_pct, 0) AS home_three_pt_pct,
            COALESCE(hgs.ft_pct, 0) AS home_ft_pct,
            COALESCE(hgs.total_rebounds, 0) AS home_total_rebounds,
            COALESCE(hgs.off_rebounds, 0) AS home_off_rebounds,
            COALESCE(hgs.assists, 0) AS home_assists,
            COALESCE(hgs.steals, 0) AS home_steals,
            COALESCE(hgs.blocks, 0) AS home_blocks,
            COALESCE(hgs.turnovers, 0) AS home_turnovers_mbb,
            COALESCE(hgs.fast_break_points, 0) AS home_fast_break_points,
            COALESCE(hgs.points_in_paint, 0) AS home_points_in_paint,
            -- away boxscore
            COALESCE(ags.fg_pct, 0) AS away_fg_pct,
            COALESCE(ags.three_pt_pct, 0) AS away_three_pt_pct,
            COALESCE(ags.ft_pct, 0) AS away_ft_pct,
            COALESCE(ags.total_rebounds, 0) AS away_total_rebounds,
            COALESCE(ags.off_rebounds, 0) AS away_off_rebounds,
            COALESCE(ags.assists, 0) AS away_assists,
            COALESCE(ags.steals, 0) AS away_steals,
            COALESCE(ags.blocks, 0) AS away_blocks,
            COALESCE(ags.turnovers, 0) AS away_turnovers_mbb,
            COALESCE(ags.fast_break_points, 0) AS away_fast_break_points,
            COALESCE(ags.points_in_paint, 0) AS away_points_in_paint,
            -- home standing
            COALESCE(hts.wins, 0) AS home_wins,
            COALESCE(hts.losses, 0) AS home_losses,
            COALESCE(hts.win_pct, 0.0) AS home_win_pct,
            COALESCE(hts.home_wins, 0) AS home_home_wins,
            COALESCE(hts.home_losses, 0) AS home_home_losses,
            COALESCE(hts.road_wins, 0) AS home_away_wins,
            COALESCE(hts.road_losses, 0) AS home_away_losses,
            COALESCE(hts.conf_wins, 0) AS home_conf_wins,
            COALESCE(hts.conf_losses, 0) AS home_conf_losses,
            -- away standing
            COALESCE(ats.wins, 0) AS away_wins,
            COALESCE(ats.losses, 0) AS away_losses,
            COALESCE(ats.win_pct, 0.0) AS away_win_pct,
            COALESCE(ats.home_wins, 0) AS away_home_wins,
            COALESCE(ats.home_losses, 0) AS away_home_losses,
            COALESCE(ats.road_wins, 0) AS away_away_wins,
            COALESCE(ats.road_losses, 0) AS away_away_losses,
            COALESCE(ats.conf_wins, 0) AS away_conf_wins,
            COALESCE(ats.conf_losses, 0) AS away_conf_losses,
            -- home BPI
            COALESCE(hb.bpi, 0) AS home_bpi,
            COALESCE(hb.bpi_offense, 0) AS home_bpi_offense,
            COALESCE(hb.bpi_defense, 0) AS home_bpi_defense,
            COALESCE(hb.sor, 0) AS home_sor,
            COALESCE(hb.sos_past, 0) AS home_sos_past,
            COALESCE(hb.proj_tournament_seed, 0) AS home_proj_tournament_seed,
            -- away BPI
            COALESCE(ab.bpi, 0) AS away_bpi,
            COALESCE(ab.bpi_offense, 0) AS away_bpi_offense,
            COALESCE(ab.bpi_defense, 0) AS away_bpi_defense,
            COALESCE(ab.sor, 0) AS away_sor,
            COALESCE(ab.sos_past, 0) AS away_sos_past,
            COALESCE(ab.proj_tournament_seed, 0) AS away_proj_tournament_seed,
            -- poll rankings (AP)
            COALESCE(hp.rank, 99) AS home_ap_rank,
            COALESCE(ap_rank.rank, 99) AS away_ap_rank,
            -- game predictor
            COALESCE(gp.home_pred_win_pct, 0) AS home_pred_win_pct,
            COALESCE(gp.home_pred_mov, 0) AS home_pred_mov,
            COALESCE(gp.matchup_quality, 0) AS matchup_quality
        FROM fact_game_results g
        LEFT JOIN (
            SELECT t1.*
            FROM fact_market_odds t1
            INNER JOIN (
                SELECT mo.game_id, MAX(mo.market_timestamp) AS max_ts
                FROM fact_market_odds mo
                INNER JOIN fact_game_results gr ON mo.game_id = gr.game_id
                WHERE mo.market_timestamp < gr.game_date
                GROUP BY mo.game_id
            ) latest
              ON t1.game_id = latest.game_id
             AND t1.market_timestamp = latest.max_ts
        ) o
          ON g.game_id = o.game_id
        LEFT JOIN fact_seed_history hh
          ON g.seed_home = hh.seed
        LEFT JOIN fact_seed_history ah
          ON g.seed_away = ah.seed
        LEFT JOIN fact_mbb_game_context gc ON g.game_id = gc.game_id
        LEFT JOIN fact_mbb_game_stats hgs ON g.game_id = hgs.game_id AND hgs.side = 'home'
        LEFT JOIN fact_mbb_game_stats ags ON g.game_id = ags.game_id AND ags.side = 'away'
        LEFT JOIN fact_mbb_team_standing hts ON g.game_id = hts.game_id AND hts.side = 'home'
        LEFT JOIN fact_mbb_team_standing ats ON g.game_id = ats.game_id AND ats.side = 'away'
        LEFT JOIN fact_mbb_bpi hb
          ON hb.team_name = g.home_team
         AND hb.season = gc.season
         AND hb.snapshot_date = (
             SELECT MAX(snapshot_date) FROM fact_mbb_bpi
             WHERE team_name = g.home_team AND season = gc.season
               AND snapshot_date <= DATE(g.game_date)
         )
        LEFT JOIN fact_mbb_bpi ab
          ON ab.team_name = g.away_team
         AND ab.season = gc.season
         AND ab.snapshot_date = (
             SELECT MAX(snapshot_date) FROM fact_mbb_bpi
             WHERE team_name = g.away_team AND season = gc.season
               AND snapshot_date <= DATE(g.game_date)
         )
        LEFT JOIN fact_mbb_poll_ranking hp
          ON hp.team_name = g.home_team
         AND hp.poll_type = 'ap'
         AND hp.snapshot_date = (
             SELECT MAX(snapshot_date) FROM fact_mbb_poll_ranking
             WHERE team_name = g.home_team AND poll_type = 'ap'
               AND snapshot_date <= DATE(g.game_date)
         )
        LEFT JOIN fact_mbb_poll_ranking ap_rank
          ON ap_rank.team_name = g.away_team
         AND ap_rank.poll_type = 'ap'
         AND ap_rank.snapshot_date = (
             SELECT MAX(snapshot_date) FROM fact_mbb_poll_ranking
             WHERE team_name = g.away_team AND poll_type = 'ap'
               AND snapshot_date <= DATE(g.game_date)
         )
        LEFT JOIN fact_mbb_game_predictor gp ON g.game_id = gp.game_id
        ORDER BY g.game_date
        '''
    elif sport == "nfl":
        query = '''
        SELECT
            'nfl' AS sport,
            g.game_id,
            g.game_date,
            g.home_team,
            g.away_team,
            g.home_score,
            g.away_score,
            g.margin,
            0 AS is_tournament_game,
            COALESCE(g.is_postseason_game, 0) AS is_postseason_game,
            COALESCE(g.round_name, '') AS round_name,
            0 AS seed_home,
            0 AS seed_away,
            COALESCE(g.playoff_experience_home, 0) AS playoff_experience_home,
            COALESCE(g.playoff_experience_away, 0) AS playoff_experience_away,
            0.0 AS home_seed_hist_win_pct,
            0.0 AS away_seed_hist_win_pct,
            0.0 AS home_seed_hist_upset_win_pct,
            0.0 AS away_seed_hist_upset_win_pct,
            o.spread AS market_spread,
            o.total_line AS market_total_line,
            o.moneyline_home AS market_moneyline_home,
            o.moneyline_away AS market_moneyline_away,
            COALESCE(gc.week_number, 0) AS week_number,
            COALESCE(gc.season, 0) AS season,
            COALESCE(gc.indoor, 0) AS indoor,
            COALESCE(gc.surface, 'turf') AS surface,
            COALESCE(gc.attendance, 0) AS attendance,
            COALESCE(hgs.total_yards, 0) AS home_total_yards,
            COALESCE(hgs.passing_yards, 0) AS home_passing_yards,
            COALESCE(hgs.rushing_yards, 0) AS home_rushing_yards,
            COALESCE(hgs.turnovers, 0) AS home_turnovers,
            COALESCE(hgs.third_down_att, 0) AS home_third_down_att,
            COALESCE(hgs.third_down_conv, 0) AS home_third_down_conv,
            COALESCE(hgs.red_zone_att, 0) AS home_red_zone_att,
            COALESCE(hgs.red_zone_conv, 0) AS home_red_zone_conv,
            COALESCE(hgs.time_of_possession_secs, 0) AS home_possession_secs,
            COALESCE(hgs.sacks_allowed, 0) AS home_sacks_allowed,
            COALESCE(hgs.penalty_yards, 0) AS home_penalty_yards,
            COALESCE(ags.total_yards, 0) AS away_total_yards,
            COALESCE(ags.passing_yards, 0) AS away_passing_yards,
            COALESCE(ags.rushing_yards, 0) AS away_rushing_yards,
            COALESCE(ags.turnovers, 0) AS away_turnovers,
            COALESCE(ags.third_down_att, 0) AS away_third_down_att,
            COALESCE(ags.third_down_conv, 0) AS away_third_down_conv,
            COALESCE(ags.red_zone_att, 0) AS away_red_zone_att,
            COALESCE(ags.red_zone_conv, 0) AS away_red_zone_conv,
            COALESCE(ags.time_of_possession_secs, 0) AS away_possession_secs,
            COALESCE(ags.sacks_allowed, 0) AS away_sacks_allowed,
            COALESCE(ags.penalty_yards, 0) AS away_penalty_yards,
            COALESCE(hts.wins, 0) AS home_wins,
            COALESCE(hts.losses, 0) AS home_losses,
            COALESCE(hts.win_pct, 0.0) AS home_win_pct,
            COALESCE(hts.home_wins, 0) AS home_home_wins,
            COALESCE(hts.home_losses, 0) AS home_home_losses,
            COALESCE(hts.away_wins, 0) AS home_away_wins,
            COALESCE(hts.away_losses, 0) AS home_away_losses,
            COALESCE(hts.current_streak, 0) AS home_streak,
            COALESCE(ats.wins, 0) AS away_wins,
            COALESCE(ats.losses, 0) AS away_losses,
            COALESCE(ats.win_pct, 0.0) AS away_win_pct,
            COALESCE(ats.home_wins, 0) AS away_home_wins,
            COALESCE(ats.home_losses, 0) AS away_home_losses,
            COALESCE(ats.away_wins, 0) AS away_away_wins,
            COALESCE(ats.away_losses, 0) AS away_away_losses,
            COALESCE(ats.current_streak, 0) AS away_streak,
            COALESCE(ir_h.total_out, 0) AS home_players_out,
            COALESCE(ir_h.skill_out, 0) AS home_skill_out,
            COALESCE(ir_h.qb_out, 0) AS home_qb_out,
            COALESCE(ir_h.total_doubtful, 0) AS home_players_doubtful,
            COALESCE(ir_a.total_out, 0) AS away_players_out,
            COALESCE(ir_a.skill_out, 0) AS away_skill_out,
            COALESCE(ir_a.qb_out, 0) AS away_qb_out,
            COALESCE(ir_a.total_doubtful, 0) AS away_players_doubtful
        FROM fact_game_results g
        LEFT JOIN (
            SELECT t1.*
            FROM fact_market_odds t1
            INNER JOIN (
                SELECT mo.game_id, MAX(mo.market_timestamp) AS max_ts
                FROM fact_market_odds mo
                INNER JOIN fact_game_results gr ON mo.game_id = gr.game_id
                WHERE mo.market_timestamp < gr.game_date
                GROUP BY mo.game_id
            ) latest
              ON t1.game_id = latest.game_id
             AND t1.market_timestamp = latest.max_ts
        ) o ON g.game_id = o.game_id
        LEFT JOIN fact_game_context gc ON g.game_id = gc.game_id
        LEFT JOIN fact_team_game_stats hgs ON g.game_id = hgs.game_id AND hgs.side = 'home'
        LEFT JOIN fact_team_game_stats ags ON g.game_id = ags.game_id AND ags.side = 'away'
        LEFT JOIN fact_team_standing hts ON g.game_id = hts.game_id AND hts.side = 'home'
        LEFT JOIN fact_team_standing ats ON g.game_id = ats.game_id AND ats.side = 'away'
        LEFT JOIN (
            SELECT game_id, team,
                SUM(CASE WHEN injury_status IN ('out','ir') THEN 1 ELSE 0 END) AS total_out,
                SUM(CASE WHEN injury_status IN ('out','ir') AND position = 'QB' THEN 1 ELSE 0 END) AS qb_out,
                SUM(CASE WHEN injury_status IN ('out','ir') AND position IN ('WR','RB','TE') THEN 1 ELSE 0 END) AS skill_out,
                SUM(CASE WHEN injury_status = 'doubtful' THEN 1 ELSE 0 END) AS total_doubtful
            FROM fact_injury_report
            GROUP BY game_id, team
        ) ir_h ON g.game_id = ir_h.game_id AND ir_h.team = g.home_team
        LEFT JOIN (
            SELECT game_id, team,
                SUM(CASE WHEN injury_status IN ('out','ir') THEN 1 ELSE 0 END) AS total_out,
                SUM(CASE WHEN injury_status IN ('out','ir') AND position = 'QB' THEN 1 ELSE 0 END) AS qb_out,
                SUM(CASE WHEN injury_status IN ('out','ir') AND position IN ('WR','RB','TE') THEN 1 ELSE 0 END) AS skill_out,
                SUM(CASE WHEN injury_status = 'doubtful' THEN 1 ELSE 0 END) AS total_doubtful
            FROM fact_injury_report
            GROUP BY game_id, team
        ) ir_a ON g.game_id = ir_a.game_id AND ir_a.team = g.away_team
        ORDER BY g.game_date
        '''
    else:
        query = '''
        SELECT
            'mlb' AS sport,
            g.game_id,
            g.game_date,
            g.home_team,
            g.away_team,
            g.home_score,
            g.away_score,
            g.margin,
            0 AS is_tournament_game,
            COALESCE(g.is_postseason_game, 0) AS is_postseason_game,
            COALESCE(g.round_name, '') AS round_name,
            0 AS seed_home,
            0 AS seed_away,
            COALESCE(g.playoff_experience_home, 0) AS playoff_experience_home,
            COALESCE(g.playoff_experience_away, 0) AS playoff_experience_away,
            0.0 AS home_seed_hist_win_pct,
            0.0 AS away_seed_hist_win_pct,
            0.0 AS home_seed_hist_upset_win_pct,
            0.0 AS away_seed_hist_upset_win_pct,
            o.spread AS market_spread,
            o.total_line AS market_total_line,
            o.moneyline_home AS market_moneyline_home,
            o.moneyline_away AS market_moneyline_away
        FROM fact_game_results g
        LEFT JOIN (
            SELECT t1.*
            FROM fact_market_odds t1
            INNER JOIN (
                SELECT mo.game_id, MAX(mo.market_timestamp) AS max_ts
                FROM fact_market_odds mo
                INNER JOIN fact_game_results gr ON mo.game_id = gr.game_id
                WHERE mo.market_timestamp < gr.game_date
                GROUP BY mo.game_id
            ) latest
              ON t1.game_id = latest.game_id
             AND t1.market_timestamp = latest.max_ts
        ) o
          ON g.game_id = o.game_id
        ORDER BY g.game_date
        '''

    df = pd.read_sql(query, conn)
    conn.close()
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    logger.info("load_base_frame: %d rows loaded for sport=%s", len(df), sport)
    return df


def build_feature_frame(sport: str):
    """Build the engineered feature frame for *sport*.

    Calls ``load_base_frame`` then applies all feature engineering transforms
    via ``finalize_feature_frame``.

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, or ``"mlb"``.

    Returns
    -------
    (feature_df, team_to_id) where *feature_df* is a pandas.DataFrame and
    *team_to_id* is a ``{team_name: int}`` encoding dict.
    """
    df = load_base_frame(sport)
    if df.empty:
        logger.warning("build_feature_frame: empty base frame for sport=%s", sport)
        return df, {}
    feature_df, team_to_id = finalize_feature_frame(df)
    logger.info(
        "build_feature_frame: %d rows, %d features for sport=%s",
        len(feature_df), len(feature_df.columns), sport,
    )
    return feature_df, team_to_id


def materialize_features_to_modeling_silver(sport: str) -> dict:
    """Build feature vectors and write them to ``modeling_silver.fact_training_features``.

    Each row in the source silver tables becomes one row in the target table,
    keyed by ``(sport, game_id)``.  Existing rows are updated via
    ``ON DUPLICATE KEY UPDATE``.

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, or ``"mlb"``.

    Returns
    -------
    dict with keys ``sport``, ``rows_written``, ``feature_version``.

    Raises
    ------
    Exception
        Re-raised from DB or feature engineering failures after logging.
    """
    logger.info("materialize_features_to_modeling_silver: sport=%s", sport)
    feature_df, _ = build_feature_frame(sport)
    if feature_df.empty:
        logger.warning("materialize_features_to_modeling_silver: no data for sport=%s", sport)
        return {"sport": sport, "rows_written": 0, "feature_version": FEATURE_VERSION}

    conn = get_connection("modeling_silver")
    cursor = conn.cursor()

    insert_sql = '''
    INSERT INTO fact_training_features (
        sport, game_id, game_date, home_team, away_team,
        target_home_win, target_cover_home, target_total_over,
        feature_version, feature_payload, training_timestamp
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
    )
    ON DUPLICATE KEY UPDATE
        game_date = VALUES(game_date),
        home_team = VALUES(home_team),
        away_team = VALUES(away_team),
        target_home_win = VALUES(target_home_win),
        target_cover_home = VALUES(target_cover_home),
        target_total_over = VALUES(target_total_over),
        feature_version = VALUES(feature_version),
        feature_payload = VALUES(feature_payload),
        training_timestamp = NOW()
    '''

    rows_written = 0
    for _, row in feature_df.iterrows():
        normalized = {}
        for col in FEATURE_COLUMNS:
            v = row[col]
            try:
                if pd.isna(v):
                    normalized[col] = 0.0
                elif hasattr(v, "item"):
                    normalized[col] = v.item()
                else:
                    normalized[col] = v
            except Exception:
                normalized[col] = v

        cursor.execute(insert_sql, (
            sport,
            row["game_id"],
            row["game_date"].to_pydatetime() if hasattr(row["game_date"], "to_pydatetime") else row["game_date"],
            row["home_team"],
            row["away_team"],
            int(row["target_home_win"]),
            int(row["target_cover_home"]),
            int(row["target_total_over"]),
            FEATURE_VERSION,
            json.dumps(normalized),
        ))
        rows_written += 1

    conn.commit()
    cursor.close()
    conn.close()
    logger.info(
        "materialize_features_to_modeling_silver: wrote %d rows for sport=%s",
        rows_written, sport,
    )
    return {"sport": sport, "rows_written": rows_written, "feature_version": FEATURE_VERSION}


def load_modeling_frame(sport: str) -> pd.DataFrame:
    """Load the training/scoring frame from ``modeling_silver`` for *sport*.

    Reads ``fact_training_features``, expands the JSON ``feature_payload``
    column into individual feature columns, and ensures all expected
    FEATURE_COLUMNS are present (defaulting missing ones to 0.0).

    Parameters
    ----------
    sport:
        One of ``"nfl"``, ``"ncaa_mbb"``, or ``"mlb"``.

    Returns
    -------
    pandas.DataFrame ready for model training or inference, or an empty
    DataFrame if no rows exist for *sport*.
    """
    logger.info("load_modeling_frame: sport=%s", sport)
    conn = get_connection("modeling_silver")
    query = '''
    SELECT
        sport,
        game_id,
        game_date,
        home_team,
        away_team,
        target_home_win,
        target_cover_home,
        target_total_over,
        feature_version,
        feature_payload
    FROM fact_training_features
    WHERE sport = %s
    ORDER BY game_date
    '''
    df = pd.read_sql(query, conn, params=[sport])
    conn.close()

    if df.empty:
        return df

    df["game_date"] = pd.to_datetime(df["game_date"])
    payload_expanded = df["feature_payload"].apply(
        lambda x: json.loads(x) if isinstance(x, str) else (x if isinstance(x, dict) else {})
    )
    payload_df = pd.json_normalize(payload_expanded)

    for col in FEATURE_COLUMNS:
        if col not in payload_df.columns:
            payload_df[col] = 0.0

    result = pd.concat(
        [
            df.drop(columns=["feature_payload"]).reset_index(drop=True),
            payload_df[FEATURE_COLUMNS].reset_index(drop=True),
        ],
        axis=1
    )
    logger.info("load_modeling_frame: %d rows for sport=%s", len(result), sport)
    return result
