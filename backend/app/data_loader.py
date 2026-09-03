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
# Same travelers and trips, with each sample name replaced by a deceased
# author of the same nationality and gender (build_travelers_anon.py). Served
# in preference to travelers.json when it exists -- see
# resolve_travelers_path().
TRAVELERS_ANON_PATH = DATA_DIR / "processed" / "multiple" / "travelers_anon.json"
TRAVELER_ENTROPY_PATH = DATA_DIR / "processed" / "multiple" / "traveler_entropy.json"
# Same script, --by region. compute_traveler_entropy.py suffixes every unit
# except airport, which keeps the original filename above.
TRAVELER_ENTROPY_REGION_PATH = (
    DATA_DIR / "processed" / "multiple" / "traveler_entropy_region.json"
)
TRAVELER_TAGS_PATH = DATA_DIR / "processed" / "multiple" / "traveler_tags.json"
# Precomputed destination recommendations, one block per traveler, from
# data/scripts/multiple/rec_sys_hybrid.py. DOES NOT EXIST YET -- the
# recommender's data prep is built but its ranking logic is still
# pseudocode (see that file), so this loader returning None is the normal
# state today rather than an error. Same tolerated-absence treatment as
# tags and entropy, one step further along: those files exist and this one
# is waiting on a script that hasn't been finished.
TRAVELER_RECOMMENDATIONS_PATH = (
    DATA_DIR / "processed" / "multiple" / "rec_sys" / "recommendations.json"
)
BEACHES_PATH = DATA_DIR / "processed" / "multiple" / "geonames_beaches.csv"
# Destination -> city record, from match_trip_cities.py. Lets a traveler's
# trip carry its destination city's UNESCO/Michelin scores without this API
# doing any name matching of its own.
TRIP_CITY_MATCHES_PATH = DATA_DIR / "processed" / "multiple" / "trip_city_matches.json"
MONTHLY_SCORES_PATH = DATA_DIR / "processed" / "monthly_scores_2025_by_city.json"
WEATHER_METRICS_PATH = DATA_DIR / "processed" / "multiple" / "weather_normals_2025_by_city.json"
COUNTRY_ALIASES_PATH = DATA_DIR / "reference" / "country_aliases.json"
M49_REGIONS_PATH = DATA_DIR / "reference" / "m49_regions.json"
VISA_REQUIREMENTS_PATH = DATA_DIR / "reference" / "visa_requirements.json"

# visa_requirements.json labels its ~199 countries (both as top-level
# departure keys and as destination keys within each) with plain English
# names pulled from its own source site, not this project's usual
# country_aliases.json canonical_name/iso2 join key. Most match a
# canonical_name or alias there case-insensitively (e.g. "Bahamas" is
# listed as an alias of "Bahamas, The") -- these 8 don't, either because
# the label is a variant country_aliases.json doesn't carry as an alias
# ("Viet Nam" vs "vietnam", "Russian Federation" vs "russia") or, for
# Palestinian Territories, because country_aliases.json has no entry for
# it at all (SimpleMaps' underlying cities database doesn't carry it).
# Verified against the full visa_requirements.json name set (all 199
# departure keys and every destination key nested under them) at the time
# this was written -- see load_visa_requirements()'s docstring.
VISA_NAME_ISO2_OVERRIDES = {
    "congo": "CG",  # country_aliases.json canonical_name is "Congo (Brazzaville)"
    "congo (dem. rep.)": "CD",  # country_aliases.json canonical_name is "Congo (Kinshasa)"
    "cote d'ivoire (ivory coast)": "CI",  # country_aliases.json alias is "cote d'ivoire" (no "(ivory coast)")
    "macao": "MO",  # country_aliases.json canonical_name is "Macau"
    "palestinian territories": "PS",  # no country_aliases.json entry at all
    "russian federation": "RU",  # country_aliases.json canonical_name is "Russia"
    "st. vincent and the grenadines": "VC",  # country_aliases.json alias is "saint vincent and the grenadines"
    "viet nam": "VN",  # country_aliases.json canonical_name is "Vietnam"
    # Not actually a name mismatch like the others above -- country_aliases.json
    # DOES label this "namibia", but its iso2 field is the float NaN, not
    # the string "NA" (Namibia's real code "NA" got parsed as a pandas
    # missing-value marker upstream). See _load_country_name_to_iso2()'s
    # docstring for why this override exists instead of just fixing the
    # source file here.
    "namibia": "NA",
}

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

