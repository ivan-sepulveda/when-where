"""
Derived from: Wikipedia's episode tables for BOTH of Conan O'Brien's
              travel series --
                * Conan Without Borders (TBS, 2015-2019), 13 specials, from
                  a saved PDF of
                  https://en.wikipedia.org/wiki/Conan_Without_Borders
                * Conan O'Brien Must Go (Max, 2024-2025), 7 episodes over
                  2 seasons, from
                  https://en.wikipedia.org/wiki/Conan_O%27Brien_Must_Go
              Without Borders names the destination country and its
              description names the city (Qatar -> Al Udeid Air Base
              outside Doha, Japan -> Tokyo and Hokuei in Tottori). MUST GO
              NAMES ONLY THE COUNTRY -- its episodes are titled "Norway",
              "Argentina", "Spain" and nothing in the article narrows them
              to a city.

Every Must Go row therefore uses THE CAPITAL RULE, which is stated in
full in chef_trips.py: a source that names a country and no city gets
that country's capital. It is why the New Zealand row says Wellington
though Auckland is the gateway, and the Netherlands row says Amsterdam
rather than the seat of government at The Hague. Each such row carries a
note saying the city was derived that way rather than read off the
source.
Requires: data/reference/airports.json, and
          data/processed/multiple/airline_routes_enhanced.csv -- both read
          by chef_trips.py, which does the actual resolution.

Same machinery as build_bourdain_trips.py and build_ramsay_trips.py: one
5-day round trip per episode, departing on the episode's air date, flying
nonstop. Writes data/processed/multiple/conan_trips.csv and .json, with a
`show` column on every row so the two series can be read apart.

    ORIGIN_PREFERENCE = JFK, LGA, EWR   (first one with a nonstop wins)

NEW YORK, NOT LOS ANGELES. Conan taped in Los Angeles across both of
these shows, so LAX would be the biographical choice -- but Ivan asked
for exactly Bourdain's airports and airlines, which makes the two
profiles differ ONLY in where they went. That is the more useful pair for
a recommender: same origin, same carrier rules, 20 episodes against
Bourdain's 246. The declared base city follows the airports rather than
the biography, so the domestic/international split is computed against
the city he departs from.

MUST GO SEASON 1 DROPPED ALL FOUR EPISODES AT ONCE. Max released
Norway, Argentina, Thailand and Ireland on 2024-04-18, so those rows all
start on the same date -- a streaming release pattern, not four journeys
in one day. They are kept anyway, because the alternative is discarding
real destinations over a scheduling artifact, and
build_conan_traveler.py suffixes the repeated trip_ids. Thailand drops
out on the flights-only rule, so three of the four survive.

ONE DATE CORRECTED AGAINST THE SOURCE. The PDF's table cell for "Conan in
Cuba" reads "March 14, 2015", but that is column bleed from a citation
sidebar ("archived ... on March 20, 2015. Retrieved March 17, 2015")
overlapping the date column. The special aired March 4, 2015, which is
what this table records. Every other date is taken from the PDF as-is.

Usage:
    python build_conan_trips.py
    python build_conan_trips.py --include-excluded   # also write excluded rows to the CSV
"""

import argparse

from chef_trips import (  # noqa: E402
    PROCESSED_DIR,
    build_rows,
    print_summary,
    write_outputs,
)

OUT_CSV_PATH = PROCESSED_DIR / "conan_trips.csv"
OUT_JSON_PATH = PROCESSED_DIR / "conan_trips.json"

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Conan_Without_Borders"
MUST_GO_URL = "https://en.wikipedia.org/wiki/Conan_O%27Brien_Must_Go"

# Bourdain's exact airports, per Ivan.
ORIGIN_PREFERENCE = ("JFK", "LGA", "EWR")

TRIP_DAYS = 5

TRAVELER = {
    "traveler_id": "conan",
    "traveler_name": "Conan O'Brien",
    "home_city": "New York City",
    "home_country": "United States",
    "source_series": "Conan Without Borders; Conan O'Brien Must Go",
}

