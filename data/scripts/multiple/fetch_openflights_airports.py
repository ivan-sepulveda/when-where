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

Each row in the output includes a `type` field ("airport", "heliport",
"station", etc., as tagged by OpenFlights/OurAirports). Defaults to
keeping only `type == "airport"` -- commercial/public airports, which is
what a trip's flight distance should be measured against -- and drops
heliports, train/bus stations, and other non-airport entries. Use
`--all-types` to keep everything, or `--type <value>` for some other
specific type.

Usage:
    python fetch_openflights_airports.py                    # airports only (default)
    python fetch_openflights_airports.py --all-types         # every row, no type filtering
    python fetch_openflights_airports.py --type heliport     # some other specific type
    python fetch_openflights_airports.py --force-download    # re-download even if cached
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import requests

DEFAULT_TYPE_FILTER = "airport"

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


def build_airports(df: pd.DataFrame, type_filter: str | None = None) -> dict:
    """Pure function: DataFrame in, output dict out. Kept separate from I/O for testing."""
    filtered = df
    if type_filter:
        filtered = df[df["type"].str.casefold() == type_filter.casefold()]

    airports = [_row_to_dict(row) for row in filtered.itertuples()]

    return {
        "source": ATTRIBUTION,
        "type_filter": type_filter,
        "total_airports": len(airports),
        "airports": airports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--type",
        default=DEFAULT_TYPE_FILTER,
        help=f"Keep only rows whose 'type' column matches this value. "
        f"Default: {DEFAULT_TYPE_FILTER!r} (commercial/public airports; drops "
        f"heliports/stations/etc.). Use --all-types to disable filtering entirely.",
    )
    parser.add_argument(
        "--all-types",
        action="store_true",
        help="Keep every row regardless of 'type' (private airstrips, heliports, stations, etc.). "
        "Overrides --type.",
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
    out = build_airports(df, type_filter=type_filter)

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out['total_airports']} airports -> {OUT_PATH}")


if __name__ == "__main__":
    main()
