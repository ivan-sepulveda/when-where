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

CONCURRENCY, AND WHY IT IS NOT ONE PROCESS PER CORE. Fetching here is pure
network wait -- a worker spends essentially all of its life blocked inside
requests.post -- so the core count is irrelevant and `multiprocessing` would
add pickling and process overhead for nothing. What actually bounds throughput
is the server: overpass-api.de's public instance grants a small number of
concurrent query *slots* per IP (2, as confirmed live via GET /api/status and
recorded in fetch_hiking_trails.py's docstring). Exceeding that doesn't run
more queries, it earns HTTP 429s and backoff, which makes the run slower as
well as being poor citizenship on a donated service.

So fetching uses a bounded *thread* pool, --workers, defaulting to 2 to match
that slot limit. The pool is fed by a single global rate limiter that staggers
request starts by REQUEST_DELAY_SECONDS no matter how many workers are running,
so raising --workers raises how many queries are in flight, never how fast they
are fired. On startup the script reads /api/status and warns if --workers
exceeds the limit the server actually advertises -- if you want to go wider than
2, point OVERPASS_URL at a mirror you host or are entitled to hammer, don't just
raise the number here.

The one genuinely CPU-bound step is --rebuild, which parses every cached
country response. That one does use multiprocessing (--rebuild-workers,
default: all cores), since it's local JSON parsing with no server to be polite
to. pool.map preserves input order and the result is sorted afterward, so the
output is byte-identical to the single-process path.

Rate limiting and retries: a descriptive User-Agent (overpass-api.de returns
HTTP 406 for a default `python-requests` UA), a politeness gap between request
starts, and exponential backoff on 429/504. Two things changed after the first
real run showed ~20 minutes per country:
  - A country that returns 504 (or times out client-side) is retried as four
    separate per-tag queries instead of the single heavy union. That converts
    the common "this country is too big to answer in one go" failure into four
    cheap queries rather than a retry loop that was going to fail again.
  - Every country gets a hard COUNTRY_BUDGET_SECONDS ceiling, so one doomed
    country can no longer burn twenty-odd minutes of a run. It's left uncached
    and picked up by the next run, which costs nothing given the cache.

Resumability: every country's response is cached to
data/raw/osm_zoos_and_gardens/<ISO2>.json and the processed output is rebuilt
from that cache each run, so an interrupted run loses nothing and a rerun
only fetches what's missing. Ctrl-C is handled: in-flight countries are
abandoned, already-cached ones are kept, and the output is still rebuilt from
whatever the cache holds. Use --force to re-fetch countries already cached
(OSM changes daily; a periodic refresh is reasonable).

Cached files are the Overpass payload with one added `_when_where` key
recording when and how it was fetched (combined query vs per-tag split). Only
`elements` is ever read back, so files cached before that key existed parse
identically. A split-fetch payload is a merge of four responses, deduped by
(type, id) -- it is assembled by this script rather than returned verbatim by
Overpass, which is exactly why the key is there to say so. A split is
all-or-nothing: if any of the four tag queries fails the country is left
uncached, because caching three of four tags would silently drop a whole
category for that country and look like a complete result forever after.

NOT RUN AGAINST A LIVE RESPONSE FROM THIS SANDBOX -- overpass-api.de is not
reachable from where this was written (all mirrors time out), same situation
fetch_hiking_trails.py was authored in. The query text and the parsing below
follow Overpass's documented `out center tags;` JSON shape (elements carry
`type`, `id`, `tags`, and either `lat`/`lon` for nodes or `center: {lat, lon}`
for ways/relations) and were verified offline against hand-built mock
responses in that shape, plus a local stub server for the pool, retry, split
and deadline paths. Run --limit 3 first and eyeball the output before a full
run.

Usage:
    python fetch_osm_zoos_and_gardens.py
    python fetch_osm_zoos_and_gardens.py --limit 5        # pilot run, first 5 countries only
    python fetch_osm_zoos_and_gardens.py --workers 2      # concurrent queries (default 2, the slot limit)
    python fetch_osm_zoos_and_gardens.py --force          # re-fetch countries already cached
    python fetch_osm_zoos_and_gardens.py --rebuild        # rebuild the output from cache, no network
    python fetch_osm_zoos_and_gardens.py --rebuild --rebuild-workers 4
