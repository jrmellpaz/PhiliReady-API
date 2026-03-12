"""
Cities Router — City demographic detail, peak demand, and data editing.

GET   /api/v1/cities/{pcode}  — City detail + peak demand (public)
PATCH /api/v1/cities/{pcode}  — Edit city parameters (auth + city access required)
"""
from datetime import datetime
from fastapi import APIRouter, Path, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Optional

from app.db.database import get_db
from app.db.models import City, User
from app.deps import RequireCityAccess
from app.services.forecast_service import forecast_city_obj
from app.schemas.responses import (
    CamelModel, CityDetailResponse, CityDemand, CityUpdateResponse,
)
from app.limiter import limiter
from app.services.ai_cache import invalidate_by_pcode

router = APIRouter()


# ── Request Model ──────────────────────────────────────────────────────────

class CityUpdateRequest(CamelModel):
    """
    Editable city parameters. All fields are optional —
    only provided fields will be updated.
    """
    population:  Optional[int]   = None   # Total population
    households:  Optional[int]   = None   # Number of households
    poverty_pct: Optional[float] = None   # Poverty incidence 0.0-1.0
    is_coastal:  Optional[int]   = None   # 0 = inland, 1 = coastal
    flood_zone:  Optional[str]   = None   # low / medium / high
    eq_zone:     Optional[str]   = None   # low / medium / high


# ── Risk Score Computation ────────────────────────────────────────────────

def compute_risk_score(city: City) -> float:
    """
    Recompute the composite risk score from city parameters.
    Called automatically after any city edit.
    Formula: weighted sum of population, poverty, coastal, flood, and EQ factors.
    """
    pop_factor = min(city.population / 2_000_000, 1.0) * 0.25
    pov_factor = (city.poverty_pct or 0.20) * 0.20
    coast_factor = (city.is_coastal or 0) * 0.15
    flood_map = {"low": 0.0, "medium": 0.5, "high": 1.0}
    flood_factor = flood_map.get(city.flood_zone, 0.5) * 0.20
    eq_factor = flood_map.get(city.eq_zone, 0.5) * 0.20
    score = pop_factor + pov_factor + coast_factor + flood_factor + eq_factor
    return round(min(max(score, 0.05), 0.99), 4)


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("/cities/{pcode}", response_model=CityDetailResponse)
@limiter.limit("30/minute")
def get_city_detail(
    request: Request,
    pcode: str = Path(..., description="City PSGC code, e.g. PH072217000"),
    db: Session = Depends(get_db),
):
    """
    Returns demographic, risk, and peak demand data for a single city.
    No authentication required — city data is public.
    """
    city = db.get(City, pcode)
    if not city:
        raise HTTPException(status_code=404, detail=f"City with PSGC code '{pcode}' not found")

    # Compute baseline peak demand (no active hazard simulation)
    forecast = forecast_city_obj(city)
    peak = CityDemand(
        rice=max(d.rice for d in forecast),
        water=max(d.water for d in forecast),
        meds=max(d.meds for d in forecast),
        kits=max(d.kits for d in forecast),
    )

    return CityDetailResponse(
        pcode=city.pcode,
        name=city.name,
        province=city.province,
        region=city.region,
        population=city.population,
        households=city.households,
        poverty_pct=city.poverty_pct,
        is_coastal=city.is_coastal,
        flood_zone=city.flood_zone,
        eq_zone=city.eq_zone,
        risk_score=city.risk_score,
        zone_type="coastal" if city.is_coastal else "inland",
        demand=peak,
        updated_by=city.updated_by,
        updated_at=city.updated_at.isoformat() if city.updated_at else None,
    )


@router.patch("/cities/{pcode}", response_model=CityUpdateResponse)
def update_city(
    pcode: str,
    body: CityUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(RequireCityAccess()),
):
    """
    Edit city parameters. Requires authentication and city access.

    Admin users can edit any city. LGU users can only edit cities
    assigned to them via the admin panel.

    Only provided fields are updated — omitted fields stay unchanged.
    The risk_score is automatically recomputed after any edit.

    Request body (camelCase accepted):
      { "population": 1020000, "floodZone": "medium" }
    """
    city = db.get(City, pcode)
    if not city:
        raise HTTPException(status_code=404, detail=f"City '{pcode}' not found")

    # Track whether any field was actually provided
    has_changes = False

    # Apply provided fields
    if body.population is not None:
        if body.population < 1:
            raise HTTPException(status_code=400, detail="Population must be positive")
        city.population = body.population
        has_changes = True

    if body.households is not None:
        if body.households < 1:
            raise HTTPException(status_code=400, detail="Households must be positive")
        city.households = body.households
        has_changes = True

    if body.poverty_pct is not None:
        if not 0.0 <= body.poverty_pct <= 1.0:
            raise HTTPException(status_code=400, detail="Poverty percentage must be 0.0-1.0")
        city.poverty_pct = body.poverty_pct
        has_changes = True

    if body.is_coastal is not None:
        if body.is_coastal not in (0, 1):
            raise HTTPException(status_code=400, detail="is_coastal must be 0 or 1")
        city.is_coastal = body.is_coastal
        has_changes = True

    if body.flood_zone is not None:
        if body.flood_zone not in ("low", "medium", "high"):
            raise HTTPException(status_code=400, detail="flood_zone must be low, medium, or high")
        city.flood_zone = body.flood_zone
        has_changes = True

    if body.eq_zone is not None:
        if body.eq_zone not in ("low", "medium", "high"):
            raise HTTPException(status_code=400, detail="eq_zone must be low, medium, or high")
        city.eq_zone = body.eq_zone
        has_changes = True

    if not has_changes:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Auto-recompute risk score from updated parameters
    city.risk_score = compute_risk_score(city)

    # Audit trail
    city.updated_by = user.email
    city.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(city)

    invalidate_by_pcode(db, pcode)

    return CityUpdateResponse(
        message=f"Updated city '{city.name}' ({pcode})",
        pcode=city.pcode,
        name=city.name,
        province=city.province,
        region=city.region,
        population=city.population,
        households=city.households,
        poverty_pct=city.poverty_pct,
        is_coastal=city.is_coastal,
        flood_zone=city.flood_zone,
        eq_zone=city.eq_zone,
        risk_score=city.risk_score,
        zone_type="coastal" if city.is_coastal else "inland",
        updated_by=city.updated_by,
        updated_at=city.updated_at.isoformat(),
    )
