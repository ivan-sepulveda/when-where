"""
Builds data/processed/multiple/city_attractions.json: for every city in
data/reference/tourist_cities.json, the zoos/aquariums, botanical gardens and
(US-only) art museums within RADIUS_KM, nearest-first with a full count -- the
same "what's actually near this city" treatment build_tourist_cities_enhanced.py
gives UNESCO sites and Michelin restaurants, for the categories behind the city
page's Aquariums/Zoos and Botanical Gardens sections.

Deliberately a separate file from tourist_cities_enhanced.json rather than more
keys inside it. Two reasons: that file is already 27MB and is loaded whole at
API startup, and these two sources refresh on a completely different cadence
(OSM changes daily, IMLS annually) from the UNESCO/Michelin/airport data that
build script joins. Keeping them apart means refreshing attractions doesn't
mean regenerating -- or re-reviewing the diff of -- a 27MB file.

Sources, both optional:
  - data/processed/multiple/osm_zoos_and_gardens.json (fetch_osm_zoos_and_gardens.py)
    -- worldwide zoos, aquariums, botanical gardens, arboretums from OSM.
  - data/processed/multiple/imls_museums.csv (fetch_imls_museums.py) -- US-only
    museum directory; its ZAW discipline feeds zoo_aquarium, BOT feeds
    botanical_garden, and ART feeds art_museum.
Either missing is a warning, not an error -- this runs with whichever it has
(the API and frontend both handle a category being absent), so you can pull OSM
first and add IMLS later without a broken intermediate state. `sources_used` in
the output records which were actually present, so a downstream reader can tell
"no zoos near this city" from "the source with zoos wasn't loaded."

CATEGORIES (deliberately coarser than either source's own taxonomy, since these
map 1:1 onto sections on the city page):
  - zoo_aquarium      -- OSM zoos/aquariums/safari parks + IMLS ZAW
  - botanical_garden  -- OSM botanical gardens/arboretums + IMLS BOT
  - art_museum        -- IMLS ART only. This one is US-only by design: the
    frontend already shows museums from worldwide_museums.json, which covers
    US cities badly (a handful of the largest art museums per country), so
    this fills that specific gap rather than replacing that list. Merging
    happens in the frontend, not here.

Note the two halves of a category aren't equivalent in scope. IMLS's BOT
discipline is "Arboretums, Botanical Gardens, & Nature Centers" while the OSM
half has no nature centers (no clean tag -- see fetch_osm_zoos_and_gardens.py),
so a US city can list a nature center that a European city with the same real
amenities won't. Each entry keeps its own `source` and `kind` so this stays
visible rather than silently blended.

DEDUPLICATION: the two sources overlap completely for US zoos and gardens (the
San Diego Zoo is in both). Two entries in the same category collapse into one
when their names normalize to the same string AND they're within
DEDUPE_RADIUS_KM of each other -- name alone would merge the many distinct
"Botanical Garden"s and "City Zoo"s across the country, and proximity alone
would merge a genuinely separate zoo and aquarium sharing a campus. IMLS wins
ties (curated, official names; OSM's are whatever a mapper typed), which is
also why the source order below is fixed rather than incidental.

Output shape, keyed by simplemaps_id as a string (the same key
tourist_cities_enhanced.json and the API use -- city names aren't unique):
  {"cities": {"1392419823": {"zoo_aquarium": {"count": 4, "places": [
      {"name": ..., "kind": "Zoo", "source": "OpenStreetMap", "distance_km": 8.3}, ...]}, ...}}}
`count` is the true total within RADIUS_KM; `places` is capped at
MAX_PLACES_PER_CATEGORY (the page shows a handful, and an uncapped list would
put hundreds of US art museums on a single New York record). Cities with
nothing in any category are omitted entirely rather than written as three empty
objects -- with OSM coverage what it is, that's most of the 3,069, and omitting
them keeps this file small enough to load at API startup without thinking
about it.

Usage:
    python build_city_attractions.py
    python build_city_attractions.py --radius-km 50   # tighter radius, e.g. to compare
"""

