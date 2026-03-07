# PhiliReady — Backend Implementation Plan
## Must-Have Features Only

**Stack:** FastAPI 0.115.x · Python 3.11+ · SQLite · SQLAlchemy 2.x · pandas 2.x  
**Map Level:** City / Municipality (All Philippines — ~1,642 LGUs)  
**Forecast Engine:** SPHERE-standard formula (primary) · Prophet (optional)  
**Deployment:** Railway  
**Serves:** TanStack Start frontend (deployed on Vercel)

---

## Project Setup

### 1. Initialize Project

```bash
mkdir philiready-backend && cd philiready-backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install fastapi==0.115.4
pip install uvicorn[standard]
pip install pandas==2.2.3
pip install numpy
pip install sqlalchemy==2.0.36
pip install httpx
pip install python-dotenv
# Optional — for Prophet model training:
# pip install prophet==1.1.6
# pip install joblib
# pip install scikit-learn
```

Freeze after install:
```bash
pip freeze > requirements.txt
```

### 3. Folder Structure

```
philiready-backend/
├── app/
│   ├── main.py                   # FastAPI app + CORS + router registration
│   ├── routers/
│   │   ├── map.py                # GET /api/map/demand-heat
│   │   ├── forecast.py           # GET /api/forecast/{pcode}
│   │   ├── simulate.py           # POST /api/simulate
│   │   └── cities.py             # GET /api/cities/{pcode}
│   ├── services/
│   │   ├── forecast_service.py   # Prophet model loading + prediction
│   │   ├── demand_service.py     # Demand score calculation
│   │   └── weather_service.py    # Open-Meteo API client
│   ├── models/
│   │   └── prophet/              # Serialized .pkl files per city
│   ├── db/
│   │   ├── database.py           # SQLAlchemy engine + session
│   │   ├── models.py             # ORM table definitions
│   │   └── seed_data.py          # ← Run once to populate PostgreSQL
│   └── schemas/
│       └── responses.py          # Pydantic response models
├── data/
│   ├── cebu_cities.csv           # City list with PSGC, population, coords
│   └── historical_distributions/ # Synthetic relief distribution CSVs
├── .env
├── requirements.txt
└── Procfile                      # For Railway deployment
```

### 4. Environment Variables

```env
# .env  (local development)
# No DATABASE_URL needed — SQLite is used automatically
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1
OPEN_METEO_ARCHIVE_URL=https://archive-api.open-meteo.com/v1
```

> **Note:** SQLite database (`philiready.db`) is created automatically in the project root. No external database server is required.

---

## Must-Have #1 — Seed Data (`seed_data.py`)

This must be run first. It populates the SQLite database with city data from `data/psgc_cities.csv` and generates synthetic training data. Everything else depends on this.

### Database Models

```python
# app/db/models.py
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship

class Base(DeclarativeBase):
    pass

class City(Base):
    __tablename__ = "cities"

    pcode       = Column(String, primary_key=True)  # e.g. "072217000"
    name        = Column(String, nullable=False)
    province    = Column(String, default="Cebu")
    latitude    = Column(Float, nullable=False)
    longitude   = Column(Float, nullable=False)
    population  = Column(Integer, nullable=False)
    households  = Column(Integer, nullable=False)
    poverty_pct = Column(Float, default=0.20)       # 0.0–1.0
    is_coastal  = Column(Integer, default=0)        # 0 or 1
    flood_zone  = Column(String, default="low")     # low / medium / high
    eq_zone     = Column(String, default="low")     # low / medium / high
    risk_score  = Column(Float, default=0.3)        # computed composite

    distributions = relationship("ReliefDistribution", back_populates="city")


class ReliefDistribution(Base):
    __tablename__ = "relief_distributions"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    city_pcode   = Column(String, ForeignKey("cities.pcode"), nullable=False)
    event_date   = Column(DateTime, nullable=False)
    hazard_type  = Column(String, nullable=False)   # typhoon / flood / earthquake
    severity     = Column(Integer, nullable=False)  # 1–4
    rice_kg      = Column(Float, nullable=False)
    water_liters = Column(Float, nullable=False)
    meds_units   = Column(Float, nullable=False)
    kits_units   = Column(Float, nullable=False)

    city = relationship("City", back_populates="distributions")
```

