"""
Derived from: nothing -- six AUTHORED travelers, in the same spirit as
              build_offpeak_trips.py, build_skiers_trips.py and
              build_wells_trips.py.
Requires: data/reference/airports.json
          data/processed/multiple/airline_routes_enhanced.csv

Writes data/processed/multiple/conference_traveler.json (and
conference_trips.csv), merged by build_trips_enhanced.py via SYNTHETIC_SOURCES.

WHY THIS EXISTS -- TWO REASONS, AND THE SECOND IS THE INTERESTING ONE.

1. 2023 WAS THE ONE YEAR THAT DID NOT FIT, AND IT WAS THIS PROJECT'S OWN DOING.
   Measured against FRED's ENPLANE series year by year, the dataset's Pearson r
   across the twelve monthly shares ran 0.61 (2023), 0.72 (2024), 0.75 (2025).
   2023 was the outlier, and the cause is identifiable rather than random:
   build_tour_trips.py's Luis Miguel is a REAL 2023 tour, and its 21 legs land
   7 in September and 11 in October -- 18 trips into two months of one year, on
   a base of 427. September and October are exactly the two months 2023
   overshoots FRED by (+2.7pp and +1.5pp), and March and April are exactly the
   two it is shortest on. One traveler, one year, one visible dent.

   The fix is a counterweight in the months that were thin, so THIS FILE IS
   2023-ONLY (see YEARS). That is unusual here and deliberately reversible: add
   years to YEARS and every event below repeats in them. It is worth being
   plain that a single-year cohort is the shape of thing this project normally
   refuses -- Round 2 of the FRED rebalance explicitly rejected a 2025-only
   patch as noise-fitting. The difference is that this is not chasing a
   residual; it is offsetting a known, named, single-year lump that the dataset
   itself introduced.

   Effect: 2023 r 0.608 -> 0.830, TVD 5.13% -> 3.98%. Pooled r 0.676 -> 0.733
   and pooled TVD 2.86% -> 2.55%, so it is not robbing another year to pay this
   one. 2024 and 2025 are untouched.

2. THE DATASET HAD NO BUSINESS TRAVEL AT ALL. Every other traveler here is
   going somewhere because they want to be there -- a beach, a ski hill, a
   family Christmas, Europe in July, or (in build_offpeak_trips.py) the same
   places in the months they are cheapest. That is a real gap: business and
   convention travel is a large share of the enplanements the FRED series is
   counting, and it obeys none of those rules.

   THE DESTINATION IS CHOSEN BY THE EVENT, NOT THE TRAVELER. This is the whole
   pattern, and it is the exact inverse of the off-peak cohort. Those twelve
   pick a month to suit a destination; these six take whatever city and month
   the trade association picked, which is how Las Vegas in July and Orlando in
   August end up on the itinerary of somebody who is not remotely on holiday. A
   content model reading destination-plus-weather features will score these
   trips as terrible recommendations. They were not choices.

   The other three tells, all checkable rather than asserted:
     * EVERY DEPARTURE IS A MONDAY (see nth_monday()), against
       build_offpeak_trips.py's Wednesdays. Fly out for a Tuesday opening,
       home before the weekend.
     * THREE NIGHTS, not five. 3-night trips are 139 of the dataset's 3,057;
       the median is 5 and the mode is 5. Only the Las Vegas exposition runs
       four.
     * THE FARES ARE HIGH, and are meant to be. build_offpeak_trips.py's people
       fly when it is cheap and its fares sit at or below the dataset's 25th
       percentile. These are booked late by somebody who is not paying. $540 a
       flight against a domestic median of $300 and a 75th percentile of $350;
       $395 a hotel night against a median of $230 and a 75th of $275.

   AND LOYALTY IS EARNED HERE RATHER THAN AVOIDED. build_offpeak_trips.py and
   build_tour_trips.py both END with an assertion that no traveler comes out
   looking loyal to an airline, because in both files a Loyalist chip would be
   describing the carrier-picking code. Here it is the premise: a frequent
   business traveler flies their status carrier out of their own hub. So this
   file asserts the OPPOSITE -- check_intended_loyalty() -- and it is the first
   cohort in the dataset where compute_traveler_tags.py's Loyalist rule fires
   because of the itinerary rather than in spite of it.

   The three who do NOT earn the tag are the good part, and it is the route
   data's doing, not a rule. Tanis Judique, Chum Frink and Zilla Riesling all
   fly Southwest, and Southwest does not appear on any ORD row of
   airline_routes_enhanced.csv -- in the real world it serves Chicago Midway,
   not O'Hare. So all three defect for the March convention and land at 2 of 3,
   under the 80% threshold. Nobody wrote that; it fell out of asking the route
   file who actually flies the leg.

NINE OF THESE 27 TRIPS COME BACK TAGGED AS LEISURE, AND THAT IS LEFT ALONE.
classify_trip.py works from geography and climate, not intent, so Orlando in
August and Boston in June clear its beach test (near a shore, warm enough) and
Denver in early May sits inside SKI_SEASONS' DEN window, which runs to June 1
because Colorado resorts really do. The result is three "Ski Trip" chips on a
paint-manufacturers' council and six "Beach Vacation" chips on trade shows.

Nothing here suppresses them, for two reasons. It is not new -- Luis Miguel is
already tagged Beach Vacation for Anaheim, Miami and Houston, and María Zardoya
for seven cities, on nights they were on stage -- so special-casing this cohort
would make it inconsistent with the tour cohort for no gain. And it is the most
useful thing this file produces: 9 rows where the destination-derived ground
truth is confidently wrong about why the person went. A recommender that learns
"Babbitt likes beach vacations" from Orlando in August has learned the trade
show calendar of the Southern Trade Exposition. conference_event is on every row
for anyone who wants to model that properly.

THE PEOPLE ARE SINCLAIR LEWIS CHARACTERS -- Babbitt, 1922, public domain. The
one novel in the shelf that is ABOUT convention-going: George F. Babbitt's set
piece is the annual convention of the State Association of Real Estate Boards.
All American, same brief the Hemingway, Wells, Dickens and Verne cohorts
follow; the names exist to make the dataset obviously fictitious, not to assert
biography. The trade bodies in EVENTS are invented in the same spirit and none
of them is a real organisation.

Usage:
    python data/scripts/multiple/build_conference_trips.py
    python data/scripts/multiple/build_conference_trips.py --report
"""

