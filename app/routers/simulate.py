"""
Simulate Router — Stateless disaster scenario simulation.

POST /api/v1/simulate

Recomputes demand scores under a user-specified disaster scenario.
Nothing is persisted — the frontend owns simulation state via URL params.
"""
from fastapi import APIRouter, Request
from app.limiter import limiter
from app.schemas.responses import SimulationRequest
from app.services.demand_service import compute_demand_scores

router = APIRouter()


@router.post("/simulate")
@limiter.limit("5/minute")
def run_simulation(request: Request, body: SimulationRequest):
    """
    Recalculates demand scores under a simulated disaster scenario.

    Request body (camelCase accepted):
      { "hazardType": "typhoon", "severity": 3 }

    Returns the same shape as GET /api/v1/map/demand-heat:
      { "PH072217000": 0.97, "PH072218000": 0.89, ... }

    This is a stateless endpoint — no data is written to the database.
    The frontend stores simulation state in URL search parameters.

    Rate limited: 5 requests per minute.
    """
    scores = compute_demand_scores(body.hazard_type, body.severity)
    return scores
