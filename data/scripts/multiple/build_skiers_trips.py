"""
Derived from: nothing -- the five travelers below are AUTHORED, in the same
              spirit as build_synthetic_trips.py's 82.
Requires: data/reference/airports.json (IATA -> city/country/coords)
          data/processed/multiple/airline_routes_enhanced.csv (who actually
          flies a route, and how far it is)

Writes data/processed/multiple/skiers_traveler.json (and .csv), which
build_trips_enhanced.py merges via its SYNTHETIC_SOURCES tuple.

WHY THIS EXISTS. build_synthetic_trips.py's travelers are loyal to an
airline, a region, or a route. None of them is loyal to a SEASON in the way
a skier is: same handful of weeks every year, same mountains, same airline,
for as long as they've been doing it. That's a distinct pattern shape for
the recommender to tell apart from Warhol's "whole network of one country"
or Chet Baker's "one route, every other week", and there was nothing like
it in the dataset.

Nine skiers over three seasons (2023-24, 2024-25, 2025-26), in two groups:

  * Five to COLORADO, one trip each per season. Four fly United out of four
    different United hubs; the fifth flies Delta out of Atlanta.
  * Four to JACKSON HOLE and UTAH, two trips each per season. Two fly
    American out of Dallas and Charlotte, two fly Delta out of Minneapolis
    and Detroit.

The trip counts differ on purpose. compute_traveler_tags.py needs
LOYALIST_MIN_TRIPS (5) carrier-recorded trips before it will call anyone an
"{Airline} Loyalist", so the Colorado five (3 trips) are tagged by hub only
while the Jackson Hole/Utah four (6 trips) carry the Loyalist chip. Having
both sides is the point: it puts a traveler who IS loyal but under-observed
next to one the rule can actually see.

THESE TRIPS ARE FABRICATED. The people, the dates, the lodging and the
costs are invented -- see the `synthetic: true` on every row and the note
in the payload. What is NOT invented is the flying: every leg below is a
route that exists in airline_routes_enhanced.csv, flown by a carrier that
the route data says actually serves it, and check_routes() below fails the
build rather than writing a trip on a route nobody flies.

THE DESTINATION IS THE AIRPORT'S CITY, NOT THE RESORT. A row that lands at
EGE says Vail, because that is what airports.json calls EGE -- not Beaver
Creek, which is nearer. Same rule as everywhere else in this project: the
airport reference decides the city, so nobody has to adjudicate which
resort a flight was "really" for. A Utah trip therefore reads as Salt Lake
City, not Park City or Alta.

That rule is followed even where the reference is wrong: airports.json
spells JAC's city "Jacksn Hole", a typo carried down from OpenFlights
upstream. It is NOT special-cased here -- correcting one airport's name
inside a trip builder would put the fix somewhere nobody would ever look
for it. Fix it in the reference or not at all.

WHY SOME SKIERS ONLY EVER FLY TO DENVER. Jim Gilmore (SFO) and Mrs. Smith (ATL)
fly to DEN every season and then drive; the others reach a mountain
airport directly. That asymmetry is the route data's, not a
stylistic choice -- United serves EGE and ASE from Houston, Newark and
Chicago, but from San Francisco the only Colorado options in the route
file are DEN and COS, and Delta's Atlanta-Colorado service is DEN and COS
as well. Giving those two a mountain airport would have meant inventing a
route, so they get the drive instead.

Usage:
    python build_skiers_trips.py
    python build_skiers_trips.py --report   # print every trip and the airlines on its route
"""

import argparse
import csv
import json
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
ROUTES_PATH = DATA_DIR / "processed" / "multiple" / "airline_routes_enhanced.csv"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
OUT_JSON = PROCESSED_DIR / "skiers_traveler.json"
OUT_CSV = PROCESSED_DIR / "skiers_trips.csv"

UNITED = "United Air Lines Inc."
DELTA = "Delta Air Lines Inc."
AMERICAN = "American Airlines Inc."
CARRIER_CODE = {UNITED: "UA", DELTA: "DL", AMERICAN: "AA"}