"""

import argparse
import json
import multiprocessing
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_STATUS_URL = "https://overpass-api.de/api/status"

# See fetch_hiking_trails.py's REQUEST_HEADERS comment for why a descriptive
# User-Agent is mandatory (a default one gets HTTP 406, deliberately).
REQUEST_HEADERS = {
    "User-Agent": "when-where-data-pipeline/0.1 (https://github.com/ivan-sepulveda/when-where)",
}

# Concurrent in-flight queries. 2 matches overpass-api.de's per-IP slot limit
# (confirmed live via /api/status -- see the docstring's CONCURRENCY section).
# Deliberately NOT os.cpu_count(): this work is network-bound, so cores are
# not the constraint and going wider than the server allows is slower, not
# faster. check_overpass_slots() warns if this exceeds what the server says.
DEFAULT_WORKERS = 2

# Server-side query budget. Was 300; lowered because the per-tag split below
# handles the heavy countries far better than a longer timeout did, and a
# shorter ceiling makes a doomed country fail fast instead of stalling a slot.
QUERY_TIMEOUT_SECONDS = 180

# Minimum gap between the START of any two requests, applied globally across
# all workers by RATE_LIMITER -- not a per-thread sleep. Raising --workers
# therefore raises how many queries overlap, never how fast they are issued.
REQUEST_DELAY_SECONDS = 3.0

# On HTTP 429 (too many requests) or 504 / client-side timeout, wait this long
# before retrying, doubling each attempt. Both were cut (60 -> 30, 3 -> 2)
# once the first real run showed a country could burn ~20 minutes before being
# given up on. The cache makes a give-up cheap: the next run retries it.
RETRY_BACKOFF_SECONDS = 30.0
MAX_RETRIES = 2

# Hard ceiling on total wall-clock spent on one country, across every attempt
# and both the combined and split strategies. Whatever is unfinished when this
# expires is abandoned uncached and retried by a later run.
COUNTRY_BUDGET_SECONDS = 600

# Don't bother issuing a request that has less than this long to run -- with a
# couple of seconds left on a country's budget it can only time out, and the
# slot is better given to the next country.
#
# Clamped to HALF of COUNTRY_BUDGET_SECONDS at the call site, which matters
# more than it looks: a floor at or above the budget refuses to issue even the
# FIRST request (the time remaining is always a hair under the full budget by
# the time it's measured), so a short budget would abort a run instantly
# without a single query going out. Half leaves room for that first attempt at
# any budget while still skipping a pointless dying request at 600s.
MIN_ATTEMPT_SECONDS = 15.0

# Below this many cached files, --rebuild parses inline: spinning up a process
# pool costs more than it saves on a handful of small JSON files.
REBUILD_MIN_FILES_FOR_POOL = 32

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


# ---------------------------------------------------------------------------
# Concurrency plumbing
# ---------------------------------------------------------------------------


class OverpassError(Exception):
    """Base for a country's fetch failing."""


class OverpassOverloaded(OverpassError):
    """HTTP 504, or a client-side read timeout -- the query was too heavy for
    the server to answer in time. This is the one failure worth retrying
    *differently* (as four per-tag queries) rather than just retrying."""


class OverpassUnavailable(OverpassError):
    """Everything else: a non-retryable HTTP status, a connection error,
    exhausted 429 retries, or the per-country budget expiring. Splitting the
    query would not help and, for 429 specifically, would make it worse."""


_PRINT_LOCK = threading.Lock()


def log(message: str) -> None:
    """print() from worker threads interleaves mid-line without this."""
    with _PRINT_LOCK:
        print(message, flush=True)


class RateLimiter:
    """Enforces a minimum gap between the START of any two requests, across
    every worker thread.

    Deliberately not a `time.sleep()` inside each worker: that would let N
    workers each fire immediately and only then pause, so the instantaneous
    rate would scale with --workers, which is the opposite of the point. Here
    each caller claims the next slot under a lock, releases the lock, and then
    sleeps until its own slot comes up -- so the claims serialize but the
    waiting doesn't."""

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._lock = threading.Lock()
        self._next_start = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            due = max(now, self._next_start)
            self._next_start = due + self._min_interval
        delay = due - time.monotonic()
        if delay > 0:
            time.sleep(delay)


RATE_LIMITER = RateLimiter(REQUEST_DELAY_SECONDS)

_THREAD_LOCAL = threading.local()


