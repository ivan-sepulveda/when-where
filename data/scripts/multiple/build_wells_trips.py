"""
Derived from: nothing -- ten AUTHORED travelers, in the same spirit as
              build_hemingway_trips.py and build_raccoons_trips.py.
Requires: data/reference/airports.json
          data/processed/multiple/airline_routes_enhanced.csv
          classify_trip.py (for the Christmas rule)
          compute_traveler_tags.py (for the United hub list)

Writes data/processed/multiple/wells_traveler.json (and .csv), merged by
build_trips_enhanced.py via SYNTHETIC_SOURCES.

WHY THIS EXISTS. Ten H.G. Wells characters, all American per the brief, all
based at a United hub, each flying home for Christmas in each of the last five
years. One holiday, one route, one carrier, five years: 50 trips.

THE POINT OF THE COHORT is a clean single-carrier, single-hub signal. Every
traveler flies United only, exactly 5 times, from a city that is a United hub
-- which clears both LOYALIST_MIN_TRIPS (5) and LOYALIST_THRESHOLD (0.80) in
compute_traveler_tags.py, so all ten should come back tagged both "United
Loyalist" and "United Hub". All seven mainland United hubs are represented.

THE HUB CLAIM IS CHECKED, NOT ASSERTED. "Based around United hubs" is only
true if base_city is spelled the way compute_traveler_tags.AIRLINE_HUBS spells
it -- that table is keyed by city STRING, so "Newark" reads as a different
place from "New York City" and silently earns no hub tag. (That is not
hypothetical: Robert Cohn in build_hemingway_trips.py is based in "Newark" and
flies EWR, and gets no United Hub chip because of it.) check_hubs() below
reads the real table and raises, so this cohort cannot drift into the same
hole.

CHRISTMAS IS THE ONLY HOLIDAY HERE, and the window is checked against the
classifier rather than eyeballed: classify_trip.CHRISTMAS_DAYS counts Dec 24
OR 25, so a window straddling neither would build cleanly and then silently
fail to tag. The destination country is checked against CHRISTMAS_COUNTRIES
for the same reason.

Usage:
    python build_wells_trips.py
"""

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_trip import CHRISTMAS_COUNTRIES, CHRISTMAS_DAYS
from compute_traveler_tags import AIRLINE_HUBS, LOYALIST_MIN_TRIPS

DATA_DIR = Path(__file__).resolve().parent.parent.parent
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
ROUTES_PATH = DATA_DIR / "processed" / "multiple" / "airline_routes_enhanced.csv"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
OUT_JSON = PROCESSED_DIR / "wells_traveler.json"
OUT_CSV = PROCESSED_DIR / "wells_trips.csv"

YEARS = [2021, 2022, 2023, 2024, 2025]
NATIONALITY = "American"
CARRIER = "UA"
CARRIER_NAME = "United Air Lines Inc."

# Days before Dec 25 to arrive, then nights away: in on the 22nd, out on the
# 27th. Covers both days classify_trip counts -- asserted in build_rows().
DAYS_BEFORE, NIGHTS = 3, 5

# base_city MUST be spelled as compute_traveler_tags.AIRLINE_HUBS spells it;
# check_hubs() enforces that against the real table.
# Four of the ten are BENCHED, not deleted -- their entries stay in the table
# below and this set is the only thing keeping them out of the build.
#
# WHY: every one of these ten flies home for Christmas, so this cohort is ten
# December trips a year and nothing else, and December was the dataset's most
# over-represented month against FRED's ENPLANE series (see
# data/scripts/multiple/build_offpeak_trips.py's docstring and the
# trip_seasonality notes). Trimming the cohort's WEIGHT was the least
# destructive lever available: each remaining traveler keeps their exact
# itinerary, the pattern is unchanged, there is simply less of it. Deleting
# trips from individual travelers, or shortening YEARS, would have edited the
# pattern itself.
#
# WHICH FOUR, and it was not arbitrary: four men from four different United
# hubs, chosen so that both women in the cohort stay, the Pollys stay together
# (same base, same route, same day -- they read as one household and splitting
# them would have invented a separation), and five distinct hubs survive.
# SFO and DEN leave the cohort entirely; the tag rules do not depend on this
# file for hub coverage.
#
# EMPTY THIS SET TO RESTORE ALL TEN. One line, nothing else to undo.
BENCHED = frozenset({
    "Edward Prendick",     # SFO
    "William Moreau",      # IAD -- Helen Walshingham still flies IAD
    "Arthur Bedford",      # EWR -- Arthur Kipps still flies EWR
    "Joseph Cavor",        # DEN
})

