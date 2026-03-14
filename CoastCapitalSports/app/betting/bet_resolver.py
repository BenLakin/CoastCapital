"""
bet_resolver.py — Resolve pending bets after games complete.

Queries fact_bet_tracking for unresolved bets whose game_date has passed,
looks up actual results from fact_game_results, determines correctness,
and updates the tracking record with outcome and profit/loss.

Public entry point: ``resolve_pending_bets()``
"""

import logging
from datetime import datetime, timezone

from database import get_connection

logger = logging.getLogger(__name__)

SCHEMA_MAP = {
    "nfl": "nfl_silver",
    "ncaa_mbb": "ncaa_mbb_silver",
    "mlb": "mlb_silver",
}


def resolve_pending_bets() -> dict:
    """Resolve all pending bets whose games have completed.

    For each unresolved bet (actual_outcome IS NULL, game_date < today):
      - Look up actual result from fact_game_results
      - Determine correctness based on bet_type
      - Calculate profit/loss
      - Update fact_bet_tracking

    Returns
    -------
    dict with resolved_count, errors, and details.
    """
    logger.info("resolve_pending_bets: starting")

    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor(dictionary=True)

        # Check if table exists
        cursor.execute("""
            SELECT COUNT(*) AS cnt
            FROM information_schema.tables
            WHERE table_schema = 'modeling_internal'
              AND table_name = 'fact_bet_tracking'
        """)
        if cursor.fetchone()["cnt"] == 0:
            cursor.close()
            conn.close()
            return {"status": "ok", "resolved_count": 0, "message": "No bet tracking table"}

        # Add columns if migrating from older schema
        for col, col_type in [
            ("spread_line", "DOUBLE"),
            ("total_line", "DOUBLE"),
            ("pick_side", "VARCHAR(10)"),
        ]:
            try:
                cursor.execute(f"""
                    SELECT COUNT(*) AS cnt FROM information_schema.columns
                    WHERE table_schema = 'modeling_internal'
                      AND table_name = 'fact_bet_tracking'
                      AND column_name = '{col}'
                """)
                if cursor.fetchone()["cnt"] == 0:
                    cursor.execute(f"ALTER TABLE fact_bet_tracking ADD COLUMN {col} {col_type}")
            except Exception:
                pass

        # Fetch pending bets
        cursor.execute("""
            SELECT id, game_id, sport, game_date, home_team, away_team,
                   bet_type, pick, pick_side, odds_american, wager_amount,
                   spread_line, total_line
            FROM fact_bet_tracking
            WHERE actual_outcome IS NULL
              AND game_date < CURDATE()
            ORDER BY game_date ASC
        """)
        pending = cursor.fetchall()
        cursor.close()
        conn.close()

        if not pending:
            logger.info("resolve_pending_bets: no pending bets to resolve")
            return {"status": "ok", "resolved_count": 0, "message": "No pending bets"}

        logger.info("resolve_pending_bets: found %d pending bets", len(pending))

        resolved = 0
        errors = []

        for bet in pending:
            try:
                result = _resolve_single_bet(bet)
                if result:
                    resolved += 1
            except Exception as exc:
                logger.warning("Failed to resolve bet %s: %s", bet["id"], exc)
                errors.append({"bet_id": bet["id"], "error": str(exc)})

        logger.info(
            "resolve_pending_bets: resolved %d/%d bets, %d errors",
            resolved, len(pending), len(errors),
        )

        return {
            "status": "ok",
            "resolved_count": resolved,
            "total_pending": len(pending),
            "errors": errors,
        }

    except Exception as exc:
        logger.error("resolve_pending_bets failed: %s", exc)
        return {"status": "error", "message": str(exc)}


