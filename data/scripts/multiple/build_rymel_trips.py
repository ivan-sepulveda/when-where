"""
Derived from: a supplied flight log -- date, flight number and airport pair
              per leg, transcribed exactly as given -- plus two further
              trips supplied by description rather than by log line (Hawaii
              2020, Iceland 2026; see FLIGHTS).
Requires: data/reference/airports.json
          data/processed/multiple/airline_routes_enhanced.csv

Writes data/processed/multiple/rymel_traveler.json (merged by
build_trips_enhanced.py via SYNTHETIC_SOURCES) and rymel_trips.csv.

ONE ROW PER LEG, like build_gomez_trips.py and unlike the skiers. This is a
flight log, not an itinerary: the leg is the fact. A round trip is two rows,
so recording a return later never means editing a row that already describes
a flight that already happened.

NO GENDER OR NATIONALITY, AND COSTS ARE NULL. The log says what was flown
and nothing about who flew it, so none of that is invented here. Age is the
exception: it was supplied separately (see AGE_AT_LAST_LEG) rather than
derived from anything in the file.

THE HOME AIRPORT CHANGES PART-WAY THROUGH, which is the most interesting
thing in this log and is NOT an error. All twelve legs pair into six clean
round trips, and the first three depart Sacramento while the last three
depart Houston:

    2023-10-11  SMF->IAH   2023-10-18  IAH->SMF    7d   from SMF
    2023-12-01  SMF->IAH   2023-12-11  IAH->SMF   10d   from SMF
    2024-05-06  SMF->IAH   2024-05-15  IAH->SMF    9d   from SMF
    2025-01-17  IAH->SMF   2025-01-22  SMF->IAH    5d   from IAH
    2025-12-20  IAH->SMF   2025-12-28  SMF->IAH    8d   from IAH
    2026-05-06  IAH->SMF   2026-05-12  SMF->IAH    6d   from IAH

Read plainly, the flying moved from Sacramento to Houston somewhere between
May 2024 and January 2025.

THE DECLARED BASE IS Washington, D.C., supplied separately. Only the 2026
Iceland trip starts and ends there; the IAH-SMF log and the 2020 Hawaii
trip do not touch Washington at all. So this remains a PARTIAL record --
enough of his flying to be useful, not all of it -- and the SMF->IAH flip
above is a change in one endpoint of those particular trips rather than
evidence about where he lives.

HE IS NO LONGER A UNITED LOYALIST, and that is the rule working rather than
a mistake. On the twelve IAH-SMF legs alone he was 100% United. Adding four
Delta legs and two Hawaiian ones takes him to 12 of 18, or 67%, under
compute_traveler_tags.py's LOYALIST_THRESHOLD of 0.80, so the tag drops and
only "Multi Hub" (from the declared D.C. base) remains. Wider flying is
supposed to cost a loyalty claim; suppressing that would make the tag mean
nothing.

Usage:
    python build_rymel_trips.py
"""

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
ROUTES_PATH = DATA_DIR / "processed" / "multiple" / "airline_routes_enhanced.csv"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
OUT_JSON = PROCESSED_DIR / "rymel_traveler.json"
OUT_CSV = PROCESSED_DIR / "rymel_trips.csv"

TRAVELER = "Lord Rymel"
ID_PREFIX = "LR"          # unused by every other traveler in trips_enhanced.json

CARRIERS = {
    "UA": "United Air Lines Inc.",
    "DL": "Delta Air Lines Inc.",
    "HA": "Hawaiian Airlines Inc.",
}

# Only the countries this log actually reaches. A leg to anywhere else fails
# the build rather than guessing a code.
COUNTRY_CODES = {"United States": "US", "Iceland": "IS"}

# Ivan's call, and it does NOT come from the log: every leg below is
# IAH<->SMF and there is no Washington flight in the file at all. The log is
# therefore a partial one -- whatever gets him to and from D.C. isn't in it.
# Spelled to match AIRLINE_HUBS in compute_traveler_tags.py, which knows
# "Washington, D.C." (IAD + DCA) and not "Washington DC".
DECLARED_BASE = {
    "base_city": "Washington, D.C.",
    "base_country": "United States",
    "base_country_code": "US",
}

