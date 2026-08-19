"""
Derived from: data/processed/multiple/bourdain_trips.json (built by
              build_bourdain_trips.py from the No Reservations and Parts
              Unknown episode lists)
Requires: data/processed/multiple/airline_routes_enhanced.csv (who flies each
          route, and the country pair behind destination_country_code),
          data/raw/bts_t100/*.csv (carrier code -> the full carrier name the
          rest of the rec-sys dataset uses)

Turns the No Reservations and Parts Unknown trips into ONE traveler in
the shape the rec-sys pipeline already speaks, and writes data/processed/multiple/
bourdain_traveler.json. build_trips_enhanced.py merges this file exactly the
way it merges synthetic_trips.json (both are listed in its
SYNTHETIC_SOURCES), so the pipeline stays:

    build_bourdain_trips.py    both shows     -> bourdain_trips.json
    build_bourdain_traveler.py + carriers     -> bourdain_traveler.json
    build_trips_enhanced.py    merge          -> trips_enhanced.json
    build_travelers.py         group          -> travelers.json
    build_travelers_anon.py    personas       -> travelers_anon.json

Bourdain is kept OUT of build_synthetic_trips.py on purpose. Those 82
travelers are hand-authored itineraries invented to exercise the
recommender; this one's itinerary is data -- 130 rows derived from two
published episode lists -- and it should be rebuildable from those
sources without touching a 120KB file of authored patterns.

WHICH AIRLINE HE FLEW
---------------------
The trip already knows its airports (JFK preferred, then LGA, then EWR --
see build_bourdain_trips.py). Among the airlines that fly that exact route:

    CARRIER_PREFERENCE = DL Delta, UA United, AA American, then anything else

The fallback is random rather than "the biggest": these are fabricated
itineraries and always handing the leftovers to the route's dominant
carrier would invent a loyalty the show never had. The draw is seeded per
trip (see pick_carrier), so it is random across trips but identical on
every run, and adding a season doesn't reshuffle the airlines on trips
that were already built.

Route membership comes from airline_routes_enhanced.csv -- the same file
that decided the trip exists at all, so a trip can never end up without an
airline. Carrier NAMES come from the T-100 extracts, so "DL" reads as
"Delta Air Lines Inc." exactly as it does on every other traveler's page;
EXTRA_CARRIER_NAMES covers the handful of airlines in the route data that
never appear in T-100 (defunct, or no US service in the extract's period).

WHAT IS FABRICATED, AND WHAT ISN'T
----------------------------------
Real: the episode, its air date, the destination, the airports, and the
fact that those airlines fly that route. Fabricated: that he made this
trip on this date, its 5-day length, and the airline chosen from the
route's operators. Not invented at all: costs. The Kaggle rows carry
prices and 128 existing trips already have none, so the accommodation and
transportation costs here are left null rather than filled with numbers
that would look like evidence. His age is computed from a real birthdate,
so it moves across both shows (49 on the first trip in 2005, 62 on the
last in 2018).

Usage:
    python build_bourdain_traveler.py
    python build_bourdain_traveler.py --report   # one line per trip: route, airlines available, pick
"""

import argparse
import csv
import json
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
BTS_DIR = DATA_DIR / "raw" / "bts_t100"

TRIPS_PATH = PROCESSED_DIR / "bourdain_trips.json"
ROUTES_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"
BTS_INTL_PATH = BTS_DIR / "T_T100I_MARKET_ALL_CARRIER.csv"
BTS_DOMESTIC_PATH = BTS_DIR / "T_T100D_SEGMENT_ALL_CARRIER.csv"
OUT_PATH = PROCESSED_DIR / "bourdain_traveler.json"

TRAVELER_NAME = "Anthony Bourdain"
TRAVELER_GENDER = "Male"
TRAVELER_NATIONALITY = "American"
BIRTH_DATE = date(1956, 6, 25)

# trip_id is prefix + ISO start date, and a duplicate prefix silently merges
# two people's trips -- "AB" is unused by the 82 travelers in
# build_synthetic_trips.py (checked against trips_enhanced.json).
ID_PREFIX = "AB"

DECLARED_BASE = {
    "base_city": "New York City",
    "base_country": "United States",
    "base_country_code": "US",
}

# In order, by IATA CODE rather than by name. Codes are what
# airline_routes_enhanced.csv actually stores, and they don't depend on the
# T-100 extracts being present -- matching on the name meant that a checkout
# without T-100 silently fell back to a random airline on every single trip,
# because there were no names to match against.
CARRIER_PREFERENCE = (("DL", "Delta"), ("UA", "United"), ("AA", "American"))

