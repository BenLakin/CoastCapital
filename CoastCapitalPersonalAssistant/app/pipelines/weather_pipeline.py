"""
Weather Pipeline — fetches current conditions and 5-day forecast from
Open-Meteo (free, no API key required).
"""
import logging
from datetime import datetime

import requests

from app.config import Config

logger = logging.getLogger(__name__)

# ── WMO Weather Code → (description, emoji) ─────────────────────────────────
# https://open-meteo.com/en/docs  —  WMO Weather interpretation codes (WW)
WMO_CODES: dict[int, tuple[str, str]] = {
    0:  ("Clear sky", "\u2600\ufe0f"),           # sunny
    1:  ("Mainly clear", "\U0001f324\ufe0f"),    # sun behind small cloud
    2:  ("Partly cloudy", "\u26c5"),              # sun behind cloud
    3:  ("Overcast", "\u2601\ufe0f"),             # cloud
    45: ("Foggy", "\U0001f32b\ufe0f"),            # fog
    48: ("Depositing rime fog", "\U0001f32b\ufe0f"),
    51: ("Light drizzle", "\U0001f326\ufe0f"),    # sun behind rain cloud
    53: ("Moderate drizzle", "\U0001f327\ufe0f"), # cloud with rain
    55: ("Dense drizzle", "\U0001f327\ufe0f"),
    56: ("Light freezing drizzle", "\U0001f327\ufe0f"),
    57: ("Dense freezing drizzle", "\U0001f327\ufe0f"),
    61: ("Slight rain", "\U0001f326\ufe0f"),
    63: ("Moderate rain", "\U0001f327\ufe0f"),
    65: ("Heavy rain", "\U0001f327\ufe0f"),
    66: ("Light freezing rain", "\U0001f327\ufe0f"),
    67: ("Heavy freezing rain", "\U0001f327\ufe0f"),
    71: ("Slight snowfall", "\U0001f328\ufe0f"),  # cloud with snow
    73: ("Moderate snowfall", "\U0001f328\ufe0f"),
    75: ("Heavy snowfall", "\U0001f328\ufe0f"),
    77: ("Snow grains", "\U0001f328\ufe0f"),
    80: ("Slight rain showers", "\U0001f326\ufe0f"),
    81: ("Moderate rain showers", "\U0001f327\ufe0f"),
    82: ("Violent rain showers", "\U0001f327\ufe0f"),
    85: ("Slight snow showers", "\U0001f328\ufe0f"),
    86: ("Heavy snow showers", "\U0001f328\ufe0f"),
    95: ("Thunderstorm", "\u26c8\ufe0f"),         # cloud with lightning and rain
    96: ("Thunderstorm with slight hail", "\u26c8\ufe0f"),
    99: ("Thunderstorm with heavy hail", "\u26c8\ufe0f"),
}

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _wmo_lookup(code: int) -> tuple[str, str]:
    """Return (description, emoji) for a WMO weather code."""
    return WMO_CODES.get(code, ("Unknown", "\u2753"))


class WeatherPipeline:
    """Fetch current weather and multi-day forecast via Open-Meteo."""

    def fetch(self, zip_code: str | None = None) -> dict:
        """
        Return current conditions + 5-day forecast for *zip_code*
        (defaults to ``Config.WEATHER_ZIP``).
        """
        zip_code = zip_code or Config.WEATHER_ZIP
        lat, lon, location = self._geocode(zip_code)
        current, forecast = self._get_forecast(lat, lon)

        return {
            "location": location,
            "current": current,
            "forecast": forecast,
            "fetched_at": datetime.now().isoformat(),
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _geocode(self, zip_code: str) -> tuple[float, float, str]:
        """Convert a zip / place name to (lat, lon, 'City, State')."""
        resp = requests.get(
            GEOCODE_URL,
            params={"name": zip_code, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results")
        if not results:
            raise ValueError(f"Could not geocode zip code: {zip_code}")

        loc = results[0]
        city = loc.get("name", zip_code)
        admin = loc.get("admin1", "")
        location_str = f"{city}, {admin}" if admin else city
        return loc["latitude"], loc["longitude"], location_str

    def _get_forecast(self, lat: float, lon: float) -> tuple[dict, list[dict]]:
        """Fetch current conditions + 6-day daily forecast from Open-Meteo."""
        resp = requests.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m,apparent_temperature",
                "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
                "timezone": "auto",
                "forecast_days": 6,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        # ── Current conditions ────────────────────────────────────────────────
        cur = data.get("current", {})
        code = cur.get("weather_code", 0)
        desc, icon = _wmo_lookup(code)

        current = {
            "temp_f": cur.get("temperature_2m"),
            "feels_like_f": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "wind_mph": cur.get("wind_speed_10m"),
            "description": desc,
            "icon": icon,
        }

        # ── Daily forecast ────────────────────────────────────────────────────
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        codes = daily.get("weather_code", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])
        precips = daily.get("precipitation_probability_max", [])

        forecast: list[dict] = []
        for i, date_str in enumerate(dates):
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            d_desc, d_icon = _wmo_lookup(codes[i] if i < len(codes) else 0)
            forecast.append({
                "date": date_str,
                "day_name": DAY_NAMES[dt.weekday()],
                "high_f": highs[i] if i < len(highs) else None,
                "low_f": lows[i] if i < len(lows) else None,
                "description": d_desc,
                "icon": d_icon,
                "precip_chance": precips[i] if i < len(precips) else None,
            })

        return current, forecast
