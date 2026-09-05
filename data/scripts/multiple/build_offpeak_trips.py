"""
Derived from: nothing -- twelve AUTHORED travelers, in the same spirit as
              build_skiers_trips.py, build_hemingway_trips.py and
              build_wells_trips.py.
Requires: data/reference/airports.json
          data/processed/multiple/airline_routes_enhanced.csv

Writes data/processed/multiple/offpeak_traveler.json (and offpeak_trips.csv),
merged by build_trips_enhanced.py via SYNTHETIC_SOURCES.

WHY THIS EXISTS -- TWO REASONS, AND THE SECOND IS THE INTERESTING ONE.

1. THE DATASET'S CALENDAR WAS WRONG, MEASURABLY. Compared against FRED's
   ENPLANE series (US air carrier domestic + international, scheduled
   passenger flights), the dataset was running 11.9% of its trips in each of
   November and December where real US enplanements run 7.7% and 8.4% -- and
   4.9% in January against a real 7.3%. Real air travel is remarkably FLAT:
   its busiest month is only 1.37x its quietest. The dataset's was 2.43x, and
   pointed at the wrong months. These twelve fill January, March, April, July
   and late August, the five months that were short. Together with turning off
   build_hemingway_trips.py's home-for-the-holidays trips (see HOME_HOLIDAYS
   there), this moves the dataset's total variation distance from that series
   from 9.9% to about 3.5%.

   NOT TO ZERO, DELIBERATELY. A dataset that matches aggregate reality exactly
   would have no ski season, no holiday travel, no summer-in-Europe -- and
   those authored patterns are the entire thing a recommender here is supposed
   to learn. November and December are still this dataset's busiest months
   after this file lands. They are just no longer twice everything else.

2. THEY GO TO POPULAR PLACES IN THE MONTHS NOBODY ELSE DOES. This is a pattern
   shape nothing else in the dataset has, and it is a genuinely hard case for
   a recommender. Every destination below -- Paris, Rome, London, Barcelona,
   Amsterdam, Tokyo, Cancun, Orlando -- is somewhere the rest of the dataset
   already goes. What differs is WHEN. On destination alone these twelve are
   indistinguishable from the summer-in-Europe travelers; on timing they are
   the opposite. A content model that scores destinations and ignores the
   calendar will call them the same person and be wrong, which is exactly the
   distinction rec_sys_data_prep.py's twelve monthly weather features exist to
   let a model make.

   OFF-PEAK MEANS OFF-PEAK FOR THE DESTINATION, not just "a quiet month". That
   is why July and late August are in here alongside January: July in Cancun
   and late August in Orlando are low season for those places -- hot, humid,
   hurricane-adjacent, schools back -- in the same way January is low season
   for Paris. One rule, five windows.

WEDNESDAY DEPARTURES, ALWAYS. The cheapest day of the week to fly, and the
detail that makes the premise checkable rather than asserted: every one of
these 240 trips departs on a Wednesday, which is true of almost nothing else
in the dataset. Same idea as the fares below.

THE FARES ARE INVENTED, AND ARE MEANT TO BE LOW. These twelve are fictional,
so unlike the travel-show hosts and the tour artists their costs are written
rather than left null -- the convention build_skiers_trips.py already uses. The
NUMBERS are chosen against the dataset's own medians: international flights
here run 340-480 against a dataset median of 600, domestic 190-250 against 300.
If the premise is "they fly when it is cheap", the cost columns should show it.

THEY ARE LOYAL TO NOBODY, AND THAT IS THE POINT. A traveler chasing fares does
not care whose plane it is. The carrier ROTATES year over year on the same
route, through whichever operators airline_routes_enhanced.csv says serve it --
so each of these twelve ends up with several airlines across twenty trips and
compute_traveler_tags.py will not tag any of them a Loyalist. That is asserted
in check_no_false_loyalty(), because a Loyalist chip here would be describing
this file's carrier rotation rather than the traveler.

THE PEOPLE ARE JULES VERNE CHARACTERS -- public domain (Verne died 1905), and
the one author in the shelf whose characters are defined by travelling. All
American per the same brief the Hemingway, Wells and Dickens cohorts follow;
the names exist to make the dataset obviously fictitious, not to assert
biography.

Usage:
    python data/scripts/multiple/build_offpeak_trips.py
    python data/scripts/multiple/build_offpeak_trips.py --report
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
OUT_JSON = PROCESSED_DIR / "offpeak_traveler.json"
OUT_CSV = PROCESSED_DIR / "offpeak_trips.csv"

YEARS = [2021, 2022, 2023, 2024, 2025]
ACCOMMODATION_TYPE = "Hotel"
TRANSPORTATION_TYPE = "Flight"

# Five windows, each the low season for the places reached in it. Every rule
# resolves to a WEDNESDAY -- see the module docstring.
#
#   window -> (month, which Wednesday, nights)
# `which`: 1 = first Wednesday of the month, 2 = second, -1 = last.
WINDOWS = {
    # The deadest week of the year for transatlantic leisure: after New Year,
    # before anything else starts. Never the 1st week, which is still holiday
    # return traffic and the opposite of off-peak.
    "January":    (1, 2, 7),
    # Before US spring break moves the market.
    "March":      (3, 1, 7),
    # After spring break, before the summer fares start.
    "LateApril":  (4, -1, 7),
    # Low season in the Caribbean and Mexico, not in Europe.
    "July":       (7, 2, 5),
    # Florida and the Caribbean at their emptiest: hottest, wettest, schools back.
    "LateAugust": (8, -1, 5),
    # --- added 2026-09-01, when the 2025 slice was tuned against FRED -------
    # Europe's two shoulder months proper, plus the start of the Caribbean's
    # low season. Same rule as the other three: low season FOR THE
    # DESTINATION, not a month that is quiet everywhere.
    "LateMay":    (5, -1, 7),   # after the spring crowds, before summer fares
    "June":       (6, 2, 5),    # Caribbean and Mexico low season begins
    # SECOND Wednesday, not the first: LateAugust starts on the last Wednesday
    # of August and runs five nights, which can end as late as September 5.
    # A first-Wednesday September window would overlap it for the travelers
    # who fly both. check_no_overlap() asserts it cannot.
    "September":  (9, 2, 7),    # Europe once the August crowds have gone
}

# Airlines this build will use, by IATA code -> the legal name this dataset
# already carries. Same allowlist discipline as build_tour_trips.py, and for
# the same reason: airline_routes_enhanced.csv is OpenFlights-derived and still
# lists US Airways ("US") and AirTran ("FL"), neither of which exists.
CARRIER_NAMES = {
    "AA": "American Airlines Inc.",
    "AS": "Alaska Airlines Inc.",
    "B6": "JetBlue Airways",
    "DL": "Delta Air Lines Inc.",
    "F9": "Frontier Airlines Inc.",
    "NK": "Spirit Air Lines",
    "UA": "United Air Lines Inc.",
    "WN": "Southwest Airlines Co.",
    "AC": "Air Canada",
    "AF": "Compagnie Natl Air France",
    "BA": "British Airways Plc",
    "EI": "Aer Lingus Plc",
    "IB": "Iberia Air Lines Of Spain",
    "KL": "Klm Royal Dutch Airlines",
    "LH": "Lufthansa German Airlines",
    "TP": "TAP-TAP Air Portugal",
    # Both taken from the T-100 international file's own carrier-name column,
    # which is where every other legal name in this dataset comes from --
    # "Icelandair" is already on 5 rows of trips_enhanced.json.
    "FI": "Icelandair",
    "SK": "Scandinavian Airlines Sys.",
}

LOYALIST_THRESHOLD = 0.80

# Fares, in the two bands described in the docstring. Deliberately at or below
# the dataset's 25th percentile for the same kind of trip.
FARES = {
    "intl":     (420.0, 1150.0),   # (flight, hotel) -- dataset medians 600 / 1262
    "domestic": (215.0,  820.0),   # dataset medians 300 / 1050
}

# name, id_prefix, gender, age in 2021, base (city, airport), and the four
# windows they fly with the destination airport for each.
#
# EVERY traveler flies in January and exactly four of the other seven windows,
# and the assignment is not uniform on purpose: the per-year month totals
# (Jan 12, Mar 9, Apr 10, May 3, Jun 4, Jul 6, Aug 11, Sep 5) are the ones the
# gap analysis against FRED called for. check_windows() asserts them, because
# an itinerary edit that quietly changed the mix would undo the whole point of
# this file without failing anything.
TRAVELERS = [
    {"name": "Phileas Fogg", "id_prefix": "OPF", "gender": "Male", "age": 42,
     "base": ("New York City", "JFK"),
     "legs": {"January": "LHR", "March": "FCO", "LateApril": "CDG", "LateAugust": "MCO", "September": "ATH"}},
    {"name": "Jean Passepartout", "id_prefix": "OPP", "gender": "Male", "age": 31,
     "base": ("New York City", "JFK"),
     "legs": {"January": "CDG", "March": "MAD", "LateApril": "AMS", "LateAugust": "SJU", "LateMay": "VIE"}},
    {"name": "Aouda", "id_prefix": "OPA", "gender": "Female", "age": 29,
     "base": ("Boston", "BOS"),
     "legs": {"January": "LIS", "March": "BCN", "LateApril": "DUB", "LateAugust": "MCO", "September": "FCO"}},
    {"name": "Captain Nemo", "id_prefix": "OPN", "gender": "Male", "age": 51,
     "base": ("Miami", "MIA"),
     "legs": {"January": "MAD", "LateApril": "LIS", "July": "CUN", "LateAugust": "CHS", "June": "SJU"}},
    {"name": "Pierre Aronnax", "id_prefix": "OPR", "gender": "Male", "age": 44,
     "base": ("Boston", "BOS"),
     "legs": {"January": "CPH", "March": "KEF", "July": "CUN", "LateAugust": "MCO", "LateMay": "MAD"}},
    {"name": "Ned Land", "id_prefix": "OPL", "gender": "Male", "age": 38,
     "base": ("San Francisco", "SFO"),
     "legs": {"January": "CDG", "March": "NRT", "LateApril": "BCN", "LateAugust": "CUN", "LateMay": "LIS"}},
    {"name": "Otto Lidenbrock", "id_prefix": "OPO", "gender": "Male", "age": 57,
     "base": ("Chicago", "ORD"),
     "legs": {"January": "CPH", "March": "LHR", "LateApril": "AMS", "July": "CUN", "September": "FCO"}},
    {"name": "Impey Barbicane", "id_prefix": "OPB", "gender": "Male", "age": 49,
     "base": ("Atlanta", "ATL"),
     "legs": {"January": "LHR", "LateApril": "FCO", "July": "CUN", "LateAugust": "SJU", "June": "MEX"}},
    {"name": "Michel Ardan", "id_prefix": "OPM", "gender": "Male", "age": 40,
     "base": ("Dallas", "DFW"),
     "legs": {"January": "CDG", "March": "MAD", "LateApril": "AMS", "LateAugust": "CUN", "September": "LHR"}},
    {"name": "Helena Glenarvan", "id_prefix": "OPH", "gender": "Female", "age": 36,
     "base": ("Seattle", "SEA"),
     "legs": {"January": "CDG", "March": "DUB", "LateApril": "AMS", "LateAugust": "MCO", "September": "LHR"}},
    {"name": "Mary Grant", "id_prefix": "OPG", "gender": "Female", "age": 27,
     "base": ("Philadelphia", "PHL"),
     "legs": {"January": "BCN", "March": "LIS", "July": "SJU", "LateAugust": "MCO", "June": "CUN"}},
    {"name": "Nadia Fedor", "id_prefix": "OPD", "gender": "Female", "age": 33,
     "base": ("Denver", "DEN"),
     "legs": {"January": "LHR", "LateApril": "KEF", "July": "CUN", "LateAugust": "MCO", "June": "MEX"}},
]


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

def nth_wednesday(year: int, month: int, which: int) -> date:
    """The 1st, 2nd ... or (which=-1) LAST Wednesday of a month.

    Every trip in this file departs on a Wednesday -- the premise is that these
    people fly when it is cheap, and that is the cheap day. Computing it rather
    than writing 240 dates by hand also means the pattern cannot rot: a typo'd
    date would be a Tuesday, and nothing would catch it."""
    if which > 0:
        d = date(year, month, 1)
        d += timedelta(days=(2 - d.weekday()) % 7)      # 2 == Wednesday
        return d + timedelta(days=7 * (which - 1))
    nxt = date(year + (month == 12), (month % 12) + 1, 1)
    d = nxt - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 2) % 7)


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

    `country_pair` IS SORTED ALPHABETICALLY, not (origin | destination) --
    JFK-CDG reads "FR|US", not "US|FR". Every origin in this file is a US
    airport, so the arrival country is whichever half is not "US" (and "US"
    itself on a domestic leg). Asserted rather than assumed, because the day
    someone adds a non-US base here this function silently starts lying.

    THIS EXISTS BECAUSE airports.json HAS NO COUNTRY CODE -- only a country
    NAME. The first version of this file fell back to None for every
    international leg, which meant all 240 trips joined to no M49 region and
    every one of these twelve came out with region entropy 0.0 over a single
    destination. The bug was invisible in the month distribution this cohort
    was built for and obvious the moment anyone looked at the region charts."""
    if not country_pair:
        return None
    halves = country_pair.split("|")
    if len(halves) != 2 or "US" not in halves:
        raise SystemExit(
            f"country_pair {country_pair!r} does not contain 'US' -- destination_iso2() "
            "assumes every origin in this file is a US airport, which is no longer true."
        )
    other = [h for h in halves if h != "US"]
    return other[0] if other else "US"


