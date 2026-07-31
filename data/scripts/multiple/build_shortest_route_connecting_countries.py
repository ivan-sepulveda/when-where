"""
Derived from: data/processed/multiple/airline_routes_enhanced.csv (built by
              build_airline_routes_enhanced.py)

For every pair of distinct countries that airline_routes_enhanced.csv's
country_pair column connects, finds the single shortest-distance route
between them (by distance_km) and writes
data/processed/multiple/shortest_route_connecting_countries.json: a
country-keyed lookup of every other country it has a route to, and the
shortest known distance in km.

    {
      "countries": {
        "US": {"FR": 8071.4, "IT": 8670.2, "MX": 1310.5, ...},
        "FR": {"US": 8071.4, ...},
        ...
      }
    }

Symmetric by construction -- US->FR and FR->US are the same physical
distance, so both directions are written from the same underlying
shortest route rather than computed independently (a route that only
exists in one direction in the source data, e.g. an FR->US flight with no
matching US->FR flight, still produces both directions here since this
is a distance lookup, not a "does this exact flight exist" one).

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


def compute_shortest_distances(routes: list[dict]) -> tuple[dict[tuple[str, str], float], int, int]:
    """Pure function: route rows in, {(country_a, country_b): shortest_km}
    out (country_a < country_b alphabetically, matching country_pair's own
    "A|B" ordering -- see build_airline_routes_enhanced.py). Also returns
    (domestic_skipped, incomplete_skipped) counts for reporting. Kept
    separate from I/O for testing."""
    shortest: dict[tuple[str, str], float] = {}
    domestic_skipped = 0
    incomplete_skipped = 0

    for route in routes:
        country_pair = route.get("country_pair")
        distance_raw = route.get("distance_km")

        if not country_pair or not distance_raw:
            incomplete_skipped += 1
            continue

        country_a, country_b = country_pair.split("|")
        if country_a == country_b:
            domestic_skipped += 1
            continue

        distance_km = float(distance_raw)
        key = (country_a, country_b)  # already alphabetical, per country_pair's own convention
        if key not in shortest or distance_km < shortest[key]:
            shortest[key] = distance_km

    return shortest, domestic_skipped, incomplete_skipped


def build_country_lookup(shortest: dict[tuple[str, str], float]) -> dict[str, dict[str, float]]:
    """Expands the alphabetical (country_a, country_b) -> km map into a
    symmetric, country-keyed nested lookup -- both US->FR and FR->US point
    at the same underlying shortest route."""
    lookup: dict[str, dict[str, float]] = {}
    for (country_a, country_b), distance_km in shortest.items():
        lookup.setdefault(country_a, {})[country_b] = distance_km
        lookup.setdefault(country_b, {})[country_a] = distance_km
    return {country: dict(sorted(destinations.items())) for country, destinations in sorted(lookup.items())}


def main():
    routes = load_routes()
    shortest, domestic_skipped, incomplete_skipped = compute_shortest_distances(routes)
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
