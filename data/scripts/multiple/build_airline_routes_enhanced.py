"""
Derived from: data/processed/multiple/airline_routes.csv (built by fetch_airline_routes.py)
              data/reference/airport_coordinates.json (built by build_airports_coordinates_map.py)
              data/reference/airports.json (built by fetch_openflights_airports.py)
              data/reference/country_aliases.json (built by build_country_aliases.py)

Adds four columns to airline_routes.csv: distance_km, distance_mi
(computed via distance_calculator.calculate_distance() from each route's
Departure/Destination IATA codes looked up in airport_coordinates.json),
country_pair (the ISO2 codes of the two countries the route connects),
and is_domestic (1/0, derived straight from country_pair -- see
add_country_pairs() below). Writes
data/processed/multiple/airline_routes_enhanced.csv (original columns
unchanged, four new ones appended).

A route whose Departure or Destination code isn't in
airport_coordinates.json (a real gap -- as of this writing, 273 of the
~4,000 distinct codes referenced in airline_routes.csv aren't in
airports.json/airport_coordinates.json, likely airports OpenFlights
doesn't carry as type "airport", or doesn't carry at all) gets blank
distance_km/distance_mi rather than being dropped from the output --
counted and reported at the end. Same treatment for country_pair and
is_domestic when a code doesn't resolve to a known country.

Usage:
    python build_airline_routes_enhanced.py
"""

import csv
import json
import sys
from pathlib import Path

# distance_calculator.py and country_lookup.py live in data/scripts/, not
# alongside this script (data/scripts/multiple/) -- only a script's own
# directory is added to sys.path automatically, so the parent has to be
# added by hand.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from country_lookup import normalize_airport_country  # noqa: E402
from distance_calculator import calculate_distance  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
ROUTES_PATH = PROCESSED_DIR / "airline_routes.csv"
COORDINATES_PATH = REFERENCE_DIR / "airport_coordinates.json"
AIRPORTS_PATH = REFERENCE_DIR / "airports.json"
ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
OUT_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"


def load_routes() -> tuple[list[dict], list[str]]:
    if not ROUTES_PATH.exists():
        raise FileNotFoundError(f"{ROUTES_PATH} not found -- run fetch_airline_routes.py first.")
    with open(ROUTES_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), reader.fieldnames


