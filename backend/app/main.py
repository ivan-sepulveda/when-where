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
    TRAVELER_ENTROPY_REGION_PATH,
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
    load_traveler_entropy,
    load_m49_regions,
    load_traveler_tags,
    load_travelers,
    load_trip_city_matches,
    load_visa_requirements,
    resolve_travelers_path,
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
# Also None until its data scripts have been run -- see load_travelers().
TRAVELERS = load_travelers()
# None until compute_traveler_entropy.py has been run. Kept separate from
# TRAVELERS rather than merged into travelers_anon.json, because the entropy
# is DERIVED from that file -- folding it back in would make a build step
# read its own output.
TRAVELER_ENTROPY = load_traveler_entropy()
# The same measure over a coarser unit: UN M49 detailed region instead of
# destination airport. Loaded separately, never merged -- the two are on
# different scales (K = 106 observed airports vs a fixed K = 22 regions),
# so averaging or comparing them across units would be meaningless.
#
# It also covers far more travelers: only the hand-authored itineraries
# record an airport, but every trip records a destination country, so this
# one is defined for all 206 rather than 82.
TRAVELER_ENTROPY_REGION = load_traveler_entropy(TRAVELER_ENTROPY_REGION_PATH)
# Also None until compute_traveler_tags.py has been run, and kept separate
# from TRAVELERS for the same reason as the entropy above: it is DERIVED
# from travelers_anon.json.
TRAVELER_TAGS = load_traveler_tags()
# The travelers who are real, named people rather than a fictional persona
# or an anonymized Kaggle row: Anthony Bourdain, Gordon Ramsay and Conan
# O'Brien (their shows' real episodes resolved onto real routes -- see
# chef_trips.py) and Eduardo Gomez (Ivan's own hand-kept flight log -- see
# build_gomez_trips.py). Hardcoded rather than derived from `synthetic` or
# `persona_match`: both are True/"authored" for the 82 fictional
# hand-authored characters too, so nothing already in the data separates "a
# real name" from "an authored persona" -- this set is the only place that
# distinction is recorded. Adding a fifth real traveler is one more id here.
REAL_PERSON_TRAVELER_IDS = frozenset({
    "anthony-bourdain",
    "gordon-ramsay",
    "conan-o-brien",
    "eduardo-gomez",
})
# None until match_trip_cities.py has been run. Resolves a trip's
# destination to a city in tourist_cities_enhanced.json so the trip can
# carry that city's UNESCO/Michelin scores -- the name matching itself is
# pipeline work and deliberately does NOT happen here (see
# backend/README.md). Weather is not in that file: it depends on each
# trip's own dates, which is the one thing this API does resolve per
# request.
TRIP_CITY_MATCHES = load_trip_city_matches()
# None until build_m49_regions.py has been run. Joined onto each trip at
# request time rather than baked into the trip data, because it's a
# property of the destination country, not of the trip -- and the M49
# standard is refreshed on its own schedule.
M49_REGIONS = load_m49_regions()
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


