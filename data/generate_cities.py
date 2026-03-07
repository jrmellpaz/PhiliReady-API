import csv
import json
import os
import random
import pandas as pd
from difflib import get_close_matches

# ── Risk estimation helpers ─────────────────────────────────────────────────
# Regions most exposed to typhoons
TYPHOON_REGIONS = {"Region I", "Region II", "Region III", "Region IV-A", "Region V",
                   "Region VIII", "CAR", "NCR", "Region IV-B"}

# Regions with significant earthquake risk
EQ_REGIONS = {"Region VII", "Region X", "Region XI", "Region XII", "BARMM",
              "Region VIII", "CAR", "Region V"}

# Coastal provinces (approximate list for random assignment fallback)
COASTAL_PROVINCES = {
    "NCR First District", "NCR Fourth District", "Bataan", "Zambales",
    "Pangasinan", "La Union", "Ilocos Norte", "Ilocos Sur", "Cagayan",
    "Batangas", "Cavite", "Quezon", "Camarines Sur", "Camarines Norte",
    "Albay", "Sorsogon", "Masbate", "Capiz", "Iloilo", "Negros Occidental",
    "Cebu", "Bohol", "Negros Oriental", "Siquijor", "Leyte", "Samar",
    "Eastern Samar", "Zamboanga del Sur", "Zamboanga del Norte", "Basilan",
    "Misamis Oriental", "Misamis Occidental", "Lanao del Norte",
    "Davao del Sur", "Davao del Norte", "Davao Oriental",
    "South Cotabato", "Surigao del Norte", "Surigao del Sur",
    "Agusan del Norte", "Sulu", "Tawi-Tawi", "Palawan",
    "Oriental Mindoro",
}

# Provincial poverty incidence (PSA 2021 SAE approximations)
POVERTY_BY_REGION = {
    "NCR": 0.04, "CAR": 0.14, "Region I": 0.12, "Region II": 0.13,
    "Region III": 0.08, "Region IV-A": 0.06, "Region IV-B": 0.20,
    "Region V": 0.25, "Region VI": 0.18, "Region VII": 0.19,
    "Region VIII": 0.27, "Region IX": 0.28, "Region X": 0.25,
    "Region XI": 0.17, "Region XII": 0.30, "Region XIII": 0.26,
    "BARMM": 0.45,
}

NAME_ALIASES = {
    'BALIWAG': 'BALIUAG',
    'STO TOMAS': 'SANTO TOMAS',
    'PIO V CORPUS': 'PIO V CORPUZ',
    'PRESIDENT CARLOS P GARCIA': 'PRES CARLOS P GARCIA',
    'PINAMUNGAJAN': 'PINAMUNGAHAN',
    'OZAMIZ': 'OZAMIS',
    'LEON T POSTIGO': 'BACUNGAN',
    'AMAI MANABILANG': 'BUMBARAN',
}

def estimate_households(pop):
    """Estimate households from population using national avg household size (approx 4.1)."""
    return max(1, int(pop / 4.1))

def is_coastal(province):
    return 1 if province in COASTAL_PROVINCES else 0

def estimate_flood_zone(region, is_coast):
    if region in TYPHOON_REGIONS:
        return "high" if is_coast else "medium"
    return "medium" if is_coast else "low"

def estimate_eq_zone(region):
    return "high" if region in EQ_REGIONS else "medium"

def compute_risk_score(pop, poverty, coastal, flood, eq):
    """Composite risk score 0–1."""
    pop_factor = min(pop / 2000000, 1.0) * 0.25
    pov_factor = poverty * 0.20
    coast_factor = coastal * 0.15
    flood_factor = {"low": 0.0, "medium": 0.5, "high": 1.0}.get(flood, 0.5) * 0.20
    eq_factor = {"low": 0.0, "medium": 0.5, "high": 1.0}.get(eq, 0.5) * 0.20
    score = pop_factor + pov_factor + coast_factor + flood_factor + eq_factor
    return round(min(max(score, 0.05), 0.99), 4)

def clean_name(name):
    if not isinstance(name, str): return ''
    name = name.upper()
    name = name.replace('CITY OF ', '')
    name = name.replace(' CITY', '')
    name = name.replace('MUNICIPALITY OF ', '')
    name = name.replace(' (CAPITAL)', '')
    name = name.replace('Ñ', 'N')
    name = name.replace('-', ' ')
    name = name.replace('.', '')
    name = ' '.join(name.split())
    return NAME_ALIASES.get(name.strip(), name.strip())


def iter_coordinate_pairs(coordinates):
    if not isinstance(coordinates, list):
        return

    if len(coordinates) >= 2 and all(isinstance(value, (int, float)) for value in coordinates[:2]):
        yield coordinates[:2]
        return

    for item in coordinates:
        yield from iter_coordinate_pairs(item)


def compute_feature_centroid(geometry):
    geometry = geometry or {}
    pairs = list(iter_coordinate_pairs(geometry.get('coordinates', [])))
    if not pairs:
        return 0.0, 0.0

    lon = sum(pair[0] for pair in pairs) / len(pairs)
    lat = sum(pair[1] for pair in pairs) / len(pairs)
    return round(lat, 6), round(lon, 6)


