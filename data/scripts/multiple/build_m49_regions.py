"""
Data Source: UN Statistics Division -- "Standard country or area codes for
             statistical use (M49)"
URL: https://unstats.un.org/unsd/methodology/m49/overview/
Raw file: data/raw/unsd_m49/UNSD_M49_2026-08-17.csv (committed)

Turns UNSD's own CSV export of the M49 "Full view" table into
data/reference/m49_regions.json -- a country -> geographic region lookup
keyed by ISO-alpha3, carrying ISO-alpha2 as well.

WHY THIS IS A build_ AND NOT A fetch_. The repo's TODO assumed this would
need scraping, because the M49 site is built for browsing. It doesn't: the
overview page offers the whole table as a semicolon-delimited CSV download,
and that file is committed under data/raw/ (15KB) the same way the T-100
extracts are. So this reads a local file and is fully reproducible offline,
with no scraper to rot when UNSD restyles the page. To refresh: download the
CSV from the URL above, drop it in data/raw/unsd_m49/, point RAW_CSV at it.

THE THREE TIERS, AND THE FOURTH ONE THIS FILE DERIVES. M49 nests as
World > region > sub-region > intermediate region, and its own rule is that
"each country or area is shown in one region only", so every join through
this file is 1:1 and totals can't double-count.

  region              5    Africa, Americas, Asia, Europe, Oceania
  subregion          17    Northern Africa, Sub-Saharan Africa, Northern
                           America, Latin America and the Caribbean, ...
  intermediate_region 7    ONLY under Sub-Saharan Africa (Eastern/Middle/
                           Southern/Western Africa) and Latin America and the
                           Caribbean (Caribbean/Central America/South
                           America). Null for every other country.
  detailed_region    22    DERIVED, not an M49 tier: the intermediate region
                           where one exists, else the sub-region.

**`detailed_region` is the one to chart, and it is the list the repo TODO
actually enumerated** ("Northern Africa, Eastern Africa, ... Melanesia,
Micronesia, Polynesia -- 22 in total"). Note that Eastern Africa is an
intermediate region, not a sub-region, so that list is this derived tier
rather than M49's literal `subregion` -- which is why it's computed here once
instead of in each consumer.

The difference is not cosmetic on this project's data: the literal
`subregion` tier puts Mexico, Costa Rica, Belize, Jamaica, the Bahamas and
all of South America into a single "Latin America and the Caribbean" bucket.
With 341 Mexico trips that one segment would be most of the non-domestic
chart. `detailed_region` splits it into Central America / Caribbean / South
America.

M49 ALSO ANSWERS THE CONTINENT QUESTION the repo README left open. Its
footnote defines **North America (code 003) = Northern America (021) +
Caribbean (029) + Central America (013)**, so a North/South America split is
available *within* M49 and doesn't require adopting a second, non-M49
continent scheme. Nothing here uses it yet; it's recorded in the output's
`notes` so the decision doesn't have to be re-researched.

ANTARCTICA HAS NO REGION -- it sits directly under World, and its row has
every region column blank. It is emitted with nulls rather than skipped or
folded into a neighbour, so a lookup on ATA answers "no region" instead of
missing.

NAMIBIA'S ISO-ALPHA2 IS THE STRING "NA". This module reads with the stdlib
`csv` module precisely so it stays a string -- `pandas.read_csv` turns it
into NaN unless told otherwise, which is the exact bug the repo README
already tracks against country_aliases.json. Don't "modernise" this to
pandas without `keep_default_na=False`.

TAIWAN IS NOT IN M49 AND IS ADDED SEPARATELY. The UN's list has no entry for
it, so a join on the M49 table alone drops it. This dataset has trips to
Taipei, and silently dropping them from a 100%-share chart would misreport
every affected traveler's totals, so a geographic assignment is supplied in
ADDITIONS -- kept OUT of `countries` and listed under the output's
`additions` key, so the M49 body of the file stays a faithful copy of the
source and the addition is impossible to mistake for one.

Usage:
    python build_m49_regions.py
    python build_m49_regions.py --csv path/to/other/export.csv
"""

import argparse
import csv
import json
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
RAW_CSV = DATA_DIR / "raw" / "unsd_m49" / "UNSD_M49_2026-08-17.csv"
OUT_JSON = DATA_DIR / "reference" / "m49_regions.json"

SOURCE_URL = "https://unstats.un.org/unsd/methodology/m49/overview/"

# UNSD exports this table semicolon-delimited, with a UTF-8 BOM.
DELIMITER = ";"
ENCODING = "utf-8-sig"

