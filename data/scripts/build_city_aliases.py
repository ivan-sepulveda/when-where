"""
Builds data/reference/city_aliases.json: a hand-maintained registry of
city name spelling variants between Michelin's scraped city names and
tourist_cities.json's spelling, keyed by iso3 then by the alias spelling.
Mirrors the country_aliases.json pattern, except there's no "full
canonical list" to build against here -- `CITY_ALIASES` below IS the
whole registry. These are genuine name variants, not diacritics or
suffix noise (those are already handled elsewhere) -- just a different
name for the same place: Seville vs Sevilla, Quebec vs Quebec City. Add
a new entry as new ones turn up, found by scanning
diff_michelin_vs_tourist_cities.py's "missing" output for a near-miss.

Usage:
    python build_city_aliases.py
"""

import json
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit. Key is
# (michelin city spelling, iso3); value is the spelling to match against
# in tourist_cities.json's city/city_ascii fields.
# ---------------------------------------------------------------------------

CITY_ALIASES = {
    ("seville", "ESP"): "sevilla",
    ("québec", "CAN"): "quebec city",
    ("antwerpen", "BEL"): "antwerp",
    ("frankfurt on the main", "DEU"): "frankfurt",
    ("hsinchu county", "TWN"): "hsinchu",
    ("hsinchu city", "TWN"): "hsinchu",
    ("alacant", "ESP"): "alicante",
    ("cebu", "PHL"): "cebu city",
    ("taguig - metro manila", "PHL"): "taguig city",
    ("dublin city", "IRL"): "dublin",
    ("city of bristol", "GBR"): "bristol",
    ("new taipei", "TWN"): "taipei",
    ("heróica puebla de zaragoza", "MEX"): "puebla",
    ("las palmas de gran canaria", "ESP"): "las palmas",
    ("donostia / san sebastián", "ESP"): "donostia",
    ("brighton and hove", "GBR"): "brighton",
    ("phang-nga", "THA"): "phangnga",
    ("les sables d’olonne", "FRA"): "les sables-d'olonne",
    ("glasgow city", "GBR"): "glasgow",
}

# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
OUT_PATH = REFERENCE_DIR / "city_aliases.json"


def build_registry() -> dict:
    by_country: dict[str, dict[str, str]] = {}
    for (alias_city, iso3), canonical in CITY_ALIASES.items():
        by_country.setdefault(iso3, {})[alias_city.strip().casefold()] = canonical.strip().casefold()

    return {
        "generated": date.today().isoformat(),
        "description": (
            "Hand-maintained city name variants between Michelin's scraped "
            "city names and tourist_cities.json's spelling -- see "
            "build_city_aliases.py for how/why these were added. Keyed by "
            "iso3, then by the alias spelling (casefolded) -> canonical "
            "spelling as it appears in tourist_cities.json's city or "
            "city_ascii field (casefolded)."
        ),
        "total_aliases": len(CITY_ALIASES),
        "cities": {
            iso3: dict(sorted(aliases.items()))
            for iso3, aliases in sorted(by_country.items())
        },
    }


def main():
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    registry = build_registry()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
    print(
        f"Wrote {registry['total_aliases']} aliases across "
        f"{len(registry['cities'])} countries -> {OUT_PATH}"
    )


if __name__ == "__main__":
    main()
