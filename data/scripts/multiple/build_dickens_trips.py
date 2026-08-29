"""
Derived from: nothing -- fourteen AUTHORED travelers, in the same spirit as
              build_hemingway_trips.py and build_wells_trips.py.
Requires: data/reference/airports.json
          data/processed/multiple/airline_routes_enhanced.csv

Writes data/processed/multiple/dickens_traveler.json (and .csv), merged by
build_trips_enhanced.py via SYNTHETIC_SOURCES.

WHY THIS EXISTS. Fourteen Dickens characters, all American, all based in New
York City, each taking one long European summer holiday a year for five years:
70 trips. The dataset's transatlantic leisure travel was thin, and what there
was clustered on London and Paris.

DIRECT FLIGHTS ONLY, AND THAT IS THE BINDING CONSTRAINT. Every trip is a
nonstop from JFK or EWR flown by the named carrier, verified against
airline_routes_enhanced.csv; check_routes() raises rather than warning. LGA has
no transatlantic service in the route data at all, so nobody flies from it.

TWO REQUESTED CITIES ARE ABSENT, DELIBERATELY. Palermo (PMO) and Malaga (AGP)
have NO nonstop from JFK or EWR anywhere in the route data. Rather than invent
the route or quietly route them through a hub, they are simply not in this
cohort. Everything else asked for is here: Barcelona, Nice, Lisbon, Porto,
Paris, Madrid, Milan and Rome.

CARRIER PER TRAVELER, CITIES ROTATING. Each person keeps one airline across all
five summers but goes somewhere different each year, which is what a real
frequent leisure traveler looks like -- loyalty to a carrier, not to a city.
Every rotation was chosen from what that carrier actually flies from that
airport, so the itineraries differ in shape as well as in name: the Delta and
American travelers out of JFK can reach Athens and Nice; the United travelers
out of EWR can reach Bilbao, Porto and the smaller UK and German cities.

ROSE AND HARRY MAYLIE MARRY at the end of Oliver Twist and travel together --
same airport, same carrier, same cities, same dates, two rows. As with the
Pollys in build_wells_trips.py, that is a couple's flight history, not a
duplication bug.

Usage:
    python build_dickens_trips.py
"""

import csv
import json
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
ROUTES_PATH = DATA_DIR / "processed" / "multiple" / "airline_routes_enhanced.csv"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
OUT_JSON = PROCESSED_DIR / "dickens_traveler.json"
OUT_CSV = PROCESSED_DIR / "dickens_trips.csv"

YEARS = [2021, 2022, 2023, 2024, 2025]
NATIONALITY = "American"
BASE_CITY = "New York City"   # spelled as compute_traveler_tags.AIRLINE_HUBS spells it

CARRIERS = {
    "AA": "American Airlines Inc.",
    "BA": "British Airways Plc",
    "DL": "Delta Air Lines Inc.",
    "TP": "TAP-TAP Air Portugal",
    "UA": "United Air Lines Inc.",
}

# Country -> ISO2, written out rather than inferred. The inference used
# elsewhere in this project is known to be wrong on some rows (it takes a
# journey's foreign country rather than the leg's arrival country), and a
# silently wrong code is worse than a build that refuses to run. Every
# destination country is asserted to be in here.
COUNTRY_CODES = {
    "Belgium": "BE", "France": "FR", "Germany": "DE", "Greece": "GR",
    "Ireland": "IE", "Italy": "IT", "Netherlands": "NL", "Portugal": "PT",
    "Spain": "ES", "Switzerland": "CH", "United Kingdom": "GB",
}

# Summer only. Every trip must start AND end inside these months -- asserted in
# build_rows(), because a 15-night trip leaving in late August can walk out of
# summer without anyone noticing.
SUMMER_MONTHS = (6, 7, 8)

# Departures drift year to year rather than landing on the same date five times;
# indexed by position in YEARS. Small enough to stay inside summer.
YEAR_SHIFT = [0, 2, -3, 4, 1]

