# 🇵🇭 PhiliReady API

**Micro-Demand Forecaster for Relief Goods** — Predicts 7-day relief supply demand for all Philippine cities and municipalities. Built for DRRMO officers and LGU coordinators.

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📖 Overview

PhiliReady is a backend API that helps Philippine disaster response teams estimate relief goods demand **before and during** natural disasters. It uses **SPHERE humanitarian standards** combined with hazard-specific demand curves to forecast daily requirements for rice, water, medicine kits, and hygiene kits across all 1,600+ cities and municipalities nationwide.

### Key Features

- **7-Day Demand Forecasting** — SPHERE-standard formula with severity-scaled demand curves for typhoons, floods, earthquakes, and volcanic events
- **Cost Estimation** — Forecasts include per-item and total PHP cost estimates using configurable unit prices
- **Interactive Map Data** — GeoJSON-ready demand heatmap endpoint for frontend map visualizations
- **Weather Integration** — Real-time and historical weather data from the [Open-Meteo API](https://open-meteo.com/)
- **What-If Simulator** — Forecast demand for hypothetical cities with custom parameters (no login required)
- **Role-Based Access Control** — JWT authentication with admin and LGU user roles
- **City-Level Permissions** — LGU users can only edit cities assigned to them; admins have full access

---

## 🛠️ Tech Stack

| Layer           | Technology                                    |
| --------------- | --------------------------------------------- |
| Framework       | [FastAPI](https://fastapi.tiangolo.com/) 0.115 |
| Language        | Python 3.11                                   |
| Database        | PostgreSQL + SQLAlchemy 2.0                   |
| Authentication  | JWT (python-jose + passlib/bcrypt)             |
| Weather Data    | Open-Meteo API (free, no key required)         |
| Data Processing | Pandas + NumPy                                |
| HTTP Client     | httpx                                         |
| Deployment      | Heroku (Procfile + runtime.txt)                |

---

## 📁 Project Structure

```
philiready_api/
├── app/
│   ├── main.py              # FastAPI entry point, CORS, router registration
│   ├── deps.py              # Auth dependencies (JWT, role checks, city access)
│   ├── db/
│   │   ├── database.py      # SQLAlchemy engine + session factory
│   │   ├── models.py        # ORM models (City, User, ReliefDistribution, ItemPrice, AiAssessmentCache)
│   │   └── seed_data.py     # Database seeder (cities, admin user, prices, distributions)
│   ├── routers/
│   │   ├── map.py           # GET /map/demand-heat — heatmap data
│   │   ├── forecast.py      # GET /forecast/{pcode} — city demand forecast
│   │   ├── simulate.py      # POST /simulate — quick forecast for custom params
│   │   ├── simulator.py     # POST /simulator — detailed what-if scenarios
│   │   ├── cities.py        # CRUD endpoints for cities
│   │   ├── weather.py       # GET /weather/{pcode} — weather data
│   │   ├── prices.py        # GET/PATCH item prices
│   │   ├── auth.py          # POST /auth/token, GET /auth/me
│   │   ├── admin.py         # Admin-only user management
│   │   ├── chat.py          # POST /chat — PhiliReady Assistant
│   │   └── explain.py       # POST /explain — AI-generated disaster-preparedness assessment
│   ├── schemas/
│   │   └── responses.py     # Pydantic response models (camelCase)
│   └── services/
│       ├── forecast_service.py  # SPHERE formula + optional Prophet models
│       ├── demand_service.py    # Demand computation helpers
│       ├── weather_service.py   # Open-Meteo API client
│       ├── auth_service.py      # JWT token creation/validation, password hashing
│       └── ai_cache.py          # DB helpers for AI assessment cache entries
├── data/
│   ├── psgc_cities.csv          # All PH cities/municipalities (PSGC codes)
│   ├── PH_Adm3_MuniCities.csv   # Administrative boundary data
│   ├── generate_cities.py       # Script to generate city CSV from raw data
│   └── parse_2024_census.py     # PSA 2024 Census data parser
├── tests/
│   └── test_api.py          # API endpoint tests
├── references/              # Project documentation and plans
├── requirements.txt         # Python dependencies
├── Procfile                 # Heroku deployment config
├── runtime.txt              # Python version (3.11.9)
├── .env.example             # Environment variable template
└── .gitignore
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **PostgreSQL** (running locally or remote)
- **pip** (Python package manager)

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/philiready_api.git
cd philiready_api
```

### 2. Create a Virtual Environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```env
# PostgreSQL connection string (required)
DATABASE_URL=postgresql://postgres:password@localhost:5432/philiready

# JWT secret — generate with: python -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRY_MINUTES=1440

# Open-Meteo (free, no API key needed)
OPEN_METEO_BASE_URL=https://api.open-meteo.com/v1
OPEN_METEO_ARCHIVE_URL=https://archive-api.open-meteo.com/v1

# Default admin account
ADMIN_EMAIL=admin@philiready.ph
ADMIN_PASSWORD=change-me-in-production

LLM_API_KEY=your-llm-api-key-here


```

### 5. Create the Database

```bash
# Create the PostgreSQL database
createdb philiready

# Seed tables, admin user, cities, prices, and synthetic distribution data
python -m app.db.seed_data
```

The seed script is **idempotent** — safe to re-run without duplicating data.

### 6. Run the Development Server

```bash
uvicorn app.main:app --reload --port 8000
```

The API is now running at **http://localhost:8000**.

---

## 📚 API Documentation

FastAPI auto-generates interactive docs:

| Tool       | URL                              |
| ---------- | -------------------------------- |
| Swagger UI | http://localhost:8000/docs        |
| ReDoc      | http://localhost:8000/redoc       |
| Health     | http://localhost:8000/health      |

### API Endpoints (v1)

All endpoints are prefixed with `/api/v1/`.

| Method | Endpoint                    | Auth     | Description                              |
| ------ | --------------------------- | -------- | ---------------------------------------- |
| GET    | `/map/demand-heat`          | —        | Demand heatmap data for all cities       |
| GET    | `/forecast/{pcode}`         | —        | 7-day demand forecast for a city         |
| POST   | `/simulate`                 | —        | Quick forecast with custom parameters    |
| POST   | `/simulator`                | —        | Detailed what-if scenario simulation     |
| GET    | `/cities`                   | —        | List all cities (paginated, filterable)  |
| GET    | `/cities/{pcode}`           | —        | Single city details                      |
| PATCH  | `/cities/{pcode}`           | LGU+     | Update city data (role-restricted)       |
| GET    | `/weather/{pcode}`          | —        | Weather data for a city                  |
| GET    | `/prices`                   | —        | Current relief item prices (PHP)         |
| PATCH  | `/prices/{item_key}`        | Admin    | Update an item price                     |
| POST   | `/auth/token`               | —        | Login (returns JWT)                      |
| GET    | `/auth/me`                  | Bearer   | Current user profile                     |
| GET    | `/admin/users`              | Admin    | List all users                           |
| POST   | `/admin/users`              | Admin    | Create a new user                        |
| POST   | `/chat`                     | —        | PhiliReady Assistant                     |
| POST   | `/explain`                  | —        | AI-generated assessment                  |

> **Note:** All API responses use **camelCase** keys (e.g., `riskScore`, `povertyPct`).

---

## 🧪 Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run a specific test
pytest tests/test_api.py::test_health_check_camel_case
```

> **Note:** Tests require a seeded PostgreSQL database (run `python -m app.db.seed_data` first).

---

## 🌐 Deployment (Heroku)

The project includes Heroku deployment files:

- **`Procfile`** — Runs uvicorn on Heroku's `$PORT`
- **`runtime.txt`** — Specifies Python 3.11.9

```bash
# Deploy to Heroku
heroku create philiready-api
heroku addons:create heroku-postgresql:essential-0
heroku config:set JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
git push heroku main

# Seed the production database
heroku run python -m app.db.seed_data
```

---

## 🔐 Authentication

PhiliReady uses **JWT Bearer tokens** for authenticated endpoints.

### Login

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -d "username=admin@philiready.ph&password=admin123"
```

### Use the Token

```bash
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer <your-token>"
```

### User Roles

| Role    | Permissions                                         |
| ------- | --------------------------------------------------- |
| `admin` | Full access — manage users, edit any city, set prices |
| `lgu`   | Edit only assigned cities                           |

---

## 📊 Forecasting Model

The demand forecasting engine uses a **two-tier approach**:

1. **SPHERE Formula** (default) — Calculates demand based on:
   - Displaced households (population × displacement rate × severity)
   - Per-item SPHERE standard rates (e.g., 1.5 kg rice/household/day)
   - Hazard-specific demand curves (typhoon, flood, earthquake, volcanic)
   - Severity multiplier (1–4 scale)

2. **Prophet Models** (optional) — If pre-trained `.pkl` model files exist in `app/models/prophet/`, the system uses Facebook Prophet for more accurate, data-driven predictions.

### Relief Items Tracked

| Item          | SPHERE Rate      | Default Price (PHP) |
| ------------- | ---------------- | ------------------- |
| Rice          | 1.5 kg/hh/day    | ₱50/kg              |
| Water         | 15.0 L/hh/day    | ₱15/L               |
| Medicine Kits | 0.08 units/hh/day | ₱500/unit            |
| Hygiene Kits  | 0.07 units/hh/day | ₱350/unit            |

---

## 📝 License

This project is for academic and humanitarian purposes.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request
