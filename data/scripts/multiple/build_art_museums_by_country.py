"""
Derived from: data/processed/multiple/art_museums.csv (built by
              fetch_art_museums.py)
Requires: data/reference/country_aliases.json (built by build_country_aliases.py)

Regroups the flat ~112-row largest-art-museums list into
data/processed/multiple/art_museums_by_country.json, keyed by ISO 3166-1
alpha-2 code (via country_lookup.normalize_country(), same resolution
every other by-country build script in this project uses) -- and cleans
up two real data-quality quirks in the source CSV along the way:

1. Gallery space is split across two columns, "Gallery space in m2 (sq
   ft)" and "Gallery space in sq ft", but they're not cleanly one-value-
   each -- in every row inspected, at least one of the two (often both)
   actually contains the *combined* "<m2>\\n(<sq ft>)" text (a leftover
   of scraping a single Wikipedia table cell into two output columns).
   parse_gallery_space() below pulls the m2 figure from the m2-labeled
   column's leading number, and the sq ft figure from whichever column
   has a parenthetical number (there's no reliable way to tell a lone
   number with no parenthetical apart -- e.g. some rows have plain
   "17,000" in both columns -- so those are left as sqft=None rather than
   guessing which unit that lone number is in).
2. Year established is sometimes a single year (most rows) and sometimes
   a slash-separated pair like "1806/1908" (e.g. a museum with two
   founding/reopening dates) -- year_established_raw keeps the original
   string, year_established is the first 4-digit year found in it (or
   None if the field doesn't parse), so callers that just want "how old
   is this" don't have to handle the slash case themselves.

A handful of country strings in the source don't resolve to a known
country out of the box (e.g. "Brasil" instead of "Brazil", "UAE" instead
of "United Arab Emirates") -- these were added to EXTRA_ALIASES in
build_country_aliases.py rather than worked around here; rerun that
script first if this one reports new unmatched names.

Usage:
    python build_art_museums_by_country.py
"""

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

# country_lookup.py lives in data/scripts/, not alongside this script
# (data/scripts/multiple/) -- only a script's own directory is added to
# sys.path automatically, so the parent has to be added by hand.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from country_lookup import normalize_country  # noqa: E402

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
MUSEUMS_PATH = PROCESSED_DIR / "art_museums.csv"
ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
OUT_PATH = PROCESSED_DIR / "art_museums_by_country.json"

# Leading number (commas/decimal allowed), optionally followed by a
# parenthetical second number -- matches both "92,000" and
# "72,735\n(782,910)" (the literal newline between number and "(" in the
# CSV is handled by \s*, which matches newlines too).
NUMBER_PAREN_RE = re.compile(r"([\d,]+(?:\.\d+)?)\s*(?:\(\s*([\d,]+(?:\.\d+)?)\s*\))?")
YEAR_RE = re.compile(r"\d{4}")


def to_float(raw: str | None) -> float | None:
    if not raw:
        return None
    return float(raw.replace(",", ""))


def parse_gallery_space(m2_field: str, sqft_field: str) -> tuple[float | None, float | None]:
    """See module docstring point 1. Returns (gallery_space_m2,
    gallery_space_sqft), either of which may be None."""
    m2_match = NUMBER_PAREN_RE.search(m2_field or "")
    sqft_match = NUMBER_PAREN_RE.search(sqft_field or "")

    gallery_space_m2 = to_float(m2_match.group(1)) if m2_match else None

    gallery_space_sqft = None
    if sqft_match and sqft_match.group(2):
        gallery_space_sqft = to_float(sqft_match.group(2))
    elif m2_match and m2_match.group(2):
        gallery_space_sqft = to_float(m2_match.group(2))

    return gallery_space_m2, gallery_space_sqft


def parse_year_established(raw: str) -> int | None:
    """See module docstring point 2. "1792" -> 1792, "1806/1908" -> 1806,
    "" or unparseable -> None."""
    match = YEAR_RE.search(raw or "")
    return int(match.group()) if match else None


def load_museums() -> list[dict]:
    if not MUSEUMS_PATH.exists():
        raise FileNotFoundError(f"{MUSEUMS_PATH} not found -- run fetch_art_museums.py first.")
    with open(MUSEUMS_PATH, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def load_iso3_to_iso2() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        raise FileNotFoundError(f"{ALIASES_PATH} not found -- run build_country_aliases.py first.")
    with open(ALIASES_PATH, encoding="utf-8") as f:
        return {iso3: entry["iso2"] for iso3, entry in json.load(f)["countries"].items()}


def build_museums_by_country(
    rows: list[dict], iso3_to_iso2: dict[str, str]
) -> tuple[dict[str, list[dict]], list[str]]:
    """Pure function: raw CSV rows + iso3->iso2 map in, ({iso2: [museum,
    ...]}, unmatched_country_names) out. Kept separate from I/O for
    testing."""
    by_country: dict[str, list[dict]] = {}
    unmatched_country_names: list[str] = []

    for row in rows:
        country_raw = row.get("Country", "").strip()
        iso3 = normalize_country(country_raw)
        iso2 = iso3_to_iso2.get(iso3) if iso3 else None
        if iso2 is None:
            if country_raw and country_raw not in unmatched_country_names:
                unmatched_country_names.append(country_raw)
            continue

        gallery_space_m2, gallery_space_sqft = parse_gallery_space(
            row.get("Gallery space in m2 (sq ft)", ""), row.get("Gallery space in sq ft", "")
        )
        year_established_raw = (row.get("Year established") or "").strip()

        by_country.setdefault(iso2, []).append(
            {
                "name": row.get("Name", "").strip(),
                "city": row.get("City", "").strip(),
                "gallery_space_m2": gallery_space_m2,
                "gallery_space_sqft": gallery_space_sqft,
                "year_established": parse_year_established(year_established_raw),
                "year_established_raw": year_established_raw,
            }
        )

    for iso2, museums in by_country.items():
        museums.sort(key=lambda m: m["gallery_space_m2"] or 0, reverse=True)

    return by_country, unmatched_country_names


def main():
    rows = load_museums()
    iso3_to_iso2 = load_iso3_to_iso2()
    by_country, unmatched_country_names = build_museums_by_country(rows, iso3_to_iso2)

    out = {
        "source": "Derived from art_museums.csv (Kaggle: drahulsingh/largest-art-museums) "
        "via build_art_museums_by_country.py -- license unresolved, see data/README.md.",
        "generated": date.today().isoformat(),
        "total_countries": len(by_country),
        "total_museums": len(rows),
        "unmatched_country_names": unmatched_country_names,
        "museums_by_country": dict(sorted(by_country.items())),
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(rows)} museums across {len(by_country)} countries -> {OUT_PATH}")
    if unmatched_country_names:
        print(
            f"{len(unmatched_country_names)} unmatched country string(s), skipped: "
            f"{unmatched_country_names} -- add to EXTRA_ALIASES in build_country_aliases.py."
        )


if __name__ == "__main__":
    main()
