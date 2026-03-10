"""
Forecast Service — Predicts 7-day relief demand for a given city.

Primary engine: SPHERE-standard formula with hazard-specific demand curves.
Optional enhancement: Pre-trained Prophet models (if .pkl files exist).

Features:
  - forecast_city(): Forecast for an existing city (DB lookup)
  - forecast_custom_city(): Forecast for hypothetical params (no DB)
  - Cost estimation: Multiplies demand × unit price from item_prices table

Usage:
    from app.services.forecast_service import forecast_city
    result = forecast_city("PH072217000", hazard_type="typhoon", severity=3)
"""
import os
from datetime import date, timedelta
from functools import lru_cache

from app.db.database import SessionLocal
from app.db.models import City, ItemPrice
from app.schemas.responses import ForecastPoint


# ── Relief item configuration ─────────────────────────────────────────────
# Central config for all relief items. To add/change items, edit this dict
# and add corresponding DB columns in models.py + seed price in seed_data.py.

RELIEF_ITEMS = {
    "rice_kg": {
        "label": "Rice",
        "short": "rice",          # Key used in API responses
        "unit": "kg",
        "sphere_rate": 1.5,       # kg per household per day
    },
    "water_liters": {
        "label": "Water",
        "short": "water",
        "unit": "L",
        "sphere_rate": 15.0,      # liters per household per day
    },
    "meds_units": {
        "label": "Medicine Kits",
        "short": "meds",
        "unit": "units",
        "sphere_rate": 0.08,      # ~1 kit per 12 families/day
    },
    "kits_units": {
        "label": "Hygiene Kits",
        "short": "kits",
        "unit": "units",
        "sphere_rate": 0.07,      # ~1 kit per 14 families/day
    },
}


# ── Demand curves ──────────────────────────────────────────────────────────

DEMAND_CURVE = {
    "typhoon":    [0.2, 1.0, 1.6, 1.4, 1.0, 0.7, 0.4],
    "flood":      [0.3, 0.8, 1.0, 0.8, 0.5, 0.3, 0.1],
    "earthquake": [1.2, 0.9, 0.6, 0.3, 0.2, 0.1, 0.1],
    "volcanic":   [0.1, 0.3, 0.6, 0.8, 0.7, 0.5, 0.3],
}

# ── Displacement model constants ──────────────────────────────────────────
# Base fraction of households displaced, indexed by severity (1-4).
BASE_DISPLACEMENT = {1: 0.10, 2: 0.20, 3: 0.35, 4: 0.55}

# Hazard-zone alignment: amplifies/dampens displacement based on how
# exposed the area is to the specific hazard type being simulated.
ZONE_MODIFIER = {"low": 0.7, "medium": 1.0, "high": 1.3}

# ── Seasonal multipliers (Philippine climate) ─────────────────────────────
# Applies to typhoon and flood only. Based on wet/dry season patterns.
# Peak: Aug-Oct (monsoon + typhoon season). Low: Jan-Mar (dry season).
SEASONAL_MULTIPLIER = {
    1: 0.85, 2: 0.85, 3: 0.85,       # Dry season
    4: 0.90, 5: 0.90,                 # Pre-monsoon transition
    6: 1.05, 7: 1.05,                 # Southwest monsoon begins
    8: 1.15, 9: 1.15, 10: 1.15,      # Peak typhoon + monsoon
    11: 1.05,                          # Late typhoon season
    12: 0.90,                          # Transition to dry
}

# National average household size (PSA, 2020 Census)
NATIONAL_AVG_HH_SIZE = 4.1

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "prophet")


# ── Price lookup ───────────────────────────────────────────────────────────

@lru_cache(maxsize=4)
def _get_unit_prices_cached(today: date) -> dict[str, float]:
    """
    Load current unit prices from the database, cached daily.
    The date param ensures the cache refreshes once per day.
    Returns a dict mapping item_key → price_per_unit (PHP).
    Falls back to hardcoded defaults if DB is unavailable.
    """
    try:
        db = SessionLocal()
        prices = db.query(ItemPrice).all()
        db.close()
        if prices:
            return {p.item_key: p.price_per_unit for p in prices}
    except Exception:
        pass

    # Fallback defaults (PHP)
    return {
        "rice_kg": 50.0,
        "water_liters": 15.0,
        "meds_units": 500.0,
        "kits_units": 350.0,
    }


def _get_unit_prices() -> dict[str, float]:
    """Get cached unit prices (refreshes daily)."""
    return _get_unit_prices_cached(date.today())


# ── Prophet model loading (optional) ──────────────────────────────────────

@lru_cache(maxsize=256)
def _load_prophet_model(pcode: str, item: str):
    """Attempt to load a pre-trained Prophet model. Returns None if not found."""
    path = os.path.join(MODEL_DIR, f"{pcode}_{item}.pkl")
    if not os.path.exists(path):
        return None
    try:
        import joblib
        return joblib.load(path)
    except ImportError:
        return None


