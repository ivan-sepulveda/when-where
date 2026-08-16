"""
Data Source: OpenStreetMap, via the Overpass API (overpass-api.de, free, no API key)
URL: https://overpass-api.de/api/interpreter -- see https://wiki.openstreetmap.org/wiki/Overpass_API
Tables Referenced: n/a (a live query, not a bulk export) -- one Overpass QL query
    per country, pulling every zoo, aquarium, botanical garden and arboretum
    inside that country's `admin_level=2` boundary, with coordinates.

Writes data/processed/multiple/osm_zoos_and_gardens.json: a flat, worldwide
list of {name, category, kind, iso2, lat, lng, osm_type, osm_id}, which
build_city_attractions.py then joins against every city by distance -- the
same "compute what's actually within N km of this city" treatment
build_tourist_cities_enhanced.py already gives UNESCO sites and Michelin
restaurants.

WHY THIS EXISTS ALONGSIDE fetch_imls_museums.py: IMLS has richer, curated,
public-domain records for exactly these categories -- but only for the United
States. Since every city currently in this project's top 10 is outside the US,
a US-only source would leave the city page's new Aquariums/Zoos and Botanical
Gardens sections empty for essentially every destination anyone looks at. OSM
is the only free source with worldwide coverage of these specific categories,
so the two are merged downstream (build_city_attractions.py), with IMLS
preferred where both describe the same place.

Unlike fetch_hiking_trails.py -- the other Overpass script here, which asks
only for `out count;` and stores a single number per country -- this one needs
each element's name and position, so it uses `out center tags;`. `center` is
what makes ways and relations (a zoo is usually mapped as an area, not a
point) come back with a single representative lat/lng instead of a member list,
so all three OSM element types can be handled identically.

Tags queried, and why these:
  - tourism=zoo -- the canonical zoo tag, and the one safari parks, petting
    zoos and wildlife parks also carry (they differ only by a `zoo=*`
    subtype, which is read below to label them).
  - tourism=aquarium -- public aquariums. (Not `shop=pet`, obviously, and
    not `amenity=fountain`.)
  - leisure=garden + garden:type=botanical -- botanical gardens. The bare
    `leisure=garden` tag is NOT queried: it covers every residential back
    garden and planted traffic island in OSM, millions of them, virtually
    none of which is a destination.
  - leisure=garden + garden:type=arboretum -- arboretums, grouped with
    botanical gardens to match IMLS's own BOT discipline, which bundles
    them ("Arboretums, Botanical Gardens, & Nature Centers").
Nature centers have no clean OSM equivalent (they scatter across
tourism=attraction, amenity=community_centre and leisure=nature_reserve, the
last of which would sweep in thousands of uninhabited reserves), so unlike
IMLS's BOT bundle, the OSM half of that category is botanical gardens and
arboretums only. A US city may therefore list a nature center from IMLS that
an equivalent European city won't -- noted in data/README.md rather than
papered over.

Unnamed elements are dropped: a nameless zoo polygon can't be displayed as a
list entry, and OSM has plenty of them (mapped geometry, missing tags). The
count dropped is reported per run and stored in the output.

Caveats worth knowing before trusting this:
  - Coverage is a mapping-effort proxy. OSM's density varies enormously by
    region, so a low count is "not mapped much here" at least as often as
    "not much here" -- the same caveat fetch_hiking_trails.py carries, and
    the reason this project treats a 0 as "nothing found," not "nothing
    exists."
  - Tagging is inconsistent at the edges: some aquariums are tagged only as
    tourism=attraction, some botanical gardens omit garden:type entirely.
    Those are missed here. Widening the query to catch them costs far more
    false positives than it gains real entries.
  - A single large site can appear more than once (e.g. a zoo mapped as both
    a node and an enclosing way, or a botanical garden split into named
    sections). build_city_attractions.py dedupes by name + proximity, which
    catches most but not all of this.
  - License: OpenStreetMap data is ODbL (Open Database License) -- share-alike
    in addition to attribution, unlike this project's CC BY / public domain
    sources. Same unresolved posture as fetch_hiking_trails.py: flag before
    this goes beyond personal/internal use. See data/README.md.

Rate limiting: same etiquette as fetch_hiking_trails.py -- one query at a
time, never concurrent, a politeness delay between countries, a descriptive
User-Agent (overpass-api.de returns HTTP 406 for a default `python-requests`
UA), and exponential backoff on 429/504. These queries are heavier than that
script's count-only ones, so expect 504s on large, densely-mapped countries;
they're retried, and a country that still fails is simply left uncached and
picked up on the next run.

Resumability: every country's raw response is cached to
data/raw/osm_zoos_and_gardens/<ISO2>.json and the processed output is rebuilt
from that cache each run, so an interrupted run loses nothing and a rerun
only fetches what's missing. Use --force to re-fetch countries already
cached (OSM changes daily; a periodic refresh is reasonable).

NOT RUN AGAINST A LIVE RESPONSE FROM THIS SANDBOX -- overpass-api.de is not
reachable from where this was written (all mirrors time out), same situation
fetch_hiking_trails.py was authored in. The query text and the parsing below
follow Overpass's documented `out center tags;` JSON shape (elements carry
`type`, `id`, `tags`, and either `lat`/`lon` for nodes or `center: {lat, lon}`
for ways/relations) and were verified offline against hand-built mock
responses in that shape. Run --limit 3 first and eyeball the output before a
full run.

Usage:
    python fetch_osm_zoos_and_gardens.py
    python fetch_osm_zoos_and_gardens.py --limit 5   # pilot run, first 5 countries only
    python fetch_osm_zoos_and_gardens.py --force     # re-fetch countries already cached
    python fetch_osm_zoos_and_gardens.py --rebuild   # rebuild the output from cache, no network
"""