class TravelerTrip(BaseModel):
    """One trip from the traveler dataset. Every cost/date/duration is
    carried BOTH parsed and raw on purpose -- see build_travelers.py: the
    parsed value is for future scoring, the raw string is what the UI shows,
    so a value in an unexpected format or currency degrades to "exactly what
    the source said" instead of a confidently wrong number."""

    trip_id: Optional[str]
    # The source's single free-text destination string, split by hand into a
    # city and a sovereign country -- see
    # data/scripts/multiple/build_trips_enhanced.py, which resolves
    # "Sydney, Aus", "Tokyo" and "Honolulu, Hawaii" through a written table
    # rather than by splitting on a comma.
    destination_raw: str
    # Null only when destination_kind is "country" (the source named no city).
    destination_city: Optional[str]
    destination_country: str
    # ISO 3166-1 alpha-2 -- the join key every other dataset in this project
    # is keyed by (weather, visas, UNESCO, Michelin, prices), which is what
    # eventually makes "how good would this trip have been" answerable
    # without a name match.
    destination_country_code: str
    # "city", "region" (an island/state/province used as a destination, e.g.
    # Bali or Hawaii -- kept in destination_city but flagged so a later
    # city-database join knows not to expect a hit), or "country".
    destination_kind: str
    start_date: Optional[str]  # ISO, or null when the source value didn't parse
    start_date_raw: Optional[str]
    end_date: Optional[str]
    end_date_raw: Optional[str]
    duration_days: Optional[int]
    duration_raw: Optional[str]
    accommodation_type: Optional[str]
    accommodation_cost: Optional[float]
    accommodation_cost_raw: Optional[str]
    transportation_type: Optional[str]
    transportation_cost: Optional[float]
    transportation_cost_raw: Optional[str]
    # True for hand-authored trips (data/scripts/multiple/build_synthetic_trips.py),
    # false for the Kaggle rows. The three fields below are only set on the
    # former: their itineraries are built on real airline routes, verified
    # against US DOT T-100 data, so the carrier and airport codes are worth
    # carrying. Defaulted so an older travelers.json without them still loads.
    synthetic: bool = False
    carrier_name: Optional[str] = None
    origin_airport: Optional[str] = None
    destination_airport: Optional[str] = None
    # True for a leg that's part of a longer journey but wasn't its point --
    # Atlanta and Paris on a Houston-to-Lisbon trip, say (see
    # data/scripts/multiple/chef_traveler.py). Only a hand-kept log can know
    # this, so it's always False elsewhere. Defaulted for the same reason
    # `synthetic` is: an older travelers.json without the field still loads.
    # The row is still served here in full -- this flags it for a consumer
    # (the Trips list, the airline/region charts) to exclude from AGGREGATES,
    # it does not remove it from the response.
    layover: bool = False
    # This trip's DESTINATION CITY's scores, joined on at request time from
    # match_trip_cities.py's output plus the city data this API already
    # loads. All three are Optional and null is a real, common state, not
    # an error:
    #   * unesco_score / michelin_score are null when the destination has
    #     no city record at all (~23 destinations -- Punta Cana, Montego
    #     Bay, Sarasota and other places below tourist_cities.json's
    #     population cutoff), or when the trip records no city.
    #   * weather_score is null for those AND for a matched city with no
    #     weather normals (only 1,770 of 3,069 cities have them), and for a
    #     trip with no parseable start date.
    # A null must never be rendered as 0: a UNESCO score of 0.0 is a real
    # value meaning "no World Heritage site within the 50km scoring radius"
    # (true of 73 of the 138 cities these trips visit, Tokyo included).
    unesco_score: Optional[float] = None
    michelin_score: Optional[float] = None
    # Date-dependent, so unlike the other two it is computed here rather
    # than looked up: the city's per-month 0-10 weather scores, averaged
    # against this trip's own dates (see scoring.month_weights).
    weather_score: Optional[float] = None
    # UN M49 geography for destination_country_code, joined on at request
    # time (see data_loader.load_m49_regions). Null when m49_regions.json
    # hasn't been built here, or when the destination country isn't in it --
    # the charts drop those trips from their denominator rather than
    # inventing an "Unknown" region, same convention as a trip with no
    # carrier.
    destination_region: Optional[str] = None
    # M49's INTERMEDIATE region where the country has one, else its
    # sub-region -- 22 values, which is the tier that keeps Central America,
    # the Caribbean and South America apart instead of merging them into
    # "Latin America and the Caribbean".
    destination_subregion: Optional[str] = None


