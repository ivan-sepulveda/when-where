"""
Derived from: data/processed/multiple/airline_routes_enhanced.csv (built by
              build_airline_routes_enhanced.py)
Requires: data/reference/airports.json, data/reference/country_aliases.json
          (same as build_airline_routes_enhanced.py -- reuses its
          load_iata_to_country() to know which country each row's
          Departure/Destination airport belongs to)

For every pair of distinct countries that airline_routes_enhanced.csv's
country_pair column connects, finds the single shortest-distance route
between them (by distance_km) -- airports included, not just the number --
and writes data/processed/multiple/shortest_route_connecting_countries.json:
a country-keyed lookup of every other country it has a route to, the
shortest known distance in km, and which two airports that route is
between.

    {
      "countries": {
        "US": {
          "FR": {"distance_km": 5534.3, "departure_airport": "BOS", "destination_airport": "CDG"},
          "MX": {"distance_km": 447.6, "departure_airport": "IAH", "destination_airport": "MEX"},
          ...
        },
        "FR": {
          "US": {"distance_km": 5534.3, "departure_airport": "CDG", "destination_airport": "BOS"},
          ...
        }
      }
    }

Symmetric by construction -- US->FR and FR->US are the same physical
route, just in the other direction, so both directions are written from
the same underlying shortest route (with departure_airport/
destination_airport swapped) rather than computed independently.

Domestic routes (country_pair like "US|US", i.e. is_domestic=1) are
excluded entirely -- this file is specifically about routes CONNECTING
two different countries, not within one. Rows with a blank country_pair
or blank distance_km (see build_airline_routes_enhanced.py's docstring
for why those gaps exist -- an unresolved airport country or missing
coordinates, not a data error) are skipped and don't affect any country
pair's minimum.

Usage:
    python build_shortest_route_connecting_countries.py
"""

import csv
import json
from datetime import date
from pathlib import Path

# build_airline_routes_enhanced.py lives alongside this script (both in
# data/scripts/multiple/) -- Python already puts a script's own directory
# on sys.path, so this import works without extra path setup.
from build_airline_routes_enhanced import load_iata_to_country  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
ROUTES_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"
OUT_PATH = PROCESSED_DIR / "shortest_route_connecting_countries.json"


def load_routes() -> list[dict]:
    if not ROUTES_PATH.exists():
        raise FileNotFoundError(
            f"{ROUTES_PATH} not found -- run build_airline_routes_enhanced.py first."
        )
    with open(ROUTES_PATH, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def compute_shortest_distances(
    routes: list[dict], iata_to_iso2: dict[str, str]
) -> tuple[dict[tuple[str, str], dict], int, int]:
    """Pure function: route rows + an IATA->ISO2 map in,
    {(country_a, country_b): {"distance_km": ..., "airport_by_country":
    {country_a: iata, country_b: iata}}} out (country_a < country_b
    alphabetically, matching country_pair's own "A|B" ordering -- see
    build_airline_routes_enhanced.py). airport_by_country records which
    specific airport (in THIS winning row) belongs to each of the two
    countries, since country_pair alone doesn't preserve which of
    Departure/Destination was which country. Also returns
    (domestic_skipped, incomplete_skipped) counts for reporting. Kept
    separate from I/O for testing."""
    shortest: dict[tuple[str, str], dict] = {}
    domestic_skipped = 0
    incomplete_skipped = 0

    for route in routes:
        country_pair = route.get("country_pair")
        distance_raw = route.get("distance_km")
        departure_iata = route.get("Departure")
        destination_iata = route.get("Destination")

        if not country_pair or not distance_raw:
            incomplete_skipped += 1
            continue

        country_a, country_b = country_pair.split("|")
        if country_a == country_b:
            domestic_skipped += 1
            continue

        distance_km = float(distance_raw)
        key = (country_a, country_b)  # already alphabetical, per country_pair's own convention
        current = shortest.get(key)
        if current is None or distance_km < current["distance_km"]:
            departure_country = iata_to_iso2.get(departure_iata)
            destination_country = iata_to_iso2.get(destination_iata)
            shortest[key] = {
                "distance_km": distance_km,
                "airport_by_country": {
                    departure_country: departure_iata,
                    destination_country: destination_iata,
                },
            }

    return shortest, domestic_skipped, incomplete_skipped


def build_country_lookup(shortest: dict[tuple[str, str], dict]) -> dict[str, dict[str, dict]]:
    """Expands the alphabetical (country_a, country_b) -> {distance_km,
    airport_by_country} map into a symmetric, country-keyed nested
    lookup -- both US->FR and FR->US point at the same underlying
    shortest route, with departure_airport/destination_airport swapped
    to match each direction."""
    lookup: dict[str, dict[str, dict]] = {}
    for (country_a, country_b), info in shortest.items():
        distance_km = info["distance_km"]
        airports = info["airport_by_country"]
        lookup.setdefault(country_a, {})[country_b] = {
            "distance_km": distance_km,
            "departure_airport": airports[country_a],
            "destination_airport": airports[country_b],
        }
        lookup.setdefault(country_b, {})[country_a] = {
            "distance_km": distance_km,
            "departure_airport": airports[country_b],
            "destination_airport": airports[country_a],
        }
    return {country: dict(sorted(destinations.items())) for country, destinations in sorted(lookup.items())}


def main():
    routes = load_routes()
    iata_to_iso2 = load_iata_to_country()
    shortest, domestic_skipped, incomplete_skipped = compute_shortest_distances(routes, iata_to_iso2)
    lookup = build_country_lookup(shortest)

    out = {
        "source": "Derived from airline_routes_enhanced.csv via build_shortest_route_connecting_countries.py",
        "generated": date.today().isoformat(),
        "total_countries": len(lookup),
        "total_country_pairs": len(shortest),
        "countries": lookup,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(lookup)} countries / {len(shortest)} country pairs -> {OUT_PATH}")
    print(f"{domestic_skipped} domestic route(s) excluded (same country on both ends).")
    print(f"{incomplete_skipped} route(s) skipped -- blank country_pair or distance_km.")


if __name__ == "__main__":
    main()