def session() -> requests.Session:
    """One requests.Session per thread. Sessions aren't documented as
    thread-safe, and a shared one across a pool is a classic source of
    intermittent, unreproducible connection errors -- but a per-thread one
    still gets connection reuse, which matters over a couple hundred
    requests to the same host."""
    existing = getattr(_THREAD_LOCAL, "session", None)
    if existing is None:
        existing = requests.Session()
        existing.headers.update(REQUEST_HEADERS)
        _THREAD_LOCAL.session = existing
    return existing


def check_overpass_slots(workers: int) -> int | None:
    """Reads GET /api/status and warns if `workers` exceeds the concurrent
    slot limit the server advertises for this IP. Returns the limit, or None
    if it couldn't be determined (which is never fatal -- the run proceeds).

    The endpoint returns plain text including a line like `Rate limit: 2`.
    A limit of 0 means no limit, per Overpass's own convention."""
    try:
        resp = requests.get(OVERPASS_STATUS_URL, headers=REQUEST_HEADERS, timeout=30)
        resp.raise_for_status()
        text = resp.text
    except requests.RequestException as exc:
        log(f"Note: couldn't read {OVERPASS_STATUS_URL} ({exc}) -- proceeding with --workers {workers}.")
        return None

    match = re.search(r"Rate limit:\s*(\d+)", text)
    if match is None:
        log(f"Note: no 'Rate limit:' line in {OVERPASS_STATUS_URL} -- proceeding with --workers {workers}.")
        return None

    limit = int(match.group(1))
    if limit == 0:
        log(f"Overpass reports no rate limit for this IP. Proceeding with --workers {workers}.")
        return 0

    if workers > limit:
        log(
            f"WARNING: --workers {workers} exceeds the {limit} concurrent slot(s) overpass-api.de\n"
            f"         grants this IP. The extra queries will queue or take HTTP 429s, so this is\n"
            f"         likely to be SLOWER than --workers {limit}, not faster. Continuing anyway."
        )
    else:
        log(f"Overpass grants {limit} concurrent slot(s) for this IP; using --workers {workers}.")
    return limit


# ---------------------------------------------------------------------------
# Query building and parsing
# ---------------------------------------------------------------------------


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


def build_query(iso2: str, tag_filters: tuple[str, ...] | None = None) -> str:
    """One query per country covering all four tag filters at once, so the
    normal case is one HTTP round trip per country rather than four.

    `tag_filters` narrows it to a subset -- that's the per-tag split used when
    the combined query is too heavy for the server to answer within its
    timeout. Same builder either way so the two paths can't drift apart.

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
    if tag_filters is None:
        tag_filters = tuple(tag_filter for tag_filter, _, _ in TAG_QUERIES)
    filters = "".join(f"nwr{tag_filter}(area.country);" for tag_filter in tag_filters)
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
    label is derived from what the element actually is. It is also what makes
    the per-tag split safe: four responses merged together are classified by
    the same rules as one combined response, so a split fetch and a combined
    fetch of the same country produce the same places."""
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


def merge_payloads(payloads: list[dict]) -> dict:
    """Four per-tag responses -> one payload in the same shape a combined
    query would have returned, deduped by (type, id).

    The dedupe is required, not defensive: an element carrying two of the
    queried tags (a zoo that is also tagged as a botanical garden) comes back
    in two of the four responses, and Overpass's own union would have returned
    it once. Without this, that element would be counted twice downstream."""
    merged_elements: list[dict] = []
    seen: set[tuple] = set()
    for payload in payloads:
        for element in payload.get("elements", []):
            key = (element.get("type"), element.get("id"))
            if key in seen:
                continue
            seen.add(key)
            merged_elements.append(element)

    head = payloads[0] if payloads else {}
    return {
        "version": head.get("version"),
        "generator": head.get("generator"),
        "osm3s": head.get("osm3s"),
        "elements": merged_elements,
    }


def cache_path(iso2: str) -> Path:
    return RAW_DIR / f"{iso2}.json"


def write_cache(iso2: str, payload: dict, mode: str, queries: int) -> None:
    """Writes a country's payload atomically (temp file + os.replace).

    Atomic because workers write concurrently and a run can be Ctrl-C'd
    mid-write: a half-written <ISO2>.json would be treated as cached by the
    next run and blow up --rebuild with a JSONDecodeError, which is a
    genuinely annoying failure to diagnose.

    `_when_where` records how the payload was obtained. Only `elements` is
    ever read back, so the 11 countries cached before this key existed parse
    identically -- but a split payload is assembled here rather than returned
    verbatim by Overpass, and the file should say so."""
    payload = dict(payload)
    payload["_when_where"] = {
        "fetched": date.today().isoformat(),
        "mode": mode,
        "queries": queries,
    }
    target = cache_path(iso2)
    tmp = target.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    os.replace(tmp, target)


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------


