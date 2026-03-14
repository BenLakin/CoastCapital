"""
recommender.py — Weekly betting recommendation engine.

Given a bankroll (default $50) and a max-per-game cap (default 50%),
loads production models for each sport, scores upcoming/recent games,
computes expected value from model probability vs market implied probability,
and allocates the bankroll across the best bets using a fractional Kelly
criterion approach.

Public entry point: ``get_betting_recommendations(bankroll, max_pct)``
"""

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from database import get_connection
from features.feature_registry import FEATURE_COLUMNS, TARGET_COLUMNS
from models.pytorch_model import SportsBinaryClassifier

logger = logging.getLogger(__name__)

MODEL_DIR = Path(os.getenv("MODEL_DIR", "/app/model_artifacts"))

SPORTS = ["nfl", "ncaa_mbb", "mlb"]
TARGETS = ["home_win", "cover_home", "total_over"]

# Fractional Kelly — use quarter-Kelly to be conservative
KELLY_FRACTION = 0.25

# Minimum edge (model_prob - implied_prob) required to consider a bet
MIN_EDGE = 0.03

# Standard spread/total odds: -110 American each side (industry standard vig)
STANDARD_SPREAD_TOTAL_ML = -110

# Map model targets to user-facing bet types
BET_TYPE_MAP = {
    "home_win": "moneyline",
    "cover_home": "spread",
    "total_over": "total",
}


