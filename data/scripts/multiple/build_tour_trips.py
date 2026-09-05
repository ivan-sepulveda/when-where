"""
Derived from: published concert itineraries, supplied by Ivan. The dates,
              cities and venues are REAL.
Requires: data/reference/airports.json (IATA -> city/country/coords)
          data/processed/multiple/airline_routes_enhanced.csv (who flies a
          route)

Writes data/processed/multiple/tour_traveler.json (and tour_trips.csv), which
build_trips_enhanced.py merges via its SYNTHETIC_SOURCES tuple.

WHY THIS EXISTS -- A SHAPE NO OTHER TRAVELER IN THIS DATASET HAS. Every
other itinerary here is a STAR: out from a home base, back to the same home
base, repeat. build_synthetic_trips.py's 82, the skiers, the raccoons, the
five travel-show hosts -- all of them. Even the Gomez flight log, which is a
real person's real legs, is mostly out-and-back.

A tour is a CHAIN. The artist leaves home once and every subsequent leg
starts where the last one ended. `origin_airport` is the PREVIOUS city, not
home, on all but the first row -- which is the fact that makes this a
different pattern for a recommender to learn. A model that has only ever
seen star itineraries will predict "and then they went home", and here they
don't, for weeks.

It also breaks an assumption the rest of the pipeline quietly makes.
compute_traveler_tags.py's hub rule reads `home_airport` as "the one airport
this traveler departs from", which is true of every declared-base traveler in
the dataset because they all fly out and back. A touring artist departs from
a different airport every time. That is not a bug in either place -- it is
the case the tag rules have not met before, and it is worth having in the
data.

THE TRAVELERS (TOURS is a table; a third artist is a third entry):

  María Zardoya   The Marías, Submarine Tour, 2024 North American leg.
                  Based in Los Angeles. 17 stops, 17 shows, 34 days away.
  Luis Miguel     2023 North American leg. Based in Mexico City. 21 stops,
                  25 shows, 52 days away -- and it opens with an
                  INTERNATIONAL departure, MEX-LAS, which no other tour leg
                  in this file is.

WHAT IS REAL HERE AND WHAT IS NOT
---------------------------------
REAL, from the published listings:
  * Every date, city and venue, and the ORDER. The chain is the tour's own
    order, not a route optimisation.
REAL, from this project's own data:
  * Airports, distances and operators come from airports.json and
    airline_routes_enhanced.csv. Nothing about the flying is asserted here
    that those two files don't support.
NOT DOCUMENTED, and so either resolved from data or left null:
  * WHICH AIRLINE. Nobody published that. The carrier is RESOLVED from the
    route data the same way build_synthetic_trips.py's ANY_CARRIER travelers'
    carriers are -- see pick_carrier() for the rule, and
    check_no_false_loyalty() for the assertion that stops this from
    inventing airline loyalty.
  * AGES. No reliable published birth dates, so `traveler_age` is null on
    every row, exactly as it is on all 95 rows of the Gomez log.
    build_travelers.py already renders that as no age rather than a zero.
  * COSTS. Null, same as the travel-show hosts' trips. Inventing what a real
    person spent on a hotel is not a thing this project does; inventing what
    a fictional skier spent is.
  * HOW LONG THEY STAYED in each city. A stop runs from its first show to
    the day before the next stop's first show. They were somewhere for those
    days and it was not home; which of them were in the show city versus in
    transit is not recorded anywhere.

FIVE RULES, EACH OF WHICH CAME FROM A REAL CHOICE
-------------------------------------------------
1. GROUND LEGS UNDER 200km (Ivan's call). A touring act drives those, and
   writing them as flights would put fake segments into every airline and
   airport statistic this project computes. Such a leg carries
   `transportation_type: "Bus"` with a null carrier and NULL AIRPORTS.
   THE COST, accepted deliberately: no destination_airport means
   classify_trip.py cannot tag that row and compute_traveler_entropy.py's
   airport unit cannot count it. The city is still a real destination on a
   real date.
   Every one of these legs is one the route data ALSO has no flight for,
   which is a good sign the cutoff is in the right place -- but the two are
   checked independently, see check_ground_legs().

2. A STOP, NOT A SHOW, IS A ROW (Ivan's call). Luis Miguel played Dolby Live
   three nights running; that is ONE stop with `shows: 3` and three
   `show_dates`, not three rows. Splitting it would put two rows on the same
   trip_id and describe one hotel stay as three journeys.
   `duration_days` is (end - start), i.e. nights, matching every other
   builder here -- so a same-day hop is 0, which is a real value in this
   dataset (see the Gomez log) and not a missing one.

3. NO RETURN LEG (Ivan's call). The last show is the last row. A flight home
   would need an invented date, and the shape this data exists to show --
   one departure, then weeks of never going home -- is complete without it.

4. SUBURB VENUES ARE NAMED FOR THEIR METRO (Ivan's call). The Kia Forum is
   in Inglewood, the UBS Arena in Elmont, the Allstate Arena in Rosemont --
   none of which is in tourist_cities, so as themselves they would carry no
   UNESCO/Michelin/weather score at all. `destination_city` is the metro
   (Los Angeles, New York, Chicago); `venue_city` keeps the municipality so
   nothing is lost.
   THE CONSEQUENCE, and it is a real one: Luis Miguel is recorded as
   visiting "Los Angeles" twice (the Kia Forum, then the Toyota Arena) and
   "New York" twice (Madison Square Garden, then the UBS Arena). Both second
   visits are GROUND arrivals, so they carry no airport at all -- his airport
   entropy is computed over 16 destinations where a city unit would see 19.
   The airport unit is not merely finer than a city unit for this traveler,
   it is blind to the four stops with no flight. Worth knowing before reading
   his entropy as "how much he moved around".

5. A LEG WITH NO NONSTOP IS STILL A FLIGHT, flown by "Airline Unknown".
   build_skiers_trips.check_routes() raises on a route nobody flies, and that
   is right THERE: a fabricated skier can be moved to a route that exists.
   A real tour date cannot. JFK-OKC and OKC-MFE have no nonstop in the route
   data -- entirely plausible, both would connect -- and the shows happened
   anyway. Failing the build would delete a real concert; silently inventing
   a carrier would be worse. So the trip is written with the dataset's
   existing UNKNOWN_CARRIER value and every such leg is printed on every run.

Usage:
    python data/scripts/multiple/build_tour_trips.py
    python data/scripts/multiple/build_tour_trips.py --report
"""