def post_overpass(query: str, label: str, deadline: float) -> dict:
    """One Overpass query, with retries, bounded by `deadline` (a
    time.monotonic() value shared across every attempt for a country).

    Raises OverpassOverloaded for 504/read-timeout -- the caller can respond
    by splitting the query. Raises OverpassUnavailable for everything else,
    including exhausted 429 retries: a 429 means "you are asking for too much
    at once", so answering it with four more queries would be exactly wrong."""
    wait = RETRY_BACKOFF_SECONDS
    last_overloaded: OverpassOverloaded | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OverpassUnavailable(f"budget of {COUNTRY_BUDGET_SECONDS}s exhausted before {label}")

        RATE_LIMITER.wait()
        # Never let one request outlive the country's remaining budget, but
        # don't bother issuing one with only seconds left on the clock either.
        # The floor is clamped to the budget so that a deliberately short
        # COUNTRY_BUDGET_SECONDS still gets one real attempt rather than
        # refusing to make any request at all.
        timeout = min(QUERY_TIMEOUT_SECONDS + 30, max(0.0, deadline - time.monotonic()))
        if timeout < min(MIN_ATTEMPT_SECONDS, COUNTRY_BUDGET_SECONDS / 2):
            raise OverpassUnavailable(
                f"only {timeout:.1f}s of the {COUNTRY_BUDGET_SECONDS}s budget left before {label}"
            )

        started = time.monotonic()
        try:
            resp = session().post(OVERPASS_URL, data={"data": query}, timeout=timeout)
            resp.raise_for_status()
            payload = resp.json()
            log(f"    {label}: ok in {time.monotonic() - started:.1f}s")
            return payload
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            elapsed = time.monotonic() - started
            if status == 504:
                last_overloaded = OverpassOverloaded(f"HTTP 504 after {elapsed:.1f}s")
                log(f"    {label}: HTTP 504 after {elapsed:.1f}s (attempt {attempt}/{MAX_RETRIES})")
            elif status == 429:
                log(f"    {label}: HTTP 429 after {elapsed:.1f}s (attempt {attempt}/{MAX_RETRIES})")
                if attempt == MAX_RETRIES:
                    raise OverpassUnavailable(f"HTTP 429 after {MAX_RETRIES} attempts") from exc
            else:
                raise OverpassUnavailable(f"HTTP {status} after {elapsed:.1f}s") from exc
        except requests.Timeout:
            elapsed = time.monotonic() - started
            last_overloaded = OverpassOverloaded(f"client timeout after {elapsed:.1f}s")
            log(f"    {label}: timed out after {elapsed:.1f}s (attempt {attempt}/{MAX_RETRIES})")
        except ValueError as exc:  # json() on a non-JSON body -- usually an Overpass error page
            raise OverpassUnavailable(f"unparseable response: {exc}") from exc
        except requests.RequestException as exc:
            raise OverpassUnavailable(str(exc)) from exc

        if attempt < MAX_RETRIES:
            sleep_for = min(wait, max(0.0, deadline - time.monotonic()))
            if sleep_for > 0:
                time.sleep(sleep_for)
            wait *= 2

    raise last_overloaded or OverpassUnavailable(f"{label} failed after {MAX_RETRIES} attempts")


def fetch_country(iso2: str) -> tuple[dict, str, int] | None:
    """(payload, mode, query_count) for one country, or None if this run
    couldn't get it.

    Returning None rather than an empty payload matters: an empty payload
    would be cached as "this country has nothing," while None leaves it
    uncached so the next run tries again.

    Strategy is combined-query-first, per-tag-split-on-overload. The split is
    ALL-OR-NOTHING -- if any one of the four tag queries fails, the whole
    country returns None. Caching three of four would permanently look like a
    complete result while silently missing an entire category for that
    country, and nothing downstream could tell."""
    deadline = time.monotonic() + COUNTRY_BUDGET_SECONDS

    try:
        return post_overpass(build_query(iso2), f"{iso2} combined", deadline), "combined", 1
    except OverpassOverloaded as exc:
        log(f"    {iso2}: combined query too heavy ({exc}) -- splitting into {len(TAG_QUERIES)} per-tag queries.")
    except OverpassUnavailable as exc:
        log(f"    {iso2}: {exc}. Leaving uncached; a later run will retry it.")
        return None

    payloads: list[dict] = []
    for tag_filter, _, _ in TAG_QUERIES:
        try:
            payloads.append(post_overpass(build_query(iso2, (tag_filter,)), f"{iso2} {tag_filter}", deadline))
        except OverpassError as exc:
            log(
                f"    {iso2}: split query {tag_filter} failed ({exc}). Leaving the WHOLE country "
                f"uncached rather than caching a partial result; a later run will retry it."
            )
            return None

    return merge_payloads(payloads), "split", len(TAG_QUERIES)


