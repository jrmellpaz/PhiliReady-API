"""
Demand Score Service — Computes normalized 0.0–1.0 demand scores per city.

Used by the choropleth map endpoint (GET /api/v1/map/demand-heat) and
the simulation endpoint (POST /api/v1/simulate) to color cities by
relative relief demand intensity.

Scoring logic:
  - Baseline (no active hazard): Uses the stored risk_score from the database,
    which is a composite of population, poverty, geography, and hazard zones.
  - Simulation (hazard + severity): Runs a full forecast for each city,
    takes the peak rice demand, normalizes per household, then scales
    all scores to 0–1 relative to the highest-demand city.
"""
from app.db.database import SessionLocal
from app.db.models import City
from app.services.forecast_service import forecast_city


def compute_demand_scores(
    hazard_type: str = None,
    severity: int = None,
) -> dict[str, float]:
    """
    Compute a normalized demand score (0.0–1.0) for every city in the database.

    Args:
        hazard_type: "typhoon" | "flood" | "earthquake" | "volcanic" | None
        severity: 1–4 | None

    Returns:
        Dict mapping PSGC code → demand score.
        Example: {"PH072217000": 0.92, "PH072218000": 0.75, ...}
    """
    db = SessionLocal()
    cities = db.query(City).all()
    db.close()

    raw_scores = {}

    for city in cities:
        if hazard_type and severity:
            # ── Simulation mode ────────────────────────────────────────
            # Run forecast and use the peak rice demand as the raw score.
            # Normalize by household count so large and small cities are
            # comparable (per-household demand intensity).
            try:
                forecast = forecast_city(city.pcode, hazard_type, severity)
                peak_rice = max(d["rice"] for d in forecast)
                raw_scores[city.pcode] = peak_rice / max(city.households, 1)
            except Exception:
                # If forecast fails for a city, use stored risk_score
                raw_scores[city.pcode] = city.risk_score
        else:
            # ── Baseline mode ──────────────────────────────────────────
            # Use the pre-computed risk_score from the database.
            # This avoids running forecasts for all ~330+ cities on every
            # baseline map load.
            raw_scores[city.pcode] = city.risk_score

    if not raw_scores:
        return {}

    # Normalize all scores to 0.0–1.0 range
    max_val = max(raw_scores.values()) or 1.0

    return {
        pcode: round(min(score / max_val, 1.0), 4)
        for pcode, score in raw_scores.items()
    }
