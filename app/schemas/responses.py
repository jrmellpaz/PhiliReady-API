"""
Pydantic response and request models for all API endpoints.

All models use camelCase for JSON serialization (frontend convention) while
keeping snake_case internally (Python convention). This is handled by
Pydantic's alias_generator.

Example:
  Python:  risk_score=0.88
  JSON:    {"riskScore": 0.88}

Every endpoint must return a CamelModel subclass (not a raw dict) to
guarantee consistent camelCase output.
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional


def to_camel(string: str) -> str:
    """
    Convert a snake_case string to camelCase.
    Example: 'risk_score' -> 'riskScore'
    """
    parts = string.split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


class CamelModel(BaseModel):
    """
    Base model that automatically converts snake_case fields to camelCase
    in JSON responses and accepts camelCase in JSON requests.
    All API models should inherit from this.
    """
    model_config = ConfigDict(
        alias_generator=to_camel,   # snake_case -> camelCase in JSON
        populate_by_name=True,      # Accept both camelCase and snake_case input
        serialize_by_alias=True,    # Output camelCase aliases in responses
    )

    def model_dump(self, **kwargs):
        """Override to always serialize using camelCase aliases."""
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)

    def model_dump_json(self, **kwargs):
        """Override to always serialize using camelCase aliases."""
        kwargs.setdefault("by_alias", True)
        return super().model_dump_json(**kwargs)


# ── Forecast Models ────────────────────────────────────────────────────────

class ForecastPoint(CamelModel):
    """
    One day in a 7-day demand forecast.
    Contains predicted demand for each relief item with confidence intervals
    and cost estimates in Philippine Pesos (PHP).
    """
    day:          str     # Date label, e.g. "Mar 04"
    rice:         float   # Predicted rice demand (kg)
    rice_lower:   float   # Rice 80% confidence interval lower bound
    rice_upper:   float   # Rice 80% confidence interval upper bound
    rice_cost:    float   # Estimated rice cost (PHP)
    water:        float   # Predicted water demand (liters)
    water_lower:  float   # Water lower bound
    water_upper:  float   # Water upper bound
    water_cost:   float   # Estimated water cost (PHP)
    meds:         float   # Predicted medicine kit demand (units)
    meds_lower:   float   # Medicine kits lower bound
    meds_upper:   float   # Medicine kits upper bound
    meds_cost:    float   # Estimated medicine cost (PHP)
    kits:         float   # Predicted hygiene kit demand (units)
    kits_lower:   float   # Hygiene kits lower bound
    kits_upper:   float   # Hygiene kits upper bound
    kits_cost:    float   # Estimated hygiene kits cost (PHP)
    total_cost:   float   # Sum of all item costs for this day (PHP)


# ── City Models ────────────────────────────────────────────────────────────

class CityDemand(CamelModel):
    """Peak single-day demand estimates across the 7-day forecast window."""
    rice:  float   # Peak rice demand (kg)
    water: float   # Peak water demand (liters)
    meds:  float   # Peak medicine kit demand (units)
    kits:  float   # Peak hygiene kit demand (units)


class CityDetailResponse(CamelModel):
    """
    Full city detail including demographics, risk assessment, and peak demand.
    Returned by GET /api/v1/cities/{pcode}.
    Includes all editable parameters so the frontend can display them in forms.
    """
    pcode:       str                   # PSGC code, e.g. "PH072217000"
    name:        str                   # City/municipality name
    province:    str                   # Province name
    region:      str                   # Region name
    population:  int                   # Total population (2024 Census)
    households:  int                   # Number of households
    poverty_pct: float                 # Poverty incidence 0.0-1.0
    is_coastal:  int                   # 0 = inland, 1 = coastal
    flood_zone:  str                   # low / medium / high
    eq_zone:     str                   # low / medium / high
    risk_score:  float                 # Composite risk score 0.0-1.0
    zone_type:   str                   # "coastal" or "inland"
    demand:      CityDemand            # Peak single-day demand estimates
    updated_by:  Optional[str] = None  # Email of last editor
    updated_at:  Optional[str] = None  # ISO timestamp of last edit


class CityUpdateResponse(CamelModel):
    """
    Response after a city edit via PATCH /api/v1/cities/{pcode}.
    Returns complete city state so the frontend can refresh the form.
    """
    message:     str                   # Success message
    pcode:       str                   # PSGC code
    name:        str                   # City/municipality name
    province:    str                   # Province name
    region:      str                   # Region name
    population:  int                   # Total population
    households:  int                   # Number of households
    poverty_pct: float                 # Poverty incidence 0.0-1.0
    is_coastal:  int                   # 0 = inland, 1 = coastal
    flood_zone:  str                   # low / medium / high
    eq_zone:     str                   # low / medium / high
    risk_score:  float                 # Composite risk score 0.0-1.0
    zone_type:   str                   # "coastal" or "inland"
    updated_by:  str                   # Email of the editor
    updated_at:  str                   # ISO timestamp


# ── Simulation Models ──────────────────────────────────────────────────────

class SimulationRequest(CamelModel):
    """
    Request body for POST /api/v1/simulate.
    Specifies a disaster scenario to simulate.
    """
    hazard_type: str   # "typhoon" | "flood" | "earthquake" | "volcanic"
    severity:    int   # 1 (minor) to 4 (catastrophic)


# ── Weather Models ─────────────────────────────────────────────────────────

class WeatherDay(CamelModel):
    """
    One day in a 7-day weather forecast.
    Returned by GET /api/v1/weather.
    """
    date:       str    # ISO date string, e.g. "2025-03-04"
    precip_mm:  float  # Total precipitation in millimeters
    wind_kmh:   float  # Maximum wind speed in km/h
    alert:      bool   # True if precip_mm > 30 (PAGASA Orange threshold)


# ── Admin Models ───────────────────────────────────────────────────────────

class AssignCitiesResponse(CamelModel):
    """Response after assigning city access to a user."""
    message:  str        # Success message
    added:    list[str]  # Newly assigned pcodes
    skipped:  list[str]  # Already-assigned pcodes (no change)
    invalid:  list[str]  # Pcodes not found in the database


class MessageResponse(CamelModel):
    """Generic success message response."""
    message: str


# ── Health Check ───────────────────────────────────────────────────────────

class HealthResponse(CamelModel):
    """Health check response."""
    status:  str
    service: str
    version: str