# Trip-id prefixes. All nine start "SK" so they can't collide with a prefix
# used anywhere else in trips_enhanced.json, whatever initials a traveler's
# name happens to share with someone else's. A duplicate prefix would
# silently merge two people's trips, since trip_id is prefix + start date.
#
# nights: every trip is a Saturday-to-Saturday ski week. build_rows()
# asserts the departure really is a Saturday rather than trusting the
# dates below to have been typed correctly.
SKIERS = [
    {
        "name": "George Gardner",
        "id_prefix": "SKGG",
        "gender": "Male",
        "nationality": "American",
        "age_in_first_season": 41,
        "base": {"city": "Houston", "country": "United States", "country_code": "US"},
        "origin": "IAH",
        "carrier": UNITED,
        "loyalty": "United",
        # Alternates Vail and Aspen; United flies IAH to both.
        "seasons": [
            {"start": "2024-02-10", "airport": "EGE", "nights": 7, "hotel": 3100.0, "flight": 415.0},
            {"start": "2025-02-08", "airport": "ASE", "nights": 7, "hotel": 3600.0, "flight": 470.0},
            {"start": "2026-02-07", "airport": "EGE", "nights": 7, "hotel": 3350.0, "flight": 445.0},
        ],
    },
    {
        "name": "Charley Wyman",
        "id_prefix": "SKCW",
        "gender": "Male",
        "nationality": "American",
        "age_in_first_season": 37,
        "base": {"city": "Newark", "country": "United States", "country_code": "US"},
        "origin": "EWR",
        "carrier": UNITED,
        "loyalty": "United",
        # Newark's only Colorado options on United are EGE and DEN.
        "seasons": [
            {"start": "2024-02-17", "airport": "EGE", "nights": 7, "hotel": 3250.0, "flight": 520.0},
            {"start": "2025-02-15", "airport": "DEN", "nights": 7, "hotel": 2400.0, "flight": 385.0},
            {"start": "2026-02-14", "airport": "EGE", "nights": 7, "hotel": 3500.0, "flight": 560.0},
        ],
    },
    {
        "name": "Liz Coates",
        "id_prefix": "SKLC",
        "gender": "Female",
        "nationality": "American",
        "age_in_first_season": 52,
        "base": {"city": "Chicago", "country": "United States", "country_code": "US"},
        "origin": "ORD",
        "carrier": UNITED,
        "loyalty": "United",
        # Chicago is the only base here with a Telluride option (MTJ).
        "seasons": [
            {"start": "2024-03-02", "airport": "ASE", "nights": 7, "hotel": 3400.0, "flight": 430.0},
            {"start": "2025-03-01", "airport": "MTJ", "nights": 7, "hotel": 2950.0, "flight": 455.0},
            {"start": "2026-02-28", "airport": "ASE", "nights": 7, "hotel": 3700.0, "flight": 480.0},
        ],
    },
    {
        "name": "Jim Gilmore",
        "id_prefix": "SKJG",
        "gender": "Male",
        "nationality": "American",
        "age_in_first_season": 45,
        "base": {"city": "San Francisco", "country": "United States", "country_code": "US"},
        "origin": "SFO",
        "carrier": UNITED,
        "loyalty": "United",
        # DEN every season and drive -- see the docstring. Summit County
        # lodging, hence the lower nightly rate than a slopeside week.
        "seasons": [
            {"start": "2024-01-13", "airport": "DEN", "nights": 7, "hotel": 2250.0, "flight": 340.0},
            {"start": "2025-01-11", "airport": "DEN", "nights": 7, "hotel": 2400.0, "flight": 365.0},
            {"start": "2026-01-10", "airport": "DEN", "nights": 7, "hotel": 2550.0, "flight": 390.0},
        ],
    },
    {
        "name": "Mrs. Smith",
        "id_prefix": "SKMS",
        "gender": "Female",
        "nationality": "American",
        "age_in_first_season": 48,
        "base": {"city": "Atlanta", "country": "United States", "country_code": "US"},
        "origin": "ATL",
        "carrier": DELTA,
        "loyalty": "Delta",
        "seasons": [
            {"start": "2024-01-27", "airport": "DEN", "nights": 7, "hotel": 2300.0, "flight": 375.0},
            {"start": "2025-01-25", "airport": "DEN", "nights": 7, "hotel": 2500.0, "flight": 400.0},
            {"start": "2026-01-24", "airport": "DEN", "nights": 7, "hotel": 2650.0, "flight": 425.0},
        ],
    },
    # --- Jackson Hole and Utah: two American loyalists, two Delta ------------
    # These four fly TWICE a season, not once. compute_traveler_tags.py needs
    # LOYALIST_MIN_TRIPS (5) carrier-recorded trips before it will award an
    # "{Airline} Loyalist" tag, and three seasons at one trip each is three --
    # which is exactly why the five Colorado skiers above are tagged by hub
    # only. Six trips clears it, so these four are the ones that actually
    # carry the Loyalist chip.
    #
    # All four bases are single-airline hubs (Dallas and Charlotte are
    # American's, Minneapolis and Detroit are Delta's, per AIRLINE_HUBS in
    # compute_traveler_tags.py), so each also gets a clean "{Airline} Hub"
    # rather than the "Multi Hub" that Chicago and Newark produce.
    {
        "name": "Ettore Moretti",
        "id_prefix": "SKEM",
        "gender": "Male",
        "nationality": "American",
        "age_in_first_season": 34,
        "base": {"city": "Dallas", "country": "United States", "country_code": "US"},
        "origin": "DFW",
        "carrier": AMERICAN,
        "loyalty": "American",
        # January in Jackson Hole, March in Utah. American flies DFW to both.
        "seasons": [
            {"start": "2024-01-06", "airport": "JAC", "nights": 7, "hotel": 4100.0, "flight": 495.0},
            {"start": "2024-03-09", "airport": "SLC", "nights": 7, "hotel": 2650.0, "flight": 355.0},
            {"start": "2025-01-04", "airport": "JAC", "nights": 7, "hotel": 4350.0, "flight": 520.0},
            {"start": "2025-03-08", "airport": "SLC", "nights": 7, "hotel": 2800.0, "flight": 370.0},
            {"start": "2026-01-03", "airport": "JAC", "nights": 7, "hotel": 4600.0, "flight": 545.0},
            {"start": "2026-03-07", "airport": "SLC", "nights": 7, "hotel": 2950.0, "flight": 385.0},
        ],
    },
    {
        "name": "Ralph Simmons",
        "id_prefix": "SKRS",
        "gender": "Male",
        "nationality": "American",
        "age_in_first_season": 39,
        "base": {"city": "Charlotte", "country": "United States", "country_code": "US"},
        "origin": "CLT",
        "carrier": AMERICAN,
        "loyalty": "American",
        # Utah twice a season. Charlotte has no Jackson Hole service on
        # American in the route file, so this one is Utah-only.
        "seasons": [
            {"start": "2024-01-20", "airport": "SLC", "nights": 7, "hotel": 2500.0, "flight": 430.0},
            {"start": "2024-03-16", "airport": "SLC", "nights": 7, "hotel": 2350.0, "flight": 400.0},
            {"start": "2025-01-18", "airport": "SLC", "nights": 7, "hotel": 2650.0, "flight": 455.0},
            {"start": "2025-03-15", "airport": "SLC", "nights": 7, "hotel": 2500.0, "flight": 420.0},
            {"start": "2026-01-17", "airport": "SLC", "nights": 7, "hotel": 2800.0, "flight": 480.0},
            {"start": "2026-03-14", "airport": "SLC", "nights": 7, "hotel": 2650.0, "flight": 445.0},
        ],
    },
    {
        "name": "Frances Clyne",
        "id_prefix": "SKFC",
        "gender": "Female",
        "nationality": "American",
        "age_in_first_season": 47,
        "base": {"city": "Minneapolis", "country": "United States", "country_code": "US"},
        "origin": "MSP",
        "carrier": DELTA,
        "loyalty": "Delta",
        # Jackson Hole twice a season -- the only traveler here loyal to one
        # mountain rather than to a state.
        "seasons": [
            {"start": "2024-02-03", "airport": "JAC", "nights": 7, "hotel": 3950.0, "flight": 445.0},
            {"start": "2024-03-23", "airport": "JAC", "nights": 7, "hotel": 3600.0, "flight": 415.0},
            {"start": "2025-02-01", "airport": "JAC", "nights": 7, "hotel": 4200.0, "flight": 470.0},
            {"start": "2025-03-22", "airport": "JAC", "nights": 7, "hotel": 3800.0, "flight": 435.0},
            {"start": "2026-01-31", "airport": "JAC", "nights": 7, "hotel": 4450.0, "flight": 495.0},
            {"start": "2026-03-21", "airport": "JAC", "nights": 7, "hotel": 4000.0, "flight": 455.0},
        ],
    },
    {
        "name": "Harvey Stone",
        "id_prefix": "SKHS",
        "gender": "Male",
        "nationality": "American",
        "age_in_first_season": 31,
        "base": {"city": "Detroit", "country": "United States", "country_code": "US"},
        "origin": "DTW",
        "carrier": DELTA,
        "loyalty": "Delta",
        # Utah twice a season. Detroit reaches SLC on Delta but not JAC.
        "seasons": [
            {"start": "2024-02-24", "airport": "SLC", "nights": 7, "hotel": 2400.0, "flight": 375.0},
            {"start": "2024-03-30", "airport": "SLC", "nights": 7, "hotel": 2200.0, "flight": 345.0},
            {"start": "2025-02-22", "airport": "SLC", "nights": 7, "hotel": 2550.0, "flight": 395.0},
            {"start": "2025-03-29", "airport": "SLC", "nights": 7, "hotel": 2350.0, "flight": 365.0},
            {"start": "2026-02-21", "airport": "SLC", "nights": 7, "hotel": 2700.0, "flight": 415.0},
            {"start": "2026-03-28", "airport": "SLC", "nights": 7, "hotel": 2500.0, "flight": 385.0},
        ],
    },
]