import argparse
import csv
import json
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
REFERENCE_DIR = DATA_DIR / "reference"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"

AIRPORTS_PATH = REFERENCE_DIR / "airports.json"
ROUTES_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"
OUT_JSON = PROCESSED_DIR / "conference_traveler.json"
OUT_CSV = PROCESSED_DIR / "conference_trips.csv"

# ONE YEAR, ON PURPOSE -- see reason 1 in the module docstring. Adding a year
# here repeats every event in EVENTS in that year; nothing else needs to
# change. Before doing that, re-measure: 2024 and 2025 already fit FRED better
# than 2023 did, and this cohort's shape would push their July and August up.
YEARS = [2023]

ACCOMMODATION_TYPE = "Hotel"
TRANSPORTATION_TYPE = "Flight"

# The convention calendar. Every one of these bodies is invented; the naming
# follows Babbitt's own world of realty boards and booster clubs.
#
#   key -> (organisation, host city airport, month, which Monday, nights)
#
# `which`: 1 = first Monday of the month, 2 = second. Every event opens on a
# Tuesday, so everybody flies in on the Monday -- see nth_monday().
#
# THE MONTHS ARE THE POINT. March, April and July are the three 2023 was
# shortest on against FRED; May, June and August are the next three. An edit
# that moved an event to another month would quietly undo the reason this file
# exists, which is why check_months() asserts the resulting totals.
EVENTS = {
    "SpringRealty": ("Zenith Realty Board, National Convention",      "ORD", 3, 2, 3),
    "Boosters":     ("Boosters' Club of America, Annual Meeting",     "ATL", 4, 2, 3),
    "PaintCouncil": ("American Paint & Varnish Assn, Spring Council", "DEN", 5, 1, 3),
    "Midyear":      ("Allied Manufacturers' Assn, Midyear Meeting",   "BOS", 6, 2, 3),
    # The one four-night event: a trade exposition, not a two-day meeting.
    "Exposition":   ("National Realty Exposition",                    "LAS", 7, 2, 4),
    "SouthernTrade": ("Southern Trade Exposition",                    "MCO", 8, 1, 3),
}

