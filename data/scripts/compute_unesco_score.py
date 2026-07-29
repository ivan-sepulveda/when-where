"""
Builds data/processed/UNESCO_SCORE_BY_COUNTRY.csv: a simple, transparent,
log-scaled 0-10 "UNESCO World Heritage density" score per country, derived
from processed/multiple/unesco_by_country.json (see
scripts/multiple/build_unesco_sites_by_country.py). Stays at scripts/ root
(and writes to processed/ root) since it isn't a geography-scoped fetch --
same reasoning as compute_monthly_scores.py and
compute_peak_tourism_indicator.py.

Scoring rule -- log-scaled against the single most-inscribed country,
same family of formula as compute_michelin_score.py:

    SITE_COUNT == 0  -> 0
    SITE_COUNT > 0   -> log(SITE_COUNT + 1) / log(MAX_SITE_COUNT + 1) * 10

This script went through two earlier versions before landing here:
  1. Plain linear against the max (`SITE_COUNT / MAX_SITE_COUNT * 10`) --
     dropped because whichever country happens to have the most sites
     (Italy, 62, as of this writing) set the whole scale, so a genuinely
     heritage-rich country like Mexico (36 sites) landed at a middling
     5.81.
  2. Fixed tiers (50+ sites -> 10, 40-49 -> 9, 30-39 -> 8, 20-29 -> 7,
     linear ramp to 6.0 at 19 sites below that) -- chosen specifically
     to decouple every country's score from wherever the current record
     holder sits, at the cost of needing hand-picked tier boundaries.
  3. This version: log-scale, matching compute_michelin_score.py's
     approach for consistency between the project's two "density of X"
     scores, at the cost of reintroducing a (much smaller than plain
     linear) dependence on the current max -- see
     compute_michelin_score.py's own docstring for the fuller log-vs-
     tiered tradeoff discussion, since that's where it was first worked
     out. Concretely, versus the tiered scheme this replaces: Mexico (36
     sites) moves from 8.0 to 8.72, Vietnam (9 sites) moves from 2.84 to
     5.56, Namibia (2 sites) moves from 0.63 to 2.65 -- log-scale gives
     more credit to low site counts than the tiered version did, since
     UNESCO's 0-62 range doesn't have anywhere near Michelin's
     three-order-of-magnitude spread for log-compression to work against.
     Kept anyway, per project decision, for consistency with
     compute_michelin_score.py's formula.
Not combined with anything else here -- like the weather/peak-tourism
scores, this is one candidate input for a traveler-profile-specific
weighted score downstream (a "food and culture traveler" profile would
presumably weight this heavily; a "beach traveler" profile might weight
it near zero).

Every country in data/reference/country_aliases.json (241 countries,
the same canonical list scripts like build_country_aliases.py already
use) gets a row, including the ~70% with zero UNESCO sites -- a country
absent from unesco_by_country.json is a real "no sites" data point for
this scoring model, not a country to silently drop.

Known iso2 gaps in country_aliases.json, patched here rather than in
that file (out of scope for this script -- see ISO2_OVERRIDES below):
  - Namibia's iso2 is stored as an actual null (`NaN`) in
    country_aliases.json, not the string "NA" -- almost certainly
    Namibia's real ISO 3166-1 alpha-2 code ("NA") getting silently
    parsed as pandas' NaN sentinel somewhere upstream in
    build_country_aliases.py's SimpleMaps ingestion, a classic footgun
    for this specific country code. Worth a real fix there someday;
    patched here so Namibia's 2 UNESCO sites (Twyfelfontein, Namib Sand
    Sea) aren't dropped from this score.
  - Palestine ("PS") has 1 UNESCO site (Old City of Hebron) but isn't in
    country_aliases.json's 241-country list at all (not present in the
    SimpleMaps World Cities Database that list was built from).

Usage:
    python compute_unesco_score.py
"""

import csv
import json
import math
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# iso2 -> canonical name, for countries UNESCO's data assigns a site to
# but that aren't resolvable via country_aliases.json -- see the
# docstring above for why each of these is here.
ISO2_OVERRIDES = {
    "NA": "Namibia",
    "PS": "Palestine",
}

# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
COUNTRY_ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
UNESCO_BY_COUNTRY_PATH = PROCESSED_DIR / "multiple" / "unesco_by_country.json"
OUTPUT_PATH = PROCESSED_DIR / "UNESCO_SCORE_BY_COUNTRY.csv"

