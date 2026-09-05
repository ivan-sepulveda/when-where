"""FastAPI app -- the first "frontend talks to a backend" piece of this project.

See backend/README.md for the full design writeup. Routes that matter:

- `GET /api/destinations/top10` -- country ranking
- `GET /api/destinations/cities/top10` -- same idea at city granularity
- `GET /api/destinations/{country}/weather` -- raw metrics for DestinationDetail
- `GET /api/destinations/cities/{city_id}` (+ `/weather`) -- back CityDetail.tsx
  the way the country routes back DestinationDetail.tsx

**Data loads once at import time** (data_loader.py) and stays in memory for the
life of the process. Every request is cheap arithmetic -- month weights plus a
few weighted averages over ~240 countries or ~3,069 cities -- with no file I/O.
Render's free tier spins the process down after ~15 min idle, but while it is up
every request after the first should be fast.

That is also why cities/top10 is a backend route at all, rather than the
frontend fetching the file the way it does the small country JSON: the city file
is 27MB, fine to hold in server memory once, not fine per page load. See
load_static_city_scores().

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
    load_traveler_recommendations,
    load_m49_regions,
    load_traveler_tags,
    load_travelers,
    load_trip_city_matches,
    load_visa_requirements,
    resolve_travelers_path,
    load_beaches,
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
# The same measure over a coarser unit: M49 detailed region, not airport.
# Loaded separately and never merged -- the scales differ (K = 106 observed
# airports vs a fixed K = 22 regions), so comparing across units is meaningless.
# It also covers far more travelers: only hand-authored itineraries record an
# airport, but every trip records a country, so this is defined for all 206
# rather than 82.
TRAVELER_ENTROPY_REGION = load_traveler_entropy(TRAVELER_ENTROPY_REGION_PATH)
# Also None until compute_traveler_tags.py has been run, and kept separate
# from TRAVELERS for the same reason as the entropy above: it is DERIVED
# from travelers_anon.json.
TRAVELER_TAGS = load_traveler_tags()
# Written by rec_sys_hybrid.py --write. Loaded here at import time like every
# other derived file, so the server never computes a recommendation per request.
# None when the file is absent; the route reports that state explicitly instead
# of erroring. See data_loader.load_traveler_recommendations for the contract.
TRAVELER_RECOMMENDATIONS = load_traveler_recommendations()
# Loaded once at startup like every other dataset here; None means the
# GeoNames extract hasn't been run in this checkout (see load_beaches()).
BEACHES = load_beaches()
# Travelers who are real named people rather than a fictional persona or an
# anonymized Kaggle row: Anthony Bourdain, Gordon Ramsay, Conan O'Brien and Rick
# Steves (real episodes resolved onto real routes -- chef_trips.py), Eduardo
# Gomez (Ivan's own flight log -- build_gomez_trips.py), and the two touring
# musicians (build_tour_trips.py).
#
# HARDCODED, not derived: `synthetic` and `persona_match` are True/"authored"
# for the fictional hand-authored characters too, so nothing in the data
# separates "a real name" from "an authored persona". This set is the only place
# that distinction is recorded, and adding a real traveler is one more id here.
# IDs are travelers_anon.json's -- Rick Steves is "rick-steves" here, not
# build_travelers.py's "rick-steves-american", since anonymization drops the
# nationality suffix for an already-unique authored name.
REAL_PERSON_TRAVELER_IDS = frozenset({
    "anthony-bourdain",
    "gordon-ramsay",
    "conan-o-brien",
    "rick-steves",
    "eduardo-gomez",
    # A real musician on a real, published tour -- the dates and venues come
    # from the tour listing, same standing as the travel-show hosts' episode
    # locations. See data/scripts/multiple/build_tour_trips.py.
    "maria-zardoya",
    "luis-miguel",
})
# None until match_trip_cities.py has run. Resolves a trip's destination to a
# city in tourist_cities_enhanced.json so the trip can carry that city's
# UNESCO/Michelin scores. The name matching is pipeline work and deliberately
# does NOT happen here (backend/README.md). Weather is not in that file: it
# depends on the trip's own dates, which is the one thing this API resolves per
# request.
TRIP_CITY_MATCHES = load_trip_city_matches()
# None until build_m49_regions.py has run. Joined onto each trip at request time
# rather than baked in, because a region is a property of the destination
# country, not of the trip -- and M49 is refreshed on its own schedule.
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
    # simplemaps_id as a string -- the stable unique key for a city here (name
    # alone is not unique: two real cities are both "Kanpur"). This is what the
    # frontend routes on: /destinations/cities/:cityId.
    city_id: str
    # Accented name ("Osaka" with the macron) and its ASCII counterpart. The
    # frontend defaults to city_ascii; `city` is there for anything that wants
    # the accented form. Not an encoding workaround -- see
    # data_loader.load_static_city_scores().
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
    # differ in scope: IMLS is US-only but curated and includes nature centers;
    # OSM is worldwide but community-mapped. See build_city_attractions.py.
    source: str
    distance_km: float


class NearbyPlaces(BaseModel):
    # Total within the attractions radius. May exceed len(places), which
    # build_city_attractions.py caps per category.
    count: int
    places: list[NearbyPlace]


class CityDetailResponse(BaseModel):
    """One city's page data -- the city counterpart of DestinationDetail's country view.

    That page assembles a country from several country-keyed files fetched
    straight from GitHub. Cities cannot work that way -- their source is 27MB
    (see this module's docstring) -- so this endpoint does the same assembly
    server-side and returns it in one response."""

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
    # The three static domain scores /api/destinations/cities/top10 ranks on,
    # for this one city. Weather is the fourth domain and is not here: it
    # depends on a date range, so it lives on the /weather route.
    unesco_score: Optional[float]
    michelin_score: Optional[float]
    price_score: Optional[float]
    # ALL FOUR fields below are null together, and only when
    # city_attractions.json has not been generated in this checkout (see
    # data_loader.load_city_attractions). The frontend hides those sections.
    # Present but empty (count=0, places=[]) means the opposite -- the data IS
    # loaded and nothing is within the radius, which is worth saying on the
    # page, since "no botanical garden within 100km" is real information.
    attractions_radius_km: Optional[float]
    zoos_and_aquariums: Optional[NearbyPlaces]
    botanical_gardens: Optional[NearbyPlaces]
    # US-only (IMLS). Deliberately NOT the whole art museum story: the
    # frontend merges this with worldwide_museums.json, which it already
    # fetches and which covers US cities badly.
    local_art_museums: Optional[NearbyPlaces]


class TripTag(BaseModel):
    """One computed label on a single TRIP -- from classify_trip.py.

    Run over every trip by build_trips_enhanced.py.

    - Same shape as TravelerTag, for the same reason: a chip is a chip wherever
      the UI meets it. The difference is scope -- a TravelerTag describes a
      person's whole history ("United Loyalist"), a TripTag one journey
      ("Ski Trip").
    - Tags are not mutually exclusive and are meant not to be: a July trip to
      Chile can be both a ski trip and summer travel.
    """

    kind: str
    tag_id: str
    label: str


class TravelerTrip(BaseModel):
    """One trip from the traveler dataset.

    Every cost, date and duration is carried BOTH parsed and raw on purpose
    (see build_travelers.py): the parsed value is for future scoring, the raw
    string is what the UI shows -- so an unexpected format or currency degrades
    to "exactly what the source said" rather than a confidently wrong number."""

    trip_id: Optional[str]
    # The source's single free-text destination string, split by hand into a
    # city and a sovereign country -- see build_trips_enhanced.py, which
    # resolves "Sydney, Aus", "Tokyo" and "Honolulu, Hawaii" through a written
    # table rather than by splitting on a comma.
    destination_raw: str
    # Null only when destination_kind is "country" (the source named no city).
    destination_city: Optional[str]
    destination_country: str
    # ISO 3166-1 alpha-2 -- the join key every other dataset here uses
    # (weather, visas, UNESCO, Michelin, prices), which is what eventually
    # makes "how good would this trip have been" answerable without a name match.
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
    # True for hand-authored trips (build_synthetic_trips.py), false for Kaggle
    # rows. The three fields below are only set on the former: their itineraries
    # are built on real airline routes, verified against US DOT T-100, so the
    # carrier and airport codes are worth carrying. Defaulted so an older
    # travelers.json without them still loads.
    synthetic: bool = False
    carrier_name: Optional[str] = None
    origin_airport: Optional[str] = None
    destination_airport: Optional[str] = None
    # True for a leg that is part of a longer journey but was not its point --
    # Atlanta and Paris on a Houston-to-Lisbon trip (chef_traveler.py). Only a
    # hand-kept log can know this, so it is always False elsewhere.
    # THE ROW IS STILL SERVED IN FULL: this flags it for a consumer (the Trips
    # list, the airline/region charts) to exclude from AGGREGATES, it does not
    # remove it from the response.
    layover: bool = False
    # Computed per-trip labels (classify_trip.py). Empty for a trip with no
    # destination airport or no parsed dates -- Kaggle rows have no airport, and
    # a tag there would assert something the source never said.
    tags: list[TripTag] = []
    # The DESTINATION CITY's scores, joined at request time from
    # match_trip_cities.py plus the city data this API already loads. All three
    # are Optional, and null is a real, common state rather than an error:
    #
    #   - unesco_score / michelin_score: null when the destination has no city
    #     record (~23 destinations -- Punta Cana, Montego Bay, Sarasota and
    #     others below tourist_cities.json's population cutoff), or the trip
    #     records no city.
    #   - weather_score: null for those, plus a matched city with no weather
    #     normals (1,770 of 3,069 have them), plus an unparseable start date.
    #
    # A NULL MUST NEVER RENDER AS 0. A UNESCO score of 0.0 is a real value
    # meaning "no World Heritage site within the 50km scoring radius" -- true of
    # 73 of the 138 cities these trips visit, Tokyo included.
    unesco_score: Optional[float] = None
    michelin_score: Optional[float] = None
    # Date-dependent, so unlike the other two it is computed here rather
    # than looked up: the city's per-month 0-10 weather scores, averaged
    # against this trip's own dates (see scoring.month_weights).
    weather_score: Optional[float] = None
    # Plog's PSYCHOCENTRIC end for this city, 0-1 (plog_categorize.py), from the
    # same trip_city_matches record as the scores above. Null on the same ~23
    # destinations with no city record. Stored as the psychocentric pole because
    # that is what the scorer returns first; the allocentric pole is 1 - this.
    # One number, not two.
    plog_score: Optional[float] = None
    # UN M49 geography for destination_country_code, joined at request time (see
    # data_loader.load_m49_regions). Null when m49_regions.json has not been
    # built, or the country is not in it -- the charts drop those trips from
    # their denominator rather than inventing an "Unknown" region, same
    # convention as a trip with no carrier.
    destination_region: Optional[str] = None
    # M49's INTERMEDIATE region where one exists, else the sub-region. 22
    # values -- the tier that keeps Central America, the Caribbean and South
    # America apart instead of merging them into "Latin America and the
    # Caribbean".
    destination_subregion: Optional[str] = None


class TravelerTag(BaseModel):
    """One computed label on a traveler -- from compute_traveler_tags.py.

    - A tag is a fact about the trips AS RECORDED, never something the
      itinerary's author declared. Two travelers written as United loyalists
      fly routes United does not serve and so are not tagged; that
      disagreement is the point of computing tags rather than storing them.
    - `share`, `trips` and `denominator` ride along so the UI can show the
      arithmetic. `denominator` is NOT trip_count: for airline_loyalist it
      counts only trips that record a carrier at all (124 of 206 travelers
      record none), matching the "Airlines flown" chart exactly.
    """

    # Stable machine id, e.g. "airline-loyalist:delta-air-lines-inc" -- built
    # from the full legal carrier name, so two airlines that shorten to the
    # same word can't collide.
    tag_id: str
    # Which rule produced it, e.g. "airline_loyalist". The frontend groups and
    # styles by this, not by parsing the label.
    kind: str
    # What gets drawn on the chip, e.g. "Delta Loyalist".
    label: str
    # Rule-specific evidence, all optional -- a future rule need not have any.
    # A tag always has an id, kind and label; nothing else is guaranteed.
    #
    # The ONE airline this tag is about, or null when it is not about one.
    # "Multi Hub" leaves this null deliberately rather than naming the first of
    # its airlines, so nothing downstream mistakes it for a single-airline tag.
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
    # airports in it. THE CITY IS THE UNIT -- every New Yorker is Multi Hub
    # whether they fly EWR, JFK or LGA -- so the airports are context, not the
    # thing matched on.
    hub_city: Optional[str] = None
    hub_airports: Optional[list[str]] = None
    # trip_pattern: which classify_trip.py tag kind earned this ("ski_trip").
    # Its own field rather than something parsed out of tag_id, and what the
    # chip's tooltip branches on.
    #
    # `trips` here is a COUNT that crossed a floor, not a share that crossed a
    # threshold -- three ski trips make a skier whether the traveler took three
    # trips or three hundred -- so `share` is for the tooltip and nothing keys
    # on it. `denominator` is trips classify_trip.py could tag at all (a
    # destination airport plus both dates), so zero means "we could not tell",
    # not "they never do this".
    trip_kind: Optional[str] = None


class TravelerSummary(BaseModel):
    """A traveler without their trips -- what /rec-sys renders as a card.
    The trips themselves are only sent by the detail route, so the grid stays
    a small response no matter how many trips the dataset grows to."""

    traveler_id: str
    name: str
    nationality: Optional[str]
    # INFERRED, never stated by the source: their nationality's country, and the
    # first plausible home city in it they did not visit on any trip (an
    # Australian who flew to Sydney three times gets Melbourne). See
    # build_travelers.py's infer_base(). Null only for a nationality that script
    # has no city list for.
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
    # True for the handful of travelers who are a real named person, rather than
    # a fictional persona (hand-authored or anonymized) or a raw Kaggle row. See
    # REAL_PERSON_TRAVELER_IDS -- NOT derivable from `synthetic` or
    # `persona_match` above, since both are also true/"authored" for the 82
    # fictional hand-authored characters.
    real_person: bool = False
    trip_count: int
    destinations: list[str]
    # Provenance, not page content -- present only when travelers_anon.json is
    # being served (data_loader.resolve_travelers_path), and never rendered.
    #
    #   "nationality"  author matches the traveler's nationality and gender
    #   "region"       same broad literary region, where a nationality has too
    #                  few deceased authors on record
    #   "unmapped"     name left as the source had it
    #
    # Null when serving raw names. Carried so an imperfect match is inspectable.
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
    """How spread out one traveler's trips are across destinations.

    See compute_traveler_entropy.py, and data/README.md for the derivation.

    Every numeric field is Optional, and that is load-bearing rather than
    defensive: `entropy` is null for the 124 travelers whose trips record no
    destination airport (the Kaggle-sourced ones). NULL IS NOT ZERO -- zero
    would claim "never varies their destination" where the truth is "the source
    does not say" -- so the page must render the two differently."""

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


class TravelerPreferences(BaseModel):
    """A per-traveler destination preference profile -- a rollup, not a new score.

    Aggregates the same per-trip UNESCO/Michelin/weather scores and
    classify_trip.py tags the trip cards already show (see
    _with_destination_scores and TravelerTrip.tags).

    - Six dimensions today. The README TODO this implements names more (food,
      architecture, nightlife) that need datasets this project does not have,
      so they are left rather than guessed at.
    - Each dimension is the MEAN of that trip-level 0-10 score over every
      non-layover trip that has one, rescaled to 0-1. A plain mean, not
      weighted by recency or trip count -- the README left that open, and a
      plain mean needs no further judgement call to defend.
    - **null, not 0**, when no trip has a score for that dimension. A
      Kaggle-sourced traveler whose one trip matched no city gets an all-null
      profile rather than an invented one.
    - `*_trips` alongside each dimension is how many trips it averaged over, so
      a profile drawn from one trip is inspectable rather than reading the same
      as one drawn from fifty.
    """

    unesco: Optional[float] = None
    michelin: Optional[float] = None
    weather: Optional[float] = None
    unesco_trips: int = 0
    michelin_trips: int = 0
    weather_trips: int = 0
    # TWO DIMENSIONS OF A DIFFERENT KIND. The three above are MEANS of a
    # destination's 0-10 quality scores -- "how much UNESCO is where this person
    # goes". These two are SHARES of the traveler's own trips -- "how much of
    # this person's travel is a beach holiday". Both land on 0-1 and both are
    # revealed preference from the same history, which is why they share a
    # radar; but the number underneath is a proportion, not an average, so the
    # UI names it that way (PreferenceAxis.kind in travelerCharts.ts).
    #
    # Numerator: trips carrying classify_trip.py's beach_vacation /
    # holiday_trip tag. THE DENOMINATOR IS NOT trip_count -- it is the trips
    # classify_trip could classify at all. A trip with no destination airport or
    # no parsed dates gets NO tags, so counting it would read a missing airport
    # as evidence of not liking beaches. 124 of 263 travelers are Kaggle rows
    # with no airport on any trip; dividing by trip_count would hand every one
    # of them a confident 0.0. They get null instead.
    holiday: Optional[float] = None
    beach: Optional[float] = None
    holiday_trips: int = 0
    beach_trips: int = 0
    # PLOG, AND ONLY ONE POLE OF IT. Plog's scale is one continuum, so
    # psychocentric and allocentric always sum to 1. Exposing both would invite
    # plotting both, and a radar's spokes read as independent dimensions -- two
    # that always sum to 1 draw the same fact twice and give every polygon a
    # symmetry that is an artefact of the encoding, not of the traveler.
    #
    # THE ALLOCENTRIC POLE is the one kept: every other axis reads "more is more
    # of a trait", and allocentric is the trait that distinguishes -- most
    # travel goes to well-connected places, so a polygon extending here is
    # saying something unusual.
    #
    # Mean of (1 - plog_score) over non-layover trips that have one -- a mean
    # like the first three, not a share like the two above.
    allocentric: Optional[float] = None
    allocentric_trips: int = 0


class TravelerDetail(TravelerSummary):
    trips: list[TravelerTrip]
    # This traveler's preference profile (see TravelerPreferences), computed
    # from the trips above. Always present as an object, never null itself,
    # since it needs nothing precomputed; individual dimensions are null when no
    # trip has that score.
    preferences: Optional[TravelerPreferences] = None
    # Null when compute_traveler_entropy.py has not been run here -- distinct
    # from "ran, but this traveler has no destination data", which is a
    # DestinationEntropy with entropy=None.
    #
    # BY DESTINATION AIRPORT. A null `entropy` inside is the common case: 124 of
    # 206 travelers record no airport at all.
    destination_entropy: Optional[DestinationEntropy] = None
    # THE SAME MEASURE BY M49 DETAILED REGION. A separate field rather than a
    # variant of the one above: the two are on different scales and answer
    # different questions ("does this person use different airports?" vs "does
    # this person visit different parts of the world?"), so the page shows both,
    # labelled, rather than picking one.
    #
    # Its `normalized` divides by a FIXED 22 -- every M49 detailed region there
    # is, not the 14 this dataset visits -- so the number does not rescale when
    # a trip to a new region is added. `destination_unit` says which unit a
    # given block came from.
    region_entropy: Optional[DestinationEntropy] = None


class TravelersResponse(BaseModel):
    # False when travelers.json has not been generated here (see
    # data_loader.load_travelers). The distinction matters to the page: false
    # means /rec-sys explains which scripts to run; true with an empty list
    # means the data genuinely has no travelers.
    dataset_available: bool
    travelers: list[TravelerSummary]


class TravelerRecommendation(BaseModel):
    """One suggested destination for one traveler.

    - `why` is not decoration and not optional in spirit: a recommendation
      nobody can check is unactionable, and the model files make naming the
      evidence a requirement.
    - `source` says WHICH model produced the row (content / collaborative /
      hybrid / popularity), so a list can be read as the mixture it is."""

    destination_key: str
    destination_city: str
    destination_country: str
    region: Optional[str] = None
    score: Optional[float] = None
    source: Optional[str] = None
    # The month this destination's weather curve peaks. Null where the city
    # has no weather normals -- 163 of 222 destinations have one, so an
    # absent month is common and means "unknown", never "any month".
    best_month: Optional[str] = None
    why: list[str] = []


class TravelerRecommendationsResponse(BaseModel):
    """Recommendations for one traveler, or an honest account of why there are none.

    **All three states return 200 on purpose.** The frontend has to tell "the
    recommender has not been run" apart from "the server is broken", and an
    HTTP error code puts both in the same branch of a fetch(). A 404 is still a
    404 -- but only for a traveler_id that does not exist.

        ok             recommendations were generated for this traveler
        not_generated  recommendations.json does not exist -- run
                       rec_sys_hybrid.py --write
        unavailable    the file exists but has nothing for this traveler

    `personalised` is separate from `status`: a popularity fallback is a
    legitimate answer with status "ok", and the UI must be able to label it
    "popular right now" rather than "for you".
    """

    traveler_id: str
    status: str
    detail: str
    personalised: bool = False
    # Which branch the hybrid took for this traveler: both / content /
    # collaborative / neither. Null when nothing has been generated.
    route: Optional[str] = None
    strategy: Optional[str] = None
    generated: Optional[str] = None
    recommendations: list[TravelerRecommendation] = []


class WeatherDetail(BaseModel):
    avg_high_c: float
    avg_low_c: float
    total_precipitation_mm: float
    avg_precipitation_hours_per_day: float
    # Estimated rainy days DURING the trip (0..trip length), not a weighted
    # average of each spanned month's ~30-day count -- see
    # scoring.resolve_rainy_days_estimate(). An estimate, not a count, so the
    # frontend presents it as a range ("1-2 days").
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
    # The departure country's own label from visa_requirements.json ("Mexico").
    # Null, alongside an empty requirements dict, when `departure_country` is
    # not a code this project has visa data for -- same "unknown, not a 404"
    # convention the weather route uses.
    departure_country_name: Optional[str]
    # destination iso2 -> requirement string ("VISA-FREE 90", "EVISA", "VISA
    # REQUIRED"), verbatim. Keyed by iso2 rather than visa_requirements.json's
    # own name label so the frontend can join it against every other
    # country-keyed response by code -- see data_loader.load_visa_requirements().
    requirements: dict[str, str]


class Beach(BaseModel):
    """One ocean beach from GeoNames (see
    data/scripts/multiple/extract_geonames_beaches.py). Lake and river
    beaches are already filtered out upstream."""

    name: str
    lat: float
    lon: float
    country_code: Optional[str] = None


class MonthTripCount(BaseModel):
    month: int          # 1-12
    name: str           # "January"
    short_name: str     # "Jan"
    trips: int
    # Excludes rows flagged `layover` -- see TravelerTrip.layover. Nearly the
    # same as `trips` (only 4 rows are flagged) but it is the honest number for
    # an aggregate.
    trips_excluding_layovers: int


class TripsByMonthResponse(BaseModel):
    # False means travelers.json isn't built in this checkout -- distinct from
    # "built and empty", which the page needs to say differently.
    available: bool
    total_trips: int
    first_year: Optional[int] = None
    last_year: Optional[int] = None
    months: list[MonthTripCount]


class BeachesResponse(BaseModel):
    # 0 with available=False means the source file hasn't been built in this
    # checkout; 0 with available=True would mean it built and found nothing.
    # The page needs to tell those apart to say anything useful.
    available: bool
    total: int
    beaches: list[Beach]


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
        # Which traveler file is being served -- "travelers_anon.json" (author
        # personas) or "travelers.json" (the source's names). Worth reporting:
        # they are interchangeable at the API level, so this is the only way to
        # tell from outside.
        "travelers_source": resolve_travelers_path().name if resolve_travelers_path() else None,
        "city_clusters": len(set(CITY_CLUSTER_REPRESENTATIVES.values())),
        "countries_with_visa_requirements": len(VISA_REQUIREMENTS),
    }


