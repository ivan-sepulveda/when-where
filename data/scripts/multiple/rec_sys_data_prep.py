"""
Derived from: data/processed/multiple/travelers_anon.json (build_travelers_anon.py)
              data/processed/multiple/trips_enhanced.json  (build_trips_enhanced.py)
              data/processed/multiple/traveler_tags.json   (compute_traveler_tags.py)
              data/processed/multiple/traveler_entropy.json + _region.json
              data/processed/multiple/trip_city_matches.json (match_trip_cities.py)
              data/processed/monthly_scores_2025_by_city.json (fetch_weather_normals.py)
              data/reference/m49_regions.json               (build_m49_regions.py)

SHARED DATA PREP for the three recommender prototypes:

    rec_sys_content_based_filtering.py   destination features x traveler taste
    rec_sys_collaborative_filtering.py   who-else-went-where
    rec_sys_hybrid.py                    both, plus the cold-start routing

**THIS FILE IS REAL AND RUNS. THE THREE FILES ABOVE ARE NOT** -- their
recommendation logic is pseudocode on purpose, because the point of this
first pass is to prove the *inputs* exist, are joined correctly, and carry
their own missingness honestly. Everything here is deliberately stdlib-only
(no numpy/pandas/scikit-learn) for the same reason every other script in
this directory is: it has to run anywhere the repo is checked out, and 263
travelers x 222 destinations is small enough that pure Python costs nothing.
The models can pull in numpy later; the prep should not need it.

WHAT A "RECOMMENDATION" IS HERE. One destination -- a (city, country) pair
-- that a given traveler has not been to. Not an airport: two airports
serving one city (New York EWR/JFK, Washington DCA/IAD, Tokyo HND/NRT) are
the same recommendation, and nobody wants to be told to visit LGA. Not a
country either: "go to Mexico" throws away the difference between Cancun and
Mexico City, which is most of what this dataset knows. The item id is
"City|Country", the same key match_trip_cities.py already writes, because a
city name can exist in two countries (George Town is in Malaysia AND the
Cayman Islands).

FOUR TABLES COME OUT OF THIS:

    destinations.json  items.  One row per (city, country) seen in any trip.
                       Content features: UNESCO / Michelin / Plog, the 12
                       monthly weather scores, M49 region, tag shares,
                       typical duration and cost, popularity.
    travelers.json     users.  One row per traveler. Taste profile (the same
                       four means the API's /api/travelers/{id} computes),
                       tags, both entropies, cadence, month-of-year mix.
    interactions.csv   the (user, item) events -- visits, first/last year,
                       and an implicit-feedback confidence.
    split.json         a deterministic leave-last-out evaluation split.

THE MISSINGNESS RULES, WHICH ARE THE WHOLE REASON THIS IS A SEPARATE FILE:

1.  **null is not zero, ever.** 41 of the 222 destinations have no city
    record in trip_city_matches.json (Punta Cana, Kahului, Providenciales
    and other resort towns below tourist_cities' population cutoff -- see
    data/README.md). Their UNESCO score is *unknown*, and a recommender that
    reads it as 0.0 will quietly learn "never send anyone to a beach town".
    Every numeric feature therefore ships with a parallel OBSERVED MASK, and
    the matrix builders impute only in the copy they hand to the model,
    never in the catalog itself.

2.  A real 0.0 is data. 73 of the visited cities have UNESCO exactly 0.0 --
    Tokyo among them, its nearest World Heritage site is ~71km out. Those
    rows are observed, masked True, and must stay distinguishable from (1).

3.  **Layover legs are excluded from interactions**, matching what
    compute_traveler_tags.py, compute_traveler_entropy.py and the API's
    _preferences() already do. Sitting in Atlanta for two hours on the way
    to Lisbon is not a visit to Atlanta, and feeding it to a recommender
    teaches it that hub airports are popular destinations.

4.  **A traveler with one trip is a cold-start user, not a low-signal one.**
    They are flagged, kept out of the evaluation split, and routed to the
    content model by rec_sys_hybrid.py. Same for the 41 unmatched
    destinations, which are cold-start ITEMS: collaborative filtering can
    still rank them (people went there), content filtering cannot.

    This is the majority case, not an edge: **160 of the 255 travelers with
    any usable trip have been to exactly one destination**, and only 85
    clear the holdout floor. Any claim about this recommender's accuracy
    that does not say which of those two populations it was measured on is
    not a claim about anything.

5.  **28 trips name a country or a region but no city** (destination_kind
    "country" / "region" -- "Greece", "Bali"), and a (city, country) item id
    cannot hold them. They are dropped, which takes 8 travelers out of the
    dataset entirely because that is ALL they have. Counted in `meta` as
    `trips_without_city` / `travelers_without_countable_trips` rather than
    quietly discarded: the alternative design is a second, coarser item
    type, and that decision should be made deliberately rather than by
    whichever join was written first.

WHY THE SPLIT IS LEAVE-LAST-OUT AND NOT RANDOM. These are itineraries with
dates. A random holdout lets the model see 2026 to predict 2019, which
scores well and means nothing. Each traveler with at least MIN_TRIPS_FOR_
HOLDOUT distinct destinations has their chronologically LAST new destination
held out; everything before it is train. No RNG anywhere in this file, so
two runs on the same inputs produce byte-identical outputs.

Usage:
    python data/scripts/multiple/rec_sys_data_prep.py            # build + write
    python data/scripts/multiple/rec_sys_data_prep.py --dry-run  # build + report
    python data/scripts/multiple/rec_sys_data_prep.py --traveler anthony-bourdain

    from rec_sys_data_prep import prepare
    data = prepare()
"""

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
REFERENCE_DIR = DATA_DIR / "reference"
OUT_DIR = PROCESSED_DIR / "rec_sys"

