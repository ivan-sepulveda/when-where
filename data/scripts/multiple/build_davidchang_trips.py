"""
Derived from: Wikipedia's episode list for Breakfast, Lunch & Dinner --
              https://en.wikipedia.org/wiki/Breakfast,_Lunch_%26_Dinner
              David Chang's 2019 Netflix series: one season, 4 episodes,
              all released the same day (2019-10-23) rather than a weekly
              schedule -- each episode drops David Chang into a city with
              one celebrity guest to eat.

Same machinery as build_bourdain_trips.py / build_ramsay_trips.py /
build_conan_trips.py / build_ricksteves_trips.py: one 5-day round trip per
episode, departing on the episode's air date, flying nonstop. Writes
data/processed/multiple/davidchang_trips.csv and .json.

ALL FOUR EPISODES SHARE ONE AIR DATE. Netflix released the whole season at
once, not weekly, so every surviving trip starts 2019-10-23 --
chef_traveler.build_trips() already handles a repeated start date by
suffixing the trip_id (`DC-2019-10-23`, `-2`, `-3`), same as Conan's Must Go
season-1 quadruple release and Rick Steves' same-day Istanbul two-parter.

VANCOUVER IS NOT DAVID CHANG'S HOME TURF -- it's Seth Rogen's (the episode
is framed as Rogen's homecoming), and Chang is based out of New York per
Ivan's instruction below. So this is an ordinary destination episode, not a
GROUND exclusion, even though the show's own premise calls it a "hometown"
trip -- it's the guest's hometown, not the traveler's.

ONE OF FOUR EPISODES EXCLUDES ON THE FLIGHTS-ONLY RULE: Phnom Penh,
Cambodia has no nonstop from any New York airport in
airline_routes_enhanced.csv (checked both PNH itself and Siem Reap/REP,
Cambodia's other international gateway -- neither has one), which matches
reality: nobody flies JFK/EWR to Cambodia nonstop. Marrakech survives only
via substitution -- Marrakech's own airport (RAK) has no New York nonstop
either, but Casablanca (CMN) does (Royal Air Maroc's JFK route), so that
episode resolves to Casablanca the same way several Rick Steves regional
episodes resolve to a country's one real gateway (see chef_trips.py's
substitution mechanism).

Requires: data/reference/airports.json, and
          data/processed/multiple/airline_routes_enhanced.csv -- both read
          by chef_trips.py, which does the actual resolution.

Usage:
    python build_davidchang_trips.py
    python build_davidchang_trips.py --include-excluded   # also write excluded rows to the CSV
"""

import argparse

from chef_trips import (  # noqa: E402
    PROCESSED_DIR,
    build_rows,
    print_summary,
    write_outputs,
)

OUT_CSV_PATH = PROCESSED_DIR / "davidchang_trips.csv"
OUT_JSON_PATH = PROCESSED_DIR / "davidchang_trips.json"

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Breakfast,_Lunch_%26_Dinner"

# Bourdain's exact airports, per Ivan ("same rules as Anthony Bourdain in
# terms of airline/airport preferences").
ORIGIN_PREFERENCE = ("JFK", "LGA", "EWR")

TRIP_DAYS = 5

TRAVELER = {
    "traveler_id": "david-chang",
    "traveler_name": "David Chang",
    "home_city": "New York City",
    "home_country": "United States",
    "source_series": "Breakfast, Lunch & Dinner",
}

SHOW = "Breakfast, Lunch & Dinner"
SHOW_CODE = "BLD"

EPISODES_RAW = [
    {"season": 1, "episode": 1, "title": "Vancouver with Seth Rogen",
     "air_date": "2019-10-23", "city": "Vancouver", "country": "Canada",
     "airports": ["YVR"],
     "note": "guest: Seth Rogen -- framed as Rogen's own hometown, not David Chang's; "
             "Chang is based out of New York per Ivan's instruction"},
    {"season": 1, "episode": 2, "title": "Marrakech with Chrissy Teigen",
     "air_date": "2019-10-23", "city": "Marrakech", "country": "Morocco",
     "airports": ["RAK", "CMN"],
     "note": "guest: Chrissy Teigen"},
    {"season": 1, "episode": 3, "title": "Los Angeles with Lena Waithe",
     "air_date": "2019-10-23", "city": "Los Angeles", "country": "United States",
     "airports": ["LAX"],
     "note": "guest: Lena Waithe"},
    {"season": 1, "episode": 4, "title": "Phnom Penh with Kate McKinnon",
     "air_date": "2019-10-23", "city": "Phnom Penh", "country": "Cambodia",
     "airports": ["PNH", "REP"],
     "note": "guest: Kate McKinnon"},
]

EPISODES = [{**ep, "show": SHOW, "show_code": SHOW_CODE} for ep in EPISODES_RAW]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-excluded",
        action="store_true",
        help="also write the excluded episodes to the CSV (blank flight columns, reason in notes)",
    )
    args = parser.parse_args()

    trips, excluded = build_rows(EPISODES, ORIGIN_PREFERENCE, TRAVELER["traveler_name"], TRIP_DAYS)

    meta = {
        "source": f"Wikipedia episode list for Breakfast, Lunch & Dinner (Netflix, 2019) -- "
                  f"{WIKIPEDIA_URL}",
        "traveler": TRAVELER,
        "assumptions": {
            "start_date": "episode original release date -- all four episodes released the "
                          "same day (2019-10-23), a Netflix same-day drop, not four journeys "
                          "on one date",
            "duration_days": TRIP_DAYS,
            "trip_shape": "round trip out of New York, nonstop each way",
            "origin_preference": list(ORIGIN_PREFERENCE),
            "flights_only": "an episode is kept only if a nonstop from JFK, LGA or EWR to the "
                            "destination airport exists in airline_routes_enhanced.csv",
            "route_data_vintage": "airline_routes_enhanced.csv is a present-day route snapshot, "
                                  "not a 2019 schedule -- exclusions mean 'no nonstop today'",
            "home_airports": "New York, per Ivan's instruction to use exactly Anthony Bourdain's "
                             "airport and airline preferences",
        },
    }
    write_outputs(OUT_CSV_PATH, OUT_JSON_PATH, trips, excluded, EPISODES, meta,
                  include_excluded=args.include_excluded)
    print_summary(trips, excluded, EPISODES, OUT_CSV_PATH, OUT_JSON_PATH)


if __name__ == "__main__":
    main()
