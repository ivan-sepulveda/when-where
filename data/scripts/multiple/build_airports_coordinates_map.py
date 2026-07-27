"""
Derived from: data/reference/airports.json (built by fetch_openflights_airports.py)

Reshapes airports.json into data/reference/airport_coordinates.json: a
flat lookup of IATA code -> {lat, lng}, dropping every other field
(name, city, country, altitude, timezone, etc.) since only coordinates
are needed here -- this is meant as a quick "IATA -> coordinates" lookup
for distance_calculator.py, not a general-purpose airports reference
(that's what airports.json/airports_by_country.json are for).

    "GKA": {"lat": -6.081689834590001, "lng": 145.391998291},
    "MAG": {"lat": -5.20707988739, "lng": 145.789001465},

Rows with no IATA code (a real subset -- OpenFlights has ICAO for some
smaller airfields/stations but no IATA) can't be included in an
IATA-keyed lookup and are skipped, counted, and reported. Duplicate IATA
codes (rare, but OpenFlights isn't perfectly deduplicated) are also
reported, keeping the first occurrence rather than silently overwriting.

Usage:
    python build_airports_coordinates_map.py
"""

import json
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
AIRPORTS_PATH = REFERENCE_DIR / "airports.json"
OUT_PATH = REFERENCE_DIR / "airport_coordinates.json"


def load_airports() -> list[dict]:
    if not AIRPORTS_PATH.exists():
        raise FileNotFoundError(
            f"{AIRPORTS_PATH} not found -- run fetch_openflights_airports.py first."
        )
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        return json.load(f)["airports"]


def build_airport_coordinates(airports: list[dict]) -> tuple[dict, int, int]:
    """Pure function: airport list in, ({iata: {lat, lng}}, no_iata_count,
    duplicates_skipped) out. Kept separate from I/O for testing."""
    coordinates: dict[str, dict] = {}
    no_iata_count = 0
    duplicates_skipped = 0

    for airport in airports:
        iata = airport.get("iata")
        if not iata:
            no_iata_count += 1
            continue

        if iata in coordinates:
            duplicates_skipped += 1
            print(f"WARNING: duplicate IATA code {iata!r} -- skipped (keeping the first entry).")
            continue

        coordinates[iata] = {"lat": airport["lat"], "lng": airport["lng"]}

    return coordinates, no_iata_count, duplicates_skipped


def main():
    airports = load_airports()
    coordinates, no_iata_count, duplicates_skipped = build_airport_coordinates(airports)

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(coordinates, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(coordinates)} airports -> {OUT_PATH}")
    print(f"{no_iata_count} airports.json rows had no IATA code and were skipped.")
    if duplicates_skipped:
        print(f"{duplicates_skipped} duplicate IATA code(s) skipped.")


if __name__ == "__main__":
    main()
