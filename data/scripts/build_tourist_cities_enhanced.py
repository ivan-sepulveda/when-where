"""
Builds data/processed/tourist_cities_enhanced.json: every city from
data/reference/tourist_cities.json (3,069 cities), enriched with UNESCO
World Heritage Site density and Michelin restaurant density computed
directly from each source's own lat/lng -- not the country-level totals
in UNESCO_SCORE_BY_COUNTRY.csv / MICHELIN_SCORE_BY_COUNTRY.csv, which
collapse an entire country (the US, China, Brazil, ...) into one number.
A city like Kyoto or Paris gets its own "how much of this is actually
nearby" signal instead of inheriting its whole country's total.

For each city, at each of RADII_KM (5, 10, 25, 50, 100 km -- cumulative,
not banded: "within_10km" includes everything already counted in
"within_5km", it isn't a 5-10km ring), records a count, plus one shared
nearest-first list (capped at max(RADII_KM) = 100km) rather than a
separate list per radius:
  - unesco_sites: {"counts": {"within_<r>km": N, ...}, "sites":
    [{name, category, distance_km}, ...]}
  - michelin_restaurants: {"counts": {"within_<r>km": N, ...},
    "restaurants": [{name, award, cuisine, distance_km}, ...]}
Each entry carries its own distance_km, so which radius bucket(s) it
belongs to is derivable without needing the entry duplicated once per
bucket -- an earlier version of this script stored a full copy of every
matching site/restaurant in every radius list it qualified for (a site
3km away appeared in all 5 buckets at once), which produced a 60MB file
for no informational gain over this ~5x-smaller shape. All of the
city's original fields (city, country, iso2, lat, lng, population, ...)
are carried through unchanged alongside the two new keys.

Distance is straight-line great-circle (haversine) distance between the
city's (lat, lng) and each site/restaurant's (lat, lng) -- same formula
and Earth-radius constant as distance_calculator.calculate_distance(),
just reimplemented in vectorized numpy instead of calling that function
in a python-level loop, since this is ~3,069 cities x (1,273 UNESCO
sites + 19,399 Michelin restaurants) ~= 63M point-pairs. Results are
identical to what calculate_distance() would return for the same pair;
only the implementation differs, for speed.

Sources:
  - Cities: data/reference/tourist_cities.json.
  - UNESCO: data/processed/multiple/unesco_world_heritage_sites.json --
    29 of 1,273 sites have no coordinates in the source (see that file's
    own `sites_missing_coordinates`) and are excluded from every city's
    radius calculation (can't compute a distance to nowhere); the count
    excluded is reported in this script's output and console summary.
  - Michelin: data/processed/multiple/michelin_restaurants.csv -- all
    19,399 rows have coordinates, none excluded.

Coverage caveat worth keeping in mind downstream: Michelin's own guide
coverage is geographically lopsided (concentrated in Europe, East Asia,
and a handful of major cities elsewhere -- see
diff_michelin_vs_tourist_cities.py /
processed/michelin_cities_missing_from_tourist_cities.csv). A 0 here
often reflects the guide's own coverage gap as much as it reflects the
destination. UNESCO's site list, by contrast, is genuinely global, so a
0 there is a more trustworthy "nothing nearby" signal.

Usage:
    python build_tourist_cities_enhanced.py
"""

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

RADII_KM = [5, 10, 25, 50, 100]

# Mean Earth radius (IUGG value) -- same constant distance_calculator.py
# uses, kept in sync here so the vectorized formula below returns
# distances identical to calculate_distance().
EARTH_RADIUS_KM = 6371.0088

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
MULTIPLE_DIR = PROCESSED_DIR / "multiple"

TOURIST_CITIES_PATH = REFERENCE_DIR / "tourist_cities.json"
UNESCO_SITES_PATH = MULTIPLE_DIR / "unesco_world_heritage_sites.json"
MICHELIN_CSV_PATH = MULTIPLE_DIR / "michelin_restaurants.csv"
OUTPUT_PATH = PROCESSED_DIR / "tourist_cities_enhanced.json"

# ---------------------------------------------------------------------------


def load_cities() -> list[dict]:
    if not TOURIST_CITIES_PATH.exists():
        raise FileNotFoundError(f"{TOURIST_CITIES_PATH} not found -- run fetch_tourist_cities.py first.")
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        return json.load(f)["cities"]


