"""
Derived from: nothing -- three AUTHORED travelers, in the same spirit as
              build_skiers_trips.py.
Requires: data/reference/airports.json
          data/processed/multiple/airline_routes_enhanced.csv
          classify_trip.py (for the Canadian Thanksgiving date)

Writes data/processed/multiple/raccoons_traveler.json (and .csv), merged by
build_trips_enhanced.py via SYNTHETIC_SOURCES.

WHY THIS EXISTS. classify_trip.py tests a trip against the DESTINATION
COUNTRY'S OWN Thanksgiving -- the US on the fourth Thursday of November,
Canada on the second Monday of October. Nothing in the dataset exercised the
Canadian half: of 62 existing Canada trips, exactly two touch October and
both miss the holiday (23-28 Oct 2019, and 6-11 Oct 2025, which misses by two
days). So the rule was correct and completely untested.

These three are Canadians living in the US who fly home to Toronto for
Thanksgiving every year -- which is both a real travel pattern and the exact
shape that separates "Canadian Thanksgiving" from "American Thanksgiving" in
the classifier.

THE DATES ARE DERIVED, NOT TYPED. The trip window is computed from
classify_trip.canadian_thanksgiving_dates(), the same function the classifier
tests against, so these trips cannot drift from the rule they exist to
exercise. Hardcoding 2021-10-11 and friends would work today and silently
rot the first time someone edited one of the two definitions.

Each trip is the long weekend: arrive the Friday before, leave the Tuesday
after, four nights, with the Monday holiday inside it.

Usage:
    python build_raccoons_trips.py
"""

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_trip import _canadian_thanksgiving_dates

DATA_DIR = Path(__file__).resolve().parent.parent.parent
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
ROUTES_PATH = DATA_DIR / "processed" / "multiple" / "airline_routes_enhanced.csv"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
OUT_JSON = PROCESSED_DIR / "raccoons_traveler.json"
OUT_CSV = PROCESSED_DIR / "raccoons_trips.csv"

AIR_CANADA = "Air Canada"
CARRIER_CODE = {AIR_CANADA: "AC"}

# The five most recent Canadian Thanksgivings that have actually happened.
SEASONS = [2021, 2022, 2023, 2024, 2025]

# Nights away, and how many days before the Monday holiday they arrive.
ARRIVE_DAYS_BEFORE = 3   # the Friday
NIGHTS = 4               # leaving the Tuesday after

# Canadian nationals based in three different US cities, all flying Air
# Canada, which serves YYZ from all three in the route data. Three bases
# rather than one so the group isn't a single origin repeated -- the shared
# thing is the destination and the date, not the route.
RACCOONS = [
    {
        "name": "Count Mippipopolous",
        "id_prefix": "CMI",
        "gender": "Male",
        "age_in_first_year": 34,
        "base": {"city": "New York City", "country": "United States", "country_code": "US"},
        "origin": "JFK",
        "hotel": 1150.0,
        "flight": 320.0,
    },
    {
        "name": "Manuel Orquito",
        "id_prefix": "MO",
        "gender": "Male",
        "age_in_first_year": 41,
        "base": {"city": "Los Angeles", "country": "United States", "country_code": "US"},
        "origin": "LAX",
        "hotel": 1200.0,
        "flight": 540.0,
    },
    {
        "name": "Mrs. Braddocks",
        "id_prefix": "MBR",
        "gender": "Female",
        "age_in_first_year": 38,
        "base": {"city": "Miami", "country": "United States", "country_code": "US"},
        "origin": "MIA",
        "hotel": 1100.0,
        "flight": 415.0,
    },
]

DESTINATION = "YYZ"
NATIONALITY = "Canadian"