CSV_COLUMNS = [
    "trip_id", "traveler_name", "start_date", "end_date", "nights",
    "origin_airport", "destination_airport", "destination_city",
    "carrier_name", "distance_km", "accommodation_cost", "transportation_cost",
]


def load_airports() -> dict:
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    return {a["iata"]: a for a in payload["airports"] if a.get("iata")}


def load_routes() -> dict:
    """(origin, destination) -> (distance_km, carrier codes). One pass over
    the route file rather than one per trip."""
    routes: dict[tuple[str, str], tuple[float | None, set[str]]] = {}
    with ROUTES_PATH.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["Departure"], row["Destination"])
            distance, carriers = routes.get(key, (None, set()))
            carriers.add(row["Airline ID"])
            if distance is None and row.get("distance_km"):
                distance = float(row["distance_km"])
            routes[key] = (distance, carriers)
    return routes


def check_routes(routes: dict) -> None:
    """Every leg must be a route the data knows, flown by the carrier the
    skier is loyal to. This raises rather than warning: a ski trip on a
    route nobody flies is exactly the kind of invented fact the rest of
    this project refuses to write, and a silent skip would leave a skier
    quietly missing a season."""
    problems = []
    for skier in SKIERS:
        for season in skier["seasons"]:
            key = (skier["origin"], season["airport"])
            if key not in routes:
                problems.append(f"{skier['name']}: no {key[0]}-{key[1]} route in {ROUTES_PATH.name}")
                continue
            code = CARRIER_CODE[skier["carrier"]]
            carriers = routes[key][1]
            if code not in carriers:
                problems.append(
                    f"{skier['name']}: {code} does not fly {key[0]}-{key[1]} "
                    f"(route data lists {', '.join(sorted(carriers))})"
                )
    if problems:
        raise SystemExit("Route check failed:\n  " + "\n  ".join(problems))


