"""
Compares Michelin restaurant locations against the tourist cities
reference list and reports which Michelin (city, country) pairs aren't
tracked -- a candidate list for expanding `ADDITIONAL_CITIES` in
fetch_tourist_cities.py, and a sanity check on how much Michelin
coverage the population cutoff actually captures. Handles several
real-world matching gotchas: country-string normalization, inconsistent
diacritics between the two sources, trailing US state-code suffixes,
city-name-is-the-country cases (Singapore, Dubai, etc.), and genuine
name variants (Seville vs Sevilla). See data/README.md for the full
matching writeup and how to add new cases.

Usage:
    python diff_michelin_vs_tourist_cities.py
"""

import re
from pathlib import Path

import pandas as pd
from city_lookup import resolve_city_alias
from country_lookup import normalize_country

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TOURIST_CITIES_PATH = Path(__file__).resolve().parent.parent / "reference" / "tourist_cities.json"
# Input lives under processed/multiple/ (fetch_michelin_restaurants.py is a
# "multiple" fetch script); this script's own output stays at processed/
# root since it isn't a geography-scoped fetch itself.
MICHELIN_CSV_PATH = Path(__file__).resolve().parent.parent / "processed" / "multiple" / "michelin_restaurants.csv"
OUT_CSV_PATH = Path(__file__).resolve().parent.parent / "processed" / "michelin_cities_missing_from_tourist_cities.csv"

# Michelin Location values that are a bare city name (no ", Country") because
# the city itself is the country/territory.
CITY_ONLY_COUNTRY = {
    "singapore": "SGP",
    "dubai": "ARE",
    "abu dhabi": "ARE",
    "macau": "MAC",
    "luxembourg": "LUX",
}

_STATE_SUFFIX_RE = re.compile(r"^(.*),\s*([A-Z]{2})$")

# ---------------------------------------------------------------------------


def _clean_city(raw_city: str) -> str:
    """Strip a trailing US state-code suffix, if the city field still has one."""
    c = str(raw_city).strip()
    m = _STATE_SUFFIX_RE.match(c)
    return m.group(1).strip() if m else c


def load_tourist_city_pairs() -> tuple[set[tuple[str, str]], int]:
    """(city or city_ascii casefolded, iso3) pairs from tourist_cities.json -- both spellings."""
    import json

    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    pairs = set()
    for c in data["cities"]:
        pairs.add((c["city"].strip().casefold(), c["iso3"]))
        pairs.add((c["city_ascii"].strip().casefold(), c["iso3"]))
    return pairs, len(data["cities"])


def build_diff() -> pd.DataFrame:
    tourist_pairs, tourist_total = load_tourist_city_pairs()
    mich = pd.read_csv(MICHELIN_CSV_PATH)

    mich = mich.copy()
    mich["clean_city"] = mich["location_city"].apply(_clean_city)
    mich["iso3"] = [
        normalize_country(cc) if pd.notna(cc) else CITY_ONLY_COUNTRY.get(str(city).casefold())
        for cc, city in zip(mich["location_country"], mich["clean_city"])
    ]

    pair_counts = (
        mich.groupby(["clean_city", "iso3"]).size().reset_index(name="restaurant_count")
    )
    pair_counts["key"] = [
        (resolve_city_alias(city, iso3) or city.strip().casefold(), iso3)
        for city, iso3 in zip(pair_counts["clean_city"], pair_counts["iso3"])
    ]
    pair_counts["in_tourist_cities"] = pair_counts["key"].isin(tourist_pairs)

    total_pairs = len(pair_counts)
    found = int(pair_counts["in_tourist_cities"].sum())
    print(f"tourist_cities.json has {tourist_total} cities")
    print(f"distinct (city, country) pairs in michelin_restaurants.csv: {total_pairs}")
    print(f"found in tourist_cities.json: {found}")
    print(f"NOT found: {total_pairs - found}")

    missing = (
        pair_counts[~pair_counts["in_tourist_cities"]]
        .drop(columns=["key", "in_tourist_cities"])
        .sort_values("restaurant_count", ascending=False)
        .rename(columns={
            "clean_city": "City",
            "iso3": "Country (ISO3)",
            "restaurant_count": "Restaurant Count",
        })
    )
    missing.insert(0, "Rank", range(1, len(missing) + 1))
    return missing


def main():
    missing = build_diff()
    missing.to_csv(OUT_CSV_PATH, index=False)
    print(f"Wrote {len(missing)} rows -> {OUT_CSV_PATH}")


if __name__ == "__main__":
    main()
