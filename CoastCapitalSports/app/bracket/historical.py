"""
historical.py — Historical bracket pipeline for backtesting.

Pulls bracket data for past seasons, runs the model's predictions against
the historical field, and compares to actual results.  Supports multi-run
optimization where the full simulation+optimize cycle runs N times to
produce diverse bracket variants for pool-winning strategy.
"""

import logging
import uuid

from bracket.bracket_data import (
    build_bracket_structure,
    fetch_tournament_field,
    fetch_tournament_games,
    load_bracket_field,
    save_bracket_field,
)
from bracket.bracket_html import generate_bracket_html, save_bracket_html
from bracket.matchup_predictor import load_ncaa_model
from bracket.optimizer import optimize_bracket, score_bracket
from bracket.simulation import TournamentSimulator
from bracket.team_profile import build_team_profiles, save_team_profiles
from database import get_connection

logger = logging.getLogger(__name__)


def run_historical_bracket(
    season: int,
    n_simulations: int = 10000,
    n_runs: int = 1,
    pool_size: int = 100,
    risk_tolerance: float = 0.5,
    output_html: bool = True,
    html_path: str = None,
    overwrite: bool = True,
) -> dict:
    """Run the full bracket pipeline for a historical (or current) season.

    Steps:
    1. Fetch or load the bracket field for the season
    2. Build team profiles from silver data
    3. Load the model
    4. Run N full optimization cycles (each: MC simulation + optimize)
    5. Fetch actual tournament results (if available)
    6. Score and save each bracket run
    7. Generate HTML for the best/default run

    Parameters
    ----------
    season:
        Academic year (e.g. 2024 for March 2024 tournament).
    n_simulations:
        Number of Monte Carlo simulations per run.
    n_runs:
        Number of full optimization runs to produce.
    pool_size:
        Assumed bracket pool size for optimization.
    risk_tolerance:
        Contrarian aggressiveness (0-1).
    output_html:
        Whether to generate HTML bracket.
    html_path:
        Output path for HTML. Defaults to /app/bracket_output/{season}_bracket.html.
    overwrite:
        If True, delete existing simulations for this season before inserting.
        If False, append new runs.

    Returns
    -------
    dict with runs list, best_run, actual_score (if available), html_path.
    """
    logger.info(
        "run_historical_bracket: season=%d sims=%d runs=%d pool=%d risk=%.2f overwrite=%s",
        season, n_simulations, n_runs, pool_size, risk_tolerance, overwrite,
    )

    # 1. Get bracket field
    field_df = load_bracket_field(season)
    if field_df.empty:
        logger.info("run_historical_bracket: fetching bracket field from ESPN")
        field = fetch_tournament_field(season)
        if not field:
            raise ValueError(f"No bracket data found for season {season}")
        save_bracket_field(season, field)
        field_df = load_bracket_field(season)

    bracket = build_bracket_structure(field_df.to_dict("records"))
    logger.info("run_historical_bracket: bracket has %d regions", len(bracket.get("regions", [])))

    # 2. Build team profiles
    profiles = build_team_profiles(season)
    team_seeds = {r["team_name"]: r["seed"] for _, r in field_df.iterrows()}
    save_team_profiles(season, profiles, team_seeds)

    # 3. Load model and get team_to_id
    model, metadata = load_ncaa_model()
    from models.modeling_data import build_feature_frame
    _, team_to_id = build_feature_frame("ncaa_mbb")

    # 4. Fetch actual results (shared across all runs)
    actual_games = fetch_tournament_games(season)

    # Overwrite existing simulations if requested
    run_batch_id = uuid.uuid4().hex[:12]
    if overwrite:
        _delete_season_simulations(season)

    # 5. Run N optimization cycles
    all_runs = []
    last_picks = None
    last_sim_results = None
    last_actual_winners = None

    for run_idx in range(n_runs):
        counter = run_idx + 1
        logger.info("run_historical_bracket: === Run %d/%d ===", counter, n_runs)

        # Each run gets a fresh simulator (fresh random state)
        simulator = TournamentSimulator(bracket, profiles, team_to_id, model)
        sim_results = simulator.run_monte_carlo(n_simulations)

        # Optimize
        picks = optimize_bracket(sim_results, bracket, pool_size, risk_tolerance)

        # Build actual winners map
        actual_winners = _build_actual_winners_map(actual_games, picks)

        # Score
        if actual_winners:
            scoring = score_bracket(picks, actual_winners)
        else:
            scoring = score_bracket(picks)

        # Determine champion pick and expected score
        champion = ""
        expected_score = 0.0
        for p in picks:
            if p.round_number == 6:
                champion = p.predicted_winner
            expected_score += p.expected_points

        # Save to DB
        _save_simulation_to_db(
            sim_results, season, n_simulations, pool_size, risk_tolerance,
            metadata, counter, counter, run_batch_id, champion, expected_score,
        )
        _save_picks_to_db(sim_results["simulation_id"], picks, actual_winners)

        # Serialize picks for response
        picks_data = [
            {
                "round": p.round_number,
                "game": p.game_number,
                "region": p.region,
                "team_a": p.team_a,
                "team_b": p.team_b,
                "seed_a": p.seed_a,
                "seed_b": p.seed_b,
                "winner": p.predicted_winner,
                "win_prob": p.win_probability,
                "is_upset": p.is_upset,
                "is_contrarian": p.is_contrarian,
                "expected_points": p.expected_points,
                "actual_winner": actual_winners.get((p.round_number, p.game_number)),
                "is_correct": (
                    actual_winners.get((p.round_number, p.game_number)) == p.predicted_winner
                    if actual_winners.get((p.round_number, p.game_number))
                    else None
                ),
            }
            for p in picks
        ]

        run_result = {
            "simulation_id": sim_results["simulation_id"],
            "simulation_counter": counter,
            "priority_ranking": counter,
            "champion": champion,
            "expected_score": round(expected_score, 1),
            "scoring": scoring,
            "picks": picks_data,
            "top_champions": dict(
                sorted(sim_results["champion_rates"].items(), key=lambda x: -x[1])[:10]
            ),
        }
        all_runs.append(run_result)

        # Keep references for HTML generation
        last_picks = picks
        last_sim_results = sim_results
        last_actual_winners = actual_winners

    # Sort runs by expected score descending and update priority_ranking
    all_runs.sort(key=lambda r: r["expected_score"], reverse=True)
    for rank, run in enumerate(all_runs, 1):
        run["priority_ranking"] = rank
        _update_priority_ranking(run["simulation_id"], rank, is_default=(rank == 1))

    # 6. Generate HTML for the best run
    html_file = None
    if output_html and all_runs and last_picks:
        html_file = html_path or f"/app/bracket_output/{season}_bracket.html"
        try:
            html = generate_bracket_html(
                last_picks, last_sim_results, bracket, season,
                metadata.get("model_version", "unknown"),
                pool_size,
                last_actual_winners if last_actual_winners else None,
            )
            save_bracket_html(html, html_file)
        except Exception as exc:
            logger.warning("HTML generation failed: %s", exc)

    logger.info(
        "run_historical_bracket: DONE season=%d runs=%d best_champion=%s",
        season, n_runs,
        all_runs[0]["champion"] if all_runs else "N/A",
    )

    return {
        "status": "ok",
        "season": season,
        "run_batch_id": run_batch_id,
        "n_runs": n_runs,
        "n_simulations": n_simulations,
        "runs": all_runs,
        "best_run": all_runs[0] if all_runs else None,
        "html_path": html_file,
        "model_version": metadata.get("model_version"),
        "has_actual_results": bool(actual_games),
    }


