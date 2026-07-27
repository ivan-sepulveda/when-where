"""
Data Source: UNESCO World Heritage Centre Open Data (data.unesco.org)
URL: https://data.unesco.org/api/explore/v2.1/catalog/datasets/whc001/exports/json/?lang=en&timezone=America%2FMexico_City
Tables Referenced: whc001 (full World Heritage List export, one record per inscribed site)

Downloads the whc001 export (~24MB -- every record carries 6 languages'
worth of name/description text, a full inscription "justification" essay
that can run 1000+ words, and a pile of image/video URLs and captions)
and writes a much smaller, English-only, travel-scoring-relevant JSON.

What gets dropped and why (see KEEP_FIELDS below to change this):
  - name_fr/es/ru/ar/zh, short_description_fr/es/ru/ar/zh -- non-English
    localized text. Only the _en variant is kept.
  - description_en, justification_en -- description_en duplicates
    short_description_en in every record checked; justification_en is
    the single biggest field per record (a multi-paragraph inscription
    essay) and isn't needed for scoring.
  - main_image_caption_*/main_video_caption_* in every language except
    English, images_urls, videos_urls, uuid, id_no -- media/bookkeeping
    fields not needed for a destination-scoring input.
  - `coordinates` (the nested {"lon":.., "lat":..} object) is NOT
    dropped -- it's flattened to top-level `lat`/`lng` keys instead (lng,
    not lon, to match the `lat`/`lng` naming used everywhere else in this
    project -- reference/tourist_cities.json, weather_normals -- so this
    can be joined against those without a rename step).

Usage:
    python fetch_unesco_world_heritage_sites.py
    python fetch_unesco_world_heritage_sites.py --force-download   # re-download even if cached
"""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

DATASET_URL = (
    "https://data.unesco.org/api/explore/v2.1/catalog/datasets/whc001/exports/json/"
    "?lang=en&timezone=America%2FMexico_City"
)

# Fields to keep from each raw record, verbatim (before the lat/lng
# flattening step, which is separate -- see flatten_coordinates()). Add a
# field name here to keep it; anything not listed is dropped.
KEEP_FIELDS = [
    "name_en",
    "short_description_en",
    "date_inscribed",
    "secondary_dates",
    "danger",
    "date_end",
    "danger_list",
    "area_hectares",
    "cultural_criteria",
    "natural_criteria",
    "criteria_txt",
    "category",
    "category_id",
    "states_names",
    "iso_codes",
    "region",
    "region_code",
    "transboundary",
    "main_image_url",
    "main_image_author",
    "main_image_copyright",
    "main_image_caption_en",
    "main_video_url",
    "main_video_author",
    "main_video_caption_en",
    "components_list",
    "components_count",
]

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "unesco"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
RAW_PATH = RAW_DIR / "whc001.json"
OUTPUT_PATH = PROCESSED_DIR / "unesco_world_heritage_sites.json"

# ---------------------------------------------------------------------------


def download_raw(force: bool = False) -> Path:
    """Download the full export to RAW_PATH, streaming so a ~24MB response
    doesn't need to be held in memory as it comes over the wire. Cached --
    skipped entirely if RAW_PATH already exists, unless --force-download."""
    if RAW_PATH.exists() and not force:
        print(f"[unesco] raw file already cached at {RAW_PATH} -- skipping download (--force-download to refetch)")
        return RAW_PATH

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[unesco] downloading {DATASET_URL} ...")
    with requests.get(DATASET_URL, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        total_bytes = 0
        with open(RAW_PATH, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
                total_bytes += len(chunk)
    print(f"[unesco] wrote {total_bytes / 1_000_000:.1f} MB -> {RAW_PATH}")
    return RAW_PATH


def flatten_coordinates(record: dict) -> tuple[float | None, float | None]:
    """Pull lat/lng out of the raw record's nested `coordinates` object.
    Returns (lat, lng), both None if the record has no coordinates at all
    (a handful of transboundary/historical records may lack them)."""
    coords = record.get("coordinates") or {}
    return coords.get("lat"), coords.get("lon")


def reduce_record(record: dict) -> dict:
    """Keep only KEEP_FIELDS (in that order, missing fields become None
    rather than being silently absent -- keeps every output record the
    same shape), plus flattened lat/lng."""
    reduced = {field: record.get(field) for field in KEEP_FIELDS}
    lat, lng = flatten_coordinates(record)
    reduced["lat"] = lat
    reduced["lng"] = lng
    return reduced


def dropped_fields(raw_records: list[dict]) -> list[str]:
    """Every key that appears in at least one raw record but isn't in
    KEEP_FIELDS and isn't `coordinates` (which is flattened into lat/lng,
    not dropped) -- computed from the actual raw data rather than
    hand-maintained, so this stays accurate if UNESCO adds/removes a
    field. Union across all records, since not every record necessarily
    has the exact same key set."""
    all_raw_keys: set[str] = set()
    for record in raw_records:
        all_raw_keys.update(record.keys())
    return sorted(all_raw_keys - set(KEEP_FIELDS) - {"coordinates"})


def build_dataset(raw_path: Path) -> dict:
    with open(raw_path, "r", encoding="utf-8") as f:
        raw_records = json.load(f)

    sites = [reduce_record(r) for r in raw_records]
    missing_coords = sum(1 for s in sites if s["lat"] is None or s["lng"] is None)

    return {
        "source": "UNESCO World Heritage Centre Open Data (whc001) -- https://data.unesco.org/pages/home/",
        "source_query_url": DATASET_URL,
        "generated": datetime.now(timezone.utc).date().isoformat(),
        "total_sites": len(sites),
        "sites_missing_coordinates": missing_coords,
        "kept_fields": KEEP_FIELDS + ["lat", "lng"],
        "dropped_fields": dropped_fields(raw_records),
        "coordinates_note": (
            "The raw `coordinates` field ({\"lon\":.., \"lat\":..}) is not in "
            "dropped_fields above because it wasn't dropped -- it was flattened "
            "into the top-level lat/lng fields listed in kept_fields instead."
        ),
        "sites": sites,
    }


def write_output(dataset: dict) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    return OUTPUT_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download the raw export even if a cached copy already exists at data/raw/unesco/whc001.json.",
    )
    args = parser.parse_args()

    raw_path = download_raw(force=args.force_download)
    dataset = build_dataset(raw_path)
    out_path = write_output(dataset)

    raw_size_mb = raw_path.stat().st_size / 1_000_000
    out_size_mb = out_path.stat().st_size / 1_000_000
    print(
        f"[unesco] {dataset['total_sites']} sites "
        f"({dataset['sites_missing_coordinates']} missing coordinates) -> {out_path}"
    )
    print(
        f"[unesco] size: {raw_size_mb:.1f} MB raw -> {out_size_mb:.1f} MB processed "
        f"({out_size_mb / raw_size_mb:.0%} of original)"
    )


if __name__ == "__main__":
    main()
