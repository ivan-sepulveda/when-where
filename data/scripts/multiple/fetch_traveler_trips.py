"""
Data Source: "Traveler Trip Data" on Kaggle
URL: https://www.kaggle.com/datasets/rkiattisak/traveler-trip-data
Tables Referenced: "Travel details dataset.csv" (~13KB, 139 rows) -- see
    find_target_csv() below, which falls back to "the only CSV present" if
    that filename has changed

Pulls the traveler/trip table via `kagglehub` (needs Kaggle API credentials --
see https://github.com/Kaggle/kagglehub#authenticate) and writes it through to
data/processed/multiple/traveler_trips.csv essentially as-is -- a raw cache
copy plus a printed column list, no reshaping. All the cleaning (currency
strings, date formats, "7 days" durations) happens in build_travelers.py, the
same fetch-then-clean split fetch_art_museums.py and
build_art_museums_by_country.py already use.

What this is: 139 trips with, per trip, a destination, start/end dates,
duration, and the traveler's name, age, gender and nationality, plus
accommodation and transportation type and cost. Confirmed column list (13):
Trip ID, Destination, Start date, End date, Duration (days), Traveler name,
Traveler age, Traveler gender, Traveler nationality, Accommodation type,
Accommodation cost, Transportation type, Transportation cost.

WHAT IT IS NOT, and this matters for how far it can be trusted: this is a
small teaching/sample dataset, not a real booking log or survey. 139 trips
across a handful of repeated traveler names is enough to build and demo a
recommendation UI against -- which is exactly what /rec-sys uses it for -- but
it is not a basis for any statistical claim about how people actually travel.
Treat it as fixture data with a plausible shape.

There's also no traveler ID in it: the same person is identifiable only by
their name and nationality repeating across rows. build_travelers.py is where
that grouping decision lives (and it's a decision, not a lookup -- see that
script's docstring).

License: CC BY 4.0. The Zenodo mirror of this dataset
(https://zenodo.org/records/10907914, DOI 10.5281/zenodo.10907914) states
Creative Commons Attribution 4.0 International, which requires attribution but
allows redistribution and reuse. Cleaner than the UNESCO/Michelin situation,
same family as this project's other CC BY sources -- but confirm the Kaggle
listing's own license field on the first real run, since a mirror's license
statement and the original uploader's aren't guaranteed to match.

SCHEMA IS UNCONFIRMED FIRST-HAND: this sandbox can't reach Kaggle
(api.kaggle.com is blocked), same situation fetch_art_museums.py and
fetch_imls_museums.py were written in. The column list above comes from the
dataset's public documentation, not from a real run. This script writes
whatever it finds through unchanged and prints the real headers, so it can't
be wrong about the schema -- build_travelers.py is the one that has to match
column names, and it resolves them defensively for the same reason.

Usage:
    python fetch_traveler_trips.py
    python fetch_traveler_trips.py --list-files   # show every file in the download, don't process
"""

import argparse
import shutil
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

KAGGLE_DATASET = "rkiattisak/traveler-trip-data"

# Confirmed from the dataset's public documentation and its Zenodo mirror, but
# not from a real run here -- find_target_csv() falls back to the only CSV
# present if this doesn't match, so it's a hint rather than a requirement.
TARGET_FILENAME = "Travel details dataset.csv"

ATTRIBUTION = (
    "Traveler Trip Data (rkiattisak) via Kaggle -- CC BY 4.0, attribution required. "
    "https://www.kaggle.com/datasets/rkiattisak/traveler-trip-data"
)

# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = DATA_DIR / "raw" / "kaggle_traveler_trips"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
PROCESSED_CSV_PATH = PROCESSED_DIR / "traveler_trips.csv"


def download_via_kagglehub() -> Path:
    import kagglehub  # imported lazily -- only needed when this actually runs

    downloaded = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    print(f"kagglehub: dataset downloaded to {downloaded}")
    return downloaded


def find_target_csv(dataset_dir: Path, filename: str = TARGET_FILENAME) -> Path:
    """Same "exact match, else the only CSV, else complain" resolution as
    fetch_art_museums.py's function of the same name -- this dataset is also
    a single-CSV listing, so a filename change shouldn't break the run."""
    if dataset_dir.is_file():
        return dataset_dir

    candidates = sorted(dataset_dir.rglob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No CSV files found under {dataset_dir}")

    for c in candidates:
        if c.name.casefold() == filename.casefold():
            return c

    if len(candidates) == 1:
        print(
            f"Note: TARGET_FILENAME {filename!r} didn't match -- using the only CSV "
            f"found instead: {candidates[0].name!r}. Update TARGET_FILENAME to silence this."
        )
        return candidates[0]

    raise FileNotFoundError(
        f"{filename!r} not found under {dataset_dir}, and more than one CSV is present so "
        f"none was picked automatically. Files present: {[c.name for c in candidates]} -- "
        f"run with --list-files to inspect, or update TARGET_FILENAME."
    )


def list_files(dataset_dir: Path) -> None:
    if dataset_dir.is_file():
        print(dataset_dir)
        return
    for path in sorted(dataset_dir.rglob("*")):
        if path.is_file():
            print(path.relative_to(dataset_dir))


def build_traveler_trips() -> Path:
    dataset_dir = download_via_kagglehub()
    csv_path = find_target_csv(dataset_dir)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_csv_path = RAW_DIR / csv_path.name
    if csv_path.resolve() != raw_csv_path.resolve():
        shutil.copyfile(csv_path, raw_csv_path)

    df = pd.read_csv(raw_csv_path)
    print(f"Columns in {csv_path.name}: {list(df.columns)}")
    print(f"Rows: {len(df)}")

    # Written through unchanged on purpose -- build_travelers.py does the
    # cleaning, so this file stays a faithful copy of the source and any
    # parsing bug is fixable without re-downloading.
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_CSV_PATH, index=False)

    print(f"\nWrote {len(df)} trips -> {PROCESSED_CSV_PATH}")
    print("Next: python scripts/multiple/build_travelers.py")
    print(f"  {ATTRIBUTION}")
    return PROCESSED_CSV_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--list-files", action="store_true", help="Download the dataset and print every file in it, without processing."
    )
    args = parser.parse_args()

    if args.list_files:
        list_files(download_via_kagglehub())
        return

    build_traveler_trips()


if __name__ == "__main__":
    main()
