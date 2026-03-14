#!/usr/bin/env python3
"""
run_weekly.py — Standalone weekly optimization runner for cron scheduling.

Runs the full weekly cycle: backfill, materialize, evaluate/refit models,
and generate the optimized $50 weekly betting plan.

Usage:
  python scripts/run_weekly.py                     # default optimization
  python scripts/run_weekly.py --force-refit        # force model refit
  python scripts/run_weekly.py --bankroll 100       # custom bankroll
  python scripts/run_weekly.py --sport mlb          # MLB only

Cron example (Monday at 7 AM):
  0 7 * * 1 cd /app && python scripts/run_weekly.py >> /var/log/weekly_optimization.log 2>&1
"""

import argparse
import json
import logging
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from pipelines.weekly_optimization import run_weekly_optimization


def main():
    parser = argparse.ArgumentParser(description="Run weekly model optimization and betting plan")
    parser.add_argument(
        "--sport", type=str, default=None,
        help="Single sport to optimize (mlb, ncaa_mbb). Default: both",
    )
    parser.add_argument("--bankroll", type=float, default=50.0, help="Weekly bankroll (default: $50)")
    parser.add_argument("--max-pct", type=float, default=0.50, help="Max fraction per game (default: 0.50)")
    parser.add_argument("--force-refit", action="store_true", help="Force model refit even if not stale")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    sports = [args.sport] if args.sport else None

    result = run_weekly_optimization(
        bankroll=args.bankroll,
        max_pct=args.max_pct,
        force_refit=args.force_refit,
        sports=sports,
    )

    # Print full result
    print(json.dumps(result, indent=2, default=str))

    # Print summary for quick scanning
    summary = result.get("summary", {})
    plan = result.get("betting_plan", {})
    print("\n" + "=" * 60)
    print("WEEKLY OPTIMIZATION SUMMARY")
    print("=" * 60)
    print(f"  Models refitted:    {summary.get('models_refitted', 0)}")
    print(f"  Bets recommended:   {summary.get('total_bets', 0)}")
    print(f"  Total wagered:      ${summary.get('total_wagered', 0):.2f}")
    print(f"  Remaining bankroll: ${plan.get('remaining_bankroll', 0):.2f}")
    print(f"  Elapsed:            {summary.get('elapsed_seconds', 0):.1f}s")

    if plan.get("bets"):
        print("\n  RECOMMENDED BETS:")
        print("  " + "-" * 56)
        for bet in plan["bets"]:
            print(
                f"  ${bet['wager']:>6.2f}  {bet['sport'].upper():<8s}  "
                f"{bet['pick']:<25s}  edge: +{bet['edge']*100:.1f}%"
            )
    else:
        print("\n  No value bets found this week.")

    print("=" * 60)

    if result.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