import argparse
import csv
import json
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# Matches CITY_DETAIL_RADIUS_KM in backend/app/data_loader.py and the widest
# radius build_tourist_cities_enhanced.py precomputes, so every "nearby" number
# on a city page means the same thing. Wider than the 50km SCORE_RADIUS_KM that
# feeds scoring on purpose: scoring asks "does this make the city better," this
# asks "could I get there on a day of my trip."
RADIUS_KM = 100

# Per city, per category. See the module docstring.
MAX_PLACES_PER_CATEGORY = 10

# Two same-named places closer than this are treated as one. 5km comfortably
# covers the usual OSM-vs-IMLS disagreement (a zoo's entrance node vs its
# geocoded mailing address) without merging genuinely separate sites.
DEDUPE_RADIUS_KM = 5.0

# IMLS discipline code -> category. Anything not listed is loaded but ignored
# (history, science, children's, ... have no section on the page yet).
IMLS_DISCIPLINE_CATEGORIES = {
    "ZAW": "zoo_aquarium",
    "BOT": "botanical_garden",
    "ART": "art_museum",
}

# Per-entry label shown next to the name for IMLS records. Shorter than
# fetch_imls_museums.py's full DISCIPLINE_LABEL, which spells out the whole
# discipline ("Zoo, Aquarium, or Wildlife Conservation") -- too long to sit
# under every row on a page.
IMLS_KINDS = {
    "ZAW": "Zoo or Aquarium",
    "BOT": "Botanical Garden or Nature Center",
    "ART": "Art Museum",
}

CATEGORIES = ("zoo_aquarium", "botanical_garden", "art_museum")

# Source label written into each entry, and the dedupe precedence order --
# earlier wins. See the module docstring for why IMLS is first.
SOURCE_IMLS = "IMLS"
SOURCE_OSM = "OpenStreetMap"
SOURCE_PRIORITY = (SOURCE_IMLS, SOURCE_OSM)

# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371.0088  # same constant as distance_calculator.py

DATA_DIR = Path(__file__).resolve().parent.parent.parent
REFERENCE_DIR = DATA_DIR / "reference"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
TOURIST_CITIES_PATH = REFERENCE_DIR / "tourist_cities.json"
OSM_PATH = PROCESSED_DIR / "osm_zoos_and_gardens.json"
IMLS_PATH = PROCESSED_DIR / "imls_museums.csv"
OUTPUT_PATH = PROCESSED_DIR / "city_attractions.json"


def load_cities() -> list[dict]:
    """Cities with a usable id and coordinates. Skips the same
    no-simplemaps_id record the API's loaders skip (see
    data_loader.load_static_city_scores) so this file's keys stay joinable
    against everything else keyed by simplemaps_id."""
    if not TOURIST_CITIES_PATH.exists():
        raise FileNotFoundError(f"{TOURIST_CITIES_PATH} not found -- run fetch_tourist_cities.py first.")
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)["cities"]

    return [
        c
        for c in cities
        if c.get("simplemaps_id") is not None and c.get("lat") is not None and c.get("lng") is not None
    ]


