"""
Builds data/processed/PRICE_LEVEL_SCORE_BY_COUNTRY.csv: a simple,
transparent 0-10 "affordability" score per country, derived from the
World Bank Price Level Index (`PA.NUS.GDP.PLI`, already fetched by
fetch_worldbank_indicator.py -- see data/processed/multiple/
worldbank_PA.NUS.GDP.PLI_<year>_by_country.json). Stays at scripts/ root
(and writes to processed/ root) since it isn't a geography-scoped fetch --
same reasoning as compute_unesco_score.py / compute_michelin_score.py.

PLI is USA=100, below 100 is cheaper, above 100 is pricier -- the raw
World Bank scale runs roughly 13 (Nigeria) to 118 (Iceland) as of this
writing. Per the project's decision, a HIGHER trip score here means MORE
affordable (cheaper), not a higher price level -- inverted from PLI's own
direction.

Scoring rule -- linear against fixed anchors, NOT the current min/max
country (so a new record-cheap or record-expensive country doesn't shift
everyone else's score, same reasoning as compute_unesco_score.py's fixed
tiers):

    PLI <= FLOOR_PLI (20)     -> 10  (very affordable)
    PLI >= CEILING_PLI (120)  -> 0   (very expensive)
    otherwise                -> 10 - (PLI - FLOOR_PLI) / 10

FLOOR_PLI=20/CEILING_PLI=120 were picked to comfortably bracket the real
observed range (13 to 118) with a little headroom on each end, rather
than being derived from the data itself -- so, unlike a min-max
normalization, both ends of the scale are fixed reference points, not
"whichever country happens to be cheapest/priciest this year."

Unlike compute_unesco_score.py/compute_michelin_score.py, PLI's
distribution isn't skewed the way site/award counts are (no long tail --
it's a roughly bell-shaped spread from ~13 to ~118, not several orders
of magnitude), so a plain linear scale is appropriate here; log-scaling
or tiering would be solving a problem this metric doesn't have.

Countries with no PLI data (81 of the 265 in the World Bank's own
country/region list -- mostly small territories, plus a few
sanctioned/conflict states) get PRICE_SCORE = "" (blank), not 0 --
missing data isn't the same as "extremely expensive," and scoring it as
0 would silently bias any downstream average toward "unaffordable" for
a country this script simply doesn't have a price signal for. See
build_overarching_trip_scores.py for how a blank here is handled when
averaging with the other per-domain scores.

Usage:
    python compute_price_level_score.py
"""

import csv
import glob
import json
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# iso2 -> canonical name, for countries country_aliases.json doesn't
# resolve cleanly -- same two gaps compute_unesco_score.py patches. See
# that script for the full explanation of each.
ISO2_OVERRIDES = {
    "NA": "Namibia",
    "PS": "Palestine",
}

# iso3 -> iso2, for the same two countries -- needed separately from
# ISO2_OVERRIDES above because the World Bank PLI data is keyed by iso3
# (NAM/PSE), and country_aliases.json's iso2 gap for Namibia means the
# iso3->iso2 map built from it is missing NAM entirely (Namibia's PLI
# value would otherwise be silently dropped, not just its name).
ISO3_TO_ISO2_OVERRIDES = {
    "NAM": "NA",
    "PSE": "PS",
}

# PLI value that scores a full 10 (very affordable) and the value that
# scores a 0 (very expensive) -- see the scoring-rule note above for why
# these are fixed anchors rather than derived from the current data.
FLOOR_PLI = 20
CEILING_PLI = 120

# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent.parent / "reference"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
COUNTRY_ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
PLI_GLOB = str(PROCESSED_DIR / "multiple" / "worldbank_PA.NUS.GDP.PLI_*_by_country.json")
OUTPUT_PATH = PROCESSED_DIR / "PRICE_LEVEL_SCORE_BY_COUNTRY.csv"

ATTRIBUTION = (
    "Derived from the World Bank's Price Level Index (PA.NUS.GDP.PLI, Data360 API) via "
    "fetch_worldbank_indicator.py -- see data/README.md"
)