def _load_production_model(sport: str, target: str):
    """Load the production (or candidate) model and metadata.

    Returns (model, metadata, stage) or (None, None, None) if unavailable.
    """
    for stage in ("production", "candidate"):
        model_path = MODEL_DIR / f"{sport}_{target}_{stage}.pt"
        meta_path = MODEL_DIR / f"{sport}_{target}_{stage}_metadata.json"
        if model_path.exists() and meta_path.exists():
            with open(meta_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            feature_cols = metadata.get("feature_columns", FEATURE_COLUMNS)
            model = SportsBinaryClassifier(
                input_dim=len(feature_cols),
                hidden_dim=int(metadata.get("hidden_dim", 128)),
                dropout=float(metadata.get("dropout", 0.1)),
            )
            model.load_state_dict(
                torch.load(model_path, map_location="cpu", weights_only=True)
            )
            model.eval()
            return model, metadata, stage
    return None, None, None


def _moneyline_to_implied_prob(ml: float) -> float:
    """Convert American moneyline odds to implied probability."""
    if ml is None or ml == 0:
        return 0.5
    if ml > 0:
        return 100.0 / (ml + 100.0)
    else:
        return abs(ml) / (abs(ml) + 100.0)


def _moneyline_to_decimal_odds(ml: float) -> float:
    """Convert American moneyline to decimal odds (payout per $1 wagered)."""
    if ml is None or ml == 0:
        return 2.0
    if ml > 0:
        return (ml / 100.0) + 1.0
    else:
        return (100.0 / abs(ml)) + 1.0


def _get_upcoming_games(sport: str, lookahead_days: int = 7):
    """Fetch upcoming games that have market odds.

    Only returns future games (game_date >= today) to prevent data leakage
    from completed games with known outcomes.  No fallback to past games.
    """
    schema_map = {
        "nfl": "nfl_silver",
        "ncaa_mbb": "ncaa_mbb_silver",
        "mlb": "mlb_silver",
    }
    schema = schema_map.get(sport)
    if not schema:
        return pd.DataFrame()

    today = datetime.now().date()
    end = today + timedelta(days=lookahead_days)

    try:
        conn = get_connection(schema)
        cursor = conn.cursor(dictionary=True)

        # Only future games — prevents data leakage from completed games
        cursor.execute(
            """
            SELECT
                g.game_id, g.game_date, g.home_team, g.away_team,
                g.home_score, g.away_score,
                o.spread AS market_spread,
                o.total_line AS market_total_line,
                o.moneyline_home AS market_moneyline_home,
                o.moneyline_away AS market_moneyline_away
            FROM fact_game_results g
            LEFT JOIN (
                SELECT t1.*
                FROM fact_market_odds t1
                INNER JOIN (
                    SELECT game_id, MAX(market_timestamp) AS max_ts
                    FROM fact_market_odds
                    GROUP BY game_id
                ) latest
                  ON t1.game_id = latest.game_id
                 AND t1.market_timestamp = latest.max_ts
            ) o ON g.game_id = o.game_id
            WHERE g.game_date >= CURDATE()
              AND g.game_date <= %s
              AND o.moneyline_home IS NOT NULL
            ORDER BY g.game_date ASC
            LIMIT 50
            """,
            (end,),
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        for col in ("game_date",):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
        return df

    except Exception as exc:
        logger.warning("_get_upcoming_games failed for %s: %s", sport, exc)
        return pd.DataFrame()


def _score_games_with_model(sport: str, target: str):
    """Score games using the production model, return predictions with game info.

    Returns a list of dicts with game_id, game_date, home_team, away_team,
    model_prob, market odds info, computed edge/EV, and bet_type.
    """
    model, metadata, stage = _load_production_model(sport, target)
    if model is None:
        return []

    # Get upcoming games with odds (future only — no past games)
    games_df = _get_upcoming_games(sport)
    if games_df.empty:
        return []

    # Score through the modeling pipeline
    try:
        from models.modeling_data import load_modeling_frame, materialize_features_to_modeling_silver

        materialize_features_to_modeling_silver(sport)
        model_df = load_modeling_frame(sport)
        if model_df.empty:
            return []

        # Filter to games that have odds
        game_ids = set(games_df["game_id"].tolist())
        scored_df = model_df[model_df["game_id"].isin(game_ids)].copy()

        # No fallback — if no upcoming games in modeling frame, return empty
        if scored_df.empty:
            return []

        # Note: feature_cols from model metadata does not include target columns.
        # Target columns are only used for post-hoc reporting (actual_result).
        feature_cols = metadata.get("feature_columns", FEATURE_COLUMNS)
        for col in feature_cols:
            if col not in scored_df.columns:
                scored_df[col] = 0.0

        X = torch.tensor(
            scored_df[feature_cols].fillna(0).values.astype(np.float32)
        )
        with torch.no_grad():
            probs = model(X).squeeze().numpy()

        if probs.ndim == 0:
            probs = np.array([float(probs)])

        target_col = TARGET_COLUMNS.get(target, f"target_{target}")
        bet_type = BET_TYPE_MAP.get(target, target)

        results = []
        for i, (_, row) in enumerate(scored_df.iterrows()):
            model_prob = float(probs[i])
            home_team = row.get("home_team", "")
            away_team = row.get("away_team", "")

            # Determine the actual result if available (for reporting only)
            actual = None
            if target_col in row and pd.notna(row.get(target_col)):
                actual = int(row[target_col])

            game_date = row.get("game_date")
            if hasattr(game_date, "strftime"):
                game_date = game_date.strftime("%Y-%m-%d")
            else:
                game_date = str(game_date)[:10] if game_date else None

            # ---- Determine odds and pick names based on bet type ----
            spread_line = None
            total_line = None

            if bet_type == "moneyline":
                # Moneyline: use actual moneyline odds per side
                ml_home = float(row.get("market_moneyline_home", 0) or 0)
                ml_away = float(row.get("market_moneyline_away", 0) or 0)
                implied_s1 = _moneyline_to_implied_prob(ml_home)
                odds_s1 = _moneyline_to_decimal_odds(ml_home)
                implied_s2 = _moneyline_to_implied_prob(ml_away)
                odds_s2 = _moneyline_to_decimal_odds(ml_away)
                odds_am_s1 = int(ml_home) if ml_home else None
                odds_am_s2 = int(ml_away) if ml_away else None
                pick_s1 = home_team
                pick_s2 = away_team
                side_s1 = "home"
                side_s2 = "away"

            elif bet_type == "spread":
                # Spread: standard -110 each side
                spread_line = float(row.get("market_spread", 0) or 0)
                implied_s1 = _moneyline_to_implied_prob(STANDARD_SPREAD_TOTAL_ML)
                odds_s1 = _moneyline_to_decimal_odds(STANDARD_SPREAD_TOTAL_ML)
                implied_s2 = implied_s1
                odds_s2 = odds_s1
                odds_am_s1 = STANDARD_SPREAD_TOTAL_ML
                odds_am_s2 = STANDARD_SPREAD_TOTAL_ML
                pick_s1 = f"{home_team} ({spread_line:+.1f})" if spread_line else home_team
                pick_s2 = f"{away_team} ({-spread_line:+.1f})" if spread_line else away_team
                side_s1 = "home"
                side_s2 = "away"

            else:  # total
                # Total: standard -110 each side
                total_line = float(row.get("market_total_line", 0) or 0)
                implied_s1 = _moneyline_to_implied_prob(STANDARD_SPREAD_TOTAL_ML)
                odds_s1 = _moneyline_to_decimal_odds(STANDARD_SPREAD_TOTAL_ML)
                implied_s2 = implied_s1
                odds_s2 = odds_s1
                odds_am_s1 = STANDARD_SPREAD_TOTAL_ML
                odds_am_s2 = STANDARD_SPREAD_TOTAL_ML
                pick_s1 = f"Over {total_line}" if total_line else "Over"
                pick_s2 = f"Under {total_line}" if total_line else "Under"
                side_s1 = "over"
                side_s2 = "under"

            # Edge & EV: side1 = model_prob, side2 = 1 - model_prob
            edge_s1 = model_prob - implied_s1
            ev_s1 = (model_prob * odds_s1) - 1.0
            edge_s2 = (1 - model_prob) - implied_s2
            ev_s2 = ((1 - model_prob) * odds_s2) - 1.0

            # Common fields
            base = {
                "game_id": row["game_id"],
                "game_date": game_date,
                "sport": sport,
                "target": target,
                "bet_type": bet_type,
                "home_team": home_team,
                "away_team": away_team,
                "actual_result": actual,
                "model_stage": stage,
                "spread_line": spread_line,
                "total_line": total_line,
            }

            # Pick the better side
            if edge_s1 >= edge_s2 and edge_s1 >= MIN_EDGE:
                results.append({
                    **base,
                    "pick": pick_s1,
                    "pick_side": side_s1,
                    "model_prob": round(model_prob, 4),
                    "market_implied_prob": round(implied_s1, 4),
                    "decimal_odds": round(odds_s1, 3),
                    "moneyline": odds_am_s1,
                    "edge": round(edge_s1, 4),
                    "ev": round(ev_s1, 4),
                })
            elif edge_s2 >= MIN_EDGE:
                results.append({
                    **base,
                    "pick": pick_s2,
                    "pick_side": side_s2,
                    "model_prob": round(1 - model_prob, 4),
                    "market_implied_prob": round(implied_s2, 4),
                    "decimal_odds": round(odds_s2, 3),
                    "moneyline": odds_am_s2,
                    "edge": round(edge_s2, 4),
                    "ev": round(ev_s2, 4),
                })

        return results

    except Exception as exc:
        logger.warning("_score_games_with_model failed for %s/%s: %s", sport, target, exc)
        return []


def _allocate_bankroll(bets: list, bankroll: float, max_pct: float) -> list:
    """Allocate bankroll across bets using fractional Kelly criterion.

    Parameters
    ----------
    bets : list of dict
        Each must have 'edge', 'decimal_odds', 'ev'.
    bankroll : float
        Total bankroll (e.g. 50.0).
    max_pct : float
        Maximum fraction of bankroll on any single bet (e.g. 0.5).

    Returns
    -------
    list of dict — same bets with 'kelly_fraction', 'wager', 'potential_profit' added.
    """
    if not bets:
        return []

    max_wager = bankroll * max_pct

    for bet in bets:
        odds = bet["decimal_odds"]
        prob = bet["model_prob"]

        # Kelly criterion: f* = (bp - q) / b
        # where b = decimal_odds - 1, p = model_prob, q = 1 - p
        b = odds - 1.0
        if b <= 0:
            bet["kelly_fraction"] = 0.0
        else:
            kelly = (b * prob - (1.0 - prob)) / b
            kelly = max(0.0, kelly) * KELLY_FRACTION  # fractional Kelly
            bet["kelly_fraction"] = round(kelly, 4)

    # Sort by EV descending
    bets.sort(key=lambda x: x["ev"], reverse=True)

    # Allocate
    remaining = bankroll
    for bet in bets:
        raw_wager = bankroll * bet["kelly_fraction"]
        wager = min(raw_wager, max_wager, remaining)
        wager = round(max(0, wager), 2)
        bet["wager"] = wager
        bet["potential_profit"] = round(wager * (bet["decimal_odds"] - 1), 2)
        remaining -= wager

    # Filter out zero-wager bets
    bets = [b for b in bets if b["wager"] > 0]
    return bets


def _store_bets_to_tracking(bets: list):
    """Store recommended bets to fact_bet_tracking for go-forward tracking."""
    if not bets:
        return
    try:
        conn = get_connection("modeling_internal")
        cursor = conn.cursor()

        # Create table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fact_bet_tracking (
                id INT AUTO_INCREMENT PRIMARY KEY,
                game_id VARCHAR(50) NOT NULL,
                sport VARCHAR(20) NOT NULL,
                game_date DATE NOT NULL,
                home_team VARCHAR(100),
                away_team VARCHAR(100),
                bet_type VARCHAR(20) NOT NULL,
                pick VARCHAR(200) NOT NULL,
                pick_side VARCHAR(10),
                odds_american INT,
                model_probability DOUBLE,
                edge DOUBLE,
                expected_value DOUBLE,
                wager_amount DOUBLE,
                spread_line DOUBLE,
                total_line DOUBLE,
                recommended_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                actual_outcome TINYINT(1),
                resolved_at TIMESTAMP NULL,
                profit_loss DOUBLE,
                week_number INT,
                year INT,
                INDEX idx_bet_tracking_game (game_id, bet_type),
                INDEX idx_bet_tracking_week (year, week_number),
                INDEX idx_bet_tracking_sport (sport, game_date)
            )
        """)

        # Add columns to existing tables if they don't exist
        for col, col_type in [
            ("spread_line", "DOUBLE"),
            ("total_line", "DOUBLE"),
            ("pick_side", "VARCHAR(10)"),
        ]:
            try:
                cursor.execute(f"""
                    SELECT COUNT(*) FROM information_schema.columns
                    WHERE table_schema = 'modeling_internal'
                      AND table_name = 'fact_bet_tracking'
                      AND column_name = '{col}'
                """)
                if cursor.fetchone()[0] == 0:
                    cursor.execute(f"ALTER TABLE fact_bet_tracking ADD COLUMN {col} {col_type}")
            except Exception:
                pass

        today = date.today()
        iso_cal = today.isocalendar()

        for bet in bets:
            # Skip if already tracked for this game + bet type
            cursor.execute(
                "SELECT id FROM fact_bet_tracking WHERE game_id = %s AND bet_type = %s",
                (bet["game_id"], bet.get("bet_type", "unknown")),
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                """
                INSERT INTO fact_bet_tracking
                    (game_id, sport, game_date, home_team, away_team, bet_type,
                     pick, pick_side, odds_american, model_probability,
                     edge, expected_value, wager_amount,
                     spread_line, total_line, week_number, year)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    bet["game_id"],
                    bet["sport"],
                    bet.get("game_date"),
                    bet.get("home_team", ""),
                    bet.get("away_team", ""),
                    bet.get("bet_type", "unknown"),
                    bet.get("pick", ""),
                    bet.get("pick_side", ""),
                    bet.get("moneyline"),
                    bet.get("model_prob"),
                    bet.get("edge"),
                    bet.get("ev"),
                    bet.get("wager", 0),
                    bet.get("spread_line"),
                    bet.get("total_line"),
                    iso_cal[1],
                    iso_cal[0],
                ),
            )

        conn.commit()
        cursor.close()
        conn.close()
        logger.info("Stored %d bets to tracking", len(bets))
    except Exception as exc:
        logger.warning("Failed to store bets to tracking: %s", exc)


