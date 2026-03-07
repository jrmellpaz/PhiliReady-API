# PhiliReady — Agent Reference

> This file is the canonical project reference for the Antigravity agent.
> Read this before planning or executing any task in this repository.
> A copy of this file lives in the root of **both** the frontend and backend repositories.
> All sections are relevant regardless of which repo you have open.

---

## What This Project Is

**PhiliReady** is a city/municipality-level Micro-Demand Forecaster for Relief Goods, covering **all cities and municipalities in the Philippines** (~1,642 LGUs) and designed to scale across ASEAN. It predicts how many relief items (rice, water, medicine kits, hygiene kits) will be needed per city or municipality over a 7-day horizon, before a disaster peaks. It is being developed as a prototype for an ASEAN humanitarian hackathon.

The primary users are DRRMO (Disaster Risk Reduction and Management Office) officers and LGU (Local Government Unit) coordinators in the Philippines. The system shifts relief distribution from **reactive scrambling** to **predictive pre-positioning**.

---

## Repository Structure

PhiliReady is split across **two separate repositories**. Each has its own `ANTIGRAVITY.md` at its root (this file).

| Repo | Stack | Deployed on |
|---|---|---|
| `philiready-frontend` | TanStack Start · React · TypeScript | Vercel |
| `philiready-backend` | FastAPI · Python 3.11 · PostgreSQL | Railway |

The repos are independent — no shared packages, no shared config files. They communicate exclusively over HTTP via the API contracts defined in this file. The `PSGC` code (e.g. `0722170000`) is the only shared identifier between them.

### Frontend repo root

```
philiready-frontend/
├── ANTIGRAVITY.md
├── app/
│   ├── routes/
│   ├── components/
│   ├── lib/
│   └── styles/
├── public/
│   └── geo/
│       └── ph-municities.json     ← city/municipality boundaries, nationwide
├── .env
├── package.json
└── vite.config.ts
```

### Backend repo root

```
philiready-backend/
├── ANTIGRAVITY.md
├── app/
│   ├── main.py
│   ├── routers/
│   ├── services/
│   ├── models/
│   │   └── prophet/               ← (optional) serialized .pkl files per city × item
│   ├── db/
│   └── schemas/
├── data/
│   └── psgc_cities.csv            ← PSGC city/municipality reference data
├── .env
├── requirements.txt
└── Procfile
```

---

## Frontend

### Stack

| Tool | Version | Role |
|---|---|---|
| `@tanstack/react-start` | v1 RC | Full-stack framework, SSR, file-based routing |
| `@tanstack/react-query` | v5 | Server state, API polling |
| `@tanstack/react-router` | v1 | Type-safe routing (bundled with Start) |
| `react-leaflet` | v4 | Map rendering |
| `leaflet` | v1.9.x | Core map library |
| `recharts` | v2.x | Forecast charts |
| `tailwindcss` | v3.x | Styling |
| `zod` | v3 | Schema validation (shared with backend types) |

### Key Conventions

- **Leaflet must never run on the server.** Always import map components through `app/components/map/MapWrapper.tsx`, which is a `lazy()`-wrapped SSR-safe shell. Never import `CebuMap.tsx` directly into a route.
- **Simulation state lives in URL search params**, not React state or a global store. Use TanStack Router's `useSearch` and `useNavigate` to read and write `sim`, `hazard`, and `severity`.
- **All API calls go through `app/lib/api.ts`** — never call `fetch` directly inside a component. All queries are wrapped in hooks in `app/lib/queries.ts`.
- **`VITE_API_BASE_URL`** is the single environment variable for the backend URL. Use `import.meta.env.VITE_API_BASE_URL` — never hardcode localhost.
- **Zod schemas in `app/lib/types.ts`** are the source of truth for all request/response shapes. If the backend response shape changes, update here first.

### Route Map

| Route | File | Purpose |
|---|---|---|
| `/` | `app/routes/index.tsx` | Main dashboard — map + detail panel |
| `/simulate` | `app/routes/simulate.tsx` | Disaster event simulator |

### Critical Files

