"""
FastAPI app -- the first real "frontend talks to a backend" piece of this
project (see backend/README.md for the full design writeup). Routes that
matter: GET /api/destinations/top10 (country ranking),
GET /api/destinations/cities/top10 (city ranking -- same idea, city
granularity), GET /api/destinations/{country}/weather (raw weather
metrics for one country's DestinationDetail page), and the city pair
GET /api/destinations/cities/{city_id} (+ /weather), which back
CityDetail.tsx the way those country routes back DestinationDetail.tsx.

Data is loaded once at import time (see data_loader.py) and kept in
memory for the life of the process -- every request just does cheap
arithmetic (month-weight resolution + a handful of weighted averages
over ~240 countries or ~3,069 cities), no file I/O or heavy computation
per request. This is deliberate: Render's free tier spins the process
down after ~15 min idle, but *while running*, every request after the
first should be fast. It's also why cities/top10 exists as a backend
route at all rather than the frontend fetching tourist_cities_enhanced.json
directly the way it fetches the small country-level static JSON --
that file is 27MB, fine to hold in server memory once, not fine to ship
to a browser per page load. See load_static_city_scores()'s docstring.

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
    CITY_DETAIL_RADIUS_KM,
    load_city_attractions,
    load_city_cluster_representatives,
    load_city_details,
    load_city_weather_metrics,
    load_city_weather_scores,
    load_country_capital_names,
    load_country_weather_metrics,
    load_country_weather_scores,
    load_static_city_scores,
    load_static_country_scores,
    load_visa_requirements,
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
# (or city) list.
STATIC_SCORES = load_static_country_scores()
WEATHER_SCORES = load_country_weather_scores()
WEATHER_METRICS = load_country_weather_metrics()
CAPITAL_NAMES = load_country_capital_names()
STATIC_CITY_SCORES = load_static_city_scores()
CITY_DETAILS = load_city_details()
# None until data/scripts/multiple/build_city_attractions.py has been run --
# see load_city_attractions()'s docstring for why that's tolerated here when
# every other missing input is fatal.
CITY_ATTRACTIONS = load_city_attractions()
CITY_WEATHER_SCORES = load_city_weather_scores()
CITY_WEATHER_METRICS = load_city_weather_metrics()
CITY_CLUSTER_REPRESENTATIVES = load_city_cluster_representatives()
VISA_REQUIREMENTS = load_visa_requirements()


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


class CityDestinationScore(BaseModel):
    # simplemaps_id, as a string -- the stable unique key for a city in
    # this dataset (city name alone isn't unique, e.g. two different
    # real cities are both named "Kanpur"). This is what the frontend
    # routes on -- /destinations/cities/:cityId, backed by
    # /api/destinations/cities/{city_id} below.
    city_id: str
    # Properly-accented name (e.g. "Ōsaka") and its ASCII-stripped
    # counterpart (e.g. "Osaka") -- per project decision, the frontend
    # should default to displaying city_ascii; city is included for
    # anything that wants the accented version. See
    # data_loader.load_static_city_scores()'s docstring for why this
    # isn't a workaround for an encoding bug (there isn't one).
    city: str
    city_ascii: str
    country_name: str
    country_code: str
    unesco_score: Optional[float]
    michelin_score: Optional[float]
    price_score: Optional[float]
    weather_score: Optional[float]
    scores_averaged: int
    trip_score: float


class TopCityDestinationsResponse(BaseModel):
    # Both None if the request didn't include dates (unlike
    # /api/destinations/top10, where they're required) -- see
    # top_city_destinations()'s docstring for why cities/top10 supports
    # a dateless call at all.
    start_date: Optional[date]
    end_date: Optional[date]
    month_weights: dict[str, float]
    destinations: list[CityDestinationScore]


class NearbyUnescoSite(BaseModel):
    name: str
    category: str  # "Cultural" / "Natural" / "Mixed"
    distance_km: float


class NearbyMichelinRestaurant(BaseModel):
    name: str
    award: str  # "3 Stars" / "2 Stars" / "1 Star" / "Bib Gourmand" / "Selected Restaurants"
    cuisine: str
    distance_km: float


class NearbyPlace(BaseModel):
    name: str
    # Specific label for this one entry, e.g. "Safari Park", "Aquarium",
    # "Botanical Garden or Nature Center" -- narrower than the category it's
    # filed under, since a section groups several real-world kinds.
    kind: str
    # "OpenStreetMap" or "IMLS". Surfaced rather than hidden because the two
    # aren't equivalent in scope (IMLS is US-only but curated and includes
    # nature centers; OSM is worldwide but community-mapped) -- see
    # data/scripts/multiple/build_city_attractions.py.
    source: str
    distance_km: float


class NearbyPlaces(BaseModel):
    # Total within the attractions radius. May exceed len(places), which
    # build_city_attractions.py caps per category.
    count: int
    places: list[NearbyPlace]


class CityDetailResponse(BaseModel):
    """One city's page data -- the counterpart to what
    DestinationDetail.tsx assembles for a country out of several
    country-keyed CSV/JSON files fetched straight from GitHub. Cities
    can't work that way (their source file is 27MB -- see this module's
    docstring), so this endpoint does the same assembly server-side and
    returns it in one response."""

    city_id: str
    city: str
    city_ascii: str
    country_name: str
    country_code: str
    # State/province/prefecture (e.g. "Tōkyō"). Null for the 18 cities in
    # this dataset that have no admin_name -- mostly city-states and small
    # territories, where there's no meaningful subdivision to name.
    admin_name: Optional[str]
    lat: float
    lng: float
    population: Optional[int]
    # Echoed back so the frontend labels its own headings from the
    # response ("...within 100km") instead of hardcoding a radius that
    # could drift from what the backend actually filtered on.
    radius_km: int
    # Full count within radius_km. May be larger than len(michelin_restaurants)
    # -- see data_loader.CITY_DETAIL_MICHELIN_LIMIT.
    unesco_site_count: int
    unesco_sites: list[NearbyUnescoSite]
    michelin_count: int
    michelin_restaurants: list[NearbyMichelinRestaurant]
    # The same three static domain scores /api/destinations/cities/top10
    # ranks on, for this one city. Weather (the fourth domain) isn't here
    # -- it depends on a date range, so it lives on
    # /api/destinations/cities/{city_id}/weather instead.
    unesco_score: Optional[float]
    michelin_score: Optional[float]
    price_score: Optional[float]
    # ALL FOUR of the fields below are null together, and only when
    # city_attractions.json hasn't been generated in this checkout (see
    # data_loader.load_city_attractions). The frontend hides those sections
    # entirely in that case. A field that's present but empty
    # (count=0, places=[]) means the opposite: the data IS loaded and there's
    # genuinely nothing within the radius -- worth saying out loud on the
    # page, since "no botanical garden within 100km" is real information.
    attractions_radius_km: Optional[float]
    zoos_and_aquariums: Optional[NearbyPlaces]
    botanical_gardens: Optional[NearbyPlaces]
    # US-only (IMLS). Deliberately NOT the whole art museum story: the
    # frontend merges this with the worldwide largest-art-museums list it
    # already fetches, which covers non-US cities well and US cities badly.
    local_art_museums: Optional[NearbyPlaces]


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


class CityWeatherResponse(BaseModel):
    city_id: str
    city_ascii: str
    start_date: date
    end_date: date
    month_weights: dict[str, float]
    # Null (not a 404) for a city this project has no weather normals for
    # yet -- ~1,770 of 3,069 cities are covered so far, see
    # data_loader.load_city_weather_metrics(). Same "unknown, not bad"
    # convention as the country route below.
    weather: Optional[WeatherDetail]


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


class VisaRequirementsResponse(BaseModel):
    departure_country: str
    # The departure country's own label as it appears in
    # visa_requirements.json (e.g. "Mexico") -- null (alongside an empty
    # requirements dict) if `departure_country` isn't a code this project
    # has visa data for, same "unknown, not a 404" convention
    # /api/destinations/{country}/weather uses for missing weather.
    departure_country_name: Optional[str]
    # destination iso2 -> requirement string (e.g. "VISA-FREE 90", "EVISA",
    # "VISA REQUIRED"), passed through verbatim -- keyed by iso2 (not
    # visa_requirements.json's own name label) so the frontend can join
    # this against every other country-keyed response by code, see
    # data_loader.load_visa_requirements()'s docstring.
    requirements: dict[str, str]


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
        "cities_loaded": len(STATIC_CITY_SCORES),
        "cities_with_weather": len(CITY_WEATHER_SCORES),
        "cities_with_weather_metrics": len(CITY_WEATHER_METRICS),
        # 0 vs null: 0 means the attractions dataset is loaded but no city has
        # anything in it (shouldn't happen), null means it hasn't been
        # generated in this checkout -- see load_city_attractions().
        "cities_with_attractions": len(CITY_ATTRACTIONS["cities"]) if CITY_ATTRACTIONS else None,
        "city_clusters": len(set(CITY_CLUSTER_REPRESENTATIVES.values())),
        "countries_with_visa_requirements": len(VISA_REQUIREMENTS),
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


@app.get("/api/destinations/cities/top10", response_model=TopCityDestinationsResponse)
def top_city_destinations(
    start_date: Optional[date] = Query(None, description="Trip start date, YYYY-MM-DD. Omit for a date-less (no weather) ranking."),
    end_date: Optional[date] = Query(None, description="Trip end date, YYYY-MM-DD. Omit for a date-less (no weather) ranking."),
):
    """City-level equivalent of /api/destinations/top10 -- same
    combine_domain_scores() math, same "average of whichever domains are
    available" rule, just run over ~3,069 cities (STATIC_CITY_SCORES)
    instead of ~240 countries.

    Unlike the country endpoint, start_date/end_date are OPTIONAL here
    (both required if either is given). The country version doesn't need
    that: with no dates, the frontend fetches
    OVERARCHING_TRIP_SCORE_BY_COUNTRY.json (48KB) directly from GitHub
    and sorts client-side, skipping this API entirely. That same static
    path isn't viable for cities -- tourist_cities_enhanced.json is 27MB
    -- so this one endpoint has to serve BOTH the static and date-aware
    cases; the static case just runs combine_domain_scores() with
    weather_score=None for every city, same "average of 3, not 4"
    behavior /api/destinations/top10 already has for any country missing
    weather data.

    Diversity guard: only cities that ARE their own geographic cluster's
    representative (CITY_CLUSTER_REPRESENTATIVES[city_id] == city_id --
    see data_loader.load_city_cluster_representatives()) are scored and
    returned at all. Without this, the top 10 was dominated by single
    metro areas -- 11 of the top 12 by static score were Osaka-area
    suburbs sharing nearly the same nearby UNESCO/Michelin density.
    Non-representative cities (e.g. Higashi-osaka, absorbed into Osaka)
    simply never appear in this endpoint's results; the representative's
    OWN score is used for ranking, not borrowed from whichever cluster
    member scored highest, so a result never shows a number that isn't
    genuinely that city's own."""
    if (start_date is None) != (end_date is None):
        raise HTTPException(status_code=400, detail="start_date and end_date must be provided together, or not at all")
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    weights = month_weights(start_date, end_date) if start_date is not None and end_date is not None else {}

    scored: list[CityDestinationScore] = []
    for city_id, base in STATIC_CITY_SCORES.items():
        if CITY_CLUSTER_REPRESENTATIVES.get(city_id) != city_id:
            continue  # absorbed into a more-populous nearby city's cluster -- see docstring above
        weather_score = resolve_weather_score(CITY_WEATHER_SCORES.get(city_id), weights) if weights else None
        trip_score, scores_averaged = combine_domain_scores(
            base["unesco_score"], base["michelin_score"], base["price_score"], weather_score
        )
        if trip_score is None:
            continue  # shouldn't happen -- see combine_domain_scores' docstring
        scored.append(
            CityDestinationScore(
                city_id=city_id,
                city=base["city"],
                city_ascii=base["city_ascii"],
                country_name=base["country_name"],
                country_code=base["country_code"],
                unesco_score=base["unesco_score"],
                michelin_score=base["michelin_score"],
                price_score=base["price_score"],
                weather_score=weather_score,
                scores_averaged=scores_averaged,
                trip_score=trip_score,
            )
        )

    scored.sort(key=lambda d: d.trip_score, reverse=True)

    return TopCityDestinationsResponse(
        start_date=start_date,
        end_date=end_date,
        month_weights=weights,
        destinations=scored[:10],
    )