def eligible(codes) -> list[str]:
    return sorted(code for code in codes if code in CARRIER_NAMES)


def check_routes(routes: dict) -> None:
    """Every leg must be a route the data knows, flown by at least one airline
    in CARRIER_NAMES. Raises rather than warning, exactly as
    build_skiers_trips.check_routes does: an invented route is the one thing
    this project will not write, and a silent skip would quietly leave a
    traveler short a window and put the month counts back out."""
    problems = []
    for t in TRAVELERS:
        for window, dest in t["legs"].items():
            key = (t["base"][1], dest)
            if key not in routes:
                problems.append(f"{t['name']}: no {key[0]}-{key[1]} route in {ROUTES_PATH.name}")
            elif not eligible(routes[key]["carriers"]):
                problems.append(
                    f"{t['name']}: {key[0]}-{key[1]} is flown only by carriers outside "
                    f"CARRIER_NAMES ({', '.join(sorted(routes[key]['carriers']))})"
                )
    if problems:
        raise SystemExit("Route check failed:\n  " + "\n  ".join(problems))


def check_windows() -> None:
    """Every traveler flies January plus exactly three of the other four
    windows, and the per-year month totals are the ones the rebalance was sized
    for. Asserted rather than trusted: the whole reason this file exists is the
    month distribution, and an itinerary edit that quietly changed it would
    undo the thing without failing anything."""
    problems = []
    for t in TRAVELERS:
        if "January" not in t["legs"]:
            problems.append(f"{t['name']} has no January leg")
        if len(t["legs"]) != 5:
            problems.append(f"{t['name']} has {len(t['legs'])} windows, expected 5")
    counts = Counter(w for t in TRAVELERS for w in t["legs"])
    expected = {"January": 12, "March": 9, "LateApril": 10, "LateMay": 3, "June": 4,
                "July": 6, "LateAugust": 11, "September": 5}
    if dict(counts) != expected:
        problems.append(f"window counts {dict(sorted(counts.items()))} != {expected}")
    if problems:
        raise SystemExit("Window check failed:\n  " + "\n  ".join(problems))