import argparse
import json
import time
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# See fetch_hiking_trails.py's REQUEST_HEADERS comment for why a descriptive
# User-Agent is mandatory (a default one gets HTTP 406, deliberately).
REQUEST_HEADERS = {
    "User-Agent": "when-where-data-pipeline/0.1 (https://github.com/ivan-sepulveda/when-where)",
}

# Higher than fetch_hiking_trails.py's 180 -- that script asks for a count,
# this one asks for elements with geometry centers, which is a heavier query
# on countries with dense OSM coverage (DE, FR, US).
QUERY_TIMEOUT_SECONDS = 300

REQUEST_DELAY_SECONDS = 3.0
RETRY_BACKOFF_SECONDS = 60.0
MAX_RETRIES = 3

# OSM tag filter -> (category, default kind label). `category` is what the
# city page groups by; `kind` is the per-entry label shown next to the name,
# refined further by KIND_BY_ZOO_SUBTYPE below for zoos.
TAG_QUERIES = (
    ('["tourism"="zoo"]', "zoo_aquarium", "Zoo"),
    ('["tourism"="aquarium"]', "zoo_aquarium", "Aquarium"),
    ('["leisure"="garden"]["garden:type"="botanical"]', "botanical_garden", "Botanical Garden"),
    ('["leisure"="garden"]["garden:type"="arboretum"]', "botanical_garden", "Arboretum"),
)

# OSM's `zoo=*` subtype -> a more specific label than plain "Zoo". Anything
# not listed (including no zoo=* tag at all, the common case) keeps the
# default from TAG_QUERIES.
KIND_BY_ZOO_SUBTYPE = {
    "petting_zoo": "Petting Zoo",
    "safari_park": "Safari Park",
    "wildlife_park": "Wildlife Park",
    "aviary": "Aviary",
    "birds": "Aviary",
    "aquarium": "Aquarium",
}

# Same two gaps fetch_hiking_trails.py, compute_michelin_score.py and
# compute_unesco_score.py all patch -- see any of them for the full
# explanation.
ISO2_OVERRIDES = {
    "NA": "Namibia",
    "PS": "Palestine",
}

ATTRIBUTION = (
    "OpenStreetMap contributors, via the Overpass API -- "
    "https://wiki.openstreetmap.org/wiki/Overpass_API -- ODbL licensed, see data/README.md"
)

# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent
REFERENCE_DIR = DATA_DIR / "reference"
RAW_DIR = DATA_DIR / "raw" / "osm_zoos_and_gardens"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
COUNTRY_ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
OUTPUT_PATH = PROCESSED_DIR / "osm_zoos_and_gardens.json"


def load_country_names() -> dict[str, str]:
    """iso2 -> canonical name, from country_aliases.json plus ISO2_OVERRIDES.
    Same function (and same deliberate duplication rather than sharing) as
    fetch_hiking_trails.py's -- this project keeps its data scripts
    self-contained."""
    if not COUNTRY_ALIASES_PATH.exists():
        raise FileNotFoundError(f"{COUNTRY_ALIASES_PATH} not found -- run build_country_aliases.py first.")
    with open(COUNTRY_ALIASES_PATH, encoding="utf-8") as f:
        data = json.load(f)

    names: dict[str, str] = {}
    for entry in data["countries"].values():
        iso2 = entry.get("iso2")
        if isinstance(iso2, str) and iso2:
            names[iso2] = entry["canonical_name"]

    for iso2, name in ISO2_OVERRIDES.items():
        names.setdefault(iso2, name)

    return names