def fetch_one(iso2: str, name: str) -> dict:
    """Worker body: fetch one country, cache it, and report. Returns a record
    for the main thread to print, so progress lines stay in completion order
    and don't interleave with each other."""
    started = time.monotonic()
    result = fetch_country(iso2)
    elapsed = time.monotonic() - started

    if result is None:
        return {"iso2": iso2, "name": name, "ok": False, "elapsed": elapsed, "places": 0, "mode": None}

    payload, mode, queries = result
    write_cache(iso2, payload, mode, queries)
    places, _, _ = parse_elements(payload, iso2)
    return {
        "iso2": iso2,
        "name": name,
        "ok": True,
        "elapsed": elapsed,
        "places": len(places),
        "mode": mode,
    }


def fetch_all(limit: int | None = None, force: bool = False, workers: int = DEFAULT_WORKERS,
              rebuild_workers: int | None = None) -> Path:
    country_names = load_country_names()
    codes = sorted(country_names)
    if limit is not None:
        codes = codes[:limit]

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    pending = [c for c in codes if force or not cache_path(c).exists()]
    print(f"{len(codes)} countries requested, {len(codes) - len(pending)} already cached, {len(pending)} to fetch.")

    if not pending:
        return rebuild_output(country_names, workers=rebuild_workers)

    check_overpass_slots(workers)
    print(
        f"Fetching with {workers} concurrent worker(s), >={REQUEST_DELAY_SECONDS}s between request starts, "
        f"{COUNTRY_BUDGET_SECONDS}s budget per country.\n"
    )

    records: list[dict] = []
    failures: list[str] = []
    run_started = time.monotonic()
    interrupted = False

    pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="overpass")
    futures = {pool.submit(fetch_one, iso2, country_names[iso2]): iso2 for iso2 in pending}
    try:
        for done, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            records.append(record)
            if not record["ok"]:
                failures.append(record["iso2"])
                log(f"[{done}/{len(pending)}] {record['iso2']} ({record['name']}) FAILED after {record['elapsed']:.1f}s")
            else:
                suffix = " via per-tag split" if record["mode"] == "split" else ""
                log(
                    f"[{done}/{len(pending)}] {record['iso2']} ({record['name']}) "
                    f"{record['places']} named places in {record['elapsed']:.1f}s{suffix}"
                )
    except KeyboardInterrupt:
        interrupted = True
        print("\nInterrupted -- abandoning in-flight countries. Cached countries are kept.")
        pool.shutdown(wait=False, cancel_futures=True)
    else:
        pool.shutdown(wait=True)

    total_elapsed = time.monotonic() - run_started
    print(f"\nFetched {len(records)} country(ies) in {total_elapsed / 60:.1f} min.")

    succeeded = [r for r in records if r["ok"]]
    if succeeded:
        mean = sum(r["elapsed"] for r in succeeded) / len(succeeded)
        print(f"  mean {mean:.1f}s per country; {sum(1 for r in succeeded if r['mode'] == 'split')} needed a per-tag split.")
        slowest = sorted(succeeded, key=lambda r: r["elapsed"], reverse=True)[:5]
        print("  slowest: " + ", ".join(f"{r['iso2']} {r['elapsed']:.0f}s" for r in slowest))

    if failures:
        print(f"\n{len(failures)} country(ies) failed this run and were NOT cached: {sorted(failures)}")
        print("Re-run (without --force) to retry just those.")

    output = rebuild_output(country_names, workers=rebuild_workers)
    if interrupted:
        raise SystemExit(130)
    return output


# ---------------------------------------------------------------------------
# Rebuild -- the one CPU-bound step, and the one that uses processes
# ---------------------------------------------------------------------------


