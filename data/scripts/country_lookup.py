"""
Shared helper for normalizing a country name/string to a canonical iso3
code, using data/reference/country_aliases.json (built by
build_country_aliases.py). Import normalize_country() from this module in
any script that needs to join data across sources with different country
naming conventions (World Bank REF_AREA codes, SimpleMaps country names,
Michelin's scraped strings, future sources, etc.).

Usage (as a library):
    from country_lookup import normalize_country
    normalize_country("USA")               # -> "USA"
    normalize_country("Chinese Mainland")  # -> "CHN"
    normalize_country("nonsense")          # -> None

Usage (as a diagnostic CLI) -- reports country strings in a CSV column
that don't resolve to a known iso3, so you know what to add to
EXTRA_ALIASES in build_country_aliases.py when wiring up a new source:
    python country_lookup.py path/to/file.csv --column location_country
"""

import argparse
from pathlib import Path

import json as json_module

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"

_alias_to_iso3: dict | None = None  # lazy-loaded, module-level cache


def _load_alias_map() -> dict:
    global _alias_to_iso3
    if _alias_to_iso3 is not None:
        return _alias_to_iso3
    if not ALIASES_PATH.exists():
        raise FileNotFoundError(
            f"{ALIASES_PATH} not found -- run build_country_aliases.py first."
        )
    with open(ALIASES_PATH, encoding="utf-8") as f:
        data = json_module.load(f)
    mapping = {}
    for iso3, entry in data["countries"].items():
        for alias in entry["aliases"]:
            mapping[alias] = iso3
    _alias_to_iso3 = mapping
    return mapping


def normalize_country(name: str | None) -> str | None:
    """Return the canonical iso3 code for a country name/string, or None if unrecognized."""
    if not name or (isinstance(name, float) and name != name):  # NaN != NaN
        return None
    return _load_alias_map().get(str(name).strip().casefold())


def report_unmapped(values) -> list[str]:
    """Given an iterable of country strings, return the distinct ones that don't resolve to an iso3."""
    seen = set()
    unmapped = []
    for v in values:
        if v is None or (isinstance(v, float) and v != v):  # skip None/NaN -- missing, not unmapped
            continue
        key = str(v).strip().casefold()
        if key in seen:
            continue
        seen.add(key)
        if normalize_country(v) is None:
            unmapped.append(v)
    return unmapped


def main():
    import pandas as pd

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="CSV file to scan")
    parser.add_argument("--column", required=True, help="Column name holding country strings")
    args = parser.parse_args()

    values = pd.read_csv(args.path)[args.column].tolist()
    unmapped = report_unmapped(values)

    if not unmapped:
        print(f"All country strings in {args.path} ({args.column!r}) resolve to a known iso3.")
        return

    print(f"{len(unmapped)} unmapped country string(s) in {args.path} ({args.column!r}):")
    for v in unmapped:
        print(f"  {v!r}")
    print(
        "\nAdd these to EXTRA_ALIASES in build_country_aliases.py (mapped to "
        "the correct iso3), then rerun that script to regenerate country_aliases.json."
    )


if __name__ == "__main__":
    main()