# Columns are read BY HEADER NAME, never by position, so a future export that
# adds a column (the LDC/LLDC/SIDS flags have moved before) still parses.
COL_REGION = "Region Name"
COL_SUBREGION = "Sub-region Name"
COL_INTERMEDIATE = "Intermediate Region Name"
COL_NAME = "Country or Area"
COL_M49 = "M49 Code"
COL_ISO2 = "ISO-alpha2 Code"
COL_ISO3 = "ISO-alpha3 Code"
REQUIRED_COLUMNS = [
    COL_REGION, COL_SUBREGION, COL_INTERMEDIATE, COL_NAME, COL_M49, COL_ISO2, COL_ISO3,
]

# Not from UNSD. See the module docstring -- M49 has no entry for Taiwan, and
# this project visits Taipei. Geographic assignment only, matching where the
# island sits relative to M49's own Eastern Asia grouping.
ADDITIONS = {
    "TWN": {
        "m49_code": None,
        "name": "Taiwan",
        "iso2": "TW",
        "region": "Asia",
        "subregion": "Eastern Asia",
        "intermediate_region": None,
        "detailed_region": "Eastern Asia",
        "source": "not in M49; added by this project (see build_m49_regions.py)",
    },
}

# What a correct parse looks like. These are properties of the M49 standard
# itself, not of one export, so a run that violates them means the input or
# the parse is wrong -- and this script would otherwise happily overwrite a
# good reference file with a broken one.
EXPECTED_REGIONS = 5
EXPECTED_DETAILED_REGIONS = 22
EXPECTED_INTERMEDIATE_REGIONS = 7
MIN_COUNTRIES = 240


def load_rows(path: Path) -> list[dict]:
    with open(path, encoding=ENCODING, newline="") as f:
        reader = csv.DictReader(f, delimiter=DELIMITER)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(
                f"{path} is missing column(s) {missing}.\n"
                f"Found: {reader.fieldnames}\n"
                f"Re-download the CSV from {SOURCE_URL}."
            )
        return list(reader)


def build(rows: list[dict]) -> tuple[dict, dict]:
    """Rows in, (countries keyed by iso3, meta) out. Pure -- no I/O."""
    countries: dict[str, dict] = {}
    regions: list[str] = []
    detailed: list[str] = []

    for row in rows:
        iso3 = (row[COL_ISO3] or "").strip()
        if not iso3:
            # Every country or area in this export has one. A blank means the
            # file has a summary row in it that this script doesn't model.
            raise SystemExit(f"Row with no ISO-alpha3 code: {row}")

        region = (row[COL_REGION] or "").strip() or None
        subregion = (row[COL_SUBREGION] or "").strip() or None
        intermediate = (row[COL_INTERMEDIATE] or "").strip() or None
        # The derived 22-value tier. Null only for Antarctica.
        detailed_region = intermediate or subregion

        if region and region not in regions:
            regions.append(region)
        if detailed_region and detailed_region not in detailed:
            detailed.append(detailed_region)

        if iso3 in countries:
            raise SystemExit(f"Duplicate ISO-alpha3 {iso3!r} -- the join would not be 1:1.")

        countries[iso3] = {
            "m49_code": (row[COL_M49] or "").strip() or None,
            "name": (row[COL_NAME] or "").strip(),
            # Kept as a string on purpose -- Namibia's is "NA".
            "iso2": (row[COL_ISO2] or "").strip() or None,
            "region": region,
            "subregion": subregion,
            "intermediate_region": intermediate,
            "detailed_region": detailed_region,
        }

    # A subregion that only ever appears as an intermediate region's parent
    # isn't one of the 22 -- no country charts as "Sub-Saharan Africa", they
    # chart as Eastern/Middle/Southern/Western Africa.
    parents = {c["subregion"] for c in countries.values() if c["intermediate_region"]}
    detailed = [name for name in detailed if name not in parents]

    subregions = sorted({c["subregion"] for c in countries.values() if c["subregion"]})
    intermediates = sorted(
        {c["intermediate_region"] for c in countries.values() if c["intermediate_region"]}
    )

    meta = {
        "regions": regions,
        "subregions": subregions,
        "intermediate_regions": intermediates,
        "detailed_regions": detailed,
        "subregions_with_intermediate_regions": sorted(parents),
    }
    return countries, meta


