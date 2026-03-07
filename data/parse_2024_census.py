"""
Parse the 2024 Census population CSV and generate an updated psgc_cities.csv.

The raw CSV contains regions, provinces, and cities/municipalities mixed together.
This script identifies hierarchy levels by matching known region and province names,
then extracts city/municipality rows with their 2024 population.

Run: python data/parse_2024_census.py
"""
import csv
import os
import re
import random

INPUT_CSV = os.path.join(os.path.dirname(__file__), "..", "references", "population_by_region_combined.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "psgc_cities.csv")

# ── Known region headers (used to detect region rows) ──────────────────────
REGION_PATTERNS = [
    "NATIONAL CAPITAL REGION",
    "CORDILLERA ADMINISTRATIVE REGION",
    "REGION I",
    "REGION II",
    "REGION III",
    "REGION IV-A",
    "MIMAROPA",
    "REGION V",
    "REGION VI",
    "NEGROS ISLAND REGION",
    "REGION VII",
    "REGION VIII",
    "REGION IX",
    "REGION X",
    "REGION XI",
    "REGION XII",
    "REGION XIII",
    "BARMM",
]

# ── Region name mapping (CSV header → clean name) ─────────────────────────
REGION_MAP = {
    "NATIONAL CAPITAL REGION (NCR)": "NCR",
    "CORDILLERA ADMINISTRATIVE REGION (CAR)": "CAR",
    "REGION I (ILOCOS REGION)": "Region I",
    "REGION II (CAGAYAN VALLEY)": "Region II",
    "REGION III (CENTRAL LUZON)": "Region III",
    "REGION IV-A (CALABARZON)": "Region IV-A",
    "MIMAROPA REGION": "Region IV-B",
    "REGION V (BICOL REGION)": "Region V",
    "REGION VI (WESTERN VISAYAS)": "Region VI",
    "NEGROS ISLAND REGION (NIR)": "NIR",
    "REGION VII (CENTRAL VISAYAS)": "Region VII",
    "REGION VIII (EASTERN VISAYAS)": "Region VIII",
    "REGION IX (ZAMBOANGA PENINSULA)": "Region IX",
    "REGION X (NORTHERN MINDANAO)": "Region X",
    "REGION XI (DAVAO REGION)": "Region XI",
    "REGION XII (SOCCSKSARGEN)": "Region XII",
    "REGION XIII (CARAGA)": "Region XIII",
    "BANGSAMORO AUTONOMOUS REGION IN MUSLIM MINDANAO (BARMM)": "BARMM",
}

# ── Known province names (used to detect province rows) ───────────────────
# These are all 81+ provinces plus special cases. When a row matches a province
# name, it's treated as a province header — the rows after it are cities/municipalities.
PROVINCES = {
    # CAR
    "ABRA", "APAYAO", "BENGUET", "IFUGAO", "KALINGA", "MOUNTAIN PROVINCE",
    # Region I
    "ILOCOS NORTE", "ILOCOS SUR", "LA UNION", "PANGASINAN",
    # Region II
    "BATANES", "CAGAYAN", "ISABELA", "NUEVA VIZCAYA", "QUIRINO",
    # Region III
    "AURORA", "BATAAN", "BULACAN", "NUEVA ECIJA", "PAMPANGA", "TARLAC", "ZAMBALES",
    # Region IV-A
    "BATANGAS", "CAVITE", "LAGUNA", "QUEZON", "RIZAL",
    # MIMAROPA
    "MARINDUQUE", "OCCIDENTAL MINDORO", "ORIENTAL MINDORO", "PALAWAN", "ROMBLON",
    # Region V
    "ALBAY", "CAMARINES NORTE", "CAMARINES SUR", "CATANDUANES", "MASBATE", "SORSOGON",
    # Region VI
    "AKLAN", "ANTIQUE", "CAPIZ", "GUIMARAS", "ILOILO",
    # NIR
    "NEGROS OCCIDENTAL", "NEGROS ORIENTAL",
    # Region VII
    "BOHOL", "CEBU", "SIQUIJOR",
    # Region VIII
    "BILIRAN", "EASTERN SAMAR", "LEYTE", "NORTHERN SAMAR", "SAMAR", "SOUTHERN LEYTE",
    # Region IX
    "ZAMBOANGA DEL NORTE", "ZAMBOANGA DEL SUR", "ZAMBOANGA SIBUGAY",
    # Region X
    "BUKIDNON", "CAMIGUIN", "LANAO DEL NORTE", "MISAMIS OCCIDENTAL", "MISAMIS ORIENTAL",
    # Region XI
    "DAVAO DE ORO", "DAVAO DEL NORTE", "DAVAO DEL SUR", "DAVAO OCCIDENTAL", "DAVAO ORIENTAL",
    # Region XII
    "COTABATO", "SARANGANI", "SOUTH COTABATO", "SULTAN KUDARAT",
    # Region XIII
    "AGUSAN DEL NORTE", "AGUSAN DEL SUR", "DINAGAT ISLANDS", "SURIGAO DEL NORTE", "SURIGAO DEL SUR",
    # BARMM
    "BASILAN", "LANAO DEL SUR", "MAGUINDANAO DEL NORTE", "MAGUINDANAO DEL SUR", "SULU", "TAWI-TAWI",
}

# ── Approximate coordinates for provinces (lat, lon centroids) ─────────────
PROVINCE_COORDS = {
    # NCR
    "NCR First District": (14.60, 120.98), "NCR Second District": (14.63, 121.08),
    "NCR Third District": (14.68, 120.95), "NCR Fourth District": (14.48, 121.02),
    # CAR
    "Abra": (17.60, 120.63), "Apayao": (18.05, 121.15), "Benguet": (16.42, 120.60),
    "Ifugao": (16.83, 121.13), "Kalinga": (17.45, 121.30), "Mountain Province": (17.05, 121.00),
    # Region I
    "Ilocos Norte": (18.20, 120.65), "Ilocos Sur": (17.40, 120.45),
    "La Union": (16.50, 120.40), "Pangasinan": (15.95, 120.35),
    # Region II
    "Batanes": (20.45, 121.97), "Cagayan": (17.95, 121.75),
    "Isabela": (16.95, 121.75), "Nueva Vizcaya": (16.45, 121.15), "Quirino": (16.45, 121.50),
    # Region III
    "Aurora": (15.75, 121.60), "Bataan": (14.68, 120.48), "Bulacan": (14.85, 121.00),
    "Nueva Ecija": (15.55, 121.00), "Pampanga": (15.05, 120.68),
    "Tarlac": (15.50, 120.55), "Zambales": (15.10, 120.00),
    # Region IV-A
    "Batangas": (13.85, 121.08), "Cavite": (14.35, 120.95), "Laguna": (14.25, 121.22),
    "Quezon": (14.00, 121.80), "Rizal": (14.58, 121.15),
    # MIMAROPA
    "Marinduque": (13.40, 121.95), "Occidental Mindoro": (13.00, 120.65),
    "Oriental Mindoro": (12.90, 121.30), "Palawan": (10.00, 118.80), "Romblon": (12.55, 122.25),
    # Region V
    "Albay": (13.18, 123.68), "Camarines Norte": (14.13, 122.95),
    "Camarines Sur": (13.65, 123.35), "Catanduanes": (13.72, 124.25),
    "Masbate": (12.35, 123.55), "Sorsogon": (12.85, 124.00),
    # Region VI
    "Aklan": (11.75, 122.35), "Antique": (11.40, 122.00), "Capiz": (11.55, 122.65),
    "Guimaras": (10.60, 122.60), "Iloilo": (10.85, 122.55),
    # NIR
    "Negros Occidental": (10.20, 122.95), "Negros Oriental": (9.60, 123.15),
    # Region VII
    "Bohol": (9.85, 124.05), "Cebu": (10.30, 123.88), "Siquijor": (9.20, 123.50),
    # Region VIII
    "Biliran": (11.52, 124.45), "Eastern Samar": (11.50, 125.50),
    "Leyte": (10.90, 124.85), "Northern Samar": (12.30, 124.50),
    "Samar": (11.80, 124.95), "Southern Leyte": (10.15, 125.15),
    # Region IX
    "Zamboanga del Norte": (8.30, 123.10), "Zamboanga del Sur": (7.85, 123.25),
    "Zamboanga Sibugay": (7.65, 122.70),
    # Region X
    "Bukidnon": (8.15, 125.05), "Camiguin": (9.17, 124.72),
    "Lanao del Norte": (8.10, 124.15), "Misamis Occidental": (8.25, 123.80),
    "Misamis Oriental": (8.50, 124.65),
    # Region XI
    "Davao de Oro": (7.60, 126.05), "Davao del Norte": (7.45, 125.75),
    "Davao del Sur": (6.95, 125.40), "Davao Occidental": (6.25, 125.70),
    "Davao Oriental": (7.10, 126.30),
    # Region XII
    "Cotabato": (7.15, 124.95), "Sarangani": (5.95, 125.30),
    "South Cotabato": (6.35, 124.95), "Sultan Kudarat": (6.50, 124.45),
    # Region XIII
    "Agusan del Norte": (8.95, 125.55), "Agusan del Sur": (8.50, 125.90),
    "Dinagat Islands": (10.10, 125.60), "Surigao del Norte": (9.75, 125.50),
    "Surigao del Sur": (8.50, 126.15),
    # BARMM
    "Basilan": (6.65, 122.00), "Lanao del Sur": (7.85, 124.40),
    "Maguindanao del Norte": (7.30, 124.35), "Maguindanao del Sur": (6.95, 124.40),
    "Sulu": (6.05, 121.00), "Tawi-Tawi": (5.10, 119.85),
}

# ── Coastal provinces ──────────────────────────────────────────────────────
COASTAL_PROVINCES = {
    "NCR First District", "NCR Fourth District", "Bataan", "Zambales",
    "Pangasinan", "La Union", "Ilocos Norte", "Ilocos Sur", "Cagayan",
    "Batanes", "Aurora",
    "Batangas", "Cavite", "Quezon",
    "Albay", "Camarines Sur", "Camarines Norte", "Catanduanes",
    "Sorsogon", "Masbate", "Marinduque", "Romblon",
    "Occidental Mindoro", "Oriental Mindoro", "Palawan",
    "Aklan", "Antique", "Capiz", "Guimaras", "Iloilo",
    "Negros Occidental", "Negros Oriental",
    "Cebu", "Bohol", "Siquijor",
    "Biliran", "Eastern Samar", "Leyte", "Northern Samar", "Samar", "Southern Leyte",
    "Zamboanga del Norte", "Zamboanga del Sur", "Zamboanga Sibugay",
    "Basilan", "Sulu", "Tawi-Tawi",
    "Misamis Oriental", "Misamis Occidental", "Camiguin", "Lanao del Norte",
    "Davao del Sur", "Davao del Norte", "Davao Oriental", "Davao Occidental",
    "South Cotabato", "Sarangani",
    "Agusan del Norte", "Surigao del Norte", "Surigao del Sur", "Dinagat Islands",
}

TYPHOON_REGIONS = {"Region I", "Region II", "Region III", "Region IV-A", "Region V",
                   "Region VIII", "CAR", "NCR", "Region IV-B"}

EQ_REGIONS = {"Region VII", "Region X", "Region XI", "Region XII", "BARMM",
              "Region VIII", "CAR", "Region V"}

POVERTY_BY_REGION = {
    "NCR": 0.04, "CAR": 0.14, "Region I": 0.12, "Region II": 0.13,
    "Region III": 0.08, "Region IV-A": 0.06, "Region IV-B": 0.20,
    "Region V": 0.25, "Region VI": 0.18, "NIR": 0.19,
    "Region VII": 0.19, "Region VIII": 0.27, "Region IX": 0.28,
    "Region X": 0.25, "Region XI": 0.17, "Region XII": 0.30,
    "Region XIII": 0.26, "BARMM": 0.45,
}


def is_region_row(name: str) -> bool:
    name_upper = name.upper()
    for pattern in REGION_PATTERNS:
        if name_upper.startswith(pattern):
            return True
    return False


def is_province_row(name: str) -> bool:
    return name.upper() in {p.upper() for p in PROVINCES if isinstance(p, str)}


def get_region_name(raw: str) -> str:
    for key, val in REGION_MAP.items():
        if raw.strip().upper() == key.upper():
            return val
    # Fallback
    return raw.strip()


def title_clean(name: str) -> str:
    """Convert 'CITY OF MANILA' → 'Manila' or 'CITY OF CEBU' → 'Cebu City'."""
    name = name.strip()
    # Handle "CITY OF X" → "X City"
    m = re.match(r"CITY OF (.+)", name, re.IGNORECASE)
    if m:
        return m.group(1).title() + " City"
    return name.title()


def province_title(name: str) -> str:
    """Clean province name: 'ILOCOS NORTE' → 'Ilocos Norte'."""
    return name.strip().title()


def generate_pcode(region: str, province: str, idx: int) -> str:
    """Generate a PSGC-like code. Not official but unique and sortable."""
    # Use a hash-based approach for consistency
    key = f"{region}_{province}_{idx}"
    h = hash(key) % 999999999
    return f"PH{h:09d}000"


def estimate_flood(region, is_coast):
    if region in TYPHOON_REGIONS:
        return "high" if is_coast else "medium"
    return "medium" if is_coast else "low"


def estimate_eq(region):
    return "high" if region in EQ_REGIONS else "medium"


def compute_risk(pop, poverty, coastal, flood, eq):
    pop_f = min(pop / 2_000_000, 1.0) * 0.25
    pov_f = poverty * 0.20
    coast_f = coastal * 0.15
    flood_f = {"low": 0, "medium": 0.5, "high": 1}.get(flood, 0.5) * 0.20
    eq_f = {"low": 0, "medium": 0.5, "high": 1}.get(eq, 0.5) * 0.20
    return round(min(max(pop_f + pov_f + coast_f + flood_f + eq_f, 0.05), 0.99), 4)


def parse_and_generate():
    random.seed(42)

    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows_raw = list(reader)

    current_region = ""
    current_province = ""
    cities = []
    city_idx = 0

    for row in rows_raw:
        name = row["REGION_PROVINCE_CITY_MUNICIPALITY"].strip()
        pop_2024 = row.get("POP_2024", "0").replace(",", "").strip()

        # Skip empty or invalid
        if not name or not pop_2024:
            continue

        try:
            pop = int(float(pop_2024))
        except (ValueError, TypeError):
            continue

        # Check if this is a region header
        if is_region_row(name):
            current_region = get_region_name(name)
            continue

        # Check if this is a province header
        if is_province_row(name):
            current_province = province_title(name)
            continue

        # NCR special case — cities are directly under region
        if current_region == "NCR" and current_province == "":
            current_province = "Metro Manila"

        # This is a city/municipality row
        city_name = title_clean(name)
        city_idx += 1

        # Get coordinates (from province centroid + small random offset)
        prov_key = current_province
        base_lat, base_lon = PROVINCE_COORDS.get(prov_key, (12.0, 122.0))
        lat = round(base_lat + random.uniform(-0.15, 0.15), 6)
        lon = round(base_lon + random.uniform(-0.15, 0.15), 6)

        # Is coastal?
        coastal = 1 if current_province in COASTAL_PROVINCES else 0

        # Poverty
        poverty = POVERTY_BY_REGION.get(current_region, 0.20)
        poverty = round(min(max(poverty + random.uniform(-0.05, 0.05), 0.01), 0.60), 4)

        # Risk factors
        flood = estimate_flood(current_region, coastal)
        eq = estimate_eq(current_region)

        # Households
        households = max(1, int(pop / 4.1))

        # Risk score
        risk = compute_risk(pop, poverty, coastal, flood, eq)

        # Generate unique pcode
        pcode = generate_pcode(current_region, current_province, city_idx)

        cities.append({
            "pcode": pcode,
            "name": city_name,
            "province": current_province,
            "region": current_region,
            "latitude": lat,
            "longitude": lon,
            "population": pop,
            "households": households,
            "poverty_pct": poverty,
            "is_coastal": coastal,
            "flood_zone": flood,
            "eq_zone": eq,
            "risk_score": risk,
        })

    # Write output CSV
    fieldnames = [
        "pcode", "name", "province", "region", "latitude", "longitude",
        "population", "households", "poverty_pct", "is_coastal",
        "flood_zone", "eq_zone", "risk_score",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cities)

    print(f"✅ Parsed {len(cities)} cities/municipalities")
    print(f"   Regions found: {len(set(c['region'] for c in cities))}")
    print(f"   Provinces found: {len(set(c['province'] for c in cities))}")
    print(f"   Output: {OUTPUT_CSV}")


if __name__ == "__main__":
    parse_and_generate()
