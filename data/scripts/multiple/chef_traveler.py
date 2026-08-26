"""
Shared machinery for turning one chef's trip rows into one traveler in the
shape the rec-sys pipeline speaks.

Used by build_bourdain_traveler.py and build_ramsay_traveler.py. What
differs between them is configuration -- the source file, the home
airports' worth of routes, the airline preference, the birthdate, the
trip_id prefix -- and it is all passed in. What is shared is the part that
has to agree between travelers: the record shape, how an airline is
chosen, and how a trip is dated.

Requires: data/processed/multiple/airline_routes_enhanced.csv (who flies
          each route, and the country pair behind
          destination_country_code),
          data/raw/bts_t100/*.csv (carrier code -> the full carrier name
          the rest of the rec-sys dataset uses)

CHOOSING AN AIRLINE. Each chef passes a CARRIER_PREFERENCE of (code,
label) pairs -- Bourdain flies DL then UA then AA, Ramsay UA then DL then
AA. When none of them serves the route, one of the route's other
operators is drawn at random.

The preference matches on IATA CODE, not on carrier name. Codes are what
airline_routes_enhanced.csv stores; matching on the name meant that a
checkout without the T-100 extracts silently fell back to a random
airline on every single trip, because there were no names to match
against.

The random draw is seeded per trip rather than from a global counter: a
counter would mean inserting one new trip re-rolls the airline on every
trip after it, and the point of a fixed seed is that yesterday's output
still matches today's.

WHAT IS FABRICATED, AND WHAT ISN'T. Real: the episode, its air date, the
destination, the airports, and the fact that those airlines fly that
route. Fabricated: that the chef made this trip on this date, its length,
and which of the route's operators they flew. Not invented at all: costs.
The Kaggle rows carry prices and plenty of existing trips have none, so
accommodation and transportation costs are left null rather than filled
with numbers that would look like evidence.
"""

import csv
import json
import random
from collections import defaultdict
from datetime import date
from pathlib import Path

from chef_trips import UNKNOWN_CARRIER  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
BTS_DIR = DATA_DIR / "raw" / "bts_t100"

ROUTES_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"
BTS_INTL_PATH = BTS_DIR / "T_T100I_MARKET_ALL_CARRIER.csv"
BTS_DOMESTIC_PATH = BTS_DIR / "T_T100D_SEGMENT_ALL_CARRIER.csv"
COUNTRY_ALIASES_PATH = DATA_DIR / "reference" / "country_aliases.json"