def parse_cached_file(path_str: str) -> tuple[str, list[dict], int, int]:
    """Reads and parses one cached country file. Module-level and taking/
    returning only plain data because multiprocessing pickles both ends --
    a closure or a Path-keyed dict here would fail under the "spawn" start
    method macOS uses by default."""
    path = Path(path_str)
    iso2 = path.stem
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    places, unnamed, uncoordinated = parse_elements(payload, iso2)
    return iso2, places, unnamed, uncoordinated


def rebuild_output(country_names: dict[str, str], workers: int | None = None) -> Path:
    """Rebuilds OUTPUT_PATH from every cached country response. Separate
    from fetching so a schema/classification change (say, adding a tag to
    TAG_QUERIES that's already in the cached responses) can be applied with
    --rebuild instead of re-querying Overpass for the whole world.

    This is the only genuinely parallelizable-by-core step in the script:
    ~240 JSON files, no network, no server to be polite to. pool.map keeps
    input order and the places are sorted afterward regardless, so the output
    is byte-identical whether one process or eight did the parsing."""
    paths = sorted(RAW_DIR.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No cached country responses in {RAW_DIR} -- run without --rebuild first.")

    if workers is None:
        workers = os.cpu_count() or 1
    workers = max(1, min(workers, len(paths)))

    started = time.monotonic()
    if workers > 1 and len(paths) >= REBUILD_MIN_FILES_FOR_POOL:
        with multiprocessing.Pool(workers) as pool:
            results = pool.map(parse_cached_file, [str(p) for p in paths])
        how = f"{workers} process(es)"
    else:
        results = [parse_cached_file(str(p)) for p in paths]
        how = "1 process"

    places: list[dict] = []
    dropped_unnamed = 0
    dropped_uncoordinated = 0
    countries_cached: list[str] = []

    for iso2, country_places, unnamed, uncoordinated in results:
        places.extend(country_places)
        dropped_unnamed += unnamed
        dropped_uncoordinated += uncoordinated
        countries_cached.append(iso2)

    places.sort(key=lambda p: (p["iso2"], p["category"], p["name"]))

    by_category: dict[str, int] = {}
    for place in places:
        by_category[place["category"]] = by_category.get(place["category"], 0) + 1

    # Set membership, not a scan per country: the old `any(p["iso2"] == iso2
    # for p in places)` inside a loop over countries is O(countries x places),
    # which is fine at 11 cached countries and very much not at 240.
    countries_with_places = {p["iso2"] for p in places}

    payload = {
        "source": (
            "OpenStreetMap via the Overpass API (tourism=zoo, tourism=aquarium, "
            "leisure=garden + garden:type=botanical/arboretum), one query per country, "
            "via fetch_osm_zoos_and_gardens.py -- see data/README.md"
        ),
        "attribution": ATTRIBUTION,
        "generated": date.today().isoformat(),
        "countries_queried": len(countries_cached),
        "countries_with_no_results": sorted(c for c in countries_cached if c not in countries_with_places),
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

    elapsed = time.monotonic() - started
    print(
        f"\nWrote {len(places)} places from {len(countries_cached)} cached countries -> {OUTPUT_PATH}"
        f"  ({how}, {elapsed:.1f}s)"
    )
    for category, count in sorted(by_category.items()):
        print(f"  {category}: {count}")
    print(f"  dropped: {dropped_unnamed} unnamed, {dropped_uncoordinated} without coordinates")
    print(f"  {ATTRIBUTION}")
    return OUTPUT_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N countries (for a pilot run).")
    parser.add_argument("--force", action="store_true", help="Re-fetch countries already cached in data/raw/.")
    parser.add_argument(
        "--workers",
        type=int,
        default=DEFAULT_WORKERS,
        help=(
            f"Concurrent Overpass queries (default {DEFAULT_WORKERS}, matching overpass-api.de's per-IP "
            "slot limit). This is network concurrency, NOT one per core -- going wider than the server "
            "allows earns HTTP 429s and is slower, not faster."
        ),
    )
    parser.add_argument(
        "--rebuild-workers",
        type=int,
        default=None,
        help="Processes used to parse the cached files (default: all cores). This step IS CPU-bound.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Rebuild the processed output from the existing raw cache without making any network requests.",
    )
    args = parser.parse_args()

    if args.workers < 1:
        parser.error("--workers must be at least 1")

    if args.rebuild:
        rebuild_output(load_country_names(), workers=args.rebuild_workers)
        return

    fetch_all(limit=args.limit, force=args.force, workers=args.workers, rebuild_workers=args.rebuild_workers)


if __name__ == "__main__":
    main()
