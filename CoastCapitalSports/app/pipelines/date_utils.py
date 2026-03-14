"""
date_utils.py — Date iteration and sport-specific season window helpers.
"""

from datetime import datetime, timedelta


def iter_dates(start_date_str: str, end_date_str: str):
    """Yield ISO date strings for every day in [*start_date_str*, *end_date_str*]."""
    start = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    current = start
    while current <= end:
        yield current.isoformat()
        current += timedelta(days=1)

def default_season_window(sport: str, season: int) -> tuple[str, str]:
    """Return ``(start_date, end_date)`` ISO strings for a sport's season."""
    season = int(season)
    if sport == "nfl":
        return f"{season}-08-01", f"{season+1}-02-28"
    if sport == "ncaa_mbb":
        return f"{season}-11-01", f"{season+1}-04-15"
    if sport == "mlb":
        return f"{season}-03-01", f"{season}-11-30"
    raise ValueError(f"Unsupported sport: {sport}")
