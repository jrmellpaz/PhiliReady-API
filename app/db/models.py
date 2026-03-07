"""
ORM models for the BariReady database.

Tables:
  - cities: City/municipality reference data (population, risk, geography)
  - relief_distributions: Synthetic historical relief distribution logs
  - users: Authenticated users (admin or LGU roles)
  - user_city_access: Junction table mapping LGU users → cities they can edit
  - item_prices: Global unit prices for relief goods (in PHP)
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Cities ─────────────────────────────────────────────────────────────────

class City(Base):
    """
    City or municipality in the Philippines.
    Primary key is the PSGC code (e.g. "PH072217000").
    """
    __tablename__ = "cities"

    pcode       = Column(String, primary_key=True)    # PSGC code, e.g. "PH072217000"
    name        = Column(String, nullable=False)       # City/municipality name
    province    = Column(String, nullable=False)       # Province name
    region      = Column(String, nullable=False)       # Region name
    latitude    = Column(Float, nullable=False)        # Centroid latitude
    longitude   = Column(Float, nullable=False)        # Centroid longitude
    population  = Column(Integer, nullable=False)      # Total population (PSA Census)
    households  = Column(Integer, nullable=False)      # Estimated number of households
    poverty_pct = Column(Float, default=0.20)          # Poverty incidence 0.0–1.0
    is_coastal  = Column(Integer, default=0)           # 0 = inland, 1 = coastal
    flood_zone  = Column(String, default="medium")     # low / medium / high
    eq_zone     = Column(String, default="medium")     # low / medium / high
    risk_score  = Column(Float, default=0.5)           # Composite risk score 0.0–1.0

    # Audit fields — tracks who last edited this city's data
    updated_by  = Column(String, nullable=True)        # Email of last editor
    updated_at  = Column(DateTime, nullable=True)      # Timestamp of last edit

    distributions = relationship("ReliefDistribution", back_populates="city")
    user_access   = relationship("UserCityAccess", back_populates="city")


# ── Relief Distributions ──────────────────────────────────────────────────

class ReliefDistribution(Base):
    """
    One day of relief distribution for one city during one disaster event.
    Generated synthetically by seed_data.py, used for demand forecasting.
    """
    __tablename__ = "relief_distributions"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    city_pcode   = Column(String, ForeignKey("cities.pcode"), nullable=False)
    event_date   = Column(DateTime, nullable=False)    # Day of distribution
    hazard_type  = Column(String, nullable=False)      # typhoon / flood / earthquake
    severity     = Column(Integer, nullable=False)     # 1–4
    rice_kg      = Column(Float, nullable=False)       # kg distributed
    water_liters = Column(Float, nullable=False)       # liters distributed
    meds_units   = Column(Float, nullable=False)       # medicine kits distributed
    kits_units   = Column(Float, nullable=False)       # hygiene kits distributed

    city = relationship("City", back_populates="distributions")


# ── Users ──────────────────────────────────────────────────────────────────

class User(Base):
    """
    Authenticated user. Roles:
      - 'admin': Can edit any city, manage users, set prices
      - 'lgu': Can only edit cities assigned via user_city_access
    """
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    email           = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    full_name       = Column(String, nullable=False)
    role            = Column(String, nullable=False, default="lgu")  # "admin" or "lgu"
    created_at      = Column(DateTime, default=datetime.utcnow)

    city_access = relationship("UserCityAccess", back_populates="user")


# ── User ↔ City Access (Junction Table) ───────────────────────────────────

class UserCityAccess(Base):
    """
    Maps LGU users to the cities they are authorized to edit.
    Admin users bypass this table (they can edit any city).
    """
    __tablename__ = "user_city_access"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    city_pcode = Column(String, ForeignKey("cities.pcode"), nullable=False)

    # Prevent duplicate assignments
    __table_args__ = (
        UniqueConstraint("user_id", "city_pcode", name="uq_user_city"),
    )

    user = relationship("User", back_populates="city_access")
    city = relationship("City", back_populates="user_access")


# ── Item Prices ────────────────────────────────────────────────────────────

class ItemPrice(Base):
    """
    Global unit prices for relief goods in Philippine Pesos (PHP).
    Used to calculate cost estimates in forecasts.
    One row per relief item.
    """
    __tablename__ = "item_prices"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    item_key       = Column(String, unique=True, nullable=False)  # e.g. "rice_kg"
    label          = Column(String, nullable=False)                # e.g. "Rice"
    unit           = Column(String, nullable=False)                # e.g. "kg"
    price_per_unit = Column(Float, nullable=False)                 # PHP per unit
    updated_at     = Column(DateTime, default=datetime.utcnow)