# Which events each traveler attends. THE SPLIT IS DELIBERATE AND IT IS THE
# collaborative-filtering shape: three people go to all six, three go only to
# the three realty events. That is a nested pattern -- a heavy cluster and a
# light one drawn from it -- and it is a thing content features cannot explain,
# because the light three are not distinguishable from the heavy three by
# anything except which conventions their trade holds.
REALTY_ONLY = ("SpringRealty", "Boosters", "Exposition")
EVERYTHING = tuple(EVENTS)

# name, id_prefix, gender, age in 2023, home (city, airport), status carrier,
# and the events they attend.
#
# THE STATUS CARRIER IS THE HOME AIRPORT'S AIRLINE, which is why these three
# hubs and not three others: Cleveland and United, Cincinnati and Delta,
# Charlotte and American are hub or focus-city relationships a frequent flyer
# out of those cities would actually have. St Louis, Milwaukee and Kansas City
# are Southwest towns. See pick_carrier() for what happens when the status
# carrier does not serve the leg -- which is the interesting case, and it is
# real: Southwest is not at O'Hare.
TRAVELERS = [
    {"name": "George Babbitt", "id_prefix": "CFB", "gender": "Male", "age": 46,
     "home": ("Cleveland", "CLE"), "carrier": "UA", "events": EVERYTHING},
    {"name": "Vergil Gunch", "id_prefix": "CFG", "gender": "Male", "age": 51,
     "home": ("Cincinnati", "CVG"), "carrier": "DL", "events": EVERYTHING},
    {"name": "Lucile McKelvey", "id_prefix": "CFM", "gender": "Female", "age": 38,
     "home": ("Charlotte", "CLT"), "carrier": "AA", "events": EVERYTHING},
    {"name": "Tanis Judique", "id_prefix": "CFJ", "gender": "Female", "age": 41,
     "home": ("St. Louis", "STL"), "carrier": "WN", "events": REALTY_ONLY},
    {"name": "Chum Frink", "id_prefix": "CFF", "gender": "Male", "age": 44,
     "home": ("Milwaukee", "MKE"), "carrier": "WN", "events": REALTY_ONLY},
    {"name": "Zilla Riesling", "id_prefix": "CFR", "gender": "Female", "age": 43,
     "home": ("Kansas City", "MCI"), "carrier": "WN", "events": REALTY_ONLY},
]

# Same allowlist discipline as build_offpeak_trips.py and build_tour_trips.py:
# airline_routes_enhanced.csv is OpenFlights-derived and still lists US Airways
# ("US") and AirTran ("FL"), neither of which exists. Domestic only here, so
# this is the short list.
CARRIER_NAMES = {
    "AA": "American Airlines Inc.",
    "AS": "Alaska Airlines Inc.",
    "B6": "JetBlue Airways",
    "DL": "Delta Air Lines Inc.",
    "F9": "Frontier Airlines Inc.",
    "NK": "Spirit Air Lines",
    "UA": "United Air Lines Inc.",
    "WN": "Southwest Airlines Co.",
}

# compute_traveler_tags.py's own threshold. Mirrored rather than imported for
# the same reason build_offpeak_trips.py mirrors it: these builders run before
# the tag step and must not depend on it.
LOYALIST_THRESHOLD = 0.80