def _prophet_forecast(model, hazard_type: str, severity: int, horizon: int = 7):
    """Generate a forecast using a pre-trained Prophet model."""
    future = model.make_future_dataframe(periods=horizon, freq="D", include_history=False)
    future["hazard_active"] = 1 if hazard_type else 0
    future["severity"] = severity if severity else 0
    forecast_df = model.predict(future)
    return forecast_df[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(horizon)


# ── Core forecast computation ─────────────────────────────────────────────

def _compute_forecast(
    population: int,
    households: int,
    is_coastal: int,
    poverty_pct: float,
    flood_zone: str,
    eq_zone: str,
    hazard_type: str,
    severity: int,
    horizon: int,
    pcode: str = None,
) -> list[ForecastPoint]:
    """
    Core forecast computation shared by forecast_city and forecast_custom_city.

    Displacement model:
      displacement_rate = base_rate × zone_mod × coastal_mod × vulnerability
                          × seasonal
      displaced_hh      = households × displacement_rate  (capped at 85%)
      demand             = displaced_hh × SPHERE_rate × curve_multiplier
                          × hh_size_factor

    Factors:
      - base_rate:       severity-driven (10%–55% of households)
      - zone_mod:        hazard-zone alignment (compound for typhoon)
      - coastal_mod:     +20% for coastal areas during typhoons/floods
      - vulnerability:   non-linear poverty curve (×1.0 to ×2.2)
      - seasonal:        wet/dry season multiplier (typhoon/flood only)
      - hh_size_factor:  scales demand by avg persons per household
    """
    # Get prices for cost estimation
    unit_prices = _get_unit_prices()

    # Try Prophet models if pcode is provided
    prophet_results = {}
    if pcode:
        for item_key in RELIEF_ITEMS:
            model = _load_prophet_model(pcode, item_key)
            if model is not None:
                try:
                    prophet_results[item_key] = _prophet_forecast(
                        model, hazard_type, severity, horizon
                    )
                except Exception:
                    pass

    # Get demand curve
    curve = DEMAND_CURVE.get(hazard_type or "typhoon", DEMAND_CURVE["typhoon"])

    # ── Compute displaced households using all city parameters ─────────
    eff_severity = severity or 1
    base_rate = BASE_DISPLACEMENT.get(eff_severity, 0.20)

    # Hazard-zone alignment with compound interaction
    eff_hazard = hazard_type or "typhoon"
    if eff_hazard == "typhoon":
        # Compound: typhoon uses flood_zone (primary) + eq_zone at 30%
        # strength (structural vulnerability to wind loading)
        flood_mod = ZONE_MODIFIER.get(flood_zone or "medium", 1.0)
        eq_raw = ZONE_MODIFIER.get(eq_zone or "medium", 1.0)
        struct_mod = 1.0 + (eq_raw - 1.0) * 0.3
        zone_mod = flood_mod * struct_mod
        coastal_mod = 1.2 if is_coastal else 1.0
    elif eff_hazard == "flood":
        zone_mod = ZONE_MODIFIER.get(flood_zone or "medium", 1.0)
        coastal_mod = 1.2 if is_coastal else 1.0
    elif eff_hazard == "earthquake":
        zone_mod = ZONE_MODIFIER.get(eq_zone or "medium", 1.0)
        coastal_mod = 1.0
    else:  # volcanic or unknown
        zone_mod = 1.0
        coastal_mod = 1.0

    # Non-linear poverty vulnerability: extreme poverty creates
    # disproportionate vulnerability (weaker housing, no savings)
    eff_poverty = poverty_pct or 0.20
    vulnerability = 1.0 + (eff_poverty ** 0.7) * 1.2

    # Seasonal adjustment (typhoon/flood only)
    if eff_hazard in ("typhoon", "flood"):
        seasonal = SEASONAL_MULTIPLIER.get(date.today().month, 1.0)
    else:
        seasonal = 1.0

    displacement_rate = min(
        base_rate * zone_mod * coastal_mod * vulnerability * seasonal, 0.85
    )
    displaced_hh = int(households * displacement_rate)

    # Household size scaling: larger families need more supplies per HH
    avg_hh_size = population / max(households, 1)
    hh_size_factor = avg_hh_size / NATIONAL_AVG_HH_SIZE

    results = []
    today = date.today()

    for day_offset in range(horizon):
        forecast_date = today + timedelta(days=day_offset)
        day_label = forecast_date.strftime("%b %d")

        # Collect per-item values
        item_vals = {}   # {short: (val, lower, upper, cost)}
        total_cost = 0.0

        for item_key, item_cfg in RELIEF_ITEMS.items():
            short = item_cfg["short"]

            if item_key in prophet_results:
                # ── Prophet model prediction ───────────────────────────
                row = prophet_results[item_key].iloc[day_offset]
                val   = max(0, round(float(row["yhat"]), 1))
                lower = max(0, round(float(row["yhat_lower"]), 1))
                upper = max(0, round(float(row["yhat_upper"]), 1))
            else:
                # ── SPHERE formula fallback ────────────────────────────────
                multiplier = curve[day_offset]
                base_demand = displaced_hh * item_cfg["sphere_rate"] * hh_size_factor
                val   = round(base_demand * multiplier, 1)
                lower = round(val * 0.80, 1)
                upper = round(val * 1.20, 1)

            # Cost estimation: demand x unit price
            price = unit_prices.get(item_key, 0)
            cost = round(val * price, 2)
            total_cost += val * price
            item_vals[short] = (val, lower, upper, cost)

        # Build a ForecastPoint (camelCase auto-conversion via Pydantic)
        point = ForecastPoint(
            day=day_label,
            rice=item_vals["rice"][0],
            rice_lower=item_vals["rice"][1],
            rice_upper=item_vals["rice"][2],
            rice_cost=item_vals["rice"][3],
            water=item_vals["water"][0],
            water_lower=item_vals["water"][1],
            water_upper=item_vals["water"][2],
            water_cost=item_vals["water"][3],
            meds=item_vals["meds"][0],
            meds_lower=item_vals["meds"][1],
            meds_upper=item_vals["meds"][2],
            meds_cost=item_vals["meds"][3],
            kits=item_vals["kits"][0],
            kits_lower=item_vals["kits"][1],
            kits_upper=item_vals["kits"][2],
            kits_cost=item_vals["kits"][3],
            total_cost=round(total_cost, 2),
        )
        results.append(point)

    return results


# ── Public API ─────────────────────────────────────────────────────────────

def forecast_city(
    pcode: str,
    hazard_type: str = None,
    severity: int = None,
    horizon: int = 7,
) -> list[ForecastPoint]:
    """
    Generate a 7-day relief demand forecast for an existing city (DB lookup).

    Args:
        pcode: PSGC code (e.g. "PH072217000")
        hazard_type: "typhoon" | "flood" | "earthquake" | "volcanic" | None
        severity: 1–4 (None = no active disaster, defaults to severity 1)
        horizon: Number of forecast days (default: 7)

    Returns:
        List of 7 dicts with day label, demand, confidence intervals, and costs.
    """
    db = SessionLocal()
    city = db.get(City, pcode)
    db.close()

    if not city:
        raise ValueError(f"City {pcode} not found")

    return _compute_forecast(
        population=city.population,
        households=city.households,
        is_coastal=city.is_coastal,
        poverty_pct=city.poverty_pct or 0.20,
        flood_zone=city.flood_zone or "medium",
        eq_zone=city.eq_zone or "medium",
        hazard_type=hazard_type,
        severity=severity,
        horizon=horizon,
        pcode=pcode,
    )


def forecast_city_obj(
    city: City,
    hazard_type: str = None,
    severity: int = None,
    horizon: int = 7,
) -> list[ForecastPoint]:
    """
    Generate a 7-day forecast using an already-loaded City ORM object.
    Avoids the redundant DB session that forecast_city() opens.
    """
    return _compute_forecast(
        population=city.population,
        households=city.households,
        is_coastal=city.is_coastal,
        poverty_pct=city.poverty_pct or 0.20,
        flood_zone=city.flood_zone or "medium",
        eq_zone=city.eq_zone or "medium",
        hazard_type=hazard_type,
        severity=severity,
        horizon=horizon,
        pcode=city.pcode,
    )


def forecast_custom_city(
    population: int,
    households: int,
    is_coastal: int = 0,
    poverty_pct: float = 0.20,
    flood_zone: str = "medium",
    eq_zone: str = "medium",
    hazard_type: str = "typhoon",
    severity: int = 2,
    horizon: int = 7,
) -> list[ForecastPoint]:
    """
    Generate a 7-day forecast for a hypothetical custom city (no DB lookup).
    Used by the simulator endpoint for unauthenticated what-if scenarios.

    Args:
        population: Total population
        households: Number of households
        is_coastal: 0 or 1
        poverty_pct: 0.0–1.0
        flood_zone: low | medium | high
        eq_zone: low | medium | high
        hazard_type: typhoon | flood | earthquake | volcanic
        severity: 1–4
        horizon: Number of forecast days (default: 7)

    Returns:
        List of 7 dicts with demand, confidence intervals, and costs.
    """
    return _compute_forecast(
        population=population,
        households=households,
        is_coastal=is_coastal,
        poverty_pct=poverty_pct,
        flood_zone=flood_zone,
        eq_zone=eq_zone,
        hazard_type=hazard_type,
        severity=severity,
        horizon=horizon,
        pcode=None,  # No DB lookup, no Prophet models
    )
