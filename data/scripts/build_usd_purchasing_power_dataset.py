"""
Data Source: World Bank Data360 API, World Development Indicators (WDI),
indicator PA.NUS.GDP.PLI (Price level index, GDP)
URL: https://data360api.worldbank.org
Tables Referenced: data/processed/multiple/worldbank_PA.NUS.GDP.PLI_<year>_by_country.json

Builds a one-row-per-country USD purchasing power dataset for every
country in PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv, from the Price Level
Index (PLI) already fetched by fetch_worldbank_indicator.py. PLI is the
PPP conversion factor divided by the market exchange rate, rebased so
USA = 100 -- it answers "how far does a dollar go here" directly, with
no separate currency-conversion step needed. This script just re-expresses
that same ratio as USD_PURCHASING_POWER = 100 / PLI: literally, what a
single US dollar's real buying power is worth in US-dollar-equivalent
terms in that country. A value of 1.50 means $1 there buys what $1.50
would buy in the US (cheaper); 0.80 means it buys what $0.80 would buy
in the US (pricier).

Countries are matched to the World Bank data by name (via
country_lookup.normalize_country), not by the Eurostat-style codes in
PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv's own COUNTRY column, since a
couple of those codes (e.g. Eurostat's "EL" for Greece) don't match
standard ISO -- matching on name sidesteps that entirely.

Usage:
    python build_usd_purchasing_power_dataset.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from country_lookup import normalize_country  # noqa: E402

PROCESSED_DIR = SCRIPTS_DIR.parent / "processed"
PEAK_TOURISM_PATH = PROCESSED_DIR / "PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv"
PLI_GLOB = "worldbank_PA.NUS.GDP.PLI_*_by_country.json"
OUTPUT_PATH = PROCESSED_DIR / "usd_purchasing_power_by_country.csv"


def find_pli_path() -> Path:
    matches = sorted((PROCESSED_DIR / "multiple").glob(PLI_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(
            f"No file matching {PLI_GLOB!r} in {PROCESSED_DIR / 'multiple'}/ -- run "
            f"scripts/multiple/fetch_worldbank_indicator.py PA.NUS.GDP.PLI first, "
            f"then scripts/multiple/fetch_latest_by_country.py."
        )
    if len(matches) > 1:
        print(f"Note: multiple files match {PLI_GLOB!r} -- using the most recently modified: {matches[0].name}")
    return matches[0]


def build_dataset() -> pd.DataFrame:
    peak_tourism = pd.read_csv(PEAK_TOURISM_PATH)
    countries = peak_tourism[["COUNTRY", "COUNTRY_NAME"]].drop_duplicates().sort_values("COUNTRY_NAME")

    pli_path = find_pli_path()
    with open(pli_path, encoding="utf-8") as f:
        pli = json.load(f)
    pli_data = pli["data"]
    pli_year = pli["year"]

    rows = []
    unmatched = []
    for _, row in countries.iterrows():
        iso3 = normalize_country(row["COUNTRY_NAME"])
        entry = pli_data.get(iso3) if iso3 else None
        if entry is None:
            unmatched.append((row["COUNTRY"], row["COUNTRY_NAME"]))
            continue
        price_level_index = entry["value"]
        rows.append({
            "COUNTRY": row["COUNTRY"],
            "COUNTRY_NAME": row["COUNTRY_NAME"],
            "PRICE_LEVEL_INDEX": round(price_level_index, 2),
            "USD_PURCHASING_POWER": round(100 / price_level_index, 4),
            "SOURCE_YEAR": pli_year,
        })

    if unmatched:
        print(f"WARNING: {len(unmatched)} country(ies) with no PLI match: {unmatched}")

    return pd.DataFrame(rows).sort_values("USD_PURCHASING_POWER", ascending=False).reset_index(drop=True)


def main():
    df = build_dataset()
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(df)} rows -> {OUTPUT_PATH}")

    cheapest = df.iloc[0]
    priciest = df.iloc[-1]
    print(f"Sanity check -- most purchasing power: {cheapest['COUNTRY_NAME']} "
          f"($1 = ${cheapest['USD_PURCHASING_POWER']:.2f} US-equivalent)")
    print(f"Sanity check -- least purchasing power: {priciest['COUNTRY_NAME']} "
          f"($1 = ${priciest['USD_PURCHASING_POWER']:.2f} US-equivalent)")


if __name__ == "__main__":
    main()
