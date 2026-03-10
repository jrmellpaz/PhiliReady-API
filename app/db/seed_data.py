"""
Seed the PostgreSQL database with initial data.

Run once:  python -m app.db.seed_data

This script:
  1. Creates all database tables if they don't exist
  2. Creates the default admin user (from .env or defaults)
  3. Seeds initial relief item prices (PHP)
  4. Loads city data from data/psgc_cities.csv
  5. Generates synthetic relief distribution records

The script is idempotent — safe to re-run without duplicating data.
"""
import os
import csv
import json
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

from app.db.database import engine, SessionLocal
from app.db.models import Base, City, ReliefDistribution, User, UserCityAccess, ItemPrice
from app.services.auth_service import hash_password


# ── Historical disaster events ─────────────────────────────────────────────

HISTORICAL_EVENTS = [
    ("2021-12-16", "typhoon",    4, "Typhoon Odette (Rai)"),
    ("2022-09-25", "typhoon",    3, "Typhoon Karding (Noru)"),
    ("2023-07-25", "typhoon",    2, "Typhoon Egay (Doksuri)"),
    ("2023-10-14", "typhoon",    3, "Typhoon Jenny (Koinu)"),
    ("2024-11-01", "typhoon",    4, "Typhoon Pepito (Man-yi)"),
    ("2022-04-10", "earthquake", 3, "Abra Earthquake"),
    ("2023-06-15", "flood",      2, "Habagat flooding"),
    ("2024-07-20", "flood",      3, "Southwest monsoon flooding"),
    ("2025-01-22", "earthquake", 3, "Bogo City M6.9"),
]


# ── Demand curves ──────────────────────────────────────────────────────────

HAZARD_CURVES = {
    "typhoon": {
        1: [0.1, 0.5, 0.8, 0.6, 0.4, 0.2, 0.1],
        2: [0.2, 1.0, 1.6, 1.4, 1.0, 0.7, 0.4],
        3: [0.4, 1.6, 2.5, 2.2, 1.7, 1.1, 0.6],
        4: [0.8, 2.8, 4.0, 3.5, 2.6, 1.6, 0.9],
    },
    "flood": {
        1: [0.3, 0.8, 1.0, 0.8, 0.5, 0.3, 0.1],
        2: [0.5, 1.3, 1.8, 1.5, 1.0, 0.6, 0.3],
        3: [0.8, 2.0, 2.8, 2.4, 1.6, 0.9, 0.4],
        4: [1.2, 3.0, 4.2, 3.6, 2.4, 1.4, 0.6],
    },
    "earthquake": {
        1: [1.2, 0.9, 0.6, 0.3, 0.2, 0.1, 0.1],
        2: [1.8, 1.4, 1.0, 0.6, 0.3, 0.2, 0.1],
        3: [3.0, 2.4, 1.8, 1.2, 0.7, 0.4, 0.2],
        4: [4.5, 3.6, 2.8, 1.9, 1.1, 0.6, 0.3],
    },
}

SPHERE = {
    "rice_kg": 1.5, "water_liters": 15.0, "meds_units": 0.08, "kits_units": 0.07,
}

# ── Default relief item prices (PHP) ──────────────────────────────────────

DEFAULT_PRICES = [
    {"item_key": "rice_kg",      "label": "Rice",          "unit": "kg",    "price_per_unit": 50.0},
    {"item_key": "water_liters", "label": "Water",         "unit": "L",     "price_per_unit": 15.0},
    {"item_key": "meds_units",   "label": "Medicine Kits", "unit": "units", "price_per_unit": 500.0},
    {"item_key": "kits_units",   "label": "Hygiene Kits",  "unit": "units", "price_per_unit": 350.0},
]

NAME_ALIASES = {
    "BALIWAG": "BALIUAG",
    "STO TOMAS": "SANTO TOMAS",
    "PIO V CORPUS": "PIO V CORPUZ",
    "PRESIDENT CARLOS P GARCIA": "PRES CARLOS P GARCIA",
    "PINAMUNGAJAN": "PINAMUNGAHAN",
    "OZAMIZ": "OZAMIS",
    "LEON T POSTIGO": "BACUNGAN",
    "AMAI MANABILANG": "BUMBARAN",
}


