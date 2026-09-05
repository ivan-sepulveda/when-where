"""Loads the already-computed data/processed files into memory once at startup.

- This API does no pipeline work of its own -- no pandas, no re-fetching. It
  reads the same CSV/JSON the data/scripts/ pipeline produces and adds one
  thing: resolving weather against a request's date range (see scoring.py).
- Reads ../data/processed and ../data/reference directly rather than copying
  files into backend/, so the API can never drift from the pipeline's output.
"""

import csv
import json
from pathlib import Path

from .scoring import MONTHS, RAW_WEATHER_METRIC_KEYS, great_circle_distance_km, weather_score_from_monthly_metrics

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data"

OVERARCHING_PATH = DATA_DIR / "processed" / "OVERARCHING_TRIP_SCORE_BY_COUNTRY.json"
TOURIST_CITIES_PATH = DATA_DIR / "reference" / "tourist_cities.json"
TOURIST_CITIES_ENHANCED_PATH = DATA_DIR / "processed" / "tourist_cities_enhanced.json"
CITY_ATTRACTIONS_PATH = DATA_DIR / "processed" / "multiple" / "city_attractions.json"
TRAVELERS_PATH = DATA_DIR / "processed" / "multiple" / "travelers.json"
# Same travelers and trips, each sample name replaced by a deceased author of
# the same nationality and gender (build_travelers_anon.py). Preferred over
# travelers.json when present -- see resolve_travelers_path().
TRAVELERS_ANON_PATH = DATA_DIR / "processed" / "multiple" / "travelers_anon.json"
TRAVELER_ENTROPY_PATH = DATA_DIR / "processed" / "multiple" / "traveler_entropy.json"
# Same script, --by region. compute_traveler_entropy.py suffixes every unit
# except airport, which keeps the filename above.
TRAVELER_ENTROPY_REGION_PATH = (
    DATA_DIR / "processed" / "multiple" / "traveler_entropy_region.json"
)
TRAVELER_TAGS_PATH = DATA_DIR / "processed" / "multiple" / "traveler_tags.json"
# Precomputed recommendations per traveler, from rec_sys_hybrid.py --write.
# Tolerated-absence like tags and entropy: a missing file means the script has
# not been run, and the route reports "not_generated" rather than failing.
TRAVELER_RECOMMENDATIONS_PATH = (
    DATA_DIR / "processed" / "multiple" / "rec_sys" / "recommendations.json"
)
BEACHES_PATH = DATA_DIR / "processed" / "multiple" / "geonames_beaches.csv"
# Destination -> city record, from match_trip_cities.py. Lets a trip carry its
# city's UNESCO/Michelin scores without this API doing any name matching.
TRIP_CITY_MATCHES_PATH = DATA_DIR / "processed" / "multiple" / "trip_city_matches.json"
MONTHLY_SCORES_PATH = DATA_DIR / "processed" / "monthly_scores_2025_by_city.json"
WEATHER_METRICS_PATH = DATA_DIR / "processed" / "multiple" / "weather_normals_2025_by_city.json"
COUNTRY_ALIASES_PATH = DATA_DIR / "reference" / "country_aliases.json"
M49_REGIONS_PATH = DATA_DIR / "reference" / "m49_regions.json"
VISA_REQUIREMENTS_PATH = DATA_DIR / "reference" / "visa_requirements.json"

# visa_requirements.json names its ~199 countries in plain English from its own
# source site, not this project's country_aliases.json join key. Most match a
# canonical_name or alias case-insensitively ("Bahamas" is an alias of
# "Bahamas, The"); these 8 don't, either because the label is a variant
# country_aliases.json doesn't carry ("Viet Nam", "Russian Federation") or, for
# Palestinian Territories, because it has no entry at all (SimpleMaps' cities
# database doesn't carry it). Checked against all 199 departure keys and every
# nested destination key -- see load_visa_requirements().
VISA_NAME_ISO2_OVERRIDES = {
    "congo": "CG",  # country_aliases.json canonical_name is "Congo (Brazzaville)"
    "congo (dem. rep.)": "CD",  # country_aliases.json canonical_name is "Congo (Kinshasa)"
    "cote d'ivoire (ivory coast)": "CI",  # country_aliases.json alias is "cote d'ivoire" (no "(ivory coast)")
    "macao": "MO",  # country_aliases.json canonical_name is "Macau"
    "palestinian territories": "PS",  # no country_aliases.json entry at all
    "russian federation": "RU",  # country_aliases.json canonical_name is "Russia"
    "st. vincent and the grenadines": "VC",  # country_aliases.json alias is "saint vincent and the grenadines"
    "viet nam": "VN",  # country_aliases.json canonical_name is "Vietnam"
    # Not a name mismatch like the others: country_aliases.json DOES say
    # "namibia", but its iso2 is the float NaN rather than "NA" (parsed as a
    # pandas missing-value marker upstream). See _load_country_name_to_iso2()
    # for why this is an override rather than a fix to the source file.
    "namibia": "NA",
}

