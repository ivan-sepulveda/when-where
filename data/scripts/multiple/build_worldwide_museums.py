"""
Builds data/processed/multiple/worldwide_museums.json by merging every
per-country TSV in data/raw/museums/.

The TSVs are the source of truth. This script has no per-country logic and
no knowledge of where any country's rows originally came from -- it globs
data/raw/museums/*.tsv, takes each file's ISO2 country code from its
filename, and concatenates the rows. Adding a country means dropping in a
new TSV; correcting a museum means editing its row. Nothing is derived,
inferred, or filled in here.

File format (see data/raw/museums/README.md for per-country provenance):
  - One file per country, named <ISO2>.tsv (e.g. JP.tsv, ES.tsv).
  - First line is a header naming the columns, which must be exactly
    COLUMNS below, in order.
  - An empty field means null -- not an empty string, and never a guess.
  - lat/lng are currently empty in every file; geocoding is a future step.

Rows are NOT deduplicated by name. Some countries legitimately have two
distinct museums whose names collide as written -- Japan has two Idemitsu
Museum of Arts branches and two National Museums of Modern Art. Collapsing
those would delete real places, so duplicate resolution belongs in the TSV,
where a human can see both rows, not in an automatic pass here.

Usage: python build_worldwide_museums.py
"""

import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
RAW_MUSEUMS_DIR = DATA_DIR / "raw" / "museums"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
OUTPUT_PATH = PROCESSED_DIR / "worldwide_museums.json"

# Column order every TSV must use. Also the field order of each output
# record, which additionally carries the iso2 taken from the filename.
COLUMNS = [
    "name",
    "category",
    "kind",
    "description",
    "location_raw",
    "city",
    "lat",
    "lng",
    "gallery_space_m2",
    "gallery_space_sqft",
    "year_established",
    "year_established_raw",
]

FLOAT_COLUMNS = {"lat", "lng", "gallery_space_m2", "gallery_space_sqft"}
INT_COLUMNS = {"year_established"}


def parse_value(column, raw):
    """One TSV cell -> its Python value. Empty means null."""
    if raw == "":
        return None
    if column in FLOAT_COLUMNS:
        return float(raw)
    if column in INT_COLUMNS:
        return int(raw)
    return raw


def load_country_tsv(path):
    """Every row of one <ISO2>.tsv, as output records."""
    iso2 = path.stem
    with open(path, encoding="utf-8") as f:
        lines = f.read().rstrip("\n").split("\n")

    header = lines[0].split("\t")
    if header != COLUMNS:
        raise ValueError(
            f"{path.name}: header does not match the expected columns.\n"
            f"  expected: {COLUMNS}\n"
            f"  found:    {header}"
        )

    places = []
    for line_number, line in enumerate(lines[1:], start=2):
        values = line.split("\t")
        if len(values) != len(COLUMNS):
            raise ValueError(
                f"{path.name} line {line_number}: expected {len(COLUMNS)} "
                f"tab-separated columns, found {len(values)}"
            )
        record = {"iso2": iso2}
        for column, raw in zip(COLUMNS, values):
            record[column] = parse_value(column, raw)
        if not record["name"]:
            raise ValueError(f"{path.name} line {line_number}: name is empty")
        places.append(record)
    return places


def build():
    tsv_paths = sorted(RAW_MUSEUMS_DIR.glob("*.tsv"))
    if not tsv_paths:
        raise FileNotFoundError(f"No TSV files found in {RAW_MUSEUMS_DIR}")

    places = []
    places_by_country = {}
    for path in tsv_paths:
        country_places = load_country_tsv(path)
        places.extend(country_places)
        places_by_country[path.stem] = len(country_places)

    kind_counts = {}
    category_counts = {}
    for place in places:
        kind_label = place["kind"] or "uncategorized"
        kind_counts[kind_label] = kind_counts.get(kind_label, 0) + 1
        category_label = place["category"] or "uncategorized"
        category_counts[category_label] = category_counts.get(category_label, 0) + 1

    payload = {
        "generated": date.today().isoformat(),
        "countries_covered": sorted(places_by_country),
        "total_places": len(places),
        "places_by_country": places_by_country,
        "places_by_category": category_counts,
        "places_by_kind": kind_counts,
        "note": (
            "Merged from the per-country TSVs in data/raw/museums/, which are "
            "the source of truth -- see that directory's README.md for each "
            "country's provenance and coverage caveats. Coverage is uneven by "
            "country and no country should be assumed exhaustive. A null "
            "category or kind means the source did not record one; it was not "
            "inferred. lat/lng are null throughout -- geocoding is a future "
            "step. Rows are not deduplicated by name: some names legitimately "
            "collide between distinct museums."
        ),
        "places": places,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"Wrote {len(places)} places ({OUTPUT_PATH.stat().st_size} bytes) -> {OUTPUT_PATH}")
    print(f"  {len(tsv_paths)} country files merged from {RAW_MUSEUMS_DIR}")
    top = sorted(places_by_country.items(), key=lambda kv: -kv[1])[:5]
    print("  largest:", ", ".join(f"{iso2}={n}" for iso2, n in top))
    print("places_by_category:", category_counts)


if __name__ == "__main__":
    build()