def get_betting_recommendations(
    bankroll: float = 50.0,
    max_pct: float = 0.50,
) -> dict:
    """Generate weekly betting recommendations.

    Parameters
    ----------
    bankroll : float
        Total bankroll to allocate (default $50).
    max_pct : float
        Maximum fraction of bankroll on a single game (default 0.50 = 50%).

    Returns
    -------
    dict with 'bankroll', 'max_per_game', 'bets', 'total_wagered',
    'sports_covered', 'generated_at'.
    """
    all_bets = []

    for sport in SPORTS:
        for target in TARGETS:
            try:
                bets = _score_games_with_model(sport, target)
                all_bets.extend(bets)
            except Exception as exc:
                logger.warning(
                    "Betting scan failed for %s/%s: %s", sport, target, exc
                )

    # Deduplicate: keep the bet with the highest edge per game_id AND target
    # This allows one moneyline + one spread + one total per game
    seen = {}
    for bet in all_bets:
        key = (bet["game_id"], bet["target"])
        if key not in seen or bet["edge"] > seen[key]["edge"]:
            seen[key] = bet
    unique_bets = list(seen.values())

    # Allocate bankroll
    allocated = _allocate_bankroll(unique_bets, bankroll, max_pct)

    total_wagered = sum(b["wager"] for b in allocated)
    sports_covered = list(set(b["sport"] for b in allocated))

    # Store bets for go-forward tracking
    _store_bets_to_tracking(allocated)

    return {
        "bankroll": bankroll,
        "max_per_game": round(bankroll * max_pct, 2),
        "bets": allocated,
        "total_wagered": round(total_wagered, 2),
        "remaining_bankroll": round(bankroll - total_wagered, 2),
        "sports_covered": sports_covered,
        "bet_count": len(allocated),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
