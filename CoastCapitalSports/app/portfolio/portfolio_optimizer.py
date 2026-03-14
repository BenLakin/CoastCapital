"""
portfolio_optimizer.py — Kelly criterion-based bankroll allocation.

Provides helpers for sizing bets using the Kelly fraction given
model-predicted win probabilities and market odds.
"""


def kelly_fraction(probability: float, odds: float) -> float:
    """Return the optimal Kelly stake fraction for a single wager.

    Parameters
    ----------
    probability:
        Estimated win probability (0–1).
    odds:
        Decimal odds (e.g. 2.0 for even money).

    Returns
    -------
    float in [0, 1] — fraction of bankroll to wager.
    """
    b = odds - 1
    q = 1 - probability
    return max(0, (b * probability - q) / b)

def optimize_portfolio(predictions: list[dict], bankroll: float = 10000) -> list[dict]:
    """Allocate *bankroll* across *predictions* using Kelly sizing.

    Parameters
    ----------
    predictions:
        List of dicts each containing ``game_id``, ``predicted_win_prob``,
        and ``odds``.
    bankroll:
        Total bankroll to allocate.

    Returns
    -------
    List of dicts with ``game_id``, ``allocation``, and ``expected_value``.
    """
    portfolio = []
    for prediction in predictions:
        stake = bankroll * kelly_fraction(prediction.get("predicted_win_prob", 0.5), prediction.get("odds", 2.0))
        portfolio.append({
            "game_id": prediction.get("game_id"),
            "allocation": stake,
            "expected_value": prediction.get("predicted_win_prob", 0.5) - 0.5
        })
    return portfolio
