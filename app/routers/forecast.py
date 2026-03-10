"""
Forecast Router — 7-day demand forecast for a single city.

GET /api/v1/forecast/{pcode}

Returns daily demand predictions with confidence intervals for
all four relief items (rice, water, medicine kits, hygiene kits).
All response keys are camelCase.
"""
from fastapi import APIRouter, Path, Query, Request, HTTPException
from fastapi.responses import JSONResponse
from app.limiter import limiter
from app.services.forecast_service import forecast_city

router = APIRouter()


@router.get("/forecast/{pcode}")
@limiter.limit("20/minute")
def get_forecast(
    request: Request,
    pcode: str = Path(
        ...,
        description="City PSGC code, e.g. PH072217000"
    ),
    hazard_type: str = Query(
        None,
        description="Hazard type: typhoon | flood | earthquake | volcanic"
    ),
    severity: int = Query(
        None,
        ge=1, le=4,
        description="Severity level: 1 (minor) to 4 (catastrophic)"
    ),
):
    """
    Returns a 7-day demand forecast for the specified city.

    Each day includes predicted demand and +/-20% confidence intervals
    for rice (kg), water (L), medicine kits, and hygiene kits.
    All keys are camelCase (e.g. riceLower, totalCost).

    Rate limited: 20 requests per minute.
    """
    try:
        forecast = forecast_city(pcode, hazard_type, severity)
        # Serialize with camelCase aliases
        return JSONResponse([point.model_dump(by_alias=True) for point in forecast])
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