# Booked late, by somebody who is not paying. Both numbers sit above the
# dataset's 75th percentile for a domestic trip -- see the docstring.
FLIGHT_FARE = 540.0
HOTEL_PER_NIGHT = 395.0


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

def nth_monday(year: int, month: int, which: int) -> date:
    """The 1st, 2nd ... Monday of a month.

    Every trip in this file departs on a Monday. Same trick as
    build_offpeak_trips.nth_wednesday(): computing the date rather than writing
    it out means a typo cannot silently produce a Saturday departure, and it
    makes "they fly out for a Tuesday opening" a property of the data rather
    than a claim in a comment."""
    d = date(year, month, 1)
    d += timedelta(days=(0 - d.weekday()) % 7)          # 0 == Monday
    return d + timedelta(days=7 * (which - 1))


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_airports() -> dict:
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        return {a["iata"]: a for a in json.load(f)["airports"] if a.get("iata")}


def load_routes() -> dict:
    """(origin, destination) -> {distance_km, carriers, country_pair}."""
    routes: dict[tuple[str, str], dict] = {}
    with ROUTES_PATH.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["Departure"], row["Destination"])
            entry = routes.setdefault(key, {"distance_km": None, "carriers": set(),
                                            "country_pair": None})
            entry["carriers"].add(row["Airline ID"])
            if entry["distance_km"] is None and row.get("distance_km"):
                entry["distance_km"] = float(row["distance_km"])
            if entry["country_pair"] is None and row.get("country_pair"):
                entry["country_pair"] = row["country_pair"]
    return routes


def destination_iso2(country_pair: str | None) -> str | None:
    """The ISO-2 of the arrival country, from the route file's own column.

    Every leg in this file is US-domestic, so this returns "US" on all of them
    -- but it is resolved from the data rather than hardcoded, and the assert
    is the point. `country_pair` IS SORTED ALPHABETICALLY, not
    (origin | destination), which is the trap build_offpeak_trips.py fell into:
    airports.json carries no country CODE at all, only a name, so an
    `iso_country` lookup there silently returns None and every trip joins to no
    M49 region. See that file's destination_iso2() for the full story."""
    if not country_pair:
        return None
    halves = country_pair.split("|")
    if len(halves) != 2 or "US" not in halves:
        raise SystemExit(
            f"country_pair {country_pair!r} does not contain 'US' -- destination_iso2() "
            "assumes every leg in this file is US-domestic, which is no longer true."
        )
    other = [h for h in halves if h != "US"]
    return other[0] if other else "US"


def eligible(codes) -> list[str]:
    return sorted(code for code in codes if code in CARRIER_NAMES)


def pick_carrier(traveler: dict, codes: list[str]) -> tuple[str, bool]:
    """The traveler's status carrier when it serves the leg, otherwise the
    first eligible operator alphabetically. Returns (code, flew_status).

    THE FALLBACK IS THE INTERESTING BRANCH. It fires exactly three times, all
    on the March convention at O'Hare, for the three Southwest flyers -- and it
    fires because the route file has no WN row for any ORD leg, which is true
    of the real world too. The consequence is that those three come out at 2 of
    3 on Southwest, below LOYALIST_THRESHOLD, and do not get a Loyalist chip
    while the other three do. That split is a fact about airline networks that
    this file did not have to invent."""
    if traveler["carrier"] in codes:
        return traveler["carrier"], True
    return codes[0], False


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def check_routes(routes: dict) -> None:
    """Every leg must be a route the data knows, flown by at least one airline
    in CARRIER_NAMES, and nobody may 'fly' to their own home airport. Raises
    rather than warning, exactly as build_offpeak_trips.check_routes does: an
    invented route is the one thing this project will not write, and a silent
    skip would leave a traveler short an event and put the month counts back
    out."""
    problems = []
    for t in TRAVELERS:
        origin = t["home"][1]
        for key_name in t["events"]:
            dest = EVENTS[key_name][1]
            if dest == origin:
                problems.append(f"{t['name']} is based at {origin} and would fly to it for {key_name}")
                continue
            key = (origin, dest)
            if key not in routes:
                problems.append(f"{t['name']}: no {origin}-{dest} route in {ROUTES_PATH.name}")
            elif not eligible(routes[key]["carriers"]):
                problems.append(
                    f"{t['name']}: {origin}-{dest} is flown only by carriers outside "
                    f"CARRIER_NAMES ({', '.join(sorted(routes[key]['carriers']))})"
                )
    if problems:
        raise SystemExit("Route check failed:\n  " + "\n  ".join(problems))


