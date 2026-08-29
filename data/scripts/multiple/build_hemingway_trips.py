"""
Derived from: nothing -- fourteen AUTHORED travelers, in the same spirit as
              build_skiers_trips.py and build_raccoons_trips.py.
Requires: data/reference/airports.json
          data/processed/multiple/airline_routes_enhanced.csv

Writes data/processed/multiple/hemingway_traveler.json (and .csv), merged by
build_trips_enhanced.py via SYNTHETIC_SOURCES.

WHY THIS EXISTS. The dataset's holiday travel was almost entirely Thanksgiving
and Christmas. The other seven American holidays people actually travel for --
Memorial Day, Juneteenth, Independence Day, Labor Day, Columbus Day, and the
two Sundays -- had no signal at all. These fourteen supply it.

TWO KINDS OF HOLIDAY DATE, AND THEY COME FROM DIFFERENT PLACES:

  * The three Monday holidays (Memorial, Labor, Columbus) come from pandas'
    USFederalHolidayCalendar. They are defined as nth-weekday rules, never
    shift, so the calendar's date is the real one.
  * Independence Day and Juneteenth are FIXED dates (Jul 4, Jun 19) and are
    taken literally, NOT from that calendar. The calendar reports the
    *observed* federal holiday, which slides to the Friday or Monday when the
    date lands on a weekend -- that is when offices shut, not when the
    barbecue happens. Travel follows the date.
  * Mother's Day and Father's Day are NOT federal holidays and are not in that
    calendar at all. They are computed here: second Sunday of May, third
    Sunday of June.

THE PEOPLE ARE HEMINGWAY CHARACTERS, ALL AMERICAN per the brief -- including
several the novels make British, Scottish, Italian or Spanish (Brett Ashley,
Mike Campbell, Rinaldi, Helen Ferguson, Pedro Romero, Manuel Garcia). Their
bases and destinations echo where each character belongs where the text
supports it -- Nick Adams to northern Michigan, Krebs out of Oklahoma, Ole
Andreson around Chicago -- and are simply plausible American cities where it
does not. The literary link is a naming convention, not a claim.

EVERY ROUTE IS REAL. Each (origin, destination, carrier) below appears in
airline_routes_enhanced.csv; check_routes() raises rather than warning.

Usage:
    python build_hemingway_trips.py
"""

import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_trip import CHRISTMAS_DAYS, _us_thanksgiving_dates

DATA_DIR = Path(__file__).resolve().parent.parent.parent
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
ROUTES_PATH = DATA_DIR / "processed" / "multiple" / "airline_routes_enhanced.csv"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
OUT_JSON = PROCESSED_DIR / "hemingway_traveler.json"
OUT_CSV = PROCESSED_DIR / "hemingway_trips.csv"

YEARS = [2021, 2022, 2023, 2024, 2025]
NATIONALITY = "American"

CARRIERS = {
    "AA": "American Airlines Inc.",
    "AS": "Alaska Airlines Inc.",
    "DL": "Delta Air Lines Inc.",
    "UA": "United Air Lines Inc.",
    "WN": "Southwest Airlines Co.",
}

# holiday -> (days to arrive BEFORE the holiday, nights away). The Monday and
# Sunday holidays get a Friday arrival; the two fixed-date ones straddle
# instead, since Jul 4 and Jun 19 land on any weekday.
HOLIDAY_WINDOW = {
    "Memorial Day": (3, 3),
    "Labor Day": (3, 3),
    "Columbus Day": (3, 3),
    "Mother's Day": (2, 2),
    "Father's Day": (2, 2),
    "Independence Day": (2, 4),
    "Juneteenth": (1, 3),
    # The two big ones get the long window they get in life: in the Wednesday
    # before Thanksgiving and out on the Sunday, and Dec 22-27 for Christmas.
    # The Christmas span deliberately covers BOTH Dec 24 and Dec 25, because
    # classify_trip.CHRISTMAS_DAYS counts either -- asserted in build_rows().
    "Thanksgiving": (1, 4),
    "Christmas": (3, 5),
}

# The holidays classify_trip.py already recognises. Trips for these should come
# back tagged "Holiday Trip"; the other seven have no rule yet and will not.
CLASSIFIED_HOLIDAYS = ("Thanksgiving", "Christmas")


def nth_weekday(year, month, weekday, n):
    """The nth given weekday of a month -- weekday 0=Monday, 6=Sunday."""
    first = date(year, month, 1)
    first_match = first + timedelta(days=(weekday - first.weekday()) % 7)
    return first_match + timedelta(days=7 * (n - 1))