def check_no_false_loyalty(trips: list[dict]) -> None:
    """No traveler may come out looking loyal to an airline. See the module
    docstring -- the rotation is a stand-in for "whoever was cheapest", and a
    Loyalist chip on one of these would be describing the rotation."""
    problems = []
    by_traveler: dict[str, Counter] = {}
    for t in trips:
        by_traveler.setdefault(t["traveler_name"], Counter())[t["carrier_name"]] += 1
    for name, counts in by_traveler.items():
        n = sum(counts.values())
        carrier, top = counts.most_common(1)[0]
        if top / n >= LOYALIST_THRESHOLD:
            problems.append(f"{name}: {top}/{n} on {carrier} ({top / n:.0%})")
    if problems:
        raise SystemExit(
            f"Carrier rotation produced a would-be Loyalist (>= {LOYALIST_THRESHOLD:.0%}):\n  "
            + "\n  ".join(problems)
        )


def check_no_overlap(trips: list[dict]) -> None:
    """No traveler may be in two places at once.

    Not hypothetical: LateAugust departs on the last Wednesday of August and
    runs five nights, which can end as late as September 5, and September was
    very nearly written as a first-Wednesday window. Eight windows resolved by
    rule rather than by hand is exactly the arrangement where that goes
    unnoticed, so it is checked."""
    by_traveler: dict[str, list[tuple[str, str, str]]] = {}
    for t in trips:
        by_traveler.setdefault(t["traveler_name"], []).append(
            (t["start_date"], t["end_date"], t["offpeak_window"]))
    problems = []
    for name, rows in by_traveler.items():
        rows.sort()
        for (s1, e1, w1), (s2, e2, w2) in zip(rows, rows[1:]):
            if s2 <= e1:
                problems.append(f"{name}: {w1} {s1}..{e1} overlaps {w2} {s2}..{e2}")
    if problems:
        raise SystemExit("Overlap check failed:\n  " + "\n  ".join(problems))


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------