def load_coordinates() -> dict:
    if not COORDINATES_PATH.exists():
        raise FileNotFoundError(
            f"{COORDINATES_PATH} not found -- run build_airports_coordinates_map.py first."
        )
    with open(COORDINATES_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_iata_to_country() -> dict[str, str]:
    """IATA code -> ISO2 country code, built by resolving each
    airports.json airport's IATA code + raw `country` name string (e.g.
    "United States") through country_lookup.normalize_airport_country()
    (which also handles Netherlands Antilles' old-name split across
    Bonaire/Sint Eustatius/Saba, Curaçao, and Sint Maarten via
    IATA_COUNTRY_OVERRIDES) and country_aliases.json's iso3->iso2
    mapping -- the same resolution build_airports_by_country.py uses, so
    a country tagged here always matches how the rest of the project
    (tourist_cities.json, the frontend's country pages, etc.) refers to
    that same country.

    Same duplicate-IATA handling as
    build_airports_coordinates_map.py's build_airport_coordinates(): keep
    the first occurrence, report duplicates skipped rather than silently
    overwriting. Airports whose country string doesn't resolve to a known
    country (see country_lookup.normalize_airport_country) are skipped
    and reported too -- same "real gap" convention as everywhere else in
    this project, not a crash.

    One extra wrinkle: country_aliases.json's iso2 field for Namibia is
    the JSON literal NaN, not the string "NA" -- almost certainly a stray
    upstream pandas read that treated the two-letter code "NA" as a
    missing value rather than data (the exact same landmine
    fetch_hiking_trails.py's ISO2_OVERRIDES works around). Rather than
    edit that generated file by hand, non-string iso2 values are treated
    as unmatched here too."""
    if not AIRPORTS_PATH.exists():
        raise FileNotFoundError(f"{AIRPORTS_PATH} not found -- run fetch_openflights_airports.py first.")
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        airports = json.load(f)["airports"]

    if not ALIASES_PATH.exists():
        raise FileNotFoundError(f"{ALIASES_PATH} not found -- run build_country_aliases.py first.")
    with open(ALIASES_PATH, encoding="utf-8") as f:
        iso3_to_iso2 = {
            iso3: entry["iso2"]
            for iso3, entry in json.load(f)["countries"].items()
            if isinstance(entry["iso2"], str)
        }

    iata_to_iso2: dict[str, str] = {}
    duplicates_skipped = 0
    unmatched_country_names: set[str] = set()

    for airport in airports:
        iata = airport.get("iata")
        if not iata:
            continue

        iso3 = normalize_airport_country(iata, airport.get("country"))
        iso2 = iso3_to_iso2.get(iso3) if iso3 else None
        if iso2 is None:
            if airport.get("country"):
                unmatched_country_names.add(airport["country"])
            continue

        if iata in iata_to_iso2:
            duplicates_skipped += 1
            continue
        iata_to_iso2[iata] = iso2

    if duplicates_skipped:
        print(f"WARNING: {duplicates_skipped} duplicate IATA code(s) skipped while building the "
              f"IATA -> country map (kept the first occurrence).")
    if unmatched_country_names:
        print(f"WARNING: {len(unmatched_country_names)} airports.json country name(s) didn't resolve "
              f"to a known country: {sorted(unmatched_country_names)}")

    return iata_to_iso2


def add_country_pairs(routes: list[dict], iata_to_iso2: dict[str, str]) -> int:
    """Mutates each route dict in place, adding country_pair and
    is_domestic.

    country_pair: the ISO2 codes of the route's two countries joined with
    "|", always sorted alphabetically so the same country pair reads
    identically regardless of which airport is Departure vs Destination
    (e.g. Departure=CDG, Destination=IAH -> "FR|US", and the reverse
    route IAH->CDG also resolves to "FR|US", not "US|FR"). Domestic
    routes (both airports in the same country) get a pair like "US|US"
    rather than being dropped or left blank -- still correct output for
    "what countries does this route connect," it's just the same country
    twice.

    is_domestic: "1" if country_pair's two halves are the same country,
    "0" if they differ -- trivial once country_pair is sorted (just
    compare the two halves), so computed alongside it rather than in a
    second pass over the routes.

    Both are blank string if either airport's IATA code doesn't resolve
    to a country (missing from airport_coordinates.json/airports.json,
    or its country string doesn't normalize -- see
    load_iata_to_country()) -- same "real gap, not a bug" treatment as
    distance_km/mi above (an unresolved route is neither known-domestic
    nor known-international, so "0" would be misleading). Returns the
    count of routes left blank."""
    missing_count = 0

    for route in routes:
        origin_iso2 = iata_to_iso2.get(route["Departure"])
        dest_iso2 = iata_to_iso2.get(route["Destination"])

        if origin_iso2 is None or dest_iso2 is None:
            route["country_pair"] = ""
            route["is_domestic"] = ""
            missing_count += 1
            continue

        route["country_pair"] = "|".join(sorted((origin_iso2, dest_iso2)))
        route["is_domestic"] = "1" if origin_iso2 == dest_iso2 else "0"

    return missing_count


def add_distances(routes: list[dict], coordinates: dict) -> int:
    """Mutates each route dict in place, adding distance_km/distance_mi
    (blank string if either airport's coordinates are missing). Returns
    the count of routes that couldn't be computed."""
    missing_count = 0

    for route in routes:
        origin = coordinates.get(route["Departure"])
        dest = coordinates.get(route["Destination"])

        if origin is None or dest is None:
            route["distance_km"] = ""
            route["distance_mi"] = ""
            missing_count += 1
            continue

        route["distance_km"] = round(
            calculate_distance(origin["lat"], origin["lng"], dest["lat"], dest["lng"]), 1
        )
        route["distance_mi"] = round(
            calculate_distance(origin["lat"], origin["lng"], dest["lat"], dest["lng"], unit="mi"), 1
        )

    return missing_count


def main():
    routes, fieldnames = load_routes()
    coordinates = load_coordinates()
    iata_to_iso2 = load_iata_to_country()

    missing_distance_count = add_distances(routes, coordinates)
    missing_country_count = add_country_pairs(routes, iata_to_iso2)

    out_fieldnames = fieldnames + ["distance_km", "distance_mi", "country_pair", "is_domestic"]
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(routes)

    print(f"Wrote {len(routes)} routes -> {OUT_PATH}")
    print(f"{missing_distance_count} route(s) left distance_km/distance_mi blank -- Departure "
          f"and/or Destination code not found in {COORDINATES_PATH.name}.")
    print(f"{missing_country_count} route(s) left country_pair blank -- Departure and/or "
          f"Destination code didn't resolve to a known country.")


if __name__ == "__main__":
    main()