def holiday_dates(years):
    """holiday name -> {year: date}, from the three sources described above."""
    calendar = USFederalHolidayCalendar()
    federal = calendar.holidays(start=f"{min(years)}-01-01", end=f"{max(years)}-12-31",
                                return_name=True)
    from_calendar = {"Memorial Day": {}, "Labor Day": {}, "Columbus Day": {}}
    for stamp, name in federal.items():
        if name in from_calendar and stamp.year in years:
            from_calendar[name][stamp.year] = stamp.date()

    dates = dict(from_calendar)
    # Fixed dates, taken literally rather than as the observed federal holiday.
    dates["Independence Day"] = {y: date(y, 7, 4) for y in years}
    dates["Juneteenth"] = {y: date(y, 6, 19) for y in years}
    # Not federal holidays; not in the calendar at all.
    dates["Mother's Day"] = {y: nth_weekday(y, 5, 6, 2) for y in years}
    dates["Father's Day"] = {y: nth_weekday(y, 6, 6, 3) for y in years}
    # DERIVED, NOT TYPED -- same discipline as build_raccoons_trips.py. The
    # Thanksgiving date comes from classify_trip's own function, so these trips
    # cannot drift from the rule they exist to exercise.
    thanksgiving = _us_thanksgiving_dates(years)
    dates["Thanksgiving"] = {d.year: d for d in thanksgiving if d.year in set(years)}
    dates["Christmas"] = {y: date(y, 12, 25) for y in years}
    return dates


# "trips" is (holiday, destination airport, carrier code) -- two or three
# holidays each, so every traveler has a signature rather than the same
# calendar as everyone else; all seven are covered by at least three people.
#
# "home" is (destination airport, carrier) and is separate because it works
# differently: EVERY traveler flies there for BOTH Thanksgiving and Christmas,
# every year. That is the pattern those two holidays actually have -- people go
# to the same place twice, six weeks apart, and it is the same place every
# year. Encoding it as two more entries in "trips" would have hidden that.
TRAVELERS = [
    {"name": "Nick Adams", "id_prefix": "HNA", "gender": "Male", "age": 29,
     "base": ("Chicago", "ORD"), "hotel": 900.0, "flight": 260.0,
     # Big Two-Hearted River country: the Michigan woods, three times a year.
     "home": ("TVC", "UA"),  # the Michigan woods he already flies to three times a year
     "trips": [("Father's Day", "TVC", "UA"), ("Labor Day", "TVC", "UA"),
               ("Columbus Day", "TVC", "UA")]},
    {"name": "Jake Barnes", "id_prefix": "HJB", "gender": "Male", "age": 34,
     "base": ("Kansas City", "MCI"), "hotel": 1050.0, "flight": 310.0,
     "home": ("ORD", "UA"),  # Chicago
     "trips": [("Memorial Day", "DEN", "UA"), ("Independence Day", "MSY", "WN")]},
    {"name": "Brett Ashley", "id_prefix": "HBA", "gender": "Female", "age": 34,
     "base": ("New York City", "JFK"), "hotel": 1600.0, "flight": 340.0,
     "home": ("SAV", "DL"),  # Savannah
     "trips": [("Mother's Day", "MIA", "DL"), ("Memorial Day", "CHS", "DL")]},
    {"name": "Robert Cohn", "id_prefix": "HRC", "gender": "Male", "age": 39,
     "base": ("Newark", "EWR"), "hotel": 1150.0, "flight": 245.0,
     "home": ("ORD", "UA"),  # Chicago
     "trips": [("Independence Day", "BOS", "UA"), ("Labor Day", "PWM", "UA")]},
    {"name": "Mike Campbell", "id_prefix": "HMC", "gender": "Male", "age": 37,
     "base": ("Boston", "BOS"), "hotel": 1400.0, "flight": 290.0,
     "home": ("RIC", "AA"),  # Richmond
     "trips": [("Labor Day", "CLT", "AA"), ("Columbus Day", "MIA", "AA")]},
    {"name": "Bill Gorton", "id_prefix": "HBG", "gender": "Male", "age": 36,
     "base": ("New York City", "LGA"), "hotel": 980.0, "flight": 230.0,
     "home": ("MSP", "DL"),  # Minneapolis
     "trips": [("Columbus Day", "BUF", "DL"), ("Father's Day", "DTW", "DL")]},
    {"name": "Pedro Romero", "id_prefix": "HPR", "gender": "Male", "age": 24,
     "base": ("San Antonio", "SAT"), "hotel": 870.0, "flight": 275.0,
     "home": ("MIA", "AA"),  # Miami
     "trips": [("Juneteenth", "PHX", "AA"), ("Independence Day", "DEN", "UA")]},
    {"name": "Frederic Henry", "id_prefix": "HFH", "gender": "Male", "age": 31,
     "base": ("Chicago", "ORD"), "hotel": 1250.0, "flight": 330.0,
     "home": ("IAD", "UA"),  # Washington
     "trips": [("Memorial Day", "BZN", "UA"), ("Labor Day", "BZN", "UA")]},
    {"name": "Catherine Barkley", "id_prefix": "HCB", "gender": "Female", "age": 28,
     "base": ("Seattle", "SEA"), "hotel": 1100.0, "flight": 240.0,
     "home": ("GEG", "AS"),  # Spokane
     "trips": [("Mother's Day", "PDX", "AS"), ("Juneteenth", "ANC", "AS")]},
    {"name": "Rinaldi", "id_prefix": "HRI", "gender": "Male", "age": 35,
     "base": ("Philadelphia", "PHL"), "hotel": 820.0, "flight": 215.0,
     "home": ("BOS", "AA"),  # Boston
     "trips": [("Father's Day", "PIT", "AA"), ("Columbus Day", "RDU", "AA")]},
    {"name": "Helen Ferguson", "id_prefix": "HHF", "gender": "Female", "age": 33,
     "base": ("Detroit", "DTW"), "hotel": 760.0, "flight": 195.0,
     "home": ("BNA", "DL"),  # Nashville
     "trips": [("Mother's Day", "TVC", "DL"), ("Labor Day", "TVC", "DL")]},
    {"name": "Ole Andreson", "id_prefix": "HOA", "gender": "Male", "age": 42,
     "base": ("Chicago", "ORD"), "hotel": 700.0, "flight": 180.0,
     "home": ("MSP", "UA"),  # Minneapolis
     "trips": [("Juneteenth", "MKE", "UA"), ("Columbus Day", "STL", "UA")]},
    {"name": "Manuel Garcia", "id_prefix": "HMG", "gender": "Male", "age": 38,
     "base": ("Los Angeles", "LAX"), "hotel": 950.0, "flight": 165.0,
     "home": ("ELP", "AA"),  # El Paso
     "trips": [("Independence Day", "SAN", "AA"), ("Memorial Day", "LAS", "AA")]},
    {"name": "Krebs", "id_prefix": "HKR", "gender": "Male", "age": 26,
     "base": ("Oklahoma City", "OKC"), "hotel": 640.0, "flight": 220.0,
     # NOT Father's Day: the third Sunday of June is always within a few days
     # of Juneteenth, so the two windows overlap and Krebs would be in Dallas
     # and Denver at once. Memorial Day is clear of it in every year.
     "home": ("ORD", "AA"),  # Chicago
     "trips": [("Memorial Day", "DFW", "AA"), ("Juneteenth", "DEN", "UA")]},
]

