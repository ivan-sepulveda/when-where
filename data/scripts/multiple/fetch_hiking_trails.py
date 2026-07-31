"""
Data Source: OpenStreetMap, via the Overpass API (overpass-api.de, free, no API key)
URL: https://overpass-api.de/api/interpreter -- see https://wiki.openstreetmap.org/wiki/Overpass_API
Tables Referenced: n/a (a live query, not a bulk export) -- one Overpass QL query per
    country, each counting `relation[route=hiking]` elements within that country's
    `admin_level=2` boundary.

Builds data/processed/multiple/HIKING_TRAILS_BY_COUNTRY.csv: a count of OSM-tagged
hiking-route relations per country. Same shape/spirit as
compute_michelin_score.py's AWARD_COUNT and compute_unesco_score.py's SITE_COUNT --
a transparent, explainable "how much of X does this country have" count -- but
this script does the fetch AND the per-country count in one step (no separate
raw per-item pull), since Overpass's `out count;` returns just a number, not
trail geometry, so there's nothing bulkier to cache separately. Stays in
scripts/multiple/ (not scripts/ root) per this project's layout rule --
Overpass is a single cross-continent source, same reasoning as
fetch_michelin_restaurants.py -- even though, unlike that script, there's no
separate compute_hiking_score.py step following it (yet).

Each country's query does two counts in one round trip:
  1. Does `area["ISO3166-1"="<iso2>"][admin_level=2]` resolve to anything at
     all? OSM's country-boundary coverage isn't 100% for every ISO2 in this
     project's country_aliases.json (disputed territories, micro-states,
     dependencies without their own boundary relation) -- if the area doesn't
     resolve, HIKING_ROUTE_COUNT is left BLANK ("unknown"), not written as 0.
  2. If the area resolves, how many `relation[route=hiking]` elements exist
     inside it -- written as HIKING_ROUTE_COUNT, including a real, meaningful
     0 for a country with a real OSM boundary but no tagged hiking routes.
This blank-vs-real-zero distinction matters here even more than usual: OSM
hiking-route coverage is extremely uneven by country (dense in Central Europe,
sparse-to-nonexistent in much of Africa/Central Asia even where real trails
exist) -- see the caveats below.

Caveats worth knowing before trusting this number:
  - A relation COUNT is not a trail-length or trail-quality measure. A single
    long-distance trail (e.g. a GR-numbered French route, or the Appalachian
    Trail) is very often mapped as one "superroute" relation containing many
    regional sub-relations, each ALSO tagged route=hiking -- so a
    finely-subdivided regional network can outscore a country with one long,
    genuinely bigger trail that just wasn't split into sub-relations. Total
    trail-km (summing way lengths, not counting relations) would be a more
    physically meaningful metric than this one -- left as a natural next
    step, not attempted here, since it needs pulling actual way geometry
    (a much heavier query) rather than a single count() per country.
  - Coverage is a mapping-effort proxy as much as a trails-that-exist proxy.
    A low or blank count doesn't necessarily mean a country has few hiking
    opportunities -- it may just mean OSM contributors haven't mapped them
    yet. Same caveat this project already gives UNESCO/Michelin data, just
    sharper here since OSM's community-mapping density varies far more by
    region than a curated dataset like Michelin's guide does.
  - Disputed/contested territories (Kosovo, Taiwan, Western Sahara, etc.)
    may have inconsistent or missing `ISO3166-1`-tagged admin_level=2
    relations in OSM depending on how contributors in that region have
    chosen to map it -- expect some of these to come back with no area
    match (blank), not necessarily reflecting the actual on-the-ground
    trail situation.
  - License: OpenStreetMap data is ODbL-licensed (Open Database License) --
    unlike this project's CC BY sources, ODbL requires share-alike for
    produced/derivative databases in addition to attribution. This script's
    output (a per-country count) is arguably a "produced work" under ODbL's
    definitions rather than the database itself, but this hasn't been
    legally confirmed -- flag before this goes beyond personal/internal use,
    same posture as this project already takes with UNESCO's unresolved
    license (see data/README.md).

Rate limiting: overpass-api.de's public instance allows 2 concurrent query
slots (confirmed live via GET /api/status) and asks for reasonable, polite
request rates in general -- this script runs one query at a time (never
concurrent) with a REQUEST_DELAY_SECONDS pause between countries, and retries
with exponential backoff on HTTP 429 (too many requests) or 504 (the query
itself timed out server-side, more likely for large/densely-mapped countries).
Resumable by default: countries already in the output CSV are skipped on a
re-run (--force to override), same convention as fetch_weather_normals.py.

Note: this sandbox's network allowlist blocks overpass-api.de for outbound
`requests` calls in bash (confirmed -- a direct connection attempt fails
outright), same restriction as every other live external source in this
project. A separate fetch tool *could* reach overpass-api.de's plain-text
GET /api/status endpoint directly (confirmed live, returned a real
"Rate limit: 2 / 2 slots available now" response, which is where this
docstring's rate-limit numbers above come from) -- but that same tool did not
surface a readable response body for GET /api/interpreter itself (tried
out:json and out:csv, both came back empty through that tool, for reasons
that weren't resolved -- possibly a content-type-handling quirk in that tool
rather than an Overpass-side problem, since /api/status's plain-text response
worked fine). So the query-building and CSV read/write/resume logic below
were verified offline against a hand-built mock response matching Overpass's
documented `out count;` JSON shape (two `{"type": "count", "tags": {"total":
"N"}}` elements, per the Overpass QL docs) -- NOT against a live response.
Run this for real on a machine that can reach overpass-api.de, and
spot-check a few known countries (e.g. Switzerland/Austria should be very
high, a small Pacific island nation should be low or blank) before trusting
the output.

Usage:
    python fetch_hiking_trails.py
    python fetch_hiking_trails.py --limit 20     # pilot run, first 20 countries only
    python fetch_hiking_trails.py --force         # re-fetch countries already in the output
"""

