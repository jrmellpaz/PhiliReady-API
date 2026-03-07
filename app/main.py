"""
PhiliReady API — Micro-Demand Forecaster for Relief Goods

FastAPI application entry point. Configures:
  - CORS for frontend cross-origin requests
  - API versioning under /api/v1/
  - All route registrations (including auth, admin, simulator, prices)
  - Health check endpoint

Run locally:
    uvicorn app.main:app --reload --port 8000

Swagger docs available at:
    http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import map, forecast, simulate, cities, weather, auth, admin, simulator, prices
from app.schemas.responses import HealthResponse


# ── FastAPI Application ────────────────────────────────────────────────────

app = FastAPI(
    title="PhiliReady API",
    description=(
        "Micro-Demand Forecaster for Relief Goods — "
        "Predicts 7-day relief demand for all Philippine cities and municipalities. "
        "Built for DRRMO officers and LGU coordinators."
    ),
    version="2.0.0",
)


# ── CORS Configuration ────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://philiready.vercel.app",   # Production frontend
        "http://localhost:3000",           # Local frontend (Next.js default)
        "http://localhost:5173",           # Local frontend (Vite default)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Router Registration ───────────────────────────────────────────────────
# All API routes are versioned under /api/v1/

API_V1_PREFIX = "/api/v1"

# Public endpoints
app.include_router(map.router,       prefix=API_V1_PREFIX, tags=["Map"])
app.include_router(forecast.router,  prefix=API_V1_PREFIX, tags=["Forecast"])
app.include_router(simulate.router,  prefix=API_V1_PREFIX, tags=["Simulate"])
app.include_router(cities.router,    prefix=API_V1_PREFIX, tags=["Cities"])
app.include_router(weather.router,   prefix=API_V1_PREFIX, tags=["Weather"])
app.include_router(simulator.router, prefix=API_V1_PREFIX, tags=["Simulator"])
app.include_router(prices.router,    prefix=API_V1_PREFIX, tags=["Prices"])

# Authenticated endpoints
app.include_router(auth.router,      prefix=API_V1_PREFIX, tags=["Authentication"])
app.include_router(admin.router,     prefix=API_V1_PREFIX, tags=["Admin"])


# ── Health Check ───────────────────────────────────────────────────────────

@app.get("/health", tags=["Infrastructure"])
def health():
    """Health check for deployment monitoring."""
    return {"status": "ok", "service": "philiready-api", "version": "2.0.0"}