TRAVELERS_PATH = PROCESSED_DIR / "travelers_anon.json"
TRIPS_PATH = PROCESSED_DIR / "trips_enhanced.json"
TAGS_PATH = PROCESSED_DIR / "traveler_tags.json"
ENTROPY_PATH = PROCESSED_DIR / "traveler_entropy.json"
ENTROPY_REGION_PATH = PROCESSED_DIR / "traveler_entropy_region.json"
MATCHES_PATH = PROCESSED_DIR / "trip_city_matches.json"
MONTHLY_SCORES_PATH = DATA_DIR / "processed" / "monthly_scores_2025_by_city.json"
M49_PATH = REFERENCE_DIR / "m49_regions.json"

MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

# A traveler needs this many DISTINCT destinations before one of them can be
# held out: hold out the only destination a 1-trip traveler has and the
# training row is empty, which is not a hard test case, it's no test case.
MIN_TRIPS_FOR_HOLDOUT = 3

# Implicit-feedback confidence, Hu/Koren style: c = 1 + ALPHA * ln(1 + visits).
# Visiting Tokyo eleven times is stronger evidence than visiting it once, but
# not eleven times stronger -- the log is what keeps Bourdain's 201 trips from
# drowning out everyone else in a factorisation.
CONFIDENCE_ALPHA = 8.0


# ---------------------------------------------------------------------------
# small containers
# ---------------------------------------------------------------------------

@dataclass
class FeatureMatrix:
    """A dense numeric matrix plus the mask that says which cells were real.

    `rows[i][j]` is always a number so a model can multiply it; `mask[i][j]`
    is False where that number was IMPUTED (column mean) rather than
    observed. Anything that averages, weights or scores must consult the
    mask -- see the module docstring, rule 1. `scaling` records each
    column's observed min/max so a value can be read back in its original
    units for display."""

    ids: list
    names: list
    rows: list
    mask: list
    scaling: dict = field(default_factory=dict)
    # Which block each column belongs to -- "content", "season",
    # "geography", "popularity". Not decoration: a one-hot region column is
    # observed for every row by construction, so counting raw observed
    # columns makes every traveler look well described. Anything gating on
    # "does this profile have enough evidence" must count within the blocks
    # that can actually be missing. See observed_in_groups().
    groups: dict = field(default_factory=dict)

    def index_of(self, item_id):
        return self.ids.index(item_id)

    def row_for(self, item_id):
        return self.rows[self.index_of(item_id)]

    def observed_count(self):
        return sum(sum(1 for cell in row if cell) for row in self.mask)

    def imputed_count(self):
        return len(self.rows) * len(self.names) - self.observed_count()

    def names_in_groups(self, *group_names):
        """Column names belonging to the named blocks, in matrix order."""
        wanted = set()
        for group in group_names:
            wanted.update(self.groups.get(group, []))
        return [name for name in self.names if name in wanted]

    def observed_in_groups(self, vector, *group_names):
        """(observed, missing) column names from `vector`, restricted to the
        named blocks. `vector` is anything aligned to `self.names` whose
        cells are None where there is no evidence -- a user content profile,
        typically."""
        wanted = set(self.names_in_groups(*group_names)) if group_names else set(self.names)
        observed, missing = [], []
        for name, value in zip(self.names, vector):
            if name not in wanted:
                continue
            (observed if value is not None else missing).append(name)
        return observed, missing


@dataclass
class UserItemMatrix:
    """The interaction matrix, held sparse because it is 98.6% empty.

    `by_user[traveler_id][destination_key] = confidence`. `visits` keeps the
    raw count alongside, since some models want the count and some want the
    confidence."""

    user_ids: list
    item_ids: list
    by_user: dict
    visits: dict

    def density(self):
        cells = len(self.user_ids) * len(self.item_ids)
        filled = sum(len(row) for row in self.by_user.values())
        return filled / cells if cells else 0.0

    def items_for(self, user_id):
        return set(self.by_user.get(user_id, {}))

    def users_for(self, item_id):
        return {u for u, row in self.by_user.items() if item_id in row}

    def dense(self):
        """Full list-of-lists, only when something really needs it. 263 x 222
        floats is 58k cells -- fine here, and not a pattern to carry into a
        dataset that grows."""
        col = {item_id: j for j, item_id in enumerate(self.item_ids)}
        rows = [[0.0] * len(self.item_ids) for _ in self.user_ids]
        for i, user_id in enumerate(self.user_ids):
            for item_id, value in self.by_user.get(user_id, {}).items():
                rows[i][col[item_id]] = value
        return rows


@dataclass
class PreparedData:
    destinations: list
    travelers: list
    interactions: list
    split: dict
    item_features: FeatureMatrix
    user_features: FeatureMatrix
    user_item: UserItemMatrix
    meta: dict

    def destination(self, key):
        return self._dest_index()[key]

    def traveler(self, traveler_id):
        return self._trav_index()[traveler_id]

    def _dest_index(self):
        if not hasattr(self, "_di"):
            self._di = {d["destination_key"]: d for d in self.destinations}
        return self._di

    def _trav_index(self):
        if not hasattr(self, "_ti"):
            self._ti = {t["traveler_id"]: t for t in self.travelers}
        return self._ti


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _read_json(path, required=True):
    if not path.exists():
        if required:
            raise FileNotFoundError(
                f"{path} not found -- run the pipeline in data/README.md first "
                "(build_trips_enhanced.py -> build_travelers.py -> build_travelers_anon.py)."
            )
        print(f"[rec_sys_data_prep] {path.name} not found -- continuing without it.")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_inputs():
    """Every input this module joins, loaded once.

    travelers_anon.json is REQUIRED and is the spine: it is what the API
    serves, it carries traveler_id, and each traveler already holds its own
    trips, so no name-to-id join is needed (traveler names are not unique
    keys -- a traveler is name + nationality, see data/README.md).

    Everything else is optional and degrades to a documented null rather
    than to a fabricated number: without trip_city_matches.json the content
    model has no features and the hybrid falls through to collaborative,
    which is exactly the behaviour a missing file should produce."""
    travelers = _read_json(TRAVELERS_PATH)["travelers"]
    trips_payload = _read_json(TRIPS_PATH)

    tags = _read_json(TAGS_PATH, required=False)
    entropy = _read_json(ENTROPY_PATH, required=False)
    entropy_region = _read_json(ENTROPY_REGION_PATH, required=False)
    matches = _read_json(MATCHES_PATH, required=False)
    monthly = _read_json(MONTHLY_SCORES_PATH, required=False)
    m49 = _read_json(M49_PATH, required=False)

    return {
        "travelers": travelers,
        "trips": trips_payload["trips"],
        "trips_meta": {k: v for k, v in trips_payload.items() if k != "trips"},
        "tags_by_id": {r["traveler_id"]: r for r in (tags or {}).get("travelers", [])},
        "entropy_by_id": {r["traveler_id"]: r for r in (entropy or {}).get("travelers", [])},
        "region_entropy_by_id": {
            r["traveler_id"]: r for r in (entropy_region or {}).get("travelers", [])
        },
        "matches": (matches or {}).get("by_destination", {}),
        "weather_by_city_id": _weather_index(monthly),
        "regions_by_iso2": _m49_index(m49),
        "detailed_regions": (m49 or {}).get("detailed_regions", []),
    }


