"""Pure scoring math for /api/destinations/top10 -- no file I/O, unit-testable without FastAPI.

Two things here exist nowhere in data/scripts/:

- `month_weights()` resolves a date range into per-month weights. Everything in
  data/processed/ is keyed by month name or number, never by a range.
- `weather_score_from_monthly_metrics()` combines compute_monthly_scores.py's six
  raw factors into one 0-10 score. data/README.md leaves them uncombined on
  purpose -- the right weighting depends on the traveler (a hike and a beach trip
  weigh rain differently). This is an equal-weighted default; `interest` is
  already sent by the frontend and is the hook for making it per-profile.

Other notes:

- `combine_domain_scores()` reuses build_overarching_trip_scores.py's rule --
  average whichever domains exist, never pad a missing one with 0 -- plus weather
  as an optional fourth.
- `great_circle_distance_km()` backs the cities/top10 diversity guard. Same
  haversine and Earth radius as data/scripts/distance_calculator.py,
  reimplemented rather than imported because the backend does not reach into
  data/scripts/ (see backend/README.md).
"""

import math
from datetime import date, timedelta

# Mean Earth radius (IUGG). In sync with distance_calculator.py's
# EARTH_RADIUS_KM so both return identical distances.
EARTH_RADIUS_KM = 6371.0088

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# Raw per-month fields from fetch_weather_normals.py's
# weather_normals_<year>_by_city.json (that script's docstring has units and
# sourcing). Here rather than data_loader.py because it is the shape
# resolve_weather_metrics() operates on -- same reasoning as MONTHS.
#
# rainy_days is deliberately EXCLUDED. The other five are daily/monthly rates
# that stay meaningful at any trip length; rainy_days is a ~30-day COUNT, so
# averaging it gives nonsense (a 7-day trip weighted to a 31-day month with 11
# rainy days would report 11). resolve_rainy_days_estimate() handles it instead.
RAW_WEATHER_METRIC_KEYS = [
    "avg_high_c",
    "avg_low_c",
    "total_precipitation_mm",
    "avg_precipitation_hours_per_day",
    "avg_sunshine_hours",
]


def weather_score_from_monthly_metrics(metrics: dict) -> float:
    """0-10, higher = more pleasant. Equal-weighted blend of six 0-1 factors.

    Factors are documented in data/SCORING.md and compute_monthly_scores.py:

        dryness     = 1 - mean(monthly_rain_score, daily_rain_score)
        daylight    = daylight_hours_score            (higher already better)
        temperature = mean(high_temperature_score, low_temperature_score)
        calm        = 1 - wind_intensity_score

        weather_score = mean(dryness, daylight, temperature, calm) * 10
    """
    dryness = 1 - (metrics["monthly_rain_score"] + metrics["daily_rain_score"]) / 2
    daylight = metrics["daylight_hours_score"]
    temperature = (metrics["high_temperature_score"] + metrics["low_temperature_score"]) / 2
    calm = 1 - metrics["wind_intensity_score"]
    return round((dryness + daylight + temperature + calm) / 4 * 10, 2)


def month_weights(start_date: date, end_date: date) -> dict[str, float]:
    """Day-weighted month weights for a trip date range, endpoints inclusive.

    - weight = (trip days in that month) / (total trip days).
      May 28 - Jun 3 (7 days) -> {"may": 4/7, "june": 3/7}.
    - Only the month NAME matters, not the year: weather normals are one
      representative year applied to any year (fetch_weather_normals.py), so
      June 2027 and June 2030 weight identically.
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
    """Weighted average of a country's monthly weather scores against the trip's months.

    None when the country has no weather data (see
    data_loader.load_country_weather_scores) -- callers must read that as
    "unknown", not "bad weather"."""
    if monthly_scores is None:
        return None
    return round(sum(monthly_scores[month] * weight for month, weight in weights.items()), 2)


def resolve_weather_metrics(
    monthly_metrics: dict[str, dict[str, float]] | None, weights: dict[str, float]
) -> dict[str, float] | None:
    """Day-weighted average of a country's RAW monthly weather metrics, for display.

    - Same shape as resolve_weather_score(), but averages the original numbers
      (RAW_WEATHER_METRIC_KEYS: avg high/low temp, precipitation, rainy days,
      sunshine hours) rather than the derived 0-10 score.
    - A 30% July / 70% August trip with sunshine 10 and 8 resolves to 8.6.
    - None when the country has no weather data -- "unknown", not zero.
    """
    if monthly_metrics is None:
        return None
    return {
        key: round(sum(monthly_metrics[month][key] * weight for month, weight in weights.items()), 2)
        for key in RAW_WEATHER_METRIC_KEYS
    }


def resolve_rainy_days_estimate(
    monthly_metrics: dict[str, dict[str, float]] | None, weights: dict[str, float], trip_days: int
) -> float | None:
    """Rainy days expected DURING the trip (0..trip_days), not a blend of monthly counts.

    See RAW_WEATHER_METRIC_KEYS above for why the naive blend is wrong. Steps:

    1. Each spanned month's `rainy_days` becomes a fraction of that month
       (rainy_days / days_sampled -- the actual sampled count, 28-31, not a
       hardcoded calendar assumption).
    2. Those fractions are day-weight-averaged with the same `weights` every
       other resolve_* function uses.
    3. The result is scaled by the trip's own length.

    A 7-day trip at 30% July (5/31 -> 16.1%) and 70% August (10/31 -> 32.3%)
    gives (0.3*0.161 + 0.7*0.323) * 7 ~= 1.82. Present it as a range ("1-2 rainy
    days"), not a single number -- it is an estimate. None when the country has
    no weather data, same "unknown, not zero" rule as the other resolve_*.
    """
    if monthly_metrics is None:
        return None
    weighted_fraction = sum(
        (monthly_metrics[month]["rainy_days"] / monthly_metrics[month]["days_sampled"]) * weight
        for month, weight in weights.items()
    )
    return round(weighted_fraction * trip_days, 2)


def combine_domain_scores(
    unesco_score: float | None,
    michelin_score: float | None,
    price_score: float | None,
    weather_score: float | None,
) -> tuple[float | None, int]:
    """Mean of whichever of the four domain scores exist.

    Same rule as build_overarching_trip_scores.py's OVERARCHING_SCORE, with
    weather as an optional fourth. Returns (None, 0) only if a country has none
    of the four, which should not happen -- UNESCO_SCORE and MICHELIN_SCORE
    cover all 242 countries, with a real 0 where applicable."""
    values = [v for v in (unesco_score, michelin_score, price_score, weather_score) if v is not None]
    if not values:
        return None, 0
    return round(sum(values) / len(values), 2), len(values)


def great_circle_distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine distance between two lat/lng points, in km.

    See this file's docstring for why it is reimplemented rather than imported
    from data/scripts/distance_calculator.py."""
    lat1r, lng1r, lat2r, lng2r = math.radians(lat1), math.radians(lng1), math.radians(lat2), math.radians(lng2)
    dlat = lat2r - lat1r
    dlng = lng2r - lng1r
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlng / 2) ** 2
    return EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))
