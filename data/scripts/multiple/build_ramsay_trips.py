"""
Derived from: Wikipedia's episode table for "Gordon Ramsay: Uncharted"
              (National Geographic, 2019-2024) -- 29 episodes over 4
              seasons, transcribed by hand from a saved PDF of
              https://en.wikipedia.org/wiki/Gordon_Ramsay:_Uncharted
              Each episode's synopsis names the region precisely enough to
              pick an airport: "India's Spice Hub" says Kannur in Kerala,
              "The Wilds of South Africa" says KwaZulu-Natal, "Michigan's
              Yooper Cuisine" says the Upper Peninsula.
Requires: data/reference/airports.json, and
          data/processed/multiple/airline_routes_enhanced.csv -- both read
          by chef_trips.py, which does the actual resolution.

Same idea as build_bourdain_trips.py, different chef and different home
airport: one 5-day round trip per episode, departing on the episode's air
date, flying nonstop out of Los Angeles. Writes
data/processed/multiple/ramsay_trips.csv and .json.

    ORIGIN_PREFERENCE = LAX, LAS   (first one with a nonstop wins)

Las Vegas is the fallback, not a second home: it only becomes the origin
when LAX has no nonstop to the destination at all. In the current route
data that happens exactly once, for Knoxville.

WHY SO MANY EPISODES DROP OUT. Uncharted is built on the premise of going
somewhere hard to reach -- the Sacred Valley, Tasmania, the Guyanese
Amazon, Lapland -- and 15 of the 29 episodes have no nonstop from Los
Angeles to anywhere near them. That is a fact about the show rather than
a gap in the data, and it is why this profile is small and long-haul
where Bourdain's is large and varied. Every dropped episode keeps its
reason in the JSON's `excluded_episodes`.

SEASON 4 DOUBLE-BILLED ITS PREMIERE. "Unlocking Florida's Keys" and
"The Cliffs of Ireland" both aired on 2024-05-27, so both trips start on
the same date. Both are kept -- they are two real episodes about two real
places -- and build_ramsay_traveler.py disambiguates the trip_id rather
than dropping one, since trip_id is otherwise prefix + start date.

REGIONS RESOLVE TO THEIR GATEWAY. Most Uncharted episodes are about a
region rather than a city, so `airports` lists the local airport first and
the gateway you would actually fly into after it: Queenstown before
Auckland for the South Island, Hobart before Melbourne for Tasmania,
Rovaniemi before Helsinki for Lapland. When the local airport has no
nonstop, the row records the gateway and a note says so -- see
chef_trips.build_rows(). Where even the gateway is a stretch (Michigan's
Upper Peninsula is not meaningfully "Detroit"), the episode is dropped
instead.

Usage:
    python build_ramsay_trips.py
    python build_ramsay_trips.py --include-excluded   # also write excluded rows to the CSV
"""

import argparse

from chef_trips import (  # noqa: E402
    NO_NONSTOP,
    PROCESSED_DIR,
    build_rows,
    print_summary,
    write_outputs,
)

OUT_CSV_PATH = PROCESSED_DIR / "ramsay_trips.csv"
OUT_JSON_PATH = PROCESSED_DIR / "ramsay_trips.json"

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Gordon_Ramsay:_Uncharted"

# Los Angeles first, Las Vegas only when LAX can't get there nonstop.
ORIGIN_PREFERENCE = ("LAX", "LAS")

TRIP_DAYS = 5

TRAVELER = {
    "traveler_id": "ramsay",
    "traveler_name": "Gordon Ramsay",
    "home_city": "Los Angeles",
    "home_country": "United States",
    "source_series": "Gordon Ramsay: Uncharted",
}

