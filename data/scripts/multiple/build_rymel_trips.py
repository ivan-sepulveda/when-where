"""
Derived from: a supplied flight log -- date, flight number and airport pair
              per leg, transcribed exactly as given.
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

THE DECLARED BASE IS NEITHER OF THEM. It is Washington, D.C., supplied
separately -- and no leg in this log touches Washington. So the log is
partial: it is the IAH-SMF part of his flying and not the whole of it, and
the SMF->IAH flip above is a change in one endpoint of these particular
trips rather than evidence about where he lives. That is recorded here
instead of being quietly reconciled, because a base that contradicts every
row in the file is exactly the kind of thing a reader should be told once,
loudly, rather than discover later.

Usage:
    python build_rymel_trips.py
"""

import csv
import json
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
UNITED = "United Air Lines Inc."

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

# (date, flight number, origin, destination) -- exactly as supplied, oldest
# first. Every leg is United; UA 2031 and UA 1148 each appear twice, on
# different dates, which is ordinary.
FLIGHTS = [
    ("2023-10-11", "UA 2031", "SMF", "IAH"),
    ("2023-10-18", "UA 2456", "IAH", "SMF"),
    ("2023-12-01", "UA 2031", "SMF", "IAH"),
    ("2023-12-11", "UA 1268", "IAH", "SMF"),
    ("2024-05-06", "UA 1794", "SMF", "IAH"),
    ("2024-05-15", "UA 1830", "IAH", "SMF"),
    ("2025-01-17", "UA 2274", "IAH", "SMF"),
    ("2025-01-22", "UA 1780", "SMF", "IAH"),
    ("2025-12-20", "UA 1148", "IAH", "SMF"),
    ("2025-12-28", "UA 1318", "SMF", "IAH"),
    ("2026-05-06", "UA 1148", "IAH", "SMF"),
    ("2026-05-12", "UA 1949", "SMF", "IAH"),
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
    seen_dates = set()
    last_year = max(date.fromisoformat(f[0]).year for f in FLIGHTS)

    for index, (day, flight, origin, destination) in enumerate(FLIGHTS, start=1):
        if day in seen_dates:
            raise SystemExit(f"leg {index}: duplicate date {day} -- trip_id would collide")
        seen_dates.add(day)

        for code in (origin, destination):
            if code not in airports:
                raise SystemExit(f"leg {index}: {code} is not in airports.json")

        distance, carriers = routes.get((origin, destination), (None, set()))
        if not carriers:
            # Not fatal: the log records a flight that was taken, and a route
            # file that has never seen it is the route file's gap.
            warnings.append(f"leg {index}: no {origin}-{destination} route in {ROUTES_PATH.name}")
        elif "UA" not in carriers:
            warnings.append(
                f"leg {index}: UA is not listed on {origin}-{destination} "
                f"(route data lists {', '.join(sorted(carriers))})"
            )

        arrival = airports[destination]
        start = date.fromisoformat(day)
        trip_id = f"{ID_PREFIX}-{day}"

        trips.append({
            "trip_id": trip_id,
            "destination_raw": f"{arrival['city']}, {arrival['country']}",
            "destination_city": arrival["city"],
            "destination_country": arrival["country"],
            "destination_country_code": "US",
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
            "carrier_name": UNITED,
            "carrier_code": "UA",
            "origin_airport": origin,
            "destination_airport": destination,
        })
        report.append({
            "leg": index, "trip_id": trip_id, "date": day, "flight_number": flight,
            "origin_airport": origin, "destination_airport": destination,
            "destination_city": arrival["city"], "carrier_name": UNITED,
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
        "carrier_preference": [UNITED],
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
        print("  every leg matches a real United route in the route data")


if __name__ == "__main__":
    main()