WITHOUT_BORDERS = [
    {"season": 1, "episode": 1, "title": "Conan in Cuba",
     "air_date": "2015-03-04", "city": "Havana", "country": "Cuba",
     "airports": ["HAV"],
     "note": "first American late-night show taped in Cuba since 1959"},
    {"season": 1, "episode": 2, "title": "Conan in Armenia",
     "air_date": "2015-11-17", "city": "Yerevan", "country": "Armenia",
     "airports": ["EVN"],
     "note": "taking his assistant Sona Movsesian to her ancestral homeland"},
    {"season": 1, "episode": 3, "title": "Conan in Qatar",
     "air_date": "2016-01-25", "city": "Doha", "country": "Qatar",
     "airports": ["DOH"],
     "note": "Al Udeid Air Base, outside Doha, with Michelle Obama"},
    {"season": 1, "episode": 4, "title": "Conan Does Korea",
     "air_date": "2016-04-09", "city": "Seoul", "country": "South Korea",
     "airports": ["ICN"],
     "note": "Seoul and the DMZ, briefly crossing into North Korea"},
    {"season": 1, "episode": 5, "title": "Conan in Berlin",
     "air_date": "2016-12-07", "city": "Berlin", "country": "Germany",
     "airports": ["TXL", "BER"],
     "note": "Tegel was Berlin's gateway in 2016; BER replaced it in 2020, "
             "and airports.json (OpenFlights) predates BER"},
    {"season": 1, "episode": 6, "title": "Conan Without Borders: Made in Mexico",
     "air_date": "2017-03-01", "city": "Mexico City", "country": "Mexico",
     "airports": ["MEX"]},
    {"season": 1, "episode": 7, "title": "Conan Without Borders: Israel",
     "air_date": "2017-09-19", "city": "Tel Aviv", "country": "Israel",
     "airports": ["TLV"],
     "note": "Israel and, across the wall, the West Bank"},
    {"season": 1, "episode": 8, "title": "Conan Without Borders: Haiti",
     "air_date": "2018-01-27", "city": "Port-au-Prince", "country": "Haiti",
     "airports": ["PAP"]},
    {"season": 1, "episode": 9, "title": "Conan in Italy",
     "air_date": "2018-04-11", "city": "Rome", "country": "Italy",
     "airports": ["FCO"],
     "note": "with producer Jordan Schlansky"},
    {"season": 1, "episode": 10, "title": "Conan in Japan",
     "air_date": "2018-11-28", "city": "Tokyo", "country": "Japan",
     "airports": ["NRT", "HND"],
     "note": "Tokyo and Hokuei in Tottori, the town named for Conan Edogawa"},
    {"season": 1, "episode": 11, "title": "Conan Without Borders: Australia",
     "air_date": "2019-04-17", "city": "Sydney", "country": "Australia",
     "airports": ["SYD", "MEL"],
     "note": "made after a video challenge from Hugh Jackman"},
    {"season": 1, "episode": 12, "title": "Conan Without Borders: Greenland",
     "air_date": "2019-09-03", "city": "Nuuk", "country": "Greenland",
     "airports": ["GOH", "SFJ", "CPH"],
     "note": "Greenland is reached from Copenhagen -- Air Greenland's own "
             "long-haul route, and the reason the Danish capital is a candidate"},
    {"season": 1, "episode": 13, "title": "Conan Without Borders: Ghana",
     "air_date": "2019-11-07", "city": "Accra", "country": "Ghana",
     "airports": ["ACC"],
     "note": "visiting during Ghana's Year of Return"},
]

