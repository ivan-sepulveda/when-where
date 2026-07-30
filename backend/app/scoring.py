"""
Pure scoring logic for the /api/destinations/top10 endpoint -- no file I/O
here (see data_loader.py for that), just the math that turns a date range
plus this project's per-country/per-city data into one ranked list. Kept
separate from main.py so the request-time logic can be unit tested without
spinning up FastAPI.

Two things happen here that don't exist anywhere in data/scripts/ yet:

1. Resolving a (start_date, end_date) range into weights over calendar
   months -- see month_weights(). Everything upstream in data/processed/
   is keyed by month name (weather) or plain month number (peak tourism,
   unused here for now), never by a date range, so this is new logic
   specific to serving a live request.
2. Combining the six raw per-month weather factors from
   compute_monthly_scores.py into a single 0-10 score -- see
   weather_score_from_monthly_metrics(). data/README.md is explicit that
   those six factors are deliberately left uncombined in the pipeline
   itself, since the "right" weighting depends on traveler profile (a
   hiking trip cares about rain very differently than a beach trip). This
   is a simple, equal-weighted default for now -- a real next step is
   letting `interest` (already sent by the frontend, not yet used here)
   change these weights per profile.

combine_domain_scores() reuses the exact "average of whichever domains
are available, never pad missing with 0" rule from
build_overarching_trip_scores.py, extended with weather as a fourth,
optional domain.
"""

from datetime import date, timedelta

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# The raw (non-normalized) per-month fields fetch_weather_normals.py
# writes to weather_normals_<year>_by_city.json -- see that script's
# docstring for units/sourcing. Kept here (rather than in data_loader.py)
# since it's the shape resolve_weather_metrics() operates on, same
# reasoning as MONTHS living here.
RAW_WEATHER_METRIC_KEYS = [
    "avg_high_c",
    "avg_low_c",
    "total_precipitation_mm",
    "avg_precipitation_hours_per_day",
    "rainy_days",
    "avg_sunshine_hours",
]


def weather_score_from_monthly_metrics(metrics: dict) -> float:
    """0-10, higher = more pleasant weather that month. Equal-weighted
    combination of the six 0-1 raw factors documented in
    data/SCORING.md / compute_monthly_scores.py:

        dryness      = 1 - mean(monthly_rain_score, daily_rain_score)
        daylight     = daylight_hours_score            (already higher=better)
        temperature  = mean(high_temperature_score, low_temperature_score)
                       (already 1=pass/0=fail)
        calm         = 1 - wind_intensity_score

        weather_score = mean(dryness, daylight, temperature, calm) * 10
    """
    dryness = 1 - (metrics["monthly_rain_score"] + metrics["daily_rain_score"]) / 2
    daylight = metrics["daylight_hours_score"]
    temperature = (metrics["high_temperature_score"] + metrics["low_temperature_score"]) / 2
    calm = 1 - metrics["wind_intensity_score"]
    return round((dryness + daylight + temperature + calm) / 4 * 10, 2)


def month_weights(start_date: date, end_date: date) -> dict[str, float]:
    """Day-weighted month weights for a trip date range: each calendar
    month gets weight = (trip days falling in that month) / (total trip
    days), inclusive of both endpoints. E.g. May 28 - Jun 3 (7 days) ->
    {"may": 4/7, "june": 3/7}.

    Only the *month name* matters, not the year -- weather normals are a
    single representative year applied to any year's dates (see
    fetch_weather_normals.py), so a trip in June 2027 uses the exact same
    weights as one in June 2030.
    """
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    counts: dict[str, int] = {}
    current = start_date
    while current <= end_date:
        month_name = MONTHS[current.month - 1]
        counts[month_name] = counts.get(month_name, 0) + 1
        current += timedelta(days=1)

    total_days = sum(counts.values())
    return {month: count / total_days for month, count in counts.items()}


def resolve_weather_score(monthly_scores: dict[str, float] | None, weights: dict[str, float]) -> float | None:
    """Weighted average of a country's per-month weather scores against
    the trip's month weights. None if the country has no weather data at
    all (see data_loader.load_country_weather_scores) -- callers should
    treat that as "unknown", not "bad weather"."""
    if monthly_scores is None:
        return None
    return round(sum(monthly_scores[month] * weight for month, weight in weights.items()), 2)


def resolve_weather_metrics(
    monthly_metrics: dict[str, dict[str, float]] | None, weights: dict[str, float]
) -> dict[str, float] | None:
    """Day-weighted average of a country's *raw* monthly weather metrics
    (RAW_WEATHER_METRIC_KEYS -- avg high/low temp, precipitation, rainy
    days, sunshine hours) against the trip's month weights. Same shape as
    resolve_weather_score(), but averages the original numbers for
    display rather than the derived 0-10 score.

    E.g. a trip that's 30% July / 70% August, with avg_sunshine_hours=10
    in July and 8 in August, resolves to 0.3*10 + 0.7*8 = 8.6. None if the
    country has no weather data at all (see
    data_loader.load_country_weather_metrics) -- callers should treat that
    as "unknown", not zero."""
    if monthly_metrics is None:
        return None
    return {
        key: round(sum(monthly_metrics[month][key] * weight for month, weight in weights.items()), 2)
        for key in RAW_WEATHER_METRIC_KEYS
    }


def combine_domain_scores(
    unesco_score: float | None,
    michelin_score: float | None,
    price_score: float | None,
    weather_score: float | None,
) -> tuple[float | None, int]:
    """Mean of whichever of the four domain scores are available -- same
    rule as build_overarching_trip_scores.py's OVERARCHING_SCORE, now with
    weather as a fourth (optional) input. Returns (None, 0) only if a
    country somehow has none of the four, which shouldn't happen in
    practice since UNESCO_SCORE/MICHELIN_SCORE cover all 242 countries
    with a real 0 where applicable."""
    values = [v for v in (unesco_score, michelin_score, price_score, weather_score) if v is not None]
    if not values:
        return None, 0
    return round(sum(values) / len(values), 2), len(values)
