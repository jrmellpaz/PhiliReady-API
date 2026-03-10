"""
Map Router — Choropleth demand heatmap endpoint.

GET /api/v1/map/demand-heat

Returns normalized demand scores (0.0–1.0) for all cities.
The frontend maps these scores to choropleth colors on the map.
"""
from fastapi import APIRouter, Query, Request
from app.limiter import limiter
from app.services.demand_service import compute_demand_scores

router = APIRouter()


@router.get("/map/demand-heat")
@limiter.limit("10/minute")
def get_demand_heatmap(
    request: Request,
    hazard_type: str = Query(
        None,
        description="Hazard type filter: typhoon | flood | earthquake | volcanic"
    ),
    severity: int = Query(
        None,
        ge=1, le=4,
        description="Severity level: 1 (minor) to 4 (catastrophic)"
    ),
):
    """
    Returns normalized demand scores for all cities/municipalities.

    Without query params: returns baseline risk scores.
    With hazard_type + severity: computes simulation-based demand scores.

    Response shape:
      { "PH072217000": 0.92, "PH072218000": 0.71, ... }

    Rate limited: 10 requests per minute.
    """
    scores = compute_demand_scores(hazard_type, severity)
    return scores