ALL_TRAVELERS = [
    {"name": "Edward Prendick", "id_prefix": "WEP", "gender": "Male", "age": 36,
     "base_city": "San Francisco", "origin": "SFO", "destination": "BOS",
     "hotel": 1450.0, "flight": 385.0},
    {"name": "William Moreau", "id_prefix": "WWM", "gender": "Male", "age": 58,
     "base_city": "Washington, D.C.", "origin": "IAD", "destination": "CHS",
     "hotel": 1300.0, "flight": 295.0},
    {"name": "Montgomery", "id_prefix": "WMG", "gender": "Male", "age": 41,
     "base_city": "Houston", "origin": "IAH", "destination": "MSY",
     "hotel": 980.0, "flight": 215.0},
    {"name": "Arthur Bedford", "id_prefix": "WAB", "gender": "Male", "age": 34,
     "base_city": "New York City", "origin": "EWR", "destination": "BUF",
     "hotel": 870.0, "flight": 240.0},
    {"name": "Joseph Cavor", "id_prefix": "WJC", "gender": "Male", "age": 52,
     "base_city": "Denver", "origin": "DEN", "destination": "MSP",
     "hotel": 1020.0, "flight": 265.0},
    # The Pollys are married and fly together -- same hub, same route, same
    # dates, two rows. See the note in main()'s payload.
    {"name": "Alfred Polly", "id_prefix": "WAP", "gender": "Male", "age": 39,
     "base_city": "Chicago", "origin": "ORD", "destination": "PIT",
     "hotel": 760.0, "flight": 190.0},
    {"name": "Miriam Polly", "id_prefix": "WMP", "gender": "Female", "age": 38,
     "base_city": "Chicago", "origin": "ORD", "destination": "PIT",
     "hotel": 760.0, "flight": 190.0},
    {"name": "Arthur Kipps", "id_prefix": "WAK", "gender": "Male", "age": 29,
     "base_city": "New York City", "origin": "EWR", "destination": "RDU",
     "hotel": 890.0, "flight": 225.0},
    {"name": "Helen Walshingham", "id_prefix": "WHW", "gender": "Female", "age": 31,
     "base_city": "Washington, D.C.", "origin": "IAD", "destination": "BOS",
     "hotel": 1180.0, "flight": 255.0},
    {"name": "Herbert George Wells", "id_prefix": "WHG", "gender": "Male", "age": 47,
     "base_city": "Los Angeles", "origin": "LAX", "destination": "SEA",
     "hotel": 1240.0, "flight": 275.0},
]

# What the build actually uses. Everything below this line -- route checks,
# rows, the summary -- goes through TRAVELERS and never through ALL_TRAVELERS,
# so a benched traveler is invisible to all of it.
TRAVELERS = [t for t in ALL_TRAVELERS if t["name"] not in BENCHED]

assert len(TRAVELERS) == len(ALL_TRAVELERS) - len(BENCHED), (
    "a name in BENCHED does not match any traveler in ALL_TRAVELERS -- a typo there "
    "would silently bench nobody"
)

CSV_COLUMNS = ["trip_id", "traveler_name", "base_city", "start_date", "end_date",
               "nights", "origin_airport", "destination_airport",
               "destination_city", "carrier_name", "distance_km", "route_carriers"]


def load_airports():
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        return {a["iata"]: a for a in json.load(f)["airports"] if a.get("iata")}


def load_routes():
    routes = {}
    with ROUTES_PATH.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["Departure"], row["Destination"])
            distance, carriers = routes.get(key, (None, set()))
            carriers.add(row["Airline ID"])
            if distance is None and row.get("distance_km"):
                distance = float(row["distance_km"])
            routes[key] = (distance, carriers)
    return routes


def check_hubs():
    """The brief was "based around United hubs", so verify it against the
    table that actually decides -- both that the city is a United hub city and
    that the origin airport is THAT city's hub airport. A right city with the
    wrong airport would still tag, but it would be a lie in the data."""
    united = AIRLINE_HUBS["United"]
    problems = []
    for traveler in TRAVELERS:
        city, origin = traveler["base_city"], traveler["origin"]
        if city not in united:
            problems.append(
                f"{traveler['name']}: base_city {city!r} is not a United hub city. "
                f"AIRLINE_HUBS['United'] has {', '.join(sorted(united))}"
            )
        elif origin not in united[city]:
            problems.append(
                f"{traveler['name']}: {origin} is not United's hub airport for "
                f"{city} ({', '.join(united[city])})"
            )
    if len(YEARS) < LOYALIST_MIN_TRIPS:
        problems.append(
            f"{len(YEARS)} trips each is under LOYALIST_MIN_TRIPS "
            f"({LOYALIST_MIN_TRIPS}) -- nobody would be tagged a United Loyalist"
        )
    if problems:
        raise SystemExit("Hub check failed:\n  " + "\n  ".join(problems))


def check_routes(routes):
    problems = []
    for traveler in TRAVELERS:
        key = (traveler["origin"], traveler["destination"])
        if key not in routes:
            problems.append(f"{traveler['name']}: no {key[0]}-{key[1]} route")
        elif CARRIER not in routes[key][1]:
            problems.append(
                f"{traveler['name']}: {CARRIER} does not fly {key[0]}-{key[1]} "
                f"(route data lists {', '.join(sorted(routes[key][1]))})"
            )
    if problems:
        raise SystemExit("Route check failed:\n  " + "\n  ".join(problems))