# Radius the per-city detail page reports UNESCO sites and Michelin
# restaurants over (see load_city_details() below and main.py's
# city_destination_detail()). Not a new constant this project invented
# here -- 100km is the largest radius build_tourist_cities_enhanced.py
# already precomputes counts for (radii_km: [5, 10, 25, 50, 100]), and
# also the radius each city's stored sites/restaurants list is itself
# capped at, so serving it recomputes nothing. Deliberately NOT the same
# as CITY_CLUSTER_RADIUS_KM/SCORE_RADIUS_KM (50km, what actually feeds a
# city's unesco_score/michelin_score): scoring asks "close enough to make
# this city a better trip," this page answers "what could I reasonably
# day-trip to," which is a wider net.
CITY_DETAIL_RADIUS_KM = 100

# How many Michelin restaurants load_city_details() keeps per city. The
# count is reported in full (Tokyo has 550 within 100km); only the named
# list is capped -- both because holding a 550-entry list per city in
# memory for 3,069 cities is a lot for a page that shows the first
# handful, and because that's what the frontend renders. UNESCO sites get
# no equivalent cap: the most any city has within 100km is 16.
CITY_DETAIL_MICHELIN_LIMIT = 10


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
    """simplemaps_id (as str) -> {city, city_ascii, country_name,
    country_code, unesco_score, michelin_score, price_score}, read from
    build_tourist_cities_enhanced.py's JSON output. Same shape and same
    reasoning as load_static_country_scores() just above -- only the
    three static (date-independent) domain scores are pulled from here,
    not that file's own precomputed OVERARCHING_SCORE, since this API
    recomputes a 4-domain (adding weather) average per request instead.

    Both `city` (e.g. "Ōsaka") and `city_ascii` (e.g. "Osaka") are
    returned -- per project decision, `city_ascii` is what the frontend
    should default to displaying, `city` is available alongside it for
    anything that wants the properly-accented name. Not a workaround for
    any encoding bug (there wasn't one -- source data and this API's own
    JSON serialization are both correctly UTF-8 throughout; a "Ōsaka"
    that renders as "ÅŒsaka" is always a client-side terminal/console
    decoding issue, not something fixable server-side), just a plain
    product choice about which name to show by default.

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
    to ship to a browser per page load.

    Two known-bad records in the source are skipped here rather than
    passed through: Windhoek, Namibia has `iso2: NaN` (a pandas artifact
    from upstream SimpleMaps processing -- a float, not the string
    country_code this dict's callers expect), and one manually-added
    city (Queenstown, New Zealand -- `included_reason: "manual_override"`,
    not from the SimpleMaps database) has `simplemaps_id: null`, which
    would otherwise become the literal string key `"None"` and silently
    collide with any other such city. Both score low enough (0.0 and 2.7
    respectively, as of this writing) that neither has actually reached
    top10's response yet, but skipping them here is the correct fix
    either way -- a route shouldn't depend on a low score to avoid
    crashing on bad input."""
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
    """simplemaps_id (as str) -> everything the per-city detail page shows
    that load_static_city_scores() throws away: where the city is (lat,
    lng, admin_name, population) and its nearby UNESCO sites / Michelin
    restaurants within CITY_DETAIL_RADIUS_KM, named individually rather
    than reduced to a score.

    This is the same "load the 27MB file once at startup, keep only what's
    needed" pass load_static_city_scores() already does, just keeping a
    different (larger) slice -- the two exist separately because ranking
    3,069 cities and rendering one city's page want genuinely different
    data, and folding both into one dict would mean the ranking endpoint
    carries per-restaurant detail it never reads. Reading the file twice
    at startup (once per loader) is deliberate over caching the parsed
    payload between them: the parse is ~0.1s, while holding the full
    payload alive long enough for both loaders to share it would keep
    several hundred MB resident on a 512MB Render instance.

    What's kept per city, and why it stays small:
      * unesco_sites -- ALL sites within the radius (max 16 for any city).
      * michelin_restaurants -- the CITY_DETAIL_MICHELIN_LIMIT nearest
        only, though michelin_count is the true full count within the
        radius (up to 550+).
    Source lists are already nearest-first and already capped at 100km
    (see tourist_cities_enhanced.json's own "note" field), so the
    distance filter below is a defensive no-op today -- it exists so
    that bumping radii_km in build_tourist_cities_enhanced.py can't
    silently widen this page's radius past CITY_DETAIL_RADIUS_KM.

    Skips the same two known-bad records load_static_city_scores() skips
    (see its docstring) so this dict's keys stay a subset of that one's."""
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
    """The zoos/aquariums, botanical gardens and (US-only) art museums near
    each city, from build_city_attractions.py's output -- or None if that
    file doesn't exist yet.

    None is a first-class case here, unlike every other loader in this
    module, which raises FileNotFoundError on a missing input. The
    difference: those inputs are all already committed to this repo, so a
    missing one means a broken checkout and failing loudly at startup is
    correct. city_attractions.json is generated from two sources that CAN'T
    be pulled from every environment (Kaggle needs credentials, Overpass
    needs to be reachable), so a checkout legitimately might not have it --
    and an API that refuses to start over a page section that hasn't been
    populated yet would be a much worse failure than that section quietly
    not rendering. main.py turns the None into null response fields, and the
    frontend hides those sections rather than claiming a city has no zoo.

    Returned shape (see build_city_attractions.py for how it's produced):
        {"radius_km": 100,
         "sources_used": {"openstreetmap": bool, "imls": bool},
         "cities": {simplemaps_id: {category: {"count": N, "places": [...]}}}}
    Cities with nothing in any category are absent from "cities" entirely,
    which is NOT the same as the file being absent -- the first means
    "nothing nearby," the second means "we haven't looked yet.\""""
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
        # Read from the file rather than assumed to equal
        # CITY_DETAIL_RADIUS_KM -- build_city_attractions.py takes a
        # --radius-km flag, so the two can legitimately differ, and the
        # frontend labels its headings from whatever this says.
        "radius_km": payload.get("radius_km", CITY_DETAIL_RADIUS_KM),
        "sources_used": payload.get("sources_used", {}),
        "cities": payload.get("cities", {}),
    }