# How close two cities must be to count as "the same area" for the cities/top10
# diversity guard (load_city_cluster_representatives()). Matches
# build_tourist_cities_enhanced.py's SCORE_RADIUS_KM (data/SCORING.md) -- the
# radius already behind each city's unesco_score/michelin_score -- rather than
# inventing a third distance constant. Calibrated on the clustering it was
# written to fix: Osaka's suburbs 9-28km, Seoul/Gimpo 25km, Brussels/Ixelles
# 2.4km, Beijing/Changping 38km all fall inside 50km; a genuinely separate trip
# (Philadelphia from NYC, ~130km) stays outside.
CITY_CLUSTER_RADIUS_KM = 50

# Radius the per-city detail page reports UNESCO sites and Michelin restaurants
# over. Not a new constant: 100km is the largest radius
# build_tourist_cities_enhanced.py precomputes (radii_km: [5,10,25,50,100]) and
# the cap on each city's stored lists, so serving it recomputes nothing.
# DELIBERATELY NOT CITY_CLUSTER_RADIUS_KM (50km, what feeds the scores) --
# scoring asks "close enough to make this city a better trip", this page asks
# "what could I day-trip to", which is a wider net.
CITY_DETAIL_RADIUS_KM = 100

# How many Michelin restaurants load_city_details() keeps per city. The COUNT is
# reported in full (Tokyo has 550 within 100km); only the named list is capped --
# holding 550 entries per city across 3,069 cities is a lot for a page that shows
# a handful, and a handful is what the frontend renders. UNESCO sites need no cap:
# the most any city has within 100km is 16.
CITY_DETAIL_MICHELIN_LIMIT = 10