# Airlines that fly these routes in airline_routes_enhanced.csv but never
# appear in the T-100 extracts, so their code has no name to look up --
# mostly airlines that died between the route file's vintage and the T-100
# extract's, plus a few that never filed with BTS. Without these, a route
# whose only operator is one of them produces a bare two-letter code where
# every other trip has a full airline name. Each build script warns about
# any code still unnamed after this map, which is the signal to add one.
EXTRA_CARRIER_NAMES = {
    "SU": "Aeroflot Russian Airlines",
    "MS": "Egyptair",
    "PS": "Ukraine International Airlines",
    "US": "US Airways Inc.",         # merged into American, 2015
    "AB": "Air Berlin PLC and CO",    # ceased operations 2017
    "VX": "Virgin America",           # merged into Alaska, 2018
    "SE": "XL Airways France",        # ceased operations 2019
    "OJ": "Fly Jamaica Airways",      # ceased operations 2019
    "HA": "Hawaiian Airlines Inc.",
    "DY": "Norwegian Air Shuttle ASA",
    "MH": "Malaysia Airlines",
    "4M": "LAN Argentina",
    "4O": "Interjet",
    "FL": "AirTran Airways Corporation",  # merged into Southwest, 2014
    "NZ": "Air New Zealand",
    "VA": "Virgin Australia",
    "TN": "Air Tahiti Nui",
    "FJ": "Fiji Airways",
    "AM": "Aeromexico",
    "U2": "easyJet Airline Company Limited",  # never files with BTS -- no US operations
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


def pick_carrier(codes, names, preference, trip_id, origin, dest):
    """The first preferred airline that flies this route, else a seeded
    random pick from whoever else does. Returns (code, name, how)."""
    for wanted, _label in preference:
        if wanted in codes:
            return wanted, names.get(wanted, wanted), "preferred"

    code = random.Random(f"{trip_id}|{origin}|{dest}").choice(sorted(codes))
    return code, names.get(code, code), "random"


def age_on(day: date, birth_date: date) -> int:
    """Age at the start of the trip, from a real birthdate -- so the traveler
    ages across the run of the show instead of being one number for a decade."""
    return day.year - birth_date.year - ((day.month, day.day) < (birth_date.month, birth_date.day))


_country_iso2_cache: dict[str, str] | None = None

# country_aliases.json stores Namibia's iso2 as the float NaN instead of
# the string "NA" -- a pandas read_csv quirk (NA parses as a null, not a
# literal) tracked in the README TODO as a fix for build_country_aliases.py
# and a full downstream rerun. That's real surgery on a file every other
# script also reads, out of scope here -- this is a one-country patch
# local to this fallback, so a documented visit doesn't fail API
# validation (destination_country_code is a required field, not Optional)
# over one bad row. Remove this once the TODO item lands.
_ISO2_OVERRIDES = {"namibia": "NA"}


def _country_name_to_iso2(name: str | None) -> str | None:
    """Fallback for a trip whose (origin, destination) has no row in
    airline_routes_enhanced.csv at all -- an assumed_flight trip (see
    chef_trips.py), where there's no route data to pull country_pair from.
    Looks the destination's country NAME up in country_aliases.json
    instead. Only used when the route-based lookup below comes up empty,
    so every trip still prefers the real route data when it exists."""
    global _country_iso2_cache
    if _country_iso2_cache is None:
        with COUNTRY_ALIASES_PATH.open() as fh:
            data = json.load(fh)
        # Namibia's iso2 ("NA") reads back from country_aliases.json as the
        # float NaN, not the string "NA" -- a pandas read_csv quirk tracked
        # in the README TODO, not something to fix here. Guard rather than
        # write a literal NaN into this file: skip any entry whose iso2
        # isn't actually a string, so Namibia (the one real case today)
        # falls back to None like any other unresolved country, instead of
        # a value that looks resolved but isn't valid JSON's idea of one.
        _country_iso2_cache = {
            alias: entry["iso2"]
            for entry in data["countries"].values()
            for alias in entry["aliases"]
            if isinstance(entry["iso2"], str)
        }
    if not name:
        return None
    key = name.strip().casefold()
    return _country_iso2_cache.get(key) or _ISO2_OVERRIDES.get(key)


def destination_country_code(country_pair, is_domestic, home_country_code="US"):
    """The destination's ISO code out of a country_pair like "FR|US".

    The pair is sorted alphabetically, not origin-then-destination, so it
    can't be read positionally. Every trip here departs the chef's home
    country, so the destination is whichever side isn't that country -- and
    on a domestic trip both sides are it anyway. San Juan is the case that
    makes this worth spelling out: the route data calls JFK-SJU "PR|US", so
    Puerto Rico reads as international against a US base."""
    if not country_pair:
        return None
    codes = country_pair.split("|")
    if is_domestic:
        return home_country_code
    other = [c for c in codes if c != home_country_code]
    return other[0] if other else home_country_code


def build_trips(trips_path, traveler, preference, id_prefix, birth_date, rebuild_hint,
                trips_key="trips", accommodation_type=ACCOMMODATION_TYPE):
    """
    (trips, report) from one traveler's <name>_trips.json.

    `traveler` carries name / gender / nationality; `rebuild_hint` is the
    script to re-run when the trips file and the route file disagree.
    `trips_key` is which array to read -- "trips" for the show-derived
    files, "legs" for a hand-kept flight log.

    THREE THINGS ARE OPTIONAL, so a flight log can use this too:

      * `show` / `episode_code` / `episode_title` -- a logged leg came from
        no episode, and the fields are omitted rather than filled with an
        empty string that would render as a blank line.
      * `birth_date` -- None leaves traveler_age null. The show travelers
        have published birthdates; a real person under a pseudonym does not
        get an invented one.
      * the carrier -- a row that already names one (`carrier` or
        `carrier_code`) keeps it, marked "logged" in the report rather than
        "preferred" or "random". The preference exists to fill a silence,
        and a log has none.

    `accommodation_type` is likewise overridable: the show travelers get
    "Hotel" as a stand-in, a flight log gets None, because a boarding pass
    says nothing about where anybody slept.
    """
    with trips_path.open() as fh:
        source = json.load(fh)

    names = load_carrier_names()
    operators, country_pairs = load_route_operators()

    trips, report = [], []
    # trip_id is prefix + start date, which is unique right up until a
    # network double-bills two episodes on one night (Uncharted season 4
    # premiered two). Rather than dropping a real episode, the second one
    # onto a date gets a -2 suffix. Silently colliding would be the bad
    # outcome: build_travelers.py keys on trip_id and would keep whichever
    # row it saw last, quietly losing a trip.
    used_ids: dict[str, int] = defaultdict(int)

    for trip in source[trips_key]:
        origin, dest = trip["origin_airport"], trip["destination_airport"]
        codes = operators.get((origin, dest), [])
        logged_code = trip.get("carrier_code") or trip.get("carrier")
        if not codes and not logged_code:
            raise SystemExit(
                f"{trip.get('episode_code') or trip.get('trip_id')}: no operator for "
                f"{origin}-{dest} in {ROUTES_PATH.name}. {trips_path.name} and the route "
                f"file are out of step -- re-run {rebuild_hint}."
            )

        start = date.fromisoformat(trip["start_date"])
        trip_id = f"{id_prefix}-{trip['start_date']}"
        used_ids[trip_id] += 1
        if used_ids[trip_id] > 1:
            trip_id = f"{trip_id}-{used_ids[trip_id]}"

        if logged_code:
            # The log says who was flown. Nothing to choose.
            code, carrier, how = logged_code, names.get(logged_code, logged_code), "logged"
        else:
            code, carrier, how = pick_carrier(codes, names, preference, trip_id, origin, dest)
        is_domestic = bool(trip.get("is_domestic"))
        city, country = trip["destination_city"], trip["destination_country"]

        report.append((trip.get("episode_code") or trip_id, f"{origin}-{dest}",
                       [names.get(c, c) for c in codes], carrier, how))

        dest_country_code = destination_country_code(country_pairs.get((origin, dest)), is_domestic)
        if dest_country_code is None and not is_domestic:
            dest_country_code = _country_name_to_iso2(country)

        trips.append({
            "trip_id": trip_id,
            "destination_raw": f"{city}, {country}",
            "destination_city": city,
            "destination_country": country,
            "destination_country_code": dest_country_code,
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
            # Pluralised because a logged red-eye can be a 1-day trip and
            # "1 days" is the kind of thing that makes a real dataset look
            # generated.
            "duration_raw": f"{trip['duration_days']} day"
                            + ("" if trip["duration_days"] == 1 else "s"),
            # None for a flight log: where somebody stayed isn't in a
            # boarding pass, and "Hotel" would be this file's only guess.
            "accommodation_type": accommodation_type,
            "accommodation_cost": None,
            "accommodation_cost_raw": None,
            "transportation_type": TRANSPORTATION_TYPE,
            "transportation_cost": None,
            "transportation_cost_raw": None,
            "traveler_name": traveler["name"],
            "traveler_age": age_on(start, birth_date) if birth_date else None,
            "traveler_gender": traveler["gender"],
            "traveler_nationality": traveler["nationality"],
            "synthetic": True,
            "carrier_name": carrier,
            "carrier_code": code,
            "origin_airport": origin,
            "destination_airport": dest,
            # True for a leg that's part of a longer journey but isn't its
            # point -- Atlanta and Paris on a Houston-to-Lisbon trip, say.
            # Only a hand-kept log can know this (an episode-derived trip is
            # always nonstop by construction), so it's always False for the
            # show travelers. Present on every trip regardless, for the same
            # reason `synthetic` is: a consumer should never have to check
            # whether the key exists. build_travelers.py, compute_traveler_
            # tags.py and compute_traveler_entropy.py all exclude layover=True
            # rows from trip_count / destinations / airline share -- Ivan's
            # call, see gomez_flight_log.md. The row stays in the data either
            # way: this flag hides it from AGGREGATES, not from the log.
            "layover": bool(trip.get("layover", False)),
            **{k: trip[k] for k in ("show", "episode_code", "episode_title") if k in trip},
        })

    trips.sort(key=lambda t: t["start_date"])
    return trips, report


def write_output(out_path, trips, traveler, declared_base, preference, source_note, trip_note):
    payload = {
        "source": source_note,
        "generated": date.today().isoformat(),
        "note": trip_note,
        # A log has no preference to report -- saying "anything else, seeded
        # random" there would describe a choice that never happened.
        "carrier_preference": ([f"{code} ({label})" for code, label in preference]
                               + ["(anything else, seeded random)"]) if preference
                              else ["(recorded as flown)"],
        "declared_bases": {traveler["name"]: declared_base},
        "total_travelers": 1,
        "total_trips": len(trips),
        "trips": trips,
    }
    with out_path.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return payload


def print_summary(trips, report, traveler, preference, out_path, show_report=False):
    # A carrier code with no name reads as "DY" on a chart where every other
    # segment says "Delta Air Lines Inc." -- name it in EXTRA_CARRIER_NAMES.
    # UNKNOWN_CARRIER is excluded on purpose: it isn't a code that's missing
    # a name, it's chef_trips.py's explicit "we don't know" placeholder for
    # an assumed_flight trip, and adding it to EXTRA_CARRIER_NAMES would be
    # inventing an airline.
    unnamed = sorted({t["carrier_code"] for t in trips
                      if t["carrier_name"] == t["carrier_code"] and t["carrier_code"] != UNKNOWN_CARRIER})
    if unnamed:
        print("WARNING -- carrier code with no name, add it to EXTRA_CARRIER_NAMES: "
              + ", ".join(unnamed))

    if show_report:
        for code, route, available, picked, how in report:
            print(f"{code:<12} {route:<9} {picked:<32} ({how}, {len(available)} on route: "
                  f"{', '.join(available)})")
        print()

    by_carrier = defaultdict(int)
    for trip in trips:
        by_carrier[trip["carrier_name"]] += 1
    preferred = sum(1 for *_rest, how in report if how == "preferred")
    logged = sum(1 for *_rest, how in report if how == "logged")

    print(f"Wrote {len(trips)} trips for {traveler['name']} -> {out_path}")
    if logged == len(trips):
        # A flight log chose nothing -- saying "0 of 1 on a preferred
        # carrier" would imply a preference was applied and lost.
        print(f"{logged} of {len(trips)} carriers taken from the log as flown")
    else:
        print(f"{preferred} of {len(trips)} on a preferred carrier "
              f"({', '.join(label for _code, label in preference)}), "
              f"{len(trips) - preferred - logged} drawn at random"
              + (f", {logged} taken from the log" if logged else ""))
    print(f"{len(by_carrier)} distinct airlines:")
    for carrier, count in sorted(by_carrier.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {count:>3}  {carrier}")