UNCHARTED = [
    # ---- Season 1 (2019) ----
    {"season": 1, "episode": 1, "title": "Peru's Sacred Valley",
     "air_date": "2019-07-21", "city": "Cusco", "country": "Peru",
     "airports": ["CUZ", "LIM"],
     "note": "the Sacred Valley of the Incas, above Cusco"},
    {"season": 1, "episode": 2, "title": "New Zealand's Rugged South",
     "air_date": "2019-07-28", "city": "Queenstown", "country": "New Zealand",
     "airports": ["ZQN", "CHC", "AKL"],
     "note": "South Island and Stewart Island"},
    {"season": 1, "episode": 3, "title": "The Mountains of Morocco",
     "air_date": "2019-08-04", "city": "Marrakesh", "country": "Morocco",
     "airports": ["RAK", "CMN"],
     "note": "the Atlas Mountains, reached from Marrakesh"},
    {"season": 1, "episode": 4, "title": "Hawaii's Hana Coast",
     "air_date": "2019-08-11", "city": "Kahului", "country": "United States",
     "airports": ["OGG"],
     "note": "the Hana coast of Maui"},
    {"season": 1, "episode": 5, "title": "The Mighty Mekong of Laos",
     "air_date": "2019-08-18", "city": "Luang Prabang", "country": "Laos",
     "airports": ["LPQ", "VTE"]},
    {"season": 1, "episode": 6, "title": "Alaska's Panhandle",
     "air_date": "2019-08-25", "city": "Juneau", "country": "United States",
     "airports": ["JNU", "SIT", "ANC"],
     "note": "southeast Alaska; Anchorage is the state's long-haul gateway, 1,000km north"},

    # ---- Season 2 (2020) ----
    {"season": 2, "episode": 1, "title": "Untamed Tasmania",
     "air_date": "2020-06-07", "city": "Hobart", "country": "Australia",
     "airports": ["HBA", "LST", "MEL"],
     "note": "Melbourne is the mainland gateway to Tasmania"},
    {"season": 2, "episode": 2, "title": "The Wilds of South Africa",
     "air_date": "2020-06-14", "city": "Durban", "country": "South Africa",
     "airports": ["DUR", "JNB"],
     "note": "KwaZulu-Natal, with a Durban market"},
    {"season": 2, "episode": 3, "title": "Louisiana's Bayou Cuisine",
     "air_date": "2020-06-21", "city": "New Orleans", "country": "United States",
     "airports": ["MSY"],
     "note": "southern Louisiana and the Chandeleur Islands"},
    {"season": 2, "episode": 4, "title": "Sumatra's Stunning Highlands",
     "air_date": "2020-06-28", "city": "Padang", "country": "Indonesia",
     "airports": ["PDG", "CGK"],
     "note": "West Sumatra"},
    {"season": 2, "episode": 5, "title": "Guyana's Wild Jungles",
     "air_date": "2020-07-05", "city": "Georgetown", "country": "Guyana",
     "airports": ["GEO"]},
    {"season": 2, "episode": 6, "title": "India's Spice Hub",
     "air_date": "2020-07-12", "city": "Kannur", "country": "India",
     "airports": ["CNN", "CCJ", "COK"],
     "note": "Kannur in Kerala, then inland to Coorg"},
    {"season": 2, "episode": 7, "title": "Norway's Viking Country",
     "air_date": "2020-07-19", "city": "Bergen", "country": "Norway",
     "airports": ["BGO", "OSL"],
     "note": "the west coast, then inland to Roros"},

    # ---- Season 3 (2021) ----
    {"season": 3, "episode": 1, "title": "Texas Throwdown",
     "air_date": "2021-05-31", "city": "San Antonio", "country": "United States",
     "airports": ["SAT", "AUS"],
     "note": "south-central Texas"},
    {"season": 3, "episode": 2, "title": "Portugal's Rugged Coast",
     "air_date": "2021-06-06", "city": "Lisbon", "country": "Portugal",
     "airports": ["LIS", "OPO"],
     "note": "the Atlantic coast"},
    {"season": 3, "episode": 3, "title": "The Maine Ingredient",
     "air_date": "2021-06-13", "city": "Portland", "country": "United States",
     "airports": ["PWM"],
     "note": "the Maine shoreline"},
    {"season": 3, "episode": 4, "title": "Croatia's Coastal Adventure",
     "air_date": "2021-06-20", "city": "Pula", "country": "Croatia",
     "airports": ["PUY", "ZAG"],
     "note": "the Istrian peninsula"},
    {"season": 3, "episode": 5, "title": "Lush and Wild Puerto Rico",
     "air_date": "2021-06-27", "city": "San Juan", "country": "Puerto Rico",
     "airports": ["SJU"],
     "note": "Culebra, Utuado and the Tanama river"},
    {"season": 3, "episode": 6, "title": "The Great Smoky Mountains",
     "air_date": "2021-07-04", "city": "Knoxville", "country": "United States",
     "airports": ["TYS", "AVL"],
     "note": "Knoxville is the Tennessee-side gateway to the Smokies"},
    {"season": 3, "episode": 7, "title": "Incredible Iceland",
     "air_date": "2021-07-11", "city": "Reykjavik", "country": "Iceland",
     "airports": ["KEF"],
     "note": "Iceland's west coast"},
    {"season": 3, "episode": 8, "title": "Holy Mole Mexico",
     "air_date": "2021-07-18", "city": "Oaxaca", "country": "Mexico",
     "airports": ["OAX", "MEX"]},
    {"season": 3, "episode": 9, "title": "Michigan's Yooper Cuisine",
     "air_date": "2021-07-25", "city": "Marquette", "country": "United States",
     "airports": ["MQT", "CIU"],
     "note": "Michigan's Upper Peninsula -- Detroit is deliberately not a candidate, "
             "it is a different peninsula 700km away"},
    {"season": 3, "episode": 10, "title": "Finland's Midnight Sun",
     "air_date": "2021-08-01", "city": "Rovaniemi", "country": "Finland",
     "airports": ["RVN", "HEL"],
     "note": "Lapland, in the far north"},

    # ---- Season 4 (2024) ----
    {"season": 4, "episode": 1, "title": "Unlocking Florida's Keys",
     "air_date": "2024-05-27", "city": "Key West", "country": "United States",
     "airports": ["EYW", "MIA"],
     "note": "Miami is the mainland gateway to the Keys"},
    {"season": 4, "episode": 2, "title": "The Cliffs of Ireland",
     "air_date": "2024-05-27", "city": "Shannon", "country": "Ireland",
     "airports": ["SNN", "DUB"],
     "note": "the west coast cliffs, nearest to Shannon"},
    {"season": 4, "episode": 3, "title": "Spain's Galician Coast",
     "air_date": "2024-06-02", "city": "Santiago de Compostela", "country": "Spain",
     "airports": ["SCQ", "LCG", "MAD"]},
    {"season": 4, "episode": 4, "title": "Big Island Ono",
     "air_date": "2024-06-09", "city": "Kailua-Kona", "country": "United States",
     "airports": ["KOA", "ITO"],
     "note": "the island of Hawaii"},
    {"season": 4, "episode": 5, "title": "Cuba's Savory Secrets",
     "air_date": "2024-06-16", "city": "Havana", "country": "Cuba",
     "airports": ["HAV"]},
    {"season": 4, "episode": 6, "title": "A Royal Taste of Jordan",
     "air_date": "2024-06-23", "city": "Amman", "country": "Jordan",
     "airports": ["AMM"]},
]