import argparse
import csv
import json
import math
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
REFERENCE_DIR = DATA_DIR / "reference"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"

AIRPORTS_PATH = REFERENCE_DIR / "airports.json"
ROUTES_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"
OUT_JSON = PROCESSED_DIR / "tour_traveler.json"
OUT_CSV = PROCESSED_DIR / "tour_trips.csv"

ACCOMMODATION_TYPE = "Hotel"
FLIGHT = "Flight"
GROUND = "Bus"

# Already in this dataset on 52 rows, from chef_trips.py -- a real trip whose
# flight can't be resolved. Reused rather than invented so anything counting
# "trips with an unresolved airline" keeps counting one thing.
UNKNOWN_CARRIER = "Airline Unknown"

# Legs shorter than this are driven, not flown. Applied as a CHECK, not as
# the thing that decides: each tour names its own ground legs and
# check_ground_legs() asserts that what the table says matches what the
# distances say. A table and a threshold that can drift apart silently is
# worse than either alone.
GROUND_MAX_KM = 200

# --------------------------------------------------------------------------
# Carriers
#
# airline_routes_enhanced.csv is OpenFlights-derived and lists operators as
# of when that data was compiled, which is NOT 2023-24: US Airways ("US") and
# AirTran ("FL") both appear on these routes and neither existed then, and
# several transatlantic carriers show up on ATL-DCA where they are plainly
# codeshares rather than operators. So the eligible set is an explicit
# allowlist of airlines that (a) really operated this flying and (b) already
# appear in this dataset under these exact legal names -- shorten_carrier()
# and airlineColors.ts are both keyed on them.
# --------------------------------------------------------------------------
CARRIER_NAMES = {
    "AA": "American Airlines Inc.",
    "AC": "Air Canada",
    "AM": "Aeromexico",
    "AS": "Alaska Airlines Inc.",
    "B6": "JetBlue Airways",
    "DL": "Delta Air Lines Inc.",
    "F9": "Frontier Airlines Inc.",
    "NK": "Spirit Air Lines",
    "UA": "United Air Lines Inc.",
    "VB": "Aeroenlaces Nacionales, S.A. de C.V. d/b/a VivaAerobus",
    "WN": "Southwest Airlines Co.",
    "Y4": "Concesionaria Vuela Compania De Aviacion SA de CV (Volaris)",
}