# ---------------------------------------------------------------------------
# DB persistence helpers
# ---------------------------------------------------------------------------

def _delete_season_simulations(season: int):
    """Delete all existing simulations for a season (overwrite mode)."""
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor()

        # Get simulation_ids to delete associated picks
        cursor.execute(
            "SELECT simulation_id FROM fact_bracket_simulations WHERE season = %s",
            (season,),
        )
        sim_ids = [row[0] for row in cursor.fetchall()]

        if sim_ids:
            placeholders = ", ".join(["%s"] * len(sim_ids))
            cursor.execute(
                f"DELETE FROM fact_bracket_picks WHERE simulation_id IN ({placeholders})",
                sim_ids,
            )
            cursor.execute(
                f"DELETE FROM fact_bracket_simulations WHERE simulation_id IN ({placeholders})",
                sim_ids,
            )

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Deleted %d existing simulations for season %d", len(sim_ids), season)
    except Exception as exc:
        logger.warning("_delete_season_simulations failed: %s", exc)


def _save_simulation_to_db(
    sim_results: dict,
    season: int,
    n_simulations: int,
    pool_size: int,
    risk_tolerance: float,
    metadata: dict,
    simulation_counter: int = 1,
    priority_ranking: int = 1,
    run_batch_id: str = None,
    champion_pick: str = None,
    expected_score: float = None,
):
    """Save simulation metadata to fact_bracket_simulations."""
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor()

        # Ensure new columns exist (for tables created before schema update)
        for col_def in [
            ("simulation_counter", "INT NOT NULL DEFAULT 1"),
            ("priority_ranking", "INT NOT NULL DEFAULT 1"),
            ("is_default", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("run_batch_id", "VARCHAR(36)"),
            ("expected_score", "DOUBLE"),
            ("champion_pick", "VARCHAR(100)"),
        ]:
            try:
                cursor.execute(
                    f"ALTER TABLE fact_bracket_simulations ADD COLUMN {col_def[0]} {col_def[1]}"
                )
            except Exception:
                pass  # Column already exists

        cursor.execute(
            """
            INSERT INTO fact_bracket_simulations
                (simulation_id, season, num_simulations, pool_size, risk_tolerance,
                 scoring_system, model_version, simulation_counter, priority_ranking,
                 is_default, run_batch_id, expected_score, champion_pick)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                num_simulations = VALUES(num_simulations),
                pool_size = VALUES(pool_size),
                simulation_counter = VALUES(simulation_counter),
                priority_ranking = VALUES(priority_ranking),
                expected_score = VALUES(expected_score),
                champion_pick = VALUES(champion_pick)
            """,
            (
                sim_results["simulation_id"],
                season,
                n_simulations,
                pool_size,
                risk_tolerance,
                "espn_standard",
                metadata.get("model_version", "unknown"),
                simulation_counter,
                priority_ranking,
                0,  # is_default — set later by _update_priority_ranking
                run_batch_id,
                expected_score,
                champion_pick,
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        logger.warning("_save_simulation_to_db: failed — %s", exc)


def _update_priority_ranking(simulation_id: str, priority_ranking: int, is_default: bool = False):
    """Update priority ranking and default flag for a simulation."""
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE fact_bracket_simulations
            SET priority_ranking = %s, is_default = %s
            WHERE simulation_id = %s
            """,
            (priority_ranking, int(is_default), simulation_id),
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        logger.warning("_update_priority_ranking failed: %s", exc)


def _save_picks_to_db(simulation_id: str, picks: list, actual_winners: dict):
    """Save bracket picks to fact_bracket_picks."""
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor()
        for p in picks:
            actual = actual_winners.get((p.round_number, p.game_number))
            is_correct = int(actual == p.predicted_winner) if actual else None
            cursor.execute(
                """
                INSERT INTO fact_bracket_picks
                    (simulation_id, round_number, game_number, region,
                     higher_seed_team, lower_seed_team, predicted_winner,
                     win_probability, is_upset, is_contrarian,
                     advancement_probability, pick_leverage,
                     actual_winner, is_correct)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    simulation_id, p.round_number, p.game_number, p.region,
                    p.team_a, p.team_b, p.predicted_winner,
                    p.win_probability, int(p.is_upset), int(p.is_contrarian),
                    p.advancement_probability, p.pick_leverage,
                    actual, is_correct,
                ),
            )
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("_save_picks_to_db: saved %d picks for %s", len(picks), simulation_id)
    except Exception as exc:
        logger.warning("_save_picks_to_db: failed — %s", exc)


def _build_actual_winners_map(actual_games: list[dict], picks: list) -> dict:
    """Map actual tournament results to pick keys.

    Returns dict: {(round_number, game_number): winner_team_name}
    """
    if not actual_games:
        return {}

    # Build a lookup by teams involved
    game_winners = {}
    for g in actual_games:
        key = tuple(sorted([g["home_team"], g["away_team"]]))
        game_winners[key] = g["winner"]

    result = {}
    for p in picks:
        key = tuple(sorted([p.team_a, p.team_b]))
        if key in game_winners:
            result[(p.round_number, p.game_number)] = game_winners[key]

    return result