def _resolve_single_bet(bet: dict) -> bool:
    """Resolve a single bet by looking up the game result.

    Handles all three bet types correctly:
    - moneyline: did the picked team win outright?
    - spread: did the picked team cover the point spread (ATS)?
    - total: did the game total go over/under the line?

    Returns True if resolved, False if game result not found.
    """
    sport = bet["sport"]
    schema = SCHEMA_MAP.get(sport)
    if not schema:
        logger.warning("Unknown sport for bet resolution: %s", sport)
        return False

    # Fetch actual game result
    try:
        conn = get_connection(schema)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT game_id, home_team, away_team, home_score, away_score, margin
            FROM fact_game_results
            WHERE game_id = %s
            LIMIT 1
            """,
            (bet["game_id"],),
        )
        game = cursor.fetchone()
        cursor.close()
        conn.close()
    except Exception as exc:
        logger.warning("Failed to fetch game %s: %s", bet["game_id"], exc)
        return False

    if not game or game.get("home_score") is None:
        # Game hasn't been ingested or hasn't been played
        return False

    home_score = float(game.get("home_score", 0) or 0)
    away_score = float(game.get("away_score", 0) or 0)
    margin = home_score - away_score  # positive = home won
    total_points = home_score + away_score

    bet_type = bet["bet_type"]
    pick = bet["pick"]
    pick_side = bet.get("pick_side", "")
    is_push = False
    correct = None

    if bet_type == "moneyline":
        # Did the predicted team win outright?
        if home_score == away_score:
            is_push = True
            correct = 0
        else:
            is_home_pick = (
                pick_side == "home"
                or pick == game.get("home_team")
                or _fuzzy_match(pick, game.get("home_team", ""))
            )
            is_away_pick = (
                pick_side == "away"
                or pick == game.get("away_team")
                or _fuzzy_match(pick, game.get("away_team", ""))
            )

            if is_home_pick:
                correct = 1 if home_score > away_score else 0
            elif is_away_pick:
                correct = 1 if away_score > home_score else 0
            else:
                logger.warning("Could not match pick '%s' to game teams", pick)
                return False

    elif bet_type == "spread":
        # Did the picked team cover the point spread (ATS)?
        # spread_line is from home perspective:
        #   spread = -7 means home favored by 7 → home covers if margin > 7
        #   spread = +3 means home underdog by 3 → home covers if margin > -3
        # Formula: home covers when (margin + spread_line) > 0
        spread_line = float(bet.get("spread_line", 0) or 0)
        ats_result = margin + spread_line

        if ats_result == 0:
            is_push = True
            correct = 0
        else:
            is_home_pick = (
                pick_side == "home"
                or _fuzzy_match(bet.get("home_team", ""), pick)
            )
            is_away_pick = (
                pick_side == "away"
                or _fuzzy_match(bet.get("away_team", ""), pick)
            )

            if is_home_pick:
                correct = 1 if ats_result > 0 else 0
            elif is_away_pick:
                correct = 1 if ats_result < 0 else 0
            else:
                logger.warning(
                    "Could not match spread pick '%s' (side=%s) to teams",
                    pick, pick_side,
                )
                return False

    elif bet_type == "total":
        # Did the game total go over or under the line?
        total_line = float(bet.get("total_line", 0) or 0)

        if total_line <= 0:
            # No line stored — cannot resolve accurately
            logger.warning(
                "No total_line stored for bet %s, cannot resolve", bet["id"]
            )
            return False

        if total_points == total_line:
            is_push = True
            correct = 0
        elif pick_side == "over" or "over" in pick.lower():
            correct = 1 if total_points > total_line else 0
        elif pick_side == "under" or "under" in pick.lower():
            correct = 1 if total_points < total_line else 0
        else:
            logger.warning(
                "Could not determine over/under direction for pick '%s'", pick
            )
            return False

    else:
        logger.warning("Unknown bet_type '%s' for bet %s", bet_type, bet["id"])
        return False

    # ---- Calculate P/L based on outcome ----
    wager = float(bet.get("wager_amount", 0) or 0)
    odds_am = bet.get("odds_american")

    if is_push:
        # Push: wager is returned, no win or loss
        profit = 0.0
    elif correct == 1 and odds_am is not None:
        # Win: payout based on American odds
        odds_am = float(odds_am)
        if odds_am > 0:
            profit = wager * (odds_am / 100.0)
        elif odds_am < 0:
            profit = wager * (100.0 / abs(odds_am))
        else:
            profit = wager  # Even odds fallback
    elif correct == 0:
        # Loss: lose the wager
        profit = -wager
    else:
        profit = 0.0

    # Update the tracking record
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE fact_bet_tracking
            SET actual_outcome = %s,
                resolved_at = NOW(),
                profit_loss = %s
            WHERE id = %s
            """,
            (correct, round(profit, 2), bet["id"]),
        )
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as exc:
        logger.warning("Failed to update bet %s: %s", bet["id"], exc)
        return False


def _fuzzy_match(pick: str, team_name: str) -> bool:
    """Check if pick fuzzy-matches a team name."""
    if not pick or not team_name:
        return False
    pick_lower = pick.lower().strip()
    team_lower = team_name.lower().strip()
    return pick_lower in team_lower or team_lower in pick_lower