def clean_city_name(name: str) -> str:
    """Normalize municipality names for matching across CSV and GeoJSON sources."""
    if not isinstance(name, str):
        return ""

    cleaned = name.upper().strip()
    replacements = [
        ("CITY OF ", ""),
        (" CITY", ""),
        ("MUNICIPALITY OF ", ""),
        (" (CAPITAL)", ""),
        ("-", " "),
        (".", ""),
        ("Ñ", "N"),
    ]
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)

    cleaned = " ".join(cleaned.split())
    return NAME_ALIASES.get(cleaned, cleaned)


def iter_coordinate_pairs(coordinates):
    """Yield [lon, lat] pairs from nested Polygon or MultiPolygon coordinates."""
    if not isinstance(coordinates, list):
        return

    if len(coordinates) >= 2 and all(isinstance(value, (int, float)) for value in coordinates[:2]):
        yield coordinates[:2]
        return

    for item in coordinates:
        yield from iter_coordinate_pairs(item)


def compute_feature_centroid(geometry: dict) -> tuple[float, float]:
    """Compute a simple centroid from GeoJSON polygon coordinates."""
    geometry = geometry or {}
    pairs = list(iter_coordinate_pairs(geometry.get("coordinates", [])))
    if not pairs:
        return 0.0, 0.0

    lon = sum(pair[0] for pair in pairs) / len(pairs)
    lat = sum(pair[1] for pair in pairs) / len(pairs)
    return round(lat, 6), round(lon, 6)


