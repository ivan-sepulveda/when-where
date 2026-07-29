"""
Builds data/processed/MICHELIN_SCORE_BY_COUNTRY.csv: a simple, transparent,
log-scaled 0-10 "Michelin food scene density" score per country, derived
from processed/multiple/michelin_restaurants.csv (see
scripts/multiple/fetch_michelin_restaurants.py). Stays at scripts/ root
(and writes to processed/ root) since it isn't a geography-scoped fetch --
same reasoning as compute_unesco_score.py.

Uses ALL Michelin awards per country (Stars + Bib Gourmand + Selected
Restaurants), not starred restaurants only -- broader coverage (51
countries vs. 48 for starred-only) and a less punishing bar for
countries with a real but modest food scene.

Scoring rule -- log-scaled against the single highest country, NOT
tiered like compute_unesco_score.py:

    AWARD_COUNT == 0  -> 0
    AWARD_COUNT > 0   -> log(AWARD_COUNT + 1) / log(MAX_AWARD_COUNT + 1) * 10

Why log-scale here but a fixed-tier scheme for UNESCO, even though both
scripts score "how much of X does this country have" the same way in
spirit: Michelin awards are far more top-heavy than UNESCO sites --
France has 3,043 awarded restaurants vs. the current UNESCO max of 62
sites (Italy), a ~50x wider spread. Under a plain linear-against-max
score, that spread crushes almost every other country toward 0: Italy,
with nearly 2,000 awards of its own, would land at just 6.5/10 because
France's total is so much larger, and Belgium (709 awards -- genuinely
one of the best food scenes per capita in the world) would land at 2.33.
Log-scale compresses that gap so having hundreds of awarded restaurants
reads as "very good" (7-9 range) rather than "basically nothing next to
France." UNESCO's site counts don't have anywhere near that order-of-
magnitude spread (0-62), so applying the same log-scale there was tried
and rejected -- it over-rewards small counts instead (a country with 2
sites would score 2.65/10, more than a quarter of the maximum, for
barely any heritage sites) without fixing a problem UNESCO's tighter
range didn't really have to begin with. See compute_unesco_score.py's
own docstring for why IT uses fixed tiers instead.

One real caveat this script inherits from log-scaling, that the tiered
UNESCO score doesn't have: every country's score still depends on
whichever country currently holds the record (France, as of this
writing) -- if some country's awarded-restaurant count someday
overtakes France's, everyone else's score shifts slightly (a smaller
effect than under plain linear scaling, since log compresses, but not
zero). Worth knowing if this script's output is ever diffed across runs
after MICHELIN_PATH is refreshed.

Every country in data/reference/country_aliases.json (241 countries)
gets a row, including the countries with zero Michelin awards -- a
country absent from the source data is a real "no Michelin-recognized
restaurants (in this dataset)" data point, not a country to silently
drop. Not combined with anything else here -- see
build_overarching_trip_scores.py for where this and the other per-domain
scores get averaged into one number.

Usage:
    python compute_michelin_score.py
"""

import csv
import json
import math
import sys
from pathlib import Path

import pandas as pd

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
from country_lookup import normalize_country, report_unmapped  # noqa: E402

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# iso2 -> canonical name, for countries country_aliases.json doesn't
# resolve cleanly -- same two gaps compute_unesco_score.py patches, kept
# here too so this script's full-country-list join doesn't depend on
# that script having been fixed the same way. See compute_unesco_score.py
# for the full explanation of each.
ISO2_OVERRIDES = {
    "NA": "Namibia",
    "PS": "Palestine",
}

# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
COUNTRY_ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
MICHELIN_PATH = PROCESSED_DIR / "multiple" / "michelin_restaurants.csv"
OUTPUT_PATH = PROCESSED_DIR / "MICHELIN_SCORE_BY_COUNTRY.csv"

ATTRIBUTION = (
    "Derived from michelin-my-maps (MIT licensed) via "
    "fetch_michelin_restaurants.py -- see data/README.md"
)


def load_country_names() -> dict[str, str]:
    """iso2 -> canonical name, for every country in country_aliases.json
    (skipping the handful with no iso2 at all -- patched back in via
    ISO2_OVERRIDES instead), plus ISO2_OVERRIDES for codes not in
    country_aliases.json at all. Same logic as compute_unesco_score.py's
    function of the same name -- kept duplicated rather than shared,
    consistent with this project's per-script self-containment."""
    if not COUNTRY_ALIASES_PATH.exists():
        raise FileNotFoundError(f"{COUNTRY_ALIASES_PATH} not found -- run build_country_aliases.py first.")
    with open(COUNTRY_ALIASES_PATH, encoding="utf-8") as f:
        data = json.load(f)

    names: dict[str, str] = {}
    iso3_to_iso2: dict[str, str] = {}
    for iso3, entry in data["countries"].items():
        iso2 = entry.get("iso2")
        if isinstance(iso2, str) and iso2:  # excludes the NaN-as-float case (Namibia)
            names[iso2] = entry["canonical_name"]
            iso3_to_iso2[iso3] = iso2

    for iso2, name in ISO2_OVERRIDES.items():
        names.setdefault(iso2, name)

    return names, iso3_to_iso2