def load_osm_places() -> list[dict]:
    """OSM places in this script's internal shape, or [] (with a warning) if
    that source hasn't been fetched yet."""
    if not OSM_PATH.exists():
        print(f"WARNING: {OSM_PATH.name} not found -- skipping OSM. Run fetch_osm_zoos_and_gardens.py for worldwide coverage.")
        return []

    with open(OSM_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    places = [
        {
            "name": p["name"],
            "category": p["category"],
            "kind": p["kind"],
            "source": SOURCE_OSM,
            "lat": float(p["lat"]),
            "lng": float(p["lng"]),
        }
        for p in payload.get("places", [])
        if p.get("category") in CATEGORIES
    ]
    print(f"{OSM_PATH.name}: {len(places)} places")
    return places


def load_imls_places() -> list[dict]:
    """IMLS museums in the same internal shape, filtered to the three
    disciplines that have a category, or [] (with a warning) if that source
    hasn't been fetched yet."""
    if not IMLS_PATH.exists():
        print(f"WARNING: {IMLS_PATH.name} not found -- skipping IMLS. Run fetch_imls_museums.py for US coverage.")
        return []

    places: list[dict] = []
    skipped_unparseable = 0
    with open(IMLS_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            category = IMLS_DISCIPLINE_CATEGORIES.get((row.get("DISCIPLINE") or "").strip().upper())
            if category is None:
                continue
            try:
                lat = float(row["LAT"])
                lng = float(row["LNG"])
            except (TypeError, ValueError):
                skipped_unparseable += 1
                continue
            name = (row.get("NAME") or "").strip()
            if not name:
                continue
            places.append(
                {
                    "name": name,
                    "category": category,
                    "kind": IMLS_KINDS[(row["DISCIPLINE"]).strip().upper()],
                    "source": SOURCE_IMLS,
                    "lat": lat,
                    "lng": lng,
                }
            )

    print(f"{IMLS_PATH.name}: {len(places)} places in scoped disciplines" + (f" ({skipped_unparseable} rows had unparseable coordinates)" if skipped_unparseable else ""))
    return places


def haversine_km(lat1: np.ndarray, lng1: np.ndarray, lat2: float, lng2: float) -> np.ndarray:
    """Vectorized great-circle distance from many points to one, in km --
    same formula and Earth radius as distance_calculator.calculate_distance(),
    reimplemented in numpy for the same reason build_tourist_cities_enhanced.py
    does: this is 3,069 cities x tens of thousands of places, which is far too
    many pairs for a python-level loop."""
    lat1r, lng1r, lat2r, lng2r = np.radians(lat1), np.radians(lng1), np.radians(lat2), np.radians(lng2)
    dlat = lat2r - lat1r
    dlng = lng2r - lng1r
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1r) * np.cos(lat2r) * np.sin(dlng / 2) ** 2
    return EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(a))


def dedupe_key(name: str) -> str:
    """Accent-, case- and punctuation-insensitive form of a place name, e.g.
    both "St. Louis Zoo" and "St Louis Zoo" -> "st louis zoo". Only used for
    the same-place check described in the module docstring, never for
    display."""
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", name) if unicodedata.category(ch) != "Mn"
    )
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in stripped.lower())
    return " ".join(cleaned.split())


def dedupe_nearby(entries: list[dict]) -> list[dict]:
    """Collapses same-name, same-area duplicates within one city's one
    category, keeping the higher-priority source (see SOURCE_PRIORITY) and,
    within a source, the nearer entry. Input is assumed sorted nearest-first;
    output preserves that order.

    O(n^2) in the number of entries for one city/category, which is fine --
    that's typically single digits and bounded well below a hundred even for
    New York's art museums."""
    kept: list[dict] = []
    for entry in entries:
        key = dedupe_key(entry["name"])
        duplicate_of = None
        for i, existing in enumerate(kept):
            if dedupe_key(existing["name"]) != key:
                continue
            gap = haversine_km(
                np.array([existing["lat"]]), np.array([existing["lng"]]), entry["lat"], entry["lng"]
            )[0]
            if gap <= DEDUPE_RADIUS_KM:
                duplicate_of = i
                break

        if duplicate_of is None:
            kept.append(entry)
            continue

        existing = kept[duplicate_of]
        if SOURCE_PRIORITY.index(entry["source"]) < SOURCE_PRIORITY.index(existing["source"]):
            # Same place, better source -- swap in place so the nearest-first
            # ordering of the surviving entry list doesn't change.
            kept[duplicate_of] = entry

    return kept


