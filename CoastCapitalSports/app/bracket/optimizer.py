"""
optimizer.py — Pool-winning bracket optimization.

Given Monte Carlo simulation results, selects bracket picks that maximize
the probability of winning an ESPN bracket pool.  Uses contrarian strategy:
picks that are underrepresented in the pool population relative to their
true probability yield the most expected value for pool-winning.
"""

import logging
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

ESPN_SCORING = {1: 10, 2: 20, 3: 40, 4: 80, 5: 160, 6: 320}

# Estimated chalk pick rates for R64 by lower seed number
# (how often the public picks the favored seed)
CHALK_RATES = {
    1: 0.99, 2: 0.94, 3: 0.90, 4: 0.85,
    5: 0.70, 6: 0.65, 7: 0.60, 8: 0.52,
    9: 0.48, 10: 0.40, 11: 0.35, 12: 0.30,
    13: 0.15, 14: 0.10, 15: 0.06, 16: 0.01,
}


@dataclass
class BracketPick:
    round_number: int
    game_number: int
    region: str
    team_a: str
    team_b: str
    seed_a: int
    seed_b: int
    predicted_winner: str
    win_probability: float
    advancement_probability: float
    is_upset: bool
    is_contrarian: bool
    pick_leverage: float
    expected_points: float

    def to_dict(self):
        return asdict(self)


def estimate_chalk_field_picks(
    bracket_structure: dict,
    advancement_rates: dict,
) -> dict[str, dict[int, float]]:
    """Estimate what the typical pool entrant would pick.

    Returns dict: {team_name: {round_number: estimated_ownership_pct}}
    """
    ownership = {}

    region_names = bracket_structure.get("regions", [])
    for region_name in region_names:
        teams = bracket_structure.get(region_name, [])

        # R64 ownership based on seed
        for i in range(0, len(teams), 2):
            if i + 1 >= len(teams):
                continue
            ta = teams[i]
            tb = teams[i + 1]
            sa = ta.get("seed", 8)
            sb = tb.get("seed", 8)

            # Lower seed number = more favored
            if sa <= sb:
                favored, underdog = ta, tb
                chalk_rate = CHALK_RATES.get(sa, 0.50)
            else:
                favored, underdog = tb, ta
                chalk_rate = CHALK_RATES.get(sb, 0.50)

            fn = favored["team_name"]
            un = underdog["team_name"]
            ownership.setdefault(fn, {})[1] = chalk_rate
            ownership.setdefault(un, {})[1] = 1.0 - chalk_rate

        # Later rounds: ownership decays based on R64 ownership * advancement
        for team_name in ownership:
            r1_own = ownership[team_name].get(1, 0)
            rates = advancement_rates.get(team_name, {})
            for round_num in range(2, 7):
                adv_rate = rates.get(round_num, 0)
                # Public picks roughly track advancement probability with chalk bias
                seed = _get_team_seed(team_name, bracket_structure)
                chalk_bias = CHALK_RATES.get(seed, 0.50)
                ownership[team_name][round_num] = r1_own * adv_rate * (0.5 + 0.5 * chalk_bias)

    return ownership


def compute_pick_leverage(
    our_prob: float,
    field_ownership: float,
    points: int,
) -> float:
    """Compute the leverage value of a pick vs the field.

    High leverage = underowned relative to true probability * high point value.
    """
    if field_ownership <= 0.01:
        field_ownership = 0.01
    return (our_prob / field_ownership) * points


