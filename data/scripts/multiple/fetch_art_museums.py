"""
Data Source: "Largest-art-museums" dataset on Kaggle
URL: https://www.kaggle.com/datasets/drahulsingh/largest-art-museums
Tables Referenced: whichever single CSV the dataset ships (see
    find_target_csv() below -- the exact filename hasn't been confirmed
    since this sandbox can't reach Kaggle to test the download)

Pulls the museum list via `kagglehub` (needs Kaggle API credentials
configured -- see https://github.com/Kaggle/kagglehub#authenticate) and
writes it through to data/processed/multiple/art_museums.csv basically
as-is (only a raw/ cache copy + column listing, no reshaping -- same
"schema unconfirmed, check the printed column list on first real run"
situation as fetch_airline_routes.py was in before its first real run).

What this almost certainly contains, based on the dataset's public
description ("112 art museums, including their names, locations, gallery
space, and year established") and a cross-check against Wikipedia's
"List of largest art museums" (which the dataset appears to be scraped
from -- same museum count and column shape): museum name, city, country,
gallery space (m2/ft2), and year established. Not confirmed first-hand --
verify against the printed column list once this actually runs.

License: unresolved. The Kaggle listing doesn't surface a clear license
in search results, and this sandbox can't load the dataset page's license
field directly. Confirm the license on the dataset page before this data
goes beyond personal/internal use -- same caveat this project already
carries for UNESCO World Heritage Site data (see data/README.md).

Usage:
    python fetch_art_museums.py
    python fetch_art_museums.py --list-files   # show every file in the downloaded dataset, don't process
"""

import argparse
import shutil
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

KAGGLE_DATASET = "drahulsingh/largest-art-museums"
# Unconfirmed -- the dataset page reports "1 CSV file" but not its name.
# find_target_csv() below falls back to "the only CSV present" when this
# doesn't match, so this is a hint, not a hard requirement. Update it (and
# this comment) once the real filename is known from a first real run.
TARGET_FILENAME = "largest-art-museums.csv"

# ---------------------------------------------------------------------------

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "kaggle_art_museums"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
PROCESSED_CSV_PATH = PROCESSED_DIR / "art_museums.csv"


def download_via_kagglehub() -> Path:
    import kagglehub  # imported lazily -- only needed when this actually runs

    downloaded = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    print(f"kagglehub: dataset downloaded to {downloaded}")
    return downloaded


def find_target_csv(dataset_dir: Path, filename: str = TARGET_FILENAME) -> Path:
    """
    kagglehub.dataset_download() returns a directory (usually) or
    sometimes a single file, depending on version/dataset -- normalize
    either case. Tries an exact (case-insensitive) filename match first;
    if that misses but there's exactly one CSV in the dataset (expected
    here -- the Kaggle listing reports "1 CSV file"), falls back to that
    rather than failing over a filename guess. Only raises if there's
    real ambiguity (zero or multiple CSVs with no match).
    """
    if dataset_dir.is_file():
        return dataset_dir

    candidates = sorted(dataset_dir.rglob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No CSV files found under {dataset_dir}")

    for c in candidates:
        if c.name.casefold() == filename.casefold():
            return c

    if len(candidates) == 1:
        print(f"Note: TARGET_FILENAME {filename!r} didn't match -- using the only CSV "
              f"found instead: {candidates[0].name!r}. Update TARGET_FILENAME to silence this.")
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


def build_art_museums() -> Path:
    dataset_dir = download_via_kagglehub()
    csv_path = find_target_csv(dataset_dir)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_csv_path = RAW_DIR / csv_path.name
    if csv_path.resolve() != raw_csv_path.resolve():
        shutil.copyfile(csv_path, raw_csv_path)

    df = pd.read_csv(raw_csv_path)
    print(f"Columns in {csv_path.name}: {list(df.columns)}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_CSV_PATH, index=False)

    print(f"Wrote {len(df)} museums -> {PROCESSED_CSV_PATH}")
    return PROCESSED_CSV_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="Download the dataset and print every file found in it, without processing anything.",
    )
    args = parser.parse_args()

    if args.list_files:
        list_files(download_via_kagglehub())
        return

    build_art_museums()


if __name__ == "__main__":
    main()