# Ivan's call. Applied as an age on the LAST leg and counted backwards with
# the calendar, so he is 25 in 2026 and 22 when the log opens in 2023 --
# every other traveler in this dataset ages across their history, and a
# single frozen number over three years would be the odd one out.
AGE_AT_LAST_LEG = 25

# (date, carrier code, flight number, origin, destination) -- oldest first.
#
# The IAH<->SMF legs are the supplied log, transcribed as given; UA 2031 and
# UA 1148 each appear twice on different dates, which is ordinary. Flight
# numbers are recorded only where the log gave one -- the Hawaii and Iceland
# legs were described by route and airline, not by flight number, so theirs
# are None rather than invented.
#
# HAWAII, 2020. A week on Oahu out of Sacramento, nonstop both ways on
# Hawaiian, which flies SMF-HNL in the route data. February deliberately:
# it is the only part of 2020 when this trip is unremarkable.
#
# ICELAND, AUGUST 2026, for the total eclipse of the 12th. Routed
# Washington-JFK-Keflavik and back, all Delta. The brief said Newark, but
# DC-EWR is United-only in the route data and EWR-KEF is Icelandair-only --
# Delta's Iceland service runs from JFK -- so keeping the airline meant
# moving the connection. Both JFK legs are same-day connections, which is
# why trip ids get a leg suffix below.
FLIGHTS = [
    ("2020-02-08", "HA", None, "SMF", "HNL"),
    ("2020-02-15", "HA", None, "HNL", "SMF"),
    ("2023-10-11", "UA", "UA 2031", "SMF", "IAH"),
    ("2023-10-18", "UA", "UA 2456", "IAH", "SMF"),
    ("2023-12-01", "UA", "UA 2031", "SMF", "IAH"),
    ("2023-12-11", "UA", "UA 1268", "IAH", "SMF"),
    ("2024-05-06", "UA", "UA 1794", "SMF", "IAH"),
    ("2024-05-15", "UA", "UA 1830", "IAH", "SMF"),
    ("2025-01-17", "UA", "UA 2274", "IAH", "SMF"),
    ("2025-01-22", "UA", "UA 1780", "SMF", "IAH"),
    ("2025-12-20", "UA", "UA 1148", "IAH", "SMF"),
    ("2025-12-28", "UA", "UA 1318", "SMF", "IAH"),
    ("2026-05-06", "UA", "UA 1148", "IAH", "SMF"),
    ("2026-05-12", "UA", "UA 1949", "SMF", "IAH"),
    ("2026-08-08", "DL", None, "DCA", "JFK"),
    ("2026-08-08", "DL", None, "JFK", "KEF"),
    ("2026-08-15", "DL", None, "KEF", "JFK"),
    ("2026-08-15", "DL", None, "JFK", "DCA"),
]

CSV_COLUMNS = ["leg", "trip_id", "date", "flight_number", "origin_airport",
               "destination_airport", "destination_city", "carrier_name",
               "distance_km", "route_carriers"]


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