```
app/
├── routes/
│   ├── __root.tsx          # Global CSS imports — leaflet.css is imported here
│   ├── index.tsx           # Dashboard, reads sim/hazard/severity from search params
│   └── simulate.tsx        # Simulator page, writes to search params on activate
├── components/
│   ├── map/
│   │   ├── MapWrapper.tsx  # SSR-safe lazy wrapper — ALWAYS use this, not CebuMap
│   │   ├── CebuMap.tsx     # Client-only Leaflet component
│   │   └── DetailPanel.tsx # Side panel shown on city click
│   └── forecast/
│       └── ForecastChart.tsx
├── lib/
│   ├── api.ts              # All fetch functions
│   ├── queries.ts          # TanStack Query hooks
│   ├── types.ts            # Zod schemas — source of truth for API shapes
│   └── leaflet-fix.ts      # Marker icon patch — imported once in CebuMap.tsx
└── styles/
    └── globals.css         # Tailwind + leaflet/dist/leaflet.css import
```

### GeoJSON Map Data

- File: `public/geo/ph-municities.json` — relative to the `philiready-frontend` repo root
- Source: `faeldon/philippines-json-maps` — PSGC 2023, nationwide city/municipality boundaries
- Each feature has `adm3_psgc` (e.g. `0722170000`) and `ADM3_EN` (e.g. `"Cebu City"`)
- **`adm3_psgc` is the join key** between map features and all API responses
- The file is served as a static asset — never fetched from GitHub at runtime

---

## Backend

### Stack

| Tool | Version | Role |
|---|---|---|
| `fastapi` | 0.115.x | REST API framework |
| `uvicorn` | latest | ASGI server |
| `pandas` | 2.2.x | Data manipulation |
| `sqlalchemy` | 2.0.x | ORM |
| `httpx` | 0.27.x | Open-Meteo API client |
| `prophet` | 1.1.6 | (Optional) Time-series forecasting — see Forecast Model section |
| `joblib` | latest | (Optional) Prophet model serialization |

### Key Conventions

- **Database:** SQLite (`philiready.db` created automatically). No external database server required.
- **Run order on first setup:** `seed_data.py` → `uvicorn`. Nothing works without the database being seeded first.
- **Forecast engine:** The primary forecasting engine uses a **SPHERE-standard formula** with demand curves. Prophet models are an optional enhancement — see Forecast Model section.
- **City data:** Loaded from `data/psgc_cities.csv` during seeding. To update city data, replace this CSV.
- All routers are registered in `main.py` under the `/api` prefix.
- **The simulate endpoint is stateless** — it recomputes scores without persisting anything. Simulation state is owned by the frontend URL.

### Critical Files

```
app/
├── main.py                     # FastAPI app, CORS config, router registration
├── routers/
│   ├── map.py                  # GET /api/map/demand-heat
│   ├── forecast.py             # GET /api/forecast/{pcode}
│   ├── simulate.py             # POST /api/simulate
│   ├── cities.py               # GET /api/cities/{pcode}
│   └── weather.py              # GET /api/weather
├── services/
│   ├── forecast_service.py     # Prophet load + predict, fallback formula
│   ├── demand_service.py       # Normalised 0–1 demand score per city
│   └── weather_service.py      # Open-Meteo API client, lru_cache by date
├── models/
│   └── prophet/                # (optional) {pcode}_{item}.pkl — one file per city × item
├── db/
│   ├── database.py             # SQLAlchemy engine + session (SQLite)
│   ├── models.py               # City and ReliefDistribution ORM models
│   └── seed_data.py            # Run once — populates cities from CSV + synthetic history
└── schemas/
    └── responses.py            # Pydantic response models
```

### Database

- **Engine:** SQLite (file: `philiready.db` in project root, created automatically)
- **Two tables:** `cities` and `relief_distributions`
- `cities.pcode` is the primary key — format `0722170000` (matches GeoJSON `adm3_psgc`)
- `cities` table holds ~1,642 Philippine cities/municipalities, loaded from `data/psgc_cities.csv`
- `relief_distributions` holds synthetic historical distribution logs per city per disaster event
- Uses `connect_args={"check_same_thread": False}` for SQLite thread safety with FastAPI

### Forecast Model

- **Primary engine:** SPHERE-standard formula with hazard-specific demand curves
  - Formula: `displaced_households × SPHERE_rate × demand_curve_multiplier × severity_factor`
  - Works for all ~1,642 cities with no training required
  - Confidence interval: ±20% of predicted value