def validate(countries: dict, meta: dict) -> None:
    """Refuse to write anything that isn't shaped like M49. An untested parse
    silently producing a plausible-but-wrong file is the failure mode worth
    spending code on here."""
    problems = []
    if len(countries) < MIN_COUNTRIES:
        problems.append(f"only {len(countries)} countries (expected >= {MIN_COUNTRIES})")
    if len(meta["regions"]) != EXPECTED_REGIONS:
        problems.append(f"{len(meta['regions'])} regions (expected {EXPECTED_REGIONS}): "
                        f"{meta['regions']}")
    if len(meta["detailed_regions"]) != EXPECTED_DETAILED_REGIONS:
        problems.append(f"{len(meta['detailed_regions'])} detailed regions "
                        f"(expected {EXPECTED_DETAILED_REGIONS})")
    if len(meta["intermediate_regions"]) != EXPECTED_INTERMEDIATE_REGIONS:
        problems.append(f"{len(meta['intermediate_regions'])} intermediate regions "
                        f"(expected {EXPECTED_INTERMEDIATE_REGIONS})")

    bad_iso3 = [k for k in countries if len(k) != 3 or not k.isalpha() or not k.isupper()]
    if bad_iso3:
        problems.append(f"malformed ISO-alpha3: {bad_iso3[:10]}")

    iso2s = [c["iso2"] for c in countries.values() if c["iso2"]]
    if len(iso2s) != len(set(iso2s)):
        dupes = sorted({i for i in iso2s if iso2s.count(i) > 1})
        problems.append(f"duplicate ISO-alpha2: {dupes}")
    # The Namibia canary: if this is None or NaN, something read the file
    # with pandas defaults.
    namibia = countries.get("NAM", {}).get("iso2")
    if namibia != "NA":
        problems.append(f"Namibia's ISO-alpha2 is {namibia!r}, expected 'NA' -- see the docstring")

    # Every country needs a region except Antarctica, which genuinely has none.
    regionless = sorted(k for k, c in countries.items() if not c["region"])
    if regionless != ["ATA"]:
        problems.append(f"countries with no region: {regionless} (expected exactly ['ATA'])")

    if problems:
        raise SystemExit("Refusing to write -- the parse doesn't look like M49:\n  "
                         + "\n  ".join(problems))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", type=Path, default=RAW_CSV,
                        help=f"UNSD M49 CSV export. Default: {RAW_CSV.name}")
    args = parser.parse_args()

    if not args.csv.exists():
        raise SystemExit(
            f"{args.csv} not found. Download the M49 table as CSV from\n  {SOURCE_URL}\n"
            f"and save it there."
        )

    countries, meta = build(load_rows(args.csv))
    validate(countries, meta)

    payload = {
        "source": "UN Statistics Division -- Standard country or area codes for "
                  "statistical use (M49)",
        "source_url": SOURCE_URL,
        "raw_file": str(args.csv.relative_to(DATA_DIR.parent)) if args.csv.is_absolute()
                    else str(args.csv),
        "generated": date.today().isoformat(),
        "total_countries": len(countries),
        "notes": [
            "M49's own rule is that each country or area appears in exactly one region, "
            "so any join through this file is 1:1 and totals cannot double-count.",
            "`detailed_region` is DERIVED, not an M49 tier: the intermediate region where "
            "one exists, else the sub-region. 22 values. This is the tier worth charting -- "
            "the literal `subregion` tier lumps all of Latin America and the Caribbean, and "
            "all of Sub-Saharan Africa, into single buckets.",
            "M49's own footnote defines North America (003) as Northern America (021) + "
            "Caribbean (029) + Central America (013), so a North/South America split is "
            "available within M49 without adopting a second continent scheme.",
            "Antarctica (ATA) has null region/subregion -- it sits directly under World.",
            "`countries` is a faithful copy of the source. Anything this project had to add "
            "is in `additions`, never merged in silently.",
        ],
        **meta,
        "additions": ADDITIONS,
        "countries": countries,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"{len(countries)} countries or areas from {args.csv.name}")
    print(f"{len(meta['regions'])} regions: {', '.join(meta['regions'])}")
    print(f"{len(meta['detailed_regions'])} detailed regions (intermediate where one exists):")
    for name in meta["detailed_regions"]:
        print(f"    {name}")
    print(f"{len(meta['intermediate_regions'])} intermediate regions, under "
          f"{', '.join(meta['subregions_with_intermediate_regions'])}")
    if ADDITIONS:
        print(f"{len(ADDITIONS)} addition(s) NOT from M49: "
              f"{', '.join(a['name'] for a in ADDITIONS.values())}")
    print()
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
