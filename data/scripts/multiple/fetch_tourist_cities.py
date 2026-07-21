"""
Build data/reference/tourist_cities.json: latitude/longitude (and other
metadata) for a fixed list of cities used throughout the project.

The list is the top N cities worldwide by population, plus a manually
curated list of additional cities that matter for travel scoring but don't
crack the population cutoff (e.g. smaller but popular tourist towns).

Data source: SimpleMaps World Cities Database, Basic tier (free, ~50.2K
prominent cities/towns worldwide), licensed CC BY 4.0.
https://simplemaps.com/data/world-cities
Attribution (required by the license) lives in data/README.md and the
top-level README.md -- keep both in sync if this script or its source
changes.

Usage:
    python fetch_tourist_cities.py
    python fetch_tourist_cities.py --force-download   # re-download even if cached

Edit TOP_N_CITIES_BY_POPULATION / ADDITIONAL_CITIES below to change which
cities end up in the output -- no need to touch the rest of the script.
"""

import argparse
import json
import zipfile
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# How many cities to include, ranked by population (largest first).
TOP_N_CITIES_BY_POPULATION = 3000

# Cities to force-include even if they don't crack the population cutoff
# above -- e.g. smaller but popular/relevant tourist towns. Each entry is
# either a plain city name (string) or a (city, country) tuple.
#
# A plain string pulls in the most populous match from EVERY country that
# has a city with that name -- e.g. "Queenstown" alone gets you both
# Queenstown, New Zealand and Queenstown, South Africa, and "Dublin" gets
# you both Dublin, Ireland and Dublin, California. It never pulls in two
# cities from the *same* country, though -- if a name recurs within one
# country (e.g. multiple Dublins across US states), only the most populous
# of those is kept, so "Charlotte" still yields just one US Charlotte.
#
# Use the (city, country) tuple form when you want exactly one specific
# country's match and nothing else -- e.g. ("Merida", "Mexico") to exclude
# the Spanish and Venezuelan Meridas entirely.
ADDITIONAL_CITIES = [
    "Positano",
    "Queenstown",
    "Cannes",
    "Parma",
    "Tulum",
    "Gijón",
    "Catania",
    "Charlotte",
    "Dublin",
    "Mexico City",
    "Da Nang",
    "Phuket",
    "Cuauhtemoc",
    "Geneva",
    "Strasbourg",
    "Mendoza",
    "Quebec",
    "Venice",
    ("Merida", "Mexico"),
    "Izmir",
    "Chon Buri",
    "Phra Nakhon Si Ayutthaya",
    "Ixelles",
    "Oaxaca",
    "Bodrum",
    "Luxembourg",
    "Annecy",
    "Montpellier",
    "Maastricht",
    "Gent",
    "Salzburg",
    "Ljubljana",
    "Dijon",
    "Monaco",
    "Santiago de Compostela",
    "Asheville",
    "Biarritz",
    "Graz",
    "Avignon",
    "Saint-Malo",
    "Lucerne",
    "Clermont-Ferrand",
    "Marbella",
    "Miami Beach",
    "Rennes",
    "Udon Thani",
    "Ko Samui",
    "Beaune",
    "Surat Thani",
    "La Rochelle",
    "Vigo",
    "Basel",
    "Angers",
    "Malmo",
    "Reims",
    "Funchal",
    "Knokke",
    "Lausanne",
    "Ubon Ratchathani",
    "Boulder",
    "Split",
    "Eindhoven",
    "Caen",
    "Dubrovnik",
    "Vannes",
    "Nancy",
    "Baden-Baden",
    "San Jose del Cabo",
    "A Coruna",
    "Liege",
    "Nimes",
    "Puebla",
    "Las Palmas",
    "Les Sables-d'Olonne",
    "Phangnga",
    ("Wellington", "New Zealand"),
    ("Verona", "Italy"),
    ("Santa Barbara", "United States"),
    ("Groningen", "Netherlands"),
    ("Bath", "United Kingdom"),
    ("Santa Monica", "United States"),
    ("Santander", "Spain"),
    ("Valladolid", "Spain"),
    ("Brighton", "United Kingdom"),
    ("Cordoba", "Spain"),
    ("Glasgow", "United Kingdom"),
    ("Donostia", "Spain"),
]