def build_city_attractions(places: list[dict], cities: list[dict], radius_km: float) -> dict:
    by_category = {category: [p for p in places if p["category"] == category] for category in CATEGORIES}
    coords = {
        category: (
            np.array([p["lat"] for p in items]) if items else np.array([]),
            np.array([p["lng"] for p in items]) if items else np.array([]),
        )
        for category, items in by_category.items()
    }

    result: dict[str, dict] = {}
    for city in cities:
        city_entry: dict[str, dict] = {}

        for category, items in by_category.items():
            if not items:
                continue
            lat, lng = coords[category]
            distances = haversine_km(lat, lng, city["lat"], city["lng"])

            order = np.argsort(distances)
            within = [int(i) for i in order if distances[i] <= radius_km]
            if not within:
                continue

            nearby = [
                {
                    "name": items[i]["name"],
                    "kind": items[i]["kind"],
                    "source": items[i]["source"],
                    "lat": items[i]["lat"],
                    "lng": items[i]["lng"],
                    "distance_km": round(float(distances[i]), 1),
                }
                for i in within
            ]
            deduped = dedupe_nearby(nearby)

            city_entry[category] = {
                # The count AFTER dedupe -- showing a raw count that includes
                # a place listed twice would make the headline number disagree
                # with the list under it for no good reason.
                "count": len(deduped),
                "places": [
                    {k: v for k, v in place.items() if k not in ("lat", "lng")}
                    for place in deduped[:MAX_PLACES_PER_CATEGORY]
                ],
            }

        if city_entry:
            result[str(city["simplemaps_id"])] = city_entry

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--radius-km", type=float, default=RADIUS_KM, help=f"Radius to search around each city (default {RADIUS_KM})."
    )
    args = parser.parse_args()

    cities = load_cities()
    osm_places = load_osm_places()
    imls_places = load_imls_places()
    places = imls_places + osm_places  # IMLS first -- dedupe_nearby() prefers whichever it sees as higher priority
    if not places:
        raise SystemExit(
            "Neither source is available -- run fetch_osm_zoos_and_gardens.py and/or fetch_imls_museums.py first."
        )

    print(f"\nJoining {len(places)} places against {len(cities)} cities within {args.radius_km}km ...")
    city_attractions = build_city_attractions(places, cities, args.radius_km)

    totals = {category: 0 for category in CATEGORIES}
    for entry in city_attractions.values():
        for category, payload in entry.items():
            totals[category] += payload["count"]

    payload = {
        "source": (
            "OpenStreetMap (via fetch_osm_zoos_and_gardens.py) and the IMLS Museum Data Files "
            "(via fetch_imls_museums.py), joined against data/reference/tourist_cities.json by "
            "great-circle distance -- see build_city_attractions.py and data/README.md"
        ),
        "generated": date.today().isoformat(),
        "radius_km": args.radius_km,
        "max_places_per_category": MAX_PLACES_PER_CATEGORY,
        "categories": list(CATEGORIES),
        # Lets a reader tell "nothing near this city" from "the source that
        # would have had it wasn't loaded when this was built."
        "sources_used": {
            "openstreetmap": bool(osm_places),
            "imls": bool(imls_places),
        },
        "note": (
            "art_museum is US-only (IMLS); the frontend merges it with "
            "worldwide_museums.json. zoo_aquarium and botanical_garden are worldwide via OSM, "
            "enriched with IMLS in the US. Counts are post-deduplication. Cities with nothing in "
            "any category are omitted entirely."
        ),
        "cities_with_attractions": len(city_attractions),
        "total_places_by_category": totals,
        "cities": city_attractions,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    size_mb = OUTPUT_PATH.stat().st_size / 1_000_000
    print(f"\nWrote {len(city_attractions)} cities ({size_mb:.1f}MB) -> {OUTPUT_PATH}")
    for category, total in totals.items():
        print(f"  {category}: {total} city-place pairs")


if __name__ == "__main__":
    main()