@app.get("/api/trips/by-month", response_model=TripsByMonthResponse)
def trips_by_month():
    """Every trip bucketed by departure month, across all years.

    - Aggregated here rather than client-side: /api/travelers ships every
      traveler with every trip nested, and a page that wants twelve numbers
      should not download megabytes to count them.
    - Two counts per month. `trips` is everything; `trips_excluding_layovers`
      drops rows flagged `layover`. Only 4 rows are flagged, so the series are
      nearly identical -- but this project's convention is that AGGREGATES
      exclude them (see TravelerTrip.layover), and a chart is an aggregate.
    """
    counts = {month: 0 for month in range(1, 13)}
    counts_no_layover = {month: 0 for month in range(1, 13)}
    years: set[int] = set()

    for traveler in (TRAVELERS or {}).values():
        for trip in traveler.get("trips", []):
            start = trip.get("start_date")
            if not start:
                continue
            try:
                month = int(start[5:7])
                years.add(int(start[:4]))
            except (ValueError, IndexError):
                continue
            if month not in counts:
                continue
            counts[month] += 1
            if not trip.get("layover"):
                counts_no_layover[month] += 1

    names = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
    months = [
        {"month": m, "name": names[m - 1], "short_name": names[m - 1][:3],
         "trips": counts[m], "trips_excluding_layovers": counts_no_layover[m]}
        for m in range(1, 13)
    ]
    return {
        "available": TRAVELERS is not None,
        "total_trips": sum(counts.values()),
        "first_year": min(years) if years else None,
        "last_year": max(years) if years else None,
        "months": months,
    }