def build_query(iso2: str) -> str:
    """One query per country covering all four tag filters at once, so this
    is one HTTP round trip per country rather than four.

    `nwr` matches nodes, ways and relations together -- a zoo may be mapped
    as any of the three. `out center tags;` gives ways/relations a single
    representative coordinate (`center`) instead of their full member
    geometry, which is both far smaller to transfer and directly usable as
    "where is this place."

    No separate area-existence check like fetch_hiking_trails.py does: that
    script needs to distinguish "no OSM boundary" (unknown, blank) from "a
    real 0", because a count of 0 is its whole output. Here, a country whose
    boundary doesn't resolve simply contributes no elements, which is
    already indistinguishable from "none mapped" in a flat list of places --
    so the extra count block would buy nothing."""
    filters = "".join(f"nwr{tag_filter}(area.country);" for tag_filter, _, _ in TAG_QUERIES)
    return (
        f"[out:json][timeout:{QUERY_TIMEOUT_SECONDS}];"
        f'area["ISO3166-1"="{iso2}"][admin_level=2]->.country;'
        f"({filters});"
        "out center tags;"
    )


def classify(tags: dict) -> tuple[str, str] | None:
    """OSM tags -> (category, kind), or None for an element that matches no
    TAG_QUERIES filter. Checked in TAG_QUERIES order, which matters for the
    rare element carrying more than one of these tags (a botanical garden
    inside a zoo, tagged as both): first match wins, so it's filed under the
    zoo rather than duplicated into both sections.

    Kept as an explicit re-check of the returned tags rather than trusting
    the query to only return matching elements -- Overpass unions can return
    an element once even when it matches several branches, and this way the
    label is derived from what the element actually is."""
    tourism = tags.get("tourism")
    leisure = tags.get("leisure")
    garden_type = tags.get("garden:type")

    if tourism == "zoo":
        subtype = (tags.get("zoo") or "").strip().lower()
        return "zoo_aquarium", KIND_BY_ZOO_SUBTYPE.get(subtype, "Zoo")
    if tourism == "aquarium":
        return "zoo_aquarium", "Aquarium"
    if leisure == "garden" and garden_type == "botanical":
        return "botanical_garden", "Botanical Garden"
    if leisure == "garden" and garden_type == "arboretum":
        return "botanical_garden", "Arboretum"
    return None


def element_coordinates(element: dict) -> tuple[float, float] | None:
    """(lat, lng) for a node (top-level lat/lon) or a way/relation
    (`center`, present because the query asks for `out center`). None if
    neither is there -- possible for a relation whose members Overpass
    couldn't resolve into a center."""
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None


def parse_elements(payload: dict, iso2: str) -> tuple[list[dict], int, int]:
    """(places, dropped_unnamed, dropped_uncoordinated) for one country's
    response. `name` is preferred over `name:en` deliberately -- the local
    name is what signage and maps use -- with `name:en` as the fallback for
    an element that only has one."""
    places: list[dict] = []
    dropped_unnamed = 0
    dropped_uncoordinated = 0

    for element in payload.get("elements", []):
        tags = element.get("tags") or {}
        classified = classify(tags)
        if classified is None:
            continue
        category, kind = classified

        name = (tags.get("name") or tags.get("name:en") or "").strip()
        if not name:
            dropped_unnamed += 1
            continue

        coordinates = element_coordinates(element)
        if coordinates is None:
            dropped_uncoordinated += 1
            continue

        lat, lng = coordinates
        places.append(
            {
                "name": name,
                "category": category,
                "kind": kind,
                "iso2": iso2,
                "lat": round(lat, 5),  # ~1m precision; full float precision is noise for a 100km join
                "lng": round(lng, 5),
                "osm_type": element.get("type", ""),
                "osm_id": element.get("id"),
            }
        )

    return places, dropped_unnamed, dropped_uncoordinated


def cache_path(iso2: str) -> Path:
    return RAW_DIR / f"{iso2}.json"


