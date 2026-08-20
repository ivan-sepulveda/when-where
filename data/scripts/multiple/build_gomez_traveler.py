"""
Derived from: data/processed/multiple/gomez_trips.json (the hand-kept
              flight log -- see build_gomez_trips.py)
Requires: chef_traveler.py, which reads
          data/processed/multiple/airline_routes_enhanced.csv and
          data/raw/bts_t100/*.csv (carrier code -> full airline name)

Turns the logged legs into ONE traveler and writes
data/processed/multiple/gomez_traveler.json, which
build_trips_enhanced.py merges via its SYNTHETIC_SOURCES tuple -- the same
last mile every other traveler in this project goes through, so the
/rec-sys page and the API need no special case for a real one.

THE ONE TRAVELER HERE WHOSE TRIPS ARE TRUE. Bourdain, Ramsay and Conan are
fabricated itineraries built on real routes: the show went somewhere, and
the trip is this project's guess at the flight. Eduardo Gomez is a
pseudonym for a real person logging real flights. Nothing about a leg is
inferred except the destination's city and country.

That difference is why three fields the others carry are absent rather
than filled:

  * NO AGE, GENDER OR NATIONALITY. The public figures have published
    biographies; a private person does not get invented ones. Their
    absence is why build_travelers.py would otherwise guess a home city,
    and why the base below is declared instead.
  * NO CARRIER PREFERENCE. CARRIER_PREFERENCE is empty on purpose: the log
    names the airline flown, and chef_traveler.build_trips() marks those
    "logged" rather than "preferred" or "random". If a future leg is ever
    logged without one, the report will say it was drawn at random, which
    is the signal to go and look it up instead.
  * NO BIRTHDATE, so traveler_age is null on every trip.

The name is a pseudonym and the dataset says so, in gomez_trips.json's
`traveler.pseudonym`. It travels through build_travelers_anon.py untouched
(`synthetic: true` keeps an authored name as-is), so the id is
"eduardo-gomez" and no author persona is assigned over it.

Usage:
    python build_gomez_traveler.py
    python build_gomez_traveler.py --report   # one line per leg: route, carrier, how it was chosen
"""

import argparse

from chef_traveler import (  # noqa: E402
    PROCESSED_DIR,
    build_trips,
    print_summary,
    write_output,
)

TRIPS_PATH = PROCESSED_DIR / "gomez_trips.json"
OUT_PATH = PROCESSED_DIR / "gomez_traveler.json"

TRAVELER = {
    "name": "Eduardo Gomez",
    "gender": None,
    "nationality": None,
}

# No birthdate: see the docstring. traveler_age comes out null.
BIRTH_DATE = None

# "EG" is unused by the 82 synthetic travelers and by AB / GR / CO
# (checked against trips_enhanced.json). A duplicate prefix would silently
# merge two people's trips, since trip_id is prefix + start date.
ID_PREFIX = "EG"

DECLARED_BASE = {
    "base_city": "Houston",
    "base_country": "United States",
    "base_country_code": "US",
}

# Empty on purpose -- the log names the airline. See the docstring.
CARRIER_PREFERENCE = ()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true",
                        help="print every leg, the airlines on that route, and which was recorded")
    args = parser.parse_args()

    trips, report = build_trips(
        TRIPS_PATH, TRAVELER, CARRIER_PREFERENCE, ID_PREFIX, BIRTH_DATE,
        rebuild_hint="build_gomez_trips.py",
        trips_key="legs",
        # Nothing in a flight log says where anyone stayed.
        accommodation_type=None,
    )

    write_output(
        OUT_PATH, trips, TRAVELER, DECLARED_BASE, CARRIER_PREFERENCE,
        source_note=f"{TRIPS_PATH.name} (a hand-kept flight log, see build_gomez_trips.py), "
                    "with the airline recorded as flown",
        trip_note="REAL trips under a pseudonym: the legs, dates, airports and airlines are "
                  "as flown, not fabricated. Costs are null because none were recorded, and "
                  "age/gender/nationality are absent because inventing them for a real "
                  "person would be the one made-up thing in a true file. Merged into "
                  "trips_enhanced.json by build_trips_enhanced.py.",
    )
    print_summary(trips, report, TRAVELER, CARRIER_PREFERENCE, OUT_PATH, show_report=args.report)


if __name__ == "__main__":
    main()
