#!/usr/bin/env python3
"""
run_bracket.py — NCAA Men's Basketball Tournament bracket optimizer.

Runs the full Monte Carlo simulation + contrarian bracket optimization
N times and stores results for web dashboard review.

Usage:
  python scripts/run_bracket.py                           # current year, 10 runs
  python scripts/run_bracket.py --year 2025               # specific season
  python scripts/run_bracket.py --num-sims 5              # fewer optimization runs
  python scripts/run_bracket.py --mc-sims 5000            # fewer MC sims per run
  python scripts/run_bracket.py --mode append             # append to existing runs
  python scripts/run_bracket.py --pool-size 50 --risk 0.7 # aggressive contrarian

Cron example (run after Selection Sunday):
  0 20 * * 0 cd /app && python scripts/run_bracket.py >> /var/log/bracket.log 2>&1
"""

import argparse
import json
import logging
import sys
import os
from datetime import datetime

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from bracket.historical import run_historical_bracket


def main():
    parser = argparse.ArgumentParser(description="Run NCAA bracket optimization")
    parser.add_argument(
        "--year", type=int, default=datetime.now().year,
        help="Tournament season year (default: current year)",
    )
    parser.add_argument(
        "--num-sims", "-n", type=int, default=10,
        help="Number of full optimization runs (default: 10)",
    )
    parser.add_argument(
        "--mc-sims", type=int, default=10000,
        help="Monte Carlo simulations per run (default: 10000)",
    )
    parser.add_argument(
        "--mode", choices=["append", "overwrite"], default="overwrite",
        help="append to existing runs or overwrite (default: overwrite)",
    )
    parser.add_argument(
        "--pool-size", type=int, default=100,
        help="Assumed bracket pool size (default: 100)",
    )
    parser.add_argument(
        "--risk", type=float, default=0.3,
        help="Contrarian risk tolerance 0-1 (default: 0.3)",
    )
    parser.add_argument("--no-html", action="store_true", help="Skip HTML generation")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    print(f"\n{'=' * 60}")
    print(f"NCAA BRACKET OPTIMIZER")
    print(f"{'=' * 60}")
    print(f"  Season:         {args.year}")
    print(f"  Optimization runs: {args.num_sims}")
    print(f"  MC sims/run:    {args.mc_sims}")
    print(f"  Mode:           {args.mode}")
    print(f"  Pool size:      {args.pool_size}")
    print(f"  Risk tolerance: {args.risk}")
    print(f"{'=' * 60}\n")

    result = run_historical_bracket(
        season=args.year,
        n_simulations=args.mc_sims,
        n_runs=args.num_sims,
        pool_size=args.pool_size,
        risk_tolerance=args.risk,
        output_html=not args.no_html,
        overwrite=(args.mode == "overwrite"),
    )

    # Print summary
    print(f"\n{'=' * 60}")
    print("BRACKET OPTIMIZATION RESULTS")
    print(f"{'=' * 60}")
    print(f"  Status:           {result['status']}")
    print(f"  Season:           {result['season']}")
    print(f"  Batch ID:         {result['run_batch_id']}")
    print(f"  Runs completed:   {result['n_runs']}")
    print(f"  Actual results:   {'Yes' if result['has_actual_results'] else 'No'}")

    if result.get("runs"):
        print(f"\n  RANKED BRACKETS:")
        print(f"  {'Rank':<6} {'Counter':<10} {'Champion':<25} {'Expected Pts':<15}")
        print(f"  {'-' * 56}")
        for run in result["runs"]:
            default_marker = " *DEFAULT*" if run["priority_ranking"] == 1 else ""
            print(
                f"  {run['priority_ranking']:<6} "
                f"{run['simulation_counter']:<10} "
                f"{run['champion']:<25} "
                f"{run['expected_score']:<15.1f}"
                f"{default_marker}"
            )

    if result.get("html_path"):
        print(f"\n  HTML bracket: {result['html_path']}")

    print(f"{'=' * 60}\n")

    # Print full JSON result
    print(json.dumps(result, indent=2, default=str))

    if result.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
