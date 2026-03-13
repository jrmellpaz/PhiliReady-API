# PhiliReady API

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
- **AI-Powered Features** — Chat assistant and AI-generated disaster preparedness assessments

---

## 🧮 Forecasting Methodology

### Core Formula

The demand forecasting engine combines **SPHERE humanitarian standards** with location-specific risk factors:

```
Displacement Rate = Base Rate × Zone Modifier × Coastal Modifier × Vulnerability × Seasonal Multiplier
```
```
Displaced Households = Total Households × Displacement Rate (capped at 85%)
```
```
Demand = Displaced Households × SPHERE Rate × Household Size Factor × Daily Curve Multiplier
```

### Relief Items & SPHERE Rates

| Item | Unit | SPHERE Rate | Description |
|------|------|-------------|-------------|
| Rice | kg | 1.5 kg/household/day | Staple food allocation |
| Water | liters | 15 L/household/day | Drinking and hygiene water |
| Medicine Kits | units | 0.08 units/household/day | ~1 kit per 12 families |
| Hygiene Kits | units | 0.07 units/household/day | ~1 kit per 14 families |

### Hazard-Specific Demand Curves

Daily demand multipliers over 7 days (normalized to peak = 1.0):

| Day | Typhoon | Flood | Earthquake | Volcanic |
|-----|---------|-------|------------|----------|
| 1   | 0.2     | 0.3   | 1.2        | 0.1      |
| 2   | 1.0     | 0.8   | 0.9        | 0.3      |
| 3   | 1.6     | 1.0   | 0.6        | 0.6      |
| 4   | 1.4     | 0.8   | 0.3        | 0.8      |
| 5   | 1.0     | 0.5   | 0.2        | 0.7      |
| 6   | 0.7     | 0.3   | 0.1        | 0.5      |
| 7   | 0.4     | 0.1   | 0.1        | 0.3      |

### Displacement Model Constants

- **Base Displacement Rates**: Severity 1-4 (10%-55% of households displaced)
- **Zone Modifiers**: Low (0.7×), Medium (1.0×), High (1.3×)
- **Coastal Amplification**: +20% for coastal areas during typhoons/floods
- **Vulnerability Factor**: Non-linear poverty scaling (1.0× to 2.2×)
- **Seasonal Multipliers**: Philippine wet/dry season adjustments (0.85× to 1.15×)
- **Household Size**: National average 4.1 persons/household (PSA 2020 Census)

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
| Rate Limiting   | slowapi                                       |
| AI Integration  | Groq API                                      |

---

## 📁 Project Structure

```
philiready_api/
├── app/
│   ├── main.py              # FastAPI entry point, CORS, router registration
│   ├── deps.py              # Auth dependencies (JWT, role checks, city access)
│   ├── limiter.py           # Rate limiting configuration
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
│       ├── forecast_service.py  # SPHERE formula computation
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
└── README.md
```

---

## 📊 Data Sources

### Primary Data Sources

- **Philippine Statistics Authority (PSA)**: 2024 Census population data
- **Philippine Statistics Geographic Code (PSGC)**: Administrative boundaries and codes
- **Open-Meteo API**: Real-time and historical weather data
- **SPHERE Standards**: Humanitarian relief guidelines (spherehandbook.org)

### Database Tables

- **cities**: 1,600+ municipalities with demographics, risk scores, and hazard zones
- **relief_distributions**: Synthetic historical distribution data for forecasting validation
- **users**: Authenticated users with role-based permissions
- **user_city_access**: LGU user ↔ city assignment mapping
- **item_prices**: Configurable unit prices for cost estimation
- **ai_assessment_cache**: Cached AI-generated assessments per scenario

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

All endpoints are prefixed with `/api/v1/`. All responses use **camelCase** keys.

#### Public Endpoints

| Method | Endpoint                    | Description                              |
| ------ | --------------------------- | ---------------------------------------- |
| GET    | `/map/demand-heat`          | Demand heatmap data for all cities       |
| GET    | `/forecast/{pcode}`         | 7-day demand forecast for a city         |
| POST   | `/simulate`                 | Quick forecast with custom parameters    |
| POST   | `/simulator`                | Detailed what-if scenario simulation     |
| GET    | `/cities`                   | List all cities (paginated, filterable)  |
| GET    | `/cities/{pcode}`           | Single city details                      |
| GET    | `/weather/{pcode}`          | Weather data for a city                  |
| GET    | `/prices`                   | Current relief item prices (PHP)         |
| POST   | `/chat`                     | PhiliReady Assistant                     |
| POST   | `/explain`                  | AI-generated assessment                  |

#### Authenticated Endpoints

| Method | Endpoint                    | Auth     | Description                              |
| ------ | --------------------------- | -------- | ---------------------------------------- |
| POST   | `/auth/token`               | —        | Login (returns JWT)                      |
| GET    | `/auth/me`                  | Bearer   | Current user profile                     |
| PATCH  | `/cities/{pcode}`           | LGU+     | Update city data (role-restricted)       |
| PATCH  | `/prices/{item_key}`        | Admin    | Update an item price                     |
| GET    | `/admin/users`              | Admin    | List all users                           |
| POST   | `/admin/users`              | Admin    | Create a new user                        |
| PATCH  | `/admin/users/{id}/cities`  | Admin    | Assign cities to LGU user                |

### Authentication

- **JWT Bearer tokens** with 24-hour expiry
- **Role-based access**: `admin` (full access) or `lgu` (city-restricted)
- **City permissions**: LGU users can only edit assigned cities

### Rate Limiting

- Public endpoints: 100 requests/hour per IP
- Authenticated endpoints: 1000 requests/hour per user

---

## 🧪 Running Tests

```bash
# Install test dependencies (if separate)
pip install pytest

# Run the test suite
pytest tests/

# Run with coverage
pytest --cov=app tests/
```

Tests verify:
- API response formats (camelCase)
- Authentication flows
- Data integrity
- PSGC code validation

---


## 🙏 Acknowledgments

- **SPHERE Project** for humanitarian standards
- **Philippine Statistics Authority** for census data
- **Open-Meteo** for weather API
- **FastAPI community** for excellent documentation

---

*Built with ❤️ for Philippine disaster response teams*
