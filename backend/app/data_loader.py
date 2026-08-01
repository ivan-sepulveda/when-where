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

from .scoring import MONTHS, RAW_WEATHER_METRIC_KEYS, great_circle_distance_km, weather_score_from_monthly_metrics

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

OVERARCHING_PATH = DATA_DIR / "processed" / "OVERARCHING_TRIP_SCORE_BY_COUNTRY.json"
TOURIST_CITIES_PATH = DATA_DIR / "reference" / "tourist_cities.json"
TOURIST_CITIES_ENHANCED_PATH = DATA_DIR / "processed" / "tourist_cities_enhanced.json"
MONTHLY_SCORES_PATH = DATA_DIR / "processed" / "monthly_scores_2025_by_city.json"
WEATHER_METRICS_PATH = DATA_DIR / "processed" / "multiple" / "weather_normals_2025_by_city.json"

# How close two cities need to be to count as "the same area" for the
# cities/top10 diversity guard (see load_city_cluster_representatives()
# below) -- matches build_tourist_cities_enhanced.py's SCORE_RADIUS_KM
# (data/SCORING.md), the radius already used to compute each city's own
# unesco_score/michelin_score, rather than inventing a third distance
# constant for this project. Calibrated against the specific clustering
# this was built to fix: Osaka's suburbs sit 9-28km out, Seoul/Gimpo is
# 25km, Brussels/Ixelles is 2.4km, Beijing/Changping is 38km -- all
# comfortably inside 50km, while a genuinely separate trip (e.g.
# Philadelphia from NYC, ~130km) stays outside it.
CITY_CLUSTER_RADIUS_KM = 50


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


