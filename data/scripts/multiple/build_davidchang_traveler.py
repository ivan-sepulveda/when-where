"""
Derived from: data/processed/multiple/davidchang_trips.json (built by
              build_davidchang_trips.py from the Breakfast, Lunch & Dinner
              episode list)
Requires: chef_traveler.py, which reads
          data/processed/multiple/airline_routes_enhanced.csv and
          data/raw/bts_t100/*.csv

The David Chang half of the pipeline build_bourdain_traveler.py,
build_ramsay_traveler.py, build_conan_traveler.py and
build_ricksteves_traveler.py run: turns the show's trips into ONE
traveler and writes data/processed/multiple/davidchang_traveler.json,
which build_trips_enhanced.py merges via its SYNTHETIC_SOURCES tuple.

    build_davidchang_trips.py     episodes    -> davidchang_trips.json
    build_davidchang_traveler.py  + carriers  -> davidchang_traveler.json
    build_trips_enhanced.py       merge       -> trips_enhanced.json

SAME AIRPORTS, SAME AIRLINES AS BOURDAIN -- per Ivan's explicit
instruction ("Base him out of NYC with the same rules as Anthony
Bourdain in terms of airline/airport preferences"). ORIGIN_PREFERENCE in
build_davidchang_trips.py is Bourdain's exact three-airport tuple
(JFK, LGA, EWR), and CARRIER_PREFERENCE below is Bourdain's exact
Delta/United/American order -- not independently derived from David
Chang's own travel habits, which the source material doesn't cover.

Age is computed from David Chang's real, published birthdate (August 5,
1977), same "real person, real birthdate" rule as Bourdain/Ramsay/
Conan/Rick Steves. His Wikipedia article doesn't state a current
residence (he was born in Arlington, VA and grew up in Vienna, VA); the
New York base is per Ivan's instruction, framed the same way Conan's
New York-not-Los-Angeles base was.

Usage:
    python build_davidchang_traveler.py
    python build_davidchang_traveler.py --report   # one line per trip: route, airlines available, pick
"""

import argparse
from datetime import date

from chef_traveler import (  # noqa: E402
    PROCESSED_DIR,
    build_trips,
    print_summary,
    write_output,
)

TRIPS_PATH = PROCESSED_DIR / "davidchang_trips.json"
OUT_PATH = PROCESSED_DIR / "davidchang_traveler.json"

TRAVELER = {
    "name": "David Chang",
    "gender": "Male",
    "nationality": "American",
}
BIRTH_DATE = date(1977, 8, 5)

# "DC" is unused by the 82 synthetic travelers, Bourdain's "AB", Ramsay's
# "GR", Conan's "CO", Gomez's "EG" and Rick Steves' "RS" (checked against
# trips_enhanced.json). A duplicate prefix would silently merge two
# people's trips, since trip_id is prefix + date.
ID_PREFIX = "DC"

DECLARED_BASE = {
    "base_city": "New York City",
    "base_country": "United States",
    "base_country_code": "US",
}

# Bourdain's exact preference order, per Ivan's instruction to use the
# same airline rules: Delta, then United, then American.
CARRIER_PREFERENCE = (("DL", "Delta"), ("UA", "United"), ("AA", "American"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print every route, the airlines that fly it, and which one was picked")
    args = parser.parse_args()

    trips, report = build_trips(
        TRIPS_PATH, TRAVELER, CARRIER_PREFERENCE, ID_PREFIX, BIRTH_DATE,
        rebuild_hint="build_davidchang_trips.py",
    )

    write_output(
        OUT_PATH, trips, TRAVELER, DECLARED_BASE, CARRIER_PREFERENCE,
        source_note=f"{TRIPS_PATH.name} (Breakfast, Lunch & Dinner episodes, see "
                    "build_davidchang_trips.py), with an airline chosen per trip from the "
                    "operators of that route",
        trip_note="FABRICATED trips for one real person: the episodes, dates and routes are "
                  "real, the journey, its 5-day length and the airline are not. Costs are "
                  "deliberately null rather than invented. Merged into trips_enhanced.json by "
                  "build_trips_enhanced.py.",
    )
    print_summary(trips, report, TRAVELER, CARRIER_PREFERENCE, OUT_PATH, show_report=args.report)


if __name__ == "__main__":
    main()