class TravelerTag(BaseModel):
    """One computed label on a traveler -- see
    data/scripts/multiple/compute_traveler_tags.py.

    A tag is a fact about the trips AS RECORDED, never something the
    itinerary's author declared. Two travelers written as United loyalists
    fly routes United doesn't serve and so aren't tagged; that disagreement
    is the point of computing tags rather than storing them.

    `share`, `trips` and `denominator` ride along with every tag so the UI can
    show the arithmetic behind it. `denominator` is NOT the traveler's
    trip_count: for airline_loyalist it counts only trips that record a
    carrier at all (124 of 206 travelers record none), matching the
    "Airlines flown" chart exactly."""

    # Stable machine id, e.g. "airline-loyalist:delta-air-lines-inc" -- built
    # from the full legal carrier name, so two airlines that shorten to the
    # same word can't collide.
    tag_id: str
    # Which rule produced it, e.g. "airline_loyalist". The frontend groups and
    # styles by this, not by parsing the label.
    kind: str
    # What gets drawn on the chip, e.g. "Delta Loyalist".
    label: str
    # Rule-specific evidence. All optional because a future rule needn't
    # have any of it -- a tag always has an id, kind and label, and nothing
    # else is guaranteed.
    #
    # The ONE airline this tag is about, or null when it isn't about one:
    # "Multi Hub" leaves this null deliberately rather than naming the first
    # of its airlines, so nothing downstream can mistake it for a
    # single-airline tag.
    carrier_name: Optional[str] = None
    # Every airline the chip draws a dot for, as full legal names -- one
    # entry for a loyalist or single-airline hub tag, several for Multi Hub.
    # A list on every kind so the component has one code path.
    carrier_names: list[str] = []
    # The same airlines in their short form ("United", "American"), for
    # wording a sentence about them without re-shortening the legal names.
    airlines: Optional[list[str]] = None
    # airline_loyalist: how much of their flying is on `carrier_name`, out of
    # how many carrier-recorded trips. NOT out of trip_count.
    share: Optional[float] = None
    trips: Optional[int] = None
    denominator: Optional[int] = None
    # airline_hub / multi_hub: the home city that earned the tag, and the hub
    # airports in it. The city is the unit -- every New Yorker is Multi Hub
    # whether they fly EWR, JFK or LGA -- so the airports are context, not
    # the thing matched on.
    hub_city: Optional[str] = None
    hub_airports: Optional[list[str]] = None


class TravelerSummary(BaseModel):
    """A traveler without their trips -- what /rec-sys renders as a card.
    The trips themselves are only sent by the detail route, so the grid stays
    a small response no matter how many trips the dataset grows to."""

    traveler_id: str
    name: str
    nationality: Optional[str]
    # INFERRED, never stated by the source: their nationality's country, and
    # the first plausible home city in it that they didn't visit on any trip
    # (an Australian who flew to Sydney three times gets Melbourne). See
    # data/scripts/multiple/build_travelers.py's infer_base(). Null only for a
    # nationality that script has no city list for.
    base_city: Optional[str] = None
    base_country: Optional[str] = None
    base_country_code: Optional[str] = None
    # How that city was picked: "primary" (the country's default),
    # "avoided_visited" (they'd been to the ones ahead of it),
    # "visited_all_candidates", or "unmapped". Carried so the guess is
    # inspectable rather than reading as fact.
    base_inference: Optional[str] = None
    gender: Optional[str]
    age: Optional[int]
    # [youngest, oldest] across this traveler's trips -- age is recorded
    # per-trip in the source, so it moves for anyone who travelled across
    # years. Null when no trip of theirs has an age at all.
    age_range: Optional[list[int]]
    # True when every one of this traveler's trips is hand-authored -- see
    # TravelerTrip.synthetic. Their name is their own rather than an author
    # persona (persona_match: "authored").
    synthetic: bool = False
    # True for the handful of travelers who are a real, named person --
    # Anthony Bourdain, Gordon Ramsay, Conan O'Brien, Eduardo Gomez -- rather
    # than a fictional persona (hand-authored or anonymized) or a raw Kaggle
    # row. See REAL_PERSON_TRAVELER_IDS: NOT derivable from `synthetic` or
    # `persona_match` above, since both are also true/"authored" for the 82
    # fictional hand-authored characters.
    real_person: bool = False
    trip_count: int
    destinations: list[str]
    # Only present when travelers_anon.json is what's being served (see
    # data_loader.resolve_travelers_path), and never rendered -- this is
    # provenance, not page content.
    # "nationality" (author matches the traveler's nationality and gender
    # exactly), "region" (same broad literary region -- used where a
    # nationality has too few deceased authors on record), or "unmapped" (name
    # left as the source had it). Null when serving raw names. Carried through
    # so an imperfect match is inspectable rather than invisible.
    persona_match: Optional[str] = None
    # Computed labels (see TravelerTag). ALWAYS a list, never null: an empty
    # list means "the rules ran and none matched", which is a real answer, and
    # the same empty list is what a checkout with no traveler_tags.json sends.
    # Those two cases are deliberately not distinguished here -- unlike
    # entropy, a tag has nothing useful to say about its own absence, and the
    # server log already reports the missing file.
    tags: list[TravelerTag] = []
    # THE SAME NUMBER the detail route's `region_entropy.normalized` carries
    # (see DestinationEntropy) -- how spread out this traveler's trips are
    # across UN M49 detailed regions, over a FIXED denominator of all 22.
    # Duplicated onto the summary so /rec-sys can filter the grid on it
    # without fetching all 2000-odd trips; computed from the same row, so the
    # card and the traveler's own page can never disagree.
    #
    # Null means "not computed" -- compute_traveler_entropy.py --by region
    # hasn't been run here, or this traveler postdates the run. NOT zero:
    # zero is a real value meaning every trip went to the same region, which
    # 154 of the current travelers genuinely do.
    region_entropy_normalized: Optional[float] = None


