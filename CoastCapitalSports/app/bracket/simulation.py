"""
simulation.py — Monte Carlo simulation of the NCAA tournament bracket.

Runs N simulations of the full 68-team tournament, tracking how often each team
advances to each round.  Results feed the optimizer for bracket pick selection.
"""

import logging
import uuid
from collections import defaultdict

import numpy as np

from bracket.matchup_predictor import predict_matchup_symmetric

logger = logging.getLogger(__name__)

ROUND_NAMES = {
    0: "First Four",
    1: "Round of 64",
    2: "Round of 32",
    3: "Sweet 16",
    4: "Elite 8",
    5: "Final Four",
    6: "Championship",
}

ESPN_SCORING = {1: 10, 2: 20, 3: 40, 4: 80, 5: 160, 6: 320}


class TournamentSimulator:
    """Monte Carlo simulator for the NCAA tournament.

    Parameters
    ----------
    bracket:
        Bracket structure from bracket_data.build_bracket_structure().
    team_profiles:
        Output of team_profile.build_team_profiles().
    team_to_id:
        Team name to integer encoding mapping.
    model:
        Loaded SportsBinaryClassifier in eval mode.
    """

    def __init__(self, bracket, team_profiles, team_to_id, model):
        self.bracket = bracket
        self.team_profiles = team_profiles
        self.team_to_id = team_to_id
        self.model = model
        self._prob_cache = {}

    def get_win_probability(
        self, team_a: str, team_b: str, seed_a: int, seed_b: int, round_name: str,
    ) -> float:
        """Get or compute cached win probability for team_a over team_b."""
        cache_key = (team_a, team_b, round_name)
        if cache_key not in self._prob_cache:
            prob = predict_matchup_symmetric(
                self.model, team_a, team_b,
                self.team_profiles, seed_a, seed_b,
                self.team_to_id, round_name,
            )
            self._prob_cache[cache_key] = prob
            self._prob_cache[(team_b, team_a, round_name)] = 1.0 - prob
        return self._prob_cache[cache_key]

    def _simulate_game(self, team_a: dict, team_b: dict, round_name: str) -> dict:
        """Simulate a single game, returning the winning team dict."""
        prob_a = self.get_win_probability(
            team_a["team_name"], team_b["team_name"],
            team_a["seed"], team_b["seed"],
            round_name,
        )
        return team_a if np.random.random() < prob_a else team_b

    def simulate_region(self, region_teams: list[dict], region_name: str) -> list[list[dict]]:
        """Simulate a single region from R64 through Elite 8.

        Parameters
        ----------
        region_teams:
            List of 16 team dicts ordered by bracket position.
        region_name:
            Region name for logging.

        Returns
        -------
        List of lists: [R64_winners(8), R32_winners(4), S16_winners(2), E8_winner(1)]
        """
        rounds = []
        current = region_teams

        for round_num in range(1, 5):  # R64, R32, S16, E8
            round_name = ROUND_NAMES[round_num]
            winners = []
            for i in range(0, len(current), 2):
                if i + 1 < len(current):
                    winner = self._simulate_game(current[i], current[i + 1], round_name)
                else:
                    winner = current[i]
                winners.append(winner)
            rounds.append(winners)
            current = winners

        return rounds

    def simulate_tournament(self) -> dict:
        """Run one full simulation of the tournament.

        Returns
        -------
        dict mapping round_number -> list of winner team_name strings.
        """
        results = defaultdict(list)
        region_names = self.bracket.get("regions", [])
        region_winners = {}

        # Simulate play-in games
        play_in_teams = self.bracket.get("play_in", [])
        play_in_winners = []
        for i in range(0, len(play_in_teams), 2):
            if i + 1 < len(play_in_teams):
                winner = self._simulate_game(
                    play_in_teams[i], play_in_teams[i + 1], "First Four",
                )
                play_in_winners.append(winner)
                results[0].append(winner["team_name"])

        # Simulate each region
        for region_name in region_names:
            region_teams = self.bracket.get(region_name, [])
            if not region_teams:
                continue

            round_results = self.simulate_region(region_teams, region_name)
            for round_idx, winners in enumerate(round_results):
                round_num = round_idx + 1
                for w in winners:
                    results[round_num].append(w["team_name"])

            # Region winner is the E8 winner
            if round_results and round_results[-1]:
                region_winners[region_name] = round_results[-1][0]

        # Final Four
        ff_pairings = self.bracket.get("ff_pairings", [(0, 1), (2, 3)])
        ff_teams = []
        for idx_a, idx_b in ff_pairings:
            if idx_a < len(region_names) and idx_b < len(region_names):
                rn_a = region_names[idx_a]
                rn_b = region_names[idx_b]
                team_a = region_winners.get(rn_a)
                team_b = region_winners.get(rn_b)
                if team_a and team_b:
                    winner = self._simulate_game(team_a, team_b, "Final Four")
                    results[5].append(winner["team_name"])
                    ff_teams.append(winner)
                elif team_a:
                    results[5].append(team_a["team_name"])
                    ff_teams.append(team_a)
                elif team_b:
                    results[5].append(team_b["team_name"])
                    ff_teams.append(team_b)

        # Championship
        if len(ff_teams) >= 2:
            champion = self._simulate_game(ff_teams[0], ff_teams[1], "Championship")
            results[6].append(champion["team_name"])
        elif ff_teams:
            results[6].append(ff_teams[0]["team_name"])

        return dict(results)

    def run_monte_carlo(self, n_simulations: int = 10000) -> dict:
        """Run N simulations and aggregate results.

        Returns
        -------
        dict with simulation_id, simulation_count, advancement_rates,
        champion_rates.
        """
        simulation_id = f"sim_{uuid.uuid4().hex[:12]}"
        advancement_counts = defaultdict(lambda: defaultdict(int))
        champion_counts = defaultdict(int)

        logger.info(
            "run_monte_carlo: starting %d simulations (id=%s)",
            n_simulations, simulation_id,
        )

        for i in range(n_simulations):
            result = self.simulate_tournament()
            for round_num, winners in result.items():
                for winner in winners:
                    advancement_counts[winner][round_num] += 1
            if 6 in result and result[6]:
                champion_counts[result[6][0]] += 1

            if (i + 1) % 1000 == 0:
                logger.info("run_monte_carlo: completed %d/%d simulations", i + 1, n_simulations)

        # Convert to rates
        advancement_rates = {}
        for team, rounds in advancement_counts.items():
            advancement_rates[team] = {
                round_num: count / n_simulations
                for round_num, count in rounds.items()
            }

        champion_rates = {
            team: count / n_simulations
            for team, count in champion_counts.items()
        }

        logger.info(
            "run_monte_carlo: completed — %d teams tracked, top champion: %s (%.1f%%)",
            len(advancement_rates),
            max(champion_rates, key=champion_rates.get) if champion_rates else "N/A",
            max(champion_rates.values()) * 100 if champion_rates else 0,
        )

        return {
            "simulation_id": simulation_id,
            "simulation_count": n_simulations,
            "advancement_rates": advancement_rates,
            "champion_rates": champion_rates,
        }