CSV_COLUMNS = ["trip_id", "traveler_name", "holiday", "holiday_date", "start_date",
               "end_date", "nights", "origin_airport", "destination_airport",
               "destination_city", "carrier_name", "distance_km", "route_carriers"]


def itinerary(traveler):
    """Every (holiday, destination, carrier) this traveler flies in a year:
    their two or three signature holidays, then the trip home for Thanksgiving
    and again for Christmas. Both check_routes() and build_rows() go through
    here, so a route can never be validated and then not built, or vice versa."""
    home_airport, home_carrier = traveler["home"]
    return [
        *traveler["trips"],
        *((holiday, home_airport, home_carrier) for holiday in CLASSIFIED_HOLIDAYS),
    ]


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
    problems = []
    for traveler in TRAVELERS:
        origin = traveler["base"][1]
        for holiday, destination, carrier in itinerary(traveler):
            if holiday not in HOLIDAY_WINDOW:
                problems.append(f"{traveler['name']}: unknown holiday {holiday!r}")
            key = (origin, destination)
            if key not in routes:
                problems.append(f"{traveler['name']}: no {origin}-{destination} route")
            elif carrier not in routes[key][1]:
                problems.append(
                    f"{traveler['name']}: {carrier} does not fly {origin}-{destination} "
                    f"(route data lists {', '.join(sorted(routes[key][1]))})"
                )
    if problems:
        raise SystemExit("Route check failed:\n  " + "\n  ".join(problems))