def weather_score_from_monthly_metrics(metrics):
    """0-10, higher = more pleasant. MIRRORS backend/app/scoring.py exactly
    -- copied rather than imported because nothing in data/scripts/ imports
    from backend/, and adding the first such import to make a prototype
    slightly shorter is a bad trade. If that formula changes, this changes
    with it; data/SCORING.md is the shared spec both answer to."""
    dryness = 1 - (metrics["monthly_rain_score"] + metrics["daily_rain_score"]) / 2
    daylight = metrics["daylight_hours_score"]
    temperature = (metrics["high_temperature_score"] + metrics["low_temperature_score"]) / 2
    calm = 1 - metrics["wind_intensity_score"]
    return round((dryness + daylight + temperature + calm) / 4 * 10, 2)


def _weather_index(monthly):
    """simplemaps_id (str) -> {month: 0-10 score}. 1,770 of 3,069 cities have
    weather normals, so plenty of matched destinations still come back with
    no monthly curve -- that is a null, not a flat 0."""
    if monthly is None:
        return {}
    out = {}
    for city_id, entry in monthly.get("cities", {}).items():
        months = entry.get("months") or {}
        if not all(month in months for month in MONTHS):
            continue
        out[str(city_id)] = {
            month: weather_score_from_monthly_metrics(months[month]) for month in MONTHS
        }
    return out


def _m49_index(m49):
    """iso2 -> M49 record, including the non-standard `additions` (Taiwan) the
    same way backend/app/data_loader.load_m49_regions does. Namibia's iso2 is
    the string "NA", so this checks for None, not falsiness."""
    if m49 is None:
        return {}
    records = list(m49.get("countries", {}).values()) + list(m49.get("additions", {}).values())
    return {r["iso2"].upper(): r for r in records if r.get("iso2") is not None}


# ---------------------------------------------------------------------------
# keys and small helpers
# ---------------------------------------------------------------------------

def destination_key(city, country):
    """The item id. Same "City|Country" shape trip_city_matches.json uses, so
    the two files can be joined by string equality with no normalisation
    step in between (normalisation already happened in match_trip_cities.py,
    and doing it twice in two places is how the two drift apart)."""
    return f"{city}|{country}"


def _is_countable(trip):
    """A trip that counts as a visit. Layovers are out (module docstring,
    rule 3); so is anything with no destination city, which would otherwise
    collapse into a "None|None" item."""
    if trip.get("layover"):
        return False
    return bool(trip.get("destination_city")) and bool(trip.get("destination_country"))


def _year(trip):
    raw = trip.get("start_date")
    try:
        return date.fromisoformat(raw).year
    except (TypeError, ValueError):
        return None


def _month_name(trip):
    raw = trip.get("start_date")
    try:
        return MONTHS[date.fromisoformat(raw).month - 1]
    except (TypeError, ValueError):
        return None


def _median(values):
    clean = sorted(v for v in values if isinstance(v, (int, float)))
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return float(clean[mid])
    return (clean[mid - 1] + clean[mid]) / 2


def _mean(values):
    clean = [v for v in values if isinstance(v, (int, float))]
    return sum(clean) / len(clean) if clean else None


def _share(numerator, denominator):
    return round(numerator / denominator, 4) if denominator else None


# ---------------------------------------------------------------------------
# items: the destination catalog
# ---------------------------------------------------------------------------

