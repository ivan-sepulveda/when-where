"""
Derived from: data/reference/city_airports.json (built by build_city_airport_map.py)
              data/reference/airports.json (built by fetch_openflights_airports.py)

Fills in the "airports" list for each city in city_airports.json by
matching every airport whose coordinates fall within DEFAULT_RADIUS_KM
(75 km) of the city's own lat/lng, measured as great-circle distance.

WHY DISTANCE AND NOT NAME MATCHING:

This script used to match on (country, city name) -- case-insensitive
exact match against airports.json's own `city` field. That was wrong in
three ways, all of which distance matching fixes for free:

  * Metro airports named after a *different* city never matched. New
    York never got EWR, because OpenFlights files Newark Liberty under
    city "Newark". Washington never got BWI (filed under "Baltimore").
  * Same-name cities in different regions cross-matched. Washington DC
    picked up OCW -- Washington, *North Carolina* -- because the country
    matched and the city string matched.
  * Country spellings had to agree exactly, so ~20 countries matched
    nothing at all (Korea South, Czechia, Cote d'Ivoire, Malta,
    Luxembourg, Monaco, Cambodia, Bahrain, ...) purely because
    OpenFlights spells the country differently than tourist_cities.json.

Coverage went from 1,198 of 3,032 cities (39%) under name matching to
roughly 90% at a 75 km radius.

WHY 75 KM:

50 km captures nearly every major international airport but drops Tokyo
Narita, which sits 58 km from the Tokyo centroid, and leaves Seoul
Incheon (49 km) and London Stansted (49 km) clearing the bar by about a
kilometre -- too fragile. 75 km clears all of those with room to spare
without reaching into the next metro over. Override with --radius-km.

Each match is appended to the city's "airports" list as
{"<IATA>": {"lat": ..., "lng": ..., "distance_km": ...}}, sorted
nearest-first, so a consumer that wants "the" airport for a city can
take the first element and one that wants all options has the distance
to rank on. airports.json rows with no IATA code (a real subset --
smaller airfields/stations OpenFlights has ICAO for but no IATA) can't
be keyed this way and are skipped, counted, and reported at the end
rather than silently dropped.

Heliports and air bases are already excluded upstream, by
fetch_openflights_airports.py's name filter -- not here. If JRB/JRA
(Manhattan heliports) or Yokota Air Base show up in the output, that
means airports.json was regenerated with --no-name-filter.

This runs over EVERY country. (An earlier version had a
`if country != "United States": continue` guard so results could be
spot-checked before going global; it was removed, though its docstring
went on claiming otherwise for a while.)

Re-running this script is safe -- it resets every city's "airports"
list to [] before re-matching, so it doesn't pile up duplicates on
repeated runs.

Usage:
    python populate_city_airports.py
    python populate_city_airports.py --radius-km 50
"""

import argparse
import json
import sys
from pathlib import Path

# distance_calculator.py lives one directory up (data/scripts/), not
# alongside this script (data/scripts/multiple/) -- only a script's own
# directory is added to sys.path automatically, so the parent has to be
# added by hand.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from distance_calculator import calculate_distance  # noqa: E402

DEFAULT_RADIUS_KM = 75.0

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
CITY_AIRPORTS_PATH = REFERENCE_DIR / "city_airports.json"
AIRPORTS_PATH = REFERENCE_DIR / "airports.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_spatial_index(airports: list[dict]) -> dict:
    """(round(lat), round(lng)) -> list of airports in that 1-degree cell.

    A flat scan would be 3,032 cities x ~6,000 airports = ~18M haversine
    calls. Bucketing by whole degree and only checking the cells around
    a city cuts that by ~3 orders of magnitude. The radius still gets
    checked exactly -- this only narrows the candidate set.

    IATA-only: rows with no IATA code can't be keyed as
    {"<IATA>": {...}} in the output, so they're excluded here and
    counted separately by the caller.
    """
    index: dict[tuple[int, int], list[dict]] = {}
    for airport in airports:
        if not airport.get("iata"):
            continue
        if airport.get("lat") is None or airport.get("lng") is None:
            continue
        key = (round(airport["lat"]), round(airport["lng"]))
        index.setdefault(key, []).append(airport)
    return index