def load_award_counts(iso3_to_iso2: dict[str, str]) -> dict[str, int]:
    """iso2 -> total Michelin award count (Stars + Bib Gourmand + Selected
    Restaurants combined -- every row in the source file, no Award-column
    filtering). Michelin's location_country is a raw scraped string
    (e.g. "Chinese Mainland", "USA"), so it's normalized to iso3 via
    country_lookup.normalize_country() first, same as every other source
    in this project that only has a country name to work with."""
    if not MICHELIN_PATH.exists():
        raise FileNotFoundError(f"{MICHELIN_PATH} not found -- run fetch_michelin_restaurants.py first.")
    michelin = pd.read_csv(MICHELIN_PATH)

    unmatched = report_unmapped(michelin["location_country"])
    if unmatched:
        print(f"WARNING: {len(unmatched)} location_country value(s) don't resolve to a country: {unmatched}")

    michelin = michelin.copy()
    michelin["iso3"] = michelin["location_country"].map(normalize_country)
    by_iso3 = michelin.dropna(subset=["iso3"]).groupby("iso3").size()

    counts: dict[str, int] = {}
    unmapped_iso3 = []
    for iso3, count in by_iso3.items():
        iso2 = iso3_to_iso2.get(iso3)
        if iso2 is None:
            unmapped_iso3.append(iso3)
            continue
        counts[iso2] = counts.get(iso2, 0) + int(count)

    if unmapped_iso3:
        print(f"WARNING: {len(unmapped_iso3)} iso3 code(s) resolved by name but have no iso2 in country_aliases.json: {unmapped_iso3}")

    return counts


def score_for_award_count(award_count: int, max_award_count: int) -> float:
    """log(count+1) / log(max+1) * 10 -- see the scoring-rule note in this
    script's docstring for why log-scale here but fixed tiers for
    compute_unesco_score.py."""
    if award_count <= 0 or max_award_count <= 0:
        return 0.0
    return round(math.log(award_count + 1) / math.log(max_award_count + 1) * 10, 2)


def build_scores(country_names: dict[str, str], award_counts: dict[str, int]) -> list[dict]:
    all_codes = set(country_names) | set(award_counts)
    max_award_count = max(award_counts.values(), default=0)

    rows = []
    for iso2 in all_codes:
        award_count = award_counts.get(iso2, 0)
        score = score_for_award_count(award_count, max_award_count)
        rows.append(
            {
                "COUNTRY": iso2,
                "COUNTRY_NAME": country_names.get(iso2, "UNKNOWN -- add to ISO2_OVERRIDES"),
                "AWARD_COUNT": award_count,
                "MICHELIN_SCORE": score,
            }
        )

    rows.sort(key=lambda r: (-r["MICHELIN_SCORE"], r["COUNTRY_NAME"]))
    return rows


def write_csv(rows: list[dict]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["COUNTRY", "COUNTRY_NAME", "AWARD_COUNT", "MICHELIN_SCORE"])
        writer.writeheader()
        writer.writerows(rows)
    return OUTPUT_PATH


def main():
    country_names, iso3_to_iso2 = load_country_names()
    award_counts = load_award_counts(iso3_to_iso2)
    rows = build_scores(country_names, award_counts)
    out_path = write_csv(rows)

    countries_with_awards = sum(1 for r in rows if r["AWARD_COUNT"] > 0)
    max_row = max(rows, key=lambda r: r["AWARD_COUNT"])
    unknown = [r for r in rows if r["COUNTRY_NAME"].startswith("UNKNOWN")]

    print(f"[michelin_score] {len(rows)} countries, {countries_with_awards} with at least one Michelin award")
    print(f"[michelin_score] max: {max_row['COUNTRY_NAME']} ({max_row['COUNTRY']}) -- {max_row['AWARD_COUNT']} awards -> score {max_row['MICHELIN_SCORE']}")
    if unknown:
        print(f"[michelin_score] WARNING: {len(unknown)} code(s) with no resolvable name -- add to ISO2_OVERRIDES: {[r['COUNTRY'] for r in unknown]}")
    print(f"[michelin_score] -> {out_path}")


if __name__ == "__main__":
    main()