def build_destination_catalog(trips, matches, weather_by_city_id, regions_by_iso2):
    """One row per (city, country) that appears in a countable trip.

    BUILT FROM THE TRIPS, LEFT-JOINED ONTO THE MATCH FILE -- not the other
    way round. trips_enhanced.json is canonical for "what destinations
    exist"; trip_city_matches.json is canonical for "what we know about
    them", and it does not cover all of them (181 of 222 as of this
    writing). Driving from the match file would silently drop 41
    destinations that people demonstrably travelled to, which is the exact
    opposite of what a candidate list should do.

    Popularity and tag shares come from the trips themselves and so exist
    for all 222; the score columns are null for the unmatched ones."""
    grouped = defaultdict(list)
    for trip in trips:
        if not _is_countable(trip):
            continue
        grouped[destination_key(trip["destination_city"], trip["destination_country"])].append(trip)

    catalog = []
    for key, dest_trips in sorted(grouped.items()):
        first = dest_trips[0]
        match = matches.get(key) or {}
        city_id = match.get("simplemaps_id")
        monthly = weather_by_city_id.get(str(city_id)) if city_id else None
        iso2 = (first.get("destination_country_code") or "").upper()
        region = regions_by_iso2.get(iso2) or {}

        tag_kinds = Counter()
        for trip in dest_trips:
            for tag in trip.get("tags") or []:
                if tag.get("kind"):
                    tag_kinds[tag["kind"]] += 1

        travellers_here = {t.get("traveler_name") for t in dest_trips if t.get("traveler_name")}
        carriers = {t.get("carrier_name") for t in dest_trips if t.get("carrier_name")}
        airports = sorted({t.get("destination_airport") for t in dest_trips if t.get("destination_airport")})

        catalog.append({
            "destination_key": key,
            "destination_city": first["destination_city"],
            "destination_country": first["destination_country"],
            "destination_country_code": first.get("destination_country_code"),
            "destination_kind": first.get("destination_kind"),
            "airports": airports,
            # --- geography -------------------------------------------------
            "region": region.get("region"),
            "detailed_region": region.get("detailed_region"),
            # --- content scores (null where unmatched) ---------------------
            "matched": bool(match),
            "simplemaps_id": city_id,
            "unesco_score": match.get("unesco_score"),
            "michelin_score": match.get("michelin_score"),
            "plog_score": match.get("plog_score"),
            # Flipped to the allocentric pole on the way in, the same way the
            # API's _preferences() does it, so "high" always means "the
            # adventurous end" on both sides of the eventual dot product.
            "allocentric_score": (
                round(1.0 - match["plog_score"], 4)
                if isinstance(match.get("plog_score"), (int, float)) else None
            ),
            "weather_by_month": monthly,
            "weather_mean": round(_mean(list(monthly.values())), 2) if monthly else None,
            "weather_best_month": (
                max(monthly, key=monthly.get) if monthly else None
            ),
            # --- behaviour of the people who went --------------------------
            "trips": len(dest_trips),
            "travelers": len(travellers_here),
            "beach_share": _share(tag_kinds.get("beach_vacation", 0), len(dest_trips)),
            "ski_share": _share(tag_kinds.get("ski_trip", 0), len(dest_trips)),
            "holiday_share": _share(tag_kinds.get("holiday_trip", 0), len(dest_trips)),
            "median_duration_days": _median([t.get("duration_days") for t in dest_trips]),
            "median_accommodation_cost": _median([t.get("accommodation_cost") for t in dest_trips]),
            "median_transportation_cost": _median([t.get("transportation_cost") for t in dest_trips]),
            "distinct_carriers": len(carriers),
            "first_class_share": _share(
                sum(1 for t in dest_trips if t.get("flight_class") == "First"), len(dest_trips)
            ),
        })
    return catalog


# ---------------------------------------------------------------------------
# users: traveler profiles
# ---------------------------------------------------------------------------

def build_traveler_profiles(travelers, catalog, tags_by_id, entropy_by_id,
                            region_entropy_by_id, regions_by_iso2):
    """One row per traveler: who they are, how they travel, and what their
    trips say they like.

    THE FOUR TASTE MEANS ARE THE SAME FOUR THE API COMPUTES in main.py's
    _preferences() -- UNESCO, Michelin, weather, allocentrism, each a mean
    over the traveler's own non-layover trips, divided by 10 onto 0-1. They
    are recomputed here rather than fetched because this script must run
    without a server, but the definition is deliberately identical: if the
    radar chart on the traveler detail page and the recommender disagree
    about what someone likes, one of them is lying to the user.

    Weather is the one that cannot be recomputed identically. The API scores
    each trip against ITS OWN DATES (a July trip to Reykjavik is not a
    January trip to Reykjavik) using scoring.month_weights(); that is done
    here too, from `weather_by_month` on the destination row, so the numbers
    match. Where a destination has no monthly curve the trip contributes
    nothing to the mean instead of contributing a zero."""
    by_key = {d["destination_key"]: d for d in catalog}
    profiles = []

    for traveler in travelers:
        trips = [t for t in traveler.get("trips", []) if _is_countable(t)]
        tag_row = tags_by_id.get(traveler["traveler_id"]) or {}
        entropy_row = entropy_by_id.get(traveler["traveler_id"]) or {}
        region_row = region_entropy_by_id.get(traveler["traveler_id"]) or {}

        sums = {"unesco": 0.0, "michelin": 0.0, "weather": 0.0, "allocentric": 0.0}
        counts = {"unesco": 0, "michelin": 0, "weather": 0, "allocentric": 0}
        tagged = Counter()
        classifiable = 0
        months = Counter()
        years = []
        durations, accommodation, transportation = [], [], []
        first_class = 0
        visited = Counter()

        for trip in trips:
            key = destination_key(trip["destination_city"], trip["destination_country"])
            visited[key] += 1
            dest = by_key.get(key, {})

            for dim, column in (("unesco", "unesco_score"),
                                ("michelin", "michelin_score"),
                                ("allocentric", "allocentric_score")):
                value = dest.get(column)
                if isinstance(value, (int, float)):
                    sums[dim] += value
                    counts[dim] += 1

            weather = _trip_weather_score(trip, dest.get("weather_by_month"))
            if weather is not None:
                sums["weather"] += weather
                counts["weather"] += 1

            # Mirrors classify_trip.tag_trips()'s own guard: a trip it
            # skipped has no tags for a reason that is not "nothing
            # matched", so it must stay out of the denominator.
            if trip.get("destination_airport") and trip.get("start_date") and trip.get("end_date"):
                classifiable += 1
                for tag in trip.get("tags") or []:
                    tagged[tag.get("kind")] += 1

            month = _month_name(trip)
            if month:
                months[month] += 1
            year = _year(trip)
            if year:
                years.append(year)
            durations.append(trip.get("duration_days"))
            accommodation.append(trip.get("accommodation_cost"))
            transportation.append(trip.get("transportation_cost"))
            if trip.get("flight_class") == "First":
                first_class += 1

        span = (max(years) - min(years) + 1) if years else None
        loyalist = next(
            (t for t in tag_row.get("tags", []) if t.get("kind") == "airline_loyalist"), None
        )

        profiles.append({
            "traveler_id": traveler["traveler_id"],
            "name": traveler["name"],
            "nationality": traveler.get("nationality"),
            "gender": traveler.get("gender"),
            "age": traveler.get("age"),
            "synthetic": traveler.get("synthetic"),
            "persona_match": traveler.get("persona_match"),
            # --- where they start from ------------------------------------
            "base_city": traveler.get("base_city"),
            "base_country": traveler.get("base_country"),
            "base_country_code": traveler.get("base_country_code"),
            "base_inference": traveler.get("base_inference"),
            # The traveler's own M49 region, joined the same way a
            # destination's is. It is what makes "somewhere they have not
            # been" separable from "somewhere far from home" -- two very
            # different recommendations that a model with no origin feature
            # cannot tell apart.
            "base_region": (regions_by_iso2.get((traveler.get("base_country_code") or "").upper()) or {}).get("region"),
            "base_detailed_region": (regions_by_iso2.get((traveler.get("base_country_code") or "").upper()) or {}).get("detailed_region"),
            "home_airport": tag_row.get("home_airport"),
            # --- how much we know about them ------------------------------
            "trip_count": len(trips),
            "distinct_destinations": len(visited),
            "first_year": min(years) if years else None,
            "last_year": max(years) if years else None,
            "trips_per_year": round(len(trips) / span, 2) if span else None,
            "cold_start": len(visited) < 2,
            # --- taste (same definitions as the API's _preferences) --------
            "pref_unesco": round(sums["unesco"] / counts["unesco"] / 10, 4) if counts["unesco"] else None,
            "pref_michelin": round(sums["michelin"] / counts["michelin"] / 10, 4) if counts["michelin"] else None,
            "pref_weather": round(sums["weather"] / counts["weather"] / 10, 4) if counts["weather"] else None,
            "pref_allocentric": round(sums["allocentric"] / counts["allocentric"], 4) if counts["allocentric"] else None,
            "pref_holiday": _share(tagged.get("holiday_trip", 0), classifiable),
            "pref_beach": _share(tagged.get("beach_vacation", 0), classifiable),
            "pref_ski": _share(tagged.get("ski_trip", 0), classifiable),
            "scored_trips": {k: counts[k] for k in counts},
            # --- how they travel ------------------------------------------
            "median_duration_days": _median(durations),
            "median_accommodation_cost": _median(accommodation),
            "median_transportation_cost": _median(transportation),
            "first_class_share": _share(first_class, len(trips)),
            "month_mix": {month: round(months[month] / len(trips), 4) for month in MONTHS} if trips else None,
            # --- precomputed signals from the rest of the pipeline ---------
            "loyalist_carrier": (loyalist or {}).get("carrier_name"),
            "tag_labels": [t.get("label") for t in tag_row.get("tags", [])],
            "home_airport_is_hub": tag_row.get("home_airport_is_hub"),
            "distinct_carriers": tag_row.get("distinct_carriers"),
            "entropy": entropy_row.get("entropy"),
            "entropy_norm_global": entropy_row.get("norm_global"),
            "region_entropy_norm_global": region_row.get("norm_global"),
        })
    return profiles