# Cities missing from the SimpleMaps Basic dataset entirely -- not an
# ADDITIONAL_CITIES lookup miss, the row just isn't in the source at all.
# (Checked directly against the raw CSV before adding here -- don't add
# something here without confirming it's truly absent, since a plain
# ADDITIONAL_CITIES entry should be tried first.) Each entry is filled in
# by hand and merged into the output as-is, tagged "manual_override".
MANUAL_CITIES = [
    {
        # Absent from SimpleMaps Basic v1.91.1 under any spelling as of
        # 2026-07-20 -- confirmed by grepping the raw CSV for "queenstown"
        # and for New Zealand rows in the Otago region. Coordinates and
        # population are from Stats NZ's subnational population estimate
        # (Queenstown urban area, SSGA18 standard) at 30 June 2025.
        "city": "Queenstown",
        "city_ascii": "Queenstown",
        "country": "New Zealand",
        "iso2": "NZ",
        "iso3": "NZL",
        "admin_name": "Otago",
        "lat": -45.0302,
        "lng": 168.6627,
        "population": 29000,
        "capital": None,
    },
]

# ---------------------------------------------------------------------------

SOURCE_URL = "https://simplemaps.com/static/data/world-cities/basic/simplemaps_worldcities_basicv1.91.1.zip"
RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "simplemaps"
REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
ZIP_PATH = RAW_DIR / "simplemaps_worldcities_basicv1.91.1.zip"
OUT_PATH = REFERENCE_DIR / "tourist_cities.json"

ATTRIBUTION = (
    "SimpleMaps World Cities Database (Basic), CC BY 4.0 -- "
    "https://simplemaps.com/data/world-cities"
)


def download_zip(force: bool = False) -> Path:
    """Download the SimpleMaps zip into raw/, reusing the cached copy unless forced."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists() and not force:
        print(f"Using cached download: {ZIP_PATH}")
        return ZIP_PATH
    print(f"Downloading {SOURCE_URL} ...")
    # A plain urllib/requests default User-Agent gets a 403 from SimpleMaps'
    # server (bot-blocking) -- a browser-like one works.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(SOURCE_URL, headers=headers, timeout=60)
    resp.raise_for_status()
    ZIP_PATH.write_bytes(resp.content)
    print(f"Saved -> {ZIP_PATH}")
    return ZIP_PATH


def load_cities_csv(zip_path: Path) -> pd.DataFrame:
    """Extract and load the single CSV inside the SimpleMaps zip."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not csv_names:
            raise ValueError(f"No CSV found inside {zip_path}")
        with zf.open(csv_names[0]) as f:
            df = pd.read_csv(f)
    return df


def _normalize(name: str) -> str:
    return str(name).strip().casefold()