MUST_GO = [
    # ---- Season 1 (2024) -- all four released the same day on Max ----
    {"season": 1, "episode": 1, "title": "Norway",
     "air_date": "2024-04-18", "city": "Oslo", "country": "Norway",
     "airports": ["OSL", "BGO"],
     "note": "the article names only the country, so the row is the capital"},
    {"season": 1, "episode": 2, "title": "Argentina",
     "air_date": "2024-04-18", "city": "Buenos Aires", "country": "Argentina",
     "airports": ["EZE", "AEP"],
     "note": "the article names only the country, so the row is the capital"},
    {"season": 1, "episode": 3, "title": "Thailand",
     "air_date": "2024-04-18", "city": "Bangkok", "country": "Thailand",
     "airports": ["BKK", "CNX"],
     "note": "the article names only the country, so the row is the capital"},
    {"season": 1, "episode": 4, "title": "Ireland",
     "air_date": "2024-04-18", "city": "Dublin", "country": "Ireland",
     "airports": ["DUB", "SNN"],
     "note": "tracing his family's roots; Shannon checked as the western gateway"},

    # ---- Season 2 (2025) ----
    {"season": 2, "episode": 1, "title": "Spain",
     "air_date": "2025-05-08", "city": "Madrid", "country": "Spain",
     "airports": ["MAD", "BCN"],
     "note": "the article names only the country, so the row is the capital"},
    {"season": 2, "episode": 2, "title": "New Zealand",
     "air_date": "2025-05-15", "city": "Wellington", "country": "New Zealand",
     "airports": ["WLG", "AKL"],
     "note": "the article names only the country, so the row is the capital -- Wellington, "
             "not Auckland, with Auckland checked as the country's gateway"},
    {"season": 2, "episode": 3, "title": "Austria",
     "air_date": "2025-05-22", "city": "Vienna", "country": "Austria",
     "airports": ["VIE"],
     "note": "the article names only the country, so the row is the capital"},

    # ---- Season 3 (2026) -- announced, not yet aired ----
    {"season": 3, "episode": 2, "title": "The Netherlands",
     "air_date": "2026-08-28", "city": "Amsterdam", "country": "Netherlands",
     "airports": ["AMS"],
     "note": "announced but not yet aired; the article names only the country, "
             "so the row is the capital -- Amsterdam, not the seat of government at The Hague"},
]

# Without Borders ran as occasional specials rather than seasons, so
# Wikipedia numbers them 1-13 straight through and this table calls that
# season 1. Must Go has real seasons. The show code prefixes episode_code,
# because "S1.E1" alone is ambiguous once there are two series in the file.
EPISODES = (
    [{**ep, "show": "Without Borders", "show_code": "CWB"} for ep in WITHOUT_BORDERS]
    + [{**ep, "show": "Must Go", "show_code": "CMG"} for ep in MUST_GO]
)


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
        "source": f"Wikipedia episode tables for Conan Without Borders (TBS, 2015-2019) -- "
                  f"{WIKIPEDIA_URL} -- and Conan O'Brien Must Go (Max, 2024-2025) -- "
                  f"{MUST_GO_URL}",
        "traveler": TRAVELER,
        "assumptions": {
            "start_date": "episode original release date (the only date the source publishes; "
                          "filming predates it)",
            "duration_days": TRIP_DAYS,
            "trip_shape": "round trip out of New York, nonstop each way",
            "origin_preference": list(ORIGIN_PREFERENCE),
            "flights_only": "an episode is kept only if a nonstop from JFK, LGA or EWR to the "
                            "destination airport exists in airline_routes_enhanced.csv",
            "route_data_vintage": "airline_routes_enhanced.csv is a present-day route snapshot, "
                                  "not a 2015-2025 schedule -- exclusions mean 'no nonstop today'",
            "must_go_cities": "Conan O'Brien Must Go episodes are titled by COUNTRY only, so "
                              "their city is that country's CAPITAL rather than a place the "
                              "source names -- see the capital rule in this script's docstring",
            "unaired_episodes": "the Must Go season 3 Netherlands episode is scheduled for "
                                "2026-08-28 and has not aired; its trip is dated from the "
                                "announced date like any other",
            "home_airports": "New York rather than Los Angeles, where the show actually taped -- "
                             "deliberately matched to Bourdain's so the two profiles differ only "
                             "in destination",
        },
    }
    write_outputs(OUT_CSV_PATH, OUT_JSON_PATH, trips, excluded, EPISODES, meta,
                  include_excluded=args.include_excluded)
    print_summary(trips, excluded, EPISODES, OUT_CSV_PATH, OUT_JSON_PATH)


if __name__ == "__main__":
    main()