ATTRIBUTION = (
    "Derived from UNESCO World Heritage Centre Open Data via "
    "fetch_unesco_world_heritage_sites.py / build_unesco_sites_by_country.py -- "
    "see data/README.md"
)


def load_country_names() -> dict[str, str]:
    """iso2 -> canonical name, for every country in country_aliases.json
    (skipping the handful with no iso2 at all, e.g. Namibia -- patched
    back in via ISO2_OVERRIDES instead), plus ISO2_OVERRIDES for codes
    UNESCO uses that aren't in country_aliases.json at all."""
    if not COUNTRY_ALIASES_PATH.exists():
        raise FileNotFoundError(f"{COUNTRY_ALIASES_PATH} not found -- run build_country_aliases.py first.")
    with open(COUNTRY_ALIASES_PATH, encoding="utf-8") as f:
        data = json.load(f)

    names: dict[str, str] = {}
    for entry in data["countries"].values():
        iso2 = entry.get("iso2")
        if isinstance(iso2, str) and iso2:  # excludes the NaN-as-float case (Namibia)
            names[iso2] = entry["canonical_name"]

    for iso2, name in ISO2_OVERRIDES.items():
        names.setdefault(iso2, name)

    return names


def load_site_counts() -> dict[str, int]:
    if not UNESCO_BY_COUNTRY_PATH.exists():
        raise FileNotFoundError(
            f"{UNESCO_BY_COUNTRY_PATH} not found -- run build_unesco_sites_by_country.py first "
            f"(which itself needs fetch_unesco_world_heritage_sites.py's output)."
        )
    with open(UNESCO_BY_COUNTRY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {iso2: len(sites) for iso2, sites in data["sites_by_country"].items()}


def score_for_site_count(site_count: int, max_site_count: int) -> float:
    """log(count+1) / log(max+1) * 10 -- see the scoring-rule note in this
    script's docstring for the log-vs-tiered tradeoff, worked out fully
    in compute_michelin_score.py's docstring."""
    if site_count <= 0 or max_site_count <= 0:
        return 0.0
    return round(math.log(site_count + 1) / math.log(max_site_count + 1) * 10, 2)


def build_scores(country_names: dict[str, str], site_counts: dict[str, int]) -> list[dict]:
    # Union, not just country_names -- a UNESCO code missing from the
    # canonical list (shouldn't happen once ISO2_OVERRIDES is kept up to
    # date, but fail loud rather than silently dropping a country with
    # real sites if a new gap like Namibia's ever turns up).
    all_codes = set(country_names) | set(site_counts)
    max_site_count = max(site_counts.values(), default=0)

    rows = []
    for iso2 in all_codes:
        site_count = site_counts.get(iso2, 0)
        score = score_for_site_count(site_count, max_site_count)
        rows.append(
            {
                "COUNTRY": iso2,
                "COUNTRY_NAME": country_names.get(iso2, "UNKNOWN -- add to ISO2_OVERRIDES"),
                "SITE_COUNT": site_count,
                "UNESCO_SCORE": score,
            }
        )

    rows.sort(key=lambda r: (-r["UNESCO_SCORE"], r["COUNTRY_NAME"]))
    return rows


def write_csv(rows: list[dict]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["COUNTRY", "COUNTRY_NAME", "SITE_COUNT", "UNESCO_SCORE"])
        writer.writeheader()
        writer.writerows(rows)
    return OUTPUT_PATH


def main():
    country_names = load_country_names()
    site_counts = load_site_counts()
    rows = build_scores(country_names, site_counts)
    out_path = write_csv(rows)

    countries_with_sites = sum(1 for r in rows if r["SITE_COUNT"] > 0)
    max_row = max(rows, key=lambda r: r["SITE_COUNT"])
    unknown = [r for r in rows if r["COUNTRY_NAME"].startswith("UNKNOWN")]

    print(f"[unesco_score] {len(rows)} countries, {countries_with_sites} with at least one UNESCO site")
    print(f"[unesco_score] max: {max_row['COUNTRY_NAME']} ({max_row['COUNTRY']}) -- {max_row['SITE_COUNT']} sites -> score {max_row['UNESCO_SCORE']}")
    if unknown:
        print(f"[unesco_score] WARNING: {len(unknown)} code(s) with no resolvable name -- add to ISO2_OVERRIDES: {[r['COUNTRY'] for r in unknown]}")
    print(f"[unesco_score] -> {out_path}")


if __name__ == "__main__":
    main()
