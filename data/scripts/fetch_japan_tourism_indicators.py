"""
Fetch two Japan Statistics Dashboard (e-Stat) indicators -- monthly
foreign-national entries and monthly foreign-visitor guest nights,
nationwide -- and join them into one tidy CSV, one row per month.

Source: the e-Stat Statistics Dashboard WebAPI (dashboard.e-stat.go.jp) --
NOT the main e-Stat API. No Application ID / registration required (see
https://dashboard.e-stat.go.jp/en/static/api). Its `getData` response is
a flat list of {time, value} observations per indicator, much simpler
than Eurostat's JSON-stat hypercube (see fetch_eurostat_dataset.py) --
no positional-index decoding needed.

Two indicators, joined on (year, month):
  - NUM_ENTRIES: "Number of entries (Foreign nationals)"
    (indicator 0204030003000010010, source: Statistics on Legal Migrants,
    i.e. Ministry of Justice border-crossing data). Counts ALL
    foreign-national entries/re-entries at the border -- not filtered to
    tourism purpose. This is the closest available proxy for "Visitor
    Arrivals to Japan" through this API (JNTO's own arrivals figure
    isn't published here), so expect it to run a bit higher than an
    official visitor-arrivals count would (it includes work-visa
    holders, returning long-term residents, etc.).
  - NUM_GUEST_NIGHTS: "Number of guest nights (Foreign visitors)"
    (indicator 1003010201000110000, source: Accommodation Survey). Total
    nights foreign visitors (no address in Japan) spent at surveyed
    accommodation facilities.

Both pulled at RegionalRank=2 (nationwide Japan) and
IsSeasonalAdjustment=1 (original, non-seasonally-adjusted figures).
NUM_GUEST_NIGHTS is also available at RegionalRank=3 (prefecture level,
all 47 prefectures) if destination-level granularity is wanted later --
not used here since NUM_ENTRIES has no prefecture breakdown (it's a
border-crossing stat, not tied to a destination) and the two need a
shared grain to join. See data/README.md for the full API research notes.

Usage:
    python fetch_japan_tourism_indicators.py
    python fetch_japan_tourism_indicators.py --since 2024-01
"""

import argparse
import csv
import json
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

DEFAULT_SINCE = "2025-01"  # YYYY-MM, inclusive

# Each entry becomes one output column. "code" = the e-Stat Dashboard
# indicator code, "name" = its English display name (for reference/logging).
INDICATORS = {
    "NUM_ENTRIES": {
        "code": "0204030003000010010",
        "name": "Number of entries (Foreign nationals)",
    },
    "NUM_GUEST_NIGHTS": {
        "code": "1003010201000110000",
        "name": "Number of guest nights (Foreign visitors)",
    },
}

COUNTRY_CODE = "JP"
COUNTRY_NAME = "Japan"

OUTPUT_FILENAME = "japan_tourism_indicators_by_month.csv"

# ---------------------------------------------------------------------------

BASE_URL = "https://dashboard.e-stat.go.jp/api/1.0/Json/getData"
RAW_DIR = Path(__file__).resolve().parent.parent / "raw" / "estat_japan"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"


def _to_time_from(since: str) -> str:
    """'2025-01' -> '20250100', the e-Stat Dashboard's month time-code format."""
    year, month = since.split("-")
    return f"{int(year):04d}{int(month):02d}00"


def fetch_indicator(indicator_code: str, since: str) -> dict:
    params = {
        "Lang": "EN",
        "IndicatorCode": indicator_code,
        "Cycle": "1",  # Month
        "RegionalRank": "2",  # Nationwide (Japan)
        "IsSeasonalAdjustment": "1",  # Original figures (not seasonally adjusted)
        "TimeFrom": _to_time_from(since),
        "MetaGetFlg": "Y",
        "SectionHeaderFlg": "1",
    }
    resp = requests.get(BASE_URL, params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    result = payload.get("GET_STATS", {}).get("RESULT", {})
    if result.get("status") != "0":
        raise ValueError(f"e-Stat API error for indicator {indicator_code!r}: {result.get('errorMsg')}")
    return payload


def parse_monthly_values(payload: dict) -> dict[tuple[int, int], int]:
    """{(year, month): value} from a getData response's DATA_OBJ list."""
    data_objs = payload["GET_STATS"]["STATISTICAL_DATA"]["DATA_INF"]["DATA_OBJ"]
    values = {}
    for obj in data_objs:
        v = obj["VALUE"]
        time_code = v["@time"]  # "YYYYMM00"
        year, month = int(time_code[:4]), int(time_code[4:6])
        values[(year, month)] = int(v["$"])
    return values


def save_raw_json(column: str, payload: dict) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / f"{column.lower()}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path


def build_rows(since: str) -> list[dict]:
    series: dict[str, dict[tuple[int, int], int]] = {}
    for column, info in INDICATORS.items():
        print(f"Fetching {info['name']} ({info['code']})...")
        payload = fetch_indicator(info["code"], since)
        save_raw_json(column, payload)
        series[column] = parse_monthly_values(payload)

    # Union of months across both indicators -- they've matched exactly so
    # far, but don't assume that holds forever (different sources, could
    # develop different reporting lags).
    all_months = sorted(set().union(*(s.keys() for s in series.values())))

    rows = []
    for year, month in all_months:
        row = {
            "COUNTRY": COUNTRY_CODE,
            "COUNTRY_NAME": COUNTRY_NAME,
            "MONTH": f"{year:04d}-{month:02d}",
        }
        for column in INDICATORS:
            row[column] = series[column].get((year, month))  # None if that source is missing this month
        rows.append(row)
    return rows


def write_csv(rows: list[dict]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    fieldnames = ["COUNTRY", "COUNTRY_NAME", "MONTH", *INDICATORS.keys()]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help=f"Earliest month to pull, YYYY-MM (default: {DEFAULT_SINCE})",
    )
    args = parser.parse_args()

    rows = build_rows(args.since)
    if not rows:
        raise SystemExit("No data returned -- check --since and the indicator codes in INDICATORS.")

    out_path = write_csv(rows)
    print(f"Wrote {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()
