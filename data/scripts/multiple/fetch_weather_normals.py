"""
Build data/processed/weather_normals_<year>_by_city.json: a "monthly climate
normal" per city in reference/tourist_cities.json -- typical daily high/low
temperature, precipitation, daylight, and wind for each calendar month,
derived from one full year of daily historical weather.

Data source: Open-Meteo Historical Weather API (ERA5/ERA5-Land reanalysis),
free for non-commercial use, no API key required.
https://open-meteo.com/en/docs/historical-weather-api

Usage:
    python fetch_weather_normals.py
    python fetch_weather_normals.py --limit 20        # pilot run, first 20 cities only
    python fetch_weather_normals.py --force            # re-fetch cities already in the output

Resumable by default: cities already present in the output file are skipped
on a re-run (see --force to override). This matters because pulling all
~5000 cities may need to be spread across multiple runs/days -- Open-Meteo's
free tier is 10,000 calls/day and a full year of daily data for many
variables costs more than "1 call" per the fractional pricing rules (see
data/README.md for details and the reasoning behind CITIES_PER_REQUEST).

Edit TARGET_YEAR / DAILY_VARIABLES / CITIES_PER_REQUEST below to change
what's pulled -- no need to touch the rest of the script.
"""

import argparse
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# Which year to build monthly normals from. Defaults to the last complete
# calendar year (e.g. run in 2026 -> uses 2025; run in 2027 -> uses 2026),
# so this doesn't need to be bumped by hand every January.
TARGET_YEAR = date.today().year - 1

# Daily variables to pull. Kept to <=10 to stay under Open-Meteo's
# "more than 10 variables counts as multiple calls" threshold (see
# data/README.md). temperature/precipitation/daylight map directly to the
# weather, rainfall, and daylight factors in the project's scoring model.
DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_hours",
    "daylight_duration",
    "sunshine_duration",
    "wind_speed_10m_max",
]

# How many cities' coordinates to pack into a single API request (comma
# separated lat/lon). Larger batches mean fewer requests but a longer URL
# and a bigger response to parse per call; smaller batches are safer/easier
# to resume if something fails partway. Tune after watching a real run.
CITIES_PER_REQUEST = 100

# Politeness delay between successful requests, in seconds. In practice
# Open-Meteo's historical archive endpoint starts returning HTTP 429 after
# just 2-4 batches of 25 cities/365 days/7 variables even with a 1s delay --
# whatever internal limit this is hitting is stricter than the advertised
# 600/min. 20s is a starting point to try; retune based on how often
# RATE_LIMIT_BACKOFF_SECONDS retries end up kicking in.
REQUEST_DELAY_SECONDS = 30.0

# On a 429 (rate limited), wait this long before retrying the *same* batch,
# doubling the wait on each subsequent retry, up to MAX_RATE_LIMIT_RETRIES
# attempts before giving up on this run (progress already made is kept --
# just rerun the script later to pick up where it left off).
RATE_LIMIT_BACKOFF_SECONDS = 60.0
MAX_RATE_LIMIT_RETRIES = 5

# ---------------------------------------------------------------------------

BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
CITIES_PATH = REFERENCE_DIR / "tourist_cities.json"
OUT_PATH = PROCESSED_DIR / f"weather_normals_{TARGET_YEAR}_by_city.json"

ATTRIBUTION = (
    "Open-Meteo Historical Weather API (ERA5/ERA5-Land reanalysis) -- "
    "https://open-meteo.com/en/docs/historical-weather-api"
)

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def load_cities() -> list[dict]:
    with open(CITIES_PATH, encoding="utf-8") as f:
        return json.load(f)["cities"]


def city_key(city: dict) -> str:
    """Stable identifier for a city -- used as the output dict's key and for resume/skip checks."""
    return str(city["simplemaps_id"])


def load_existing_output() -> dict:
    if OUT_PATH.exists():
        with open(OUT_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {
        "source": ATTRIBUTION,
        "year": TARGET_YEAR,
        "daily_variables": DAILY_VARIABLES,
        "generated": date.today().isoformat(),
        "cities": {},
    }


def save_output(out: dict) -> None:
    out["generated"] = date.today().isoformat()
    out["total_cities"] = len(out["cities"])
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)


def fetch_batch(cities: list[dict], year: int) -> list[dict]:
    """
    Call the archive API for a batch of cities at once (comma-separated
    lat/lon). Returns a list of per-city response dicts in the same order
    as `cities`. Open-Meteo returns a single JSON object (not a list) when
    only one location is requested -- normalized to a one-item list here so
    callers don't have to special-case it.
    """
    lats = ",".join(str(c["lat"]) for c in cities)
    lngs = ",".join(str(c["lng"]) for c in cities)
    params = {
        "latitude": lats,
        "longitude": lngs,
        "start_date": f"{year}-01-01",
        "end_date": f"{year}-12-31",
        "daily": ",".join(DAILY_VARIABLES),
        # "auto" resolves each coordinate to its own local timezone, so
        # daily aggregates line up with local calendar days/months rather
        # than UTC -- important for a *monthly* normal.
        "timezone": "auto",
    }
    resp = requests.get(BASE_URL, params=params, timeout=120)
    resp.raise_for_status()
    payload = resp.json()
    return payload if isinstance(payload, list) else [payload]