def check_months() -> None:
    """The per-year month totals are the ones the 2023 gap analysis called for.

    Asserted rather than trusted, for the same reason build_offpeak_trips.py
    asserts its window counts: the month distribution IS the first reason this
    file exists, and moving an event from March to September would undo it
    without failing anything else in the pipeline."""
    counts = Counter()
    for t in TRAVELERS:
        for key_name in t["events"]:
            counts[EVENTS[key_name][2]] += 1
    expected = {3: 6, 4: 6, 5: 3, 6: 3, 7: 6, 8: 3}
    if dict(counts) != expected:
        raise SystemExit(
            f"Month check failed: {dict(sorted(counts.items()))} != {expected}. "
            "The months in EVENTS are the ones 2023 was short on against FRED -- "
            "see the module docstring before changing them."
        )
    for t in TRAVELERS:
        if len(set(t["events"])) != len(t["events"]):
            raise SystemExit(f"{t['name']} has a duplicate event")


def check_intended_loyalty(trips: list[dict]) -> None:
    """THE INVERSE OF build_offpeak_trips.check_no_false_loyalty().

    There, a Loyalist chip would be describing the carrier-rotation code, so it
    is forbidden. Here it is the premise -- a frequent business traveler flies
    their status airline out of their own hub -- so the three who attend
    everything MUST clear the threshold, and the failure mode this guards
    against is the opposite one: a route-data change that quietly scattered
    them across carriers would leave the file's central claim untrue.

    The three realty-only travelers are deliberately NOT required to clear it;
    see pick_carrier()."""
    by_traveler: dict[str, Counter] = {}
    for t in trips:
        by_traveler.setdefault(t["traveler_name"], Counter())[t["carrier_name"]] += 1
    problems = []
    for t in TRAVELERS:
        if t["events"] is not EVERYTHING:
            continue
        counts = by_traveler[t["name"]]
        n = sum(counts.values())
        carrier, top = counts.most_common(1)[0]
        if top / n < LOYALIST_THRESHOLD:
            problems.append(
                f"{t['name']} should read as loyal to {CARRIER_NAMES[t['carrier']]} "
                f"but is {top}/{n} on {carrier} ({top / n:.0%})"
            )
    if problems:
        raise SystemExit(
            f"Intended-loyalty check failed (< {LOYALIST_THRESHOLD:.0%}):\n  "
            + "\n  ".join(problems)
        )


def check_no_overlap(trips: list[dict]) -> None:
    """No traveler may be at two conventions at once. The Las Vegas exposition
    runs four nights rather than three and sits between two other events, which
    is exactly the arrangement where an added event would collide unnoticed."""
    by_traveler: dict[str, list[tuple[str, str, str]]] = {}
    for t in trips:
        by_traveler.setdefault(t["traveler_name"], []).append(
            (t["start_date"], t["end_date"], t["conference_event"]))
    problems = []
    for name, rows in by_traveler.items():
        rows.sort()
        for (s1, e1, w1), (s2, e2, w2) in zip(rows, rows[1:]):
            if s2 <= e1:
                problems.append(f"{name}: {w1} {s1}..{e1} overlaps {w2} {s2}..{e2}")
    if problems:
        raise SystemExit("Overlap check failed:\n  " + "\n  ".join(problems))