def _cells_to_check(lat: float, lng: float, radius_km: float) -> list[tuple[int, int]]:
    """Every 1-degree cell that could hold a point within radius_km.

    A degree of latitude is ~111 km everywhere; a degree of longitude
    shrinks toward the poles, so the longitude span has to widen as
    |lat| grows or high-latitude cities would miss airports that are
    well inside the radius. Near the poles cos(lat) -> 0 and the span
    blows up, so it's capped at a full sweep of all 360 longitudes.
    """
    import math

    lat_cells = int(math.ceil(radius_km / 111.0)) + 1
    cos_lat = math.cos(math.radians(lat))
    if abs(cos_lat) < 0.01:
        lng_cells = 180
    else:
        lng_cells = min(180, int(math.ceil(radius_km / (111.0 * abs(cos_lat)))) + 1)

    cells = []
    for dlat in range(-lat_cells, lat_cells + 1):
        for dlng in range(-lng_cells, lng_cells + 1):
            # Wrap longitude so cities near the antimeridian (Fiji, NZ,
            # far-east Russia) still see cells on the other side of it.
            cells.append((round(lat) + dlat, (round(lng) + dlng + 180) % 360 - 180))
    return cells


def populate_city_airports(
    city_airports: dict,
    airports: list[dict],
    radius_km: float = DEFAULT_RADIUS_KM,
) -> dict:
    """Pure function: mutates and returns city_airports's cities_by_country
    in place. Kept separate from I/O for testing."""
    index = build_spatial_index(airports)
    no_iata_count = sum(1 for a in airports if not a.get("iata"))

    cities_matched = 0
    cities_unmatched = 0
    airports_attached = 0

    for cities in city_airports["cities_by_country"].values():
        for city_info in cities.values():
            city_info["airports"] = []  # reset so reruns don't duplicate

            lat, lng = city_info["lat"], city_info["lng"]
            candidates = []
            for cell in _cells_to_check(lat, lng, radius_km):
                candidates.extend(index.get(cell, []))

            matches = []
            for airport in candidates:
                distance_km = calculate_distance(lat, lng, airport["lat"], airport["lng"])
                if distance_km <= radius_km:
                    matches.append((distance_km, airport))

            if not matches:
                cities_unmatched += 1
                continue

            cities_matched += 1
            # Nearest first, tie-broken on IATA so the output is stable
            # across runs regardless of dict/index ordering.
            matches.sort(key=lambda m: (m[0], m[1]["iata"]))
            for distance_km, airport in matches:
                city_info["airports"].append(
                    {
                        airport["iata"]: {
                            "lat": airport["lat"],
                            "lng": airport["lng"],
                            "distance_km": round(distance_km, 1),
                        }
                    }
                )
                airports_attached += 1

    city_airports["radius_km"] = radius_km
    city_airports["match_method"] = (
        f"great-circle distance from city centroid, <= {radius_km} km "
        f"(was: exact (country, city name) match)"
    )

    return {
        "cities_matched": cities_matched,
        "cities_unmatched": cities_unmatched,
        "airports_attached": airports_attached,
        "airports_json_rows_with_no_iata": no_iata_count,
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--radius-km",
        type=float,
        default=DEFAULT_RADIUS_KM,
        help=f"Attach every airport within this many km of the city centroid. "
        f"Default: {DEFAULT_RADIUS_KM}",
    )
    args = parser.parse_args()

    city_airports = load_json(CITY_AIRPORTS_PATH)
    airports = load_json(AIRPORTS_PATH)["airports"]

    stats = populate_city_airports(city_airports, airports, radius_km=args.radius_km)

    with open(CITY_AIRPORTS_PATH, "w", encoding="utf-8") as f:
        json.dump(city_airports, f, indent=2, ensure_ascii=False)

    total = stats["cities_matched"] + stats["cities_unmatched"]
    pct = (stats["cities_matched"] / total * 100) if total else 0.0
    print(
        f"Matched airports for {stats['cities_matched']} of {total} cities ({pct:.0f}%) "
        f"within {args.radius_km} km ({stats['airports_attached']} airport entries attached)."
    )
    print(f"{stats['cities_unmatched']} cities had no airport within {args.radius_km} km.")
    print(
        f"{stats['airports_json_rows_with_no_iata']} airports.json rows had no IATA code "
        f"and couldn't be included (need an IATA code to key {{'<IATA>': {{...}}}})."
    )
    print(f"Wrote -> {CITY_AIRPORTS_PATH}")


if __name__ == "__main__":
    main()
