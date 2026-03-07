"""
Weather Service — Fetches 7-day weather forecast from Open-Meteo API.

Uses the Open-Meteo free forecast API (no API key required) to get
precipitation, wind speed, and temperature data. Results are cached
by date so only one API call is made per day.

The service defaults to Manila coordinates but can be extended to accept
per-city coordinates in the future.

PAGASA alert thresholds:
  - Orange rainfall warning: > 30mm in a day
"""
import httpx
from functools import lru_cache
from datetime import date

# Open-Meteo forecast API endpoint (free, no authentication needed)
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Default coordinates (Manila, Philippines)
DEFAULT_LAT = 14.5995
DEFAULT_LON = 120.9842


@lru_cache(maxsize=8)
def _get_forecast_cached(today: date) -> dict:
    """
    Fetch raw forecast data from Open-Meteo, cached by date.

    The lru_cache key is the current date, so the cache naturally refreshes
    once per day. maxsize=8 keeps a week+ of history in memory.
    """
    return _fetch_forecast()


def _fetch_forecast() -> dict:
    """
    Make the actual HTTP request to Open-Meteo.

    Requests 7-day daily data including:
      - precipitation_sum: Total daily rainfall (mm)
      - windspeed_10m_max: Maximum wind speed at 10m height (km/h)
      - temperature_2m_max/min: Daily high/low temperature (°C)
    """
    params = {
        "latitude": DEFAULT_LAT,
        "longitude": DEFAULT_LON,
        "daily": ",".join([
            "precipitation_sum",
            "windspeed_10m_max",
            "temperature_2m_max",
            "temperature_2m_min",
        ]),
        "timezone": "Asia/Manila",
        "forecast_days": 7,
    }

    try:
        response = httpx.get(FORECAST_URL, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        # Return empty data on API failure — the endpoint should still respond
        return {"daily": {"time": [], "precipitation_sum": [], "windspeed_10m_max": []}}


def get_weekly_forecast() -> list:
    """
    Return a structured 7-day weather forecast for the frontend weather widget.

    Returns:
        List of 7 WeatherDay models (auto camelCase), each with:
          - date: ISO date string (e.g. "2025-03-04")
          - precipMm: Total precipitation in mm
          - windKmh: Maximum wind speed in km/h
          - alert: True if precipitation exceeds PAGASA Orange threshold (30mm)
    """
    from app.schemas.responses import WeatherDay

    raw = _get_forecast_cached(date.today())
    daily = raw.get("daily", {})

    days = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])
    wind = daily.get("windspeed_10m_max", [])

    return [
        WeatherDay(
            date=d,
            precip_mm=round(p or 0, 1),
            wind_kmh=round(w or 0, 1),
            alert=(p or 0) > 30,
        )
        for d, p, w in zip(days, precip, wind)
    ]