def build_rows(airports: dict, routes: dict) -> tuple[list[dict], list[dict]]:
    trips, report = [], []

    for traveler in TRAVELERS:
        base_city, origin = traveler["base"]
        for year_index, year in enumerate(YEARS):
            for window, dest in sorted(traveler["legs"].items(),
                                       key=lambda kv: (WINDOWS[kv[0]][0], kv[0])):
                month, which, nights = WINDOWS[window]
                start = nth_wednesday(year, month, which)
                assert start.weekday() == 2, f"{start} is not a Wednesday"
                end = start + timedelta(days=nights)

                route = routes[(origin, dest)]
                distance, carriers = route["distance_km"], route["carriers"]
                codes = eligible(carriers)
                # Rotate year over year on the same route -- a fare-chaser does
                # not fly the same airline to Paris five Januaries running.
                # Deterministic: the year's index picks the operator.
                code = codes[year_index % len(codes)]

                arrival = airports[dest]
                domestic = arrival["country"] == "United States"
                flight, hotel = FARES["domestic" if domestic else "intl"]

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
                    "transportation_cost": flight,
                    "transportation_cost_raw": f"${flight:,.0f}",
                    "traveler_name": traveler["name"],
                    "traveler_age": traveler["age"] + (year - YEARS[0]),
                    "traveler_gender": traveler["gender"],
                    "traveler_nationality": "American",
                    "synthetic": True,
                    "carrier_name": CARRIER_NAMES[code],
                    "origin_airport": origin,
                    "destination_airport": dest,
                    "layover": False,
                    # Which low season this is. Kept on the row because the
                    # month alone does not say it: July is off-peak here
                    # because of where they went, not because July is quiet.
                    "offpeak_window": window,
                })
                report.append({
                    "trip_id": trips[-1]["trip_id"],
                    "traveler_name": traveler["name"],
                    "window": window,
                    "start_date": start.isoformat(),
                    "weekday": start.strftime("%A"),
                    "end_date": end.isoformat(),
                    "nights": nights,
                    "origin_airport": origin,
                    "destination_airport": dest,
                    "destination_city": arrival["city"],
                    "carrier_name": CARRIER_NAMES[code],
                    "distance_km": distance,
                    "transportation_cost": flight,
                    "route_carriers": ", ".join(sorted(carriers)),
                })

    check_no_false_loyalty(trips)
    check_no_overlap(trips)
    trips.sort(key=lambda t: (t["traveler_name"], t["start_date"]))
    report.sort(key=lambda r: (r["traveler_name"], r["start_date"]))
    return trips, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the off-peak (shoulder-season) travelers.")
    parser.add_argument("--report", action="store_true", help="print every trip")
    args = parser.parse_args()

    airports = load_airports()
    routes = load_routes()
    check_windows()
    check_routes(routes)
    trips, report = build_rows(airports, routes)

    declared_bases = {t["name"]: dict(base_city=t["base"][0], base_country="United States",
                                      base_country_code="US") for t in TRAVELERS}

    payload = {
        "source": (
            "Hand-authored travelers, written for this project -- see "
            "build_offpeak_trips.py. Twelve people who go to popular places in those "
            "places' low seasons: Europe in January and March, the Caribbean and "
            "Florida in July and late August. Every departure is a Wednesday."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED -- the people, dates, lodging and fares are "
            "invented, and every row carries synthetic: true so they can always be told "
            "apart from the Kaggle rows. The flying is not invented: every leg is a "
            "route present in airline_routes_enhanced.csv flown by a carrier that route "
            "data says serves it, and the build fails rather than writing a trip on a "
            "route nobody flies. The fares are deliberately at or below the dataset's "
            "25th percentile for the same kind of trip, because the premise is that "
            "these people fly when it is cheap. The carrier ROTATES year over year on "
            "each route, so none of them reads as an airline loyalist -- asserted in "
            "check_no_false_loyalty(). This cohort exists partly to correct the "
            "dataset's month distribution against FRED's ENPLANE series; see the module "
            "docstring. Merged into trips_enhanced.json by build_trips_enhanced.py."
        ),
        "windows": {w: {"month": m, "which_wednesday": k, "nights": n}
                    for w, (m, k, n) in WINDOWS.items()},
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
    print(f"{len(TRAVELERS)} off-peak travelers, {len(trips)} trips over "
          f"{YEARS[0]}-{YEARS[-1]}")
    print("  by month: " + "  ".join(
        f"{m}:{months.get(i, 0)}" for i, m in enumerate(
            "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1) if months.get(i)))
    print(f"  every departure a Wednesday: {all(r['weekday'] == 'Wednesday' for r in report)}")
    carriers = Counter(t["carrier_name"] for t in trips)
    print(f"  {len(carriers)} airlines, top share "
          f"{carriers.most_common(1)[0][1] / len(trips):.0%} "
          f"({carriers.most_common(1)[0][0]})")
    print(f"  {len({t['destination_city'] for t in trips})} destinations, "
          f"{len({t['origin_airport'] for t in trips})} home airports")

    if args.report:
        print()
        for t in TRAVELERS:
            rows = [r for r in report if r["traveler_name"] == t["name"]]
            legs = ", ".join(f"{r['window']}->{r['destination_airport']}" for r in rows[:4])
            print(f"  {t['name']:<20} {t['base'][1]}  {len(rows):2} trips  {legs}")

    print()
    print(f"Wrote -> {OUT_CSV}")
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