def load_static_country_scores() -> dict[str, dict]:
    """iso2 -> {country_name, unesco_score, michelin_score, price_score}.

    From build_overarching_trip_scores.py. Only the three static
    (date-independent) scores are taken; that file's own OVERARCHING_SCORE is a
    3-domain average and is deliberately unused, because this API recomputes a
    4-domain average (adding weather) per request."""
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
    """simplemaps_id (str) -> the three static domain scores plus city and country names.

    From build_tourist_cities_enhanced.py. Same shape and reasoning as
    load_static_country_scores() -- the file's own OVERARCHING_SCORE is unused
    because this API recomputes a 4-domain average per request.

    - **Both names are returned.** `city_ascii` ("Osaka") is what the frontend
      defaults to; `city` ("Osaka" accented) is there for anything that wants
      it. A product choice, not an encoding workaround -- source and responses
      are UTF-8 throughout, and a mangled accent is always client-side.
    - **Keyed by simplemaps_id, not name.** City names are not unique here (two
      real cities are both "Kanpur"). Cast to str so it matches
      monthly_scores_<year>_by_city.json's string keys without converting again.
    - **Loads the 27MB file once and keeps six fields.** This is why
      cities/top10 is a backend endpoint rather than a frontend fetch the way
      the 48KB country file is: 27MB is fine in server memory, not fine per
      page load.
    - **Two known-bad source records are skipped**, not passed through:
      Windhoek has `iso2: NaN` (a float, from upstream pandas), and Queenstown
      (`included_reason: "manual_override"`) has `simplemaps_id: null`, which
      would become the string key "None" and collide. Both score low enough
      (0.0 and 2.7) that neither has reached top10, but a route should not
      depend on a low score to survive bad input.
    """
    if not TOURIST_CITIES_ENHANCED_PATH.exists():
        raise FileNotFoundError(
            f"{TOURIST_CITIES_ENHANCED_PATH} not found -- run data/scripts/build_tourist_cities_enhanced.py first."
        )
    with open(TOURIST_CITIES_ENHANCED_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    scores: dict[str, dict] = {}
    skipped = []
    for city in payload["cities"]:
        simplemaps_id = city.get("simplemaps_id")
        iso2 = city.get("iso2")
        if simplemaps_id is None or not isinstance(iso2, str):
            skipped.append(city.get("city", "<unnamed>"))
            continue
        scores[str(simplemaps_id)] = {
            "city": city["city"],
            "city_ascii": city["city_ascii"],
            "country_name": city["country"],
            "country_code": iso2,
            "unesco_score": city["unesco_score"],
            "michelin_score": city["michelin_score"],
            "price_score": city["price_score"],
        }

    if skipped:
        print(f"[data_loader] load_static_city_scores: skipped {len(skipped)} city record(s) with missing simplemaps_id or non-string iso2: {skipped}")

    return scores


def load_city_details() -> dict[str, dict]:
    """simplemaps_id (str) -> what the per-city page shows and the ranking loader drops.

    Location (lat, lng, admin_name, population) plus nearby UNESCO sites and
    Michelin restaurants within CITY_DETAIL_RADIUS_KM, named individually
    rather than reduced to a score.

    - Separate from load_static_city_scores() because ranking 3,069 cities and
      rendering one city's page want different data; merging them would make
      the ranking endpoint carry per-restaurant detail it never reads.
    - Reading the 27MB file twice at startup is deliberate. The parse is ~0.1s;
      keeping the payload alive for both loaders to share would hold several
      hundred MB resident on a 512MB Render instance.
    - Kept per city: ALL unesco_sites within the radius (max 16 anywhere), and
      the CITY_DETAIL_MICHELIN_LIMIT nearest restaurants -- though
      michelin_count is the true full count (up to 550+).
    - The distance filter below is a defensive no-op today: source lists are
      already nearest-first and capped at 100km. It exists so raising radii_km
      upstream cannot silently widen this page.
    - Skips the same two bad records as load_static_city_scores(), so this
      dict's keys stay a subset of that one's.
    """
    if not TOURIST_CITIES_ENHANCED_PATH.exists():
        raise FileNotFoundError(
            f"{TOURIST_CITIES_ENHANCED_PATH} not found -- run data/scripts/build_tourist_cities_enhanced.py first."
        )
    with open(TOURIST_CITIES_ENHANCED_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    details: dict[str, dict] = {}
    for city in payload["cities"]:
        simplemaps_id = city.get("simplemaps_id")
        iso2 = city.get("iso2")
        if simplemaps_id is None or not isinstance(iso2, str):
            continue  # see load_static_city_scores() for what these two records are

        unesco = city.get("unesco_sites") or {}
        michelin = city.get("michelin_restaurants") or {}
        radius_key = f"within_{CITY_DETAIL_RADIUS_KM}km"

        nearby_sites = [
            site for site in unesco.get("sites", []) if site["distance_km"] <= CITY_DETAIL_RADIUS_KM
        ]
        nearby_restaurants = [
            restaurant
            for restaurant in michelin.get("restaurants", [])
            if restaurant["distance_km"] <= CITY_DETAIL_RADIUS_KM
        ]

        details[str(simplemaps_id)] = {
            "city": city["city"],
            "city_ascii": city["city_ascii"],
            "country_name": city["country"],
            "country_code": iso2,
            "admin_name": city.get("admin_name"),
            "lat": city["lat"],
            "lng": city["lng"],
            "population": city.get("population"),
            "unesco_site_count": unesco.get("counts", {}).get(radius_key, len(nearby_sites)),
            "unesco_sites": nearby_sites,
            "michelin_count": michelin.get("counts", {}).get(radius_key, len(nearby_restaurants)),
            "michelin_restaurants": nearby_restaurants[:CITY_DETAIL_MICHELIN_LIMIT],
        }

    return details


def load_city_attractions() -> dict | None:
    """Zoos, gardens and (US-only) art museums near each city, or None if not generated.

    From build_city_attractions.py.

    - **None is first-class here**, unlike every other loader in this module,
      which raises on a missing input. Those inputs are committed, so a missing
      one means a broken checkout and failing loudly is right. This file needs
      Kaggle credentials and a reachable Overpass, so a checkout legitimately
      may not have it -- and refusing to start over one unpopulated page
      section is a worse failure than that section not rendering. main.py maps
      None to null fields and the frontend hides the section.
    - Shape:
        {"radius_km": 100,
         "sources_used": {"openstreetmap": bool, "imls": bool},
         "cities": {simplemaps_id: {category: {"count": N, "places": [...]}}}}
    - A city absent from "cities" has nothing nearby. That is NOT the same as
      the file being absent, which means nobody has looked yet.
    """
    if not CITY_ATTRACTIONS_PATH.exists():
        print(
            f"[data_loader] {CITY_ATTRACTIONS_PATH.name} not found -- the city page's "
            "Aquariums/Zoos and Botanical Gardens sections will be hidden. Run "
            "data/scripts/multiple/build_city_attractions.py to populate them."
        )
        return None

    with open(CITY_ATTRACTIONS_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    return {
        # Read from the file, not assumed equal to CITY_DETAIL_RADIUS_KM:
        # build_city_attractions.py takes --radius-km, so they can differ, and
        # the frontend labels its headings from whatever this says.
        "radius_km": payload.get("radius_km", CITY_DETAIL_RADIUS_KM),
        "sources_used": payload.get("sources_used", {}),
        "cities": payload.get("cities", {}),
    }


def resolve_travelers_path() -> Path | None:
    """Which travelers file the API serves, or None if neither exists.

    - travelers_anon.json wins whenever present: same travelers and trips with
      the source's filler names ("John Smith", "Ken Tanaka") swapped for real
      deceased authors, which is what makes a grid of 124 cards legible -- half
      the source names are permutations of Smith/Lee/Kim.
    - Deleting that file is all it takes to go back to raw names, which is why
      this is a file-existence check rather than a config flag.
    - Separate from load_travelers() so /health can report which file is served
      without re-deriving the rule.
    """
    if TRAVELERS_ANON_PATH.exists():
        return TRAVELERS_ANON_PATH
    if TRAVELERS_PATH.exists():
        return TRAVELERS_PATH
    return None


def load_travelers() -> dict[str, dict] | None:
    """traveler_id -> one traveler and every trip they took, or None if not generated.

    From build_travelers.py, or build_travelers_anon.py when present (see
    resolve_travelers_path()).

    - Same None-instead-of-raising rule as load_city_attractions(): the source
      is a Kaggle dataset that cannot be pulled everywhere, and /rec-sys
      showing an empty state beats the API refusing to start. main.py turns the
      None into an explicit "dataset not generated" response, so the page can
      tell that apart from zero travelers in the data.
    - Keyed by traveler_id rather than kept as the file's list: both callers
      either look one up or iterate all, and a dict does both.
    - Insertion order is preserved, so /api/travelers can serve
      build_travelers.py's own most-trips-first order without re-sorting.
    """
    path = resolve_travelers_path()
    if path is None:
        print(
            f"[data_loader] {TRAVELERS_PATH.name} not found -- /rec-sys will show an empty "
            "state. Run data/scripts/multiple/fetch_traveler_trips.py then build_travelers.py "
            "to populate it."
        )
        return None

    print(f"[data_loader] serving travelers from {path.name}")
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    return {traveler["traveler_id"]: traveler for traveler in payload.get("travelers", [])}


def load_traveler_entropy(path: Path = TRAVELER_ENTROPY_PATH) -> dict | None:
    """Destination entropy per traveler, or None if not generated.

    From compute_traveler_entropy.py.

    - **Called once per UNIT.** The airport file (default) and the region file
      are two runs of the same script over the same travelers, differing only
      in what counts as a distinct destination. Served separately, not merged,
      because the scales are not comparable: `global_distinct_destinations` is
      106 for airports and a fixed 22 for regions.
    - Same None-instead-of-raising rule as load_travelers(): derived from
      travelers_anon.json, which may itself be absent, so the traveler page
      just omits the entropy block.
    - Shape:
        {"global_distinct_destinations": 106,
         "ln_global_distinct_destinations": 4.6634,
         "destination_unit": "airport",
         "by_traveler": {traveler_id: {entropy, norm_global, ...}}}
    - Re-keyed by traveler_id here; the file stores a sorted LIST so a human
      reading it sees the most-varied traveler first. The dataset-level fields
      ride along because the page must say what the normalisation divided BY --
      a bare 0.65 means nothing without "of 106 airports", and that denominator
      moves whenever the trip data does.
    """
    if not path.exists():
        unit_flag = "" if path == TRAVELER_ENTROPY_PATH else " --by region"
        print(
            f"[data_loader] {path.name} not found -- traveler pages will omit that "
            f"entropy block. Run data/scripts/multiple/compute_traveler_entropy.py{unit_flag}."
        )
        return None

    with open(path, encoding="utf-8") as f:
        payload = json.load(f)

    return {
        "destination_unit": payload.get("destination_unit"),
        "global_distinct_destinations": payload.get("global_distinct_destinations"),
        "ln_global_distinct_destinations": payload.get("ln_global_distinct_destinations"),
        "by_traveler": {row["traveler_id"]: row for row in payload.get("travelers", [])},
    }


def load_trip_city_matches() -> dict | None:
    """(destination_city, destination_country) -> the tourist_cities record it resolves to.

    From match_trip_cities.py; None if not generated.

    - Same None-instead-of-raising rule as load_traveler_tags(): derived from
      travelers_anon.json, so trips just render without destination scores.
    - Shape:
        {city_name: {country_name: {simplemaps_id, unesco_score,
                                    michelin_score, matched_city, ...}}}
    - **Re-nested into two levels** from the file's flat "city|country" keys on
      purpose: a city name can appear in more than one country (George Town is
      in both Malaysia and the Cayman Islands, and only one is in the city
      list), so the country is required rather than forgettable.
    - ONLY matched destinations are carried. An unmatched one is absent, which
      the caller reads as "no score" -- same as an absent file.
    """
    if not TRIP_CITY_MATCHES_PATH.exists():
        print(
            f"[data_loader] {TRIP_CITY_MATCHES_PATH.name} not found -- trips will be served "
            "without destination scores. Run data/scripts/multiple/match_trip_cities.py."
        )
        return None

    with open(TRIP_CITY_MATCHES_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    nested: dict[str, dict[str, dict]] = {}
    for row in payload.get("destinations", []):
        if row.get("match_status") != "matched":
            continue
        city, country = row.get("destination_city"), row.get("destination_country")
        if not isinstance(city, str) or not isinstance(country, str):
            continue
        nested.setdefault(city, {})[country] = row
    return nested


def load_traveler_tags() -> dict | None:
    """Tags per traveler from compute_traveler_tags.py, or None if not generated.

    - Same None-instead-of-raising rule as load_traveler_entropy(): derived
      from travelers_anon.json, so the pages just render no chips.
    - Shape:
        {"rules": {"airline_loyalist": {"threshold": 0.8, ...}},
         "by_traveler": {traveler_id: {tags: [...], top_carrier, ...}}}
    - Re-keyed by traveler_id; the file stores a sorted LIST so a human reading
      the CSV sees tagged travelers first.
    - `rules` rides along because a chip's tooltip must name the threshold that
      produced it -- 80% is a choice, and --threshold can change it without the
      frontend knowing.
    """
    if not TRAVELER_TAGS_PATH.exists():
        print(
            f"[data_loader] {TRAVELER_TAGS_PATH.name} not found -- travelers will be served "
            "with no tags. Run data/scripts/multiple/compute_traveler_tags.py."
        )
        return None

    with open(TRAVELER_TAGS_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    return {
        "rules": payload.get("rules", {}),
        "by_traveler": {row["traveler_id"]: row for row in payload.get("travelers", [])},
    }


def load_traveler_recommendations() -> dict | None:
    """Precomputed recommendations per traveler from rec_sys_hybrid.py, or None.

    - **Absence is not an error.** The route reports "not_generated" rather
      than failing, so the site works before the file is built. That is the
      point of reading a file instead of importing the model: the
      offline/online split (backend/README.md) lets the recommender change
      without touching the server. Re-run `rec_sys_hybrid.py --write` after any
      pipeline change -- this file is a build artifact and goes stale silently.
    - Contract (rec_sys_hybrid.write_recommendations() states the same shape
      from the writing end; the two must agree):

        {"generated": "2026-09-05",
         "strategy": "hybrid: switching + reciprocal rank fusion",
         "top_n": 3,
         "travelers": [
           {"traveler_id": "anthony-bourdain",
            "route": "both",              # both|content|collaborative|neither
            "personalised": true,         # false on the popularity fallback
            "recommendations": [
              {"destination_key": "Valencia|Spain",
               "destination_city": "Valencia",
               "destination_country": "Spain",
               "region": "Southern Europe",
               "score": 0.87,
               "source": "hybrid",        # which model produced it
               "best_month": "may",       # null when the city has no curve
               "why": ["Closest to their Lisbon and Barcelona trips"]}
            ]}
         ]}

    - Re-keyed by traveler_id, same as load_traveler_tags(): the file stores a
      list (readable in order) and the API serves one traveler at a time.
    """
    if not TRAVELER_RECOMMENDATIONS_PATH.exists():
        print(
            f"[data_loader] {TRAVELER_RECOMMENDATIONS_PATH.name} not found -- the Recommend "
            "button will report that recommendations haven't been generated. Run "
            "data/scripts/multiple/rec_sys_hybrid.py once its ranking logic exists."
        )
        return None

    with open(TRAVELER_RECOMMENDATIONS_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    return {
        "generated": payload.get("generated"),
        "strategy": payload.get("strategy"),
        "top_n": payload.get("top_n"),
        "by_traveler": {row["traveler_id"]: row for row in payload.get("travelers", [])},
    }


def load_m49_regions() -> dict | None:
    """UN M49 geographic regions per country, or None if not generated.

    From build_m49_regions.py. Same tolerated-absence rule as the other derived
    loaders -- the region charts render their empty state.

    - **Re-keyed by ISO-alpha2.** The file is keyed by alpha-3, which is what
      tourist_cities.json carries and what the M49 export is organised around,
      but every traveler trip records `destination_country_code` in alpha-2 --
      so the API would otherwise rebuild this index per request.
    - `detailed_region` is the value worth charting: M49's intermediate region
      where one exists, else its sub-region. 22 values. See build_m49_regions.py
      for why the literal `subregion` tier is not the one -- short version, it
      puts Mexico, the Caribbean and all of South America in one bucket, and
      this dataset has 341 Mexico trips.
    - `additions` is merged into the index but NOT into the file's own
      `countries` body: M49 has no Taiwan entry and this dataset visits Taipei.
      That keeps the lookup complete while leaving the on-disk copy of the
      standard faithful. The count is logged so the addition cannot go unseen.
    """
    if not M49_REGIONS_PATH.exists():
        print(
            f"[data_loader] {M49_REGIONS_PATH.name} not found -- traveler pages will omit "
            "the region charts. Run data/scripts/multiple/build_m49_regions.py."
        )
        return None

    with open(M49_REGIONS_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    additions = payload.get("additions", {})
    by_iso2: dict[str, dict] = {}
    for record in list(payload.get("countries", {}).values()) + list(additions.values()):
        iso2 = record.get("iso2")
        # Namibia's iso2 is the string "NA" -- a falsy check would work, but a
        # None check is what is meant, so be explicit.
        if iso2 is not None:
            by_iso2[iso2.upper()] = record

    if additions:
        print(f"[data_loader] m49_regions.json: {len(additions)} non-M49 addition(s) merged "
              f"({', '.join(a['name'] for a in additions.values())})")

    return {
        "by_iso2": by_iso2,
        "regions": payload.get("regions", []),
        "detailed_regions": payload.get("detailed_regions", []),
    }


def load_city_cluster_representatives() -> dict[str, str]:
    """simplemaps_id -> the representative city for its geographic cluster.

    Every city maps to something; a city with nothing else within
    CITY_CLUSTER_RADIUS_KM maps to itself.

    **Why:** without it, one metro area fills multiple top-10 spots -- 11 of
    the top 12 by static score were Osaka-area suburbs (Osaka, Higashi-osaka,
    Toyonaka, Nara, Hirakata, Amagasaki...), because nearby cities share the
    UNESCO/Michelin density that feeds their scores. top_city_destinations()
    ranks only cities that ARE their cluster's representative.

    **Algorithm** -- greedy and population-ordered, NOT transitive clustering:

    1. Sort all cities by population, descending.
    2. Walk the list. A city becomes a representative unless it is within
       CITY_CLUSTER_RADIUS_KM of an existing one (which, going descending, is
       always at least as populous) -- then it is absorbed instead.

    This avoids the long-chain problem of transitive clustering (A near B, B
    near C, A far from C, yet all three "the same cluster"). Every city is
    anchored to one fixed most-populous representative in range, matching the
    rule this was built to: if there is a cluster, use the highest population.

    O(n * r) where r is representatives found so far, not O(n^2) -- r stays
    well under n since most of the ~3,069 cities are not clustered. ~1s for the
    full dataset (3,069 -> 1,967 representatives at 50km), fine at startup
    without a spatial index.
    """
    if not TOURIST_CITIES_PATH.exists():
        raise FileNotFoundError(f"{TOURIST_CITIES_PATH} not found -- run data/scripts/multiple/fetch_tourist_cities.py first.")
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)["cities"]

    # Skip the one record load_static_city_scores() skips (Queenstown, NZ --
    # manually added, no simplemaps_id) so these keys stay a subset of that
    # dict's; a "None" cluster entry would be dead weight anyway.
    cities_by_population = sorted(
        (c for c in cities if c.get("simplemaps_id") is not None), key=lambda c: c["population"] or 0, reverse=True
    )

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
    """iso2 -> most populous 'primary'-tagged capital from reference/tourist_cities.json.

    Same convention as build_peak_tourism_interactive_chart.py's
    load_capital_lat(), rather than a second way to pick "the" representative
    city. Not every country has a 'primary' entry (small territories mostly);
    those have no weather data available to this API."""
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
    """iso2 -> display name of the capital used as that country's weather proxy.

    E.g. "JP" -> "Tokyo"; see _pick_primary_capitals(). Weather is resolved
    from one representative capital, not a national average, so the frontend
    can caption which city the numbers are from instead of implying they are
    country-wide."""
    capitals = _pick_primary_capitals()
    return {iso2: capital["city"] for iso2, capital in capitals.items()}


def load_country_weather_scores() -> dict[str, dict[str, float]]:
    """iso2 -> {month_name: weather_score_0_10}, for countries whose capital has data.

    - **Coverage is a subset today, on purpose.** fetch_weather_normals.py is a
      slow, resumable pull against Open-Meteo's rate-limited API (1,770 of a
      ~3,069 city target -- see data/README.md), so some large countries are
      missing (Australia, India, Switzerland) purely because their capital has
      not been pulled, not for any data-quality reason.
    - A missing country drops out of the weather average in
      scoring.combine_domain_scores() rather than getting a fabricated score --
      the same handling PRICE_SCORE already gets upstream.
    - Restart the API after pulling more cities to pick them up. No code change.
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
    """simplemaps_id -> {month_name: weather_score_0_10}, for cities with data.

    - No capital-city proxy step, unlike load_country_weather_scores(): that
      indirection exists to get from a country down to SOME representative
      city, and monthly_scores_<year>_by_city.json is already keyed by the
      exact city being scored.
    - Same coverage caveat: 1,770 of 3,069 cities have data, so most --
      including several currently in the top static-score results -- fall out
      of the weather average rather than getting a fabricated score.
    """
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


# Pulled alongside RAW_WEATHER_METRIC_KEYS but kept separate, because neither is
# averaged the plain way. rainy_days needs days_sampled (that month's real
# 28-31 day count) to become a fraction-of-month in
# scoring.resolve_rainy_days_estimate() -- see that docstring for why averaging
# the raw count is wrong. RAW_WEATHER_METRIC_KEYS drives
# resolve_weather_metrics()'s uniform "just average it" loop, and these two do
# not fit that shape.
EXTRA_MONTHLY_KEYS = ["rainy_days", "days_sampled"]


def load_country_weather_metrics() -> dict[str, dict[str, dict[str, float]]]:
    """iso2 -> {month_name: {raw metric: value}}, in original units, for display.

    - Straight from weather_normals_<year>_by_city.json: avg high/low temp,
      precipitation, sunshine hours (scoring.RAW_WEATHER_METRIC_KEYS) plus
      rainy_days/days_sampled (EXTRA_MONTHLY_KEYS above).
    - This is the INPUT to load_country_weather_scores()'s 0-10 score, kept raw
      so pages can show "Daily Sunlight Hours" rather than one abstract number.
    - Same primary-capital resolution and same missing-capital-means-absent
      behaviour as load_country_weather_scores().
    """
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


def load_city_weather_metrics() -> dict[str, dict[str, dict[str, float]]]:
    """simplemaps_id -> {month_name: {raw metric: value}} -- the city-level counterpart.

    Same fields, units and display-not-scoring purpose as
    load_country_weather_metrics() (DestinationDetail shows these for a
    country, CityDetail for a city).

    - No capital proxy, for the same reason load_city_weather_scores() needs
      none: the file is already keyed by the exact city.
    - Same coverage caveat -- ~1,770 of 3,069 cities have normals, so a missing
      city gets a null `weather` in the response, not a 404 or a made-up number.
    """
    if not WEATHER_METRICS_PATH.exists():
        raise FileNotFoundError(
            f"{WEATHER_METRICS_PATH} not found -- run data/scripts/multiple/fetch_weather_normals.py first."
        )
    with open(WEATHER_METRICS_PATH, encoding="utf-8") as f:
        weather_cities = json.load(f)["cities"]

    keys_to_pull = RAW_WEATHER_METRIC_KEYS + EXTRA_MONTHLY_KEYS
    return {
        city_id: {
            month: {key: entry["months"][month][key] for key in keys_to_pull}
            for month in MONTHS
            if month in entry["months"]
        }
        for city_id, entry in weather_cities.items()
    }


def _load_country_name_to_iso2() -> dict[str, str]:
    """lowercased country name -> iso2, for load_visa_requirements() only.

    Built from every canonical_name and alias in country_aliases.json, plus
    VISA_NAME_ISO2_OVERRIDES for the visa labels that match nothing there.
    Nothing else in this module needs a name-keyed lookup -- everything else is
    iso2-keyed at the source.

    Skips any entry whose iso2 is not a string. Currently only Namibia, whose
    real code "NA" was parsed as a pandas missing-value marker upstream and
    became the float NaN (the same issue load_static_city_scores() works around
    for Windhoek). Namibia is then restored via VISA_NAME_ISO2_OVERRIDES rather
    than left skipped: unlike that low-scoring skip, it is a normal
    visa_requirements.json entry -- both departure and destination -- and a NaN
    dict key would 500 the whole endpoint.
    """
    if not COUNTRY_ALIASES_PATH.exists():
        raise FileNotFoundError(f"{COUNTRY_ALIASES_PATH} not found -- run data/scripts/fetch_tourist_cities.py first.")
    with open(COUNTRY_ALIASES_PATH, encoding="utf-8") as f:
        countries = json.load(f)["countries"]

    name_to_iso2: dict[str, str] = {}
    for country in countries.values():
        iso2 = country["iso2"]
        if not isinstance(iso2, str):
            continue
        name_to_iso2[country["canonical_name"].lower()] = iso2
        for alias in country["aliases"]:
            name_to_iso2[alias.lower()] = iso2

    name_to_iso2.update(VISA_NAME_ISO2_OVERRIDES)
    return name_to_iso2


def load_visa_requirements() -> dict[str, dict]:
    """Departure iso2 -> that country's label and its per-destination visa requirements.

    Shape: {"country_name": the file's own top-level label,
            "requirements": {destination iso2: requirement string}}.

    - **Requirement strings pass through verbatim** ("VISA-FREE 90",
      "EVISA \u00b7 VISA ON ARRIVAL 30"). This loader does not parse or score
      them; it regroups the file by iso2 -- both the departure key and the
      destination keys inside it.
    - **Why iso2 and not names:** the file's labels come from the scraped
      source ("South Korea") and do not match this project's country_name
      values elsewhere ("Korea, South", from World Bank data), though both
      resolve to KR. iso2 is what lets a response join against every other
      country-keyed route.
    - Both directions normalise through _load_country_name_to_iso2().
    - **A destination that fails to normalise is dropped and logged**, not
      raised, and does not take out the departure country. Verified that all
      199 names resolve cleanly today -- this guards a future refresh adding a
      label the override list has not caught up to.
    - A departure country whose OWN label fails to normalise is skipped
      entirely, with a warning -- same log-and-continue as
      load_static_city_scores().
    """
    if not VISA_REQUIREMENTS_PATH.exists():
        raise FileNotFoundError(f"{VISA_REQUIREMENTS_PATH} not found -- see data/reference/visa_requirements.json.")
    with open(VISA_REQUIREMENTS_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    name_to_iso2 = _load_country_name_to_iso2()

    requirements_by_iso2: dict[str, dict] = {}
    skipped_departures = []
    skipped_destinations = []
    for departure_name, requirements in payload.items():
        departure_iso2 = name_to_iso2.get(departure_name.lower())
        if departure_iso2 is None:
            skipped_departures.append(departure_name)
            continue

        destination_requirements: dict[str, str] = {}
        for destination_name, requirement in requirements.items():
            destination_iso2 = name_to_iso2.get(destination_name.lower())
            if destination_iso2 is None:
                skipped_destinations.append(f"{departure_name} -> {destination_name}")
                continue
            destination_requirements[destination_iso2] = requirement

        requirements_by_iso2[departure_iso2] = {
            "country_name": departure_name,
            "requirements": destination_requirements,
        }

    if skipped_departures:
        print(f"[data_loader] load_visa_requirements: skipped {len(skipped_departures)} departure countr(ies) with no iso2 match: {skipped_departures}")
    if skipped_destinations:
        print(f"[data_loader] load_visa_requirements: skipped {len(skipped_destinations)} destination entr(ies) with no iso2 match: {skipped_destinations}")

    return requirements_by_iso2


def load_beaches() -> list[dict] | None:
    """Ocean beaches from extract_geonames_beaches.py, or None if not generated.

    - Same None-instead-of-raising rule as load_traveler_tags(): building it
      needs the 1.5GB GeoNames dump in data/globalshorelines/, absent from a
      fresh checkout, so /beaches says so rather than 500ing.
    - Only the four fields the map needs are kept. feature_code (BCH/BCHS) is
      dropped -- it separates "beach" from "beaches", which matters when
      filtering GeoNames and not at all when drawing a dot.
    """
    if not BEACHES_PATH.exists():
        print(
            f"[data_loader] {BEACHES_PATH.name} not found -- /api/beaches will return "
            "an empty list. Run data/scripts/multiple/extract_geonames_beaches.py."
        )
        return None

    beaches = []
    with open(BEACHES_PATH, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                lat, lon = float(row["lat"]), float(row["lon"])
            except (TypeError, ValueError):
                continue
            beaches.append({
                "name": row["name"],
                "lat": lat,
                "lon": lon,
                "country_code": row["country_code"] or None,
            })
    return beaches
