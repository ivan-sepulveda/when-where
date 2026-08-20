"""
Derived from: data/processed/multiple/bourdain_trips.json (built by
              build_bourdain_trips.py from the No Reservations and Parts
              Unknown episode lists)
Requires: chef_traveler.py, which reads
          data/processed/multiple/airline_routes_enhanced.csv and
          data/raw/bts_t100/*.csv

Turns the No Reservations and Parts Unknown trips into ONE traveler in
the shape the rec-sys pipeline already speaks, and writes
data/processed/multiple/bourdain_traveler.json. build_trips_enhanced.py
merges this file exactly the way it merges synthetic_trips.json (all of
them are listed in its SYNTHETIC_SOURCES), so the pipeline stays:

    build_bourdain_trips.py    both shows     -> bourdain_trips.json
    build_bourdain_traveler.py + carriers     -> bourdain_traveler.json
    build_trips_enhanced.py    merge          -> trips_enhanced.json
    build_travelers.py         group          -> travelers.json
    build_travelers_anon.py    personas       -> travelers_anon.json

Bourdain is kept OUT of build_synthetic_trips.py on purpose. Those 82
travelers are hand-authored itineraries invented to exercise the
recommender; this one's itinerary is data -- 130 rows derived from two
published episode lists -- and it should be rebuildable from those
sources without touching a 120KB file of authored patterns.

WHICH AIRLINE HE FLEW
---------------------
The trip already knows its airports (JFK preferred, then LGA, then EWR --
see build_bourdain_trips.py). Among the airlines that fly that exact
route: Delta, then United, then American, then anything else at random.
See chef_traveler.py for why that is matched on IATA code and why the
random draw is seeded per trip.

His age is computed from a real birthdate, so it moves across both shows
(49 on the first trip in 2005, 62 on the last in 2018).

Usage:
    python build_bourdain_traveler.py
    python build_bourdain_traveler.py --report   # one line per trip: route, airlines available, pick
"""

import argparse
from datetime import date

from chef_traveler import (  # noqa: E402
    PROCESSED_DIR,
    build_trips,
    print_summary,
    write_output,
)

TRIPS_PATH = PROCESSED_DIR / "bourdain_trips.json"
OUT_PATH = PROCESSED_DIR / "bourdain_traveler.json"

TRAVELER = {
    "name": "Anthony Bourdain",
    "gender": "Male",
    "nationality": "American",
}
BIRTH_DATE = date(1956, 6, 25)

# trip_id is prefix + ISO start date, and a duplicate prefix silently merges
# two people's trips -- "AB" is unused by the 82 travelers in
# build_synthetic_trips.py (checked against trips_enhanced.json).
ID_PREFIX = "AB"

DECLARED_BASE = {
    "base_city": "New York City",
    "base_country": "United States",
    "base_country_code": "US",
}

# In order, by IATA code. See chef_traveler.pick_carrier().
CARRIER_PREFERENCE = (("DL", "Delta"), ("UA", "United"), ("AA", "American"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print every route, the airlines that fly it, and which one was picked")
    args = parser.parse_args()

    trips, report = build_trips(
        TRIPS_PATH, TRAVELER, CARRIER_PREFERENCE, ID_PREFIX, BIRTH_DATE,
        rebuild_hint="build_bourdain_trips.py",
    )

    write_output(
        OUT_PATH, trips, TRAVELER, DECLARED_BASE, CARRIER_PREFERENCE,
        source_note=f"{TRIPS_PATH.name} (No Reservations and Parts Unknown episodes, see "
                    "build_bourdain_trips.py), with an airline chosen per trip from the "
                    "operators of that route",
        trip_note="FABRICATED trips for one real person: the episodes, dates and routes are "
                  "real, the journey, its 5-day length and the airline are not. Costs are "
                  "deliberately null rather than invented. Merged into trips_enhanced.json by "
                  "build_trips_enhanced.py.",
    )
    print_summary(trips, report, TRAVELER, CARRIER_PREFERENCE, OUT_PATH, show_report=args.report)


if __name__ == "__main__":
    main()
