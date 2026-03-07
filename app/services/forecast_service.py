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

SEVERITY_MULTIPLIER = {1: 0.5, 2: 1.0, 3: 1.6, 4: 2.5}

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models", "prophet")


# ── Price lookup ───────────────────────────────────────────────────────────

def _get_unit_prices() -> dict[str, float]:
    """
    Load current unit prices from the database.
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
    households: int,
    is_coastal: int,
    poverty_pct: float,
    hazard_type: str,
    severity: int,
    horizon: int,
    pcode: str = None,
) -> list[ForecastPoint]:
    """
    Core forecast computation shared by forecast_city and forecast_custom_city.

    Formula:
      demand = displaced_hh × SPHERE_rate × curve_multiplier × severity

    Where:
      - displaced_hh = households × displacement_rate
      - displacement_rate depends on severity, coastal exposure, and poverty
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

    # Get demand curve and severity multiplier
    curve = DEMAND_CURVE.get(hazard_type or "typhoon", DEMAND_CURVE["typhoon"])
    sev_mult = SEVERITY_MULTIPLIER.get(severity or 1, 1.0)

    # Estimate displaced households
    displaced_hh = int(households * 0.35 * sev_mult)

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
                # ── SPHERE formula fallback ────────────────────────────
                multiplier = curve[day_offset] * sev_mult
                base_demand = displaced_hh * item_cfg["sphere_rate"]
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
        households=city.households,
        is_coastal=city.is_coastal,
        poverty_pct=city.poverty_pct or 0.20,
        hazard_type=hazard_type,
        severity=severity,
        horizon=horizon,
        pcode=pcode,
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
        flood_zone: low | medium | high (not used in forecast, for context)
        eq_zone: low | medium | high (not used in forecast, for context)
        hazard_type: typhoon | flood | earthquake | volcanic
        severity: 1–4
        horizon: Number of forecast days (default: 7)

    Returns:
        List of 7 dicts with demand, confidence intervals, and costs.
    """
    return _compute_forecast(
        households=households,
        is_coastal=is_coastal,
        poverty_pct=poverty_pct,
        hazard_type=hazard_type,
        severity=severity,
        horizon=horizon,
        pcode=None,  # No DB lookup, no Prophet models
    )
