"""
Data Source: "Airline Routes (92k) and Airports (10k)" dataset on Kaggle
URL: https://www.kaggle.com/datasets/moonnectar/airline-routes-92k-and-airports-10k-dataset
Tables Referenced: Full_Merge_of_All_Unique_Routes.csv (the dataset also
    ships separate airports/routes CSVs -- only the merged unique-routes
    file is pulled here)

Pulls the merged routes CSV via `kagglehub` (needs Kaggle API credentials
configured -- see https://github.com/Kaggle/kagglehub#authenticate) and
writes it through to data/processed/multiple/airline_routes.csv basically
as-is (only a raw/ cache copy + column listing, no reshaping -- the
schema hasn't been inspected yet since this sandbox can't reach Kaggle to
test the download; check the printed column list on first real run).

Unlike fetch_michelin_restaurants.py, there's no non-Kaggle fallback here
-- this merged file doesn't appear to be mirrored anywhere else publicly,
so a Kaggle account + API token is required to run this one.

Usage:
    python fetch_airline_routes.py
    python fetch_airline_routes.py --list-files   # show every file in the downloaded dataset, don't process
"""

import argparse
import shutil
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

KAGGLE_DATASET = "moonnectar/airline-routes-92k-and-airports-10k-dataset"
TARGET_FILENAME = "Full_Merge_of_All_Unique_Routes.csv"

# ---------------------------------------------------------------------------

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "kaggle_airline_routes"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
RAW_CSV_PATH = RAW_DIR / TARGET_FILENAME
PROCESSED_CSV_PATH = PROCESSED_DIR / "airline_routes.csv"


def download_via_kagglehub() -> Path:
    import kagglehub  # imported lazily -- only needed when this actually runs

    downloaded = Path(kagglehub.dataset_download(KAGGLE_DATASET))
    print(f"kagglehub: dataset downloaded to {downloaded}")
    return downloaded


def find_target_csv(dataset_dir: Path, filename: str = TARGET_FILENAME) -> Path:
    """
    kagglehub.dataset_download() returns a directory (usually) or
    sometimes a single file, depending on version/dataset -- normalize
    either case, then find the specific requested file (case-insensitive,
    since Kaggle uploads sometimes vary casing) rather than just grabbing
    the first CSV, since this dataset ships multiple (airports, routes,
    and this merged file).
    """
    if dataset_dir.is_file():
        return dataset_dir

    candidates = sorted(dataset_dir.rglob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No CSV files found under {dataset_dir}")

    for c in candidates:
        if c.name.casefold() == filename.casefold():
            return c

    raise FileNotFoundError(
        f"{filename!r} not found under {dataset_dir}. Files present: "
        f"{[c.name for c in candidates]} -- run with --list-files to inspect, "
        f"or update TARGET_FILENAME if the dataset's filename has changed."
    )


def list_files(dataset_dir: Path) -> None:
    if dataset_dir.is_file():
        print(dataset_dir)
        return
    for path in sorted(dataset_dir.rglob("*")):
        if path.is_file():
            print(path.relative_to(dataset_dir))


def build_airline_routes() -> Path:
    dataset_dir = download_via_kagglehub()
    csv_path = find_target_csv(dataset_dir)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    if csv_path.resolve() != RAW_CSV_PATH.resolve():
        shutil.copyfile(csv_path, RAW_CSV_PATH)

    df = pd.read_csv(RAW_CSV_PATH)
    print(f"Columns in {TARGET_FILENAME}: {list(df.columns)}")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_CSV_PATH, index=False)

    print(f"Wrote {len(df)} routes -> {PROCESSED_CSV_PATH}")
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

    build_airline_routes()


if __name__ == "__main__":
    main()