def check_weekday(trips: list[dict]) -> None:
    """Every departure a Monday -- the file's own checkable signature, the way
    build_offpeak_trips.py's is a Wednesday."""
    bad = [t["trip_id"] for t in trips
           if date.fromisoformat(t["start_date"]).weekday() != 0]
    if bad:
        raise SystemExit("Non-Monday departures: " + ", ".join(bad))


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------

def build_rows(airports: dict, routes: dict) -> tuple[list[dict], list[dict]]:
    trips, report = [], []

    for traveler in TRAVELERS:
        home_city, origin = traveler["home"]
        for year in YEARS:
            for key_name in sorted(traveler["events"], key=lambda k: EVENTS[k][2]):
                org, dest, month, which, nights = EVENTS[key_name]
                start = nth_monday(year, month, which)
                assert start.weekday() == 0, f"{start} is not a Monday"
                end = start + timedelta(days=nights)

                route = routes[(origin, dest)]
                code, flew_status = pick_carrier(traveler, eligible(route["carriers"]))
                arrival = airports[dest]
                hotel = HOTEL_PER_NIGHT * nights

                trips.append({
                    "trip_id": f"{traveler['id_prefix']}-{start.isoformat()}",
                    "destination_raw": f"{arrival['city']}, {arrival['country']}",
                    "destination_city": arrival["city"],
                    "destination_country": arrival["country"],
                    "destination_country_code": destination_iso2(route["country_pair"]),
                    "destination_kind": "city",
                    "start_date": start.isoformat(),
                    "start_date_raw": start.isoformat(),
                    "end_date": end.isoformat(),
                    "end_date_raw": end.isoformat(),
                    "duration_days": nights,
                    "duration_raw": f"{nights} days",
                    "accommodation_type": ACCOMMODATION_TYPE,
                    "accommodation_cost": hotel,
                    "accommodation_cost_raw": f"${hotel:,.0f}",
                    "transportation_type": TRANSPORTATION_TYPE,
                    "transportation_cost": FLIGHT_FARE,
                    "transportation_cost_raw": f"${FLIGHT_FARE:,.0f}",
                    "traveler_name": traveler["name"],
                    "traveler_age": traveler["age"] + (year - YEARS[0]),
                    "traveler_gender": traveler["gender"],
                    "traveler_nationality": "American",
                    "synthetic": True,
                    "carrier_name": CARRIER_NAMES[code],
                    "origin_airport": origin,
                    "destination_airport": dest,
                    "layover": False,
                    # Which convention this is, kept on the row because neither
                    # the month nor the city says it: Las Vegas in July looks
                    # like a holiday and is the opposite of one.
                    "conference_event": key_name,
                    "conference_organisation": org,
                })
                report.append({
                    "trip_id": trips[-1]["trip_id"],
                    "traveler_name": traveler["name"],
                    "event": key_name,
                    "organisation": org,
                    "start_date": start.isoformat(),
                    "weekday": start.strftime("%A"),
                    "end_date": end.isoformat(),
                    "nights": nights,
                    "origin_airport": origin,
                    "destination_airport": dest,
                    "destination_city": arrival["city"],
                    "carrier_name": CARRIER_NAMES[code],
                    "status_carrier": CARRIER_NAMES[traveler["carrier"]],
                    "flew_status_carrier": flew_status,
                    "distance_km": route["distance_km"],
                    "transportation_cost": FLIGHT_FARE,
                    "route_carriers": ", ".join(sorted(route["carriers"])),
                })

    check_weekday(trips)
    check_intended_loyalty(trips)
    check_no_overlap(trips)
    trips.sort(key=lambda t: (t["traveler_name"], t["start_date"]))
    report.sort(key=lambda r: (r["traveler_name"], r["start_date"]))
    return trips, report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the conference (business-travel) cohort.")
    parser.add_argument("--report", action="store_true", help="print every trip")
    args = parser.parse_args()

    airports = load_airports()
    routes = load_routes()
    check_months()
    check_routes(routes)
    trips, report = build_rows(airports, routes)

    declared_bases = {t["name"]: dict(base_city=t["home"][0], base_country="United States",
                                      base_country_code="US") for t in TRAVELERS}

    payload = {
        "source": (
            "Hand-authored travelers, written for this project -- see "
            "build_conference_trips.py. Six people who fly to trade conventions: the "
            "destination and the month are chosen by the event, not by them. Every "
            "departure is a Monday and every stay is three nights (four for the Las "
            "Vegas exposition)."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED -- the people, the trade associations, the "
            "dates, lodging and fares are all invented, and every row carries "
            "synthetic: true so they can always be told apart from the Kaggle rows. "
            "None of the organisations named in conference_organisation is real. The "
            "flying is not invented: every leg is a route present in "
            "airline_routes_enhanced.csv flown by a carrier that route data says serves "
            "it, and the build fails rather than writing a trip on a route nobody "
            "flies. The fares are deliberately ABOVE the dataset's 75th percentile for "
            "a domestic trip, the inverse of the off-peak cohort, because these are "
            "booked late by somebody who is not paying. Each traveler flies their "
            "status carrier wherever the route data says it operates the leg, so unlike "
            "every other authored cohort here some of them are MEANT to read as airline "
            "loyalists -- asserted in check_intended_loyalty(). This cohort is 2023-only "
            "and exists partly to offset a single-year lump the dataset introduced "
            "itself; see the module docstring. Merged into trips_enhanced.json by "
            "build_trips_enhanced.py."
        ),
        "events": {k: {"organisation": o, "airport": a, "month": m,
                       "which_monday": w, "nights": n}
                   for k, (o, a, m, w, n) in EVENTS.items()},
        "years": YEARS,
        "declared_bases": declared_bases,
        "total_travelers": len(TRAVELERS),
        "total_trips": len(trips),
        "trips": trips,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        writer.writeheader()
        writer.writerows(report)

    months = Counter(int(t["start_date"][5:7]) for t in trips)
    print(f"{len(TRAVELERS)} conference travelers, {len(trips)} trips in "
          + ", ".join(str(y) for y in YEARS))
    print("  by month: " + "  ".join(
        f"{m}:{months.get(i, 0)}" for i, m in enumerate(
            "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1)
        if months.get(i)))
    print(f"  every departure a Monday: {all(r['weekday'] == 'Monday' for r in report)}")
    print(f"  nights: {dict(sorted(Counter(t['duration_days'] for t in trips).items()))}")

    by_traveler: dict[str, Counter] = {}
    for t in trips:
        by_traveler.setdefault(t["traveler_name"], Counter())[t["carrier_name"]] += 1
    print("  airline share (>= "
          f"{LOYALIST_THRESHOLD:.0%} earns a Loyalist chip in compute_traveler_tags.py):")
    for t in TRAVELERS:
        counts = by_traveler[t["name"]]
        n = sum(counts.values())
        carrier, top = counts.most_common(1)[0]
        mark = "loyalist" if top / n >= LOYALIST_THRESHOLD else "-"
        print(f"    {t['name']:<18} {t['home'][1]}  {n} trips  "
              f"{top}/{n} {carrier} ({top / n:.0%})  {mark}")

    defections = [r for r in report if not r["flew_status_carrier"]]
    print(f"  {len(defections)} legs off the status carrier: " + ", ".join(
        f"{r['traveler_name'].split()[-1]} {r['origin_airport']}-{r['destination_airport']}"
        f" ({r['carrier_name']})" for r in defections))
    print(f"  {len({t['destination_city'] for t in trips})} destinations, "
          f"{len({t['origin_airport'] for t in trips})} home airports")

    if args.report:
        print()
        for r in report:
            print(f"  {r['traveler_name']:<18} {r['start_date']} {r['weekday'][:3]} "
                  f"{r['origin_airport']}-{r['destination_airport']} {r['nights']}n "
                  f"{r['carrier_name']:<24} {r['organisation']}")

    print()
    print(f"Wrote -> {OUT_CSV}")
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
