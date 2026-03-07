"""
Prices Router — Relief goods unit price management.

GET   /api/v1/prices              — List all current unit prices
PATCH /api/v1/prices/{item_key}   — Update a price (admin only)

Prices are in Philippine Pesos (PHP) and apply globally.
They are used to calculate cost estimates in forecast responses.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import User, ItemPrice
from app.deps import require_admin
from app.schemas.responses import CamelModel

router = APIRouter(prefix="/prices", tags=["Prices"])


# ── Request/Response Models ───────────────────────────────────────────────

class PriceResponse(CamelModel):
    """One item's price info."""
    item_key:       str     # e.g. "rice_kg"
    label:          str     # e.g. "Rice"
    unit:           str     # e.g. "kg"
    price_per_unit: float   # PHP per unit
    updated_at:     str     # ISO timestamp


class UpdatePriceRequest(CamelModel):
    """Request body for updating a price."""
    price_per_unit: float   # New price in PHP


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.get("", response_model=list[PriceResponse])
def list_prices(db: Session = Depends(get_db)):
    """
    List all current relief goods unit prices.
    No authentication required — prices are public.
    """
    prices = db.query(ItemPrice).all()
    return [
        PriceResponse(
            item_key=p.item_key,
            label=p.label,
            unit=p.unit,
            price_per_unit=p.price_per_unit,
            updated_at=p.updated_at.isoformat() if p.updated_at else "",
        )
        for p in prices
    ]


@router.patch("/{item_key}", response_model=PriceResponse)
def update_price(
    item_key: str,
    body: UpdatePriceRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Update the unit price for a relief goods item. Admin only.

    Path param: item_key — e.g. "rice_kg", "water_liters"
    Body (camelCase accepted): { "pricePerUnit": 55.0 }
    """
    price = db.query(ItemPrice).filter(ItemPrice.item_key == item_key).first()

    if not price:
        raise HTTPException(
            status_code=404,
            detail=f"Price entry for '{item_key}' not found. "
                   f"Valid keys: rice_kg, water_liters, meds_units, kits_units",
        )

    if body.price_per_unit < 0:
        raise HTTPException(
            status_code=400,
            detail="Price must be non-negative",
        )

    price.price_per_unit = body.price_per_unit
    price.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(price)

    return PriceResponse(
        item_key=price.item_key,
        label=price.label,
        unit=price.unit,
        price_per_unit=price.price_per_unit,
        updated_at=price.updated_at.isoformat(),
    )