def aggregate_monthly(daily: dict) -> dict:
    """
    Turn one city's raw daily arrays (as returned under the "daily" key)
    into 12 calendar-month summaries.
    """
    df = pd.DataFrame({"date": pd.to_datetime(daily["time"])})
    for var in DAILY_VARIABLES:
        df[var] = daily.get(var)
    df["month"] = df["date"].dt.month

    months = {}
    for m in range(1, 13):
        rows = df[df["month"] == m]
        if rows.empty:
            months[MONTH_NAMES[m - 1]] = None
            continue

        rainy_days = int((rows["precipitation_sum"] >= 1.0).sum())
        months[MONTH_NAMES[m - 1]] = {
            "days_sampled": int(len(rows)),
            "avg_high_c": round(rows["temperature_2m_max"].mean(), 1),
            "avg_low_c": round(rows["temperature_2m_min"].mean(), 1),
            "total_precipitation_mm": round(rows["precipitation_sum"].sum(), 1),
            "avg_precipitation_hours_per_day": round(rows["precipitation_hours"].mean(), 1),
            "rainy_days": rainy_days,
            "avg_daylight_hours": round(rows["daylight_duration"].mean() / 3600, 1),
            "avg_sunshine_hours": round(rows["sunshine_duration"].mean() / 3600, 1),
            "avg_max_wind_kmh": round(rows["wind_speed_10m_max"].mean(), 1),
        }
    return months


def fetch_batch_with_retry(batch: list[dict], year: int) -> tuple[list[dict] | None, bool]:
    """
    Wraps fetch_batch() with automatic retry-with-backoff on HTTP 429.
    Returns (responses, should_stop_run):
      - (responses, False) on success.
      - (None, False) on a non-429 failure -- caller should skip this batch
        and move on to the next one.
      - (None, True) if still rate-limited after MAX_RATE_LIMIT_RETRIES --
        caller should stop the whole run (progress so far is unaffected;
        rerunning the script later will resume from here).
    """
    wait = RATE_LIMIT_BACKOFF_SECONDS
    for attempt in range(1, MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return fetch_batch(batch, year), False
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status != 429:
                print(f"  FAILED (HTTP {status}): {exc}. Skipping this batch.")
                return None, False
            if attempt == MAX_RATE_LIMIT_RETRIES:
                print(
                    f"  RATE LIMITED (HTTP 429) after {MAX_RATE_LIMIT_RETRIES} retries -- "
                    f"stopping this run. Progress so far is already saved; "
                    f"rerun this script later (no --force) to pick up where it left off."
                )
                return None, True
            print(
                f"  RATE LIMITED (HTTP 429) -- waiting {wait:.0f}s before "
                f"retry {attempt}/{MAX_RATE_LIMIT_RETRIES}..."
            )
            time.sleep(wait)
            wait *= 2
    return None, True  # unreachable


def build_weather_normals(limit: int | None = None, force: bool = False) -> Path:
    cities = load_cities()
    if limit is not None:
        cities = cities[:limit]

    out = load_existing_output()
    if force:
        out["cities"] = {}

    pending = [c for c in cities if force or city_key(c) not in out["cities"]]
    print(
        f"{len(cities)} cities requested, {len(cities) - len(pending)} already "
        f"in {OUT_PATH.name}, {len(pending)} to fetch."
    )

    for i in range(0, len(pending), CITIES_PER_REQUEST):
        batch = pending[i : i + CITIES_PER_REQUEST]
        print(
            f"Fetching batch {i // CITIES_PER_REQUEST + 1} "
            f"({len(batch)} cities: {batch[0]['city']}..{batch[-1]['city']}) ..."
        )
        responses, should_stop = fetch_batch_with_retry(batch, TARGET_YEAR)
        if should_stop:
            break
        if responses is None:
            continue

        if len(responses) != len(batch):
            print(
                f"  WARNING: requested {len(batch)} cities but got "
                f"{len(responses)} responses back -- skipping this batch to "
                f"avoid mismatched city/data pairing."
            )
            continue

        for city, resp in zip(batch, responses):
            if "daily" not in resp:
                print(f"  WARNING: no daily data for {city['city']} ({city['country']}) -- skipped")
                continue
            out["cities"][city_key(city)] = {
                "city": city["city"],
                "country": city["country"],
                "admin_name": city.get("admin_name"),
                "lat": city["lat"],
                "lng": city["lng"],
                "months": aggregate_monthly(resp["daily"]),
            }

        save_output(out)  # checkpoint after every batch, not just at the end
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Done. {len(out['cities'])}/{len(cities)} cities -> {OUT_PATH}")
    return OUT_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Only process the first N cities (for a pilot run)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-fetch cities already present in the output file",
    )
    args = parser.parse_args()
    build_weather_normals(limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()