def _trip_weather_score(trip, monthly):
    """The trip's weather score against its OWN dates, day-weighted across
    the months it spans -- scoring.month_weights() reimplemented in nine
    lines rather than imported, for the reason given in
    weather_score_from_monthly_metrics().

    THE 0-DAY RULE (already load-bearing elsewhere in this repo): an end
    date that is missing, unparseable or before the start date means a
    ONE-DAY trip, i.e. the start date alone. Trips landing after midnight
    really do record a 1-day duration in the Gomez log, so this is the
    difference between a score and a crash."""
    if not monthly:
        return None
    try:
        start = date.fromisoformat(trip["start_date"])
    except (KeyError, TypeError, ValueError):
        return None
    try:
        end = date.fromisoformat(trip["end_date"])
    except (KeyError, TypeError, ValueError):
        end = start
    if end < start:
        end = start

    counts = Counter()
    current = start
    while current <= end:
        counts[MONTHS[current.month - 1]] += 1
        current = date.fromordinal(current.toordinal() + 1)
    total = sum(counts.values())
    return round(sum(monthly[m] * n / total for m, n in counts.items()), 2)


# ---------------------------------------------------------------------------
# interactions
# ---------------------------------------------------------------------------

def build_interactions(travelers):
    """The (traveler, destination) events, one row per pair -- not per trip.

    Implicit feedback: there are no ratings in this dataset and there never
    will be, so "went there" is the signal and "went there repeatedly" is
    the strength. c = 1 + ALPHA * ln(1 + visits) is the Hu/Koren
    formulation; the log matters because trip counts here span 1 to 201."""
    rows = []
    for traveler in travelers:
        trips = [t for t in traveler.get("trips", []) if _is_countable(t)]
        grouped = defaultdict(list)
        for trip in trips:
            grouped[destination_key(trip["destination_city"], trip["destination_country"])].append(trip)

        for key, dest_trips in sorted(grouped.items()):
            years = [y for y in (_year(t) for t in dest_trips) if y]
            dates = sorted(t.get("start_date") or "" for t in dest_trips)
            rows.append({
                "traveler_id": traveler["traveler_id"],
                "destination_key": key,
                "visits": len(dest_trips),
                "confidence": round(1.0 + CONFIDENCE_ALPHA * math.log1p(len(dest_trips)), 4),
                "first_year": min(years) if years else None,
                "last_year": max(years) if years else None,
                "first_visit": dates[0] or None,
                "last_visit": dates[-1] or None,
            })
    return rows


def build_user_item_matrix(interactions):
    user_ids = sorted({r["traveler_id"] for r in interactions})
    item_ids = sorted({r["destination_key"] for r in interactions})
    by_user = defaultdict(dict)
    visits = defaultdict(dict)
    for row in interactions:
        by_user[row["traveler_id"]][row["destination_key"]] = row["confidence"]
        visits[row["traveler_id"]][row["destination_key"]] = row["visits"]
    return UserItemMatrix(user_ids, item_ids, dict(by_user), dict(visits))


