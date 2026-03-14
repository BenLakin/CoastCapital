"""
backtest.py — Historical backtesting engine for sports prediction models.

Simulates the past N months of betting activity using the current production
model and the same Quarter-Kelly allocation strategy used in production.
Each week gets a fresh $100 bankroll, and the engine tracks wins, losses,
and profit/loss to compute ROI, accuracy, and AUC.

Public entry point: ``run_backtest(sport, target, months, weekly_bankroll, max_pct)``
"""

import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from database import get_connection
from features.feature_registry import FEATURE_COLUMNS, TARGET_COLUMNS
from betting.recommender import (
    _load_production_model,
    _moneyline_to_implied_prob,
    _moneyline_to_decimal_odds,
    KELLY_FRACTION,
    MIN_EDGE,
    BET_TYPE_MAP,
    STANDARD_SPREAD_TOTAL_ML,
)

logger = logging.getLogger(__name__)


def run_backtest(
    sport: str,
    target: str,
    months: int = 24,
    weekly_bankroll: float = 100.0,
    max_pct: float = 0.50,
) -> dict:
    """Run a historical backtest for a sport/target combination.

    Simulates the past ``months`` months by:
    1. Loading the current production model
    2. Loading historical data from modeling_silver
    3. Splitting into ISO weekly windows
    4. For each week: scoring games, applying Quarter-Kelly allocation,
       checking actual outcomes, recording P/L
    5. Computing cumulative statistics

    Parameters
    ----------
    sport : str
        One of "nfl", "ncaa_mbb", "mlb".
    target : str
        One of "home_win", "cover_home", "total_over".
    months : int
        Number of months to look back (default: 24).
    weekly_bankroll : float
        Simulated bankroll per week (default: $100).
    max_pct : float
        Maximum fraction of bankroll on any single bet (default: 0.50).

    Returns
    -------
    dict with weekly_results, cumulative_pnl, total_roi, accuracy, auc_score,
    and summary statistics.
    """
    logger.info(
        "run_backtest: sport=%s target=%s months=%d bankroll=%.2f",
        sport, target, months, weekly_bankroll,
    )

    # 1. Load model
    model, metadata, stage = _load_production_model(sport, target)
    if model is None:
        return {
            "status": "error",
            "message": f"No model found for {sport}/{target}",
        }

    # 2. Load historical data
    try:
        from models.modeling_data import load_modeling_frame, materialize_features_to_modeling_silver
        materialize_features_to_modeling_silver(sport)
        df = load_modeling_frame(sport)
    except Exception as exc:
        return {"status": "error", "message": f"Failed to load data: {exc}"}

    if df.empty:
        return {"status": "error", "message": "No data available for backtesting"}

    target_col = TARGET_COLUMNS.get(target, f"target_{target}")
    if target_col not in df.columns:
        return {"status": "error", "message": f"Target column {target_col} not found"}

    # Filter to the backtest window
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=months * 30)
    cutoff = cutoff.replace(tzinfo=None)
    df = df[df["game_date"] >= cutoff].copy()
    df = df.dropna(subset=[target_col])

    if df.empty:
        return {"status": "error", "message": f"No data in the past {months} months"}

    # 3. Add ISO week/year columns
    df["_iso_year"] = df["game_date"].dt.isocalendar().year.astype(int)
    df["_iso_week"] = df["game_date"].dt.isocalendar().week.astype(int)
    df["_week_key"] = df["_iso_year"].astype(str) + "-W" + df["_iso_week"].astype(str).str.zfill(2)

    # 4. Score all games with the model
    import torch
    feature_cols = metadata.get("feature_columns", FEATURE_COLUMNS)
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.0

    X = torch.tensor(df[feature_cols].fillna(0).values.astype(np.float32))
    with torch.no_grad():
        probs = model(X).squeeze().numpy()
    if probs.ndim == 0:
        probs = np.array([float(probs)])

    df["_model_prob"] = probs
    df["_actual"] = df[target_col].astype(int)

    # Get market odds/lines from the feature payload if available
    odds_cols = ["market_moneyline_home", "market_moneyline_away",
                 "market_spread", "market_total_line"]
    for col in odds_cols:
        if col not in df.columns:
            df[col] = 0

    bet_type = BET_TYPE_MAP.get(target, target)

    # 5. Simulate week by week
    weekly_results = []
    all_predictions = []
    all_actuals = []

    week_keys = sorted(df["_week_key"].unique())
    for week_key in week_keys:
        week_df = df[df["_week_key"] == week_key].copy()
        if week_df.empty:
            continue

        week_bets = []
        for _, row in week_df.iterrows():
            prob = float(row["_model_prob"])
            actual = int(row["_actual"])

            # ---- Determine odds based on bet type ----
            if bet_type == "moneyline":
                ml_home = float(row.get("market_moneyline_home", 0) or 0)
                ml_away = float(row.get("market_moneyline_away", 0) or 0)
                implied_s1 = _moneyline_to_implied_prob(ml_home)
                odds_s1 = _moneyline_to_decimal_odds(ml_home)
                implied_s2 = _moneyline_to_implied_prob(ml_away)
                odds_s2 = _moneyline_to_decimal_odds(ml_away)
            else:
                # Spread and total: standard -110 each side
                implied_s1 = _moneyline_to_implied_prob(STANDARD_SPREAD_TOTAL_ML)
                odds_s1 = _moneyline_to_decimal_odds(STANDARD_SPREAD_TOTAL_ML)
                implied_s2 = implied_s1
                odds_s2 = odds_s1

            edge_s1 = prob - implied_s1
            ev_s1 = (prob * odds_s1) - 1.0
            edge_s2 = (1 - prob) - implied_s2
            ev_s2 = ((1 - prob) * odds_s2) - 1.0

            # Pick the better side (same logic as recommender)
            # Side1 = home (moneyline/spread) or over (total)
            # Side2 = away (moneyline/spread) or under (total)
            # Correctness: actual==1 means home_win/cover_home/total_over
            if edge_s1 >= edge_s2 and edge_s1 >= MIN_EDGE:
                week_bets.append({
                    "prob": prob,
                    "edge": edge_s1,
                    "ev": ev_s1,
                    "decimal_odds": odds_s1,
                    "pick_side": "home" if bet_type != "total" else "over",
                    "actual": actual,
                    "correct": int(actual == 1),
                })
                all_predictions.append(prob)
                all_actuals.append(actual)
            elif edge_s2 >= MIN_EDGE:
                week_bets.append({
                    "prob": 1 - prob,
                    "edge": edge_s2,
                    "ev": ev_s2,
                    "decimal_odds": odds_s2,
                    "pick_side": "away" if bet_type != "total" else "under",
                    "actual": actual,
                    "correct": int(actual == 0),
                })
                all_predictions.append(1 - prob)
                all_actuals.append(1 - actual)

        if not week_bets:
            weekly_results.append({
                "week": week_key,
                "bets": 0,
                "wins": 0,
                "losses": 0,
                "accuracy": None,
                "pnl": 0.0,
                "roi": 0.0,
                "wagered": 0.0,
            })
            continue

        # Apply Kelly allocation
        max_wager = weekly_bankroll * max_pct
        remaining = weekly_bankroll
        total_pnl = 0.0
        total_wagered = 0.0
        wins = 0
        losses = 0

        # Sort by EV descending
        week_bets.sort(key=lambda x: x["ev"], reverse=True)

        for bet in week_bets:
            b = bet["decimal_odds"] - 1.0
            if b <= 0:
                continue
            kelly = (b * bet["prob"] - (1.0 - bet["prob"])) / b
            kelly = max(0.0, kelly) * KELLY_FRACTION

            raw_wager = weekly_bankroll * kelly
            wager = min(raw_wager, max_wager, remaining)
            wager = round(max(0, wager), 2)

            if wager <= 0:
                continue

            total_wagered += wager
            remaining -= wager

            if bet["correct"]:
                profit = wager * (bet["decimal_odds"] - 1)
                total_pnl += profit
                wins += 1
            else:
                total_pnl -= wager
                losses += 1

        accuracy = wins / (wins + losses) if (wins + losses) > 0 else None
        roi = total_pnl / total_wagered if total_wagered > 0 else 0.0

        weekly_results.append({
            "week": week_key,
            "bets": wins + losses,
            "wins": wins,
            "losses": losses,
            "accuracy": round(accuracy, 4) if accuracy is not None else None,
            "pnl": round(total_pnl, 2),
            "roi": round(roi, 4),
            "wagered": round(total_wagered, 2),
        })

    # 6. Compute aggregate statistics
    total_pnl = sum(r["pnl"] for r in weekly_results)
    total_wagered = sum(r["wagered"] for r in weekly_results)
    total_bets = sum(r["bets"] for r in weekly_results)
    total_wins = sum(r["wins"] for r in weekly_results)
    total_losses = sum(r["losses"] for r in weekly_results)
    overall_accuracy = total_wins / total_bets if total_bets > 0 else None
    overall_roi = total_pnl / total_wagered if total_wagered > 0 else 0.0

    # Cumulative P/L series for charting
    cumulative_pnl = []
    running_total = 0.0
    for r in weekly_results:
        running_total += r["pnl"]
        cumulative_pnl.append(round(running_total, 2))

    # AUC (if we have predictions)
    auc_score = None
    if all_predictions and all_actuals and len(set(all_actuals)) > 1:
        try:
            from sklearn.metrics import roc_auc_score
            auc_score = float(roc_auc_score(all_actuals, all_predictions))
        except Exception:
            pass

    # Max drawdown
    peak = 0.0
    max_drawdown = 0.0
    for cum in cumulative_pnl:
        peak = max(peak, cum)
        drawdown = peak - cum
        max_drawdown = max(max_drawdown, drawdown)

    # Best/worst weeks
    pnl_values = [r["pnl"] for r in weekly_results if r["bets"] > 0]
    best_week_pnl = max(pnl_values) if pnl_values else 0.0
    worst_week_pnl = min(pnl_values) if pnl_values else 0.0

    logger.info(
        "run_backtest: DONE sport=%s target=%s — %d weeks, %d bets, "
        "accuracy=%.3f, ROI=%.1f%%, total P/L=$%.2f",
        sport, target, len(weekly_results), total_bets,
        overall_accuracy or 0, overall_roi * 100, total_pnl,
    )

    return {
        "status": "ok",
        "sport": sport,
        "target": target,
        "bet_type": BET_TYPE_MAP.get(target, target),
        "model_stage": stage,
        "months": months,
        "weekly_bankroll": weekly_bankroll,
        "max_pct": max_pct,
        "weekly_results": weekly_results,
        "cumulative_pnl": cumulative_pnl,
        "summary": {
            "total_weeks": len(weekly_results),
            "weeks_with_bets": len([r for r in weekly_results if r["bets"] > 0]),
            "total_bets": total_bets,
            "total_wins": total_wins,
            "total_losses": total_losses,
            "accuracy": round(overall_accuracy, 4) if overall_accuracy else None,
            "auc": round(auc_score, 4) if auc_score else None,
            "total_wagered": round(total_wagered, 2),
            "total_pnl": round(total_pnl, 2),
            "roi": round(overall_roi, 4),
            "roi_pct": round(overall_roi * 100, 2),
            "max_drawdown": round(max_drawdown, 2),
            "best_week_pnl": round(best_week_pnl, 2),
            "worst_week_pnl": round(worst_week_pnl, 2),
        },
    }
