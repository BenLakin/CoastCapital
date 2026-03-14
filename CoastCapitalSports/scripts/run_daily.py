#!/usr/bin/env python3
"""
run_daily.py — Standalone daily pipeline runner for cron scheduling.

Runs the daily MLB and NCAA MBB pipeline (ingest, materialize, score, news, bets).

Usage:
  python scripts/run_daily.py                    # all active sports, today
  python scripts/run_daily.py --sport mlb        # MLB only
  python scripts/run_daily.py --sport ncaa_mbb   # NCAA MBB only
  python scripts/run_daily.py --date 2026-03-07  # specific date
  python scripts/run_daily.py --no-news          # skip news ingest
  python scripts/run_daily.py --no-betting       # skip betting recs

Cron example (daily at 6 AM):
  0 6 * * * cd /app && python scripts/run_daily.py >> /var/log/daily_pipeline.log 2>&1
"""

import argparse
import json
import logging
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from pipelines.daily_sport_pipeline import run_daily_pipeline


def main():
    parser = argparse.ArgumentParser(description="Run daily sports pipeline")
    parser.add_argument(
        "--sport", type=str, default=None,
        help="Single sport to run (mlb, ncaa_mbb, nfl). Default: mlb + ncaa_mbb + nfl",
    )
    parser.add_argument("--date", type=str, default=None, help="Date override (YYYY-MM-DD)")
    parser.add_argument("--no-news", action="store_true", help="Skip news ingestion")
    parser.add_argument("--no-betting", action="store_true", help="Skip betting recommendations")
    parser.add_argument("--bankroll", type=float, default=50.0, help="Bankroll amount (default: 50)")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    sports = [args.sport] if args.sport else ["mlb", "ncaa_mbb", "nfl"]

    result = run_daily_pipeline(
        sports=sports,
        date_str=args.date,
        skip_news=args.no_news,
        skip_betting=args.no_betting,
        bankroll=args.bankroll,
    )

    print(json.dumps(result, indent=2, default=str))

    if result.get("status") != "ok":
        sys.exit(1)


if __name__ == "__main__":
    main()
