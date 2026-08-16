"""
Data Source: OpenFlights Airport Database
URL: https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat
Tables Referenced: airports.dat (no header row; 14 comma-separated columns, `\\N` = null)

Downloads OpenFlights' airport list -- ~7,700 airports, heliports, and
airfields worldwide with names and coordinates -- and writes
data/reference/airports.json. This project only uses it for lat/long
(to compute great-circle distance between an origin and a destination),
not for route/connectivity data: OpenFlights' *route* database
(routes.dat) hasn't been updated since June 2014 and is unreliable for
"does this flight currently exist," but airport locations don't go
stale the same way, so airports.dat is still a fine coordinates source.

FILTERING -- read this before changing it:

Each row has a `type` column, which OpenFlights documents as
"airport", "heliport", "station", etc. In practice, in the main
airports.dat, **every single one of the 7,698 rows is typed
"airport"** -- the other values only appear in OpenFlights' extended
dataset. So `--type airport` (the default) is effectively a no-op and
does NOT drop heliports, despite what it looks like. This was a real
bug: "New York" ended up with JRB (Downtown-Manhattan/Wall St Heliport)
and JRA (West 30th St. Heliport) attached to it as if they were
commercial airports. The `--type` flag is kept because it still works
correctly if someone points this at the extended dataset, but it is not
what actually filters heliports out.

What actually filters them out is is_excluded_by_name() below: a
case-insensitive match on the airport's *name*. It drops

  * heliports and helipads ("... Heliport", "... Helipad")
  * air bases ("... Air Base", "... Airbase", "... Air Force Base")

because neither is somewhere a traveler can book a commercial flight
into, and both were polluting city->airport matching. Pass
--no-name-filter to keep them.

One carve-out: a handful of airports are *joint* civil-military fields
that OpenFlights names with both halves -- "Charleston Air Force
Base-International Airport" (CHS), "Sheppard Air Force Base-Wichita
Falls Municipal Airport" (SPS), "Cheongju International Airport/Cheongju
Air Base" (CJJ). Those are real commercial airports you can fly into,
and a naive air-base match wipes them out -- CHS is 11 km from
Charleston and was the city's only airport. So an air-base match is
overridden when the name also carries a civil marker
(CIVIL_MARKER_PATTERN: International/Municipal/Regional/Civil).
Heliports are never rescued this way -- they're excluded
unconditionally.

Known limitation: name matching is a heuristic and doesn't catch every
military field, because they aren't named consistently -- "Joint Base
Andrews", "Atsugi Naval Air Facility", "Davison Army Air Field" and the
"RAF <name>" fields all survive it. Catching those properly means
switching to OurAirports' airports.csv, which carries a real `type`
column plus a `scheduled_service` yes/no flag; that's a larger change
and hasn't been done.

Usage:
    python fetch_openflights_airports.py                    # airports only, name filter on (default)
    python fetch_openflights_airports.py --no-name-filter    # keep heliports and air bases
    python fetch_openflights_airports.py --all-types         # every row, no type filtering
    python fetch_openflights_airports.py --type heliport     # some other specific type
    python fetch_openflights_airports.py --force-download    # re-download even if cached
"""

import argparse
import json
import re
from pathlib import Path

import pandas as pd
import requests

DEFAULT_TYPE_FILTER = "airport"

# All case-insensitive.
#
# HELIPORT_PATTERN: excluded unconditionally.
#
# AIRBASE_PATTERN: `air\s*(force\s*)?base` covers "Air Base", "Airbase"
# (one word -- e.g. "Nordholz Naval Airbase") and "Air Force Base"
# (e.g. "Mc Guire Air Force Base"), which a plain "air base" match would
# miss since "Force" sits between the two words.
#
# CIVIL_MARKER_PATTERN: rescues joint civil-military fields from
# AIRBASE_PATTERN (see the module docstring). Deliberately does NOT
# include the bare word "Airport" -- plenty of purely military fields
# are named "... Air Force Base Airport", so that would rescue almost
# everything and defeat the filter.
HELIPORT_PATTERN = re.compile(r"heli(?:port|pad)", re.IGNORECASE)
AIRBASE_PATTERN = re.compile(r"air\s*(?:force\s*)?base", re.IGNORECASE)
CIVIL_MARKER_PATTERN = re.compile(r"international|municipal|regional|civil", re.IGNORECASE)


def is_excluded_by_name(name: str) -> bool:
    """True if this airport's name marks it as a heliport, or as an air
    base that isn't also a civil airport."""
    if not isinstance(name, str):
        return False
    if HELIPORT_PATTERN.search(name):
        return True
    return bool(AIRBASE_PATTERN.search(name)) and not CIVIL_MARKER_PATTERN.search(name)