@app.get("/api/beaches", response_model=BeachesResponse)
def beaches():
    """Every ocean beach, for the /beaches map.

    Served whole rather than paged or bbox-queried: ~11.8k rows, the map draws
    all of them at once, and a filtered endpoint would need the client to say
    what it is looking at before it could draw anything."""
    rows = BEACHES if BEACHES is not None else []
    return {"available": BEACHES is not None, "total": len(rows), "beaches": rows}


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
    """City-level equivalent of /api/destinations/top10, over ~3,069 cities.

    Same combine_domain_scores() math and same "average of whichever domains
    are available" rule, run over STATIC_CITY_SCORES instead of ~240 countries.

    - **Dates are OPTIONAL here** (both required if either is given), unlike
      the country endpoint. That one does not need them: with no dates the
      frontend fetches the 48KB country JSON from GitHub and sorts client-side,
      skipping this API. That path is not viable for cities -- the source is
      27MB -- so this one endpoint serves both the static and date-aware cases.
      The static case runs combine_domain_scores() with weather_score=None,
      i.e. the same "average of 3, not 4" the country route already does for
      any country missing weather.
    - **Diversity guard:** only cities that are their own cluster's
      representative are scored or returned (CITY_CLUSTER_REPRESENTATIVES; see
      data_loader.load_city_cluster_representatives()). Without it the top 10
      was one metro area -- 11 of the top 12 by static score were Osaka-area
      suburbs sharing nearly the same UNESCO/Michelin density.
    - The representative's OWN score is used for ranking, never borrowed from
      whichever cluster member scored highest, so a result never shows a number
      that is not genuinely that city's.
    """
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
    """Lookup for one city's attraction categories, or None if the dataset is absent.

    `attractions("zoo_aquarium")` -> NearbyPlaces.

    The null-vs-empty distinction is the whole point, so it lives here rather
    than being repeated per category:

    - dataset absent -> None for every category ("we have not looked")
    - dataset present, no entry for this category -> an EMPTY NearbyPlaces
      ("we looked, nothing within the radius")

    A city missing from the dataset's `cities` map still gets the empty form:
    build_city_attractions.py omits cities with nothing in any category, which
    means the same thing.
    """
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
    """Everything CityDetail.tsx renders for one city.

    Location, the UNESCO sites and Michelin restaurants within
    CITY_DETAIL_RADIUS_KM (100km) named individually, and the three static
    domain scores.

    - Weather is a separate route (it needs a date range). Art museums are not
      here at all -- that dataset is small and country-keyed, so the frontend
      fetches it from GitHub the way DestinationDetail does.
    - `city_id` is a simplemaps_id as a string, exactly as cities/top10 returns
      it.
    - **An unknown city_id genuinely is a 404**, unlike the "unknown, not a
      404" convention the weather and visa routes use for missing data about a
      valid place: this is not a city the project knows at all, so there is no
      partial answer.
    - Declared after cities/top10 so that literal path matches first -- FastAPI
      resolves in declaration order and "top10" would be swallowed by {city_id}.
    """
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
    """City-level equivalent of /api/destinations/{country}/weather.

    Same day-weighted averaging and trip-length-scaled rainy-day estimate, read
    from this city's own normals rather than its country's capital's.

    - No `capital_city` field, for that reason: there is no proxy to disclose.
    - 404 on an unknown city_id (same reasoning as city_destination_detail),
      but `weather: null` for a known city whose normals have not been pulled.
    """
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
    """One country's raw weather metrics, day-weighted over a trip's date range.

    Avg high/low temp, precipitation, sunshine hours, plus a trip-length-scaled
    rainy-day estimate. For DISPLAY ("Daily Sunlight Hours"), not scoring.

    - The rainy-day figure is scoring.resolve_rainy_days_estimate(), NOT a
      plain weighted average of each month's own count -- that would make a
      short trip show more rainy days than it has.
    - `country` is an ISO 3166-1 alpha-2 code, case-insensitive.
    - `weather` is null, not a 404, for a valid-looking code with no data yet --
      same "unknown, not bad" convention as top10's weather_score.
    """
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
    """Every traveler, without their trips -- the /rec-sys card grid.

    - Already ordered most-trips-first by build_travelers.py and not re-sorted
      here, so the page's ordering has one source of truth.
    - No pagination: the point of the page is showing all of them at once.
      Revisit if the dataset is ever swapped for a real one.
    - `dataset_available: false` with an empty list means travelers.json has
      not been generated (see load_travelers()). Deliberately not a 500 or a
      bare empty 200 -- the page tells the user which scripts to run.
    """
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
    """The region-entropy figure the /rec-sys grid filters on, or None if unbuilt.

    Routed through _destination_entropy() rather than reading the row directly,
    so the number on a card is by construction the number on that traveler's
    own page."""
    entropy = _destination_entropy(traveler_id, TRAVELER_ENTROPY_REGION)
    return entropy.normalized if entropy is not None else None