# THE ALLOWLIST IS NOT ENOUGH ON ITS OWN. Adding Aeromexico, Volaris and
# VivaAerobus so that MEX-LAS could resolve immediately put Aeromexico on
# Miami-Atlanta, because the route file lists it there -- as a codeshare, not
# as an operator. A Mexican carrier is therefore eligible only on a leg that
# actually touches Mexico. This is the same class of mistake CARRIER_NAMES
# already guards against (US Airways, AirTran), caught one layer further in:
# the file's carrier column answers "whose code appears on this route", which
# is not the same question as "who flies the aircraft".
MEXICO_CARRIERS = {"AM", "VB", "Y4"}

# compute_traveler_tags.py tags an "{Airline} Loyalist" at 80% of
# carrier-recorded trips. Since these carriers are resolved rather than
# documented, a loyalist chip here would be an artifact of the code below,
# not a fact about the artist -- so the build asserts it can't happen.
LOYALIST_THRESHOLD = 0.80

COUNTRY_NAMES = {"US": "United States", "CA": "Canada", "MX": "Mexico"}


def stop(dates, city, airport, venue, cc="US", venue_city=None):
    """One stop on a tour: the metro it is recorded as, its gateway airport,
    and every show played there.

    `venue_city` is set only where the venue's municipality differs from the
    metro name used as `destination_city` -- see rule 4 in the module
    docstring. Where it is None the two are the same and nothing was lost."""
    return {"dates": list(dates), "city": city, "airport": airport,
            "venue": venue, "cc": cc, "venue_city": venue_city}


TOURS = [
    {
        "artist": "María Zardoya",
        "id_prefix": "MZ",
        "nationality": "American",
        "gender": "Female",
        "age": None,
        "base": {"city": "Los Angeles", "country": "United States",
                 "country_code": "US", "airport": "LAX"},
        "tour": "The Submarine Tour",
        "source": "Published 2024 North American tour dates for The Marías.",
        "stops": [
            stop(["2024-07-16"], "Oakland",          "OAK", "Fox Theater"),
            stop(["2024-07-19"], "Las Vegas",        "LAS", "The Chelsea at the Cosmopolitan"),
            stop(["2024-07-20"], "Phoenix",          "PHX", "Arizona Financial Theatre"),
            stop(["2024-07-22"], "Dallas",           "DFW", "South Side Ballroom"),
            stop(["2024-07-24"], "Houston",          "IAH", "713 Music Hall"),
            stop(["2024-07-26"], "Orlando",          "MCO", "Hard Rock Live"),
            stop(["2024-07-27"], "Miami",            "MIA", "The Fillmore Miami Beach"),
            stop(["2024-07-30"], "Atlanta",          "ATL", "Tabernacle"),
            stop(["2024-08-02"], "Washington, D.C.", "DCA", "The Anthem"),
            stop(["2024-08-03"], "Philadelphia",     "PHL", "The Met Philadelphia"),
            stop(["2024-08-06"], "Toronto",          "YYZ", "History", cc="CA"),
            stop(["2024-08-08"], "New York",         "LGA", "Radio City Music Hall"),
            stop(["2024-08-11"], "Boston",           "BOS", "MGM Music Hall at Fenway"),
            stop(["2024-08-13"], "Chicago",          "ORD", "The Salt Shed"),
            stop(["2024-08-15"], "Denver",           "DEN", "The Mission Ballroom"),
            stop(["2024-08-16"], "Salt Lake City",   "SLC", "Twilight Concert Series"),
            stop(["2024-08-18"], "San Diego",        "SAN", "Cal Coast Credit Union Open Air Theatre"),
        ],
        # Keyed by the stop's FIRST show date, which is unique. Not by city:
        # Luis Miguel below has two stops both recorded as "Los Angeles", one
        # arrived at by air and one by road, and a city key could not tell
        # them apart.
        "ground_arrivals": {"2024-08-03"},
    },
    {
        "artist": "Luis Miguel",
        "id_prefix": "LM",
        "nationality": "Mexican",
        "gender": "Male",
        "age": None,
        "base": {"city": "Mexico City", "country": "Mexico",
                 "country_code": "MX", "airport": "MEX"},
        "tour": "Luis Miguel Tour 2023",
        "source": "Published 2023 North American tour dates for Luis Miguel.",
        "stops": [
            stop(["2023-09-15", "2023-09-16", "2023-09-17"],
                 "Las Vegas", "LAS", "Dolby Live"),
            stop(["2023-09-20"], "Anaheim",         "SNA", "Honda Center"),
            stop(["2023-09-21"], "San Diego",       "SAN", "Pechanga Arena"),
            stop(["2023-09-23"], "Phoenix",         "PHX", "Footprint Center"),
            stop(["2023-09-24"], "Los Angeles",     "LAX", "Kia Forum", venue_city="Inglewood"),
            stop(["2023-09-27"], "Los Angeles",     "ONT", "Toyota Arena", venue_city="Ontario"),
            stop(["2023-09-30"], "Palm Springs",    "PSP", "Acrisure Arena", venue_city="Thousand Palms"),
            stop(["2023-10-04", "2023-10-05"],
                 "Chicago", "ORD", "Allstate Arena", venue_city="Rosemont"),
            stop(["2023-10-06"], "Indianapolis",    "IND", "Gainbridge Fieldhouse"),
            stop(["2023-10-08"], "New York",        "LGA", "Madison Square Garden"),
            stop(["2023-10-11", "2023-10-13"],
                 "Miami", "MIA", "Kaseya Center"),
            stop(["2023-10-18"], "Boston",          "BOS", "TD Garden"),
            stop(["2023-10-20"], "Washington, D.C.", "DCA", "Capital One Arena"),
            stop(["2023-10-21"], "Newark",          "EWR", "Prudential Center"),
            stop(["2023-10-22"], "New York",        "JFK", "UBS Arena", venue_city="Elmont"),
            stop(["2023-10-26"], "Oklahoma City",   "OKC", "Paycom Center"),
            stop(["2023-10-28"], "McAllen",         "MFE", "Payne Arena", venue_city="Hidalgo"),
            stop(["2023-10-29"], "Dallas",          "DFW", "American Airlines Center"),
            stop(["2023-11-02"], "Houston",         "IAH", "Toyota Center"),
            stop(["2023-11-04"], "San Antonio",     "SAT", "Frost Bank Center"),
            stop(["2023-11-05"], "Austin",          "AUS", "Moody Center"),
        ],
        # Anaheim->San Diego, LA->Ontario, Ontario->Palm Springs,
        # Newark->Elmont, San Antonio->Austin. All five are under 200km and
        # none of them is a route anybody flies.
        "ground_arrivals": {"2023-09-21", "2023-09-27", "2023-09-30",
                            "2023-10-22", "2023-11-05"},
    },
]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------