def load_static_city_scores() -> dict[str, dict]:
    """simplemaps_id (as str) -> {city, country_name, country_code,
    unesco_score, michelin_score, price_score}, read from
    build_tourist_cities_enhanced.py's JSON output. Same shape and same
    reasoning as load_static_country_scores() just above -- only the
    three static (date-independent) domain scores are pulled from here,
    not that file's own precomputed OVERARCHING_SCORE, since this API
    recomputes a 4-domain (adding weather) average per request instead.

    Keyed by simplemaps_id, not city name -- city names aren't unique in
    this dataset (e.g. two different real cities are both named
    "Kanpur"), simplemaps_id is the only safe join key. Cast to str here
    so it matches monthly_scores_<year>_by_city.json's string keys (see
    load_city_weather_scores()) without a second conversion at the call
    site.

    Loads the full 27MB tourist_cities_enhanced.json once at startup and
    discards everything except the six fields above (unesco_sites,
    michelin_restaurants, airports per-city detail isn't needed for
    ranking) -- this is exactly why cities/top10 exists as a backend
    endpoint instead of the frontend fetching that file directly the way
    it does OVERARCHING_TRIP_SCORE_BY_COUNTRY.json (48KB) for the static
    country case; 27MB is fine to hold in server memory once, not fine
    to ship to a browser per page load."""
    if not TOURIST_CITIES_ENHANCED_PATH.exists():
        raise FileNotFoundError(
            f"{TOURIST_CITIES_ENHANCED_PATH} not found -- run data/scripts/build_tourist_cities_enhanced.py first."
        )
    with open(TOURIST_CITIES_ENHANCED_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    return {
        str(city["simplemaps_id"]): {
            "city": city["city"],
            "country_name": city["country"],
            "country_code": city["iso2"],
            "unesco_score": city["unesco_score"],
            "michelin_score": city["michelin_score"],
            "price_score": city["price_score"],
        }
        for city in payload["cities"]
    }


def load_city_cluster_representatives() -> dict[str, str]:
    """simplemaps_id (str) -> simplemaps_id (str) of the representative
    city for its geographic cluster. Every city maps to something -- a
    city with no other city within CITY_CLUSTER_RADIUS_KM maps to
    itself.

    Exists so /api/destinations/cities/top10 doesn't let one metro area
    fill multiple spots in the top 10 -- without this, 11 of the top 12
    results by static score were Osaka-area suburbs (Osaka itself,
    Higashi-osaka, Toyonaka, Nara, Hirakata, Amagasaki, ...), since
    nearby cities share nearly the same UNESCO/Michelin density that
    feeds their scores. The endpoint only ranks/returns cities that ARE
    their own cluster's representative -- see top_city_destinations().

    Algorithm -- greedy, population-ordered, NOT a true transitive/graph
    clustering:
        1. Sort all cities by population, descending.
        2. Walk down that list. A city becomes its own cluster's
           representative UNLESS it's within CITY_CLUSTER_RADIUS_KM of
           an already-designated representative (which, since we're
           going population-descending, is always at least as populous)
           -- in which case it's absorbed into that representative's
           cluster instead of starting a new one.
    This deliberately avoids the long-chain problem a true transitive
    clustering has (A near B, B near C, but A far from C, yet all three
    end up "the same cluster" purely by chaining) -- every city's
    cluster is anchored to one fixed, most-populous representative
    within range, matching the explicit rule this was built to: "if
    there's a cluster, use the one with the highest population."

    O(n * r) where r is the representative count found so far (not O(n^2)
    -- r stays well under n since most of the world's ~3,069 tourist
    cities aren't clustered) -- verified at ~1s for the full dataset
    (3,069 cities -> 1,967 representatives at 50km), comfortably fine to
    run once at startup rather than needing a spatial index."""
    if not TOURIST_CITIES_PATH.exists():
        raise FileNotFoundError(f"{TOURIST_CITIES_PATH} not found -- run data/scripts/multiple/fetch_tourist_cities.py first.")
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)["cities"]

    cities_by_population = sorted(cities, key=lambda c: c["population"] or 0, reverse=True)

    representatives: list[dict] = []  # [{"id": str, "lat": float, "lng": float}, ...], population-descending
    assignment: dict[str, str] = {}

    for city in cities_by_population:
        city_id = str(city["simplemaps_id"])
        nearby_rep = next(
            (
                rep
                for rep in representatives
                if great_circle_distance_km(city["lat"], city["lng"], rep["lat"], rep["lng"]) <= CITY_CLUSTER_RADIUS_KM
            ),
            None,
        )
        if nearby_rep is not None:
            assignment[city_id] = nearby_rep["id"]
        else:
            representatives.append({"id": city_id, "lat": city["lat"], "lng": city["lng"]})
            assignment[city_id] = city_id

    return assignment


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


def load_city_weather_scores() -> dict[str, dict[str, float]]:
    """simplemaps_id (as str) -> {month_name: weather_score_0_10}, for
    every city with weather data in monthly_scores_<year>_by_city.json.

    Unlike load_country_weather_scores() just above, no capital-city
    proxy step is needed here -- that indirection exists specifically to
    get from a country down to *some* representative city; for city-level
    ranking there's no indirection to do, monthly_scores_<year>_by_city.json
    is already keyed by the exact city being scored. Same coverage
    caveat as the country version still applies though: only 1,770 of
    3,069 cities have weather data as of this writing (see
    fetch_weather_normals.py), so most cities -- including several in the
    current top static-score results -- fall out of the weather average
    entirely in scoring.combine_domain_scores() rather than getting a
    fabricated score."""
    if not MONTHLY_SCORES_PATH.exists():
        raise FileNotFoundError(
            f"{MONTHLY_SCORES_PATH} not found -- run data/scripts/compute_monthly_scores.py first."
        )
    with open(MONTHLY_SCORES_PATH, encoding="utf-8") as f:
        monthly_cities = json.load(f)["cities"]

    return {
        city_id: {month: weather_score_from_monthly_metrics(entry["months"][month]) for month in MONTHS}
        for city_id, entry in monthly_cities.items()
    }


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