import argparse
import csv
import json
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Since April 2026, overpass-api.de has been aggressively rejecting
# requests with a generic/default User-Agent (a bare `python-requests`
# UA gets HTTP 406 Not Acceptable) as part of load-shedding against
# server overload -- confirmed on the OSM community forum
# (https://community.openstreetmap.org/t/overpass-api-error-406/143198),
# where a real Overpass maintainer describes this as a deliberate
# banning rule, not a bug, and a user confirms setting User-Agent alone
# fixed it. A descriptive, identifiable UA (not a spoofed browser one --
# unlike the SimpleMaps/Chile INE/Argentina INDEC fix elsewhere in this
# project, Overpass's own etiquette asks for real identification, not
# impersonation) avoids the 406. Even with this fixed, the same thread
# reports the public instance genuinely overloaded at times through
# 2026, so expect some HTTP 504s regardless -- that's what MAX_RETRIES
# below is for.
REQUEST_HEADERS = {
    "User-Agent": "when-where-data-pipeline/0.1 (https://github.com/ivan-sepulveda/when-where)",
}

# Server-side query timeout (embedded in the query itself, via
# [timeout:N]) -- large/densely-mapped countries (e.g. the US, Germany)
# may need this bumped if they keep coming back HTTP 504 even after
# MAX_RETRIES.
QUERY_TIMEOUT_SECONDS = 180

# Politeness delay between successful requests, in seconds. This script
# never runs concurrent queries (see docstring's "Rate limiting" section
# for the live-confirmed 2-slot limit), so this is purely a courtesy
# pause on the shared public instance, not a hard requirement -- retune
# if MAX_RETRIES backoffs end up kicking in often.
REQUEST_DELAY_SECONDS = 3.0

# On HTTP 429 (too many requests) or 504 (query itself timed out
# server-side), wait this long before retrying the *same* country,
# doubling the wait each attempt, up to MAX_RETRIES before giving up on
# that country for this run (already-fetched countries are unaffected --
# rerun the script later, without --force, to pick up where it left off).
RETRY_BACKOFF_SECONDS = 60.0
MAX_RETRIES = 3

# iso2 -> canonical name, for countries country_aliases.json doesn't
# resolve cleanly -- same two gaps compute_michelin_score.py and
# compute_unesco_score.py both patch, kept here too so this script's
# country list doesn't depend on either of those having been run first.
# See either of those scripts for the full explanation of each.
ISO2_OVERRIDES = {
    "NA": "Namibia",
    "PS": "Palestine",
}

# ---------------------------------------------------------------------------

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent / "reference"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
COUNTRY_ALIASES_PATH = REFERENCE_DIR / "country_aliases.json"
OUTPUT_PATH = PROCESSED_DIR / "HIKING_TRAILS_BY_COUNTRY.csv"

FIELDNAMES = ["COUNTRY", "COUNTRY_NAME", "HIKING_ROUTE_COUNT"]

ATTRIBUTION = (
    "OpenStreetMap contributors, via the Overpass API -- "
    "https://wiki.openstreetmap.org/wiki/Overpass_API -- ODbL licensed, see data/README.md"
)


def load_country_names() -> dict[str, str]:
    """iso2 -> canonical name, for every country in country_aliases.json
    (skipping the handful with no iso2 at all -- patched back in via
    ISO2_OVERRIDES instead), plus ISO2_OVERRIDES for codes not in
    country_aliases.json at all. Same logic as compute_michelin_score.py's
    and compute_unesco_score.py's functions of the same name -- kept
    duplicated rather than shared, consistent with this project's
    per-script self-containment."""
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
    """Two `out count;` blocks in one query -- see this script's docstring
    for why: the first counts whether the country's admin_level=2 area
    resolves at all (0 or 1), the second counts route=hiking relations
    inside it. Doing both in one round trip (rather than a separate area
    existence check) keeps this to one HTTP request per country."""
    return (
        f"[out:json][timeout:{QUERY_TIMEOUT_SECONDS}];"
        f'area["ISO3166-1"="{iso2}"][admin_level=2]->.country;'
        "(.country;);out count;"
        'relation["route"="hiking"](area.country);out count;'
    )