### Database Session

```python
# app/db/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")

# psycopg2 requires postgresql:// not postgres:// — Railway sometimes
# generates the latter, so normalise it here
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # drops stale connections before use
    pool_size=5,          # sensible default for Railway free tier
    max_overflow=10,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### Seed Data Script

```python
# app/db/seed_data.py
"""
Run once:  python -m app.db.seed_data
Populates cities table and generates synthetic relief distribution history.
Requires PostgreSQL to be running and DATABASE_URL set in .env
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.db.database import engine, SessionLocal
from app.db.models import Base, City, ReliefDistribution

# ── 1. Cebu cities/municipalities data ────────────────────────────────────
#   Source: PSA 2020 Census + PSGC 2023
#   Coordinates: approximate centroids for each city/municipality
CITIES_DATA = [
    # pcode           name                     lat       lon      pop     hh    pov   coast flood  eq    risk
    ("072217000", "Cebu City",              10.317,  123.891, 964169, 214264, 0.14, 1, "high",   "medium", 0.88),
    ("1380600000", "Mandaue City",           10.323,  123.944, 362654,  80590, 0.12, 1, "medium", "medium", 0.75),
    ("1380600000", "Lapu-Lapu City",         10.311,  123.980, 497785, 110619, 0.15, 1, "high",   "low",    0.82),
    ("1380600000", "Talisay City",           10.244,  123.848, 254484,  56552, 0.19, 1, "medium", "medium", 0.71),
    ("1380600000", "Carcar City",            10.107,  123.641, 141055,  31346, 0.22, 0, "low",    "low",    0.45),
    ("1380600000", "Danao City",             10.527,  124.027, 127904,  28423, 0.24, 1, "medium", "medium", 0.63),
    ("1380600000", "Naga City",              10.212,  123.757, 111226,  24717, 0.21, 0, "low",    "medium", 0.48),
    ("1380600000", "Bogo City",              11.051,  124.000,  82813,  18403, 0.28, 1, "high",   "high",   0.91),
    ("1380600000", "Consolacion",            10.373,  123.961,  81309,  18069, 0.18, 1, "medium", "low",    0.62),
    ("072206000", "Cordova",                10.256,  124.011,  65715,  14603, 0.16, 1, "high",   "low",    0.73),
    ("072208000", "Liloan",                 10.398,  124.012,  97938,  21764, 0.19, 1, "medium", "low",    0.58),
    ("072210000", "Minglanilla",            10.243,  123.796, 129298,  28733, 0.17, 0, "low",    "medium", 0.44),
    ("072211000", "San Fernando",           10.163,  123.715,  81040,  18009, 0.23, 0, "low",    "low",    0.38),
    ("1380600000", "Talisay",                10.244,  123.848, 254484,  56552, 0.19, 1, "medium", "medium", 0.68),
    ("1380600000", "Alcoy",                   9.720,  123.498,  13902,   3090, 0.31, 1, "low",    "low",    0.35),
    ("1380600000", "Alegria",                 9.765,  123.400,  14896,   3310, 0.30, 1, "low",    "low",    0.33),
    ("1380600000", "Alcantara",               9.979,  123.400,   9963,   2214, 0.29, 0, "low",    "low",    0.28),
    ("1380600000", "Aloguinsan",             10.100,  123.533,  17640,   3920, 0.32, 1, "low",    "low",    0.36),
    ("1380600000", "Argao",                   9.880,  123.608,  54440,  12098, 0.27, 1, "low",    "low",    0.42),
    ("1380600000", "Asturias",               10.622,  123.713,  28017,   6226, 0.33, 1, "medium", "medium", 0.55),
    # Add remaining ~34 municipalities following same pattern
    # Full list: https://psa.gov.ph/classification/psgc — filter Region VII, Cebu province
]

# ── 2. Typhoon demand multiplier curve (7 days) ────────────────────────────
TYPHOON_CURVE = {
    1: [0.1, 0.5, 0.8, 0.6, 0.4, 0.2, 0.1],
    2: [0.2, 1.0, 1.6, 1.4, 1.0, 0.7, 0.4],
    3: [0.4, 1.6, 2.5, 2.2, 1.7, 1.1, 0.6],
    4: [0.8, 2.8, 4.0, 3.5, 2.6, 1.6, 0.9],
}

EARTHQUAKE_CURVE = {
    1: [1.2, 0.9, 0.6, 0.3, 0.2, 0.1, 0.1],  # front-loaded, quick taper
    2: [1.8, 1.4, 1.0, 0.6, 0.3, 0.2, 0.1],
    3: [3.0, 2.4, 1.8, 1.2, 0.7, 0.4, 0.2],
    4: [4.5, 3.6, 2.8, 1.9, 1.1, 0.6, 0.3],
}

FLOOD_CURVE = {
    1: [0.3, 0.8, 1.0, 0.8, 0.5, 0.3, 0.1],
    2: [0.5, 1.3, 1.8, 1.5, 1.0, 0.6, 0.3],
    3: [0.8, 2.0, 2.8, 2.4, 1.6, 0.9, 0.4],
    4: [1.2, 3.0, 4.2, 3.6, 2.4, 1.4, 0.6],
}

HAZARD_CURVES = {
    "typhoon":    TYPHOON_CURVE,
    "flood":      FLOOD_CURVE,
    "earthquake": EARTHQUAKE_CURVE,
}

# SPHERE standard minimums (per family per day)
SPHERE = {
    "rice_kg":      1.5,   # kg/family/day
    "water_liters": 15.0,  # L/family/day (15L minimum per SPHERE)
    "meds_units":   0.08,  # kit per family (approx 1 kit per 12 families/day)
    "kits_units":   0.07,
}

# Known historical typhoon events to anchor synthetic data
HISTORICAL_EVENTS = [
    ("2021-12-16", "typhoon",    4, "Typhoon Odette (Rai)"),
    ("2022-09-25", "typhoon",    3, "Typhoon Karding (Noru)"),
    ("2023-07-25", "typhoon",    2, "Typhoon Egay (Doksuri)"),
    ("2023-10-14", "typhoon",    3, "Typhoon Jenny (Koinu)"),
    ("2024-11-01", "typhoon",    4, "Typhoon Pepito (Man-yi)"),
    ("2022-04-10", "earthquake", 3, "Abra Earthquake spillover"),
    ("2023-06-15", "flood",      2, "Habagat flooding"),
    ("2024-07-20", "flood",      3, "Southwest monsoon flooding"),
    ("2025-01-22", "earthquake", 3, "Bogo City M6.9"),
]


def generate_distributions(city: tuple, event_date_str: str,
                             hazard_type: str, severity: int) -> list:
    """Generate 7 days of synthetic distribution records for one city + event."""
    (pcode, name, lat, lon, pop, hh, pov, coast,
     flood_zone, eq_zone, risk) = city

    curve = HAZARD_CURVES.get(hazard_type, TYPHOON_CURVE)[severity]

    # Displacement rate — higher for coastal, higher severity
    base_displacement = 0.15 + (severity * 0.10) + (coast * 0.10)
    # Vulnerability modifier — poverty amplifies demand
    vuln_modifier = 1.0 + (pov * 1.2)

    displaced_hh = int(hh * min(base_displacement * vuln_modifier, 0.85))

    records = []
    event_date = datetime.strptime(event_date_str, "%Y-%m-%d")

    for day_offset, multiplier in enumerate(curve):
        if multiplier < 0.05:
            continue
        dist_date = event_date + timedelta(days=day_offset)

        # Add ±15% noise for realism
        noise = lambda: np.random.uniform(0.85, 1.15)

        records.append(ReliefDistribution(
            city_pcode=pcode,
            event_date=dist_date,
            hazard_type=hazard_type,
            severity=severity,
            rice_kg=      round(displaced_hh * SPHERE["rice_kg"]      * multiplier * noise(), 1),
            water_liters= round(displaced_hh * SPHERE["water_liters"] * multiplier * noise(), 1),
            meds_units=   round(displaced_hh * SPHERE["meds_units"]   * multiplier * noise(), 1),
            kits_units=   round(displaced_hh * SPHERE["kits_units"]   * multiplier * noise(), 1),
        ))

    return records


def run():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    print("Seeding cities...")
    for city_row in CITIES_DATA:
        (pcode, name, lat, lon, pop, hh, pov, coast,
         flood_zone, eq_zone, risk) = city_row

        existing = db.get(City, pcode)
        if existing:
            continue

        db.add(City(
            pcode=pcode, name=name,
            latitude=lat, longitude=lon,
            population=pop, households=hh,
            poverty_pct=pov, is_coastal=coast,
            flood_zone=flood_zone, eq_zone=eq_zone,
            risk_score=risk,
        ))

    db.commit()

    print("Generating synthetic distributions...")
    for event_date, hazard_type, severity, label in HISTORICAL_EVENTS:
        print(f"  → {label} ({event_date})")
        for city_row in CITIES_DATA:
            records = generate_distributions(city_row, event_date,
                                             hazard_type, severity)
            db.add_all(records)
        db.commit()

    total = db.query(ReliefDistribution).count()
    print(f"\n✅ Seed complete. {len(CITIES_DATA)} cities, {total} distribution records.")
    db.close()


if __name__ == "__main__":
    run()
```

---

## Must-Have #2 — Prophet Forecast Service

### Overview

One Prophet model is trained **per city × per relief item**. Models are serialized to `.pkl` files and loaded at startup. At inference time, the service loads the relevant model, injects a hazard event regressor if a simulation is active, and returns a 7-day forecast.

### Training Script (run once after seeding)

```python
# app/models/train_models.py
"""
Run once:  python -m app.models.train_models
Trains Prophet models for each city × item and saves to app/models/prophet/
"""
import os
import joblib
import pandas as pd
from prophet import Prophet
from app.db.database import SessionLocal
from app.db.models import City, ReliefDistribution

ITEMS = ["rice_kg", "water_liters", "meds_units", "kits_units"]
OUTPUT_DIR = "app/models/prophet"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def train_for_city_item(city_pcode: str, item: str, db) -> Prophet:
    rows = (
        db.query(ReliefDistribution)
        .filter(ReliefDistribution.city_pcode == city_pcode)
        .order_by(ReliefDistribution.event_date)
        .all()
    )

    if len(rows) < 10:
        return None  # Not enough data — use fallback formula

    df = pd.DataFrame([{
        "ds":            r.event_date,
        "y":             getattr(r, item),
        "hazard_type":   r.hazard_type,
        "severity":      r.severity,
    } for r in rows])

    df["ds"] = pd.to_datetime(df["ds"])

    # Add hazard regressor — 1 when disaster is active, 0 otherwise
    df["hazard_active"] = 1

    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=False,
        daily_seasonality=False,
        interval_width=0.80,          # 80% confidence interval
        changepoint_prior_scale=0.05, # reduce overfitting on sparse data
    )
    model.add_regressor("hazard_active")
    model.add_regressor("severity")

    model.fit(df)
    return model


def run():
    db = SessionLocal()
    cities = db.query(City).all()

    for city in cities:
        for item in ITEMS:
            print(f"Training {city.pcode} ({city.name}) — {item}...")
            model = train_for_city_item(city.pcode, item, db)

            if model is None:
                print(f"  ⚠ Skipped (insufficient data) — will use fallback")
                continue

            path = f"{OUTPUT_DIR}/{city.pcode}_{item}.pkl"
            joblib.dump(model, path)
            print(f"  ✅ Saved to {path}")

    db.close()
    print("\nTraining complete.")


if __name__ == "__main__":
    run()
```

### Forecast Service

```python
# app/services/forecast_service.py
import os
import joblib
import numpy as np
import pandas as pd
from datetime import date, timedelta
from functools import lru_cache
from app.db.database import SessionLocal
from app.db.models import City

MODEL_DIR = "app/models/prophet"
ITEMS = ["rice_kg", "water_liters", "meds_units", "kits_units"]

# Demand curves for fallback formula (when model not available)
DEMAND_CURVE = {
    "typhoon":    [0.2, 1.0, 1.6, 1.4, 1.0, 0.7, 0.4],
    "flood":      [0.3, 0.8, 1.0, 0.8, 0.5, 0.3, 0.1],
    "earthquake": [1.2, 0.9, 0.6, 0.3, 0.2, 0.1, 0.1],
    "volcanic":   [0.1, 0.3, 0.6, 0.8, 0.7, 0.5, 0.3],
}

SEVERITY_MULTIPLIER = {1: 0.5, 2: 1.0, 3: 1.6, 4: 2.5}

# SPHERE daily demand per household
SPHERE = {
    "rice_kg": 1.5, "water_liters": 15.0,
    "meds_units": 0.08, "kits_units": 0.07,
}


@lru_cache(maxsize=256)
def load_model(pcode: str, item: str):
    """Load model from disk. Cached in memory after first load."""
    path = f"{MODEL_DIR}/{pcode}_{item}.pkl"
    if not os.path.exists(path):
        return None
    return joblib.load(path)


def forecast_city(
    pcode: str,
    hazard_type: str = None,
    severity: int = None,
    horizon: int = 7,
) -> list[dict]:
    """
    Returns a list of 7 forecast dicts:
    { day, rice, water, meds, kits, lower, upper }
    """
    db = SessionLocal()
    city = db.get(City, pcode)
    db.close()

    if not city:
        raise ValueError(f"City {pcode} not found")

    results = []
    today = date.today()

    # Try Prophet model first; fall back to formula if not available
    prophet_results = {}
    for item in ITEMS:
        model = load_model(pcode, item)
        if model is None:
            continue

        future = model.make_future_dataframe(periods=horizon, freq="D",
                                              include_history=False)
        future["hazard_active"] = 1 if hazard_type else 0
        future["severity"] = severity if severity else 0

        forecast_df = model.predict(future)
        prophet_results[item] = forecast_df[["ds", "yhat",
                                              "yhat_lower", "yhat_upper"]].tail(horizon)

    # Build response
    curve = DEMAND_CURVE.get(hazard_type or "typhoon", DEMAND_CURVE["typhoon"])
    sev_mult = SEVERITY_MULTIPLIER.get(severity or 1, 1.0)
    displaced_hh = int(city.households * 0.35 * sev_mult)

    for day_offset in range(horizon):
        forecast_date = today + timedelta(days=day_offset)
        day_label = forecast_date.strftime("%b %-d")
        day_row = {"day": day_label}

        for item in ITEMS:
            short = item.replace("_kg", "").replace("_liters", "").replace("_units", "")
            item_key = {
                "rice_kg": "rice", "water_liters": "water",
                "meds_units": "meds", "kits_units": "kits",
            }[item]

            if item in prophet_results:
                row = prophet_results[item].iloc[day_offset]
                val   = max(0, round(float(row["yhat"]), 1))
                lower = max(0, round(float(row["yhat_lower"]), 1))
                upper = max(0, round(float(row["yhat_upper"]), 1))
            else:
                # Formula fallback
                multiplier = curve[day_offset] * sev_mult
                base_demand = displaced_hh * SPHERE[item]
                val   = round(base_demand * multiplier, 1)
                lower = round(val * 0.80, 1)
                upper = round(val * 1.20, 1)

            if day_offset == 0:
                day_row[item_key]           = val
                day_row[f"{item_key}_lower"] = lower
                day_row[f"{item_key}_upper"] = upper
            else:
                day_row[item_key]           = val
                day_row[f"{item_key}_lower"] = lower
                day_row[f"{item_key}_upper"] = upper

        results.append(day_row)

    return results
```

### Demand Score Service

```python
# app/services/demand_service.py
"""
Computes a normalized 0.0–1.0 demand score per city.
Used to color the choropleth map.
"""
from app.db.database import SessionLocal
from app.db.models import City
from app.services.forecast_service import forecast_city

SEVERITY_MULTIPLIER = {1: 1.1, 2: 1.3, 3: 1.6, 4: 2.0}


def compute_demand_scores(
    hazard_type: str = None,
    severity: int = None,
) -> dict[str, float]:
    """
    Returns { pcode: score } for all cities.
    Score is normalized peak 7-day rice demand relative to max across all cities.
    """
    db = SessionLocal()
    cities = db.query(City).all()
    db.close()

    raw_scores = {}

    for city in cities:
        if hazard_type and severity:
            # Use forecast peak
            forecast = forecast_city(city.pcode, hazard_type, severity)
            peak_rice = max(d["rice"] for d in forecast)
            # Normalize by city's household count to get per-hh intensity
            raw_scores[city.pcode] = peak_rice / max(city.households, 1)
        else:
            # Baseline: use stored risk_score
            raw_scores[city.pcode] = city.risk_score

    if not raw_scores:
        return {}

    max_val = max(raw_scores.values()) or 1.0

    return {
        pcode: round(min(score / max_val, 1.0), 4)
        for pcode, score in raw_scores.items()
    }
```

---

## Must-Have #3 — API Routers

### FastAPI App Entry Point

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import map, forecast, simulate, cities

app = FastAPI(
    title="PhiliReady API",
    description="Micro-Demand Forecaster for Relief Goods",
    version="0.1.0",
)

# ── CORS ────────────────────────────────────────────────────────────────────
# Allow your Vercel frontend domain. Add localhost for local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://philiready.vercel.app",   # ← update with your actual domain
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ─────────────────────────────────────────────────────────────────
app.include_router(map.router,      prefix="/api")
app.include_router(forecast.router, prefix="/api")
app.include_router(simulate.router, prefix="/api")
app.include_router(cities.router,   prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok", "service": "philiready-api"}
```

### Pydantic Schemas

```python
# app/schemas/responses.py
from pydantic import BaseModel

class ForecastPoint(BaseModel):
    day:         str
    rice:        float
    water:       float
    meds:        float
    kits:        float
    rice_lower:  float
    rice_upper:  float

class CityDetailResponse(BaseModel):
    pcode:      str
    name:       str
    population: int
    risk_score: float
    zone_type:  str
    demand: dict[str, float]

class SimulationRequest(BaseModel):
    hazard_type: str   # typhoon | flood | earthquake | volcanic
    severity:    int   # 1–4

class DemandHeatmapResponse(BaseModel):
    scores: dict[str, float]  # { pcode: 0.0–1.0 }
```

### Map Router

```python
# app/routers/map.py
from fastapi import APIRouter, Query
from app.services.demand_service import compute_demand_scores

router = APIRouter()

@router.get("/map/demand-heat")
def get_demand_heatmap(
    hazard_type: str = Query(None, description="typhoon|flood|earthquake|volcanic"),
    severity:    int = Query(None, ge=1, le=4),
):
    """
    Returns normalized demand scores per city/municipality.
    Frontend maps these to choropleth colors.

    Response shape: { "072217000": 0.92, "1380600000": 0.71, ... }
    """
    scores = compute_demand_scores(hazard_type, severity)
    return scores
```

### Forecast Router

```python
# app/routers/forecast.py
from fastapi import APIRouter, Path, Query, HTTPException
from app.services.forecast_service import forecast_city

router = APIRouter()

@router.get("/forecast/{pcode}")
def get_forecast(
    pcode:       str = Path(..., description="City PSGC code e.g. 072217000"),
    hazard_type: str = Query(None),
    severity:    int = Query(None, ge=1, le=4),
):
    """
    Returns 7-day demand forecast for a single city.

    Response: list of { day, rice, water, meds, kits, *_lower, *_upper }
    """
    try:
        return forecast_city(pcode, hazard_type, severity)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
```

### Simulate Router

```python
# app/routers/simulate.py
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.demand_service import compute_demand_scores

router = APIRouter()

class SimulateRequest(BaseModel):
    hazard_type: str
    severity:    int

@router.post("/simulate")
def run_simulation(body: SimulateRequest):
    """
    Recalculates demand scores under a simulated disaster scenario.
    Returns the same shape as /api/map/demand-heat.

    This is a stateless endpoint — no event is persisted.
    The frontend stores simulation state in URL search params.
    """
    scores = compute_demand_scores(body.hazard_type, body.severity)
    return scores
```

### Cities Router

```python
# app/routers/cities.py
from fastapi import APIRouter, Path, HTTPException
from app.db.database import SessionLocal
from app.db.models import City
from app.services.forecast_service import forecast_city

router = APIRouter()

@router.get("/cities/{pcode}")
def get_city_detail(
    pcode: str = Path(..., description="PSGC code e.g. 072217000"),
):
    """
    Returns demographic + risk data for a single city.
    Also includes pre-computed peak demand for the detail panel bars.
    """
    db = SessionLocal()
    city = db.get(City, pcode)
    db.close()

    if not city:
        raise HTTPException(status_code=404, detail=f"City {pcode} not found")

    # Compute baseline peak demand (no simulation)
    forecast = forecast_city(pcode)
    peak = {
        "rice":  max(d["rice"]  for d in forecast),
        "water": max(d["water"] for d in forecast),
        "meds":  max(d["meds"]  for d in forecast),
        "kits":  max(d["kits"]  for d in forecast),
    }

    zone_type = "coastal" if city.is_coastal else "inland"

    return {
        "pcode":      city.pcode,
        "name":       city.name,
        "population": city.population,
        "risk_score": city.risk_score,
        "zone_type":  zone_type,
        "demand":     peak,
    }
```

---

## Must-Have #4 — Open-Meteo Weather Service

Used by the forecast service as an additional context layer. Also exposed to the frontend for the weather widget.

```python
# app/services/weather_service.py
import httpx
from functools import lru_cache
from datetime import date, timedelta

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

@lru_cache(maxsize=8)
def get_cebu_forecast_cached(today: date) -> dict:
    """Cached by date — refreshes once per day naturally."""
    return _fetch_forecast()

def _fetch_forecast() -> dict:
    params = {
        "latitude":   10.317,
        "longitude":  123.891,
        "daily": ",".join([
            "precipitation_sum",
            "windspeed_10m_max",
            "temperature_2m_max",
            "temperature_2m_min",
        ]),
        "timezone":   "Asia/Manila",
        "forecast_days": 7,
    }
    response = httpx.get(FORECAST_URL, params=params, timeout=10)
    response.raise_for_status()
    return response.json()

def get_weekly_forecast() -> list[dict]:
    """Returns structured 7-day forecast for the frontend weather widget."""
    raw = get_cebu_forecast_cached(date.today())
    daily = raw.get("daily", {})

    days = daily.get("time", [])
    precip = daily.get("precipitation_sum", [])
    wind = daily.get("windspeed_10m_max", [])

    return [
        {
            "date":       d,
            "precip_mm":  round(p or 0, 1),
            "wind_kmh":   round(w or 0, 1),
            "alert":      (p or 0) > 30,   # PAGASA Orange threshold
        }
        for d, p, w in zip(days, precip, wind)
    ]
```

Add a route to expose it:

```python
# Add to app/main.py or create app/routers/weather.py
@app.get("/api/weather")
def get_weather():
    from app.services.weather_service import get_weekly_forecast
    return get_weekly_forecast()
```

---

## Deployment — Railway

### 1. Add PostgreSQL Plugin on Railway

In the Railway dashboard after creating your project:

1. Click **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Railway provisions a Postgres instance and automatically injects `DATABASE_URL` into your service's environment — no manual copy-pasting needed
3. Confirm the variable exists under your service's **Variables** tab before deploying

### 2. Procfile

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### 3. runtime.txt

```
python-3.11.9
```

### 4. Add a Release Command for Seeding

Railway supports a `RELEASE_COMMAND` environment variable that runs once after each deploy, before traffic is served. Use this to run the seed script automatically on first deploy.

In Railway dashboard → your service → **Variables**, add:

```
RELEASE_COMMAND=python -m app.db.seed_data
```

The seed script is safe to re-run — it checks for existing records before inserting, so repeated deploys won't duplicate data:

```python
# The check already in seed_data.py — no changes needed
existing = db.get(City, pcode)
if existing:
    continue
```

### 5. Commit Only the Model `.pkl` Files

Unlike the database, Prophet models are trained artifacts that don't change at runtime — commit them to the repo so they're available after deploy:

```bash
# Train models locally first
python -m app.models.train_models

# Commit only the .pkl files, not the database
git add app/models/prophet/*.pkl
git commit -m "Add trained Prophet models"

# Make sure philiready.db is gitignored
echo "philiready.db" >> .gitignore
git add .gitignore && git commit -m "Ignore local SQLite artifact"
```

> **Why not train on Railway?** Prophet training for 80 models takes 3–5 minutes and uses significant CPU. Railway free tier has CPU limits and the build/release step has a timeout. Training locally and committing the `.pkl` files is the reliable path for a hackathon.

### 6. Deploy

```bash
# Install Railway CLI
npm install -g @railway/cli

railway login
railway init    # link to your Railway project
railway up      # push and deploy
```

Railway detects `Procfile` and `requirements.txt` automatically. After deploy completes, the release command runs `seed_data.py` against the live Postgres instance.

### 7. Get Your Backend URL

Railway assigns a public URL under **Settings → Networking → Public Domain**:

```
https://philiready-backend-production.up.railway.app
```

Paste this into your Vercel frontend as `VITE_API_BASE_URL`.

---

## Local Development Order

### Prerequisites — Local PostgreSQL

You need a local Postgres instance running before the first setup. The fastest options:

```bash
# Option A — Docker (recommended, no local install)
docker run --name philiready-db \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=philiready \
  -p 5432:5432 -d postgres:16

# Option B — Homebrew (macOS)
brew install postgresql@16
brew services start postgresql@16
createdb philiready

# Option C — Windows
# Download installer from https://www.postgresql.org/download/windows/
# Create a database named "philiready" via pgAdmin after install
```

### First-Time Setup Commands

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up .env with your local DATABASE_URL
echo "DATABASE_URL=postgresql://postgres:password@localhost:5432/philiready" > .env

# 3. Run Alembic migrations to create tables
#    (or use Base.metadata.create_all for the hackathon — simpler)
python -c "from app.db.database import engine; from app.db.models import Base; Base.metadata.create_all(engine)"

# 4. Seed the database
python -m app.db.seed_data

# 5. Train Prophet models (~3–5 min for 20 cities × 4 items)
python -m app.models.train_models

# 6. Start the API server
uvicorn app.main:app --reload --port 8000

# 7. Check Swagger docs at:
#    http://localhost:8000/docs
```

---

## API Reference Summary

| Method | Endpoint | Description | Returns |
|--------|----------|-------------|---------|
| `GET`  | `/health` | Health check | `{ status: "ok" }` |
| `GET`  | `/api/map/demand-heat` | Choropleth scores for all cities | `{ pcode: score }` |
| `GET`  | `/api/forecast/{pcode}` | 7-day demand forecast for one city | `ForecastPoint[]` |
| `POST` | `/api/simulate` | Recompute scores under disaster scenario | `{ pcode: score }` |
| `GET`  | `/api/cities/{pcode}` | City demographic + demand detail | `CityDetailResponse` |
| `GET`  | `/api/weather` | 7-day Open-Meteo weather for Cebu City | `WeatherDay[]` |

All endpoints return JSON. All `pcode` values follow the `PH072XXXXXXX` format matching `ADM3_PCODE` in the GeoJSON.

---

## Testing Checklist Before Demo

- [ ] Local PostgreSQL is running and `DATABASE_URL` in `.env` connects successfully
- [ ] `python -m app.db.seed_data` completes with no errors — check city count and record count printed
- [ ] `python -m app.models.train_models` produces `.pkl` files in `app/models/prophet/`
- [ ] `GET /health` returns `{ "status": "ok" }`
- [ ] `GET /api/map/demand-heat` returns ~20 PSGC keys with scores between 0 and 1
- [ ] `GET /api/forecast/072217000` returns 7 forecast items with rice/water/meds/kits values
- [ ] `POST /api/simulate` with `{ "hazard_type": "typhoon", "severity": 3 }` returns higher scores than baseline
- [ ] `GET /api/cities/072217000` returns Cebu City with correct population
- [ ] CORS headers present in response (check with `curl -I` or browser Network tab from frontend domain)
- [ ] Railway Postgres plugin is provisioned and `DATABASE_URL` is visible under service Variables
- [ ] After `railway up`, release command runs `seed_data.py` successfully (check Railway deploy logs)
- [ ] Railway deployment URL responds to `/health` from the internet
- [ ] `philiready.db` is listed in `.gitignore` and not present in the repo
