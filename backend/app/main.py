"""
FastAPI app -- the first real "frontend talks to a backend" piece of this
project (see backend/README.md for the full design writeup). Two routes
that matter: GET /api/destinations/top10 (ranking) and
GET /api/destinations/{country}/weather (raw weather metrics for one
country's DestinationDetail page).

Data is loaded once at import time (see data_loader.py) and kept in
memory for the life of the process -- every request just does cheap
arithmetic (month-weight resolution + a handful of weighted averages
over ~240 countries), no file I/O or heavy computation per request. This
is deliberate: Render's free tier spins the process down after ~15 min
idle, but *while running*, every request after the first should be fast.

Usage (local dev):
    uvicorn app.main:app --reload --port 8000
"""

import os
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .data_loader import (
    load_country_capital_names,
    load_country_weather_metrics,
    load_country_weather_scores,
    load_static_country_scores,
)
from .scoring import (
    combine_domain_scores,
    month_weights,
    resolve_rainy_days_estimate,
    resolve_weather_metrics,
    resolve_weather_score,
)

app = FastAPI(
    title="when-where API",
    version="0.1.0",
    description="Ranks countries as trip destinations for a given date range. See backend/README.md.",
)

# Origins allowed to call this API from a browser. Overridable via the
# ALLOWED_ORIGINS env var (comma-separated) for previewing a branch
# deploy or a different domain without a code change.
DEFAULT_ALLOWED_ORIGINS = [
    "https://travel.iesepulveda.com",
    "http://localhost:5173",  # vite dev
    "http://localhost:4173",  # vite preview
]
allowed_origins_env = os.environ.get("ALLOWED_ORIGINS")
ALLOWED_ORIGINS = (
    [origin.strip() for origin in allowed_origins_env.split(",") if origin.strip()]
    if allowed_origins_env
    else DEFAULT_ALLOWED_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Loaded once at startup -- see data_loader.py's docstrings for what each
# of these covers and why weather data is a subset of the full country
# list.
STATIC_SCORES = load_static_country_scores()
WEATHER_SCORES = load_country_weather_scores()
WEATHER_METRICS = load_country_weather_metrics()
CAPITAL_NAMES = load_country_capital_names()


class DestinationScore(BaseModel):
    country: str
    country_name: str
    unesco_score: Optional[float]
    michelin_score: Optional[float]
    price_score: Optional[float]
    weather_score: Optional[float]
    scores_averaged: int
    trip_score: float


class TopDestinationsResponse(BaseModel):
    start_date: date
    end_date: date
    departure_country: Optional[str]
    month_weights: dict[str, float]
    destinations: list[DestinationScore]


class WeatherDetail(BaseModel):
    avg_high_c: float
    avg_low_c: float
    total_precipitation_mm: float
    avg_precipitation_hours_per_day: float
    # Estimated rainy days DURING the trip itself (0..trip length), not a
    # weighted average of each spanned month's own ~30-day count -- see
    # scoring.resolve_rainy_days_estimate(). An estimate, not an integer
    # count -- the frontend presents this as a range (e.g. "1-2 days").
    rainy_days: float
    avg_sunshine_hours: float


class CountryWeatherResponse(BaseModel):
    country: str
    start_date: date
    end_date: date
    month_weights: dict[str, float]
    weather: Optional[WeatherDetail]
    # The primary capital city this weather is actually resolved from
    # (see data_loader.load_country_capital_names) -- e.g. "Tokyo" for
    # Japan. Null alongside weather when there's no data at all.
    capital_city: Optional[str]


@app.get("/health")
def health():
    """Render hits this (or `/`) for its health check; also handy for
    confirming how many countries currently have weather data without
    reading server logs."""
    return {
        "status": "ok",
        "countries_loaded": len(STATIC_SCORES),
        "countries_with_weather": len(WEATHER_SCORES),
        "countries_with_weather_metrics": len(WEATHER_METRICS),
    }


@app.get("/api/destinations/top10", response_model=TopDestinationsResponse)
def top_destinations(
    start_date: date = Query(..., description="Trip start date, YYYY-MM-DD"),
    end_date: date = Query(..., description="Trip end date, YYYY-MM-DD"),
    departure_country: Optional[str] = Query(
        None,
        description=(
            "ISO2 departure country. Accepted and echoed back, but NOT yet "
            "used in scoring -- reserved for a future distance/flight-time "
            "score. See backend/README.md."
        ),
    ),
):
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    weights = month_weights(start_date, end_date)

    scored: list[DestinationScore] = []
    for iso2, base in STATIC_SCORES.items():
        weather_score = resolve_weather_score(WEATHER_SCORES.get(iso2), weights)
        trip_score, scores_averaged = combine_domain_scores(
            base["unesco_score"], base["michelin_score"], base["price_score"], weather_score
        )
        if trip_score is None:
            continue  # shouldn't happen -- see combine_domain_scores' docstring
        scored.append(
            DestinationScore(
                country=iso2,
                country_name=base["country_name"],
                unesco_score=base["unesco_score"],
                michelin_score=base["michelin_score"],
                price_score=base["price_score"],
                weather_score=weather_score,
                scores_averaged=scores_averaged,
                trip_score=trip_score,
            )
        )

    scored.sort(key=lambda d: d.trip_score, reverse=True)

    return TopDestinationsResponse(
        start_date=start_date,
        end_date=end_date,
        departure_country=departure_country,
        month_weights=weights,
        destinations=scored[:10],
    )


@app.get("/api/destinations/{country}/weather", response_model=CountryWeatherResponse)
def country_weather(
    country: str,
    start_date: date = Query(..., description="Trip start date, YYYY-MM-DD"),
    end_date: date = Query(..., description="Trip end date, YYYY-MM-DD"),
):
    """Day-weighted average of a single country's raw weather metrics
    (avg high/low temp, precipitation, sunshine hours) over a trip's date
    range, plus a trip-length-scaled rainy-day estimate (see
    scoring.resolve_rainy_days_estimate -- NOT a plain weighted average
    of each month's own day count, which would make a short trip show
    more "rainy days" than it actually has) -- for display
    (DestinationDetail's "Daily Sunlight Hours" etc.), not scoring.
    `country` is an ISO 3166-1 alpha-2 code, case-insensitive. `weather`
    is null (not a 404) for a valid-looking code this project simply has
    no weather data for yet -- same "unknown, not bad" convention as
    /api/destinations/top10's weather_score."""
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    iso2 = country.upper()
    weights = month_weights(start_date, end_date)
    trip_days = (end_date - start_date).days + 1
    country_metrics = WEATHER_METRICS.get(iso2)
    metrics = resolve_weather_metrics(country_metrics, weights)
    rainy_days_estimate = resolve_rainy_days_estimate(country_metrics, weights, trip_days)

    weather = WeatherDetail(**metrics, rainy_days=rainy_days_estimate) if metrics is not None else None

    return CountryWeatherResponse(
        country=iso2,
        start_date=start_date,
        end_date=end_date,
        month_weights=weights,
        weather=weather,
        capital_city=CAPITAL_NAMES.get(iso2),
    )