SOURCE_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"
RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "openflights"
REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
RAW_PATH = RAW_DIR / "airports.dat"
OUT_PATH = REFERENCE_DIR / "airports.json"

ATTRIBUTION = (
    "OpenFlights Airport Database -- "
    "https://openflights.org/data.php (coordinates only; route data is "
    "historical/unmaintained since June 2014 and is not used here)"
)

# airports.dat has no header row -- column order per OpenFlights' docs.
COLUMNS = [
    "airport_id",
    "name",
    "city",
    "country",
    "iata",
    "icao",
    "latitude",
    "longitude",
    "altitude_ft",
    "timezone_utc_offset",
    "dst",
    "tz_database_time_zone",
    "type",
    "source",
]


def download_dat(force: bool = False) -> Path:
    """Download airports.dat into raw/, reusing the cached copy unless forced."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if RAW_PATH.exists() and not force:
        print(f"Using cached download: {RAW_PATH}")
        return RAW_PATH
    print(f"Downloading {SOURCE_URL} ...")
    resp = requests.get(SOURCE_URL, timeout=60)
    resp.raise_for_status()
    RAW_PATH.write_bytes(resp.content)
    print(f"Saved -> {RAW_PATH}")
    return RAW_PATH


def load_airports(dat_path: Path) -> pd.DataFrame:
    """Parse the raw .dat CSV into a typed DataFrame."""
    df = pd.read_csv(
        dat_path,
        header=None,
        names=COLUMNS,
        na_values=["\\N"],
        keep_default_na=True,
        encoding="utf-8",
    )
    return df


def _row_to_dict(row) -> dict:
    def clean(val):
        return None if pd.isna(val) else val

    return {
        "airport_id": int(row.airport_id),
        "name": row.name,
        "city": clean(row.city),
        "country": clean(row.country),
        "iata": clean(row.iata),
        "icao": clean(row.icao),
        "lat": float(row.latitude),
        "lng": float(row.longitude),
        "altitude_ft": None if pd.isna(row.altitude_ft) else int(row.altitude_ft),
        "timezone_utc_offset": None if pd.isna(row.timezone_utc_offset) else float(row.timezone_utc_offset),
        "dst": clean(row.dst),
        "tz_database_time_zone": clean(row.tz_database_time_zone),
        "type": clean(row.type),
        "source": clean(row.source),
    }


def build_airports(
    df: pd.DataFrame,
    type_filter: str | None = None,
    exclude_by_name: bool = True,
) -> dict:
    """Pure function: DataFrame in, output dict out. Kept separate from I/O for testing."""
    filtered = df
    if type_filter:
        filtered = filtered[filtered["type"].str.casefold() == type_filter.casefold()]

    excluded_by_name = 0
    if exclude_by_name:
        before = len(filtered)
        # is_excluded_by_name returns False for non-str (NaN) names, so
        # rows with a missing name are kept rather than silently dropped.
        excluded_mask = filtered["name"].map(is_excluded_by_name).astype(bool)
        filtered = filtered[~excluded_mask]
        excluded_by_name = before - len(filtered)

    airports = [_row_to_dict(row) for row in filtered.itertuples()]

    return {
        "source": ATTRIBUTION,
        "type_filter": type_filter,
        "name_filter": (
            f"exclude /{HELIPORT_PATTERN.pattern}/; "
            f"exclude /{AIRBASE_PATTERN.pattern}/ unless /{CIVIL_MARKER_PATTERN.pattern}/"
        )
        if exclude_by_name
        else None,
        "excluded_by_name": excluded_by_name,
        "total_airports": len(airports),
        "airports": airports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--type",
        default=DEFAULT_TYPE_FILTER,
        help=f"Keep only rows whose 'type' column matches this value. "
        f"Default: {DEFAULT_TYPE_FILTER!r}. NOTE: in the main airports.dat every row "
        f"is typed 'airport', so this is a no-op there -- heliports are dropped by the "
        f"name filter, not this. Use --all-types to disable type filtering entirely.",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Keep every row regardless of 'type' (private airstrips, heliports, stations, etc.). "
        "Overrides --type.",
    )
    parser.add_argument(
        "--no-name-filter",
        action="store_true",
        help="Keep heliports/helipads and air bases, which are excluded by default "
        "via a name match -- see is_excluded_by_name().",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download airports.dat even if a cached copy exists in raw/",
    )
    args = parser.parse_args()

    type_filter = None if args.all_types else args.type

    dat_path = download_dat(force=args.force_download)
    df = load_airports(dat_path)
    out = build_airports(df, type_filter=type_filter, exclude_by_name=not args.no_name_filter)

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    if out["excluded_by_name"]:
        print(f"Excluded {out['excluded_by_name']} heliports/air bases by name.")
    print(f"Wrote {out['total_airports']} airports -> {OUT_PATH}")


if __name__ == "__main__":
    main()
