"""
Derived from: data/processed/multiple/conan_trips.json (built by
              build_conan_trips.py from the Conan Without Borders and
              Conan O'Brien Must Go episode lists)
Requires: chef_traveler.py, which reads
          data/processed/multiple/airline_routes_enhanced.csv and
          data/raw/bts_t100/*.csv

The Conan half of the pipeline build_bourdain_traveler.py and
build_ramsay_traveler.py run: turns both shows' trips into ONE
traveler and writes data/processed/multiple/conan_traveler.json, which
build_trips_enhanced.py merges via its SYNTHETIC_SOURCES tuple.

    build_conan_trips.py     both shows      -> conan_trips.json
    build_conan_traveler.py  + carriers      -> conan_traveler.json
    build_trips_enhanced.py  merge           -> trips_enhanced.json

DELIBERATELY IDENTICAL TO BOURDAIN except for the destinations. Same home
airports (JFK, then LGA, then EWR), same airline preference (Delta, then
United, then American, then a seeded random draw), same 5-day trip. Ivan
asked for that on purpose: with the origin and the carrier rules held
constant, any difference between these two travelers is a difference in
where they went and when, which is the variable the recommender is
actually about. Ramsay is the opposite case -- see build_ramsay_traveler.py.

Age is computed from a real birthdate, so he ages across both shows
(51 at Cuba in 2015, 62 by the Austria episode in 2025).

Usage:
    python build_conan_traveler.py
    python build_conan_traveler.py --report   # one line per trip: route, airlines available, pick
"""

import argparse
from datetime import date

from chef_traveler import (  # noqa: E402
    PROCESSED_DIR,
    build_trips,
    print_summary,
    write_output,
)

TRIPS_PATH = PROCESSED_DIR / "conan_trips.json"
OUT_PATH = PROCESSED_DIR / "conan_traveler.json"

TRAVELER = {
    "name": "Conan O'Brien",
    "gender": "Male",
    "nationality": "American",
}
BIRTH_DATE = date(1963, 4, 18)

# "CO" is unused by the 82 synthetic travelers, by Bourdain's "AB" and by
# Ramsay's "GR" (checked against trips_enhanced.json). A duplicate prefix
# would silently merge two people's trips, since trip_id is prefix + date.
ID_PREFIX = "CO"

# Follows ORIGIN_PREFERENCE in build_conan_trips.py rather than where the
# show taped -- see that file's "NEW YORK, NOT LOS ANGELES".
DECLARED_BASE = {
    "base_city": "New York City",
    "base_country": "United States",
    "base_country_code": "US",
}

# Bourdain's order exactly, per Ivan.
CARRIER_PREFERENCE = (("DL", "Delta"), ("UA", "United"), ("AA", "American"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print every route, the airlines that fly it, and which one was picked")
    args = parser.parse_args()

    trips, report = build_trips(
        TRIPS_PATH, TRAVELER, CARRIER_PREFERENCE, ID_PREFIX, BIRTH_DATE,
        rebuild_hint="build_conan_trips.py",
    )

    write_output(
        OUT_PATH, trips, TRAVELER, DECLARED_BASE, CARRIER_PREFERENCE,
        source_note=f"{TRIPS_PATH.name} (Conan Without Borders episodes, see "
                    "build_conan_trips.py), with an airline chosen per trip from the "
                    "operators of that route",
        trip_note="FABRICATED trips for one real person: the episodes, dates and routes are "
                  "real, the journey, its 5-day length and the airline are not. Costs are "
                  "deliberately null rather than invented. Merged into trips_enhanced.json by "
                  "build_trips_enhanced.py.",
    )
    print_summary(trips, report, TRAVELER, CARRIER_PREFERENCE, OUT_PATH, show_report=args.report)


if __name__ == "__main__":
    main()