- **Optional enhancement:** Meta Prophet (`prophet==1.1.6`)
  - One model per **city × relief item** (e.g. `0722170000_rice_kg.pkl`)
  - When a `.pkl` model exists for a city, it is used instead of the formula
  - Provides statistically meaningful 80% confidence intervals
  - Training script: `python -m app.models.train_models`
  - Not practical for all 1,642 cities — intended for cities with real historical data

### Demand Curve Reference

Multiplier arrays (7 days) used in the fallback formula and seed data generation:

```python
# Typhoon
{1: [0.1,0.5,0.8,0.6,0.4,0.2,0.1], 2: [0.2,1.0,1.6,1.4,1.0,0.7,0.4],
 3: [0.4,1.6,2.5,2.2,1.7,1.1,0.6], 4: [0.8,2.8,4.0,3.5,2.6,1.6,0.9]}

# Earthquake — front-loaded, quick taper
{1: [1.2,0.9,0.6,0.3,0.2,0.1,0.1], 2: [1.8,1.4,1.0,0.6,0.3,0.2,0.1],
 3: [3.0,2.4,1.8,1.2,0.7,0.4,0.2], 4: [4.5,3.6,2.8,1.9,1.1,0.6,0.3]}

# Flood
{1: [0.3,0.8,1.0,0.8,0.5,0.3,0.1], 2: [0.5,1.3,1.8,1.5,1.0,0.6,0.3],
 3: [0.8,2.0,2.8,2.4,1.6,0.9,0.4], 4: [1.2,3.0,4.2,3.6,2.4,1.4,0.6]}
```

---

## API Contracts

These are the exact request/response shapes. Frontend `types.ts` Zod schemas and backend Pydantic schemas must match these at all times.

### `GET /api/map/demand-heat`

Returns normalised demand scores (0.0–1.0) for all cities. Used to color the choropleth map.

**Query params:**
- `hazard_type` (optional): `typhoon | flood | earthquake | volcanic`
- `severity` (optional): `1 | 2 | 3 | 4`

**Response:**
```json
{
  "0722170000": 0.92,
  "0722180000": 0.75,
  "0722140000": 0.82
}
```

Keys are `adm3_psgc` values from the GeoJSON. Scores are floats between 0.0 and 1.0 inclusive. With ~1,642 cities nationwide, this response will be larger than the original Cebu-only scope.

---

### `GET /api/forecast/{pcode}`

Returns a 7-day daily forecast for a single city.

**Path param:** `pcode` — e.g. `0722170000`

**Query params:**
- `hazard_type` (optional): `typhoon | flood | earthquake | volcanic`
- `severity` (optional): `1 | 2 | 3 | 4`

**Response:**
```json
[
  {
    "day": "Mar 4",
    "rice": 4800.0,
    "water": 9600.0,
    "meds": 310.0,
    "kits": 280.0,
    "rice_lower": 4100.0,
    "rice_upper": 5500.0
  }
]
```

Array always has exactly 7 items. `lower` and `upper` are Prophet's 80% confidence interval bounds.

---

### `GET /api/cities/{pcode}`

Returns demographic data and peak demand estimates for a single city.

**Path param:** `pcode` — e.g. `0722170000`

**Response:**
```json
{
  "pcode": "0722170000",
  "name": "Cebu City",
  "population": 964169,
  "risk_score": 0.88,
  "zone_type": "coastal",
  "demand": {
    "rice": 7200.0,
    "water": 14400.0,
    "meds": 466.0,
    "kits": 419.0
  }
}
```

`demand` values represent the peak single-day estimate across the 7-day baseline forecast. `zone_type` is `"coastal"` or `"inland"`.

---

### `POST /api/simulate`

Recomputes demand scores under a disaster scenario. Stateless — nothing is persisted.

**Request body:**
```json
{
  "hazard_type": "typhoon",
  "severity": 3
}
```

**Response:** Same shape as `GET /api/map/demand-heat`
```json
{
  "0722170000": 0.97,
  "0722180000": 0.89
}
```

---

### `GET /api/weather`

Returns a 7-day weather forecast for Manila (default) from Open-Meteo. Can be extended to accept lat/lon params.

