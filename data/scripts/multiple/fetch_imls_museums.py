"""
Data Source: "Museums, Aquariums, and Zoos" (the IMLS Museum Data Files) on Kaggle
URL: https://www.kaggle.com/datasets/imls/museum-directory
Tables Referenced: whichever CSV(s) the dataset ships (see find_museum_csvs()
    below -- the IMLS release is split across three files by discipline group,
    and the Kaggle mirror may ship them either way, so this script reads and
    concatenates every CSV it finds rather than guessing one filename)

Pulls the US museum directory via `kagglehub` (needs Kaggle API credentials --
see https://github.com/Kaggle/kagglehub#authenticate) and writes
data/processed/multiple/imls_museums.csv: one row per museum, normalized down
to the seven fields this project actually uses -- NAME, DISCIPLINE,
DISCIPLINE_LABEL, CITY, STATE, LAT, LNG.

Why this dataset: it's the only one in this project with per-institution
coordinates for zoos, aquariums and botanical gardens, which is what
build_city_attractions.py needs to answer "what's within 100km of this city"
the same way UNESCO sites and Michelin restaurants already are. The disciplines
that matter downstream:
  - ZAW: Zoos, Aquariums, & Wildlife Conservation
  - BOT: Arboretums, Botanical Gardens, & Nature Centers
  - ART: Art Museums -- used to enrich the city page's existing Art Museums
    section, which otherwise only knows the ~112 largest art museums worldwide
    (see build_art_museums_by_country.py) and so shows almost nothing for a
    US city.
Every other discipline (history, science, children's, natural history,
historical societies, general) is kept in the output too -- it costs nothing
to carry and saves re-running this if a section for one of them ever gets
built -- but nothing consumes it yet.

COVERAGE, and this is the important caveat: IMLS is a US federal agency and
this file covers all 50 US states plus DC and nothing else. It is NOT a world
museum directory. Every non-US city gets zero rows from this source, which is
exactly why fetch_osm_zoos_and_gardens.py exists alongside it -- that one
covers the same three categories worldwide, at the cost of OSM's uneven
community-mapping density. build_city_attractions.py merges both.

License: public domain, unusually cleanly for this project. The IMLS data file
documentation states: "Unless specifically noted, all information contained
herein is in the public domain and may be used and reprinted without special
permission. Citation of this source is required." -- see
https://www.imls.gov/sites/default/files/museum_data_file_documentation_and_users_guide.pdf
The Kaggle listing is a mirror of that federal release; the ATTRIBUTION string
below is written into the output as a reminder that citation, not permission,
is what's required here. Contrast with UNESCO's unresolved license and OSM's
share-alike ODbL (see data/README.md).

SCHEMA IS UNCONFIRMED FIRST-HAND. This sandbox can't reach Kaggle
(api.kaggle.com is blocked), same situation fetch_art_museums.py was written
in. Two header conventions are known to exist for this data -- the raw IMLS
release uses short uppercase codes (COMMONNAME, DISCIPLINE, LATITUDE,
LONGITUDE, PHCITY, PHSTATE), while the Kaggle mirror is generally described
with human-readable headers ("Museum Name", "Museum Type", "Latitude",
"Longitude", "City (Physical Location)") -- so COLUMN_CANDIDATES below accepts
either, and resolve_columns() prints exactly what it matched. Run it once and
check that printout before trusting the output; if a header matches neither
list, add it to the relevant tuple rather than renaming anything upstream.

Usage:
    python fetch_imls_museums.py
    python fetch_imls_museums.py --list-files     # show every file in the download, don't process
    python fetch_imls_museums.py --list-columns   # show each CSV's headers, don't process
"""

import argparse
import shutil
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

KAGGLE_DATASET = "imls/museum-directory"

# Header name candidates per output field, tried in order, matched
# case-insensitively and ignoring surrounding whitespace. First tuple entry
# is the raw-IMLS name, the rest are the human-readable variants the Kaggle
# mirror is described with. A field with no match is fatal for NAME/LAT/LNG
# (nothing downstream works without them) and blank-but-tolerated for the
# rest -- see resolve_columns().
COLUMN_CANDIDATES = {
    "NAME": ("COMMONNAME", "Museum Name", "MUSEUM NAME", "LEGALNAME", "Legal Name"),
    "DISCIPLINE": ("DISCIPLINE", "Museum Type", "MUSEUM TYPE", "DISCIPL"),
    # Physical location first, mailing/administrative address second -- for a
    # museum whose admin office sits elsewhere, the physical address is the
    # one a traveler cares about. (LAT/LNG below are the actual join key
    # regardless; CITY/STATE are for display and sanity-checking.)
    "CITY": ("PHCITY", "City (Physical Location)", "ADCITY", "City (Administrative Location)", "CITY"),
    "STATE": ("PHSTATE", "State (Physical Location)", "ADSTATE", "State (Administrative Location)", "STATE"),
    "LAT": ("LATITUDE", "Latitude", "LAT"),
    "LNG": ("LONGITUDE", "Longitude", "LONG", "LNG"),
}

