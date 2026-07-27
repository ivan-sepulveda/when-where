"""
Derived from: data/reference/city_airports.json (built by build_city_airport_map.py)
              data/reference/airports.json (built by fetch_openflights_airports.py)

Fills in the "airports" list for each city in city_airports.json by
matching against airports.json on (country, city name) -- case-
insensitive exact match on city name, within the same country.

Restricted to the United States only for now:

    if country != "United States":
        continue

so results can be manually spot-checked before opening this up to every
country -- remove that guard once verified. (Every other country's
"airports" list is left untouched, still empty, when this restriction is
in place.)

Each match is appended to the city's "airports" list as
{"<IATA>": {"lat": ..., "lng": ...}}. airports.json rows with no IATA
code (a real subset -- smaller airfields/stations OpenFlights has ICAO
for but no IATA) can't be keyed this way and are skipped, counted, and
reported at the end rather than silently dropped.

Re-running this script is safe -- it resets a country's cities'
"airports" lists to [] before re-matching, so it doesn't pile up
duplicates on repeated runs.

Usage:
    python populate_city_airports.py
"""

import json
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
CITY_AIRPORTS_PATH = REFERENCE_DIR / "city_airports.json"
AIRPORTS_PATH = REFERENCE_DIR / "airports.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found.")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_airport_lookup(airports: list[dict]) -> dict:
    """(country, city.casefold()) -> list of airport dicts, IATA-only
    (rows with no IATA code can't be keyed as {"<IATA>": {...}} and are
    excluded from the lookup -- counted separately by the caller)."""
    lookup: dict[tuple[str, str], list[dict]] = {}
    for airport in airports:
        if not airport.get("iata") or not airport.get("city") or not airport.get("country"):
            continue
        key = (airport["country"], airport["city"].casefold())
        lookup.setdefault(key, []).append(airport)
    return lookup


def populate_city_airports(city_airports: dict, airports: list[dict]) -> dict:
    """Pure function: mutates and returns city_airports's cities_by_country
    in place. Kept separate from I/O for testing."""
    lookup = build_airport_lookup(airports)
    no_iata_count = sum(
        1 for a in airports if a.get("country") and a.get("city") and not a.get("iata")
    )

    cities_matched = 0
    cities_unmatched = 0
    airports_attached = 0

    for country, cities in city_airports["cities_by_country"].items():
        #if country != "United States":
        #    continue

        for city_name, city_info in cities.items():
            city_info["airports"] = []  # reset so reruns don't duplicate

            matches = lookup.get((country, city_name.casefold()), [])
            if not matches:
                cities_unmatched += 1
                continue

            cities_matched += 1
            for airport in matches:
                city_info["airports"].append(
                    {airport["iata"]: {"lat": airport["lat"], "lng": airport["lng"]}}
                )
                airports_attached += 1

    return {
        "cities_matched": cities_matched,
        "cities_unmatched": cities_unmatched,
        "airports_attached": airports_attached,
        "airports_json_rows_with_no_iata": no_iata_count,
    }


def main():
    city_airports = load_json(CITY_AIRPORTS_PATH)
    airports = load_json(AIRPORTS_PATH)["airports"]

    stats = populate_city_airports(city_airports, airports)

    with open(CITY_AIRPORTS_PATH, "w", encoding="utf-8") as f:
        json.dump(city_airports, f, indent=2, ensure_ascii=False)

    print(f"Matched airports for {stats['cities_matched']} United States cities "
          f"({stats['airports_attached']} airport entries attached).")
    print(f"{stats['cities_unmatched']} United States cities had no matching airport.")
    print(f"{stats['airports_json_rows_with_no_iata']} airports.json rows had no IATA code "
          f"and couldn't be included (need an IATA code to key {{'<IATA>': {{...}}}}).")
    print(f"Wrote -> {CITY_AIRPORTS_PATH}")


if __name__ == "__main__":
    main()