def fetch_country(iso2: str) -> dict | None:
    """The raw Overpass payload for one country, or None if this run
    couldn't get it (non-retryable HTTP error, or retries exhausted).
    Returning None rather than an empty payload matters: an empty payload
    would be cached as "this country has nothing," while None leaves it
    uncached so the next run tries again."""
    query = build_query(iso2)
    wait = RETRY_BACKOFF_SECONDS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                OVERPASS_URL, data={"data": query}, headers=REQUEST_HEADERS, timeout=QUERY_TIMEOUT_SECONDS + 30
            )
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status not in (429, 504):
                print(f"  FAILED ({iso2}, HTTP {status}): {exc}. Skipping.")
                return None
            if attempt == MAX_RETRIES:
                print(f"  Still HTTP {status} for {iso2} after {MAX_RETRIES} retries -- skipping this run.")
                return None
            print(f"  HTTP {status} for {iso2} -- waiting {wait:.0f}s before retry {attempt}/{MAX_RETRIES}...")
            time.sleep(wait)
            wait *= 2
        except requests.RequestException as exc:
            print(f"  FAILED ({iso2}): {exc}. Skipping.")
            return None

    return None  # unreachable


def rebuild_output(country_names: dict[str, str]) -> Path:
    """Rebuilds OUTPUT_PATH from every cached country response. Separate
    from fetching so a schema/classification change (say, adding a tag to
    TAG_QUERIES that's already in the cached responses) can be applied with
    --rebuild instead of re-querying Overpass for the whole world."""
    places: list[dict] = []
    dropped_unnamed = 0
    dropped_uncoordinated = 0
    countries_cached = []

    for path in sorted(RAW_DIR.glob("*.json")):
        iso2 = path.stem
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        country_places, unnamed, uncoordinated = parse_elements(payload, iso2)
        places.extend(country_places)
        dropped_unnamed += unnamed
        dropped_uncoordinated += uncoordinated
        countries_cached.append(iso2)

    places.sort(key=lambda p: (p["iso2"], p["category"], p["name"]))

    by_category: dict[str, int] = {}
    for place in places:
        by_category[place["category"]] = by_category.get(place["category"], 0) + 1

    payload = {
        "source": (
            "OpenStreetMap via the Overpass API (tourism=zoo, tourism=aquarium, "
            "leisure=garden + garden:type=botanical/arboretum), one query per country, "
            "via fetch_osm_zoos_and_gardens.py -- see data/README.md"
        ),
        "attribution": ATTRIBUTION,
        "generated": date.today().isoformat(),
        "countries_queried": len(countries_cached),
        "countries_with_no_results": sorted(
            iso2 for iso2 in countries_cached if not any(p["iso2"] == iso2 for p in places)
        ),
        "total_places": len(places),
        "places_by_category": by_category,
        "dropped_unnamed": dropped_unnamed,
        "dropped_missing_coordinates": dropped_uncoordinated,
        "note": (
            "Coverage reflects OSM mapping density, not just what exists on the ground -- a low "
            "count in a region is often under-mapping. Nature centers are NOT included (no clean "
            "OSM tag); IMLS's BOT discipline does include them, so US cities may list nature "
            "centers that comparable cities elsewhere won't. See fetch_osm_zoos_and_gardens.py."
        ),
        "places": places,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\nWrote {len(places)} places from {len(countries_cached)} cached countries -> {OUTPUT_PATH}")
    for category, count in sorted(by_category.items()):
        print(f"  {category}: {count}")
    print(f"  dropped: {dropped_unnamed} unnamed, {dropped_uncoordinated} without coordinates")
    print(f"  {ATTRIBUTION}")
    return OUTPUT_PATH


def fetch_all(limit: int | None = None, force: bool = False) -> Path:
    country_names = load_country_names()
    codes = sorted(country_names)
    if limit is not None:
        codes = codes[:limit]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pending = [c for c in codes if force or not cache_path(c).exists()]
    print(f"{len(codes)} countries requested, {len(codes) - len(pending)} already cached, {len(pending)} to fetch.")

    failures = []
    for i, iso2 in enumerate(pending, start=1):
        print(f"[{i}/{len(pending)}] {iso2} ({country_names[iso2]}) ...")
        payload = fetch_country(iso2)
        if payload is None:
            failures.append(iso2)
        else:
            # Written per country, immediately -- this is the checkpoint
            # that makes an interrupted run cost nothing.
            with open(cache_path(iso2), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            places, _, _ = parse_elements(payload, iso2)
            print(f"  {len(places)} named places cached.")
        time.sleep(REQUEST_DELAY_SECONDS)

    if failures:
        print(f"\n{len(failures)} country(ies) failed this run and were NOT cached: {failures}")
        print("Re-run (without --force) to retry just those.")

    return rebuild_output(country_names)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N countries (for a pilot run).")
    parser.add_argument("--force", action="store_true", help="Re-fetch countries already cached in data/raw/.")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the processed output from the existing raw cache without making any network requests.",
    )
    args = parser.parse_args()

    if args.rebuild:
        rebuild_output(load_country_names())
        return

    fetch_all(limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()
