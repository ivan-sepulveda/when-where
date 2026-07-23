"""
Data Source: MMA Statistics Database (Maldives Monetary Authority), Table 3.1 Tourism Indicators
URL: https://database.mma.gov.mv/monthly-statistics/real/tourism-indicators
Tables Referenced: Table 3.1 Tourism Indicators, 2020 - 2026 (levels columns 1-12:
    total arrivals, bednights, average stay, bed capacity and occupancy rate,
    resorts in operation, arrival flights, travel receipts)

Fetches the 12 underlying series behind Table 3.1 through the MMA Statistics
API (SERIES_IDS below) and joins them into one tidy monthly CSV. Series IDs
were found by browsing the site's own Viya catalog (Real Sector > Tourism >
Tourism Indicators / International Flight Movements / Memorandum Items),
since the API itself has no name-search endpoint -- only fetch-by-ID. The
table's y/y %-change columns aren't separate series; they're computed here
from the same monthly levels with a 12-month percent change. Requires an
MMA_API_TOKEN in .env.local (see .env.local.example) -- register for one at
https://database.mma.gov.mv/api/register. Live fetching is unverified in
this sandbox, since its network allowlist blocks database.mma.gov.mv even
for the read-only API.

Usage:
    python fetch_maldives_mma_tourism_indicators.py
    python fetch_maldives_mma_tourism_indicators.py --since 2020-01
    python fetch_maldives_mma_tourism_indicators.py --list-series
"""

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_DIR = REPO_ROOT / "data" / "raw" / "mma_maldives"
PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "asia"
OUTPUT_FILENAME = "maldives_mma_tourism_indicators_monthly.csv"

BASE_URL = "https://database.mma.gov.mv/api/series"
COUNTRY_CODE = "MV"
COUNTRY_NAME = "Maldives"

# Column name -> (MMA series ID, display name for --list-series). IDs found
# via https://database.mma.gov.mv/viya/explore/102 (Real Sector > Tourism).
SERIES_IDS = {
    "total_arrivals": (104, "Total tourist arrivals"),
    "bednights": (205, "Bed nights"),
    "avg_stay_days": (210, "Average stay"),
    "operational_bed_capacity": (226, "Operational numbers (bed capacity)"),
    "bednight_capacity": (211, "Bed night capacity"),
    "registered_bed_capacity": (221, "Registered bed capacity"),
    "occupancy_rate_pct": (216, "Occupancy rate"),
    "resorts_in_operation": (239, "Operational numbers - Resorts"),
    "arrival_flights_total": (242, "Total number of arrival flights"),
    "arrival_flights_scheduled": (243, "Scheduled flights"),
    "arrival_flights_general": (244, "General flights"),
    "travel_receipts_musd": (246, "Travel receipts"),
}

# Table 3.1's y/y %-change block only covers these 8 of the 12 columns.
YOY_COLUMNS = [
    "total_arrivals",
    "bednights",
    "operational_bed_capacity",
    "bednight_capacity",
    "registered_bed_capacity",
    "arrival_flights_total",
    "arrival_flights_scheduled",
    "arrival_flights_general",
]


def get_token() -> str:
    load_dotenv(REPO_ROOT / ".env.local")
    token = os.getenv("MMA_API_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "MMA_API_TOKEN is not set. Copy .env.local.example to .env.local "
            "and fill in a real token from https://database.mma.gov.mv/api/register."
        )
    return token


def fetch_series_batch(ids: list[int], token: str) -> list[dict]:
    """Fetch one or more MMA series by ID, following pagination (the API
    returns at most `per_page` series per request, not per_page data points --
    see links.next in the response) until every requested series is back."""
    headers = {"Authorization": f"Bearer {token}"}
    url = BASE_URL
    params = {"ids": ",".join(str(i) for i in ids)}
    series = []

    while url:
        # Note: unlike the sample snippet in the API docs, we leave TLS
        # verification on (no verify=False) -- there's no reason to disable
        # certificate checking for a plain HTTPS GET.
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        series.extend(payload.get("data", []))

        url = payload.get("links", {}).get("next")
        params = None  # the `next` link already has query params baked in
    return series


def save_raw_json(series: list[dict]) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RAW_DIR / "tourism_indicators.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(series, f, indent=2, ensure_ascii=False)
    return out_path


def build_dataframe(series: list[dict], since: str | None) -> pd.DataFrame:
    id_to_column = {v[0]: k for k, v in SERIES_IDS.items()}
    found_ids = {s["id"] for s in series}
    missing = [f"{name} ({sid})" for sid, name in ((sid, n) for sid, n in [(v[0], v[1]) for v in SERIES_IDS.values()]) if sid not in found_ids]
    if missing:
        print(f"Warning: no data returned for: {', '.join(missing)}", file=sys.stderr)

    merged = None
    for s in series:
        column = id_to_column.get(s["id"])
        if column is None:
            continue  # a series we didn't ask for; ignore
        df = pd.DataFrame(s["data"])  # columns: date, amount
        if df.empty:
            continue
        df["ref_date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m")
        df = df[["ref_date", "amount"]].rename(columns={"amount": column})
        merged = df if merged is None else merged.merge(df, on="ref_date", how="outer")

    if merged is None:
        raise ValueError("No matching series data returned -- check SERIES_IDS and the API response.")

    merged = merged.sort_values("ref_date").reset_index(drop=True)
    if since:
        merged = merged[merged["ref_date"] >= since].reset_index(drop=True)

    # Y/Y %-change columns, matching Table 3.1's "Period y/y % change" block --
    # computed locally rather than fetched, since MMA doesn't publish these as
    # separate series. Looked up by calendar date (same month, prior year)
    # rather than a positional 12-row shift, so a missing month in one
    # series' history doesn't silently misalign the comparison.
    for column in YOY_COLUMNS:
        if column not in merged.columns:
            continue
        by_ref_date = merged.set_index("ref_date")[column]
        prior_ref_date = (pd.to_datetime(merged["ref_date"]) - pd.DateOffset(years=1)).dt.strftime("%Y-%m")
        prior_values = prior_ref_date.map(by_ref_date)
        merged[f"{column}_yoy_pct"] = (merged[column] / prior_values - 1) * 100

    merged.insert(0, "country_name", COUNTRY_NAME)
    merged.insert(0, "country", COUNTRY_CODE)
    return merged


def write_output(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    return out_path


def list_series():
    print(f"{'column':<28} {'id':>5}  name")
    for column, (series_id, name) in SERIES_IDS.items():
        print(f"{column:<28} {series_id:>5}  {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--since", default=None, help="Earliest month to keep, YYYY-MM (default: full history)")
    parser.add_argument("--list-series", action="store_true", help="Print the column -> series ID mapping and exit")
    args = parser.parse_args()

    if args.list_series:
        list_series()
        return

    token = get_token()
    ids = [v[0] for v in SERIES_IDS.values()]
    print(f"Fetching {len(ids)} series from {BASE_URL} ...")
    series = fetch_series_batch(ids, token)
    save_raw_json(series)

    df = build_dataframe(series, args.since)
    out_path = write_output(df)
    print(f"Wrote {len(df)} rows ({df['ref_date'].min()} - {df['ref_date'].max()}) -> {out_path}")


if __name__ == "__main__":
    main()