def load_municity_reference(reference_path):
    with open(reference_path, 'r', encoding='utf-8') as f:
        payload = json.load(f)

    mapping = {}
    for feature in payload.get('features', []):
        props = feature.get('properties', {})
        name = props.get('ADM3_EN')
        if not name:
            continue

        clean = clean_name(name)
        lat, lon = compute_feature_centroid(feature.get('geometry', {}))
        entry = {
            'pcode': props.get('ADM3_PCODE'),
            'name': name.strip(),
            'province': props.get('ADM2_EN', 'Unknown Province'),
            'region': props.get('ADM1_EN', 'Unknown Region'),
            'latitude': lat,
            'longitude': lon,
        }

        for alias_name in (props.get('ADM3_EN'), props.get('ADM3ALT1EN'), props.get('ADM3ALT2EN')):
            clean_alias = clean_name(alias_name)
            if clean_alias:
                mapping.setdefault(clean_alias, []).append(entry)

    return mapping

def generate_csv():
    output_dir = os.path.join(os.path.dirname(__file__))
    os.makedirs(output_dir, exist_ok=True)
    
    psgc_path = os.path.join(output_dir, "PH_Adm3_MuniCities.csv")
    pop_path = os.path.join(os.path.dirname(output_dir), "references", "population_by_region_combined.csv")
    reference_path = os.path.join(os.path.dirname(output_dir), "references", "municities.json")
    output_path = os.path.join(output_dir, "psgc_cities.csv")

    if not os.path.exists(psgc_path):
        print(f"❌ Missing {psgc_path}. Please download the official PSGC CSV first.")
        return 0

    if not os.path.exists(reference_path):
        print(f"❌ Missing {reference_path}. Please add the municipality GeoJSON reference first.")
        return 0

    print("Loading data...")
    df_psgc = pd.read_csv(psgc_path)
    df_pop = pd.read_csv(pop_path)
    reference_mapping = load_municity_reference(reference_path)

    # Clean names for matching
    df_pop['clean_name'] = df_pop['REGION_PROVINCE_CITY_MUNICIPALITY'].apply(clean_name)
    df_psgc['clean_name'] = df_psgc['adm3_en'].apply(clean_name)

    # Dictionary of population by clean name
    # Average of duplicate names goes into dict (since some barangay/municipality names overlap)
    pop_dict = df_pop.groupby('clean_name')['POP_2020'].mean().to_dict()

    fieldnames = [
        "pcode", "name", "province", "region", "latitude", "longitude",
        "population", "households", "poverty_pct", "is_coastal",
        "flood_zone", "eq_zone", "risk_score",
    ]

    rows = []
    seen_pcodes = set()
    matched_counts = {}
    mapped = 0
    fuzzy_mapped = 0
    unmapped = 0
    skipped_reference = 0

    print("Matching and generating records...")
    for _, row in df_psgc.iterrows():
        source_name = row['adm3_en']
        clean_n = row['clean_name']
        match_index = matched_counts.get(clean_n, 0)
        matched_counts[clean_n] = match_index + 1
        reference_rows = reference_mapping.get(clean_n, [])
        reference = reference_rows[match_index] if match_index < len(reference_rows) else None

        if not reference or not reference.get('pcode'):
            skipped_reference += 1
            continue

        pcode = reference['pcode']
        if pcode in seen_pcodes:
            continue
        seen_pcodes.add(pcode)

        name = reference['name'] if reference.get('name') else source_name
        
        # Try to find population
        pop = 50000  # fallback
        if clean_n in pop_dict:
            pop = int(pop_dict[clean_n])
            mapped += 1
        else:
            close = get_close_matches(clean_n, pop_dict.keys(), n=1, cutoff=0.85)
            if close:
                pop = int(pop_dict[close[0]])
                fuzzy_mapped += 1
            else:
                unmapped += 1
                # Fallback pop based on whether it is a city or municipality
                if row.get('geo_level') == 'City':
                    pop = 150000
                elif row.get('geo_level') == 'Mun':
                    pop = 35000

        region = reference['region'] if reference.get('region') else random.choice(list(POVERTY_BY_REGION.keys()))
        province = reference['province'] if reference.get('province') else "Prov_" + str(row.get('adm2_psgc', '000'))
        lat = reference['latitude']
        lon = reference['longitude']

        coastal = is_coastal(province)
        poverty = POVERTY_BY_REGION.get(region, 0.20)
        poverty = round(min(max(poverty + random.uniform(-0.05, 0.05), 0.01), 0.60), 4)
        flood = estimate_flood_zone(region, coastal)
        eq = estimate_eq_zone(region)
        hh = estimate_households(pop)
        risk = compute_risk_score(pop, poverty, coastal, flood, eq)

        rows.append({
            "pcode": pcode,
            "name": name,
            "province": province,
            "region": region,
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "population": pop,
            "households": hh,
            "poverty_pct": poverty,
            "is_coastal": coastal,
            "flood_zone": flood,
            "eq_zone": eq,
            "risk_score": risk,
        })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} cities to {output_path}")
    print(f"Stats: {mapped} exact matches, {fuzzy_mapped} fuzzy matches, {unmapped} fallbacks, {skipped_reference} skipped not in reference.")
    return len(rows)

if __name__ == "__main__":
    random.seed(42)
    generate_csv()