def city_attractions(city_id: str):
    """Returns a lookup for one city's attraction categories:
    `attractions("zoo_aquarium")` -> NearbyPlaces, or None if the dataset
    isn't loaded at all.

    The null-vs-empty distinction is the whole point of this helper, so it
    lives in one place rather than being repeated per category:
      * dataset absent  -> None for every category ("we haven't looked").
      * dataset present, city has no entry for this category -> an EMPTY
        NearbyPlaces ("we looked, there's nothing within the radius").
    A city can be missing from the dataset's `cities` map entirely and still
    get the empty form -- build_city_attractions.py omits cities with nothing
    in any category, which means the same thing as an empty category."""
    if CITY_ATTRACTIONS is None:
        return lambda category: None

    by_category = CITY_ATTRACTIONS["cities"].get(city_id, {})

    def lookup(category: str) -> NearbyPlaces:
        entry = by_category.get(category)
        if entry is None:
            return NearbyPlaces(count=0, places=[])
        return NearbyPlaces(
            count=entry["count"], places=[NearbyPlace(**place) for place in entry["places"]]
        )

    return lookup


@app.get("/api/destinations/cities/{city_id}", response_model=CityDetailResponse)
def city_destination_detail(city_id: str):
    """Everything CityDetail.tsx renders for one city: where it is, the
    UNESCO World Heritage Sites and Michelin Guide restaurants within
    CITY_DETAIL_RADIUS_KM (100km) named individually, and its three
    static domain scores. Weather is a separate route (it needs a date
    range); art museums aren't here at all -- that dataset is small and
    country-keyed, so the frontend already fetches it directly from
    GitHub the same way DestinationDetail does.

    `city_id` is a simplemaps_id as a string, exactly as
    /api/destinations/cities/top10 returns it. Unlike the "unknown, not a
    404" convention the weather/visa routes use for *missing data about a
    valid place*, an unrecognized city_id genuinely is a 404 here: it
    isn't a city this project knows about at all, so there's no partial
    answer to give.

    Declared after cities/top10 so that literal path keeps matching first
    -- FastAPI resolves routes in declaration order, and "top10" would
    otherwise be swallowed by {city_id}."""
    detail = CITY_DETAILS.get(city_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"No city with id {city_id!r}")

    scores = STATIC_CITY_SCORES.get(city_id, {})
    attractions = city_attractions(city_id)

    return CityDetailResponse(
        city_id=city_id,
        city=detail["city"],
        city_ascii=detail["city_ascii"],
        country_name=detail["country_name"],
        country_code=detail["country_code"],
        admin_name=detail["admin_name"],
        lat=detail["lat"],
        lng=detail["lng"],
        population=detail["population"],
        radius_km=CITY_DETAIL_RADIUS_KM,
        unesco_site_count=detail["unesco_site_count"],
        unesco_sites=[NearbyUnescoSite(**site) for site in detail["unesco_sites"]],
        michelin_count=detail["michelin_count"],
        michelin_restaurants=[
            NearbyMichelinRestaurant(**restaurant) for restaurant in detail["michelin_restaurants"]
        ],
        unesco_score=scores.get("unesco_score"),
        michelin_score=scores.get("michelin_score"),
        price_score=scores.get("price_score"),
        attractions_radius_km=CITY_ATTRACTIONS["radius_km"] if CITY_ATTRACTIONS else None,
        zoos_and_aquariums=attractions("zoo_aquarium"),
        botanical_gardens=attractions("botanical_garden"),
        local_art_museums=attractions("art_museum"),
    )


