"""
Derived from: data/processed/multiple/airline_routes.csv (built by fetch_airline_routes.py)
              data/reference/airport_coordinates.json (built by build_airports_coordinates_map.py)

Adds distance_km and distance_mi columns to airline_routes.csv, computed
via distance_calculator.calculate_distance() from each route's
Departure/Destination IATA codes looked up in airport_coordinates.json.
Writes data/processed/multiple/airline_routes_enhanced.csv (original
columns unchanged, two new ones appended).

A route whose Departure or Destination code isn't in
airport_coordinates.json (a real gap -- as of this writing, 273 of the
~4,000 distinct codes referenced in airline_routes.csv aren't in
airports.json/airport_coordinates.json, likely airports OpenFlights
doesn't carry as type "airport", or doesn't carry at all) gets blank
distance_km/distance_mi rather than being dropped from the output --
counted and reported at the end.

Usage:
    python build_airline_routes_enhanced.py
"""

import csv
import json
import sys
from pathlib import Path

# distance_calculator.py lives in data/scripts/, not alongside this
# script (data/scripts/multiple/) -- only a script's own directory is
# added to sys.path automatically, so the parent has to be added by hand.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from distance_calculator import calculate_distance  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
ROUTES_PATH = PROCESSED_DIR / "airline_routes.csv"
COORDINATES_PATH = REFERENCE_DIR / "airport_coordinates.json"
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

    missing_count = add_distances(routes, coordinates)

    out_fieldnames = fieldnames + ["distance_km", "distance_mi"]
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(routes)

    print(f"Wrote {len(routes)} routes -> {OUT_PATH}")
    print(f"{missing_count} route(s) left blank -- Departure and/or Destination code "
          f"not found in {COORDINATES_PATH.name}.")


if __name__ == "__main__":
    main()
