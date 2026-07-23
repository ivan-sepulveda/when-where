"""
Track the latest available year for a World Bank WDI indicator, without
hammering the API on every run. Annual indicators only get a new data
point once a year (often with a lag), so this module caches the latest
known year per indicator in a JSON file, along with a "last checked"
date, and only re-queries the API when it's worth it: skip the check if
the cached year is at most 1 year behind the current year (the normal,
expected state); once it falls 2+ years behind, re-check, but no more
often than every 30 days.

Usage:
    from latest_year_cache import get_latest_year
    year = get_latest_year("NY.GDP.DEFL.KD.ZG")
"""

import json
from datetime import date
from pathlib import Path

import requests

CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "reference" / "latest_year_cache.json"
BASE_URL = "https://data360api.worldbank.org/data360/data"
DATABASE_ID = "WB_WDI"
STALE_CHECK_INTERVAL_DAYS = 30


def to_data360_indicator_id(wdi_code: str) -> str:
    return f"{DATABASE_ID}_{wdi_code.replace('.', '_')}"


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, sort_keys=True)


def _should_recheck(latest_year: int, last_checked: str, today: date) -> bool:
    """
    latest_year: cached latest year (int)
    last_checked: cached "YYYY-MM-DD" date string
    today: date to evaluate against (injectable for testing)
    """
    gap = today.year - latest_year

    if gap <= 1:
        # Normal state (indicator lags ~1 year) -- don't bother checking.
        return False

    # gap >= 2: the cache looks stale relative to what we'd expect.
    # Only actually hit the API once every STALE_CHECK_INTERVAL_DAYS.
    last_checked_date = date.fromisoformat(last_checked)
    days_since_check = (today - last_checked_date).days
    return days_since_check >= STALE_CHECK_INTERVAL_DAYS


def _fetch_latest_year_from_api(wdi_code: str, ref_area: str) -> int:
    indicator_id = to_data360_indicator_id(wdi_code)
    resp = requests.get(
        BASE_URL,
        params={
            "DATABASE_ID": DATABASE_ID,
            "INDICATOR": indicator_id,
            "REF_AREA": ref_area,
            "isLatestData": "true",
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    rows = payload.get("value", [])
    if not rows:
        raise ValueError(f"No LATEST_DATA record returned for {indicator_id} / {ref_area}")
    return int(rows[0]["TIME_PERIOD"])


def get_latest_year(
    wdi_code: str,
    ref_area: str = "USA",
    force: bool = False,
    today: date | None = None,
) -> int:
    """
    Return the latest available year for a WDI indicator, using the cache
    when possible and only hitting the API when the cache is stale enough
    to be worth rechecking (see module docstring for the schedule).

    `ref_area` is the reference country used as a proxy for "is new data
    out yet" -- USA is a reasonable default since it's reliably reported.
    `force=True` bypasses the schedule and always re-checks the API.
    """
    today = today or date.today()
    cache = _load_cache()
    entry = cache.get(wdi_code)

    if entry and not force:
        if not _should_recheck(entry["latest_year"], entry["last_checked"], today):
            return entry["latest_year"]

    latest_year = _fetch_latest_year_from_api(wdi_code, ref_area)
    cache[wdi_code] = {
        "latest_year": latest_year,
        "last_checked": today.isoformat(),
        "ref_area": ref_area,
    }
    _save_cache(cache)
    return latest_year


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("indicator_codes", nargs="*", default=["NY.GDP.DEFL.KD.ZG"])
    parser.add_argument("--ref-area", default="USA")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    for code in args.indicator_codes:
        year = get_latest_year(code, ref_area=args.ref_area, force=args.force)
        print(f"{code}: latest year = {year}")
