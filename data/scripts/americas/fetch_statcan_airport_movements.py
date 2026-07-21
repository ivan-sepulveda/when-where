"""
Fetch Statistics Canada table 23-10-0304-01 -- "Domestic and international
itinerant movements, by geography, airports with NAV CANADA services and
other selected airports, monthly" -- and write the full table (every
airport, every available month) to a single tidy CSV.

By default this keeps everything the table has -- no date range, no airport
filter. `CITY_AIRPORT_PATTERNS` (below) is still available for narrowing to
this project's curated Canadian destination cities (reference/
tourist_cities.json) via `--cities-only`, and `--years-back`/`--start-date`/
`--end-date` for narrowing the time range, but neither is applied unless
asked for.

Unlike the other sources in this project, this one isn't reached through
open.canada.ca's own CKAN API -- StatCan tables aren't loaded into CKAN's
datastore (`datastore_active: false` on every resource of this dataset), so
open.canada.ca only hosts metadata + a link out to the real thing:
Statistics Canada's Web Data Service (WDS), a REST API in front of the same
"CODR" tables shown on statcan.gc.ca. The bulk-download route used here:

    GET https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{productId}/en
    -> {"status": "SUCCESS", "object": "<url of a .zip containing the full table CSV>"}

`productId` is the table number with the "-01" suffix and dashes stripped:
23-10-0304-01 -> 23100304. This call is a GET with no API key, confirmed live
against the real endpoint (see the note near the bottom of this docstring).
The zip it points to (currently
https://www150.statcan.gc.ca/n1/tbl/csv/23100304-eng.zip) contains two CSVs:
the full data table (`23100304.csv`) and a metadata sidecar
(`23100304_MetaData.csv`) -- only the former is used here.

The data CSV follows StatCan's standard full-table export schema (confirmed
against the column list the user supplied, which matches this table
exactly): `REF_DATE, GEO, DGUID, Airports, Domestic and international
itinerant movements, UOM, UOM_ID, SCALAR_FACTOR, SCALAR_ID, VECTOR,
COORDINATE, VALUE, STATUS, SYMBOL, TERMINATED, DECIMALS`. `REF_DATE` is
"YYYY-MM". `Airports` is a specific airport's full name + province, e.g.
"Toronto/Lester B. Pearson International, Ontario" -- not the city alone --
so matching a city requires a substring lookup, not an exact join. `Domestic
and international itinerant movements` (same name as the table's title) is
the table's one non-geography breakdown dimension -- expect category values
like "Total itinerant movements", "Domestic", "Transborder", "Other
international" rather than every row meaning the same thing; keep this
column in the output rather than assuming a single value throughout.

Airport matching (`CITY_AIRPORT_PATTERNS` below): built from well-established
Canadian airport naming conventions (these exact names appear across many
public NAV CANADA / StatCan aviation tables), NOT confirmed against a live
pull of this specific table -- this sandbox cannot reach statcan.gc.ca at
all (see note below), so the match patterns are our best offline knowledge,
not a verified fact. **The first live run of this script should be spot-
checked**: `report_unmatched_patterns()` prints any configured city whose
pattern matched zero rows, which is the signal a name needs correcting.
Several suburb cities in `tourist_cities.json` (Mississauga, Brampton,
Markham, Vaughan -- all Toronto suburbs; Laval, Longueuil -- Montreal
suburbs; Gatineau -- across the river from Ottawa; Surrey, Burnaby --
Vancouver suburbs) have no airport of their own in this table, so they're
deliberately mapped to their metro area's airport as a shared proxy
(`is_proxy: True` in the config, carried through to the `match_type` output
column) rather than silently dropped or given fabricated dedicated data.
Oshawa and St. Catharines are left unmapped -- their local airports
(Oshawa Executive, Niagara District) are small GA fields not expected to be
part of the NAV CANADA / "other selected airports" scope this table covers,
and guessing would be worse than leaving them out; `report_unmatched_patterns()`
covers configured-but-zero-match cities, not unconfigured ones, so this is a
separate, deliberate omission -- see CITY_AIRPORT_PATTERNS comments.

Usage:
    python fetch_statcan_airport_movements.py                      # everything: all airports, all time
    python fetch_statcan_airport_movements.py --cities-only        # curated Canadian destination cities only
    python fetch_statcan_airport_movements.py --years-back 5       # last 5 years, all airports
    python fetch_statcan_airport_movements.py --start-date 2020-01 --end-date 2025-12
    python fetch_statcan_airport_movements.py --cities-only --years-back 5
    python fetch_statcan_airport_movements.py --force-download      # bypass the raw/ zip cache

Output is always processed/statcan_airport_movements.csv, regardless of
which filters are applied -- rerunning with different flags overwrites it.

API docs: https://www.statcan.gc.ca/en/developers/wds/user-guide
Dataset page: https://open.canada.ca/data/en/dataset/0b985486-61b6-45a9-bb99-db4116c29fe1

Note on verification: this sandbox's network allowlist blocks
`statcan.gc.ca` entirely for outbound shell/requests calls (confirmed --
`curl` to the zip URL returns a proxy 403), the same restriction that's
blocked every other live source in this project (see World Bank/Eurostat/
e-Stat notes in data/README.md). A separate fetch tool with different
network access WAS able to reach the WDS API directly: `GET
.../getFullTableDownloadCSV/23100304/en` returned
`{"status":"SUCCESS","object":"https://www150.statcan.gc.ca/n1/tbl/csv/23100304-eng.zip"}`
live, confirming the productId, the endpoint, and the zip URL are all
correct as of 2026-07-20. That same tool could not fetch the zip's binary
contents (it renders pages, not arbitrary binary downloads), so the actual
data rows, exact `Airports` column spellings, and the `Domestic and
international itinerant movements` category values are NOT verified here.
`filter_movements()` and `match_city()` were verified offline against a
synthetic fixture built to match the documented schema (see
tests/test_fetch_statcan_airport_movements.py if present, or the
`_self_check()` function below) -- not real StatCan rows. Run this for real
on a machine that can reach statcan.gc.ca, then check the printed unmatched-
pattern warnings before trusting the output.
"""

