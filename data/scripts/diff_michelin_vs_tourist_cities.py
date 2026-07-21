"""
Compare processed/multiple/michelin_restaurants.csv against reference/tourist_cities.json
and report which Michelin (city, country) pairs aren't in the tourist cities
list -- a candidate list for expanding ADDITIONAL_CITIES in
fetch_tourist_cities.py, and a sanity check on how much Michelin coverage the
current TOP_N_CITIES_BY_POPULATION cutoff actually captures.

Matching notes (see data/README.md for the full writeup):
  - Country strings are normalized to iso3 via country_lookup.normalize_country()
    -- raw string matching fails on things like "USA" vs "United States" or
    "Chinese Mainland" vs "China".
  - City strings are matched against BOTH tourist_cities.json's city and
    city_ascii fields, not just one. Michelin's own spelling is inconsistent
    about diacritics: it drops macrons for Japanese cities ("Kyoto", not
    "Kyōto" -- matches city_ascii, not city) but keeps accents for others
    ("São Paulo", not "Sao Paulo" -- matches city, not city_ascii). Matching
    against only one field silently drops whichever set doesn't use that
    field's convention.
  - A trailing US two-letter state-code suffix (", NY", ", CA", etc.), if
    still present on the city side, is stripped before comparing.
  - A handful of Michelin Location values are a bare city name with no
    ", Country" suffix, because the city IS the country/territory
    (Singapore, Dubai, Abu Dhabi, Macau, Luxembourg) -- CITY_ONLY_COUNTRY
    below maps those directly to an iso3 instead of going through
    normalize_country().
  - Genuine name variants between the two sources -- not diacritics, not
    a suffix-stripping rule, just a different name for the same place
    (Seville vs Sevilla, Quebec vs Quebec City, Antwerpen vs Antwerp) --
    are resolved via city_lookup.resolve_city_alias(), backed by
    data/reference/city_aliases.json (mirrors country_lookup.py /
    country_aliases.json). Found by manually scanning the top of the
    "missing" output and checking tourist_cities.json for a near-miss.
    Add new ones to CITY_ALIASES in build_city_aliases.py and rerun it --
    there's no general rule that catches these, unlike the
    diacritic/suffix cases above.

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