class DestinationEntropy(BaseModel):
    """How spread out one traveler's trips are across destinations. See
    data/scripts/multiple/compute_traveler_entropy.py, and data/README.md
    for the derivation.

    Every numeric field here is Optional and that is load-bearing, not
    defensive: `entropy` is null for the 124 travelers whose trips record no
    destination airport (the Kaggle-sourced ones). Null is NOT zero -- zero
    would claim "never varies their destination" where the truth is "the
    source doesn't say" -- so the page must render the two differently."""

    # -sum(p ln p) in nats. 0.0 is a real value (every trip to one airport);
    # null means unknown.
    entropy: Optional[float] = None
    # entropy / ln(global_distinct_destinations). The canonical normalisation.
    # Comparable between travelers, but nobody in the current data exceeds
    # ~0.65, since that would need visiting most of the 106 airports.
    normalized: Optional[float] = None
    # How many distinct destinations this traveler has, and how many of their
    # trips carried one. Both are needed to read `entropy` honestly: a 0 from
    # one trip is arithmetic, a 0 from 53 trips is a finding.
    n_destinations: int = 0
    trips_with_destination: int = 0
    # False when trips_with_destination < 2 -- an entropy computed from a
    # single observation can only be 0 and says nothing about the person.
    is_informative: bool = False
    # The most-visited destination and its share, so the page can say what a
    # low number actually means for this traveler ("53 of 53 trips to JFK").
    top_destination: Optional[str] = None
    top_destination_share: Optional[float] = None
    # The denominator, echoed so the page can show what `normalized` is a
    # fraction OF. It's a property of the whole dataset and moves whenever the
    # trip data does, so hardcoding 106 in the frontend would silently rot.
    global_distinct_destinations: Optional[int] = None
    destination_unit: Optional[str] = None


class TravelerDetail(TravelerSummary):
    trips: list[TravelerTrip]
    # Null when compute_traveler_entropy.py hasn't been run in this checkout,
    # which is distinct from "ran, but this traveler has no destination data"
    # (that's a DestinationEntropy with entropy=None).
    #
    # BY DESTINATION AIRPORT. Null `entropy` inside it is the common case --
    # 124 of 206 travelers record no airport at all.
    destination_entropy: Optional[DestinationEntropy] = None
    # THE SAME MEASURE BY UN M49 DETAILED REGION. Deliberately a separate
    # field rather than a variant of the one above: the two are on different
    # scales and answer different questions ("does this person use different
    # airports?" vs "does this person visit different parts of the world?"),
    # so the page shows both, labelled, rather than picking one.
    #
    # Its `normalized` divides by a FIXED 22 -- every M49 detailed region
    # there is, not the 14 this dataset visits -- so the number doesn't
    # rescale when a trip to a new region is added. `destination_unit` says
    # which unit any given block came from.
    region_entropy: Optional[DestinationEntropy] = None