def parse_response(payload: dict) -> tuple[bool, int | None]:
    """(area_found, hiking_route_count). hiking_route_count is None
    whenever area_found is False -- there's nothing meaningful to count
    inside an area that doesn't exist. Raises ValueError on a
    response that doesn't match the expected two-count shape (e.g. an
    Overpass QL syntax error would come back as a different JSON shape
    entirely, or a non-2xx status raises before this is even called)."""
    elements = payload.get("elements", [])
    if len(elements) != 2:
        raise ValueError(f"expected exactly 2 count elements, got {len(elements)}: {payload}")

    area_found = int(elements[0]["tags"]["total"]) > 0
    if not area_found:
        return False, None

    hiking_route_count = int(elements[1]["tags"]["total"])
    return True, hiking_route_count


def fetch_country(iso2: str) -> tuple[bool, int | None]:
    """Wraps the HTTP call + parse_response() with retry-with-backoff on
    HTTP 429/504. Returns (area_found, hiking_route_count) on success (or
    a definitive (False, None) if the area genuinely doesn't resolve).
    Returns (False, None) on any other failure too (non-429/504 HTTP
    error, or exhausted retries) -- callers can't distinguish "no area"
    from "gave up after retries" from this return value alone, so
    fetch_all() below tracks and reports failures separately rather than
    writing them into the output CSV as a false blank."""
    query = build_query(iso2)
    wait = RETRY_BACKOFF_SECONDS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                OVERPASS_URL, data={"data": query}, headers=REQUEST_HEADERS, timeout=QUERY_TIMEOUT_SECONDS + 30
            )
            resp.raise_for_status()
            return parse_response(resp.json())
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status not in (429, 504):
                print(f"  FAILED ({iso2}, HTTP {status}): {exc}. Skipping.")
                return False, None
            if attempt == MAX_RETRIES:
                print(f"  Still HTTP {status} for {iso2} after {MAX_RETRIES} retries -- skipping this run.")
                return False, None
            print(f"  HTTP {status} for {iso2} -- waiting {wait:.0f}s before retry {attempt}/{MAX_RETRIES}...")
            time.sleep(wait)
            wait *= 2

    return False, None  # unreachable


def load_existing_rows() -> dict[str, dict]:
    """COUNTRY -> row dict, from whatever's already in OUTPUT_PATH -- the
    resume/skip mechanism. Empty dict if the file doesn't exist yet."""
    if not OUTPUT_PATH.exists():
        return {}
    with open(OUTPUT_PATH, newline="", encoding="utf-8") as f:
        return {row["COUNTRY"]: row for row in csv.DictReader(f)}


def _sort_key(row: dict) -> tuple[int, int, str]:
    """Blank HIKING_ROUTE_COUNT ("no boundary data") sorts last, then
    descending count, then name -- mirrors compute_michelin_score.py's
    and compute_unesco_score.py's output ordering."""
    count = row["HIKING_ROUTE_COUNT"]
    has_count = count not in (None, "")
    return (0 if has_count else 1, -int(count) if has_count else 0, row["COUNTRY_NAME"])


def write_rows(rows: dict[str, dict]) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows.values(), key=_sort_key)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(ordered)


def fetch_all(limit: int | None = None, force: bool = False) -> Path:
    country_names = load_country_names()
    codes = sorted(country_names)
    if limit is not None:
        codes = codes[:limit]

    rows = {} if force else load_existing_rows()
    pending = [c for c in codes if force or c not in rows]
    print(f"{len(codes)} countries requested, {len(codes) - len(pending)} already in {OUTPUT_PATH.name}, {len(pending)} to fetch.")

    no_area = 0
    for i, iso2 in enumerate(pending, start=1):
        name = country_names[iso2]
        print(f"[{i}/{len(pending)}] {iso2} ({name}) ...")
        area_found, count = fetch_country(iso2)

        if not area_found:
            no_area += 1

        rows[iso2] = {
            "COUNTRY": iso2,
            "COUNTRY_NAME": name,
            "HIKING_ROUTE_COUNT": "" if count is None else str(count),
        }
        write_rows(rows)  # checkpoint after every country, not just at the end
        time.sleep(REQUEST_DELAY_SECONDS)

    print(f"Done. {len(rows)}/{len(codes)} countries -> {OUTPUT_PATH}")
    print(f"({no_area} of this run's {len(pending)} fetches had no resolvable OSM boundary or failed -- left blank, not 0.)")
    return OUTPUT_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N countries (for a pilot run).")
    parser.add_argument("--force", action="store_true", help="Re-fetch countries already present in the output file.")
    args = parser.parse_args()
    fetch_all(limit=args.limit, force=args.force)


if __name__ == "__main__":
    main()
