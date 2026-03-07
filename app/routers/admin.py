"""
Admin Router — User management and city access assignment.

GET    /api/v1/admin/users                    — List all users
POST   /api/v1/admin/users/{id}/cities        — Assign city access to a user
DELETE /api/v1/admin/users/{id}/cities/{pcode} — Remove city access

All endpoints require admin role.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, UserCityAccess, City
from app.deps import require_admin
from app.schemas.responses import CamelModel, AssignCitiesResponse, MessageResponse

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Response Models ───────────────────────────────────────────────────────

class UserWithCities(CamelModel):
    """User profile with their assigned city list."""
    id:        int
    email:     str
    full_name: str
    role:      str
    cities:    list[str]  # List of pcode strings


class AssignCitiesRequest(CamelModel):
    """Request body for assigning cities to a user."""
    pcodes: list[str]  # List of PSGC codes to assign


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[UserWithCities])
def list_users(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    List all users with their assigned cities.
    Admin only.
    """
    users = db.query(User).all()
    result = []
    for u in users:
        city_pcodes = [access.city_pcode for access in u.city_access]
        result.append(UserWithCities(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            cities=city_pcodes,
        ))
    return result


@router.post("/users/{user_id}/cities", status_code=201, response_model=AssignCitiesResponse)
def assign_cities(
    user_id: int,
    body: AssignCitiesRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Assign city edit access to a user. Admin only.

    Request body (camelCase accepted):
      { "pcodes": ["PH072217000", "PH072218000"] }

    Cities that are already assigned will be skipped (idempotent).
    Invalid pcodes are reported but don't block the valid ones.
    """
    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    added = []
    skipped = []
    invalid = []

    for pcode in body.pcodes:
        # Check if the city exists
        city = db.get(City, pcode)
        if not city:
            invalid.append(pcode)
            continue

        # Check if already assigned
        existing = (
            db.query(UserCityAccess)
            .filter(UserCityAccess.user_id == user_id, UserCityAccess.city_pcode == pcode)
            .first()
        )
        if existing:
            skipped.append(pcode)
            continue

        db.add(UserCityAccess(user_id=user_id, city_pcode=pcode))
        added.append(pcode)

    db.commit()

    return AssignCitiesResponse(
        message=f"City access updated for user {target_user.email}",
        added=added,
        skipped=skipped,
        invalid=invalid,
    )


@router.delete("/users/{user_id}/cities/{pcode}", response_model=MessageResponse)
def remove_city_access(
    user_id: int,
    pcode: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Remove a specific city from a user's edit access. Admin only.
    """
    access = (
        db.query(UserCityAccess)
        .filter(UserCityAccess.user_id == user_id, UserCityAccess.city_pcode == pcode)
        .first()
    )

    if not access:
        raise HTTPException(
            status_code=404,
            detail=f"User {user_id} does not have access to city '{pcode}'",
        )

    db.delete(access)
    db.commit()

    return MessageResponse(message=f"Removed access to '{pcode}' for user {user_id}")