def _with_regions(trip: dict) -> dict:
    """A trip dict plus its destination's M49 region and detailed region.

    Returns the trip unchanged when the lookup is not loaded or the country is
    not in it, leaving both null -- which the charts treat as "not
    classifiable", as distinct from a region named "Unknown"."""
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
    """A trip dict plus its city's UNESCO/Michelin scores and a date-resolved weather score.

    - Returns the trip unchanged when the match file is not loaded or the
      destination is not in it, leaving all three null -- which the trip card
      reads as "nothing to show", not as a zero.
    - Each of the three fills in independently: a matched city with no weather
      normals still carries UNESCO and Michelin.
    - **THE 0-DAY RULE (Ivan's):** a trip whose end date is missing,
      unparseable, or before its start is treated as ONE day -- the start date
      alone. month_weights() rejects a reversed range outright, and a trip
      landing after midnight legitimately records a 1-day duration (see the
      Gomez log), so this is the difference between a weather score and a 500.
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
        "plog_score": match.get("plog_score"),
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


def _preferences(scored_trips: list[dict]) -> TravelerPreferences:
    """This traveler's destination preference profile (see TravelerPreferences).

    Built from trips already carrying unesco/michelin/weather scores -- the
    SAME list passed to TravelerDetail.trips, after _with_destination_scores.

    - **Computed here rather than offline**, unlike tags and entropy, because
      nothing here needs cross-traveler context (a global K, a T-100 volume
      table). It is a plain mean over trips this function already holds, so
      precomputing would only add a file to keep in sync with
      match_trip_cities.py.
    - Layover legs are excluded, same convention as entropy and tags: Atlanta
      on a Houston-to-Lisbon trip is not a destination whose scores should
      count any more than it counts toward trip_count.
    - The holiday/beach dimensions are shares, not means (see
      TravelerPreferences). They share the layover exclusion but not the
      denominator: theirs is CLASSIFIABLE trips, not trips with a score.
    """
    sums = {"unesco": 0.0, "michelin": 0.0, "weather": 0.0, "allocentric": 0.0}
    counts = {"unesco": 0, "michelin": 0, "weather": 0, "allocentric": 0}
    tagged = {"holiday": 0, "beach": 0}
    classifiable = 0

    for trip in scored_trips:
        if trip.get("layover"):
            continue
        for dim, key in (("unesco", "unesco_score"), ("michelin", "michelin_score"), ("weather", "weather_score")):
            value = trip.get(key)
            if isinstance(value, (int, float)):
                sums[dim] += value
                counts[dim] += 1

        # Flipped to the allocentric pole on the way in, so the mean below is a
        # mean of allocentric values rather than 1 minus a mean of psychocentric
        # ones. Equal for a plain mean, but only for a plain mean -- doing it
        # here keeps that from becoming a trap if this is ever weighted.
        plog = trip.get("plog_score")
        if isinstance(plog, (int, float)):
            sums["allocentric"] += 1.0 - plog
            counts["allocentric"] += 1

        # Mirrors classify_trip.tag_trips()'s own guard exactly. A trip it
        # skipped has no tags for a reason that is NOT "nothing matched",
        # and must stay out of the denominator.
        if not (trip.get("destination_airport") and trip.get("start_date") and trip.get("end_date")):
            continue
        classifiable += 1
        kinds = {tag.get("kind") for tag in (trip.get("tags") or [])}
        for dim, kind in (("holiday", "holiday_trip"), ("beach", "beach_vacation")):
            if kind in kinds:
                tagged[dim] += 1

    return TravelerPreferences(
        unesco=round(sums["unesco"] / counts["unesco"] / 10, 4) if counts["unesco"] else None,
        michelin=round(sums["michelin"] / counts["michelin"] / 10, 4) if counts["michelin"] else None,
        weather=round(sums["weather"] / counts["weather"] / 10, 4) if counts["weather"] else None,
        unesco_trips=counts["unesco"],
        michelin_trips=counts["michelin"],
        weather_trips=counts["weather"],
        # Already 0-1, so no /10 -- unlike the three above, which rescale a
        # 0-10 trip score.
        allocentric=round(sums["allocentric"] / counts["allocentric"], 4) if counts["allocentric"] else None,
        allocentric_trips=counts["allocentric"],
        holiday=round(tagged["holiday"] / classifiable, 4) if classifiable else None,
        beach=round(tagged["beach"] / classifiable, 4) if classifiable else None,
        holiday_trips=classifiable,
        beach_trips=classifiable,
    )


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
    """This traveler's entropy row for one unit, or None if that file is absent.

    `source` is a loaded entropy payload -- the airport one by default, or the
    region one.

    A traveler present in TRAVELERS but absent from the entropy file means the
    two were generated at different times. Treated as "not computed" rather
    than filled with zeros, same null/zero rule as everywhere in this block."""
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

    - 404 on an unknown traveler_id, and also when the dataset is not loaded --
      same reasoning as the city routes: an id this project cannot resolve has
      no partial answer. The list route communicates the "dataset not
      generated" case, since that is the page someone lands on first; getting
      here with a real id and no dataset means a stale bookmark, which reads as
      not-found anyway.
    - `traveler_id` is build_travelers.py's slug ("john-smith-american"),
      derived from the name and nationality it grouped on -- so the URL shows
      which two fields decided that this person is one person.
    """
    traveler = TRAVELERS.get(traveler_id) if TRAVELERS else None
    if traveler is None:
        raise HTTPException(status_code=404, detail=f"No traveler with id {traveler_id!r}")

    scored_trips = [_with_destination_scores(_with_regions(trip)) for trip in traveler["trips"]]

    return TravelerDetail(
        **{k: v for k, v in traveler.items() if k != "trips"},
        trips=scored_trips,
        preferences=_preferences(scored_trips),
        tags=_tags(traveler_id),
        destination_entropy=_destination_entropy(traveler_id),
        region_entropy=_destination_entropy(traveler_id, TRAVELER_ENTROPY_REGION),
        real_person=traveler_id in REAL_PERSON_TRAVELER_IDS,
    )