def resolve_travelers_path() -> Path | None:
    """Which travelers file the API actually serves, or None if neither has
    been generated yet.

    travelers_anon.json wins whenever it's present: it's the same travelers
    and the same trips with the source's filler names ("John Smith",
    "Ken Tanaka") swapped for real deceased authors, which is what makes a
    grid of 124 cards legible -- half the source names are permutations of
    Smith/Lee/Kim. Deleting that file is all it takes to go back to the raw
    names; nothing else in the stack needs to change, which is why this is a
    file-existence check rather than a config flag.

    Exposed separately from load_travelers() so /health can report WHICH file
    is being served without re-deriving the rule."""
    if TRAVELERS_ANON_PATH.exists():
        return TRAVELERS_ANON_PATH
    if TRAVELERS_PATH.exists():
        return TRAVELERS_PATH
    return None


def load_travelers() -> dict[str, dict] | None:
    """traveler_id -> one traveler and every trip they took, from
    build_travelers.py's output (or build_travelers_anon.py's, when that
    exists -- see resolve_travelers_path()) -- or None if neither file does.

    Same "None instead of raising" treatment as load_city_attractions()
    above, for the same reason: travelers.json is generated from a Kaggle
    dataset that can't be pulled from every environment, so a checkout
    legitimately might not have it, and /rec-sys showing an empty state is a
    far better failure than the whole API refusing to start. (main.py's
    /api/travelers turns the None into an explicit "dataset not generated"
    response rather than an empty list, so the page can tell "no travelers
    loaded" from "zero travelers in the data.")

    Keyed by traveler_id here rather than kept as the source file's list,
    since both routes that use it look one up by id or iterate all of them --
    the dict does both, the list only does the second.

    Ordering is preserved (python dicts keep insertion order), so
    /api/travelers can return them in build_travelers.py's own
    most-trips-first order without re-sorting."""
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
    """Destination entropy per traveler, from
    compute_traveler_entropy.py's output -- or None if that file doesn't
    exist yet.

    Called once per UNIT: the airport file (the default) and the region file
    are two runs of the same script over the same travelers, differing only
    in what counts as a distinct destination. They are loaded and served
    separately rather than merged, because their scales are not comparable --
    see `global_distinct_destinations` below, which is 106 for airports and a
    fixed 22 for regions.

    Same None-instead-of-raising treatment as load_city_attractions() and
    load_travelers(): this is derived from travelers_anon.json, which itself
    may not exist in a given checkout, so a missing file is a normal state
    and the traveler page just doesn't render the entropy block.

    Returned shape:
        {"global_distinct_destinations": 106,
         "ln_global_distinct_destinations": 4.6634,
         "destination_unit": "airport",
         "by_traveler": {traveler_id: {entropy, norm_global, ...}}}

    Re-keyed by traveler_id here (the file itself stores a sorted LIST, so
    that a human reading the CSV/JSON sees the most-varied traveler first).
    The dataset-level fields are kept alongside because the traveler page has
    to be able to say what the normalisation was divided BY -- a bare 0.65
    means nothing without "of 106 destination airports", and that denominator
    changes whenever the trip data does."""
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
    """(destination_city, destination_country) -> the tourist_cities record
    it resolves to, from match_trip_cities.py's output -- or None if that
    file doesn't exist yet.

    Same None-instead-of-raising treatment as load_traveler_tags() below:
    it's derived from travelers_anon.json, so a missing file is a normal
    checkout state, and trips simply render without destination scores.

    Returned shape:
        {city_name: {country_name: {simplemaps_id, unesco_score,
                                    michelin_score, matched_city, ...}}}

    Re-nested from the file's flat "city|country" keys into two levels on
    purpose: a city name can legitimately appear in more than one country
    (George Town is in both Malaysia and the Cayman Islands, and only one
    of them is in the city list), so the country is a required second step
    rather than something a caller can forget. ONLY MATCHED destinations
    are carried -- an unmatched one is absent, which the caller reads as
    "no score", the same as an absent file.
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
    """Tags per traveler, from compute_traveler_tags.py's output -- or None
    if that file doesn't exist yet.

    Same None-instead-of-raising treatment as load_traveler_entropy(), and
    for the same reason: this is derived from travelers_anon.json, so a
    missing file is a normal checkout state and the pages simply render no
    chips.

    Returned shape:
        {"rules": {"airline_loyalist": {"threshold": 0.8, ...}},
         "by_traveler": {traveler_id: {tags: [...], top_carrier, ...}}}

    Re-keyed by traveler_id here; the file itself stores a sorted LIST so a
    human reading the CSV sees the tagged travelers first. The rule
    parameters ride along because a chip's tooltip has to be able to say
    what threshold produced it -- 80% is a choice, not a constant, and
    --threshold can change it without the frontend knowing."""
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
    """Precomputed destination recommendations per traveler, from
    rec_sys_hybrid.py -- or None when that file doesn't exist yet.

    **None is the expected answer today.** The recommender's data
    preparation is real and runs (rec_sys_data_prep.py), but the ranking
    logic in the three rec_sys_*.py model files is still pseudocode, so
    nothing writes this file. The route that reads it says
    "not_generated" rather than failing, and the moment
    rec_sys_hybrid.py starts writing recommendations.json, the API serves
    it with no further change here. That is the whole point of loading it
    from a file instead of importing the model: the offline/online split
    this project already uses for tags and entropy (see backend/README.md)
    means a recommender can be finished without touching the server.

    Expected file shape (the contract rec_sys_hybrid.py has to satisfy):

        {"generated": "2026-09-14",
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
               "best_month": "may",       # null when the city has no weather curve
               "why": ["Closest to your Lisbon and Barcelona trips"]}
            ]}
         ]}

    Re-keyed by traveler_id here, same as load_traveler_tags(), because the
    file stores a list (readable in order) and the API looks up one
    traveler at a time."""
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
    """UN M49 geographic regions per country, from build_m49_regions.py's
    output -- or None if that file doesn't exist yet.

    Same tolerated-absence treatment as the other derived loaders: a missing
    file means the region charts render their empty state rather than the
    server refusing to start.

    RE-KEYED BY ISO-ALPHA2 HERE. The file itself is keyed by ISO-alpha3,
    which is what tourist_cities.json carries and what the M49 export is
    organised around -- but every traveler trip records
    `destination_country_code`, which is alpha-2, so the API would otherwise
    re-derive this index on every request.

    `detailed_region` is the value worth charting: M49's intermediate region
    where one exists, else its sub-region, 22 values in all. See
    build_m49_regions.py for why the literal `subregion` tier isn't the one
    (short version: it puts Mexico, the Caribbean and all of South America in
    one bucket, and this dataset has 341 Mexico trips).

    `additions` is merged into the index but NOT into the file's own
    `countries` body: M49 has no entry for Taiwan and this dataset visits
    Taipei. Merging here keeps the lookup complete while leaving the on-disk
    copy of the standard faithful. The count is logged so the addition can't
    become invisible."""
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
        # Namibia's iso2 is the string "NA" -- a falsy-check on it would be
        # fine, but a None-check is what's meant, so be explicit.
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

    # Skip the same one record load_static_city_scores() skips (Queenstown,
    # NZ -- manually added, no simplemaps_id) so this dict's keys stay a
    # subset of that one's; a "None" cluster entry here would be dead
    # weight, since STATIC_CITY_SCORES has no matching key for it anyway.
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


def load_city_weather_metrics() -> dict[str, dict[str, dict[str, float]]]:
    """simplemaps_id (as str) -> {month_name: {raw metric name: value}},
    the city-level counterpart of load_country_weather_metrics() just
    above -- same fields, same units, same display-not-scoring purpose
    (DestinationDetail shows these for a country, CityDetail for a city).

    No primary-capital proxy step here, for the same reason
    load_city_weather_scores() doesn't need one:
    weather_normals_<year>_by_city.json is already keyed by the exact city
    being asked about, so there's no country -> representative-city
    indirection to do. Same coverage caveat still applies though -- only
    ~1,770 of 3,069 cities have normals pulled so far (see
    fetch_weather_normals.py), so a city missing here gets a null
    `weather` in the response rather than a 404 or a fabricated number."""
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
    """lowercased country name -> iso2, built from every canonical_name and
    alias in country_aliases.json plus VISA_NAME_ISO2_OVERRIDES layered on
    top for the handful of visa_requirements.json labels that don't match
    anything there (see that constant's comment for which, and why). Exists
    only to support load_visa_requirements() below -- nothing else in this
    module needs a name-keyed lookup, everything else here is already
    iso2-keyed at the source.

    Skips any country_aliases.json entry whose iso2 isn't actually a
    string -- currently just Namibia, whose real code "NA" got parsed as
    a pandas missing-value marker upstream and became the float NaN
    instead (same known issue load_static_city_scores() already works
    around for Namibia's Windhoode). Namibia's real code is restored via
    VISA_NAME_ISO2_OVERRIDES below rather than left skipped -- unlike
    load_static_city_scores()'s low-scoring skip, Namibia is a normal
    visa_requirements.json entry (both a departure and destination) that
    would otherwise 500 the whole endpoint (a dict can't have a NaN
    key -- see load_visa_requirements() for how a bad iso2 here used to
    propagate)."""
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
    """iso2 (of the DEPARTURE/passport country) -> {"country_name": the
    departure country's own label as it appears as a top-level key in
    visa_requirements.json, "requirements": {destination iso2: requirement
    string, ...}}, read straight from reference/visa_requirements.json.

    Requirement strings are passed through verbatim (e.g. "VISA-FREE 90",
    "EVISA · VISA ON ARRIVAL 30", "VISA REQUIRED") -- this loader doesn't
    parse or score them, just regroups the source file by iso2 (both the
    departure key AND, unlike an earlier version of this function, the
    destination keys within it) so main.py's response can be joined
    against every other country-keyed route here -- e.g. the frontend
    matching a visa requirement to a /api/destinations/top10 row -- by
    iso2 rather than by name string. Name-string joins don't work here:
    this file's destination labels are whatever the scraped source site
    used ("South Korea"), which don't match this project's own
    country_name values elsewhere ("Korea, South", from World Bank data --
    see build_overarching_trip_scores.py), even though both resolve to
    the same iso2 (KR).

    Both departure and destination normalization go through the same
    _load_country_name_to_iso2() map (country_aliases.json's
    canonical_name/aliases plus VISA_NAME_ISO2_OVERRIDES for the labels
    that don't match anything there). A destination that fails to
    normalize is dropped from that departure country's requirements dict
    (logged, not raised) rather than the whole departure entry being
    skipped -- verified at the time this was written that this never
    actually happens (all 199 names in the file, departure and
    destination alike, resolve cleanly), but a future refresh of this
    file could add a new label the override list hasn't caught up to yet,
    and one bad destination label shouldn't take out an entire country's
    otherwise-good data.

    A departure country whose OWN label doesn't normalize to any iso2 is
    still skipped entirely (with a printed warning) -- same "log and
    continue" handling load_static_city_scores() uses for its two
    known-bad records."""
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
    """Ocean beaches from extract_geonames_beaches.py -- or None if that file
    doesn't exist yet.

    Same None-instead-of-raising treatment as load_traveler_tags(): building
    it needs the 1.5GB GeoNames dump in data/globalshorelines/, which is not
    in a fresh checkout, so a missing file is normal and /beaches simply says
    so rather than 500ing.

    Only the four fields the map needs are kept. The file's feature_code
    column (BCH/BCHS) is dropped here -- it distinguishes "beach" from
    "beaches", which matters when filtering GeoNames and not at all when
    drawing a dot.
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
