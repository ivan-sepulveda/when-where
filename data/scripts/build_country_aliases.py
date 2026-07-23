"""
Builds data/reference/country_aliases.json: a canonical iso3-keyed
country registry with alternate name spellings, so scripts pulling from
different sources (World Bank REF_AREA codes, SimpleMaps country names,
Michelin's scraped strings, etc.) can normalize a country name/string to
one shared iso3 key before joining data. Canonical names/iso3/iso2 come
from the *full* SimpleMaps World Cities Database download, not the
trimmed reference subset, for full country coverage. `EXTRA_ALIASES` is
a hand-maintained list of alternate spellings seen in other sources that
don't match SimpleMaps' own naming -- use `country_lookup.py`'s
`report_unmapped()` to find new ones.

Usage:
    python build_country_aliases.py
"""

import json
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit. Add an iso3: [aliases]
# entry whenever a new source uses a country string that doesn't match
# SimpleMaps' own naming (run country_lookup.py in CLI mode against the new
# source to find these).
# ---------------------------------------------------------------------------

EXTRA_ALIASES = {
    "USA": ["usa", "us", "u.s.a.", "united states of america"],
    "CHN": ["chinese mainland", "prc", "people's republic of china"],
    "HKG": ["hong kong sar china"],
    "MCO": ["principality of monaco"],
    "KOR": ["south korea", "republic of korea"],
    "PHL": ["the philippines"],
    "TUR": ["türkiye", "turkiye"],
    # Michelin's scraper occasionally leaks the raw iso3 code into the
    # country field instead of a name -- map those straight through.
    "ARE": ["are"],
    "THA": ["tha"],
}

# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
RAW_SIMPLEMAPS_ZIP = (
    Path(__file__).resolve().parent.parent
    / "raw" / "simplemaps" / "simplemaps_worldcities_basicv1.91.1.zip"
)
OUT_PATH = REFERENCE_DIR / "country_aliases.json"


def load_canonical_countries() -> pd.DataFrame:
    """country/iso2/iso3, deduplicated, from the full SimpleMaps download."""
    if not RAW_SIMPLEMAPS_ZIP.exists():
        raise FileNotFoundError(
            f"{RAW_SIMPLEMAPS_ZIP} not found -- run fetch_tourist_cities.py "
            f"at least once first (it caches the SimpleMaps zip at that path)."
        )
    with zipfile.ZipFile(RAW_SIMPLEMAPS_ZIP) as zf:
        with zf.open("worldcities.csv") as f:
            df = pd.read_csv(f, usecols=["country", "iso2", "iso3"])
    return df.drop_duplicates(subset="iso3").sort_values("iso3")


def build_country_aliases() -> dict:
    canonical = load_canonical_countries()

    countries = {}
    for row in canonical.itertuples():
        aliases = {row.country.strip().casefold()}
        aliases.update(a.casefold() for a in EXTRA_ALIASES.get(row.iso3, []))
        countries[row.iso3] = {
            "canonical_name": row.country,
            "iso2": row.iso2,
            "aliases": sorted(aliases),
        }

    # Catch typos in EXTRA_ALIASES -- an iso3 that isn't in the canonical list at all.
    unknown = set(EXTRA_ALIASES) - set(countries)
    if unknown:
        print(
            f"WARNING: EXTRA_ALIASES references iso3 codes not found in the "
            f"canonical SimpleMaps list: {sorted(unknown)} -- check for typos."
        )

    return {
        "generated": date.today().isoformat(),
        "canonical_source": "SimpleMaps World Cities Database (Basic) -- see fetch_tourist_cities.py",
        "total_countries": len(countries),
        "countries": dict(sorted(countries.items())),
    }


def main():
    out = build_country_aliases()
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out['total_countries']} countries -> {OUT_PATH}")


if __name__ == "__main__":
    main()
