"""
Builds data/processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.csv: a single
0-10 number per country, the plain average of this project's per-domain
country scores so far --

    UNESCO_SCORE   (compute_unesco_score.py       -- World Heritage Sites)
    MICHELIN_SCORE (compute_michelin_score.py      -- Michelin awards)
    PRICE_SCORE    (compute_price_level_score.py   -- affordability, cheaper = higher)

All three are already built on the same 242-country canonical list
(reference/country_aliases.json), keyed by the same ISO2 `COUNTRY`
column, so this script is a straight join -- no name-matching/aliasing
needed here, unlike scripts that join against Eurostat-coded or raw-text
sources.

Missing data is averaged around, not treated as a 0: PRICE_SCORE is
blank for ~59 countries with no World Bank PLI value (see
compute_price_level_score.py) -- a country's OVERARCHING_SCORE is the
average of however many of the three scores it actually has (1, 2, or
3), never silently padded with a 0 for a domain with no data. See
SCORES_AVERAGED in the output -- always check it before trusting a
score built from only 1 or 2 domains for a given country. A country
missing ALL THREE (UNESCO/Michelin both legitimately 0 for a country
with no data in either simply average to 0 in those domains -- see next
paragraph -- but PRICE_SCORE missing is different) gets
OVERARCHING_SCORE = "" (blank), not 0/10 or 5/10, since there's nothing
to average.

Worth being explicit about what "0" means in each input, since they
don't all mean the same thing: UNESCO_SCORE=0 and MICHELIN_SCORE=0 are
REAL, deliberate zeros (see those scripts) -- "this country genuinely
has no UNESCO sites / no Michelin-recognized restaurants (in this
dataset)" is itself a meaningful trip-scoring signal, not missing data.
PRICE_SCORE, by contrast, is blank rather than 0 when the World Bank has
no PLI value for a country -- there is no such thing as a country with a
"real" price level of exactly the worst-possible score; missing PLI data
just means this project doesn't know. That's why only PRICE_SCORE ever
produces a blank cell here, while UNESCO_SCORE/MICHELIN_SCORE's 0s are
included in the average like any other value.

Not weighted, not traveler-profile-aware -- literally
`mean(available_scores)`, per the request that kicked this script off.
A "food and culture traveler" profile weighting Michelin/UNESCO more
heavily than affordability (or a budget traveler doing the reverse) is a
natural next step, but isn't what this script does; it's the flat,
unweighted baseline everything profile-specific would build on top of.

Written as both a CSV (data/processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.csv,
one row per country, matching every other *_SCORE_BY_COUNTRY.csv in this
project) and a JSON (…json, an object keyed by iso2 `COUNTRY` code, plus
the source/generated/counts metadata this project's other JSON outputs
carry -- see unesco_by_country.json, monthly_scores_<year>_by_city.json).
Same rows, same blank-vs-zero handling either way (a missing PRICE_SCORE
is `null` in the JSON, matching the CSV's blank cell); JSON is there for
anything downstream (e.g. the frontend) that wants this data as-is
without a CSV parser.

Usage:
    python build_overarching_trip_scores.py
"""

import csv
import json
from datetime import date
from pathlib import Path

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
UNESCO_PATH = PROCESSED_DIR / "UNESCO_SCORE_BY_COUNTRY.csv"
MICHELIN_PATH = PROCESSED_DIR / "MICHELIN_SCORE_BY_COUNTRY.csv"
PRICE_PATH = PROCESSED_DIR / "PRICE_LEVEL_SCORE_BY_COUNTRY.csv"
OUTPUT_CSV_PATH = PROCESSED_DIR / "OVERARCHING_TRIP_SCORE_BY_COUNTRY.csv"
OUTPUT_JSON_PATH = PROCESSED_DIR / "OVERARCHING_TRIP_SCORE_BY_COUNTRY.json"

ATTRIBUTION = (
    "Derived from UNESCO_SCORE_BY_COUNTRY.csv, MICHELIN_SCORE_BY_COUNTRY.csv, "
    "and PRICE_LEVEL_SCORE_BY_COUNTRY.csv via build_overarching_trip_scores.py -- "
    "see data/SCORING.md"
)

# (label used in the output column name, path, the score column to read from it)
SCORE_SOURCES = [
    ("UNESCO_SCORE", UNESCO_PATH, "UNESCO_SCORE"),
    ("MICHELIN_SCORE", MICHELIN_PATH, "MICHELIN_SCORE"),
    ("PRICE_SCORE", PRICE_PATH, "PRICE_SCORE"),
]


