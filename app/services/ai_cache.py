"""
app/services/ai_cache.py
DB helpers for reading, writing, and invalidating AI assessment cache entries.

Cache key: (pcode, hazard, severity)
  - Baseline:   hazard='',   severity=0
  - Simulation: hazard='typhoon', severity=2  (etc.)
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import AiAssessmentCache


def get_cached(
    db: Session,
    pcode: str,
    hazard: str,
    severity: int,
) -> AiAssessmentCache | None:
    """Return cached entry or None if not found."""
    return (
        db.query(AiAssessmentCache)
        .filter_by(pcode=pcode, hazard=hazard, severity=severity)
        .first()
    )


def save_cached(
    db: Session,
    pcode: str,
    hazard: str,
    severity: int,
    text: str,
) -> AiAssessmentCache:
    """Insert or update the cached text for this city/scenario."""
    entry = get_cached(db, pcode, hazard, severity)
    now = datetime.now(timezone.utc)

    if entry:
        entry.text = text
        entry.generated_at = now
    else:
        entry = AiAssessmentCache(
            pcode=pcode,
            hazard=hazard,
            severity=severity,
            text=text,
            generated_at=now,
        )
        db.add(entry)

    db.commit()
    db.refresh(entry)
    return entry


def invalidate_by_pcode(db: Session, pcode: str) -> int:
    """
    Delete ALL cached assessments for a city (all scenarios).
    Called automatically from the PATCH /cities/{pcode} endpoint
    whenever a city's parameters are edited.

    Returns the number of rows deleted.
    """
    deleted = (
        db.query(AiAssessmentCache)
        .filter_by(pcode=pcode)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted