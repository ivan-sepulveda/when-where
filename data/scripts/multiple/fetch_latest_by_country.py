"""
Fetch a WDI indicator's value for every country/region in our reference
list (data/reference/worldbank_countries.json), for the latest available
year (via latest_year_cache.get_latest_year), and write the result to a
single JSON file keyed by country code.

Usage:
    python fetch_latest_by_country.py
        Runs every indicator listed in reference/worldbank_metrics.json.
        This is the normal way to run it -- add a new indicator by adding
        an entry to that file, not by editing this script.
    python fetch_latest_by_country.py NY.GDP.DEFL.KD.ZG
    python fetch_latest_by_country.py NY.GDP.DEFL.KD.ZG SP.POP.TOTL
        Explicit codes on the command line override the registry and run
        just those (code doesn't need to be in worldbank_metrics.json --
        unit/name just fall back to generic values if it's not).

Not every country/region will have data for the latest year (reporting
lags vary a lot by country) -- those are listed under "missing_codes"
rather than silently dropped.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import requests

from latest_year_cache import BASE_URL, DATABASE_ID, get_latest_year, to_data360_indicator_id

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
COUNTRIES_PATH = REFERENCE_DIR / "worldbank_countries.json"
METRICS_PATH = REFERENCE_DIR / "worldbank_metrics.json"
PAGE_SIZE = 1000


def load_countries() -> dict:
    """code -> name, from the reference file built earlier from the WB bulk XML."""
    with open(COUNTRIES_PATH, encoding="utf-8") as f:
        return json.load(f)["countries"]


def load_metrics() -> dict:
    """
    WDI code -> {"code", "name", "unit", "notes"}, from the indicator
    registry at reference/worldbank_metrics.json. This is the single place
    that lists which indicators the project tracks -- add a new indicator
    by adding an entry here, not by editing this script.
    """
    with open(METRICS_PATH, encoding="utf-8") as f:
        metrics = json.load(f)["metrics"]
    return {m["code"]: m for m in metrics}


def fetch_year_records(indicator_id: str, year: int) -> list[dict]:
    """Page through the Data360 API for one indicator/year across all REF_AREAs."""
    rows = []
    skip = 0
    total = None

    while total is None or skip < total:
        resp = requests.get(
            BASE_URL,
            params={
                "DATABASE_ID": DATABASE_ID,
                "INDICATOR": indicator_id,
                "TIME_PERIOD": year,
                "top": PAGE_SIZE,
                "skip": skip,
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()

        batch = payload.get("value", [])
        if not batch:
            break

        rows.extend(batch)
        total = payload.get("count", len(rows))
        skip += PAGE_SIZE

    return rows


def build_country_lookup(records: list[dict]) -> dict:
    """REF_AREA -> record, dropping rows with no observed value."""
    return {
        r["REF_AREA"]: r
        for r in records
        if r.get("REF_AREA") and r.get("OBS_VALUE") not in (None, "")
    }


def build_country_indicator_json(wdi_code: str, metrics: dict | None = None) -> Path:
    metrics = metrics or {}
    meta = metrics.get(wdi_code, {})

    year = get_latest_year(wdi_code)
    indicator_id = to_data360_indicator_id(wdi_code)
    countries = load_countries()

    print(f"[{wdi_code}] latest year = {year}")
    print(f"[{wdi_code}] fetching {indicator_id} for {year}...")
    records = fetch_year_records(indicator_id, year)
    by_ref_area = build_country_lookup(records)

    data = {}
    missing = []
    for code, name in countries.items():
        rec = by_ref_area.get(code)
        if rec is None:
            missing.append(code)
            continue
        data[code] = {
            "country_name": name,
            "value": float(rec["OBS_VALUE"]),
        }

    out = {
        "indicator": wdi_code,
        "indicator_id": indicator_id,
        "name": meta.get("name", wdi_code),
        "unit": meta.get("unit", "unknown -- add this indicator to reference/worldbank_metrics.json"),
        "year": year,
        "generated": date.today().isoformat(),
        "countries_total": len(countries),
        "countries_with_data": len(data),
        "countries_missing_data": len(missing),
        "missing_codes": sorted(missing),
        "data": dict(sorted(data.items())),
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"worldbank_{wdi_code}_{year}_by_country.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(
        f"[{wdi_code}] wrote {len(data)}/{len(countries)} countries "
        f"({len(missing)} missing for {year}) -> {out_path}"
    )
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "indicator_codes",
        nargs="*",
        default=None,
        help=(
            "One or more WDI indicator codes. If omitted, runs every "
            "indicator listed in reference/worldbank_metrics.json."
        ),
    )
    args = parser.parse_args()

    metrics = load_metrics()
    codes = args.indicator_codes if args.indicator_codes else list(metrics.keys())

    if not codes:
        print("No indicator codes given and reference/worldbank_metrics.json is empty.", file=sys.stderr)
        sys.exit(1)

    for code in codes:
        try:
            build_country_indicator_json(code, metrics=metrics)
        except Exception as exc:
            print(f"[{code}] FAILED: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
