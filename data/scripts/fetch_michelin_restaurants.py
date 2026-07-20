"""
Fetch the Michelin Guide restaurants dataset (michelin-my-maps project) --
name, location, cuisine, price, and award tier (3/2/1 Stars, Bib Gourmand,
Selected Restaurants) for every restaurant in the MICHELIN guide.

Primary source: the Kaggle dataset via kagglehub. Requires kagglehub
installed (see requirements.txt) and Kaggle API credentials configured --
see https://github.com/Kaggle/kagglehub#authenticate. If that fails for
any reason (not installed, no credentials, network issue, etc.), this
falls back automatically to the same project's CSV published directly on
GitHub, which needs no authentication.

    Kaggle:  https://www.kaggle.com/datasets/ngshiheng/michelin-guide-restaurants-2021
    GitHub:  https://github.com/ngshiheng/michelin-my-maps

Both are the same underlying dataset (the GitHub repo is the source of
the Kaggle dataset) -- MIT licensed, scraped from the MICHELIN guide
website. See data/README.md for the license/attribution details and the
project's own disclaimer about research-only use of the scraped content.

Usage:
    python fetch_michelin_restaurants.py
    python fetch_michelin_restaurants.py --force-fallback   # skip kagglehub, use the GitHub CSV directly
"""

import argparse
import shutil
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

KAGGLE_DATASET = "ngshiheng/michelin-guide-restaurants-2021"
FALLBACK_CSV_URL = (
    "https://raw.githubusercontent.com/ngshiheng/michelin-my-maps/"
    "refs/heads/main/data/michelin_my_maps.csv"
)

# ---------------------------------------------------------------------------

RAW_DIR = Path(__file__).resolve().parent.parent / "raw" / "michelin"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
RAW_CSV_PATH = RAW_DIR / "michelin_my_maps.csv"
PROCESSED_CSV_PATH = PROCESSED_DIR / "michelin_restaurants.csv"

# As of the michelin-my-maps CSV schema this script was built against.
EXPECTED_COLUMNS = [
    "Name", "Address", "Location", "Price", "Cuisine", "Longitude", "Latitude",
    "PhoneNumber", "Url", "WebsiteUrl", "Award", "GreenStar",
    "FacilitiesAndServices", "Description",
]


def _find_csv(path: Path) -> Path:
    """
    kagglehub.dataset_download() returns a directory (usually) or
    sometimes a file, depending on version/dataset -- normalize either
    case to a single CSV file path.
    """
    if path.is_file():
        if path.suffix.lower() != ".csv":
            raise ValueError(f"Expected a CSV file, got {path}")
        return path

    candidates = sorted(path.rglob("*.csv"))
    if not candidates:
        raise FileNotFoundError(f"No CSV file found under {path}")
    # Prefer a filename that mentions "michelin" if there's more than one
    # file in the downloaded dataset.
    for c in candidates:
        if "michelin" in c.name.lower():
            return c
    return candidates[0]


def download_via_kagglehub() -> Path:
    import kagglehub  # imported lazily -- the fallback path works even if this isn't installed

    downloaded = kagglehub.dataset_download(KAGGLE_DATASET)
    csv_path = _find_csv(Path(downloaded))
    print(f"kagglehub: using {csv_path}")
    return csv_path


def download_via_fallback() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading fallback CSV from {FALLBACK_CSV_URL} ...")
    # A default urllib/requests User-Agent gets blocked by some CDNs (see
    # fetch_tourist_cities.py) -- a browser-like one avoids that.
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        )
    }
    resp = requests.get(FALLBACK_CSV_URL, headers=headers, timeout=60)
    resp.raise_for_status()
    RAW_CSV_PATH.write_bytes(resp.content)
    print(f"Saved -> {RAW_CSV_PATH}")
    return RAW_CSV_PATH


def get_source_csv(force_fallback: bool = False) -> tuple[Path, str]:
    """Returns (csv_path, source_label). Tries kagglehub first unless force_fallback."""
    if not force_fallback:
        try:
            return download_via_kagglehub(), "kagglehub"
        except Exception as exc:
            print(
                f"kagglehub download failed ({exc.__class__.__name__}: {exc}) "
                f"-- falling back to the GitHub CSV."
            )
    return download_via_fallback(), "github_fallback"


def normalize(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        print(f"WARNING: expected columns missing from source CSV: {missing}")

    # "Location" is "<City>, <Country>" -- split out for easier joining to
    # reference/tourist_cities.json later. rsplit(",", 1) rather than
    # split(",", 1) in case a city name itself ever contains a comma.
    if "Location" in df.columns:
        split = df["Location"].astype(str).str.rsplit(",", n=1, expand=True)
        df["location_city"] = split[0].str.strip()
        df["location_country"] = split[1].str.strip() if split.shape[1] > 1 else None

    if "GreenStar" in df.columns:
        df["GreenStar"] = df["GreenStar"].fillna(0).astype(int).astype(bool)

    return df


def build_michelin_restaurants(force_fallback: bool = False) -> Path:
    csv_path, source = get_source_csv(force_fallback=force_fallback)

    # Keep an untouched copy of the source under raw/, regardless of which
    # path it came from -- kagglehub's own cache lives outside this repo.
    if csv_path.resolve() != RAW_CSV_PATH.resolve():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(csv_path, RAW_CSV_PATH)

    df = normalize(csv_path)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_CSV_PATH, index=False)

    print(f"[{source}] wrote {len(df)} restaurants -> {PROCESSED_CSV_PATH}")
    return PROCESSED_CSV_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force-fallback", action="store_true",
        help="Skip kagglehub and use the GitHub CSV fallback directly",
    )
    args = parser.parse_args()
    build_michelin_restaurants(force_fallback=args.force_fallback)


if __name__ == "__main__":
    main()