def train_test_split(interactions):
    """Leave-last-out, deterministic, no RNG.

    For each traveler with at least MIN_TRIPS_FOR_HOLDOUT distinct
    destinations, the destination they visited LAST (by first_visit date --
    the first time they went somewhere new, which is the moment a
    recommender could have been useful) becomes the test item. Ties break on
    the destination key so the split is stable across runs.

    Travelers below the floor are `cold_start_users`: excluded from the
    split entirely rather than tested on an empty profile. That set is not a
    nuisance, it is the population rec_sys_hybrid.py exists to route."""
    by_user = defaultdict(list)
    for row in interactions:
        by_user[row["traveler_id"]].append(row)

    train, test, cold = [], [], []
    for traveler_id, rows in sorted(by_user.items()):
        if len(rows) < MIN_TRIPS_FOR_HOLDOUT:
            cold.append(traveler_id)
            train.extend(rows)
            continue
        ordered = sorted(rows, key=lambda r: (r["first_visit"] or "", r["destination_key"]))
        held = ordered[-1]
        test.append({"traveler_id": traveler_id, "destination_key": held["destination_key"],
                     "first_visit": held["first_visit"], "visits": held["visits"]})
        train.extend(ordered[:-1])

    return {
        "strategy": "leave-last-out by first_visit date",
        "min_distinct_destinations_for_holdout": MIN_TRIPS_FOR_HOLDOUT,
        "train_interactions": len(train),
        "test_interactions": len(test),
        "evaluable_users": len(test),
        "cold_start_users": cold,
        "train": train,
        "test": test,
    }


# ---------------------------------------------------------------------------
# feature matrices
# ---------------------------------------------------------------------------

def _scale_columns(ids, names, raw_rows):
    """Min-max each column over its OBSERVED values; impute missing cells
    with the observed column mean and record that in the mask.

    Imputing the mean is the least-opinionated choice available: it moves an
    unknown city neither up nor down the ranking relative to the average
    one. It is still a lie, which is why the mask exists and why every
    consumer is expected to read it."""
    n_cols = len(names)
    columns = [[] for _ in range(n_cols)]
    for row in raw_rows:
        for j, value in enumerate(row):
            if isinstance(value, (int, float)):
                columns[j].append(float(value))

    scaling, fills = {}, []
    for j, name in enumerate(names):
        observed = columns[j]
        low = min(observed) if observed else 0.0
        high = max(observed) if observed else 0.0
        scaling[name] = {"min": low, "max": high, "observed": len(observed)}
        mean = sum(observed) / len(observed) if observed else 0.0
        fills.append((mean - low) / (high - low) if high > low else 0.0)

    rows, mask = [], []
    for row in raw_rows:
        scaled_row, mask_row = [], []
        for j, value in enumerate(row):
            name = names[j]
            low, high = scaling[name]["min"], scaling[name]["max"]
            if isinstance(value, (int, float)):
                scaled_row.append((float(value) - low) / (high - low) if high > low else 0.0)
                mask_row.append(True)
            else:
                scaled_row.append(fills[j])
                mask_row.append(False)
        rows.append(scaled_row)
        mask.append(mask_row)

    return FeatureMatrix(ids=ids, names=names, rows=rows, mask=mask, scaling=scaling)


def build_item_feature_matrix(catalog, detailed_regions):
    """Destination x feature, everything on 0-1.

    Three families, in this order: CONTENT (what the place is like),
    SEASON (the 12 monthly weather scores -- the "when" half of when-where,
    and the only reason a recommender here can answer "go in April" rather
    than just "go"), and GEOGRAPHY (one-hot over M49's 22 detailed regions).

    Popularity is deliberately LAST and deliberately logged. A content model
    that ranks on popularity is not a content model, but leaving it out
    entirely denies the hybrid an obvious prior, so it goes in flagged."""
    content = [
        "unesco_score", "michelin_score", "allocentric_score",
        "beach_share", "ski_share", "holiday_share",
        "median_duration_days", "median_accommodation_cost", "median_transportation_cost",
    ]
    season = [f"weather_{month}" for month in MONTHS]
    regions = sorted(r for r in detailed_regions if r)
    geo = [f"region_{r}" for r in regions]
    popularity = ["log_trips", "log_travelers"]
    names = content + season + geo + popularity

    ids, raw = [], []
    for dest in catalog:
        monthly = dest.get("weather_by_month") or {}
        row = [dest.get(column) for column in content]
        row += [monthly.get(month) for month in MONTHS]
        # One-hot is fully observed by construction: an unknown region is a
        # row of zeros, and `region_known` would be the honest extra column
        # if any destination lacked one -- none does today, so it is not
        # invented here.
        row += [1.0 if dest.get("detailed_region") == r else 0.0 for r in regions]
        row += [math.log1p(dest.get("trips") or 0), math.log1p(dest.get("travelers") or 0)]
        ids.append(dest["destination_key"])
        raw.append(row)

    matrix = _scale_columns(ids, names, raw)
    matrix.groups = {"content": content, "season": season,
                     "geography": geo, "popularity": popularity}
    return matrix