import argparse
import io
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd
import requests

PRODUCT_ID = "23100304"
WDS_DOWNLOAD_URL_TEMPLATE = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/{product_id}/en"

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "statcan_airport_movements"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed"
OUTPUT_FILENAME = "statcan_airport_movements.csv"

# city (must match reference/tourist_cities.json's "city" field exactly) ->
# (list of case-insensitive substrings to match against the Airports column,
#  is_proxy: True if this is a shared regional airport rather than the
#  city's own, note: human-readable justification).
CITY_AIRPORT_PATTERNS = {
    "Toronto": (["toronto"], False, "Toronto/Lester B. Pearson International"),
    "Montréal": (["montr"], False, "Montréal/Pierre Elliott Trudeau International (matches accented + unaccented spelling)"),
    "Vancouver": (["vancouver"], False, "Vancouver International"),
    "Calgary": (["calgary"], False, "Calgary International"),
    "Edmonton": (["edmonton"], False, "Edmonton International"),
    "Ottawa": (["ottawa"], False, "Ottawa/Macdonald-Cartier International"),
    "Winnipeg": (["winnipeg"], False, "Winnipeg/James Armstrong Richardson International"),
    "Quebec City": (["québec", "quebec"], False, "Québec/Jean Lesage International"),
    "Hamilton": (["hamilton"], False, "Hamilton/John C. Munro International"),
    "Halifax": (["halifax"], False, "Halifax/Robert L. Stanfield International"),
    "Victoria": (["victoria"], False, "Victoria International"),
    "Windsor": (["windsor"], False, "Windsor International"),
    "London": (["london"], False, "London International, Ontario -- Canadian table, no risk of matching UK London"),
    "Saskatoon": (["saskatoon"], False, "Saskatoon/John G. Diefenbaker International"),
    "Regina": (["regina"], False, "Regina International"),
    "Kitchener": (["kitchener", "waterloo", "region of waterloo"], False, "Region of Waterloo International"),
    # Suburb cities with no airport of their own -- mapped to the metro
    # area's airport as a shared proxy. `is_proxy=True` flows through to the
    # `match_type` output column so downstream code can tell these apart
    # from a city's own dedicated airport.
    "Mississauga": (["toronto"], True, "Toronto suburb -- shares Pearson"),
    "Brampton": (["toronto"], True, "Toronto suburb -- shares Pearson"),
    "Markham": (["toronto"], True, "Toronto suburb -- shares Pearson"),
    "Vaughan": (["toronto"], True, "Toronto suburb -- shares Pearson"),
    "Laval": (["montr"], True, "Montreal suburb -- shares Trudeau"),
    "Longueuil": (["montr"], True, "Montreal suburb -- shares Trudeau"),
    "Gatineau": (["ottawa"], True, "Across the river from Ottawa -- shares Macdonald-Cartier"),
    "Surrey": (["vancouver"], True, "Vancouver suburb -- shares Vancouver International"),
    "Burnaby": (["vancouver"], True, "Vancouver suburb -- shares Vancouver International"),
    # Deliberately NOT mapped: Oshawa (Oshawa Executive -- small GA field,
    # unlikely to be in this table's NAV CANADA / "other selected airports"
    # scope) and St. Catharines (Niagara District -- same reasoning). Guessing
    # a match here would be worse than leaving them out -- see docstring.
}


def resolve_zip_url(product_id: str = PRODUCT_ID) -> str:
    """Ask StatCan's WDS API for the current bulk-download zip URL, rather
    than hardcoding it -- StatCan reissues these URLs on table updates."""
    url = WDS_DOWNLOAD_URL_TEMPLATE.format(product_id=product_id)
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "SUCCESS" or "object" not in payload:
        raise ValueError(f"Unexpected WDS response for product {product_id}: {payload!r}")
    return payload["object"]