@app.get("/api/travelers/{traveler_id}/recommendations", response_model=TravelerRecommendationsResponse)
def traveler_recommendations(traveler_id: str, limit: int = Query(3, ge=1, le=10)):
    """Up to `limit` destinations this traveler has not been to.

    **READS A PRECOMPUTED FILE, COMPUTES NOTHING.** Same offline/online split
    as tags and entropy: ranking 224 candidates against a taste vector is
    pipeline work, and doing it per request would put the one expensive thing
    this API avoids back into the request path. rec_sys_hybrid.py --write
    produces recommendations.json; this route serves it.

    - Status is "not_generated" when that file is absent, so the button, the
      fetch and the empty state all work before the file exists.
    - 404 only for an unknown traveler_id, matching /api/travelers/{id}.
    """
    if not TRAVELERS or traveler_id not in TRAVELERS:
        raise HTTPException(status_code=404, detail=f"No traveler with id {traveler_id!r}")

    if TRAVELER_RECOMMENDATIONS is None:
        return TravelerRecommendationsResponse(
            traveler_id=traveler_id,
            status="not_generated",
            detail=(
                "Recommendations haven't been generated for this dataset yet. "
                "Run data/scripts/multiple/rec_sys_hybrid.py."
            ),
        )

    block = TRAVELER_RECOMMENDATIONS["by_traveler"].get(traveler_id)
    rows = (block or {}).get("recommendations") or []
    if not rows:
        return TravelerRecommendationsResponse(
            traveler_id=traveler_id,
            status="unavailable",
            detail="No recommendation could be made for this traveler.",
            route=(block or {}).get("route"),
            strategy=TRAVELER_RECOMMENDATIONS.get("strategy"),
            generated=TRAVELER_RECOMMENDATIONS.get("generated"),
        )

    return TravelerRecommendationsResponse(
        traveler_id=traveler_id,
        status="ok",
        detail="",
        # Defaults to True only when the generator said so -- a missing flag
        # is read as "not personalised", the safer of the two labels to be
        # wrong about.
        personalised=bool(block.get("personalised")),
        route=block.get("route"),
        strategy=TRAVELER_RECOMMENDATIONS.get("strategy"),
        generated=TRAVELER_RECOMMENDATIONS.get("generated"),
        recommendations=[TravelerRecommendation(**row) for row in rows[:limit]],
    )


@app.get("/api/destinations/{departure_country}/visa-requirements", response_model=VisaRequirementsResponse)
def visa_requirements(departure_country: str):
    """All of a departure country's visa requirements against every other country.

    `/api/destinations/MX/visa-requirements` returns every entry
    visa_requirements.json files under "Mexico".

    - **Keyed by destination iso2**, not the file's own name labels: those do
      not string-match this project's country_name values elsewhere, though
      both resolve to the same iso2. See data_loader.load_visa_requirements().
    - `departure_country` is an ISO 3166-1 alpha-2 code, case-insensitive.
    - `requirements` is an empty dict, not a 404, for a valid-looking code with
      no visa data -- same "unknown, not bad" convention as the weather route.
    """
    iso2 = departure_country.upper()
    entry = VISA_REQUIREMENTS.get(iso2)

    return VisaRequirementsResponse(
        departure_country=iso2,
        departure_country_name=entry["country_name"] if entry is not None else None,
        requirements=entry["requirements"] if entry is not None else {},
    )