def build_user_feature_matrix(profiles, detailed_regions):
    """Traveler x feature, everything on 0-1.

    This is the SIDE-INFORMATION matrix -- who someone is -- and is not the
    same thing as their position in item-feature space. That second vector
    (the taste profile a content model actually scores against) is built by
    build_user_content_profiles() below, out of the items they visited, and
    the two are kept apart on purpose: mixing "prefers long trips" with
    "has been to Southern Europe a lot" into one vector makes it impossible
    to say afterwards which half drove a recommendation."""
    taste = ["pref_unesco", "pref_michelin", "pref_weather", "pref_allocentric",
             "pref_holiday", "pref_beach", "pref_ski"]
    behaviour = ["median_duration_days", "median_accommodation_cost",
                 "median_transportation_cost", "first_class_share",
                 "trips_per_year", "entropy_norm_global", "region_entropy_norm_global"]
    season = [f"month_{month}" for month in MONTHS]
    regions = sorted(r for r in detailed_regions if r)
    geo = [f"base_region_{r}" for r in regions]
    names = taste + behaviour + season + geo

    ids, raw = [], []
    for profile in profiles:
        mix = profile.get("month_mix") or {}
        row = [profile.get(column) for column in taste]
        row += [profile.get(column) for column in behaviour]
        row += [mix.get(month) for month in MONTHS]
        row += [1.0 if profile.get("base_detailed_region") == r else 0.0 for r in regions]
        ids.append(profile["traveler_id"])
        raw.append(row)

    matrix = _scale_columns(ids, names, raw)
    matrix.groups = {"taste": taste, "behaviour": behaviour,
                     "season": season, "geography": geo}
    return matrix


def build_user_content_profiles(user_item, item_features, split=None):
    """Each traveler's centre of gravity in ITEM-FEATURE space: the
    visit-weighted mean of the destinations they have been to.

    This is the vector a content-based model scores candidates against, and
    building it here rather than inside rec_sys_content_based_filtering.py
    is the line this repo draws between prep and model: assembling the
    inputs is data work and runs today; deciding what to do with them is the
    model, and is pseudocode until it is not.

    IMPUTED CELLS ARE SKIPPED, not averaged in. A traveler whose only
    Michelin-scored trip was to an unmatched resort town gets `None` for the
    Michelin coordinate rather than the global mean wearing their name --
    the same null-is-not-zero rule as everywhere else, one level up.

    Pass `split` to build the profile from TRAIN interactions only, which is
    what any honest offline evaluation needs; omit it to profile against
    everything, which is what a live recommendation would use."""
    allowed = None
    if split is not None:
        allowed = defaultdict(set)
        for row in split["train"]:
            allowed[row["traveler_id"]].add(row["destination_key"])

    index = {item_id: i for i, item_id in enumerate(item_features.ids)}
    profiles = {}
    for user_id in user_item.user_ids:
        weights = user_item.visits.get(user_id, {})
        sums = [0.0] * len(item_features.names)
        totals = [0.0] * len(item_features.names)
        for item_id, visits in weights.items():
            if allowed is not None and item_id not in allowed[user_id]:
                continue
            i = index.get(item_id)
            if i is None:
                continue
            for j in range(len(item_features.names)):
                if item_features.mask[i][j]:
                    sums[j] += item_features.rows[i][j] * visits
                    totals[j] += visits
        profiles[user_id] = [
            round(sums[j] / totals[j], 6) if totals[j] else None
            for j in range(len(item_features.names))
        ]
    return profiles


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def prepare(inputs=None):
    """Build everything, in memory, from the files on disk.

    The three model files call THIS, not the written outputs -- the JSON/CSV
    this script writes is for reading with human eyes and for anything
    outside Python, and a model that reads a file it did not just build is a
    model that can silently train on last week's dataset."""
    inputs = inputs or load_inputs()

    catalog = build_destination_catalog(
        inputs["trips"], inputs["matches"], inputs["weather_by_city_id"], inputs["regions_by_iso2"]
    )
    profiles = build_traveler_profiles(
        inputs["travelers"], catalog, inputs["tags_by_id"],
        inputs["entropy_by_id"], inputs["region_entropy_by_id"], inputs["regions_by_iso2"],
    )
    interactions = build_interactions(inputs["travelers"])
    user_item = build_user_item_matrix(interactions)
    split = train_test_split(interactions)

    detailed_regions = inputs["detailed_regions"] or sorted(
        {d["detailed_region"] for d in catalog if d.get("detailed_region")}
    )
    item_features = build_item_feature_matrix(catalog, detailed_regions)
    user_features = build_user_feature_matrix(profiles, detailed_regions)

    matched = sum(1 for d in catalog if d["matched"])
    with_weather = sum(1 for d in catalog if d.get("weather_by_month"))
    meta = {
        "generated_from": {
            "travelers": TRAVELERS_PATH.name,
            "trips": TRIPS_PATH.name,
            "matches": MATCHES_PATH.name,
            "weather": MONTHLY_SCORES_PATH.name,
            "regions": M49_PATH.name,
        },
        "item_unit": "destination (city, country)",
        "interaction_signal": "implicit -- visits, no ratings exist in this dataset",
        "confidence_alpha": CONFIDENCE_ALPHA,
        "travelers": len(profiles),
        "destinations": len(catalog),
        "destinations_matched": matched,
        "destinations_unmatched": len(catalog) - matched,
        "destinations_with_weather": with_weather,
        "interactions": len(interactions),
        "trips_counted": sum(r["visits"] for r in interactions),
        "trips_total": len(inputs["trips"]),
        "layover_trips_excluded": sum(1 for t in inputs["trips"] if t.get("layover")),
        # Rule 5 in the module docstring: a country- or region-level
        # destination has no city, so it cannot be an item under this key.
        # Surfaced, not swallowed.
        "trips_without_city": sum(
            1 for t in inputs["trips"]
            if not t.get("layover") and not t.get("destination_city")
        ),
        "travelers_without_countable_trips": sum(
            1 for p in profiles if p["trip_count"] == 0
        ),
        "travelers_with_one_destination": sum(
            1 for p in profiles if p["distinct_destinations"] == 1
        ),
        "matrix_density": round(user_item.density(), 4),
        "item_feature_count": len(item_features.names),
        "user_feature_count": len(user_features.names),
        "item_cells_imputed": item_features.imputed_count(),
        "user_cells_imputed": user_features.imputed_count(),
        "cold_start_users": len(split["cold_start_users"]),
        "evaluable_users": split["evaluable_users"],
    }

    return PreparedData(
        destinations=catalog,
        travelers=profiles,
        interactions=interactions,
        split=split,
        item_features=item_features,
        user_features=user_features,
        user_item=user_item,
        meta=meta,
    )


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def _write_csv(path, rows, columns):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _csv_value(row.get(c)) for c in columns})