def build_rows(airports, routes):
    trips, report = [], []
    for traveler in TRAVELERS:
        origin, destination = traveler["origin"], traveler["destination"]
        arrival_airport = airports[destination]
        distance, route_carriers = routes[(origin, destination)]

        if arrival_airport["country"] not in CHRISTMAS_COUNTRIES:
            raise SystemExit(
                f"{traveler['name']}: {arrival_airport['country']} is not in "
                f"CHRISTMAS_COUNTRIES -- classify_trip would not tag this"
            )

        for year in YEARS:
            start = date(year, 12, 25) - timedelta(days=DAYS_BEFORE)
            end = start + timedelta(days=NIGHTS)
            span = {start + timedelta(days=n) for n in range(NIGHTS + 1)}
            if not any(d.month == 12 and d.day in CHRISTMAS_DAYS for d in span):
                raise SystemExit(
                    f"{traveler['name']} {year}: trip {start}..{end} covers no day "
                    f"in CHRISTMAS_DAYS {CHRISTMAS_DAYS} -- it would not be tagged"
                )

            trips.append({
                "trip_id": f"{traveler['id_prefix']}-{start.isoformat()}",
                "destination_raw": f"{arrival_airport['city']}, {arrival_airport['country']}",
                "destination_city": arrival_airport["city"],
                "destination_country": arrival_airport["country"],
                "destination_country_code": "US",
                "destination_kind": "city",
                "start_date": start.isoformat(),
                "start_date_raw": start.isoformat(),
                "end_date": end.isoformat(),
                "end_date_raw": end.isoformat(),
                "duration_days": NIGHTS,
                "duration_raw": f"{NIGHTS} days",
                "accommodation_type": "Hotel",
                "accommodation_cost": traveler["hotel"],
                "accommodation_cost_raw": f"${traveler['hotel']:,.0f}",
                "transportation_type": "Flight",
                "transportation_cost": traveler["flight"],
                "transportation_cost_raw": f"${traveler['flight']:,.0f}",
                "traveler_name": traveler["name"],
                "traveler_age": traveler["age"] + (year - YEARS[0]),
                "traveler_gender": traveler["gender"],
                "traveler_nationality": NATIONALITY,
                "synthetic": True,
                "carrier_name": CARRIER_NAME,
                "origin_airport": origin,
                "destination_airport": destination,
            })
            report.append({
                "trip_id": trips[-1]["trip_id"], "traveler_name": traveler["name"],
                "base_city": traveler["base_city"], "start_date": start.isoformat(),
                "end_date": end.isoformat(), "nights": NIGHTS,
                "origin_airport": origin, "destination_airport": destination,
                "destination_city": arrival_airport["city"],
                "carrier_name": CARRIER_NAME, "distance_km": distance,
                "route_carriers": ", ".join(sorted(route_carriers)),
            })

    seen = set()
    for trip in trips:
        if trip["trip_id"] in seen:
            raise SystemExit(f"duplicate trip_id {trip['trip_id']}")
        seen.add(trip["trip_id"])

    trips.sort(key=lambda t: (t["traveler_name"], t["start_date"]))
    report.sort(key=lambda r: (r["traveler_name"], r["start_date"]))
    return trips, report


def main():
    airports = load_airports()
    routes = load_routes()
    check_hubs()
    check_routes(routes)
    trips, report = build_rows(airports, routes)

    payload = {
        "source": (
            "Hand-authored travelers, written for this project -- see "
            "build_wells_trips.py. Ten H.G. Wells characters, all American, each "
            "based at a United hub and flying home for Christmas every year."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED -- the people, lodging and costs are "
            "invented, and every row carries synthetic: true. The flying is not: "
            "every origin-destination pair is served by United in "
            "airline_routes_enhanced.csv and the build fails otherwise. Each "
            "traveler's base city is checked against compute_traveler_tags."
            "AIRLINE_HUBS['United'], so the hub claim is verified rather than "
            "asserted. The Christmas window (Dec 22-27) is checked against "
            "classify_trip.CHRISTMAS_DAYS, so these trips cannot build cleanly "
            "and then fail to earn a Holiday Trip tag. Alfred and Miriam Polly "
            "are married and deliberately share an itinerary -- identical route "
            "and dates, two rows -- which is what a couple's flight history "
            "looks like, not a duplication bug. Merged into trips_enhanced.json "
            "by build_trips_enhanced.py."
        ),
        "carrier_preference": [CARRIER_NAME],
        "declared_bases": {t["name"]: dict(base_city=t["base_city"],
                                           base_country="United States",
                                           base_country_code="US")
                           for t in TRAVELERS},
        "total_travelers": len(TRAVELERS),
        "total_trips": len(trips),
        "trips": trips,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Wrote {len(trips)} trips from {len(TRAVELERS)} travelers -> {OUT_JSON}")

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(report)
    print(f"Wrote {OUT_CSV}")

    for traveler in TRAVELERS:
        own = [t for t in trips if t["traveler_name"] == traveler["name"]]
        print(f"  {traveler['name']:22} {traveler['base_city']:16} "
              f"{traveler['origin']}->{traveler['destination']}  {len(own)} trips  "
              f"{own[0]['start_date']} .. {own[-1]['end_date']}")


if __name__ == "__main__":
    main()
