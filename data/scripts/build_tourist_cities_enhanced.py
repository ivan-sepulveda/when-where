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

Also adds `airports`: every airport within AIRPORT_RADIUS_KM (100km,
one flat radius, not the 5/10/25/50/100 tiers above -- a much wider net
than makes sense for UNESCO sites or restaurants, since travelers
routinely fly into an airport 60-90km from where they're actually
going, e.g. Ontario (ONT) for Los Angeles or Southend (SEN) for
London), sorted nearest-first as {count, airports: [{iata, name,
country, distance_km}, ...]}. Filtered down from
data/reference/airports.json's full 7,698 airports two ways:
  1. Must have an IATA code -- drops entries with only an ICAO code or
     no code at all (the ones OpenFlights carries for tiny airfields
     with no commercial identity).
  2. Must appear as a Departure or Destination at least once in
     data/processed/multiple/airline_routes.csv -- drops general-
     aviation and military fields that happen to sit within range but
     that no traveler would fly into (a raw within-100km query returns
     22 airports for Los Angeles and 24 for London, including things
     like Santa Monica Municipal, Van Nuys, RAF Northolt, and Biggin
     Hill; filtering to scheduled-service airports brings that down to
     7 and 7). Both counts are still a little wider than what most
     people would name off the top of their head (Chino, Riverside
     Municipal, Cambridge) -- these are real small commercial fields
     within range, not noise, just not household names.
Note airline_routes.csv is itself an OpenFlights snapshot, not a live
schedule -- "has a route in this dataset" means "had scheduled service
as of whenever that snapshot was taken," not "has service today."

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

# Flat radius for airports -- deliberately not one of RADII_KM's tiers,
# see the airports section of this file's docstring for why 100km alone
# (not 5/10/25/50km too) is the right net for "which airports serve this
# city," unlike UNESCO sites/restaurants.
AIRPORT_RADIUS_KM = 100

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
AIRPORTS_JSON_PATH = REFERENCE_DIR / "airports.json"
AIRLINE_ROUTES_CSV_PATH = MULTIPLE_DIR / "airline_routes.csv"
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


