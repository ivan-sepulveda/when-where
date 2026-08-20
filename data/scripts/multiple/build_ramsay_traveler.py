"""
Derived from: data/processed/multiple/ramsay_trips.json (built by
              build_ramsay_trips.py from the Gordon Ramsay: Uncharted
              episode list)
Requires: chef_traveler.py, which reads
          data/processed/multiple/airline_routes_enhanced.csv and
          data/raw/bts_t100/*.csv

The Ramsay half of the same pipeline build_bourdain_traveler.py runs:
turns the Uncharted trips into ONE traveler and writes
data/processed/multiple/ramsay_traveler.json, which
build_trips_enhanced.py merges via its SYNTHETIC_SOURCES tuple.

    build_ramsay_trips.py     Uncharted      -> ramsay_trips.json
    build_ramsay_traveler.py  + carriers     -> ramsay_traveler.json
    build_trips_enhanced.py   merge          -> trips_enhanced.json

HOW HE DIFFERS FROM BOURDAIN, ON PURPOSE. Same machinery, three different
settings, and the point of adding him is that the recommender gets a
second real-world-shaped profile that is not a copy of the first:

  * he flies out of LOS ANGELES (LAX, then LAS as fallback), not New York
  * he prefers UNITED, then Delta, then American -- Bourdain's order is
    Delta first
  * Uncharted is 29 episodes to Bourdain's 246, and its whole premise is
    hard-to-reach places, so far more of it fails the flights-only rule

Nationality is recorded as British, which is what he is, while the base
city is Los Angeles, which is where these trips depart. build_travelers.py
prefers a declared base over its nationality-based guess, so the two don't
fight -- see its infer_base().

Age is computed from a real birthdate, so he ages across the run of the
show (52 in season 1, 57 by season 4).

Usage:
    python build_ramsay_traveler.py
    python build_ramsay_traveler.py --report   # one line per trip: route, airlines available, pick
"""

import argparse
from datetime import date

from chef_traveler import (  # noqa: E402
    PROCESSED_DIR,
    build_trips,
    print_summary,
    write_output,
)

TRIPS_PATH = PROCESSED_DIR / "ramsay_trips.json"
OUT_PATH = PROCESSED_DIR / "ramsay_traveler.json"

TRAVELER = {
    "name": "Gordon Ramsay",
    "gender": "Male",
    "nationality": "British",
}
BIRTH_DATE = date(1966, 11, 8)

# "GR" is unused by the 82 synthetic travelers and by Bourdain's "AB"
# (checked against trips_enhanced.json). A duplicate prefix would silently
# merge two people's trips, since trip_id is prefix + start date.
ID_PREFIX = "GR"

DECLARED_BASE = {
    "base_city": "Los Angeles",
    "base_country": "United States",
    "base_country_code": "US",
}

# United first, per Ivan. Same mechanism as Bourdain's, different order --
# see chef_traveler.pick_carrier().
CARRIER_PREFERENCE = (("UA", "United"), ("DL", "Delta"), ("AA", "American"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print every route, the airlines that fly it, and which one was picked")
    args = parser.parse_args()

    trips, report = build_trips(
        TRIPS_PATH, TRAVELER, CARRIER_PREFERENCE, ID_PREFIX, BIRTH_DATE,
        rebuild_hint="build_ramsay_trips.py",
    )

    write_output(
        OUT_PATH, trips, TRAVELER, DECLARED_BASE, CARRIER_PREFERENCE,
        source_note=f"{TRIPS_PATH.name} (Gordon Ramsay: Uncharted episodes, see "
                    "build_ramsay_trips.py), with an airline chosen per trip from the "
                    "operators of that route",
        trip_note="FABRICATED trips for one real person: the episodes, dates and routes are "
                  "real, the journey, its 5-day length and the airline are not. Costs are "
                  "deliberately null rather than invented. Merged into trips_enhanced.json by "
                  "build_trips_enhanced.py.",
    )
    print_summary(trips, report, TRAVELER, CARRIER_PREFERENCE, OUT_PATH, show_report=args.report)


if __name__ == "__main__":
    main()