def resolve_additional_cities(df: pd.DataFrame, entries: list) -> pd.DataFrame:
    """
    Look up ADDITIONAL_CITIES entries by name (or name+country) in df.

    (city, country) tuples resolve to a single row for that country
    (warning and picking the most populous if that country itself has
    more than one same-named city).

    Plain city-name strings resolve to ONE row per country that has a
    matching city -- the most populous such city within each country --
    so a name that's ambiguous across countries (e.g. "Queenstown" in New
    Zealand and South Africa) pulls in all of them, while a name that
    merely recurs within one country (e.g. several US Dublins) still only
    contributes a single row for that country.

    Missing names are skipped with a warning rather than failing the run.
    """
    rows = []
    for entry in entries:
        if isinstance(entry, tuple):
            city, country = entry
            matches = df[
                (df["city_ascii"].apply(_normalize) == _normalize(city))
                & (df["country"].apply(_normalize) == _normalize(country))
            ]
            label = f"{city}, {country}"

            if matches.empty:
                print(f"[ADDITIONAL_CITIES] WARNING: no match found for {label!r} -- skipped")
                continue

            if len(matches) > 1:
                options = ", ".join(
                    f"{r.city}, {r.admin_name} ({r.country}), pop {r.population:,.0f}"
                    if pd.notna(r.population)
                    else f"{r.city}, {r.admin_name} ({r.country}), pop unknown"
                    for r in matches.itertuples()
                )
                print(
                    f"[ADDITIONAL_CITIES] WARNING: {label!r} is ambiguous ({options}) "
                    f"-- using the most populous match."
                )
                matches = matches.sort_values("population", ascending=False)

            rows.append(matches.iloc[0])
            continue

        city = entry
        matches = df[df["city_ascii"].apply(_normalize) == _normalize(city)]

        if matches.empty:
            print(f"[ADDITIONAL_CITIES] WARNING: no match found for {city!r} -- skipped")
            continue

        countries = sorted(matches["country"].unique())
        if len(countries) > 1:
            print(
                f"[ADDITIONAL_CITIES] {city!r} matches {len(countries)} countries "
                f"({', '.join(countries)}) -- including the most populous city "
                f"from each. Use a (city, country) tuple instead if you only want one."
            )

        by_pop = matches.sort_values("population", ascending=False)
        for _, group in by_pop.groupby("country", sort=False):
            rows.append(group.iloc[0])

    if not rows:
        return df.iloc[0:0]
    return pd.DataFrame(rows)


def _row_to_dict(row, included_reason: str) -> dict:
    def clean(val):
        return None if pd.isna(val) or val == "" else val

    return {
        "city": row.city,
        "city_ascii": row.city_ascii,
        "country": row.country,
        "iso2": row.iso2,
        "iso3": row.iso3,
        "admin_name": clean(row.admin_name),
        "lat": row.lat,
        "lng": row.lng,
        "population": None if pd.isna(row.population) else int(row.population),
        "capital": clean(row.capital),
        "simplemaps_id": int(row.id),
        "included_reason": included_reason,
    }


def build_tourist_cities(df: pd.DataFrame) -> dict:
    """Pure function: DataFrame in, output dict out. Kept separate from I/O for testing."""
    ranked = df.dropna(subset=["population"]).sort_values("population", ascending=False)
    top_n = ranked.head(TOP_N_CITIES_BY_POPULATION)
    top_n_ids = set(top_n["id"])

    additional = resolve_additional_cities(df, ADDITIONAL_CITIES)

    cities = [_row_to_dict(row, "top_n_population") for row in top_n.itertuples()]
    seen_ids = set(top_n_ids)
    for row in additional.itertuples():
        if row.id in seen_ids:
            continue  # already included via top_n -- don't duplicate
        cities.append(_row_to_dict(row, "additional_cities"))
        seen_ids.add(row.id)

    # (city_ascii, country) pairs already covered, for dedup against
    # MANUAL_CITIES -- these entries have no simplemaps id to key off of.
    seen_name_country = {(c["city_ascii"].casefold(), c["country"].casefold()) for c in cities}
    for manual in MANUAL_CITIES:
        key = (manual["city_ascii"].casefold(), manual["country"].casefold())
        if key in seen_name_country:
            print(
                f"[MANUAL_CITIES] {manual['city']}, {manual['country']!r} is already "
                f"present from another source -- skipped duplicate."
            )
            continue
        cities.append({**manual, "simplemaps_id": None, "included_reason": "manual_override"})
        seen_name_country.add(key)

    cities.sort(key=lambda c: (c["population"] is None, -(c["population"] or 0)))

    return {
        "source": ATTRIBUTION,
        "top_n_cities_by_population": TOP_N_CITIES_BY_POPULATION,
        "additional_cities_requested": len(ADDITIONAL_CITIES),
        "manual_cities_added": len(MANUAL_CITIES),
        "total_cities": len(cities),
        "cities": cities,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download the source zip even if a cached copy exists in raw/",
    )
    args = parser.parse_args()

    zip_path = download_zip(force=args.force_download)
    df = load_cities_csv(zip_path)
    out = build_tourist_cities(df)

    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {out['total_cities']} cities -> {OUT_PATH}")


if __name__ == "__main__":
    main()
