"""
Shared helper for resolving a city-name spelling variant to the canonical
spelling used in tourist_cities.json, using
data/reference/city_aliases.json (built by build_city_aliases.py).

This handles genuine city-name variants between sources -- not diacritics
or suffix noise, which diff_michelin_vs_tourist_cities.py's _clean_city()
and its dual city/city_ascii matching already handle directly -- just a
different name for the same place (Seville vs Sevilla, Quebec vs Quebec
City, Antwerpen vs Antwerp). Mirrors country_lookup.normalize_country().

Usage (as a library):
    from city_lookup import resolve_city_alias
    resolve_city_alias("Seville", "ESP")      # -> "sevilla"
    resolve_city_alias("Nonexistent", "ESP")  # -> None
"""

import json as json_module
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
ALIASES_PATH = REFERENCE_DIR / "city_aliases.json"

_alias_map: dict | None = None  # lazy-loaded, module-level cache


def _load_alias_map() -> dict:
    global _alias_map
    if _alias_map is not None:
        return _alias_map
    if not ALIASES_PATH.exists():
        raise FileNotFoundError(
            f"{ALIASES_PATH} not found -- run build_city_aliases.py first."
        )
    with open(ALIASES_PATH, encoding="utf-8") as f:
        data = json_module.load(f)
    _alias_map = data["cities"]
    return _alias_map


def resolve_city_alias(city: str | None, iso3: str | None) -> str | None:
    """
    Return the tourist_cities.json spelling (casefolded) for a
    (city, iso3) pair, or None if no alias is registered for it.
    """
    if not city or not iso3:
        return None
    return _load_alias_map().get(iso3, {}).get(str(city).strip().casefold())


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python city_lookup.py <city> <iso3>")
        raise SystemExit(1)
    print(resolve_city_alias(sys.argv[1], sys.argv[2]))