def load_unesco_sites() -> tuple[list[dict], int]:
    """Returns (sites_with_coordinates, sites_missing_coordinates_count).
    Each returned site is {name, category, lat, lng}."""
    if not UNESCO_SITES_PATH.exists():
        raise FileNotFoundError(
            f"{UNESCO_SITES_PATH} not found -- run fetch_unesco_world_heritage_sites.py first."
        )
    with open(UNESCO_SITES_PATH, encoding="utf-8") as f:
        data = json.load(f)

    sites, missing = [], 0
    for s in data["sites"]:
        if s.get("lat") is None or s.get("lng") is None:
            missing += 1
            continue
        sites.append({"name": s.get("name_en"), "category": s.get("category"), "lat": s["lat"], "lng": s["lng"]})
    return sites, missing


def load_michelin_restaurants() -> tuple[list[dict], int]:
    """Returns (restaurants_with_coordinates, restaurants_missing_coordinates_count).
    Each returned restaurant is {name, award, cuisine, lat, lng}."""
    if not MICHELIN_CSV_PATH.exists():
        raise FileNotFoundError(f"{MICHELIN_CSV_PATH} not found -- run fetch_michelin_restaurants.py first.")

    restaurants, missing = [], 0
    with open(MICHELIN_CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lat, lng = row.get("Latitude"), row.get("Longitude")
            if not lat or not lng:
                missing += 1
                continue
            restaurants.append(
                {
                    "name": row["Name"],
                    "award": row["Award"],
                    "cuisine": row.get("Cuisine") or None,
                    "lat": float(lat),
                    "lng": float(lng),
                }
            )
    return restaurants, missing


def haversine_km(lat1: np.ndarray, lng1: np.ndarray, lat2: float, lng2: float) -> np.ndarray:
    """Vectorized great-circle distance from many (lat1, lng1) points to one
    (lat2, lng2) point, in km -- same formula/constant as
    distance_calculator.calculate_distance(), reimplemented in numpy
    purely for speed across ~63M point-pairs (a python-level loop calling
    calculate_distance() once per pair would be far slower for a dataset
    this size)."""
    lat1r, lng1r, lat2r, lng2r = np.radians(lat1), np.radians(lng1), np.radians(lat2), np.radians(lng2)
    dlat = lat2r - lat1r
    dlng = lng2r - lng1r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlng / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


def nearby_by_radius(distances_km: np.ndarray, items: list[dict], extra_fields: list[str], list_key: str) -> dict:
    """Builds {"counts": {"within_5km": N, ...}, list_key: [...]} for one
    city against one source (UNESCO sites or Michelin restaurants), given
    that source's precomputed distances from this city.

    The list is stored once -- nearest-first, capped at max(RADII_KM) --
    rather than once per radius. Cumulative radii mean a site 3km away
    belongs to every one of the 5/10/25/50/100km buckets at once; an
    earlier version of this script stored a full copy of each matching
    entry in every bucket it qualified for, which made the output ~5x
    larger than it needed to be for no informational gain (each entry
    already carries its own distance_km, so which buckets it belongs to
    is derivable, not something that needs restating per bucket). Counts
    per radius are kept as their own small dict so "how many within
    25km" is still a single lookup, not something that requires
    filtering the list at read time.

    Sorts once, then uses searchsorted to find each radius's cutoff in
    the sorted array (O(log n) per radius) rather than re-filtering the
    full array once per radius."""
    order = np.argsort(distances_km)
    sorted_distances = distances_km[order]
    max_radius = max(RADII_KM)

    counts = {}
    for radius in RADII_KM:
        cutoff = int(np.searchsorted(sorted_distances, radius, side="right"))
        counts[f"within_{radius}km"] = cutoff

    list_cutoff = int(np.searchsorted(sorted_distances, max_radius, side="right"))
    entries = []
    for i in order[:list_cutoff]:
        entry = {"name": items[i]["name"]}
        for field in extra_fields:
            entry[field] = items[i][field]
        entry["distance_km"] = round(float(distances_km[i]), 1)
        entries.append(entry)

    return {"counts": counts, list_key: entries}


def build_enhanced_cities(cities: list[dict], unesco_sites: list[dict], michelin_restaurants: list[dict]) -> list[dict]:
    unesco_lat = np.array([s["lat"] for s in unesco_sites])
    unesco_lng = np.array([s["lng"] for s in unesco_sites])
    michelin_lat = np.array([r["lat"] for r in michelin_restaurants])
    michelin_lng = np.array([r["lng"] for r in michelin_restaurants])

    enhanced = []
    for city in cities:
        city_lat, city_lng = city["lat"], city["lng"]

        unesco_dist = haversine_km(unesco_lat, unesco_lng, city_lat, city_lng)
        michelin_dist = haversine_km(michelin_lat, michelin_lng, city_lat, city_lng)

        enriched = dict(city)
        enriched["unesco_sites"] = nearby_by_radius(unesco_dist, unesco_sites, ["category"], "sites")
        enriched["michelin_restaurants"] = nearby_by_radius(
            michelin_dist, michelin_restaurants, ["award", "cuisine"], "restaurants"
        )
        enhanced.append(enriched)
    return enhanced


def main():
    start = time.time()

    cities = load_cities()
    unesco_sites, unesco_missing = load_unesco_sites()
    michelin_restaurants, michelin_missing = load_michelin_restaurants()

    enhanced = build_enhanced_cities(cities, unesco_sites, michelin_restaurants)

    dataset = {
        "source": (
            "Derived from data/reference/tourist_cities.json (cities), "
            "data/processed/multiple/unesco_world_heritage_sites.json (UNESCO sites), and "
            "data/processed/multiple/michelin_restaurants.csv (Michelin restaurants) "
            "via build_tourist_cities_enhanced.py -- see data/SCORING.md"
        ),
        "generated": datetime.now(timezone.utc).date().isoformat(),
        "radii_km": RADII_KM,
        "note": (
            'Each radius is cumulative ("within_10km" includes everything in '
            '"within_5km", not a 5-10km band). Each city\'s "sites"/"restaurants" list is '
            "stored once (nearest-first, capped at max(radii_km)), not once per radius -- "
            "use each entry's distance_km against radii_km to see which bucket(s) it "
            'falls in, or just read the matching count in "counts". Distance is '
            "straight-line great-circle distance from the city's own lat/lng, same "
            "formula as distance_calculator.calculate_distance."
        ),
        "total_cities": len(enhanced),
        "total_unesco_sites_used": len(unesco_sites),
        "unesco_sites_missing_coordinates_excluded": unesco_missing,
        "total_michelin_restaurants_used": len(michelin_restaurants),
        "michelin_restaurants_missing_coordinates_excluded": michelin_missing,
        "cities": enhanced,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    elapsed = time.time() - start
    max_radius_key = f"within_{max(RADII_KM)}km"
    max_unesco_city = max(enhanced, key=lambda c: c["unesco_sites"]["counts"][max_radius_key])
    max_michelin_city = max(enhanced, key=lambda c: c["michelin_restaurants"]["counts"][max_radius_key])
    zero_both_100km = sum(
        1
        for c in enhanced
        if c["unesco_sites"]["counts"][max_radius_key] == 0 and c["michelin_restaurants"]["counts"][max_radius_key] == 0
    )

    print(
        f"[tourist_cities_enhanced] {len(enhanced)} cities x {len(unesco_sites)} UNESCO sites x "
        f"{len(michelin_restaurants)} Michelin restaurants, radii {RADII_KM} -> {OUTPUT_PATH} ({elapsed:.1f}s)"
    )
    print(
        f"[tourist_cities_enhanced] most UNESCO sites within {max(RADII_KM)}km: {max_unesco_city['city']}, "
        f"{max_unesco_city['country']} ({max_unesco_city['unesco_sites']['counts'][max_radius_key]})"
    )
    print(
        f"[tourist_cities_enhanced] most Michelin restaurants within {max(RADII_KM)}km: {max_michelin_city['city']}, "
        f"{max_michelin_city['country']} ({max_michelin_city['michelin_restaurants']['counts'][max_radius_key]})"
    )
    print(f"[tourist_cities_enhanced] {zero_both_100km} cities with zero of both within {max(RADII_KM)}km")
    if unesco_missing:
        print(f"[tourist_cities_enhanced] NOTE: {unesco_missing} UNESCO site(s) excluded (missing coordinates)")


if __name__ == "__main__":
    main()
