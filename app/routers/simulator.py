"""
Simulator Router — Custom city forecast calculator (no auth required).

GET /api/v1/simulator/forecast

Accepts city parameters as query params and returns a 7-day forecast.
Nothing is persisted — purely computational. Parameters are designed to
work as URL search params so the frontend can store simulation state in
the URL (persists across refreshes without database writes).

Both authenticated and unauthenticated users can use this endpoint.
All response keys are camelCase.
"""
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from app.services.forecast_service import forecast_custom_city

router = APIRouter(prefix="/simulator", tags=["Simulator"])


@router.get("/forecast")
def simulate_custom_city(
    population: int = Query(
        ..., ge=1,
        description="Total population of the hypothetical city"
    ),
    households: int = Query(
        None, ge=1,
        description="Number of households (if omitted, estimated from population / 4.1)"
    ),
    is_coastal: int = Query(
        0, ge=0, le=1,
        description="Is the city coastal? 0 = inland, 1 = coastal"
    ),
    poverty_pct: float = Query(
        0.20, ge=0.0, le=1.0,
        description="Poverty incidence (0.0-1.0)"
    ),
    flood_zone: str = Query(
        "medium",
        description="Flood zone classification: low | medium | high"
    ),
    eq_zone: str = Query(
        "medium",
        description="Earthquake zone classification: low | medium | high"
    ),
    hazard_type: str = Query(
        "typhoon",
        description="Simulated hazard: typhoon | flood | earthquake | volcanic"
    ),
    severity: int = Query(
        2, ge=1, le=4,
        description="Disaster severity: 1 (minor) to 4 (catastrophic)"
    ),
):
    """
    Generate a 7-day relief demand forecast for a hypothetical custom city.

    All parameters are passed as query params so the frontend can store
    them in URL search params (persists across page refreshes).

    No authentication required. Nothing is saved to the database.
    All response keys are camelCase.
    """
    # Estimate households if not provided
    if households is None:
        households = max(1, int(population / 4.1))

    forecast = forecast_custom_city(
        population=population,
        households=households,
        is_coastal=is_coastal,
        poverty_pct=poverty_pct,
        flood_zone=flood_zone,
        eq_zone=eq_zone,
        hazard_type=hazard_type,
        severity=severity,
    )
    # Serialize with camelCase aliases
    return JSONResponse([point.model_dump(by_alias=True) for point in forecast])