@app.get("/api/destinations/cities/{city_id}/weather", response_model=CityWeatherResponse)
def city_weather(
    city_id: str,
    start_date: date = Query(..., description="Trip start date, YYYY-MM-DD"),
    end_date: date = Query(..., description="Trip end date, YYYY-MM-DD"),
):
    """City-level equivalent of /api/destinations/{country}/weather --
    same day-weighted averaging and same trip-length-scaled rainy-day
    estimate, just read from this city's own normals instead of its
    country's primary capital's. No capital_city field in the response,
    for that reason: there's no proxy city to disclose, the numbers are
    the city's own.

    404s on an unknown city_id (same reasoning as
    city_destination_detail() above), but returns `weather: null` for a
    known city whose normals simply haven't been pulled yet."""
    if city_id not in CITY_DETAILS:
        raise HTTPException(status_code=404, detail=f"No city with id {city_id!r}")
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    weights = month_weights(start_date, end_date)
    trip_days = (end_date - start_date).days + 1
    city_metrics = CITY_WEATHER_METRICS.get(city_id)
    metrics = resolve_weather_metrics(city_metrics, weights)
    rainy_days_estimate = resolve_rainy_days_estimate(city_metrics, weights, trip_days)

    weather = WeatherDetail(**metrics, rainy_days=rainy_days_estimate) if metrics is not None else None

    return CityWeatherResponse(
        city_id=city_id,
        city_ascii=CITY_DETAILS[city_id]["city_ascii"],
        start_date=start_date,
        end_date=end_date,
        month_weights=weights,
        weather=weather,
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


@app.get("/api/destinations/{departure_country}/visa-requirements", response_model=VisaRequirementsResponse)
def visa_requirements(departure_country: str):
    """All of a departure country's visa requirements against every other
    country, e.g. `/api/destinations/MX/visa-requirements` returns every
    entry visa_requirements.json has filed under "Mexico" (its own key),
    keyed by destination iso2 rather than the file's own name labels --
    see data_loader.load_visa_requirements() for why (short version: this
    file's destination names don't string-match this project's own
    country_name values elsewhere, but both resolve to the same iso2).
    `departure_country` is an ISO 3166-1 alpha-2 code, case-insensitive.
    `requirements` is an empty dict (not a 404) for a valid-looking code
    this project simply has no visa data for -- same "unknown, not bad"
    convention as /api/destinations/{country}/weather's null weather."""
    iso2 = departure_country.upper()
    entry = VISA_REQUIREMENTS.get(iso2)

    return VisaRequirementsResponse(
        departure_country=iso2,
        departure_country_name=entry["country_name"] if entry is not None else None,
        requirements=entry["requirements"] if entry is not None else {},
    )