class TravelersResponse(BaseModel):
    # False when travelers.json hasn't been generated in this checkout (see
    # data_loader.load_travelers). The distinction matters to the page: with
    # this false, /rec-sys explains which scripts to run; with it true and an
    # empty list, the data genuinely has no travelers in it.
    dataset_available: bool
    travelers: list[TravelerSummary]


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
        # Same 0-vs-null convention as the line above.
        "travelers_loaded": len(TRAVELERS) if TRAVELERS is not None else None,
        "traveler_entropy_loaded": (
            len(TRAVELER_ENTROPY["by_traveler"]) if TRAVELER_ENTROPY is not None else None
        ),
        # Which of the two traveler files is actually being served --
        # "travelers_anon.json" (author personas) or "travelers.json" (the
        # source's own names). Worth reporting: they're interchangeable at
        # the API level, so this is the only way to tell from outside.
        "travelers_source": resolve_travelers_path().name if resolve_travelers_path() else None,
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


@app.get("/api/travelers", response_model=TravelersResponse)
def travelers():
    """Every traveler in the dataset, without their trips -- the /rec-sys
    card grid. Already ordered most-trips-first by build_travelers.py, and
    not re-sorted here so the page's ordering has exactly one source of
    truth.

    No pagination: this is 139 trips' worth of travelers, and the whole point
    of the page is showing all of them at once. Revisit if the dataset is
    ever swapped for a real one.

    `dataset_available: false` with an empty list means travelers.json hasn't
    been generated here -- see load_travelers(). That's deliberately NOT a
    500 or an empty 200: the page tells the user which scripts to run."""
    if TRAVELERS is None:
        return TravelersResponse(dataset_available=False, travelers=[])

    return TravelersResponse(
        dataset_available=True,
        travelers=[
            TravelerSummary(
                **{k: v for k, v in t.items() if k != "trips"},
                tags=_tags(t["traveler_id"]),
                region_entropy_normalized=_region_entropy_normalized(t["traveler_id"]),
                real_person=t["traveler_id"] in REAL_PERSON_TRAVELER_IDS,
            )
            for t in TRAVELERS.values()
        ],
    )


def _region_entropy_normalized(traveler_id: str) -> Optional[float]:
    """The region-entropy figure the /rec-sys grid filters on, or None when
    that file hasn't been built. Deliberately routed through
    _destination_entropy() rather than reading the row directly, so the
    number on a card is by construction the number on that traveler's own
    page."""
    entropy = _destination_entropy(traveler_id, TRAVELER_ENTROPY_REGION)
    return entropy.normalized if entropy is not None else None


def _with_regions(trip: dict) -> dict:
    """A trip dict plus its destination's M49 region and detailed region.

    Returns the trip unchanged when the lookup isn't loaded or the country
    isn't in it, leaving both fields null -- which is what the charts treat
    as "not classifiable", as distinct from a region named "Unknown"."""
    if M49_REGIONS is None:
        return trip
    code = (trip.get("destination_country_code") or "").upper()
    record = M49_REGIONS["by_iso2"].get(code)
    if record is None:
        return trip
    return {
        **trip,
        "destination_region": record.get("region"),
        "destination_subregion": record.get("detailed_region"),
    }