def load_municity_reference() -> dict[str, list[dict]]:
    """Load canonical municipality metadata from the GeoJSON reference file."""
    reference_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "references", "municities.json"
    )

    if not os.path.exists(reference_path):
        raise FileNotFoundError(
            f"Municipality reference file not found at {reference_path}."
        )

    with open(reference_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    mapping: dict[str, list[dict]] = {}
    for feature in payload.get("features", []):
        properties = feature.get("properties", {})
        name = properties.get("ADM3_EN")
        if not name:
            continue

        latitude, longitude = compute_feature_centroid(feature.get("geometry", {}))
        entry = {
            "pcode": properties.get("ADM3_PCODE"),
            "name": name.strip(),
            "province": properties.get("ADM2_EN", "Unknown Province"),
            "region": properties.get("ADM1_EN", "Unknown Region"),
            "latitude": latitude,
            "longitude": longitude,
        }

        alias_names = [
            properties.get("ADM3_EN"),
            properties.get("ADM3ALT1EN"),
            properties.get("ADM3ALT2EN"),
        ]
        for alias_name in alias_names:
            clean_name = clean_city_name(alias_name)
            if clean_name:
                mapping.setdefault(clean_name, []).append(entry)

    return mapping


def build_city_record(row: dict, reference_mapping: dict[str, list[dict]], matched_counts: dict[str, int]) -> dict | None:
    """Merge synthetic city metrics with canonical identifiers from the reference GeoJSON."""
    source_name = row["name"].strip()
    clean_name = clean_city_name(source_name)
    match_index = matched_counts.get(clean_name, 0)
    matched_counts[clean_name] = match_index + 1

    canonical_rows = reference_mapping.get(clean_name, [])
    canonical = canonical_rows[match_index] if match_index < len(canonical_rows) else None

    if not canonical or not canonical.get("pcode"):
        return None

    pcode = canonical["pcode"]
    name = canonical["name"] or source_name
    province = canonical["province"] or row["province"]
    region = canonical["region"] or row["region"]
    latitude = canonical["latitude"] or float(row["latitude"])
    longitude = canonical["longitude"] or float(row["longitude"])

    return {
        "legacy_pcode": row["pcode"],
        "pcode": pcode,
        "name": name,
        "province": province,
        "region": region,
        "latitude": latitude,
        "longitude": longitude,
        "population": int(row["population"]),
        "households": int(row["households"]),
        "poverty_pct": float(row["poverty_pct"]),
        "is_coastal": int(row["is_coastal"]),
        "flood_zone": row["flood_zone"],
        "eq_zone": row["eq_zone"],
        "risk_score": float(row["risk_score"]),
    }


def apply_city_fields(city: City, city_row: dict) -> None:
    """Copy canonical seed values onto a City ORM row."""
    city.name = city_row["name"]
    city.province = city_row["province"]
    city.region = city_row["region"]
    city.latitude = city_row["latitude"]
    city.longitude = city_row["longitude"]
    city.population = city_row["population"]
    city.households = city_row["households"]
    city.poverty_pct = city_row["poverty_pct"]
    city.is_coastal = city_row["is_coastal"]
    city.flood_zone = city_row["flood_zone"]
    city.eq_zone = city_row["eq_zone"]
    city.risk_score = city_row["risk_score"]


def create_city(city_row: dict, updated_by: str = None, updated_at=None) -> City:
    """Create a City ORM row from a merged city record."""
    return City(
        pcode=city_row["pcode"],
        name=city_row["name"],
        province=city_row["province"],
        region=city_row["region"],
        latitude=city_row["latitude"],
        longitude=city_row["longitude"],
        population=city_row["population"],
        households=city_row["households"],
        poverty_pct=city_row["poverty_pct"],
        is_coastal=city_row["is_coastal"],
        flood_zone=city_row["flood_zone"],
        eq_zone=city_row["eq_zone"],
        risk_score=city_row["risk_score"],
        updated_by=updated_by,
        updated_at=updated_at,
    )


def find_legacy_city(db, city_row: dict):
    """Find an existing city row that still uses a legacy pcode."""
    legacy_pcode = city_row.get("legacy_pcode")
    if legacy_pcode and legacy_pcode != city_row["pcode"]:
        legacy_city = db.get(City, legacy_pcode)
        if legacy_city:
            return legacy_city

    matches = db.query(City).filter(City.name == city_row["name"]).all()
    if len(matches) == 1 and matches[0].pcode != city_row["pcode"]:
        return matches[0]

    return None


def migrate_city_pcode(db, legacy_city: City, city_row: dict) -> None:
    """Replace a legacy city pcode with the canonical one and preserve related rows."""
    replacement = create_city(
        city_row,
        updated_by=legacy_city.updated_by,
        updated_at=legacy_city.updated_at,
    )
    db.add(replacement)
    db.flush()

    db.query(ReliefDistribution).filter(
        ReliefDistribution.city_pcode == legacy_city.pcode
    ).update({ReliefDistribution.city_pcode: city_row["pcode"]}, synchronize_session=False)

    db.query(UserCityAccess).filter(
        UserCityAccess.city_pcode == legacy_city.pcode
    ).update({UserCityAccess.city_pcode: city_row["pcode"]}, synchronize_session=False)

    db.delete(legacy_city)


def upsert_city(db, city_row: dict) -> str:
    """Insert, update, or migrate a city row to the canonical pcode."""
    existing = db.get(City, city_row["pcode"])
    if existing:
        apply_city_fields(existing, city_row)
        return "updated"

    legacy_city = find_legacy_city(db, city_row)
    if legacy_city:
        migrate_city_pcode(db, legacy_city, city_row)
        return "migrated"

    db.add(create_city(city_row))
    return "added"


def prune_stale_cities(db, valid_pcodes: set[str]) -> int:
    """Remove rows that do not exist in the canonical municipality dataset."""
    stale_pcodes = [
        city.pcode
        for city in db.query(City).all()
        if city.pcode not in valid_pcodes
    ]
    if not stale_pcodes:
        return 0

    db.query(ReliefDistribution).filter(
        ReliefDistribution.city_pcode.in_(stale_pcodes)
    ).delete(synchronize_session=False)
    db.query(UserCityAccess).filter(
        UserCityAccess.city_pcode.in_(stale_pcodes)
    ).delete(synchronize_session=False)
    db.query(City).filter(City.pcode.in_(stale_pcodes)).delete(synchronize_session=False)
    return len(stale_pcodes)


def generate_distributions(city_row: dict, event_date_str: str,
                           hazard_type: str, severity: int) -> list:
    """Generate 7 days of synthetic distribution records for one city/event."""
    hh = city_row["households"]
    poverty = city_row["poverty_pct"]
    coastal = city_row["is_coastal"]
    pcode = city_row["pcode"]

    curve = HAZARD_CURVES.get(hazard_type, HAZARD_CURVES["typhoon"])[severity]

    base_displacement = 0.15 + (severity * 0.10) + (coastal * 0.10)
    vulnerability_modifier = 1.0 + (poverty * 1.2)
    displaced_hh = int(hh * min(base_displacement * vulnerability_modifier, 0.85))

    records = []
    event_date = datetime.strptime(event_date_str, "%Y-%m-%d")

    for day_offset, multiplier in enumerate(curve):
        if multiplier < 0.05:
            continue

        dist_date = event_date + timedelta(days=day_offset)
        noise = lambda: np.random.uniform(0.85, 1.15)

        records.append(ReliefDistribution(
            city_pcode=pcode,
            event_date=dist_date,
            hazard_type=hazard_type,
            severity=severity,
            rice_kg=round(displaced_hh * SPHERE["rice_kg"] * multiplier * noise(), 1),
            water_liters=round(displaced_hh * SPHERE["water_liters"] * multiplier * noise(), 1),
            meds_units=round(displaced_hh * SPHERE["meds_units"] * multiplier * noise(), 1),
            kits_units=round(displaced_hh * SPHERE["kits_units"] * multiplier * noise(), 1),
        ))

    return records


def load_cities_from_csv() -> list[dict]:
    """Load city data from CSV metrics merged with canonical GeoJSON identifiers."""
    csv_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "data", "psgc_cities.csv"
    )

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"City data file not found at {csv_path}. "
            "Run 'python data/generate_cities.py' first."
        )

    reference_mapping = load_municity_reference()
    matched_counts: dict[str, int] = {}
    seen_pcodes: set[str] = set()
    cities = []
    skipped = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            city_record = build_city_record(row, reference_mapping, matched_counts)
            if city_record is None:
                skipped.append(row["name"].strip())
                continue
            # Guard against duplicate pcodes caused by common municipality
            # names (e.g. Concepcion, Magsaysay, Rizal) matching to the
            # wrong canonical GeoJSON entry.
            if city_record["pcode"] in seen_pcodes:
                skipped.append(row["name"].strip())
                continue
            seen_pcodes.add(city_record["pcode"])
            cities.append(city_record)

    if skipped:
        print(f"  -> Skipped {len(skipped)} rows not present in municities.json")

    return cities