def find_pli_path() -> Path:
    matches = sorted(glob.glob(PLI_GLOB), key=lambda p: Path(p).stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(
            f"No file matching {PLI_GLOB!r} -- run scripts/multiple/fetch_worldbank_indicator.py "
            f"PA.NUS.GDP.PLI, then scripts/multiple/fetch_latest_by_country.py, first."
        )
    if len(matches) > 1:
        print(f"Note: multiple files match {PLI_GLOB!r} -- using the most recently modified: {Path(matches[0]).name}")
    return Path(matches[0])


def load_country_names() -> dict[str, str]:
    """iso3 -> iso2, and iso2 -> canonical name -- for every country in
    country_aliases.json (skipping the handful with no iso2 at all --
    patched back in via ISO2_OVERRIDES instead), plus ISO2_OVERRIDES for
    codes not in country_aliases.json at all."""
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
    for iso3, iso2 in ISO3_TO_ISO2_OVERRIDES.items():
        iso3_to_iso2.setdefault(iso3, iso2)

    return names, iso3_to_iso2


def load_pli_by_iso3(pli_path: Path) -> dict[str, float]:
    with open(pli_path, encoding="utf-8") as f:
        data = json.load(f)
    return {iso3: entry["value"] for iso3, entry in data["data"].items()}


def score_for_pli(pli: float | None) -> float | None:
    """None (missing PLI) stays None -- see the docstring's "blank, not
    0" note above. Otherwise, linear against the fixed FLOOR_PLI/
    CEILING_PLI anchors, clamped to [0, 10]."""
    if pli is None:
        return None
    raw = 10 - (pli - FLOOR_PLI) / (CEILING_PLI - FLOOR_PLI) * 10
    return round(max(0.0, min(10.0, raw)), 2)


def build_scores(country_names: dict[str, str], iso3_to_iso2: dict[str, str], pli_by_iso3: dict[str, float]) -> list[dict]:
    pli_by_iso2: dict[str, float] = {}
    unmapped_iso3 = []
    for iso3, value in pli_by_iso3.items():
        iso2 = iso3_to_iso2.get(iso3)
        if iso2 is None:
            unmapped_iso3.append(iso3)
            continue
        pli_by_iso2[iso2] = value
    if unmapped_iso3:
        print(f"Note: {len(unmapped_iso3)} World Bank iso3 code(s) have no iso2 in country_aliases.json (likely region aggregates, e.g. WLD/ARB): {unmapped_iso3[:10]}{'...' if len(unmapped_iso3) > 10 else ''}")

    all_codes = set(country_names) | set(pli_by_iso2)

    rows = []
    for iso2 in all_codes:
        pli = pli_by_iso2.get(iso2)
        score = score_for_pli(pli)
        rows.append(
            {
                "COUNTRY": iso2,
                "COUNTRY_NAME": country_names.get(iso2, "UNKNOWN -- add to ISO2_OVERRIDES"),
                "PRICE_LEVEL_INDEX": round(pli, 2) if pli is not None else "",
                "PRICE_SCORE": score if score is not None else "",
            }
        )

    # Missing scores sort last (score=None treated as -1 for sort purposes only).
    rows.sort(key=lambda r: (-(r["PRICE_SCORE"] if r["PRICE_SCORE"] != "" else -1), r["COUNTRY_NAME"]))
    return rows


def write_csv(rows: list[dict]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["COUNTRY", "COUNTRY_NAME", "PRICE_LEVEL_INDEX", "PRICE_SCORE"])
        writer.writeheader()
        writer.writerows(rows)
    return OUTPUT_PATH


def main():
    pli_path = find_pli_path()
    country_names, iso3_to_iso2 = load_country_names()
    pli_by_iso3 = load_pli_by_iso3(pli_path)
    rows = build_scores(country_names, iso3_to_iso2, pli_by_iso3)
    out_path = write_csv(rows)

    with_score = [r for r in rows if r["PRICE_SCORE"] != ""]
    unknown = [r for r in rows if r["COUNTRY_NAME"].startswith("UNKNOWN")]

    print(f"[price_level_score] {len(rows)} countries, {len(with_score)} with PLI data")
    if with_score:
        cheapest = with_score[0]
        priciest = with_score[-1]
        print(f"[price_level_score] most affordable: {cheapest['COUNTRY_NAME']} (PLI {cheapest['PRICE_LEVEL_INDEX']}) -> score {cheapest['PRICE_SCORE']}")
        print(f"[price_level_score] least affordable: {priciest['COUNTRY_NAME']} (PLI {priciest['PRICE_LEVEL_INDEX']}) -> score {priciest['PRICE_SCORE']}")
    if unknown:
        print(f"[price_level_score] WARNING: {len(unknown)} code(s) with no resolvable name -- add to ISO2_OVERRIDES: {[r['COUNTRY'] for r in unknown]}")
    print(f"[price_level_score] -> {out_path}")


if __name__ == "__main__":
    main()