# IMLS discipline code -> the label this project displays. Codes are from the
# IMLS user's guide (see the URL in this module's docstring). The Kaggle
# mirror's human-readable "Museum Type" values are mapped onto the same codes
# by normalize_discipline() below, so downstream code only ever sees the code.
DISCIPLINE_LABELS = {
    "ART": "Art Museum",
    "BOT": "Arboretum, Botanical Garden, or Nature Center",
    "CMU": "Children's Museum",
    "GMU": "General Museum",
    "HSC": "Historical Society or Historic Preservation",
    "HST": "History Museum",
    "NAT": "Natural History or Natural Science Museum",
    "SCI": "Science & Technology Museum or Planetarium",
    "ZAW": "Zoo, Aquarium, or Wildlife Conservation",
}

# Substring -> code, for the Kaggle mirror's spelled-out type values (e.g.
# "ZOO, AQUARIUM, OR WILDLIFE CONSERVATION"). Matched against an uppercased
# value, first hit wins, so order matters where two labels share a word:
# "NATURAL HISTORY" must be tested before "HISTORY", and "SCIENCE" before
# "NATURAL SCIENCE" would be wrong for the same reason -- hence the explicit
# ordering here rather than a plain dict comprehension over DISCIPLINE_LABELS.
DISCIPLINE_KEYWORDS = (
    ("ZOO", "ZAW"),
    ("AQUARIUM", "ZAW"),
    ("WILDLIFE", "ZAW"),
    ("BOTANIC", "BOT"),
    ("ARBORET", "BOT"),
    ("NATURE CENTER", "BOT"),
    ("ART", "ART"),
    ("CHILDREN", "CMU"),
    ("NATURAL HISTORY", "NAT"),
    ("NATURAL SCIENCE", "NAT"),
    ("SCIENCE", "SCI"),
    ("TECHNOLOG", "SCI"),
    ("PLANETARIUM", "SCI"),
    ("HISTORICAL SOCIET", "HSC"),
    ("HISTORIC PRESERVATION", "HSC"),
    ("HISTORY", "HST"),
    ("GENERAL", "GMU"),
    ("UNCATEGORIZED", "GMU"),
)

ATTRIBUTION = (
    "Institute of Museum and Library Services (IMLS), Museum Data Files -- "
    "public domain, citation required. https://www.imls.gov/research-evaluation/data-collection/museum-data-files"
)

# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = DATA_DIR / "raw" / "kaggle_imls_museums"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
PROCESSED_CSV_PATH = PROCESSED_DIR / "imls_museums.csv"

FIELDNAMES = ["NAME", "DISCIPLINE", "DISCIPLINE_LABEL", "CITY", "STATE", "LAT", "LNG"]


def download_via_kagglehub() -> Path:
    import kagglehub  # imported lazily -- only needed when this actually runs

    downloaded = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    print(f"kagglehub: dataset downloaded to {downloaded}")
    return downloaded


