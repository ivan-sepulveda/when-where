"""
Derived from: data/reference/tourist_cities.json (built by fetch_tourist_cities.py)

Generates data/reference/city_airports.json: every city in
tourist_cities.json, nested as country -> city -> {lat, lng, airports}.
Uses tourist_cities.json's "city_ascii" field for the city key (not
"city") -- airports.json's own city names (from OpenFlights) are
unaccented, e.g. "Osaka" not "Ōsaka", so keying on the accented form
would silently fail to match against airports.json later even though
it's the same city (see populate_city_airports.py). lat/lng still come
straight from tourist_cities.json; "airports" is left an empty list for
now, e.g.:

    "United States": {
      "Houston": {
        "lat": 29.786,
        "lng": -95.3885,
        "airports": []
      }
    }

Filling "airports" in is a judgment call (which specific airport(s)
actually serve a city -- not something to infer automatically), so this
script only lays out the empty structure for now.

Duplicate (country, city) pairs -- tourist_cities.json legitimately
contains same-named cities within the same country in rare cases -- are
skipped with a warning rather than silently overwritten; since
tourist_cities.json is sorted by population descending, the first
(most-populous) one encountered is the one that's kept.

This is a template meant to be filled in by hand after generation, so
re-running this script WON'T overwrite an existing output file unless
--force is passed (to avoid silently wiping out manual edits).

Usage:
    python build_city_airport_map.py
    python build_city_airport_map.py --force   # regenerate, discarding any existing file
"""

import argparse
import json
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
TOURIST_CITIES_PATH = REFERENCE_DIR / "tourist_cities.json"
OUT_PATH = REFERENCE_DIR / "city_airports.json"


def load_tourist_cities() -> list[dict]:
    if not TOURIST_CITIES_PATH.exists():
        raise FileNotFoundError(
            f"{TOURIST_CITIES_PATH} not found -- run fetch_tourist_cities.py first."
        )
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        return json.load(f)["cities"]


def build_city_airport_map(cities: list[dict]) -> dict:
    """Pure function: city list in, {country: {city: {lat, lng, airports}}}
    dict out (plus a duplicate-pairs count). Kept separate from I/O for
    testing."""
    by_country: dict[str, dict[str, dict]] = {}
    duplicates_skipped = 0

    for city in cities:
        country = city["country"]
        city_name = city["city_ascii"]

        country_bucket = by_country.setdefault(country, {})
        if city_name in country_bucket:
            duplicates_skipped += 1
            print(
                f"WARNING: duplicate (country, city) pair -- {city_name!r}, {country!r} "
                f"already present -- skipped (keeping the first/most-populous entry)."
            )
            continue

        country_bucket[city_name] = {
            "lat": city["lat"],
            "lng": city["lng"],
            "airports": [],
        }

    return by_country, duplicates_skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing city_airports.json. Default: refuse if the file already "
        "exists, so manual edits (airports filled in by hand) aren't wiped out.",
    )
    args = parser.parse_args()

    if OUT_PATH.exists() and not args.force:
        raise SystemExit(
            f"{OUT_PATH} already exists -- refusing to overwrite possible manual edits. "
            f"Pass --force to regenerate it from scratch anyway."
        )

    cities = load_tourist_cities()
    by_country, duplicates_skipped = build_city_airport_map(cities)

    total_cities = sum(len(v) for v in by_country.values())
    out = {
        "source": "Derived from data/reference/tourist_cities.json",
        "total_countries": len(by_country),
        "total_cities": total_cities,
        "duplicate_country_city_pairs_skipped": duplicates_skipped,
        "cities_by_country": by_country,
    }

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {total_cities} cities across {len(by_country)} countries -> {OUT_PATH}")


if __name__ == "__main__":
    main()