TRAVELERS = [
    {"name": "Oliver Twist", "id_prefix": "DOT", "gender": "Male", "age": 24,
     "origin": "JFK", "carrier": "DL", "depart": (6, 12),
     "cities": ["LHR", "CDG", "FCO", "BCN", "AMS"], "nights": [12, 14, 11, 13, 15],
     "hotel": 2400.0, "flight": 890.0},
    {"name": "Jack Dawkins", "id_prefix": "DJD", "gender": "Male", "age": 22,
     "origin": "JFK", "carrier": "DL", "depart": (7, 3),
     "cities": ["BCN", "LIS", "NCE", "MXP", "ATH"], "nights": [10, 12, 14, 11, 13],
     "hotel": 1750.0, "flight": 810.0},
    {"name": "Charley Bates", "id_prefix": "DCB", "gender": "Male", "age": 23,
     "origin": "JFK", "carrier": "AA", "depart": (7, 18),
     "cities": ["MAD", "BCN", "FCO", "MXP", "CDG"], "nights": [14, 11, 13, 15, 10],
     "hotel": 1900.0, "flight": 845.0},
    {"name": "Toby Crackit", "id_prefix": "DTC", "gender": "Male", "age": 35,
     "origin": "EWR", "carrier": "UA", "depart": (8, 2),
     "cities": ["LIS", "BCN", "MAD", "FCO", "MXP"], "nights": [11, 13, 10, 12, 14],
     "hotel": 2050.0, "flight": 875.0},
    {"name": "Mr. Brownlow", "id_prefix": "DMB", "gender": "Male", "age": 63,
     "origin": "JFK", "carrier": "AA", "depart": (6, 20),
     "cities": ["LHR", "DUB", "MAN", "ZRH", "CDG"], "nights": [15, 10, 12, 14, 11],
     "hotel": 3300.0, "flight": 1150.0},
    # Rose and Harry marry at the end of the novel and fly together.
    {"name": "Rose Maylie", "id_prefix": "DRM", "gender": "Female", "age": 27,
     "origin": "JFK", "carrier": "BA", "depart": (7, 10),
     "cities": ["LHR", "LCY", "MAN", "CDG", "FCO"], "nights": [13, 15, 11, 10, 12],
     "hotel": 2700.0, "flight": 960.0},
    {"name": "Harry Maylie", "id_prefix": "DHM", "gender": "Male", "age": 30,
     "origin": "JFK", "carrier": "BA", "depart": (7, 10),
     "cities": ["LHR", "LCY", "MAN", "CDG", "FCO"], "nights": [13, 15, 11, 10, 12],
     "hotel": 2700.0, "flight": 960.0},
    {"name": "Bill Sikes", "id_prefix": "DBS", "gender": "Male", "age": 38,
     "origin": "EWR", "carrier": "UA", "depart": (6, 26),
     "cities": ["DUB", "EDI", "GLA", "MAN", "BFS"], "nights": [10, 12, 11, 13, 10],
     "hotel": 1500.0, "flight": 720.0},
    {"name": "Nancy Sikes", "id_prefix": "DNS", "gender": "Female", "age": 26,
     "origin": "JFK", "carrier": "DL", "depart": (8, 8),
     "cities": ["NCE", "BCN", "LIS", "VCE", "MAD"], "nights": [12, 14, 10, 13, 11],
     "hotel": 2150.0, "flight": 830.0},
    {"name": "Edwin Leeford", "id_prefix": "DEL", "gender": "Male", "age": 55,
     "origin": "EWR", "carrier": "UA", "depart": (7, 25),
     "cities": ["AMS", "BRU", "FRA", "TXL", "HAM"], "nights": [13, 11, 15, 12, 10],
     "hotel": 2600.0, "flight": 905.0},
    {"name": "Estella Havisham", "id_prefix": "DEH", "gender": "Female", "age": 29,
     "origin": "EWR", "carrier": "UA", "depart": (6, 15),
     "cities": ["BCN", "MAD", "BIO", "LIS", "MXP"], "nights": [14, 12, 13, 15, 11],
     "hotel": 2850.0, "flight": 920.0},
    {"name": "Miss Havisham", "id_prefix": "DMH", "gender": "Female", "age": 68,
     "origin": "EWR", "carrier": "UA", "depart": (7, 6),
     "cities": ["FCO", "MXP", "VCE", "ZRH", "GVA"], "nights": [15, 13, 14, 12, 15],
     "hotel": 3600.0, "flight": 1080.0},
    {"name": "Abel Magwitch", "id_prefix": "DAM", "gender": "Male", "age": 61,
     "origin": "EWR", "carrier": "TP", "depart": (8, 12),
     # TAP flies EWR to exactly two places, so Magwitch alternates between them.
     "cities": ["LIS", "OPO", "LIS", "OPO", "LIS"], "nights": [11, 14, 12, 15, 13],
     "hotel": 1650.0, "flight": 780.0},
    {"name": "Joe Gargery", "id_prefix": "DJG", "gender": "Male", "age": 46,
     "origin": "EWR", "carrier": "UA", "depart": (6, 8),
     "cities": ["MAN", "BHX", "EDI", "DUB", "LHR"], "nights": [10, 11, 13, 12, 14],
     "hotel": 1800.0, "flight": 760.0},
]

CSV_COLUMNS = ["trip_id", "traveler_name", "year", "start_date", "end_date", "nights",
               "origin_airport", "destination_airport", "destination_city",
               "destination_country", "carrier_name", "distance_km", "route_carriers"]


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


