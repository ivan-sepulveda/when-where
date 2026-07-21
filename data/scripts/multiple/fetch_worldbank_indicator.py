"""
Fetch a World Development Indicators (WDI) series from the World Bank's
Data360 API.

Data360 exposes WDI indicators as JSON, paginated at up to 1000 records per
call (use `skip` to page through). Indicator IDs are the classic WDI dotted
codes with dots replaced by underscores and a `WB_WDI_` prefix, e.g.
`NY.GDP.DEFL.KD.ZG` -> `WB_WDI_NY_GDP_DEFL_KD_ZG`.

Usage:
    python fetch_worldbank_indicator.py NY.GDP.DEFL.KD.ZG
    python fetch_worldbank_indicator.py NY.GDP.DEFL.KD.ZG SP.POP.TOTL

API docs: https://data360api.worldbank.org (see /swagger or the
Data360 Open API spec on GitHub: worldbank/open-api-specs)
"""

import argparse
import csv
import sys
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "worldbank"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed"

BASE_URL = "https://data360api.worldbank.org/data360/data"
DATABASE_ID = "WB_WDI"
PAGE_SIZE = 1000

# Tidy column subset pulled out of each raw record.
FIELDNAMES = [
    "ref_area",
    "indicator",
    "time_period",
    "obs_value",
    "unit_measure",
    "freq",
]


def to_data360_indicator_id(wdi_code: str) -> str:
    """NY.GDP.DEFL.KD.ZG -> WB_WDI_NY_GDP_DEFL_KD_ZG"""
    return f"{DATABASE_ID}_{wdi_code.replace('.', '_')}"


def fetch_all_records(indicator_id: str) -> list[dict]:
    """Page through the Data360 API until all records for one indicator are fetched."""
    rows = []
    skip = 0
    total = None

    while total is None or skip < total:
        resp = requests.get(
            BASE_URL,
            params={
                "DATABASE_ID": DATABASE_ID,
                "INDICATOR": indicator_id,
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
        print(f"  ...fetched {len(rows)}/{total}")

    return rows


def save_raw_json(wdi_code: str, rows: list[dict]) -> Path:
    import json

    out_dir = RAW_DIR / wdi_code
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{wdi_code}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    return out_path


def write_csv(wdi_code: str, rows: list[dict]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / f"worldbank_{wdi_code}.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            writer.writerow(
                {
                    "ref_area": r.get("REF_AREA"),
                    "indicator": r.get("INDICATOR"),
                    "time_period": r.get("TIME_PERIOD"),
                    "obs_value": r.get("OBS_VALUE"),
                    "unit_measure": r.get("UNIT_MEASURE"),
                    "freq": r.get("FREQ"),
                }
            )
    return out_path


def fetch_indicator(wdi_code: str) -> Path:
    indicator_id = to_data360_indicator_id(wdi_code)
    print(f"[{wdi_code}] fetching {indicator_id}...")

    rows = fetch_all_records(indicator_id)
    if not rows:
        raise ValueError(f"No records returned for {indicator_id}. Check the code.")

    save_raw_json(wdi_code, rows)
    out_path = write_csv(wdi_code, rows)
    print(f"[{wdi_code}] wrote {len(rows)} rows -> {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "indicator_codes",
        nargs="*",
        default=["NY.GDP.DEFL.KD.ZG"],
        help="One or more WDI indicator codes, dotted form (default: NY.GDP.DEFL.KD.ZG)",
    )
    args = parser.parse_args()

    for code in args.indicator_codes:
        try:
            fetch_indicator(code)
        except Exception as exc:
            print(f"[{code}] FAILED: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