def run():
    """Main seed function — creates tables, admin user, prices, cities, distributions."""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    # ── Step 1: Create default admin user ──────────────────────────────────
    admin_email = os.getenv("ADMIN_EMAIL", "admin@philiready.ph")
    admin_password = os.getenv("ADMIN_PASSWORD", "admin123")

    existing_admin = db.query(User).filter(User.email == admin_email).first()
    if not existing_admin:
        admin = User(
            email=admin_email,
            hashed_password=hash_password(admin_password),
            full_name="System Admin",
            role="admin",
        )
        db.add(admin)
        db.commit()
        print(f"  -> Created admin user: {admin_email}")
    else:
        print(f"  -> Admin user already exists: {admin_email}")

    # ── Step 2: Seed item prices ───────────────────────────────────────────
    existing_prices = db.query(ItemPrice).count()
    if existing_prices == 0:
        for price_data in DEFAULT_PRICES:
            db.add(ItemPrice(**price_data))
        db.commit()
        print(f"  -> Seeded {len(DEFAULT_PRICES)} item prices")
    else:
        print(f"  -> Item prices already exist ({existing_prices} entries)")

    # ── Step 3: Load cities from CSV ───────────────────────────────────────
    print("Loading cities from CSV + canonical municipality reference...")
    cities_data = load_cities_from_csv()
    city_stats = {"added": 0, "updated": 0, "migrated": 0, "removed": 0}

    for city_row in cities_data:
        result = upsert_city(db, city_row)
        city_stats[result] += 1

    valid_pcodes = {city_row["pcode"] for city_row in cities_data}
    city_stats["removed"] = prune_stale_cities(db, valid_pcodes)

    db.commit()
    print(
        "  -> Synced cities "
        f"(added: {city_stats['added']}, updated: {city_stats['updated']}, migrated: {city_stats['migrated']}, removed: {city_stats['removed']}, total: {len(cities_data)})"
    )

    # ── Step 4: Generate synthetic distribution records ────────────────────
    existing_count = db.query(ReliefDistribution).count()
    if existing_count > 0:
        print(f"  -> Skipping distribution generation ({existing_count} records exist)")
    else:
        print("Generating synthetic relief distributions...")
        np.random.seed(42)

        total_records = 0
        for event_date, hazard_type, severity, label in HISTORICAL_EVENTS:
            print(f"  -> {label} ({event_date})")
            batch = []
            for city_row in cities_data:
                records = generate_distributions(city_row, event_date, hazard_type, severity)
                batch.extend(records)
            db.add_all(batch)
            db.commit()
            total_records += len(batch)

        print(f"  -> Generated {total_records} distribution records")

    # ── Summary ────────────────────────────────────────────────────────────
    total_cities = db.query(City).count()
    total_dists = db.query(ReliefDistribution).count()
    total_users = db.query(User).count()
    total_prices = db.query(ItemPrice).count()
    print(f"\n[OK] Seed complete:")
    print(f"   {total_users} users | {total_prices} prices | {total_cities} cities | {total_dists} distributions")
    db.close()


if __name__ == "__main__":
    run()