def load_airports() -> dict:
    with open(AIRPORTS_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    return {a["iata"]: a for a in payload["airports"] if a.get("iata")}


def load_routes() -> dict:
    """(origin, destination) -> carrier codes. One pass over the route file
    rather than one per leg."""
    routes: dict[tuple[str, str], set[str]] = {}
    with ROUTES_PATH.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            routes.setdefault((row["Departure"], row["Destination"]), set()).add(row["Airline ID"])
    return routes


def great_circle_km(airports: dict, origin: str, dest: str) -> float:
    """Distance between two airports, from airports.json's own coordinates.

    NOT read off airline_routes_enhanced.csv, which only has a distance where
    it has a ROUTE -- and every ground leg in this file is precisely a pair
    nobody flies, so that column is null exactly where the ground rule needs
    a number. Computing it here means the 200km cutoff can be checked on
    every leg rather than on the ones that happen to have a flight."""
    lat1, lon1, lat2, lon2 = (math.radians(v) for v in (
        airports[origin]["lat"], airports[origin]["lng"],
        airports[dest]["lat"], airports[dest]["lng"],
    ))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371.0 * 2 * math.asin(math.sqrt(a))


# --------------------------------------------------------------------------
# The chain
# --------------------------------------------------------------------------

def legs_of(tour: dict) -> list[dict]:
    """The tour as a list of legs, each carrying where it STARTS.

    This is the whole difference from every other builder here: leg N's
    origin is leg N-1's gateway airport. Only the first leg departs from
    home.

    Note the origin is the previous stop's GATEWAY even when the artist
    arrived there by road: he drives Newark to Elmont and then flies out of
    JFK, so JFK is where the next leg starts regardless of how he reached
    it."""
    out = []
    origin = tour["base"]["airport"]
    for i, s in enumerate(tour["stops"]):
        first = date.fromisoformat(s["dates"][0])
        out.append({
            **s,
            "index": i + 1,
            "first_show": first,
            "last_show": date.fromisoformat(s["dates"][-1]),
            "country": COUNTRY_NAMES[s["cc"]],
            "origin": origin,
            "ground": s["dates"][0] in tour["ground_arrivals"],
        })
        origin = s["airport"]
    return out


def check_ground_legs(airports: dict) -> None:
    """The ground table and the distance threshold must agree.

    Two ways to be wrong, both checked: a leg marked ground that is too long
    to drive between shows, and a leg left as a flight that is shorter than
    the cutoff. Either means the table and GROUND_MAX_KM have drifted apart,
    and the one thing worse than picking the wrong cutoff is having a cutoff
    nobody notices has stopped applying."""
    problems = []
    for tour in TOURS:
        for leg in legs_of(tour):
            distance = great_circle_km(airports, leg["origin"], leg["airport"])
            if leg["ground"] and distance > GROUND_MAX_KM:
                problems.append(
                    f"{tour['artist']} {leg['dates'][0]}: {leg['origin']}-{leg['airport']} is "
                    f"marked ground but is {distance:.0f}km, over the {GROUND_MAX_KM}km cutoff"
                )
            if not leg["ground"] and distance <= GROUND_MAX_KM:
                problems.append(
                    f"{tour['artist']} {leg['dates'][0]}: {leg['origin']}-{leg['airport']} is "
                    f"{distance:.0f}km, at or under the {GROUND_MAX_KM}km cutoff, but is not in "
                    "ground_arrivals"
                )
    if problems:
        raise SystemExit("Ground-leg check failed:\n  " + "\n  ".join(problems))


def eligible_carriers(codes, airports=None, origin=None, dest=None) -> list[str]:
    """The subset of a route's operators this build will use -- see
    CARRIER_NAMES for why the route file's own list can't be used raw, and
    MEXICO_CARRIERS for why membership in it still isn't sufficient.

    Called without the airport arguments (as check-style callers do) the
    Mexico rule is skipped; the one place that actually writes a carrier
    always passes them."""
    codes = {code for code in codes if code in CARRIER_NAMES}
    if airports is not None and origin is not None and dest is not None:
        touches_mexico = any(
            airports.get(code, {}).get("country") == "Mexico" for code in (origin, dest)
        )
        if not touches_mexico:
            codes -= MEXICO_CARRIERS
    return sorted(codes)


def pick_carrier(codes, used: Counter, airports, origin, dest) -> str | None:
    """Choose one airline for a leg: the eligible carrier this artist has
    flown LEAST so far, ties broken alphabetically. None when the route data
    knows no eligible operator -- see rule 5 in the module docstring.

    Deterministic, and deliberately spreading rather than preferring. Nobody
    published which airline they flew, so any single choice would be invented
    -- but a choice that happened to concentrate on one carrier would be
    worse than invented, because compute_traveler_tags.py would then hang an
    "{Airline} Loyalist" chip on them and the chip would be describing this
    function rather than describing the artist. Least-used-first makes that
    unlikely; check_no_false_loyalty() makes it impossible."""
    available = eligible_carriers(codes, airports, origin, dest)
    if not available:
        return None
    return min(available, key=lambda code: (used[code], code))


def check_no_false_loyalty(trips: list[dict], artist: str) -> None:
    """No resolved carrier may reach the loyalist threshold. See pick_carrier.

    "Airline Unknown" is excluded from the denominator as well as the
    numerator: it is the absence of a resolution, not a resolution."""
    flown = [t for t in trips if t["carrier_name"] and t["carrier_name"] != UNKNOWN_CARRIER]
    if not flown:
        return
    for carrier, n in Counter(t["carrier_name"] for t in flown).items():
        share = n / len(flown)
        if share >= LOYALIST_THRESHOLD:
            raise SystemExit(
                f"{artist}: carrier resolution produced {share:.0%} on {carrier} "
                f"({n} of {len(flown)} resolved legs), at or above the "
                f"{LOYALIST_THRESHOLD:.0%} loyalist threshold. That chip would describe "
                "pick_carrier(), not the traveler."
            )


# --------------------------------------------------------------------------
# Rows
# --------------------------------------------------------------------------

def build_rows(airports: dict, routes: dict) -> tuple[list[dict], list[dict], list[str]]:
    trips, report, unresolved = [], [], []

    for tour in TOURS:
        legs = legs_of(tour)
        used: Counter = Counter()
        tour_trips: list[dict] = []

        for i, leg in enumerate(legs):
            # A stop runs from its first show to the day BEFORE the next
            # stop's first show, so no two rows claim the same day and the
            # tour reads as one unbroken block of time away. The last stop
            # ends on its own last show.
            start = leg["first_show"]
            end = (legs[i + 1]["first_show"] - timedelta(days=1)
                   if i + 1 < len(legs) else leg["last_show"])
            nights = (end - start).days
            distance = great_circle_km(airports, leg["origin"], leg["airport"])
            carriers = routes.get((leg["origin"], leg["airport"]), set())

            if leg["ground"]:
                carrier_name = None
                origin_airport = destination_airport = None
                transportation = GROUND
            else:
                code = pick_carrier(carriers, used, airports, leg["origin"], leg["airport"])
                if code is None:
                    carrier_name = UNKNOWN_CARRIER
                    unresolved.append(
                        f"{tour['artist']} {leg['dates'][0]} {leg['origin']}-{leg['airport']} "
                        f"({leg['city']}, {distance:.0f}km)"
                    )
                else:
                    used[code] += 1
                    carrier_name = CARRIER_NAMES[code]
                origin_airport = leg["origin"]
                destination_airport = leg["airport"]
                transportation = FLIGHT

            row = {
                "trip_id": f"{tour['id_prefix']}-{start.isoformat()}",
                "destination_raw": f"{leg['city']}, {leg['country']}",
                "destination_city": leg["city"],
                "destination_country": leg["country"],
                "destination_country_code": leg["cc"],
                "destination_kind": "city",
                "start_date": start.isoformat(),
                "start_date_raw": start.isoformat(),
                "end_date": end.isoformat(),
                "end_date_raw": end.isoformat(),
                "duration_days": nights,
                "duration_raw": f"{nights} days",
                "accommodation_type": ACCOMMODATION_TYPE,
                # Null, not invented -- these are real people. Same as the
                # travel-show hosts' trips.
                "accommodation_cost": None,
                "accommodation_cost_raw": None,
                "transportation_type": transportation,
                "transportation_cost": None,
                "transportation_cost_raw": None,
                "traveler_name": tour["artist"],
                "traveler_age": tour["age"],
                "traveler_gender": tour["gender"],
                "traveler_nationality": tour["nationality"],
                # "not from the Kaggle CSV", which is what this flag has
                # always meant here -- NOT "made up". The dates are real.
                "synthetic": True,
                "carrier_name": carrier_name,
                "origin_airport": origin_airport,
                "destination_airport": destination_airport,
                "layover": False,
                # Provenance, the same way the hosts' trips carry `show` and
                # `episode_title`: what a reader needs to check this row
                # against the published listing.
                "tour": tour["tour"],
                "venue": leg["venue"],
                # The municipality the venue is actually in, where that
                # differs from the metro this row is filed under. Null when
                # they are the same. See rule 4.
                "venue_city": leg["venue_city"],
                # A residency is one stop, not several rows -- rule 2.
                "shows": len(leg["dates"]),
                "show_dates": leg["dates"],
                "tour_leg": leg["index"],
                "tour_legs_total": len(legs),
            }
            trips.append(row)
            tour_trips.append(row)

            report.append({
                "trip_id": row["trip_id"],
                "traveler_name": tour["artist"],
                "tour_leg": leg["index"],
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "nights": nights,
                "shows": len(leg["dates"]),
                "origin_airport": leg["origin"],
                "destination_airport": leg["airport"],
                "destination_city": leg["city"],
                "venue_city": leg["venue_city"] or "",
                "venue": leg["venue"],
                "transportation_type": transportation,
                "carrier_name": carrier_name or "",
                "distance_km": round(distance, 1),
                "route_carriers": ", ".join(sorted(carriers)),
            })

        check_no_false_loyalty(tour_trips, tour["artist"])

    trips.sort(key=lambda t: (t["traveler_name"], t["start_date"]))
    report.sort(key=lambda r: (r["traveler_name"], r["start_date"]))
    return trips, report, unresolved


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Build the touring-musician travelers.")
    parser.add_argument("--report", action="store_true",
                        help="print every leg and which airlines the route data lists")
    args = parser.parse_args()

    airports = load_airports()
    routes = load_routes()
    check_ground_legs(airports)
    trips, report, unresolved = build_rows(airports, routes)

    declared_bases = {
        t["artist"]: dict(base_city=t["base"]["city"],
                          base_country=t["base"]["country"],
                          base_country_code=t["base"]["country_code"])
        for t in TOURS
    }

    payload = {
        "source": (
            "Published concert itineraries, one traveler per tour -- see "
            "build_tour_trips.py. A TOUR IS A CHAIN, not a star: every leg after the "
            "first departs from the previous show's city rather than from home, which "
            "is a pattern no other itinerary in this dataset has."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "The dates, cities and venues are REAL and come from the published "
            "listings; `synthetic: true` here means 'not from the Kaggle CSV', the "
            "same as it does on the travel-show hosts' rows. What is NOT documented is "
            "left null rather than invented: age, accommodation cost and transportation "
            "cost are null on every row. The AIRLINE is resolved from "
            "airline_routes_enhanced.csv rather than published -- least-flown-first "
            "among the carriers that route data says serve the leg, and the build fails "
            "if that resolution ever concentrates enough on one airline to earn a "
            "Loyalist tag; a leg with no nonstop in the route data is still a flight, "
            "flown by 'Airline Unknown'. Legs under 200km are ground transport with no "
            "airports or carrier, so they are invisible to airport entropy and to "
            "classify_trip.py by design. A multi-night residency is ONE stop carrying "
            "`shows` and `show_dates`, not one row per night. Suburb venues are filed "
            "under their metro city with `venue_city` recording the municipality. "
            "Merged into trips_enhanced.json by build_trips_enhanced.py."
        ),
        "carrier_preference": ["resolved from route data, least-flown-first"],
        "declared_bases": declared_bases,
        "tours": [{"artist": t["artist"], "tour": t["tour"], "source": t["source"],
                   "stops": len(t["stops"]),
                   "shows": sum(len(s["dates"]) for s in t["stops"])} for t in TOURS],
        "unresolved_nonstops": unresolved,
        "total_travelers": len(TOURS),
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

    for tour in TOURS:
        rows = [t for t in trips if t["traveler_name"] == tour["artist"]]
        flown = [t for t in rows if t["transportation_type"] == FLIGHT]
        resolved = [t for t in flown if t["carrier_name"] != UNKNOWN_CARRIER]
        first, last = rows[0]["start_date"], rows[-1]["end_date"]
        away = (date.fromisoformat(last) - date.fromisoformat(first)).days + 1
        cities = Counter(t["destination_city"] for t in rows)
        repeated = {c: n for c, n in cities.items() if n > 1}
        print(f"{tour['artist']} -- {tour['tour']}")
        print(f"  {len(rows)} stops, {sum(t['shows'] for t in rows)} shows, {first} to {last} "
              f"({away} days away from {tour['base']['city']} without returning)")
        print(f"  {len(flown)} flights ({len(resolved)} with a resolved airline, "
              f"{len(flown) - len(resolved)} unknown), {len(rows) - len(flown)} ground")
        print(f"  {len(cities)} distinct cities, "
              f"{len({t['origin_airport'] for t in rows if t['origin_airport']})} "
              f"distinct departure airports, "
              f"{len({t['carrier_name'] for t in resolved})} airlines")
        if repeated:
            print(f"  visited twice: {', '.join(f'{c} ({n})' for c, n in sorted(repeated.items()))}")

    if unresolved:
        # Printed every run, never buried: these are the legs where this file
        # is writing a flight the route data cannot corroborate. See rule 5.
        print()
        print(f"{len(unresolved)} leg(s) have no nonstop in the route data -- "
              f"written as '{UNKNOWN_CARRIER}':")
        for line in unresolved:
            print(f"  {line}")

    if args.report:
        print()
        print(f"{'leg':>3}  {'date':10} {'from':4} {'to':4} {'city':<17} {'sh':>2} "
              f"{'nt':>3} {'km':>6}  {'carrier':<26} route carriers")
        for r in report:
            print(f"{r['tour_leg']:3}  {r['start_date']:10} {r['origin_airport']:4} "
                  f"{r['destination_airport']:4} {r['destination_city']:<17} {r['shows']:2} "
                  f"{r['nights']:3} {r['distance_km']:6.0f}  "
                  f"{(r['carrier_name'] or r['transportation_type']):<26} {r['route_carriers']}")

    print()
    print(f"Wrote -> {OUT_CSV}")
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