CSV_COLUMNS = ["trip_id", "traveler_name", "start_date", "end_date", "nights",
               "canadian_thanksgiving", "origin_airport", "destination_airport",
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


def check_routes(routes):
    """Air Canada must actually fly each origin to Toronto. Raises rather than
    warning: a trip on a route nobody flies is the one thing this project
    refuses to write."""
    problems = []
    for raccoon in RACCOONS:
        key = (raccoon["origin"], DESTINATION)
        if key not in routes:
            problems.append(f"{raccoon['name']}: no {key[0]}-{key[1]} route in {ROUTES_PATH.name}")
        elif CARRIER_CODE[AIR_CANADA] not in routes[key][1]:
            problems.append(
                f"{raccoon['name']}: AC does not fly {key[0]}-{key[1]} "
                f"(route data lists {', '.join(sorted(routes[key][1]))})"
            )
    if problems:
        raise SystemExit("Route check failed:\n  " + "\n  ".join(problems))


def build_rows(airports, routes):
    holidays = {d.year: d for d in _canadian_thanksgiving_dates(SEASONS)}
    arrival_airport = airports[DESTINATION]
    trips, report = [], []

    for raccoon in RACCOONS:
        for year in SEASONS:
            holiday = holidays[year]
            if holiday.weekday() != 0:
                raise SystemExit(f"{year}: Canadian Thanksgiving resolved to a "
                                 f"{holiday.strftime('%A')}, expected a Monday")
            start = holiday - timedelta(days=ARRIVE_DAYS_BEFORE)
            end = start + timedelta(days=NIGHTS)
            if not (start <= holiday <= end):
                raise SystemExit(f"{raccoon['name']} {year}: trip does not contain the holiday")

            distance, carriers = routes[(raccoon["origin"], DESTINATION)]
            trips.append({
                "trip_id": f"{raccoon['id_prefix']}-{start.isoformat()}",
                "destination_raw": f"{arrival_airport['city']}, {arrival_airport['country']}",
                "destination_city": arrival_airport["city"],
                "destination_country": arrival_airport["country"],
                "destination_country_code": "CA",
                "destination_kind": "city",
                "start_date": start.isoformat(),
                "start_date_raw": start.isoformat(),
                "end_date": end.isoformat(),
                "end_date_raw": end.isoformat(),
                "duration_days": NIGHTS,
                "duration_raw": f"{NIGHTS} days",
                "accommodation_type": "Hotel",
                "accommodation_cost": raccoon["hotel"],
                "accommodation_cost_raw": f"${raccoon['hotel']:,.0f}",
                "transportation_type": "Flight",
                "transportation_cost": raccoon["flight"],
                "transportation_cost_raw": f"${raccoon['flight']:,.0f}",
                "traveler_name": raccoon["name"],
                "traveler_age": raccoon["age_in_first_year"] + (year - SEASONS[0]),
                "traveler_gender": raccoon["gender"],
                "traveler_nationality": NATIONALITY,
                "synthetic": True,
                "carrier_name": AIR_CANADA,
                "origin_airport": raccoon["origin"],
                "destination_airport": DESTINATION,
            })
            report.append({
                "trip_id": trips[-1]["trip_id"], "traveler_name": raccoon["name"],
                "start_date": start.isoformat(), "end_date": end.isoformat(),
                "nights": NIGHTS, "canadian_thanksgiving": holiday.isoformat(),
                "origin_airport": raccoon["origin"], "destination_airport": DESTINATION,
                "destination_city": arrival_airport["city"], "carrier_name": AIR_CANADA,
                "distance_km": distance, "route_carriers": ", ".join(sorted(carriers)),
            })

    trips.sort(key=lambda t: (t["traveler_name"], t["start_date"]))
    report.sort(key=lambda r: (r["traveler_name"], r["start_date"]))
    return trips, report


def main():
    airports = load_airports()
    routes = load_routes()
    check_routes(routes)
    trips, report = build_rows(airports, routes)

    payload = {
        "source": (
            "Hand-authored travelers, written for this project -- see "
            "build_raccoons_trips.py. Three Canadians based in US cities who fly "
            "home to Toronto for Canadian Thanksgiving every year."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED -- the people, lodging and costs are "
            "invented, and every row carries synthetic: true. The flying is not: "
            "Air Canada serves JFK/LAX/MIA-YYZ in airline_routes_enhanced.csv and "
            "the build fails rather than writing a trip on a route nobody flies. "
            "The dates are DERIVED from classify_trip.py's own Canadian "
            "Thanksgiving function (second Monday of October), so these trips "
            "cannot drift from the rule they exist to exercise. Merged into "
            "trips_enhanced.json by build_trips_enhanced.py."
        ),
        "carrier_preference": [AIR_CANADA],
        "declared_bases": {r["name"]: dict(base_city=r["base"]["city"],
                                           base_country=r["base"]["country"],
                                           base_country_code=r["base"]["country_code"])
                           for r in RACCOONS},
        "total_travelers": len(RACCOONS),
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

    print(f"Wrote {len(trips)} trips from {len(RACCOONS)} travelers -> {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")
    for raccoon in RACCOONS:
        mine = [t for t in trips if t["traveler_name"] == raccoon["name"]]
        print(f"  {raccoon['name']:18} {raccoon['base']['city']:14} {raccoon['origin']}-YYZ  "
              f"{len(mine)} trips  {mine[0]['start_date']} .. {mine[-1]['start_date']}")
    print("  every trip contains its year's Canadian Thanksgiving (asserted in build_rows)")


if __name__ == "__main__":
    main()
