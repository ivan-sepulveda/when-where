"""
Build data/processed/monthly_scores_<year>_by_city.json: a set of simple,
transparent, rule-based scores per city per calendar month, derived from
processed/multiple/weather_normals_<year>_by_city.json (see
scripts/multiple/fetch_weather_normals.py). This script itself stays at
scripts/ root (and writes its own output to processed/ root) since it isn't
a geography-scoped fetch -- only its weather-normals *input* lives under
multiple/.

This is intentionally a rule-based model, not a learned one -- each score
is a plain formula over one weather-normal field, documented below and in
data/README.md, so it's easy to see why a city/month scored the way it did
and to adjust the rules later.

Usage:
    python compute_monthly_scores.py
    python compute_monthly_scores.py --year 2024   # score a different year's weather_normals file

Edit HIGH_TEMP_THRESHOLD_C / LOW_TEMP_THRESHOLD_C below to change the
temperature cutoffs -- no need to touch the rest of the script.
"""

import argparse
import json
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# Which year's weather_normals file to score. Defaults to the last complete
# calendar year, matching fetch_weather_normals.py's default -- so running
# this with no arguments scores whatever that script would have just built.
SCORE_YEAR = date.today().year - 1

# A month scores 0 (worst) on HIGH_TEMPERATURE_SCORE once its average daily
# high reaches this many degrees C, otherwise 1 (best).
HIGH_TEMP_THRESHOLD_C = 35

# A month scores 0 (worst) on LOW_TEMPERATURE_SCORE once its average daily
# low drops to this many degrees C or below, otherwise 1 (best).
LOW_TEMP_THRESHOLD_C = 0

# WIND_INTENSITY_SCORE scales linearly from 0 (calm) to 1 (uncomfortable) as
# avg_max_wind_kmh goes from 0 to this many km/h, then stays capped at 1
# beyond it. 80 km/h sits at the boundary between Beaufort force 9 (Strong
# Gale) and force 10 (Storm) -- see the Beaufort scale reference table in
# data/README.md for how the rest of the scale maps onto this 0-1 range.
WIND_COMFORT_CEILING_KMH = 80

# ---------------------------------------------------------------------------

HOURS_PER_DAY = 24  # unit-conversion constant, not really "tunable"

# Output stays at processed/ root (this script isn't a geography-scoped
# fetch), but its weather-normals input now lives under processed/multiple/.
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
WEATHER_DIR = PROCESSED_DIR / "multiple"

ATTRIBUTION = (
    "Derived from Open-Meteo Historical Weather API data via "
    "fetch_weather_normals.py -- see data/README.md"
)


def weather_normals_path(year: int) -> Path:
    return WEATHER_DIR / f"weather_normals_{year}_by_city.json"


def scores_output_path(year: int) -> Path:
    return PROCESSED_DIR / f"monthly_scores_{year}_by_city.json"


def load_weather_normals(year: int) -> dict:
    path = weather_normals_path(year)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found -- run scripts/multiple/fetch_weather_normals.py first "
            f"(or pass --year to score a different year that's already been pulled)."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def compute_month_scores(month: dict | None) -> dict | None:
    """
    Compute the six rule-based scores for one city/month's weather normal.
    Returns None if there's no data for that month (e.g. an incomplete pull).

        MONTHLY_RAIN_SCORE   = rainy_days / days_sampled
        DAILY_RAIN_SCORE     = avg_precipitation_hours_per_day / 24
        DAYLIGHT_HOURS_SCORE = avg_sunshine_hours / 24
        HIGH_TEMPERATURE_SCORE = 0 if avg_high_c >= HIGH_TEMP_THRESHOLD_C else 1
        LOW_TEMPERATURE_SCORE  = 0 if avg_low_c <= LOW_TEMP_THRESHOLD_C else 1
        WIND_INTENSITY_SCORE  = min(avg_max_wind_kmh / WIND_COMFORT_CEILING_KMH, 1)

    None of these are combined into one overall score here -- that's a
    traveler-profile-specific weighting decision left for downstream code
    (see the project's guidance on supporting different traveler profiles).
    """
    if month is None or not month.get("days_sampled"):
        return None

    wind_intensity_score = max(month["avg_max_wind_kmh"], 0) / WIND_COMFORT_CEILING_KMH

    return {
        "monthly_rain_score": round(month["rainy_days"] / month["days_sampled"], 3),
        "daily_rain_score": round(month["avg_precipitation_hours_per_day"] / HOURS_PER_DAY, 3),
        "daylight_hours_score": round(month["avg_sunshine_hours"] / HOURS_PER_DAY, 3),
        "high_temperature_score": 0 if month["avg_high_c"] >= HIGH_TEMP_THRESHOLD_C else 1,
        "low_temperature_score": 0 if month["avg_low_c"] <= LOW_TEMP_THRESHOLD_C else 1,
        "wind_intensity_score": round(min(wind_intensity_score, 1.0), 3),
    }


def build_monthly_scores(weather_normals: dict, year: int) -> dict:
    cities_out = {}
    for city_id, city in weather_normals["cities"].items():
        cities_out[city_id] = {
            "city": city["city"],
            "country": city["country"],
            "admin_name": city.get("admin_name"),
            "lat": city["lat"],
            "lng": city["lng"],
            "months": {
                month_name: compute_month_scores(month_data)
                for month_name, month_data in city["months"].items()
            },
        }

    return {
        "source": ATTRIBUTION,
        "year": year,
        "generated": date.today().isoformat(),
        "scoring_rules": {
            "monthly_rain_score": "rainy_days / days_sampled",
            "daily_rain_score": "avg_precipitation_hours_per_day / 24",
            "daylight_hours_score": "avg_sunshine_hours / 24",
            "high_temperature_score": f"0 if avg_high_c >= {HIGH_TEMP_THRESHOLD_C} else 1",
            "low_temperature_score": f"0 if avg_low_c <= {LOW_TEMP_THRESHOLD_C} else 1",
            "wind_intensity_score": f"min(avg_max_wind_kmh / {WIND_COMFORT_CEILING_KMH}, 1) -- see Beaufort scale reference in data/README.md",
        },
        "total_cities": len(cities_out),
        "cities": cities_out,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--year", type=int, default=SCORE_YEAR,
        help=f"Year to score (default: {SCORE_YEAR}, the last complete calendar year)",
    )
    args = parser.parse_args()

    weather_normals = load_weather_normals(args.year)
    out = build_monthly_scores(weather_normals, args.year)

    out_path = scores_output_path(args.year)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Scored {out['total_cities']} cities -> {out_path}")


if __name__ == "__main__":
    main()