def build_rows(airports, routes):
    trips, report, warnings = [], [], []
    last_year = max(date.fromisoformat(f[0]).year for f in FLIGHTS)
    # A same-day connection puts two legs on one date, so ids get a "-2",
    # "-3" suffix in those cases only. Single-leg days keep the plain
    # PREFIX-DATE id every existing row already uses.
    per_day = Counter(f[0] for f in FLIGHTS)
    seen_on_day = Counter()

    for index, (day, carrier_code, flight, origin, destination) in enumerate(FLIGHTS, start=1):
        if carrier_code not in CARRIERS:
            raise SystemExit(f"leg {index}: unknown carrier code {carrier_code!r}")

        for code in (origin, destination):
            if code not in airports:
                raise SystemExit(f"leg {index}: {code} is not in airports.json")

        distance, carriers = routes.get((origin, destination), (None, set()))
        if not carriers:
            # Not fatal: the log records a flight that was taken, and a route
            # file that has never seen it is the route file's gap.
            warnings.append(f"leg {index}: no {origin}-{destination} route in {ROUTES_PATH.name}")
        elif carrier_code not in carriers:
            warnings.append(
                f"leg {index}: {carrier_code} is not listed on {origin}-{destination} "
                f"(route data lists {', '.join(sorted(carriers))})"
            )

        arrival = airports[destination]
        if arrival["country"] not in COUNTRY_CODES:
            raise SystemExit(f"leg {index}: no country code for {arrival['country']!r}")
        start = date.fromisoformat(day)
        seen_on_day[day] += 1
        trip_id = f"{ID_PREFIX}-{day}"
        if per_day[day] > 1:
            trip_id = f"{trip_id}-{seen_on_day[day]}"

        trips.append({
            "trip_id": trip_id,
            "destination_raw": f"{arrival['city']}, {arrival['country']}",
            "destination_city": arrival["city"],
            "destination_country": arrival["country"],
            "destination_country_code": COUNTRY_CODES[arrival["country"]],
            "destination_kind": "city",
            "start_date": day,
            "start_date_raw": day,
            "end_date": day,
            "end_date_raw": day,
            "duration_days": 0,
            "duration_raw": "0 days",
            "accommodation_type": None,
            "accommodation_cost": None,
            "accommodation_cost_raw": None,
            "transportation_type": "Flight",
            "transportation_cost": None,
            "transportation_cost_raw": None,
            "traveler_name": TRAVELER,
            "traveler_age": AGE_AT_LAST_LEG - (last_year - start.year),
            "traveler_gender": None,
            "traveler_nationality": None,
            "synthetic": True,
            "carrier_name": CARRIERS[carrier_code],
            "carrier_code": carrier_code,
            "origin_airport": origin,
            "destination_airport": destination,
        })
        report.append({
            "leg": index, "trip_id": trip_id, "date": day, "flight_number": flight,
            "origin_airport": origin, "destination_airport": destination,
            "destination_city": arrival["city"], "carrier_name": CARRIERS[carrier_code],
            "distance_km": distance, "route_carriers": ", ".join(sorted(carriers)),
        })
    return trips, report, warnings


def main():
    airports = load_airports()
    routes = load_routes()
    trips, report, warnings = build_rows(airports, routes)

    payload = {
        "source": (
            "A supplied flight log -- date, flight number and airport pair per leg, "
            "transcribed exactly as given. See build_rymel_trips.py."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "One row per FLIGHT LEG, not per trip: a round trip is two rows. Costs are "
            "null because none were recorded, and age/gender/nationality are absent "
            "rather than invented. The home airport changes part-way through the log -- "
            "the first three round trips depart Sacramento, the last three depart "
            "Houston. The declared base is neither: it is Washington, D.C., supplied "
            "separately, and NO leg in this log touches Washington -- so this is a "
            "partial log, the IAH-SMF part of his flying rather than all of it. Age was "
            "supplied too (25 on the last leg, counted back with the calendar); gender "
            "and nationality were not, and are absent rather than invented. Merged into "
            "trips_enhanced.json by build_trips_enhanced.py."
        ),
        "carrier_preference": sorted(CARRIERS.values()),
        "declared_bases": {TRAVELER: DECLARED_BASE},
        "total_travelers": 1,
        "total_trips": len(trips),
        "trips": trips,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(report)

    print(f"Wrote {len(trips)} legs for {TRAVELER} -> {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")
    by_dest = {}
    for t in trips:
        by_dest[t["destination_city"]] = by_dest.get(t["destination_city"], 0) + 1
    print(f"  legs by arrival city: {by_dest}")
    print(f"  date range: {trips[0]['start_date']} .. {trips[-1]['start_date']}")
    for w in warnings:
        print(f"  WARNING: {w}")
    if not warnings:
        print("  every leg matches a real route flown by its carrier in the route data")


if __name__ == "__main__":
    main()