def build_rows(airports, routes):
    dates = holiday_dates(YEARS)
    trips, report = [], []

    for traveler in TRAVELERS:
        base_city, origin = traveler["base"]
        for holiday, destination, carrier in itinerary(traveler):
            days_before, nights = HOLIDAY_WINDOW[holiday]
            arrival_airport = airports[destination]
            distance, route_carriers = routes[(origin, destination)]

            for year in YEARS:
                holiday_date = dates[holiday][year]
                start = holiday_date - timedelta(days=days_before)
                end = start + timedelta(days=nights)
                if not (start <= holiday_date <= end):
                    raise SystemExit(
                        f"{traveler['name']} {holiday} {year}: trip {start}..{end} "
                        f"does not contain the holiday ({holiday_date})"
                    )
                # For the two the classifier knows, containing the date is not
                # enough -- it has to be a day classify_trip actually tests.
                # Christmas is the live risk: CHRISTMAS_DAYS counts Dec 24 and
                # 25, so a window that straddled neither would build cleanly
                # and then silently fail to tag.
                if holiday == "Christmas":
                    span = {start + timedelta(days=n) for n in range(nights + 1)}
                    if not any(d.month == 12 and d.day in CHRISTMAS_DAYS for d in span):
                        raise SystemExit(
                            f"{traveler['name']} Christmas {year}: trip {start}..{end} "
                            f"covers no day in CHRISTMAS_DAYS {CHRISTMAS_DAYS} -- "
                            f"classify_trip would not tag it"
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
                    "holiday": holiday, "holiday_date": holiday_date.isoformat(),
                    "start_date": start.isoformat(), "end_date": end.isoformat(),
                    "nights": nights, "origin_airport": origin,
                    "destination_airport": destination,
                    "destination_city": arrival_airport["city"],
                    "carrier_name": CARRIERS[carrier], "distance_km": distance,
                    "route_carriers": ", ".join(sorted(route_carriers)),
                })

    # Nobody can be in two places at once. Holidays that sit close together in
    # the calendar (Father's Day and Juneteenth above all) produce windows that
    # overlap, so this is checked rather than assumed. Overlap implies a
    # duplicate trip_id too, since the id is keyed on the start date.
    by_traveler = {}
    for trip in trips:
        by_traveler.setdefault(trip["traveler_name"], []).append(trip)
    for name, own in by_traveler.items():
        own.sort(key=lambda t: t["start_date"])
        for earlier, later in zip(own, own[1:]):
            if later["start_date"] <= earlier["end_date"]:
                raise SystemExit(
                    f"{name}: trips overlap -- {earlier['start_date']}..{earlier['end_date']} "
                    f"to {earlier['destination_airport']} and {later['start_date']}.."
                    f"{later['end_date']} to {later['destination_airport']}. "
                    f"Two of this traveler's holidays fall too close together."
                )

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
            "build_hemingway_trips.py. Fourteen Hemingway characters, all American, "
            "each with two or three US holidays they travel for every year."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED -- the people, lodging and costs are invented, "
            "and every row carries synthetic: true. The flying is not: every "
            "(origin, destination, carrier) appears in airline_routes_enhanced.csv and "
            "the build fails otherwise. Holiday dates come from three places: the three "
            "Monday holidays from pandas' USFederalHolidayCalendar (nth-weekday rules "
            "that never shift), Independence Day and Juneteenth as literal Jul 4 / "
            "Jun 19 rather than the observed federal date, and Mother's/Father's Day "
            "computed (2nd Sunday of May, 3rd Sunday of June) since they are not "
            "federal holidays at all. Merged into trips_enhanced.json by "
            "build_trips_enhanced.py."
        ),
        "carrier_preference": sorted(CARRIERS.values()),
        "declared_bases": {t["name"]: dict(base_city=t["base"][0],
                                           base_country="United States",
                                           base_country_code="US")
                           for t in TRAVELERS},
        "total_travelers": len(TRAVELERS),
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

    print(f"Wrote {len(trips)} trips from {len(TRAVELERS)} travelers -> {OUT_JSON}")
    print(f"Wrote {OUT_CSV}")
    import collections
    by_holiday = collections.Counter(r["holiday"] for r in report)
    print("  trips per holiday:", dict(sorted(by_holiday.items())))
    for t in TRAVELERS:
        mine = [r for r in report if r["traveler_name"] == t["name"]]
        holidays = sorted({r["holiday"] for r in mine})
        dests = sorted({r["destination_airport"] for r in mine})
        print(f"  {t['name']:19} {t['base'][1]} -> {'/'.join(dests):11} {len(mine):2} trips  {', '.join(holidays)}")


if __name__ == "__main__":
    main()