def check_routes(routes, airports):
    """Every leg must be a real nonstop on the named carrier, to a country this
    file has an ISO2 code for."""
    problems = []
    for traveler in TRAVELERS:
        origin, carrier = traveler["origin"], traveler["carrier"]
        if len(traveler["cities"]) != len(YEARS) or len(traveler["nights"]) != len(YEARS):
            problems.append(f"{traveler['name']}: needs {len(YEARS)} cities and nights")
        for destination in set(traveler["cities"]):
            key = (origin, destination)
            if destination not in airports:
                problems.append(f"{traveler['name']}: {destination} not in airports.json")
                continue
            country = airports[destination]["country"]
            if country not in COUNTRY_CODES:
                problems.append(f"{traveler['name']}: no ISO2 for {country} ({destination})")
            if key not in routes:
                problems.append(f"{traveler['name']}: no nonstop {origin}-{destination}")
            elif carrier not in routes[key][1]:
                problems.append(
                    f"{traveler['name']}: {carrier} does not fly {origin}-{destination} "
                    f"(route data lists {', '.join(sorted(routes[key][1]))})"
                )
    if problems:
        raise SystemExit("Route check failed:\n  " + "\n  ".join(problems))


def build_rows(airports, routes):
    trips, report = [], []
    for traveler in TRAVELERS:
        origin, carrier = traveler["origin"], traveler["carrier"]
        month, day = traveler["depart"]

        for index, year in enumerate(YEARS):
            destination = traveler["cities"][index]
            nights = traveler["nights"][index]
            arrival = airports[destination]
            distance, route_carriers = routes[(origin, destination)]

            start = date(year, month, day) + timedelta(days=YEAR_SHIFT[index])
            end = start + timedelta(days=nights)
            if start.month not in SUMMER_MONTHS or end.month not in SUMMER_MONTHS:
                raise SystemExit(
                    f"{traveler['name']} {year}: {start}..{end} leaves summer "
                    f"(months {SUMMER_MONTHS})"
                )
            if not 10 <= nights <= 15:
                raise SystemExit(f"{traveler['name']} {year}: {nights} nights is outside 10-15")

            trips.append({
                "trip_id": f"{traveler['id_prefix']}-{start.isoformat()}",
                "destination_raw": f"{arrival['city']}, {arrival['country']}",
                "destination_city": arrival["city"],
                "destination_country": arrival["country"],
                "destination_country_code": COUNTRY_CODES[arrival["country"]],
                "destination_kind": "city",
                "start_date": start.isoformat(),
                "start_date_raw": start.isoformat(),
                "end_date": end.isoformat(),
                "end_date_raw": end.isoformat(),
                "duration_days": nights,
                "duration_raw": f"{nights} days",
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
                "carrier_name": CARRIERS[carrier],
                "origin_airport": origin,
                "destination_airport": destination,
            })
            report.append({
                "trip_id": trips[-1]["trip_id"], "traveler_name": traveler["name"],
                "year": year, "start_date": start.isoformat(), "end_date": end.isoformat(),
                "nights": nights, "origin_airport": origin,
                "destination_airport": destination, "destination_city": arrival["city"],
                "destination_country": arrival["country"],
                "carrier_name": CARRIERS[carrier], "distance_km": distance,
                "route_carriers": ", ".join(sorted(route_carriers)),
            })

    # Nobody in two places at once, and no id reused.
    by_traveler = {}
    for trip in trips:
        by_traveler.setdefault(trip["traveler_name"], []).append(trip)
    for name, own in by_traveler.items():
        own.sort(key=lambda t: t["start_date"])
        for earlier, later in zip(own, own[1:]):
            if later["start_date"] <= earlier["end_date"]:
                raise SystemExit(f"{name}: trips overlap at {later['start_date']}")
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
    check_routes(routes, airports)
    trips, report = build_rows(airports, routes)

    payload = {
        "source": (
            "Hand-authored travelers, written for this project -- see "
            "build_dickens_trips.py. Fourteen Dickens characters, all American, all "
            "based in New York City, each taking one long European summer holiday a "
            "year from 2021 to 2025."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED -- the people, lodging and costs are "
            "invented, and every row carries synthetic: true. The flying is not: "
            "every trip is a NONSTOP from JFK or EWR on the named carrier, present "
            "in airline_routes_enhanced.csv, and the build fails otherwise. LGA has "
            "no transatlantic service in the route data, so nobody departs from it. "
            "Palermo and Malaga were requested but have no nonstop from either NYC "
            "airport in the data, so they are absent rather than invented. Each "
            "traveler keeps one carrier across all five summers but visits a "
            "different city each year. Rose and Harry Maylie are married and "
            "deliberately share an itinerary -- identical route and dates, two rows. "
            "Country codes come from an explicit table in the script rather than "
            "being inferred. Merged into trips_enhanced.json by "
            "build_trips_enhanced.py."
        ),
        "carrier_preference": sorted(CARRIERS.values()),
        "declared_bases": {t["name"]: dict(base_city=BASE_CITY,
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
        own = sorted((r for r in report if r["traveler_name"] == traveler["name"]),
                     key=lambda r: r["year"])
        cities = " ".join(f"{r['destination_airport']}" for r in own)
        span = f"{min(r['nights'] for r in own)}-{max(r['nights'] for r in own)}n"
        print(f"  {traveler['name']:19} {traveler['origin']} {traveler['carrier']}  "
              f"{cities}  {span}")


if __name__ == "__main__":
    main()
