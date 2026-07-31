"""
Derived from: data/reference/airports.json (built by fetch_openflights_airports.py,
sourced from the OpenFlights Airport Database)
Requires: data/reference/country_aliases.json (built by build_country_aliases.py)
          -- run that first if this errors with a FileNotFoundError.

Regroups the flat airports.json list by country into
data/reference/airports_by_country.json, keyed by ISO 3166-1 alpha-2 code
(not the raw OpenFlights country name string) via country_lookup.py's
normalize_country(), so this joins cleanly against everything else in the
project that already keys off iso2 (tourist_cities.json, the frontend's
country dropdown, etc.) without a separate normalization step downstream.
Each airport's own `country` field is dropped in the output since it's
now implied by which key it's nested under.

OpenFlights country strings that don't resolve to a known country (see
country_lookup.normalize_country) are skipped and reported at the end --
same pattern as country_lookup.py's own CLI diagnostic mode. Add any
recurring miss to EXTRA_ALIASES in build_country_aliases.py and rerun
that script first.

Defaults to keeping only `type == "airport"` (commercial/public airports),
dropping heliports/stations/etc. -- same default as
fetch_openflights_airports.py, applied again here in case airports.json
was built with `--all-types`. Use `--all-types` to keep everything, or
`--type <value>` for some other specific type.

Usage:
    python build_airports_by_country.py                # airports only (default)
    python build_airports_by_country.py --all-types     # every type, no filtering
    python build_airports_by_country.py --type heliport # some other specific type
"""

import argparse
import json
import sys
from pathlib import Path

# country_lookup.py lives one directory up (data/scripts/), not alongside
# this script (data/scripts/multiple/) -- only a script's own directory is
# added to sys.path automatically, so the parent has to be added by hand.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from country_lookup import normalize_airport_country  # noqa: E402

DEFAULT_TYPE_FILTER = "airport"

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
AIRPORTS_PATH = REFERENCE_DIR / "airports.json"
ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
OUT_PATH = REFERENCE_DIR / "airports_by_country.json"

# Keys to keep on each airport object in the output -- everything from
# airports.json except "country", which becomes redundant once airports
# are nested under their country's key.
AIRPORT_FIELDS = [
    "airport_id",
    "name",
    "city",
    "iata",
    "icao",
    "lat",
    "lng",
    "altitude_ft",
    "timezone_utc_offset",
    "dst",
    "tz_database_time_zone",
    "type",
    "source",
]


def load_airports() -> list[dict]:
    if not AIRPORTS_PATH.exists():
        raise FileNotFoundError(
            f"{AIRPORTS_PATH} not found -- run fetch_openflights_airports.py first."
        )
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        return json.load(f)["airports"]


def load_iso3_to_country() -> dict:
    """iso3 -> {iso2, canonical_name}, from country_aliases.json."""
    if not ALIASES_PATH.exists():
        raise FileNotFoundError(
            f"{ALIASES_PATH} not found -- run build_country_aliases.py first."
        )
    with open(ALIASES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {
        iso3: {"iso2": entry["iso2"], "canonical_name": entry["canonical_name"]}
        for iso3, entry in data["countries"].items()
    }


def build_airports_by_country(
    airports: list[dict], iso3_to_country: dict, type_filter: str | None = None
) -> dict:
    """Pure function: airport list + alias map in, output dict out. Kept
    separate from I/O for testing."""
    if type_filter:
        airports = [a for a in airports if (a.get("type") or "").casefold() == type_filter.casefold()]

    by_country: dict[str, dict] = {}
    unmatched_country_names: set[str] = set()
    skipped = 0

    for airport in airports:
        iso3 = normalize_airport_country(airport.get("iata"), airport.get("country"))
        if iso3 is None:
            if airport.get("country"):
                unmatched_country_names.add(airport["country"])
            skipped += 1
            continue

        country_info = iso3_to_country.get(iso3)
        if country_info is None:
            # Shouldn't happen -- normalize_country only returns iso3 codes
            # that exist in country_aliases.json -- but don't silently drop
            # data if the two files ever drift out of sync.
            unmatched_country_names.add(airport.get("country") or iso3)
            skipped += 1
            continue

        iso2 = country_info["iso2"]
        entry = by_country.setdefault(
            iso2, {"country_name": country_info["canonical_name"], "airports": []}
        )
        entry["airports"].append({field: airport.get(field) for field in AIRPORT_FIELDS})

    total_airports = sum(len(v["airports"]) for v in by_country.values())

    return {
        "source": "Derived from data/reference/airports.json (OpenFlights Airport Database)",
        "type_filter": type_filter,
        "total_countries": len(by_country),
        "total_airports": total_airports,
        "skipped_unmatched_country": skipped,
        "unmatched_country_names": sorted(unmatched_country_names),
        "airports_by_country": by_country,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--type",
        default=DEFAULT_TYPE_FILTER,
        help=f"Keep only airports whose 'type' field matches this value. "
        f"Default: {DEFAULT_TYPE_FILTER!r} (commercial/public airports; drops "
        f"heliports/stations/etc.). Use --all-types to disable filtering entirely.",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Keep every airport regardless of 'type' (private airstrips, heliports, stations, "
        "etc.). Overrides --type.",
    )
    args = parser.parse_args()

    type_filter = None if args.all_types else args.type

    airports = load_airports()
    iso3_to_country = load_iso3_to_country()
    out = build_airports_by_country(airports, iso3_to_country, type_filter=type_filter)

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out['total_airports']} airports across {out['total_countries']} countries -> {OUT_PATH}")

    if out["unmatched_country_names"]:
        print(
            f"\n{out['skipped_unmatched_country']} airport(s) skipped -- "
            f"{len(out['unmatched_country_names'])} unmatched country string(s):"
        )
        for name in out["unmatched_country_names"]:
            print(f"  {name!r}")
        print(
            "\nAdd recurring misses to EXTRA_ALIASES in build_country_aliases.py "
            "(mapped to the correct iso3), then rerun that script and this one."
        )


if __name__ == "__main__":
    main()
