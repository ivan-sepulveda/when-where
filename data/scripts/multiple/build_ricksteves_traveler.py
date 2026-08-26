"""
Derived from: data/processed/multiple/ricksteves_trips.json (built by
              build_ricksteves_trips.py from the Rick Steves' Europe
              episode list)
Requires: chef_traveler.py, which reads
          data/processed/multiple/airline_routes_enhanced.csv and
          data/raw/bts_t100/*.csv

The Rick Steves half of the pipeline build_bourdain_traveler.py,
build_ramsay_traveler.py and build_conan_traveler.py run: turns the
show's trips into ONE traveler and writes
data/processed/multiple/ricksteves_traveler.json, which
build_trips_enhanced.py merges via its SYNTHETIC_SOURCES tuple.

    build_ricksteves_trips.py     episodes    -> ricksteves_trips.json
    build_ricksteves_traveler.py  + carriers  -> ricksteves_traveler.json
    build_trips_enhanced.py       merge       -> trips_enhanced.json

ONE HOME AIRPORT, NOT THREE. Bourdain/Ramsay/Conan each get an ordered
preference of three home airports because New York and Los Angeles each
have three sizeable ones. Seattle has one that matters here (SEA), so
ORIGIN_PREFERENCE in build_ricksteves_trips.py is a one-element tuple --
not a simplification, just what Seattle actually is.

CARRIER_PREFERENCE is Delta, then United, then Alaska. Delta is SEA's own
transatlantic hub carrier and wins most of these trips outright (it's the
only preferred airline on the Paris/London/Amsterdam routes); United
covers the Frankfurt route; Alaska -- SEA's biggest carrier by far in
real life -- is included third for the same "home team" reason Bourdain's
preference leads with Delta and Ramsay's with United, but it doesn't
actually fly any of the six European routes this dataset uses, so expect
it to lose every tie and show up only if a future episode adds a route it
serves.

Age is computed from Rick Steves' real, published birthdate (May 10,
1955), so he ages across the show's real 25-year run (45 at the Season 1
premiere in 2000, 70 by the Season 13 London finale in 2025) -- same
"real person, real birthdate" rule as Bourdain/Ramsay/Conan.

Usage:
    python build_ricksteves_traveler.py
    python build_ricksteves_traveler.py --report   # one line per trip: route, airlines available, pick
"""

import argparse
from datetime import date

from chef_traveler import (  # noqa: E402
    PROCESSED_DIR,
    build_trips,
    print_summary,
    write_output,
)

TRIPS_PATH = PROCESSED_DIR / "ricksteves_trips.json"
OUT_PATH = PROCESSED_DIR / "ricksteves_traveler.json"

TRAVELER = {
    "name": "Rick Steves",
    "gender": "Male",
    "nationality": "American",
}
BIRTH_DATE = date(1955, 5, 10)

# "RS" is unused by the 82 synthetic travelers, Bourdain's "AB", Ramsay's
# "GR", Conan's "CO" and Gomez's "EG" (checked against trips_enhanced.json).
# A duplicate prefix would silently merge two people's trips, since
# trip_id is prefix + date.
ID_PREFIX = "RS"

# Rick Steves lives in Edmonds, WA (a Seattle suburb) and the show's
# company is headquartered there -- see build_ricksteves_trips.py.
DECLARED_BASE = {
    "base_city": "Seattle",
    "base_country": "United States",
    "base_country_code": "US",
}

# Home-team order: SEA's real Skyteam transatlantic hub carrier first,
# United (Frankfurt) second, Alaska -- Seattle's actual biggest carrier,
# but absent from every European route this dataset flies -- third.
CARRIER_PREFERENCE = (("DL", "Delta"), ("UA", "United"), ("AS", "Alaska"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print every route, the airlines that fly it, and which one was picked")
    args = parser.parse_args()

    trips, report = build_trips(
        TRIPS_PATH, TRAVELER, CARRIER_PREFERENCE, ID_PREFIX, BIRTH_DATE,
        rebuild_hint="build_ricksteves_trips.py",
    )

    write_output(
        OUT_PATH, trips, TRAVELER, DECLARED_BASE, CARRIER_PREFERENCE,
        source_note=f"{TRIPS_PATH.name} (Rick Steves' Europe episodes, see "
                    "build_ricksteves_trips.py), with an airline chosen per trip from the "
                    "operators of that route",
        trip_note="FABRICATED trips for one real person: the episodes, dates and routes are "
                  "real, the journey, its 5-day length and the airline are not. Costs are "
                  "deliberately null rather than invented. Merged into trips_enhanced.json by "
                  "build_trips_enhanced.py.",
    )
    print_summary(trips, report, TRAVELER, CARRIER_PREFERENCE, OUT_PATH, show_report=args.report)


if __name__ == "__main__":
    main()