def load_scores(path: Path, score_column: str) -> dict[str, tuple[str, float | None]]:
    """iso2 -> (COUNTRY_NAME, score or None if blank in the source CSV)."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found -- run the script that builds it first.")
    with open(path, newline="", encoding="utf-8") as f:
        rows = {}
        for row in csv.DictReader(f):
            raw = row[score_column]
            score = float(raw) if raw != "" else None
            rows[row["COUNTRY"]] = (row["COUNTRY_NAME"], score)
        return rows


def build_overarching_scores() -> list[dict]:
    per_source = {label: load_scores(path, col) for label, path, col in SCORE_SOURCES}

    all_codes = set()
    for scores in per_source.values():
        all_codes |= set(scores)

    country_names: dict[str, str] = {}
    for scores in per_source.values():
        for iso2, (name, _) in scores.items():
            country_names.setdefault(iso2, name)

    rows = []
    for iso2 in all_codes:
        values = {}
        for label, _, _ in SCORE_SOURCES:
            entry = per_source[label].get(iso2)
            values[label] = entry[1] if entry else None

        available = [v for v in values.values() if v is not None]
        overarching = round(sum(available) / len(available), 2) if available else None

        rows.append(
            {
                "COUNTRY": iso2,
                "COUNTRY_NAME": country_names.get(iso2, "UNKNOWN"),
                "UNESCO_SCORE": values["UNESCO_SCORE"] if values["UNESCO_SCORE"] is not None else "",
                "MICHELIN_SCORE": values["MICHELIN_SCORE"] if values["MICHELIN_SCORE"] is not None else "",
                "PRICE_SCORE": values["PRICE_SCORE"] if values["PRICE_SCORE"] is not None else "",
                "SCORES_AVERAGED": len(available),
                "OVERARCHING_SCORE": overarching if overarching is not None else "",
            }
        )

    # Blank OVERARCHING_SCORE (no data at all -- shouldn't happen given
    # UNESCO/Michelin cover all 242 countries with a real 0, but sort
    # defensively rather than crash if it ever does) sorts last.
    rows.sort(key=lambda r: (-(r["OVERARCHING_SCORE"] if r["OVERARCHING_SCORE"] != "" else -1), r["COUNTRY_NAME"]))
    return rows


def write_csv(rows: list[dict]) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["COUNTRY", "COUNTRY_NAME", "UNESCO_SCORE", "MICHELIN_SCORE", "PRICE_SCORE", "SCORES_AVERAGED", "OVERARCHING_SCORE"]
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return OUTPUT_CSV_PATH


def write_json(rows: list[dict]) -> Path:
    """Same data as write_csv, reshaped into this project's usual JSON
    convention: an object keyed by iso2 code plus source/generated/count
    metadata (see unesco_by_country.json, monthly_scores_*.json). Blank
    CSV cells (PRICE_SCORE missing, or OVERARCHING_SCORE with zero inputs)
    become JSON `null`, not the string "" the CSV uses."""

    def blank_to_none(value):
        return value if value != "" else None

    countries = {
        r["COUNTRY"]: {
            "country_name": r["COUNTRY_NAME"],
            "unesco_score": blank_to_none(r["UNESCO_SCORE"]),
            "michelin_score": blank_to_none(r["MICHELIN_SCORE"]),
            "price_score": blank_to_none(r["PRICE_SCORE"]),
            "scores_averaged": r["SCORES_AVERAGED"],
            "overarching_score": blank_to_none(r["OVERARCHING_SCORE"]),
        }
        for r in rows
    }

    payload = {
        "source": ATTRIBUTION,
        "generated": date.today().isoformat(),
        "total_countries": len(rows),
        "full_data_countries": sum(1 for r in rows if r["SCORES_AVERAGED"] == 3),
        "partial_data_countries": sum(1 for r in rows if r["SCORES_AVERAGED"] in (1, 2)),
        "no_data_countries": sum(1 for r in rows if r["SCORES_AVERAGED"] == 0),
        "countries": countries,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return OUTPUT_JSON_PATH


def main():
    rows = build_overarching_scores()
    csv_path = write_csv(rows)
    json_path = write_json(rows)

    full_data = sum(1 for r in rows if r["SCORES_AVERAGED"] == 3)
    partial_data = sum(1 for r in rows if r["SCORES_AVERAGED"] in (1, 2))
    no_data = sum(1 for r in rows if r["SCORES_AVERAGED"] == 0)
    unknown = [r for r in rows if r["COUNTRY_NAME"] == "UNKNOWN"]

    print(f"[overarching_trip_scores] {len(rows)} countries -- {full_data} with all 3 scores, {partial_data} partial, {no_data} with none")
    top5 = [r for r in rows if r["OVERARCHING_SCORE"] != ""][:5]
    print("[overarching_trip_scores] top 5:")
    for r in top5:
        print(f"  {r['COUNTRY_NAME']}: {r['OVERARCHING_SCORE']} (UNESCO {r['UNESCO_SCORE']}, Michelin {r['MICHELIN_SCORE']}, Price {r['PRICE_SCORE'] or 'n/a'}, n={r['SCORES_AVERAGED']})")
    if unknown:
        print(f"[overarching_trip_scores] WARNING: {len(unknown)} code(s) with no resolvable name: {[r['COUNTRY'] for r in unknown]}")
    print(f"[overarching_trip_scores] -> {csv_path}")
    print(f"[overarching_trip_scores] -> {json_path}")


if __name__ == "__main__":
    main()