# Airlines that fly these routes in airline_routes_enhanced.csv but never
# appear in the T-100 extracts, so their code has no name to look up --
# mostly airlines that died between the route file's vintage and the T-100
# extract's, plus a few that never filed with BTS. Without these, a route
# whose only operator is one of them produces a bare two-letter code where
# every other trip has a full airline name. main() warns about any code
# still unnamed after this map, which is the signal to add one here.
EXTRA_CARRIER_NAMES = {
    "SU": "Aeroflot Russian Airlines",
    "MS": "Egyptair",
    "PS": "Ukraine International Airlines",
    "US": "US Airways Inc.",        # merged into American, 2015
    "AB": "Air Berlin PLC and CO",   # ceased operations 2017
    "VX": "Virgin America",          # merged into Alaska, 2018
    "SE": "XL Airways France",       # ceased operations 2019
    "OJ": "Fly Jamaica Airways",     # ceased operations 2019
    "HA": "Hawaiian Airlines Inc.",
    "DY": "Norwegian Air Shuttle ASA",
    "MH": "Malaysia Airlines",
    "4M": "LAN Argentina",
    "4O": "Interjet",
}

ACCOMMODATION_TYPE = "Hotel"
TRANSPORTATION_TYPE = "Flight"


def load_carrier_names() -> dict[str, str]:
    """Two-letter carrier code -> full carrier name, from the T-100 extracts
    plus EXTRA_CARRIER_NAMES. T-100 is the naming authority here only because
    the rest of the rec-sys data already uses its spellings ("Delta Air Lines
    Inc.", "United Air Lines Inc.") -- a chart that says "Delta" on one
    traveler and "DL" on another is the thing this avoids."""
    names: dict[str, str] = {}
    for path in (BTS_INTL_PATH, BTS_DOMESTIC_PATH):
        if not path.exists():
            print(f"WARNING: {path} not found -- carrier names may fall back to bare codes.")
            continue
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                names.setdefault(row["UNIQUE_CARRIER"], row["CARRIER_NAME"])
    names.update(EXTRA_CARRIER_NAMES)
    return names


def load_route_operators() -> tuple[dict, dict]:
    """((origin, dest) -> sorted carrier codes, (origin, dest) -> country_pair)."""
    operators = defaultdict(set)
    country_pairs = {}
    with ROUTES_PATH.open(newline="") as fh:
        for row in csv.DictReader(fh):
            key = (row["Departure"], row["Destination"])
            operators[key].add(row["Airline ID"])
            if row.get("country_pair"):
                country_pairs.setdefault(key, row["country_pair"])
    return {k: sorted(v) for k, v in operators.items()}, country_pairs


def pick_carrier(codes, names, trip_id, origin, dest):
    """Delta, then United, then American, then a seeded random pick from
    whoever else flies the route.

    The seed is the trip itself, not a global counter: a global counter would
    mean inserting one new trip re-rolls the airline on every trip after it,
    and the point of a fixed seed is that yesterday's output still matches
    today's."""
    for wanted, _label in CARRIER_PREFERENCE:
        if wanted in codes:
            return wanted, names.get(wanted, wanted), "preferred"

    code = random.Random(f"{trip_id}|{origin}|{dest}").choice(sorted(codes))
    return code, names.get(code, code), "random"


def age_on(day: date) -> int:
    """Age at the start of the trip, from a real birthdate -- so he ages
    across the run of the show instead of being one number for eight years."""
    return day.year - BIRTH_DATE.year - ((day.month, day.day) < (BIRTH_DATE.month, BIRTH_DATE.day))


def destination_country_code(country_pair, is_domestic):
    """The destination's ISO code out of a country_pair like "FR|US".

    The pair is sorted alphabetically, not origin-then-destination, so it
    can't be read positionally. Every trip here departs New York, so the
    destination is whichever side isn't US -- and on a domestic trip both
    sides are US anyway. San Juan is the case that makes this worth
    spelling out: the route data calls JFK-SJU "PR|US", so Puerto Rico
    reads as international against a US base."""
    if not country_pair:
        return None
    codes = country_pair.split("|")
    if is_domestic:
        return "US"
    other = [c for c in codes if c != "US"]
    return other[0] if other else "US"


