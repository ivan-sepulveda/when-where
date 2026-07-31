"""
Loads this project's already-computed data/processed files into memory
once at startup (see main.py) -- this API deliberately does no scoring
pipeline work of its own (no pandas, no re-fetching sources); it reads the
same CSV/JSON outputs the data/scripts/ pipeline already produces and adds
one thing on top: resolving weather against whatever date range a request
asks for (see scoring.py).

Reads straight from ../data/processed and ../data/reference in this
monorepo rather than duplicating any files into backend/ -- one source of
truth, so the API can never drift from what the data pipeline actually
produced.
"""

import json
from pathlib import Path

from .scoring import MONTHS, RAW_WEATHER_METRIC_KEYS, weather_score_from_monthly_metrics

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

OVERARCHING_PATH = DATA_DIR / "processed" / "OVERARCHING_TRIP_SCORE_BY_COUNTRY.json"
TOURIST_CITIES_PATH = DATA_DIR / "reference" / "tourist_cities.json"
MONTHLY_SCORES_PATH = DATA_DIR / "processed" / "monthly_scores_2025_by_city.json"
WEATHER_METRICS_PATH = DATA_DIR / "processed" / "multiple" / "weather_normals_2025_by_city.json"


def load_static_country_scores() -> dict[str, dict]:
    """iso2 -> {country_name, unesco_score, michelin_score, price_score},
    read from build_overarching_trip_scores.py's JSON output. Only the
    three static (date-independent) domain scores are pulled from here --
    that file's own precomputed OVERARCHING_SCORE is a 3-domain average
    and is intentionally NOT used for ranking here, since this API
    recomputes a 4-domain (adding weather) average per request instead."""
    if not OVERARCHING_PATH.exists():
        raise FileNotFoundError(
            f"{OVERARCHING_PATH} not found -- run data/scripts/build_overarching_trip_scores.py first."
        )
    with open(OVERARCHING_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    return {
        iso2: {
            "country_name": country["country_name"],
            "unesco_score": country["unesco_score"],
            "michelin_score": country["michelin_score"],
            "price_score": country["price_score"],
        }
        for iso2, country in payload["countries"].items()
    }


def _pick_primary_capitals() -> dict[str, dict]:
    """iso2 -> most populous 'primary'-tagged capital city entry from
    reference/tourist_cities.json. Same convention as
    build_peak_tourism_interactive_chart.py's load_capital_lat() -- kept
    consistent with that rather than inventing a second way to pick "the"
    representative city for a country. Not every country has a
    'primary'-tagged entry (small territories mostly); those countries
    simply have no weather data available to this API."""
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)["cities"]

    capitals: dict[str, dict] = {}
    for city in cities:
        if city.get("capital") != "primary":
            continue
        iso2 = city["iso2"]
        current = capitals.get(iso2)
        if current is None or (city["population"] or 0) > (current["population"] or 0):
            capitals[iso2] = city
    return capitals


def load_country_capital_names() -> dict[str, str]:
    """iso2 -> display name of the primary capital city used as this
    country's weather proxy (e.g. "JP" -> "Tokyo") -- see
    _pick_primary_capitals(). Weather here is resolved from one
    representative capital, not a national average, so the frontend
    captions weather data with which city it's actually based on rather
    than implying it's country-wide."""
    capitals = _pick_primary_capitals()
    return {iso2: capital["city"] for iso2, capital in capitals.items()}


def load_country_weather_scores() -> dict[str, dict[str, float]]:
    """iso2 -> {month_name: weather_score_0_10}, for every country whose
    primary capital has weather data in monthly_scores_<year>_by_city.json.

    fetch_weather_normals.py is a slow, resumable, still-in-progress pull
    against Open-Meteo's rate-limited historical API (1,770 of a ~3,069
    city target as of this writing -- see data/README.md), so this
    intentionally covers a *subset* of countries today, including some
    large, surprising gaps (e.g. Australia, India, Switzerland) simply
    because their capital hasn't been pulled yet, not because of any data
    quality issue. Countries missing here fall out of the weather average
    entirely in scoring.combine_domain_scores() rather than getting a
    fabricated score -- same missing-data handling PRICE_SCORE already
    gets in build_overarching_trip_scores.py. Re-run this loader (i.e.
    restart the API) after fetch_weather_normals.py pulls more cities to
    pick up newly-available countries -- no code change needed.
    """
    capitals = _pick_primary_capitals()

    if not MONTHLY_SCORES_PATH.exists():
        raise FileNotFoundError(
            f"{MONTHLY_SCORES_PATH} not found -- run data/scripts/compute_monthly_scores.py first."
        )
    with open(MONTHLY_SCORES_PATH, encoding="utf-8") as f:
        monthly_cities = json.load(f)["cities"]

    weather_by_country: dict[str, dict[str, float]] = {}
    for iso2, capital in capitals.items():
        city_entry = monthly_cities.get(str(capital["simplemaps_id"]))
        if city_entry is None:
            continue
        weather_by_country[iso2] = {
            month: weather_score_from_monthly_metrics(city_entry["months"][month]) for month in MONTHS
        }
    return weather_by_country


# Pulled alongside RAW_WEATHER_METRIC_KEYS even though neither is
# averaged the same simple way: rainy_days needs days_sampled (that
# month's real sampled day count, 28-31) to turn into a fraction-of-month
# in scoring.resolve_rainy_days_estimate() -- see that function's
# docstring for why a plain weighted average of the raw count would be
# wrong. Keeping this small and explicit here rather than folding it into
# RAW_WEATHER_METRIC_KEYS, since that constant specifically drives
# resolve_weather_metrics()'s uniform "just average it" loop and these
# two don't fit that shape.
EXTRA_MONTHLY_KEYS = ["rainy_days", "days_sampled"]


def load_country_weather_metrics() -> dict[str, dict[str, dict[str, float]]]:
    """iso2 -> {month_name: {raw metric name: value}}, straight from
    weather_normals_<year>_by_city.json's per-month numbers (avg high/low
    temp, precipitation, sunshine hours -- see scoring.RAW_WEATHER_METRIC_KEYS
    -- plus rainy_days/days_sampled, see EXTRA_MONTHLY_KEYS above). This is
    the *input* to load_country_weather_scores()'s 0-10 score, kept here in
    its original units for display (e.g. DestinationDetail's "Daily
    Sunlight Hours") rather than folded into one abstract number.

    Same primary-capital-per-country resolution and same "missing capital
    data -> country just isn't in the dict" behavior as
    load_country_weather_scores() -- see that function's docstring for why
    coverage is a subset of all countries."""
    capitals = _pick_primary_capitals()

    if not WEATHER_METRICS_PATH.exists():
        raise FileNotFoundError(
            f"{WEATHER_METRICS_PATH} not found -- run data/scripts/multiple/fetch_weather_normals.py first."
        )
    with open(WEATHER_METRICS_PATH, encoding="utf-8") as f:
        weather_cities = json.load(f)["cities"]

    keys_to_pull = RAW_WEATHER_METRIC_KEYS + EXTRA_MONTHLY_KEYS
    metrics_by_country: dict[str, dict[str, dict[str, float]]] = {}
    for iso2, capital in capitals.items():
        city_entry = weather_cities.get(str(capital["simplemaps_id"]))
        if city_entry is None:
            continue
        metrics_by_country[iso2] = {
            month: {key: city_entry["months"][month][key] for key in keys_to_pull}
            for month in MONTHS
            if month in city_entry["months"]
        }
    return metrics_by_country