def _with_destination_scores(trip: dict) -> dict:
    """A trip dict plus its destination city's UNESCO/Michelin scores and a
    weather score resolved against the trip's OWN dates.

    Returns the trip unchanged when the match file isn't loaded or this
    destination isn't in it, leaving all three null -- which the trip card
    reads as "nothing to show" rather than as a zero. Each of the three is
    filled in independently: a matched city with no weather normals still
    carries UNESCO and Michelin.

    THE 0-DAY RULE (Ivan's): a trip whose end date is missing, unparseable
    or before its start date is treated as ONE day, i.e. the start date
    alone. month_weights() rejects a reversed range outright, and a trip
    that lands after midnight legitimately records a 1-day duration (see
    the Gomez flight log), so this is the difference between a weather
    score and a 500.
    """
    if TRIP_CITY_MATCHES is None:
        return trip
    city, country = trip.get("destination_city"), trip.get("destination_country")
    if not isinstance(city, str) or not isinstance(country, str):
        return trip
    match = TRIP_CITY_MATCHES.get(city, {}).get(country)
    if match is None:
        return trip

    scored = {
        **trip,
        "unesco_score": match.get("unesco_score"),
        "michelin_score": match.get("michelin_score"),
    }

    monthly = CITY_WEATHER_SCORES.get(match["simplemaps_id"])
    if monthly is None:
        return scored
    try:
        start = date.fromisoformat(trip["start_date"])
    except (KeyError, TypeError, ValueError):
        return scored
    try:
        end = date.fromisoformat(trip["end_date"])
    except (KeyError, TypeError, ValueError):
        end = start
    if end < start:
        end = start

    scored["weather_score"] = resolve_weather_score(monthly, month_weights(start, end))
    return scored


def _tags(traveler_id: str) -> list[TravelerTag]:
    """This traveler's tags, or an empty list when the tags file isn't there
    or predates them. Attached to the SUMMARY as well as the detail, so the
    /rec-sys grid can show chips without fetching every traveler's trips."""
    if TRAVELER_TAGS is None:
        return []
    row = TRAVELER_TAGS["by_traveler"].get(traveler_id)
    if row is None:
        return []
    return [TravelerTag(**tag) for tag in row.get("tags", [])]


def _destination_entropy(
    traveler_id: str, source: Optional[dict] = None
) -> Optional[DestinationEntropy]:
    """This traveler's entropy row for one unit, or None if that file isn't
    there. `source` is a loaded entropy payload -- the airport one by default,
    or the region one.

    A traveler present in TRAVELERS but absent from the entropy file means
    the two were generated at different times -- treated as "not computed"
    rather than filled with zeros, for the same reason the null/zero
    distinction matters everywhere else in this block."""
    source = TRAVELER_ENTROPY if source is None else source
    if source is None:
        return None
    row = source["by_traveler"].get(traveler_id)
    if row is None:
        return None

    return DestinationEntropy(
        entropy=row.get("entropy"),
        normalized=row.get("norm_global"),
        n_destinations=row.get("n_destinations", 0),
        trips_with_destination=row.get("trips_with_destination", 0),
        is_informative=row.get("entropy_is_informative", False),
        top_destination=row.get("top_destination"),
        top_destination_share=row.get("top_destination_share"),
        global_distinct_destinations=source["global_distinct_destinations"],
        destination_unit=source["destination_unit"],
    )


@app.get("/api/travelers/{traveler_id}", response_model=TravelerDetail)
def traveler_detail(traveler_id: str):
    """One traveler and every trip they took.

    404 on an unknown traveler_id, and also when the dataset isn't loaded at
    all -- same reasoning as the city routes: an id this project can't
    resolve has no partial answer to give. The list route above is where the
    "dataset not generated" case is communicated, since that's the page
    someone lands on first; getting here with a real id but no dataset means
    a stale bookmark, which reads as "not found" anyway.

    `traveler_id` is build_travelers.py's slug (e.g. "john-smith-american"),
    derived from the name and nationality it grouped on -- so the URL shows
    which two fields decided that this person is one person."""
    traveler = TRAVELERS.get(traveler_id) if TRAVELERS else None
    if traveler is None:
        raise HTTPException(status_code=404, detail=f"No traveler with id {traveler_id!r}")

    return TravelerDetail(
        **{k: v for k, v in traveler.items() if k != "trips"},
        trips=[_with_destination_scores(_with_regions(trip)) for trip in traveler["trips"]],
        tags=_tags(traveler_id),
        destination_entropy=_destination_entropy(traveler_id),
        region_entropy=_destination_entropy(traveler_id, TRAVELER_ENTROPY_REGION),
        real_person=traveler_id in REAL_PERSON_TRAVELER_IDS,
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