EPISODES = [{**ep, "show": "Uncharted", "show_code": "GRU"} for ep in UNCHARTED]


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
        "source": f"Wikipedia episode table for Gordon Ramsay: Uncharted "
                  f"(National Geographic, 2019-2024), seasons 1-4 -- {WIKIPEDIA_URL}",
        "traveler": TRAVELER,
        "assumptions": {
            "start_date": "episode original release date (the only date the source publishes; "
                          "filming predates it)",
            "duration_days": TRIP_DAYS,
            "trip_shape": "round trip out of Los Angeles, nonstop each way",
            "origin_preference": list(ORIGIN_PREFERENCE),
            "flights_only": "an episode is kept only if a nonstop from LAX or LAS to the "
                            "destination airport exists in airline_routes_enhanced.csv",
            "route_data_vintage": "airline_routes_enhanced.csv is a present-day route snapshot, "
                                  "not a 2019-2024 schedule -- exclusions mean 'no nonstop today'",
        },
    }
    write_outputs(OUT_CSV_PATH, OUT_JSON_PATH, trips, excluded, EPISODES, meta,
                  include_excluded=args.include_excluded)
    print_summary(trips, excluded, EPISODES, OUT_CSV_PATH, OUT_JSON_PATH)


if __name__ == "__main__":
    main()