def find_museum_csvs(dataset_dir: Path) -> list[Path]:
    """Every CSV in the download, sorted. Unlike fetch_art_museums.py's
    find_target_csv(), this deliberately does NOT try to pick one file: the
    IMLS release is split into three files by discipline group (the
    ART/BOT/CMU/HST/NAT/SCI/ZAW file, the general-museums file, and the
    historical-societies file), and which of those the Kaggle mirror ships --
    all three, or one pre-merged file -- isn't confirmed from here. Reading
    every CSV and concatenating handles both shapes; the deduplication in
    build_museum_table() below keeps a pre-merged file from double-counting
    if the mirror happens to ship both."""
    if dataset_dir.is_file():
        return [dataset_dir]

    candidates = sorted(dataset_dir.rglob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No CSV files found under {dataset_dir}")
    return candidates


def list_files(dataset_dir: Path) -> None:
    if dataset_dir.is_file():
        print(dataset_dir)
        return
    for path in sorted(dataset_dir.rglob("*")):
        if path.is_file():
            print(path.relative_to(dataset_dir))


def resolve_columns(columns) -> dict[str, str]:
    """Output field -> the actual header in this CSV, matched
    case-insensitively against COLUMN_CANDIDATES. Prints what it matched (and
    what it didn't) since this script's schema is unconfirmed -- see the
    module docstring. Raises if NAME, LAT or LNG can't be resolved: a row
    with no name is undisplayable and a row with no coordinates can't be
    joined to a city, so there'd be nothing left to write."""
    normalized = {str(c).strip().casefold(): str(c) for c in columns}

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for field, candidates in COLUMN_CANDIDATES.items():
        for candidate in candidates:
            actual = normalized.get(candidate.casefold())
            if actual is not None:
                resolved[field] = actual
                break
        else:
            missing.append(field)

    print(f"  resolved columns: { {k: v for k, v in resolved.items()} }")
    if missing:
        print(f"  NO MATCH for: {missing} (left blank -- add the real header to COLUMN_CANDIDATES)")

    required = [f for f in ("NAME", "LAT", "LNG") if f not in resolved]
    if required:
        raise KeyError(
            f"Required field(s) {required} matched no column. Headers present: {list(columns)} -- "
            f"add the right ones to COLUMN_CANDIDATES and re-run."
        )
    return resolved


def normalize_discipline(value) -> str:
    """A raw IMLS code ("ZAW"), a spelled-out Kaggle label ("ZOO, AQUARIUM,
    OR WILDLIFE CONSERVATION"), or anything else -> a code from
    DISCIPLINE_LABELS, or "" for a value this doesn't recognize.

    Returns "" rather than guessing a default: an unrecognized discipline
    silently filed under, say, GMU would quietly put a mystery institution
    into a section it may not belong in, whereas "" makes it visibly
    unclassified in the output and in this script's summary."""
    if not isinstance(value, str):
        return ""

    text = value.strip().upper()
    if text in DISCIPLINE_LABELS:
        return text

    for keyword, code in DISCIPLINE_KEYWORDS:
        if keyword in text:
            return code
    return ""


def build_museum_table() -> Path:
    dataset_dir = download_via_kagglehub()
    csv_paths = find_museum_csvs(dataset_dir)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frames: list[pd.DataFrame] = []

    for csv_path in csv_paths:
        raw_csv_path = RAW_DIR / csv_path.name
        if csv_path.resolve() != raw_csv_path.resolve():
            shutil.copyfile(csv_path, raw_csv_path)

        # low_memory=False: these files are wide (50 columns) with sparse
        # financial fields, which makes pandas' chunked type inference emit
        # DtypeWarnings and guess inconsistently between chunks.
        df = pd.read_csv(raw_csv_path, low_memory=False)
        print(f"{csv_path.name}: {len(df)} rows, {len(df.columns)} columns")

        resolved = resolve_columns(df.columns)
        out = pd.DataFrame(
            {
                field: (df[resolved[field]] if field in resolved else pd.Series([None] * len(df)))
                for field in ("NAME", "DISCIPLINE", "CITY", "STATE", "LAT", "LNG")
            }
        )
        frames.append(out)

    museums = pd.concat(frames, ignore_index=True)

    museums["NAME"] = museums["NAME"].astype("string").str.strip()
    museums["CITY"] = museums["CITY"].astype("string").str.strip()
    museums["STATE"] = museums["STATE"].astype("string").str.strip()
    museums["DISCIPLINE"] = museums["DISCIPLINE"].map(normalize_discipline)
    museums["DISCIPLINE_LABEL"] = museums["DISCIPLINE"].map(lambda c: DISCIPLINE_LABELS.get(c, ""))
    museums["LAT"] = pd.to_numeric(museums["LAT"], errors="coerce")
    museums["LNG"] = pd.to_numeric(museums["LNG"], errors="coerce")

    before = len(museums)

    # Dropped, in this order, with each count reported below:
    #   1. no name -- nothing to display.
    #   2. no usable coordinates -- can't be joined to a city by distance,
    #      which is the only thing this data is used for downstream. (IMLS
    #      geocodes from the administrative address, so a handful of records
    #      legitimately have none.)
    #   3. exact duplicates on (name, lat, lng) -- see find_museum_csvs()
    #      for why the same museum could appear twice.
    named = museums[museums["NAME"].notna() & (museums["NAME"] != "")]
    dropped_unnamed = before - len(named)

    located = named[named["LAT"].notna() & named["LNG"].notna()]
    dropped_unlocated = len(named) - len(located)

    # 0,0 is the Gulf of Guinea, not a US museum -- a classic failed-geocode
    # sentinel. Cheap to drop, and leaving it in would put phantom museums
    # within 100km of Accra.
    located = located[(located["LAT"] != 0) | (located["LNG"] != 0)]

    deduped = located.drop_duplicates(subset=["NAME", "LAT", "LNG"])
    dropped_duplicate = len(located) - len(deduped)

    result = deduped[FIELDNAMES].sort_values(["STATE", "CITY", "NAME"], na_position="last")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    result.to_csv(PROCESSED_CSV_PATH, index=False)

    print(f"\nWrote {len(result)} museums -> {PROCESSED_CSV_PATH}")
    print(f"  dropped: {dropped_unnamed} unnamed, {dropped_unlocated} without coordinates, {dropped_duplicate} duplicates")
    print("  by discipline:")
    for code, count in result["DISCIPLINE"].value_counts().items():
        label = DISCIPLINE_LABELS.get(code, "UNRECOGNIZED -- check normalize_discipline()")
        print(f"    {code or '(blank)':>4}  {count:>6}  {label}")
    print(f"\n  {ATTRIBUTION}")
    return PROCESSED_CSV_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--list-files", action="store_true", help="Download the dataset and print every file in it, without processing."
    )
    parser.add_argument(
        "--list-columns",
        action="store_true",
        help="Download the dataset and print each CSV's headers, without processing. Use this first if the run below errors on a missing column.",
    )
    args = parser.parse_args()

    if args.list_files:
        list_files(download_via_kagglehub())
        return

    if args.list_columns:
        for csv_path in find_museum_csvs(download_via_kagglehub()):
            print(f"\n{csv_path.name}:")
            print(f"  {list(pd.read_csv(csv_path, nrows=0).columns)}")
        return

    build_museum_table()


if __name__ == "__main__":
    main()