def build_rows(airports: dict, routes: dict) -> tuple[list[dict], list[dict]]:
    trips, report = [], []
    for skier in SKIERS:
        # Age advances with the calendar, not with the position in the list --
        # the travelers who fly twice a season would otherwise age two years
        # per season.
        first_year = min(date.fromisoformat(s["start"]).year for s in skier["seasons"])
        for season in skier["seasons"]:
            start = date.fromisoformat(season["start"])
            if start.weekday() != 5:
                raise SystemExit(
                    f"{skier['name']} {season['start']} is a {start.strftime('%A')}, not a Saturday "
                    "-- these are Saturday-to-Saturday ski weeks, so this is a typo in the table."
                )
            nights = season["nights"]
            end = start + timedelta(days=nights)
            airport = airports[season["airport"]]
            distance, carriers = routes[(skier["origin"], season["airport"])]
            city, country = airport["city"], airport["country"]

            trips.append({
                "trip_id": f"{skier['id_prefix']}-{start.isoformat()}",
                "destination_raw": f"{city}, {country}",
                "destination_city": city,
                "destination_country": country,
                "destination_country_code": "US",
                "destination_kind": "city",
                "start_date": start.isoformat(),
                "start_date_raw": start.isoformat(),
                "end_date": end.isoformat(),
                "end_date_raw": end.isoformat(),
                "duration_days": nights,
                "duration_raw": f"{nights} days",
                "accommodation_type": "Hotel",
                "accommodation_cost": season["hotel"],
                "accommodation_cost_raw": f"${season['hotel']:,.0f}",
                "transportation_type": "Flight",
                "transportation_cost": season["flight"],
                "transportation_cost_raw": f"${season['flight']:,.0f}",
                "traveler_name": skier["name"],
                "traveler_age": skier["age_in_first_season"] + (start.year - first_year),
                "traveler_gender": skier["gender"],
                "traveler_nationality": skier["nationality"],
                "synthetic": True,
                "carrier_name": skier["carrier"],
                "origin_airport": skier["origin"],
                "destination_airport": season["airport"],
            })
            report.append({
                "trip_id": trips[-1]["trip_id"],
                "traveler_name": skier["name"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "nights": nights,
                "origin_airport": skier["origin"],
                "destination_airport": season["airport"],
                "destination_city": city,
                "carrier_name": skier["carrier"],
                "distance_km": distance,
                "accommodation_cost": season["hotel"],
                "transportation_cost": season["flight"],
                "route_carriers": ", ".join(sorted(carriers)),
            })

    trips.sort(key=lambda t: (t["traveler_name"], t["start_date"]))
    report.sort(key=lambda r: (r["traveler_name"], r["start_date"]))
    return trips, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the Colorado skier travelers.")
    parser.add_argument("--report", action="store_true",
                        help="print every trip and which airlines the route data lists")
    args = parser.parse_args()

    airports = load_airports()
    routes = load_routes()
    check_routes(routes)
    trips, report = build_rows(airports, routes)

    declared_bases = {s["name"]: dict(base_city=s["base"]["city"],
                                      base_country=s["base"]["country"],
                                      base_country_code=s["base"]["country_code"])
                      for s in SKIERS}

    payload = {
        "source": (
            "Hand-authored travelers, written for this project -- see "
            "build_skiers_trips.py. Five Colorado skiers, one trip each per ski "
            "season for three seasons, four loyal to United out of four of its "
            "hubs and one loyal to Delta out of Atlanta."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED -- the people, dates, lodging and costs are "
            "invented, and every row carries synthetic: true so they can always be "
            "told apart from the Kaggle rows. The flying is not invented: every leg "
            "is a route present in airline_routes_enhanced.csv flown by a carrier "
            "that route data says serves it, and the build fails rather than writing "
            "a trip on a route nobody flies. Destination city is whatever "
            "airports.json calls the arrival airport, so an EGE trip reads as Vail. "
            "Merged into trips_enhanced.json by build_trips_enhanced.py."
        ),
        "carrier_preference": sorted({s["carrier"] for s in SKIERS}),
        "declared_bases": declared_bases,
        "total_travelers": len(SKIERS),
        "total_trips": len(trips),
        "trips": trips,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report)

    print(f"Wrote {len(trips)} trips from {len(SKIERS)} skiers -> {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")
    for skier in SKIERS:
        mine = [t for t in trips if t["traveler_name"] == skier["name"]]
        airports_used = sorted({t["destination_airport"] for t in mine})
        cities = sorted({t["destination_city"] for t in mine})
        print(f"  {skier['name']:18} {skier['origin']} ({skier['loyalty']:6}) "
              f"{len(mine)} trips -> {'/'.join(airports_used)} = {', '.join(cities)}")
    if args.report:
        print()
        for r in report:
            print(f"  {r['trip_id']}  {r['start_date']}..{r['end_date']}  "
                  f"{r['origin_airport']}-{r['destination_airport']} {r['distance_km']:.0f}km  "
                  f"{r['carrier_name']}  [route data lists: {r['route_carriers']}]")


if __name__ == "__main__":
    main()