def build_trips():
    with TRIPS_PATH.open() as fh:
        source = json.load(fh)

    names = load_carrier_names()
    operators, country_pairs = load_route_operators()

    trips, report = [], []
    for trip in source["trips"]:
        origin, dest = trip["origin_airport"], trip["destination_airport"]
        codes = operators.get((origin, dest), [])
        if not codes:
            raise SystemExit(
                f"{trip['episode_code']}: no operator for {origin}-{dest} in {ROUTES_PATH.name}. "
                "bourdain_trips.json and the route file are out of step -- re-run "
                "build_bourdain_trips.py."
            )

        start = date.fromisoformat(trip["start_date"])
        trip_id = f"{ID_PREFIX}-{trip['start_date']}"
        code, carrier, how = pick_carrier(codes, names, trip_id, origin, dest)
        is_domestic = bool(trip.get("is_domestic"))
        city, country = trip["destination_city"], trip["destination_country"]

        report.append((trip["episode_code"], f"{origin}-{dest}",
                       [names.get(c, c) for c in codes], carrier, how))

        trips.append({
            "trip_id": trip_id,
            "destination_raw": f"{city}, {country}",
            "destination_city": city,
            "destination_country": country,
            "destination_country_code": destination_country_code(
                country_pairs.get((origin, dest)), is_domestic),
            "destination_kind": "city",
            "start_date": trip["start_date"],
            "start_date_raw": trip["start_date"],
            "end_date": trip["end_date"],
            # *_raw carries what the source literally said, and the API's
            # TravelerTrip requires BOTH halves of every date and cost pair --
            # Optional there means "may be null", not "may be absent", so a
            # missing key is a 500 on the traveler page, not a null field.
            "end_date_raw": trip["end_date"],
            "duration_days": trip["duration_days"],
            "duration_raw": f"{trip['duration_days']} days",
            "accommodation_type": ACCOMMODATION_TYPE,
            "accommodation_cost": None,
            "accommodation_cost_raw": None,
            "transportation_type": TRANSPORTATION_TYPE,
            "transportation_cost": None,
            "transportation_cost_raw": None,
            "traveler_name": TRAVELER_NAME,
            "traveler_age": age_on(start),
            "traveler_gender": TRAVELER_GENDER,
            "traveler_nationality": TRAVELER_NATIONALITY,
            "synthetic": True,
            "carrier_name": carrier,
            "carrier_code": code,
            "origin_airport": origin,
            "destination_airport": dest,
            "show": trip["show"],
            "episode_code": trip["episode_code"],
            "episode_title": trip["episode_title"],
        })

    # trip_id is ID_PREFIX + the start date, so two episodes airing on the
    # same day would collapse into one trip downstream -- build_travelers.py
    # keys on trip_id and would silently keep whichever it saw last. The two
    # shows never overlap (No Reservations ended in 2012, Parts Unknown began
    # in 2013) and the same-day Parts Unknown "Prime Cuts" openers are all
    # excluded upstream, but that's a property of today's data, not a
    # guarantee, so it's checked rather than assumed.
    duplicates = sorted({t["trip_id"] for t in trips
                         if sum(1 for x in trips if x["trip_id"] == t["trip_id"]) > 1})
    if duplicates:
        raise SystemExit(
            "duplicate trip_id(s), two episodes share an air date: "
            + ", ".join(duplicates)
            + " -- give one of them its own ID_PREFIX or exclude it in build_bourdain_trips.py."
        )

    trips.sort(key=lambda t: t["start_date"])
    return trips, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print every route, the airlines that fly it, and which one was picked")
    args = parser.parse_args()

    trips, report = build_trips()

    # A carrier code with no name reads as "DY" on a chart where every other
    # segment says "Delta Air Lines Inc." -- name it in EXTRA_CARRIER_NAMES.
    unnamed = sorted({t["carrier_code"] for t in trips if t["carrier_name"] == t["carrier_code"]})
    if unnamed:
        print("WARNING -- carrier code with no name, add it to EXTRA_CARRIER_NAMES: "
              + ", ".join(unnamed))

    if args.report:
        for code, route, available, picked, how in report:
            print(f"{code:<7} {route:<9} {picked:<32} ({how}, {len(available)} on route: "
                  f"{', '.join(available)})")
        print()

    payload = {
        "source": f"{TRIPS_PATH.name} (No Reservations episodes, see build_bourdain_trips.py), "
                  "with an airline chosen per trip from the operators of that route",
        "generated": date.today().isoformat(),
        "note": "FABRICATED trips for one real person: the episodes, dates and routes are real, "
                "the journey, its 5-day length and the airline are not. Costs are deliberately "
                "null rather than invented. Merged into trips_enhanced.json by "
                "build_trips_enhanced.py.",
        "carrier_preference": [f"{code} ({label})" for code, label in CARRIER_PREFERENCE]
                              + ["(anything else, seeded random)"],
        "declared_bases": {TRAVELER_NAME: DECLARED_BASE},
        "total_travelers": 1,
        "total_trips": len(trips),
        "trips": trips,
    }
    with OUT_PATH.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")

    by_carrier = defaultdict(int)
    for trip in trips:
        by_carrier[trip["carrier_name"]] += 1
    preferred = sum(1 for _c, _r, _a, _p, how in report if how == "preferred")

    print(f"Wrote {len(trips)} trips for {TRAVELER_NAME} -> {OUT_PATH}")
    print(f"{preferred} of {len(trips)} on a preferred carrier "
          f"({', '.join(label for _code, label in CARRIER_PREFERENCE)}), "
          f"{len(trips) - preferred} drawn at random")
    print(f"{len(by_carrier)} distinct airlines:")
    for carrier, count in sorted(by_carrier.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>3}  {carrier}")


if __name__ == "__main__":
    main()