def load_scheduled_service_iatas() -> set[str]:
    """IATA codes that appear as a Departure or Destination at least once
    in airline_routes.csv -- the "has scheduled service" filter used by
    load_airports() below."""
    if not AIRLINE_ROUTES_CSV_PATH.exists():
        raise FileNotFoundError(f"{AIRLINE_ROUTES_CSV_PATH} not found -- run fetch_airline_routes.py first.")
    served: set[str] = set()
    with open(AIRLINE_ROUTES_CSV_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            served.add(row["Departure"])
            served.add(row["Destination"])
    return served


def load_airports() -> tuple[list[dict], dict]:
    """Returns (airports_used, stats). Each returned airport is {iata,
    name, country, lat, lng}. An airport is used only if it has an IATA
    code AND has at least one scheduled route in airline_routes.csv --
    see this file's docstring for why (drops general-aviation/military
    fields OpenFlights otherwise mixes in with real commercial
    airports)."""
    if not AIRPORTS_JSON_PATH.exists():
        raise FileNotFoundError(f"{AIRPORTS_JSON_PATH} not found -- run fetch_openflights_airports.py first.")
    with open(AIRPORTS_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    served = load_scheduled_service_iatas()

    total = len(data["airports"])
    no_iata = 0
    no_scheduled_service = 0
    airports = []
    for a in data["airports"]:
        iata = a.get("iata")
        if not iata:
            no_iata += 1
            continue
        if iata not in served:
            no_scheduled_service += 1
            continue
        airports.append({"iata": iata, "name": a.get("name"), "country": a.get("country"), "lat": a["lat"], "lng": a["lng"]})

    stats = {
        "total_airports_in_source": total,
        "airports_excluded_no_iata_code": no_iata,
        "airports_excluded_no_scheduled_service": no_scheduled_service,
        "airports_used": len(airports),
    }
    return airports, stats


def load_all_airport_coords_unfiltered() -> np.ndarray:
    """Every airport in airports.json with coordinates, IATA code or not,
    scheduled service or not -- used only for the console diagnostic in
    main() that splits "zero airports within 100km" into "genuinely
    nothing nearby" vs. "something's there in the raw source but it got
    filtered out" (see that diagnostic for why this distinction matters:
    ~half of this project's zero-airport cities turned out to be the
    latter, e.g. Yinchuan's own airport exists in the source 18.8km away
    but has no IATA code at all -- a known OpenFlights coverage gap,
    concentrated in China)."""
    with open(AIRPORTS_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    coords = [(a["lat"], a["lng"]) for a in data["airports"] if a.get("lat") is not None and a.get("lng") is not None]
    return np.array(coords)


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


def nearby_airports(distances_km: np.ndarray, airports: list[dict]) -> dict:
    """Builds {"count": N, "airports": [...]} for one city -- a single
    flat AIRPORT_RADIUS_KM cutoff, not the tiered counts/list shape
    nearby_by_radius() builds for UNESCO sites/restaurants, since
    airports only need the one radius here (see this file's docstring)."""
    order = np.argsort(distances_km)
    sorted_distances = distances_km[order]
    cutoff = int(np.searchsorted(sorted_distances, AIRPORT_RADIUS_KM, side="right"))

    entries = []
    for i in order[:cutoff]:
        a = airports[i]
        entries.append(
            {
                "iata": a["iata"],
                "name": a["name"],
                "country": a["country"],
                "distance_km": round(float(distances_km[i]), 1),
            }
        )
    return {"count": len(entries), "airports": entries}


def build_enhanced_cities(
    cities: list[dict], unesco_sites: list[dict], michelin_restaurants: list[dict], airports: list[dict]
) -> list[dict]:
    unesco_lat = np.array([s["lat"] for s in unesco_sites])
    unesco_lng = np.array([s["lng"] for s in unesco_sites])
    michelin_lat = np.array([r["lat"] for r in michelin_restaurants])
    michelin_lng = np.array([r["lng"] for r in michelin_restaurants])
    airport_lat = np.array([a["lat"] for a in airports])
    airport_lng = np.array([a["lng"] for a in airports])

    enhanced = []
    for city in cities:
        city_lat, city_lng = city["lat"], city["lng"]

        unesco_dist = haversine_km(unesco_lat, unesco_lng, city_lat, city_lng)
        michelin_dist = haversine_km(michelin_lat, michelin_lng, city_lat, city_lng)
        airport_dist = haversine_km(airport_lat, airport_lng, city_lat, city_lng)

        enriched = dict(city)
        enriched["unesco_sites"] = nearby_by_radius(unesco_dist, unesco_sites, ["category"], "sites")
        enriched["michelin_restaurants"] = nearby_by_radius(
            michelin_dist, michelin_restaurants, ["award", "cuisine"], "restaurants"
        )
        enriched["airports"] = nearby_airports(airport_dist, airports)
        enhanced.append(enriched)
    return enhanced


def main():
    start = time.time()

    cities = load_cities()
    unesco_sites, unesco_missing = load_unesco_sites()
    michelin_restaurants, michelin_missing = load_michelin_restaurants()
    airports, airport_stats = load_airports()

    enhanced = build_enhanced_cities(cities, unesco_sites, michelin_restaurants, airports)

    dataset = {
        "source": (
            "Derived from data/reference/tourist_cities.json (cities), "
            "data/processed/multiple/unesco_world_heritage_sites.json (UNESCO sites), "
            "data/processed/multiple/michelin_restaurants.csv (Michelin restaurants), and "
            "data/reference/airports.json + data/processed/multiple/airline_routes.csv (airports) "
            "via build_tourist_cities_enhanced.py -- see data/SCORING.md"
        ),
        "generated": datetime.now(timezone.utc).date().isoformat(),
        "radii_km": RADII_KM,
        "airport_radius_km": AIRPORT_RADIUS_KM,
        "note": (
            'Each unesco_sites/michelin_restaurants radius is cumulative ("within_10km" '
            'includes everything in "within_5km", not a 5-10km band). Each city\'s '
            '"sites"/"restaurants" list is stored once (nearest-first, capped at '
            "max(radii_km)), not once per radius -- use each entry's distance_km against "
            'radii_km to see which bucket(s) it falls in, or just read the matching count '
            'in "counts". airports uses a single flat airport_radius_km cutoff instead '
            "(see this script's docstring for why) and is filtered to airports with an "
            "IATA code and at least one scheduled route in airline_routes.csv -- see "
            "airports_excluded_no_iata_code / airports_excluded_no_scheduled_service below "
            "for how many that dropped. Distance is straight-line great-circle distance "
            "from the city's own lat/lng, same formula as "
            "distance_calculator.calculate_distance."
        ),
        "total_cities": len(enhanced),
        "total_unesco_sites_used": len(unesco_sites),
        "unesco_sites_missing_coordinates_excluded": unesco_missing,
        "total_michelin_restaurants_used": len(michelin_restaurants),
        "michelin_restaurants_missing_coordinates_excluded": michelin_missing,
        "total_airports_used": airport_stats["airports_used"],
        "airports_excluded_no_iata_code": airport_stats["airports_excluded_no_iata_code"],
        "airports_excluded_no_scheduled_service": airport_stats["airports_excluded_no_scheduled_service"],
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

    max_airport_city = max(enhanced, key=lambda c: c["airports"]["count"])
    zero_airports = [c for c in enhanced if c["airports"]["count"] == 0]

    # Split the zero-airport cities into "genuinely nothing within 100km"
    # vs. "something's there in the raw source, just filtered out (no
    # IATA code / no scheduled route)" -- see load_all_airport_coords_unfiltered().
    all_airport_coords = load_all_airport_coords_unfiltered()
    zero_but_something_in_raw = 0
    for c in zero_airports:
        d = haversine_km(all_airport_coords[:, 0], all_airport_coords[:, 1], c["lat"], c["lng"])
        if (d <= AIRPORT_RADIUS_KM).any():
            zero_but_something_in_raw += 1

    print(
        f"[tourist_cities_enhanced] {len(enhanced)} cities x {len(unesco_sites)} UNESCO sites x "
        f"{len(michelin_restaurants)} Michelin restaurants x {len(airports)} airports, radii {RADII_KM} "
        f"(airports: {AIRPORT_RADIUS_KM}km) -> {OUTPUT_PATH} ({elapsed:.1f}s)"
    )
    print(
        f"[tourist_cities_enhanced] most UNESCO sites within {max(RADII_KM)}km: {max_unesco_city['city']}, "
        f"{max_unesco_city['country']} ({max_unesco_city['unesco_sites']['counts'][max_radius_key]})"
    )
    print(
        f"[tourist_cities_enhanced] most Michelin restaurants within {max(RADII_KM)}km: {max_michelin_city['city']}, "
        f"{max_michelin_city['country']} ({max_michelin_city['michelin_restaurants']['counts'][max_radius_key]})"
    )
    print(
        f"[tourist_cities_enhanced] most airports within {AIRPORT_RADIUS_KM}km: {max_airport_city['city']}, "
        f"{max_airport_city['country']} ({max_airport_city['airports']['count']})"
    )
    print(f"[tourist_cities_enhanced] {zero_both_100km} cities with zero UNESCO sites and zero Michelin restaurants within {max(RADII_KM)}km")
    print(
        f"[tourist_cities_enhanced] {len(zero_airports)} cities with zero scheduled-service airports within "
        f"{AIRPORT_RADIUS_KM}km -- {zero_but_something_in_raw} of those DO have an airport in the raw source "
        f"nearby, just filtered out (no IATA code or no scheduled route); {len(zero_airports) - zero_but_something_in_raw} "
        f"have nothing in the raw source either"
    )
    if unesco_missing:
        print(f"[tourist_cities_enhanced] NOTE: {unesco_missing} UNESCO site(s) excluded (missing coordinates)")
    print(
        f"[tourist_cities_enhanced] NOTE: {airport_stats['airports_excluded_no_iata_code']} airport(s) excluded "
        f"(no IATA code), {airport_stats['airports_excluded_no_scheduled_service']} excluded (no scheduled route "
        f"in airline_routes.csv)"
    )


if __name__ == "__main__":
    main()
