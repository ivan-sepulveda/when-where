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
TOP_N_CITIES_BY_POPULATION = 550

# Cities to force-include even if they don't crack the population cutoff
# above -- e.g. smaller but popular/relevant tourist towns. Each entry is
# either a plain city name (string) or a (city, country) tuple. Use the
# tuple form when a name is ambiguous across countries (e.g. "Merida"
# exists in Mexico, Spain, and Venezuela) -- the plain-string form will
# still work, but falls back to the most populous match and prints a
# warning so you can disambiguate if that's not the one you meant.
ADDITIONAL_CITIES = [
    "Charlotte",
    ("Merida", "Mexico"),
]

# ---------------------------------------------------------------------------

SOURCE_URL = "https://simplemaps.com/static/data/world-cities/basic/simplemaps_worldcities_basicv1.91.1.zip"
RAW_DIR = Path(__file__).resolve().parent.parent / "raw" / "simplemaps"
REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
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
    Warns on ambiguous matches (picks the most populous) and missing ones
    (skips) rather than failing the whole run.
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
        else:
            city = entry
            matches = df[df["city_ascii"].apply(_normalize) == _normalize(city)]
            label = city

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
                f"-- using the most populous match. Disambiguate with a "
                f"(city, country) tuple if that's not the one you meant."
            )
            matches = matches.sort_values("population", ascending=False)

        rows.append(matches.iloc[0])

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

    cities.sort(key=lambda c: (c["population"] is None, -(c["population"] or 0)))

    return {
        "source": ATTRIBUTION,
        "top_n_cities_by_population": TOP_N_CITIES_BY_POPULATION,
        "additional_cities_requested": len(ADDITIONAL_CITIES),
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