def optimize_bracket(
    simulation_results: dict,
    bracket_structure: dict,
    pool_size: int = 100,
    risk_tolerance: float = 0.5,
) -> list[BracketPick]:
    """Generate optimal bracket picks for pool-winning.

    Works backwards from the championship (most valuable picks first).

    Parameters
    ----------
    simulation_results:
        Output of TournamentSimulator.run_monte_carlo().
    bracket_structure:
        Output of bracket_data.build_bracket_structure().
    pool_size:
        Number of entries in the bracket pool.
    risk_tolerance:
        0.0 = pure chalk, 1.0 = maximum contrarian. Default 0.5.

    Returns
    -------
    List of BracketPick objects for all games.
    """
    advancement_rates = simulation_results.get("advancement_rates", {})
    champion_rates = simulation_results.get("champion_rates", {})
    field_ownership = estimate_chalk_field_picks(bracket_structure, advancement_rates)

    all_picks = []
    forced_winners = {}  # {team_name: True} — teams that must win due to later picks

    region_names = bracket_structure.get("regions", [])

    # --- Step 1: Pick champion (round 6) ---
    champion_pick = _pick_best_team_for_round(
        champion_rates, field_ownership, 6, risk_tolerance,
    )
    if champion_pick:
        forced_winners[champion_pick] = True

    # --- Step 2: Pick Final Four (round 5) ---
    # Champion must be one of the FF teams
    ff_pairings = bracket_structure.get("ff_pairings", [(0, 1), (2, 3)])
    ff_picks = {}
    for idx_a, idx_b in ff_pairings:
        if idx_a < len(region_names) and idx_b < len(region_names):
            rn_a = region_names[idx_a]
            rn_b = region_names[idx_b]

            # Get all teams that could come from these regions
            candidates_a = _get_region_teams(bracket_structure, rn_a)
            candidates_b = _get_region_teams(bracket_structure, rn_b)

            # If champion is from one of these regions, they must win
            best_a = _pick_region_representative(
                candidates_a, advancement_rates, field_ownership, 5,
                risk_tolerance, forced_winners,
            )
            best_b = _pick_region_representative(
                candidates_b, advancement_rates, field_ownership, 5,
                risk_tolerance, forced_winners,
            )

            if best_a:
                ff_picks[rn_a] = best_a
                forced_winners[best_a] = True
            if best_b:
                ff_picks[rn_b] = best_b
                forced_winners[best_b] = True

    # --- Step 3: Build full bracket region by region ---
    game_number = 0
    for region_name in region_names:
        teams = bracket_structure.get(region_name, [])
        region_picks = _build_region_picks(
            teams, region_name, advancement_rates, field_ownership,
            risk_tolerance, forced_winners, game_number,
        )
        all_picks.extend(region_picks)
        game_number += len(region_picks)

    # --- Step 4: Add Final Four and Championship picks ---
    for idx, (idx_a, idx_b) in enumerate(ff_pairings):
        if idx_a < len(region_names) and idx_b < len(region_names):
            rn_a = region_names[idx_a]
            rn_b = region_names[idx_b]
            winner_a = ff_picks.get(rn_a, "")
            winner_b = ff_picks.get(rn_b, "")
            if winner_a and winner_b:
                # Determine FF game winner
                ff_winner = champion_pick if champion_pick in (winner_a, winner_b) else winner_a
                adv_rate = advancement_rates.get(ff_winner, {}).get(6, 0)
                own = field_ownership.get(ff_winner, {}).get(5, 0.1)
                leverage = compute_pick_leverage(adv_rate, own, ESPN_SCORING[5])
                seed_a = _get_team_seed(winner_a, bracket_structure)
                seed_b = _get_team_seed(winner_b, bracket_structure)

                all_picks.append(BracketPick(
                    round_number=5,
                    game_number=game_number,
                    region="Final Four",
                    team_a=winner_a,
                    team_b=winner_b,
                    seed_a=seed_a,
                    seed_b=seed_b,
                    predicted_winner=ff_winner,
                    win_probability=advancement_rates.get(ff_winner, {}).get(5, 0),
                    advancement_probability=adv_rate,
                    is_upset=seed_a > 0 and seed_b > 0 and _get_team_seed(ff_winner, bracket_structure) > min(seed_a, seed_b),
                    is_contrarian=leverage > ESPN_SCORING[5] * 1.5,
                    pick_leverage=leverage,
                    expected_points=adv_rate * ESPN_SCORING[5],
                ))
                game_number += 1

    # Championship game
    if champion_pick:
        champ_rate = champion_rates.get(champion_pick, 0)
        champ_own = field_ownership.get(champion_pick, {}).get(6, 0.1)
        champ_leverage = compute_pick_leverage(champ_rate, champ_own, ESPN_SCORING[6])
        champ_seed = _get_team_seed(champion_pick, bracket_structure)

        all_picks.append(BracketPick(
            round_number=6,
            game_number=game_number,
            region="Championship",
            team_a=champion_pick,
            team_b="",
            seed_a=champ_seed,
            seed_b=0,
            predicted_winner=champion_pick,
            win_probability=champ_rate,
            advancement_probability=champ_rate,
            is_upset=champ_seed > 4,
            is_contrarian=champ_leverage > ESPN_SCORING[6] * 1.5,
            pick_leverage=champ_leverage,
            expected_points=champ_rate * ESPN_SCORING[6],
        ))

    logger.info(
        "optimize_bracket: generated %d picks, champion=%s (%.1f%%)",
        len(all_picks),
        champion_pick or "N/A",
        champion_rates.get(champion_pick, 0) * 100 if champion_pick else 0,
    )

    return all_picks