def _csv_value(value):
    """Lists and dicts flatten for CSV; None stays EMPTY rather than becoming
    the string "None" or a 0 -- a CSV reader can tell an empty cell from a
    zero, and this file's whole thesis is that those are different."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_outputs(data, out_dir=OUT_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(out_dir / "destinations.json", "w", encoding="utf-8") as f:
        json.dump({**data.meta, "destinations": data.destinations}, f, indent=2, ensure_ascii=False)
    _write_csv(out_dir / "destinations.csv", data.destinations, [
        "destination_key", "destination_city", "destination_country", "detailed_region",
        "matched", "unesco_score", "michelin_score", "allocentric_score", "weather_mean",
        "weather_best_month", "trips", "travelers", "beach_share", "ski_share", "holiday_share",
        "median_duration_days", "median_accommodation_cost", "median_transportation_cost",
    ])

    with open(out_dir / "travelers.json", "w", encoding="utf-8") as f:
        json.dump({**data.meta, "travelers": data.travelers}, f, indent=2, ensure_ascii=False)
    _write_csv(out_dir / "travelers.csv", data.travelers, [
        "traveler_id", "name", "base_city", "home_airport", "trip_count", "distinct_destinations",
        "cold_start", "pref_unesco", "pref_michelin", "pref_weather", "pref_allocentric",
        "pref_holiday", "pref_beach", "pref_ski", "entropy_norm_global",
        "region_entropy_norm_global", "loyalist_carrier", "first_class_share",
    ])

    with open(out_dir / "interactions.json", "w", encoding="utf-8") as f:
        json.dump({**data.meta, "interactions": data.interactions}, f, indent=2, ensure_ascii=False)
    _write_csv(out_dir / "interactions.csv", data.interactions, [
        "traveler_id", "destination_key", "visits", "confidence",
        "first_visit", "last_visit", "first_year", "last_year",
    ])

    with open(out_dir / "split.json", "w", encoding="utf-8") as f:
        json.dump({**data.meta, **data.split}, f, indent=2, ensure_ascii=False)

    # The two matrices, written flat so they can be eyeballed or loaded by
    # something that is not this module. Masks travel WITH the values --
    # a matrix file without its mask is a file that has forgotten which of
    # its numbers were made up.
    for name, matrix in (("item_features", data.item_features), ("user_features", data.user_features)):
        with open(out_dir / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump({
                "ids": matrix.ids,
                "feature_names": matrix.names,
                "scaling": matrix.scaling,
                "rows": matrix.rows,
                "observed_mask": matrix.mask,
            }, f, indent=2, ensure_ascii=False)

    return out_dir


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def report(data, traveler_id=None):
    m = data.meta
    print(f"{m['travelers']} travelers x {m['destinations']} destinations "
          f"-> {m['interactions']} interactions ({m['matrix_density']:.1%} dense)")
    print(f"  trips counted {m['trips_counted']} of {m['trips_total']} "
          f"({m['layover_trips_excluded']} layover legs and "
          f"{m['trips_without_city']} city-less country/region trips excluded)")
    print(f"  {m['travelers_without_countable_trips']} travelers have nothing countable at all; "
          f"{m['travelers_with_one_destination']} have been to exactly one destination")
    print(f"  destinations with content scores: {m['destinations_matched']} "
          f"({m['destinations_unmatched']} unmatched -> content-cold items)")
    print(f"  destinations with a weather curve: {m['destinations_with_weather']}")
    print(f"  item features {m['item_feature_count']} ({m['item_cells_imputed']} cells imputed), "
          f"user features {m['user_feature_count']} ({m['user_cells_imputed']} imputed)")
    print(f"  split: {data.split['train_interactions']} train / "
          f"{data.split['test_interactions']} test over {m['evaluable_users']} users; "
          f"{m['cold_start_users']} cold-start users held out of evaluation")

    print()
    print("Most-visited destinations")
    for dest in sorted(data.destinations, key=lambda d: -d["trips"])[:8]:
        scores = "  ".join(
            f"{label} {dest[column]:5.2f}" if isinstance(dest.get(column), (int, float)) else f"{label}    --"
            for label, column in (("unesco", "unesco_score"), ("michelin", "michelin_score"),
                                  ("weather", "weather_mean"))
        )
        print(f"  {dest['destination_key']:36} {dest['trips']:4} trips  "
              f"{dest['travelers']:3} travelers  {scores}")

    if traveler_id:
        print()
        profile = data.traveler(traveler_id)
        print(f"{profile['name']} ({profile['traveler_id']})")
        print(f"  base {profile['base_city']} ({profile['home_airport'] or 'no airport'}), "
              f"{profile['trip_count']} trips to {profile['distinct_destinations']} destinations")
        print(f"  taste  unesco {_fmt(profile['pref_unesco'])}  michelin {_fmt(profile['pref_michelin'])}  "
              f"weather {_fmt(profile['pref_weather'])}  allocentric {_fmt(profile['pref_allocentric'])}")
        print(f"  tags   {', '.join(profile['tag_labels']) or 'none'}")
        held = next((t for t in data.split["test"] if t["traveler_id"] == traveler_id), None)
        print(f"  holdout: {held['destination_key'] if held else 'none (cold start)'}")


def _fmt(value):
    return f"{value:.3f}" if isinstance(value, (int, float)) else "  --"


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="build and report, write nothing")
    parser.add_argument("--traveler", help="also report this traveler_id's prepared inputs")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    data = prepare()
    report(data, traveler_id=args.traveler)

    if args.dry_run:
        print()
        print("--dry-run: nothing written.")
        return

    out = write_outputs(data, out_dir=args.out_dir)
    print()
    for name in sorted(p.name for p in out.glob("*")):
        print(f"Wrote -> {out / name}")


if __name__ == "__main__":
    main()
