"""
Weather Router — 7-day weather forecast from Open-Meteo.

GET /api/v1/weather

Returns daily precipitation, wind speed, and PAGASA alert status.
Currently defaults to Manila; can be extended with lat/lon params.
All response keys are camelCase.
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from app.limiter import limiter
from app.services.weather_service import get_weekly_forecast

router = APIRouter()


@router.get("/weather")
@limiter.limit("30/minute")
def get_weather(request: Request):
    """
    Returns a 7-day weather forecast for the Philippines (Manila default).

    Each day includes:
      - date: ISO date string
      - precipMm: Total precipitation in millimeters
      - windKmh: Maximum wind speed in km/h
      - alert: True if precipitation exceeds PAGASA Orange threshold (30mm)

    Data is cached daily — only one Open-Meteo API call per day.
    All keys are camelCase.

    Rate limited: 30 requests per minute.
    """
    forecast = get_weekly_forecast()
    return JSONResponse([day.model_dump(by_alias=True) for day in forecast])