def score_bracket(picks: list[BracketPick], actual_winners: dict = None) -> dict:
    """Score a bracket against actual results.

    Parameters
    ----------
    picks:
        Optimized bracket picks.
    actual_winners:
        Optional dict: {(round_number, game_number): winner_team_name}

    Returns
    -------
    dict with total_score, round_scores, correct_picks, total_picks.
    """
    if not actual_winners:
        # Return expected score
        total_expected = sum(p.expected_points for p in picks)
        return {
            "mode": "expected",
            "total_expected_score": round(total_expected, 1),
            "max_possible_score": sum(
                ESPN_SCORING.get(r, 0) * count
                for r, count in _count_games_per_round(picks).items()
            ),
        }

    total_score = 0
    correct = 0
    round_scores = {}

    for pick in picks:
        key = (pick.round_number, pick.game_number)
        actual = actual_winners.get(key)
        if actual and actual == pick.predicted_winner:
            points = ESPN_SCORING.get(pick.round_number, 0)
            total_score += points
            correct += 1
            round_scores.setdefault(pick.round_number, 0)
            round_scores[pick.round_number] = round_scores.get(pick.round_number, 0) + points

    return {
        "mode": "actual",
        "total_score": total_score,
        "correct_picks": correct,
        "total_picks": len(picks),
        "accuracy": correct / len(picks) if picks else 0,
        "round_scores": round_scores,
        "max_possible_score": 1920,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pick_best_team_for_round(
    rates: dict, field_ownership: dict, round_num: int, risk_tolerance: float,
) -> str | None:
    """Pick the team with the highest leverage for a given round."""
    best_team = None
    best_leverage = -1

    for team, rate in rates.items():
        if rate < 0.05:  # Minimum threshold
            continue
        own = field_ownership.get(team, {}).get(round_num, 0.1)
        points = ESPN_SCORING.get(round_num, 10)
        leverage = compute_pick_leverage(rate, own, points)

        # Blend leverage with pure probability based on risk tolerance
        score = (1 - risk_tolerance) * rate * points + risk_tolerance * leverage

        if score > best_leverage:
            best_leverage = score
            best_team = team

    return best_team


def _pick_region_representative(
    candidates: list[str],
    advancement_rates: dict,
    field_ownership: dict,
    round_num: int,
    risk_tolerance: float,
    forced_winners: dict,
) -> str | None:
    """Pick the best team from a region for a given round, respecting forced winners."""
    # If a forced winner is in this set of candidates, pick them
    for c in candidates:
        if c in forced_winners:
            return c

    best_team = None
    best_score = -1

    for team in candidates:
        rate = advancement_rates.get(team, {}).get(round_num, 0)
        if rate < 0.03:
            continue
        own = field_ownership.get(team, {}).get(round_num, 0.1)
        points = ESPN_SCORING.get(round_num, 10)
        leverage = compute_pick_leverage(rate, own, points)
        score = (1 - risk_tolerance) * rate * points + risk_tolerance * leverage
        if score > best_score:
            best_score = score
            best_team = team

    return best_team


def _build_region_picks(
    teams: list[dict],
    region_name: str,
    advancement_rates: dict,
    field_ownership: dict,
    risk_tolerance: float,
    forced_winners: dict,
    game_offset: int,
) -> list[BracketPick]:
    """Build picks for a single region (R64 through E8)."""
    picks = []
    current = list(teams)
    game_num = game_offset

    for round_num in range(1, 5):
        next_round = []
        for i in range(0, len(current), 2):
            if i + 1 >= len(current):
                next_round.append(current[i])
                continue

            ta = current[i]
            tb = current[i + 1]
            ta_name = ta["team_name"] if isinstance(ta, dict) else ta
            tb_name = tb["team_name"] if isinstance(tb, dict) else tb
            sa = ta.get("seed", 0) if isinstance(ta, dict) else 0
            sb = tb.get("seed", 0) if isinstance(tb, dict) else 0

            # Determine winner
            if ta_name in forced_winners:
                winner_name = ta_name
            elif tb_name in forced_winners:
                winner_name = tb_name
            else:
                # Pick by leverage/probability blend
                rate_a = advancement_rates.get(ta_name, {}).get(round_num, 0)
                rate_b = advancement_rates.get(tb_name, {}).get(round_num, 0)
                own_a = field_ownership.get(ta_name, {}).get(round_num, 0.5)
                own_b = field_ownership.get(tb_name, {}).get(round_num, 0.5)
                points = ESPN_SCORING.get(round_num, 10)
                lev_a = compute_pick_leverage(rate_a, own_a, points)
                lev_b = compute_pick_leverage(rate_b, own_b, points)
                score_a = (1 - risk_tolerance) * rate_a * points + risk_tolerance * lev_a
                score_b = (1 - risk_tolerance) * rate_b * points + risk_tolerance * lev_b
                winner_name = ta_name if score_a >= score_b else tb_name

            rate_w = advancement_rates.get(winner_name, {}).get(round_num, 0)
            own_w = field_ownership.get(winner_name, {}).get(round_num, 0.1)
            lev_w = compute_pick_leverage(rate_w, own_w, ESPN_SCORING.get(round_num, 10))
            winner_seed = sa if winner_name == ta_name else sb
            loser_seed = sb if winner_name == ta_name else sa
            is_upset = (
                winner_seed > 0 and loser_seed > 0 and winner_seed > loser_seed
            )

            picks.append(BracketPick(
                round_number=round_num,
                game_number=game_num,
                region=region_name,
                team_a=ta_name,
                team_b=tb_name,
                seed_a=sa,
                seed_b=sb,
                predicted_winner=winner_name,
                win_probability=rate_w,
                advancement_probability=rate_w,
                is_upset=is_upset,
                is_contrarian=lev_w > ESPN_SCORING.get(round_num, 10) * 1.5,
                pick_leverage=lev_w,
                expected_points=rate_w * ESPN_SCORING.get(round_num, 10),
            ))
            game_num += 1

            winner_dict = ta if winner_name == ta_name else tb
            next_round.append(winner_dict)

        current = next_round

    return picks


def _get_team_seed(team_name: str, bracket_structure: dict) -> int:
    """Look up a team's seed from the bracket structure."""
    for region_name in bracket_structure.get("regions", []):
        for team in bracket_structure.get(region_name, []):
            if team.get("team_name") == team_name:
                return team.get("seed", 0)
    for team in bracket_structure.get("play_in", []):
        if team.get("team_name") == team_name:
            return team.get("seed", 0)
    return 0


def _get_region_teams(bracket_structure: dict, region_name: str) -> list[str]:
    """Get all team names from a region."""
    return [t["team_name"] for t in bracket_structure.get(region_name, [])]


def _count_games_per_round(picks: list[BracketPick]) -> dict[int, int]:
    """Count games per round from picks."""
    counts = {}
    for p in picks:
        counts[p.round_number] = counts.get(p.round_number, 0) + 1
    return counts