def download_and_extract(zip_url: str, force: bool = False) -> Path:
    """Download the table zip (cached in raw/ unless --force-download) and
    extract the main data CSV (skip the *_MetaData.csv sidecar)."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = RAW_DIR / f"{PRODUCT_ID}.zip"

    if force or not zip_path.exists():
        print(f"[{PRODUCT_ID}] downloading {zip_url} ...")
        resp = requests.get(zip_url, timeout=120)
        resp.raise_for_status()
        zip_path.write_bytes(resp.content)
    else:
        print(f"[{PRODUCT_ID}] using cached {zip_path} (--force-download to bypass)")

    with zipfile.ZipFile(zip_path) as zf:
        data_names = [n for n in zf.namelist() if n.lower().endswith(".csv") and "metadata" not in n.lower()]
        if not data_names:
            raise ValueError(f"No data CSV found in {zip_path} -- contents: {zf.namelist()}")
        csv_name = data_names[0]
        extracted_path = RAW_DIR / csv_name
        with zf.open(csv_name) as src, open(extracted_path, "wb") as dst:
            dst.write(src.read())

    return extracted_path


def match_city(airport_value: str) -> tuple[str, bool] | tuple[None, None]:
    """Return (city, is_proxy) for the first CITY_AIRPORT_PATTERNS entry
    whose pattern matches `airport_value` (case-insensitive substring), or
    (None, None) if nothing matches. First match wins -- patterns are
    specific enough (city/airport names) that this project doesn't expect
    genuine ambiguity, but check `report_unmatched_patterns()` output if a
    surprising city shows up in the results."""
    lowered = airport_value.lower()
    for city, (patterns, is_proxy, _note) in CITY_AIRPORT_PATTERNS.items():
        if any(p.lower() in lowered for p in patterns):
            return city, is_proxy
    return None, None


def report_unmatched_patterns(df: pd.DataFrame) -> None:
    """Print a warning for any configured city whose pattern matched zero
    rows -- the signal an airport name in CITY_AIRPORT_PATTERNS is wrong."""
    matched_cities = set(df["city"].dropna().unique()) if "city" in df.columns else set()
    missing = [city for city in CITY_AIRPORT_PATTERNS if city not in matched_cities]
    if missing:
        print(
            f"WARNING: {len(missing)} configured city/cities matched zero rows -- "
            f"check CITY_AIRPORT_PATTERNS spelling against the real Airports column: "
            f"{', '.join(missing)}"
        )


def filter_movements(
    df: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
    filter_cities: bool = False,
) -> pd.DataFrame:
    """Filter to a REF_DATE range and (optionally) to airports matching
    CITY_AIRPORT_PATTERNS, tagging each matched row with its city and
    match_type (own_airport / shared_proxy)."""
    out = df.copy()
    out["REF_DATE"] = out["REF_DATE"].astype(str)

    if start_date:
        out = out[out["REF_DATE"] >= start_date]
    if end_date:
        out = out[out["REF_DATE"] <= end_date]

    if filter_cities:
        matches = out["Airports"].astype(str).map(match_city)
        out = out.assign(
            city=[m[0] for m in matches],
            is_proxy=[m[1] for m in matches],
        )
        out = out[out["city"].notna()]
        out["match_type"] = out["is_proxy"].map({True: "shared_proxy", False: "own_airport"})
        out = out.drop(columns=["is_proxy"])

    return out


def write_outputs(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    return out_path


def fetch_dataset(
    start_date: str | None = None,
    end_date: str | None = None,
    filter_cities: bool = False,
    force_download: bool = False,
) -> Path:
    zip_url = resolve_zip_url()
    csv_path = download_and_extract(zip_url, force=force_download)

    print(f"[{PRODUCT_ID}] reading {csv_path} ...")
    df = pd.read_csv(csv_path, low_memory=False)

    filtered = filter_movements(df, start_date=start_date, end_date=end_date, filter_cities=filter_cities)
    if filter_cities:
        report_unmatched_patterns(filtered)

    out_path = write_outputs(filtered)
    print(f"[{PRODUCT_ID}] wrote {len(filtered)} rows -> {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--years-back",
        type=int,
        default=None,
        help="How many years of history to keep, counted back from today. "
        "Ignored if --start-date is also given. Default: no limit (all available history).",
    )
    parser.add_argument("--start-date", default=None, help="REF_DATE lower bound, 'YYYY-MM'.")
    parser.add_argument("--end-date", default=None, help="REF_DATE upper bound, 'YYYY-MM'.")
    parser.add_argument(
        "--cities-only",
        action="store_true",
        help="Filter to airports matching CITY_AIRPORT_PATTERNS (this project's curated Canadian "
        "destination cities) instead of keeping every airport in the table.",
    )
    parser.add_argument("--force-download", action="store_true", help="Bypass the cached raw/ zip.")
    args = parser.parse_args()

    start_date = args.start_date
    if start_date is None and args.years_back is not None:
        cutoff = date.today().replace(year=date.today().year - args.years_back)
        start_date = cutoff.strftime("%Y-%m")

    fetch_dataset(
        start_date=start_date,
        end_date=args.end_date,
        filter_cities=args.cities_only,
        force_download=args.force_download,
    )


if __name__ == "__main__":
    main()