**Response:**
```json
[
  {
    "date": "2025-03-04",
    "precip_mm": 12.4,
    "wind_kmh": 28.0,
    "alert": false
  }
]
```

`alert` is `true` when `precip_mm > 30` (PAGASA Orange threshold). Array always has 7 items.

---

### `GET /health`

**Response:**
```json
{ "status": "ok", "service": "philiready-api" }
```

---

## Environment Variables

### Frontend (`.env` in `philiready-frontend` root)

```env
VITE_API_BASE_URL=https://your-backend.railway.app   # production
# or
VITE_API_BASE_URL=http://localhost:8000               # local dev
```

### Backend (`.env` in `philiready-backend` root)

```env
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1
OPEN_METEO_ARCHIVE_URL=https://archive-api.open-meteo.com/v1
```

No `DATABASE_URL` needed — SQLite database (`philiready.db`) is created automatically in the project root.

---

## Deployment

| Service | Platform | URL pattern |
|---|---|---|
| Frontend | Vercel | `https://philiready.vercel.app` |
| Backend API | Railway | `https://philiready-backend-production.up.railway.app` |
| Database | SQLite | `philiready.db` — bundled with the app, no external DB needed |

**CORS** — `app/main.py` in `philiready-backend` allows the Vercel domain and `localhost:3000` / `localhost:5173`. If the Vercel domain changes, update the `allow_origins` list in `app/main.py`.

**Prophet models** — (optional) trained locally, committed to `philiready-backend` at `app/models/prophet/*.pkl`. Do not add `*.pkl` to `.gitignore`.

**Database seeding** — runs via `python -m app.db.seed_data`. On Railway, use `RELEASE_COMMAND=python -m app.db.seed_data`. The seed script is idempotent (skips existing records).

---

## Data Sources

| Data | Source | Location in repo |
|---|---|---|
| City/municipality list | PSGC 2023 + PSA 2020 Census | `data/psgc_cities.csv` in `philiready-backend` |
| City/municipality boundaries | `faeldon/philippines-json-maps` (PSGC 2023) | `public/geo/ph-municities.json` in `philiready-frontend` |
| Live weather | Open-Meteo Forecast API | Fetched per request, cached by date in `app/services/weather_service.py` |
| Relief distribution history | Synthetic — generated by `seed_data.py` | `relief_distributions` table in SQLite |
| Disaster event anchors | NDRRMC historical records (manually referenced) | `HISTORICAL_EVENTS` list in `app/db/seed_data.py` |

**SPHERE humanitarian standards** used as demand formula baseline:
- Rice: `1.5 kg / household / day`
- Water: `15.0 L / household / day`
- Medicine kits: `0.08 units / household / day`
- Hygiene kits: `0.07 units / household / day`

---

## PSGC Code Reference (Sample Cities)

| City | PSGC (`adm3_psgc`) | Region |
|---|---|---|
| Cebu City | `0722170000` | VII |
| Manila | `1380600000` | NCR |
| Davao City | `1124020000` | XI |
| Tacloban City | `0837470000` | VIII |
| Baguio City | `1411020000` | CAR |

Full list of ~1,642 cities/municipalities in `data/psgc_cities.csv`.

---

## Relief Item Configuration

Relief items are defined in a single config dictionary (`RELIEF_ITEMS`) in the forecast service. To add or modify items, update this dict and the corresponding DB columns.

```python
RELIEF_ITEMS = {
    "rice_kg":      {"label": "Rice",          "unit": "kg",    "sphere_rate": 1.5},
    "water_liters": {"label": "Water",         "unit": "L",     "sphere_rate": 15.0},
    "meds_units":   {"label": "Medicine Kits", "unit": "units", "sphere_rate": 0.08},
    "kits_units":   {"label": "Hygiene Kits",  "unit": "units", "sphere_rate": 0.07},
}
```

---

## What Is Not Built Yet (Won't Have)

Do not implement the following unless explicitly instructed. These are out of scope for the current hackathon prototype:

- Real-time push notifications or SSE streams
- PAGASA bulletin scraper
- Barangay-level map (current scope is city/municipality only)
- Mobile-responsive layout
- Volcano eruption hazard GeoJSON layer
- Alembic migration files (tables are created via `Base.metadata.create_all`)
