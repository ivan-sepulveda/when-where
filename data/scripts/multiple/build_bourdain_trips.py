"""
Derived from: the published episode lists for BOTH of Anthony Bourdain's
              travel series, transcribed by hand from saved PDFs --
                * No Reservations (Travel Channel, 2005-2012), 42 episodes
                  over 9 seasons, from IMDb tt0475900
                  (https://www.imdb.com/title/tt0475900/episodes/?season=1
                  through &season=9)
                * Parts Unknown (CNN, 2013-2018), 103 episodes over 12
                  seasons, from Wikipedia's "Anthony Bourdain: Parts
                  Unknown" episode table
              The destination city/country and the candidate airports for
              each episode come from the episode title plus that source's
              own synopsis (No Reservations S1.E8 "Uzbekistan" -> Tashkent,
              because the synopsis names the capital; Parts Unknown
              "Southern Italy" -> Apulia, so Bari before Rome).
Requires: data/reference/airports.json (IATA -> name/city/country/coords),
          data/processed/multiple/airline_routes_enhanced.csv (built by
          build_airline_routes_enhanced.py -- which airports are actually
          connected by a nonstop, and how far apart they are)

Turns each episode of either show into one "trip opportunity" row: a
5-day round trip out of New York, departing on the episode's air date,
flying nonstop to the airport that serves the place Bourdain visited.
Writes data/processed/multiple/bourdain_trips.csv and .json, with a
`show` column on every row so the two series can be read apart.

WHAT THIS IS AND IS NOT
-----------------------
This is a *synthetic* travel history in the shape of the show, not a
record of Bourdain's actual flights. The air date is used as the trip
start date because it is the only date IMDb publishes -- shooting
happened weeks or months earlier. The 5-day duration is a modeling
assumption, uniform across every episode. Treat the output as a
plausible traveler profile for the recommender, not as biography.

FLIGHTS ONLY
------------
Every row must be a real nonstop that exists in
airline_routes_enhanced.csv from one of the three New York airports:

    ORIGIN_PREFERENCE = JFK, LGA, EWR   (first one with a nonstop wins)

JFK and LGA are preferred over EWR, so a destination served from both
JFK and EWR (BCN, for example) is recorded as a JFK trip and EWR is only
listed as an alternate. EWR is used when it is the only New York airport
with the nonstop.

An episode is EXCLUDED when no such nonstop exists, or when there was no
flight to begin with:

  * ground_trip -- home turf or driven: New Jersey (twice, one per show),
    the Bronx, Queens, Brooklyn, the Lower East Side, the Hudson Valley,
    the Connecticut holiday special, the US/Mexico border, the Les Halles
    kitchen episode
  * compilation -- clip shows and studio specials: "Leftovers 1" and "2",
    "Food Porn" 1 and 2, the holiday specials, all eight Parts Unknown
    "Prime Cuts" season openers, and the two posthumous specials
    ("Tony's Impact", "Under the Tarp")
  * no_single_destination -- regional travelogues with no one gateway:
    "U.S. Southwest", "U.S. Heartland", "Caribbean Island Hopping",
    "Off the Charts"
  * no_nyc_nonstop -- nowhere to fly nonstop from New York. Roughly half
    the Parts Unknown catalogue falls here, which is the point of the
    show: Myanmar, Libya, Congo, Madagascar, Tanzania, Iran, Bhutan,
    Armenia, Oman, Borneo, Sichuan, Okinawa, the Punjab, Paraguay,
    Asuncion, Tbilisi, Cologne, Antarctica (no scheduled service at all),
    alongside the No Reservations list -- Tashkent, Christchurch, Jaipur,
    Jakarta, Beirut, Windhoek, Papeete, Florence and the rest.

Excluded episodes are not silently dropped: every one of them is kept in
the EPISODES tables below with an `exclude` reason, echoed into the JSON
output's "excluded_episodes" list, and printed in the run summary. The
route data is a present-day snapshot, so an exclusion means "no nonstop
in the data we have", not "unreachable in 2005".

Multi-city and region episodes resolve to the first candidate airport
with a New York nonstop, and the destination columns then follow that
airport: S2.E10 "India: Kolkata/Bombay" becomes Mumbai because CCU has no
nonstop, "Greek Islands" becomes Athens, "Ecuador" becomes Guayaquil.
The episode's own subject stays in the episode_destination column and a
note records the substitution.

Usage:
    python build_bourdain_trips.py
    python build_bourdain_trips.py --include-excluded   # also write excluded rows to the CSV
"""

import argparse
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
REFERENCE_DIR = DATA_DIR / "reference"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"

AIRPORTS_PATH = REFERENCE_DIR / "airports.json"
ROUTES_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"
OUT_CSV_PATH = PROCESSED_DIR / "bourdain_trips.csv"
OUT_JSON_PATH = PROCESSED_DIR / "bourdain_trips.json"

IMDB_URL = "https://www.imdb.com/title/tt0475900/episodes/"
PARTS_UNKNOWN_URL = "https://en.wikipedia.org/wiki/Anthony_Bourdain:_Parts_Unknown"

# New York airports in preference order. The first one with a nonstop to
# the destination becomes the trip's origin; the rest are recorded as
# alternates so a later model can see the trip was flyable more than one
# way.
ORIGIN_PREFERENCE = ("JFK", "LGA", "EWR")

# Every trip is a 5-day round trip departing on the air date, so the
# return leg is start + 5 days (matching the duration convention in
# data/processed/multiple/traveler_trips.csv, where duration is end minus
# start in days).
TRIP_DAYS = 5

TRAVELER = {
    "traveler_id": "bourdain",
    "traveler_name": "Anthony Bourdain",
    "home_city": "New York City",
    "home_country": "United States",
    "source_series": "Anthony Bourdain: No Reservations",
}

# Exclusion reason codes -- see the module docstring.
GROUND = "ground_trip"          # home turf or driven, no flight involved
COMPILATION = "compilation"     # clip show, not a new journey
AMBIGUOUS = "no_single_destination"  # a region or several countries, no one gateway
NO_NONSTOP = "no_nyc_nonstop"   # no nonstop from JFK/LGA/EWR in the route data

# season, episode, title and air_date transcribed from the IMDb episode
# list PDFs. `airports` is the ordered list of candidate destination
# airports for the place the episode is about -- ordered by how well the
# airport serves that place, NOT by which New York airport flies there.
NO_RESERVATIONS = [
    # ---- Season 1 (2005-2006) ----
    {"season": 1, "episode": 1, "title": "France: Why the French Don't Suck",
     "air_date": "2005-07-25", "city": "Paris", "country": "France",
     "airports": ["CDG", "ORY"]},
    {"season": 1, "episode": 2, "title": "Iceland: Hello Darkness My Old Friend",
     "air_date": "2005-08-01", "city": "Reykjavik", "country": "Iceland",
     "airports": ["KEF"]},
    {"season": 1, "episode": 3, "title": "New Jersey",
     "air_date": "2005-08-08", "city": "Newark", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "Bourdain's home state, reached by car from New York"},
    {"season": 1, "episode": 4, "title": "Vietnam: The Island of Mr. Sang",
     "air_date": "2005-08-15", "city": "Hanoi", "country": "Vietnam",
     "airports": ["HAN"]},
    {"season": 1, "episode": 5, "title": "Malaysia: Into the Jungle",
     "air_date": "2005-08-22", "city": "Kuala Lumpur", "country": "Malaysia",
     "airports": ["KUL"]},
    {"season": 1, "episode": 6, "title": "Sicily",
     "air_date": "2005-10-10", "city": "Palermo", "country": "Italy",
     "airports": ["PMO", "CTA"],
     "note": "Il Capo market places the episode in Palermo; Catania checked as the other Sicilian gateway"},
    {"season": 1, "episode": 7, "title": "Las Vegas",
     "air_date": "2005-10-17", "city": "Las Vegas", "country": "United States",
     "airports": ["LAS"]},
    {"season": 1, "episode": 8, "title": "Uzbekistan",
     "air_date": "2005-10-24", "city": "Tashkent", "country": "Uzbekistan",
     "airports": ["TAS"]},
    {"season": 1, "episode": 9, "title": "New Zealand: Down Under the Down Under",
     "air_date": "2005-11-07", "city": "Christchurch", "country": "New Zealand",
     "airports": ["CHC"]},
    {"season": 1, "episode": 10, "title": "Iceland Special Edition",
     "air_date": "2006-06-20", "city": "Reykjavik", "country": "Iceland",
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "special re-cut of earlier footage, not a new journey"},

    # ---- Season 2 (2006) ----
    {"season": 2, "episode": 0, "title": "Leftovers 1",
     "air_date": "2006-03-27", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of unused footage, no destination"},
    {"season": 2, "episode": 1, "title": "Asia Special: China & Japan",
     "air_date": "2006-03-27", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "revisits Philippines/Malaysia/Thailand/Japan footage from earlier episodes"},
    {"season": 2, "episode": 2, "title": "South Florida",
     "air_date": "2006-04-03", "city": "Miami", "country": "United States",
     "airports": ["MIA", "FLL"]},
    {"season": 2, "episode": 3, "title": "Peru",
     "air_date": "2006-04-10", "city": "Lima", "country": "Peru",
     "airports": ["LIM"]},
    {"season": 2, "episode": 4, "title": "Canada",
     "air_date": "2006-04-17", "city": "Montreal", "country": "Canada",
     "airports": ["YUL"],
     "note": "synopsis names the Montreal Culinary Institute"},
    {"season": 2, "episode": 5, "title": "Sweden",
     "air_date": "2006-04-24", "city": "Stockholm", "country": "Sweden",
     "airports": ["ARN"]},
    {"season": 2, "episode": 6, "title": "Puerto Rico",
     "air_date": "2006-05-01", "city": "San Juan", "country": "Puerto Rico",
     "airports": ["SJU"]},
    {"season": 2, "episode": 7, "title": "Japan",
     "air_date": "2006-05-08", "city": "Osaka", "country": "Japan",
     "airports": ["KIX", "ITM"],
     "note": "synopsis begins the episode in Osaka, not Tokyo"},
    {"season": 2, "episode": 8, "title": "US/Mexico Border",
     "air_date": "2006-05-22", "city": "Piedras Negras", "country": "Mexico",
     "airports": [], "exclude": GROUND,
     "exclude_note": "Texas border towns and a border crossing by road, no destination airport"},
    {"season": 2, "episode": 9, "title": "India: Rajasthan",
     "air_date": "2006-05-29", "city": "Jaipur", "country": "India",
     "airports": ["JAI"]},
    {"season": 2, "episode": 10, "title": "India: Kolkata/Bombay",
     "air_date": "2006-06-05", "city": "Kolkata", "country": "India",
     "airports": ["CCU", "BOM"],
     "note": "two-city episode, Kolkata and Bombay"},
    {"season": 2, "episode": 11, "title": "Korea",
     "air_date": "2006-06-12", "city": "Seoul", "country": "South Korea",
     "airports": ["ICN"]},
    {"season": 2, "episode": 12, "title": "Indonesia",
     "air_date": "2006-06-19", "city": "Jakarta", "country": "Indonesia",
     "airports": ["CGK", "DPS"]},
    {"season": 2, "episode": 13, "title": "Special: Decoding Ferran Adria",
     "air_date": "2006-07-03", "city": "Barcelona", "country": "Spain",
     "airports": ["BCN"],
     "note": "elBulli is in Roses, Catalonia -- Barcelona is its gateway airport"},
    {"season": 2, "episode": 14, "title": "Beirut",
     "air_date": "2006-08-21", "city": "Beirut", "country": "Lebanon",
     "airports": ["BEY"]},

    # ---- Season 3 (2007) ----
    {"season": 3, "episode": 0, "title": "Leftovers 2",
     "air_date": "2007-01-01", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of unused footage, no destination"},
    {"season": 3, "episode": 1, "title": "Ireland",
     "air_date": "2007-01-01", "city": "Dublin", "country": "Ireland",
     "airports": ["DUB"]},
    {"season": 3, "episode": 2, "title": "Ghana",
     "air_date": "2007-01-08", "city": "Accra", "country": "Ghana",
     "airports": ["ACC"]},
    {"season": 3, "episode": 3, "title": "Pacific NW",
     "air_date": "2007-01-15", "city": "Seattle", "country": "United States",
     "airports": ["SEA", "PDX"],
     "note": "episode covers Washington and Oregon; Seattle is the primary gateway"},
    {"season": 3, "episode": 4, "title": "Namibia",
     "air_date": "2007-01-22", "city": "Windhoek", "country": "Namibia",
     "airports": ["WDH"]},
    {"season": 3, "episode": 5, "title": "Russia",
     "air_date": "2007-01-29", "city": "Moscow", "country": "Russia",
     "airports": ["SVO", "DME"]},
    {"season": 3, "episode": 6, "title": "Los Angeles",
     "air_date": "2007-02-05", "city": "Los Angeles", "country": "United States",
     "airports": ["LAX"]},
    {"season": 3, "episode": 7, "title": "Shanghai",
     "air_date": "2007-07-30", "city": "Shanghai", "country": "China",
     "airports": ["PVG"]},
    {"season": 3, "episode": 8, "title": "New York City",
     "air_date": "2007-08-06", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "Bourdain's home city -- the trip's origin, not a destination"},
    {"season": 3, "episode": 9, "title": "Brazil",
     "air_date": "2007-08-13", "city": "Sao Paulo", "country": "Brazil",
     "airports": ["GRU"],
     "note": "synopsis is about Sao Paulo, not Rio"},
    {"season": 3, "episode": 10, "title": "French Polynesia",
     "air_date": "2007-08-20", "city": "Papeete", "country": "French Polynesia",
     "airports": ["PPT"]},
    {"season": 3, "episode": 11, "title": "Cleveland",
     "air_date": "2007-08-27", "city": "Cleveland", "country": "United States",
     "airports": ["CLE"]},
    {"season": 3, "episode": 12, "title": "Hong Kong",
     "air_date": "2007-09-03", "city": "Hong Kong", "country": "Hong Kong",
     "airports": ["HKG"]},
    {"season": 3, "episode": 13, "title": "Argentina",
     "air_date": "2007-09-10", "city": "Buenos Aires", "country": "Argentina",
     "airports": ["EZE", "AEP"],
     "note": "journey begins in Buenos Aires before continuing to Patagonia"},
    {"season": 3, "episode": 14, "title": "South Carolina",
     "air_date": "2007-09-17", "city": "Charleston", "country": "United States",
     "airports": ["CHS"]},
    {"season": 3, "episode": 15, "title": "Tuscany",
     "air_date": "2007-09-24", "city": "Florence", "country": "Italy",
     "airports": ["FLR", "PSA"]},
    {"season": 3, "episode": 16, "title": "Holiday Special",
     "air_date": "2007-12-10", "city": "Connecticut", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "Connecticut holiday special, a drive from New York"},

    # ---- Season 4 (2008) ----
    {"season": 4, "episode": 1, "title": "Singapore",
     "air_date": "2008-01-07", "city": "Singapore", "country": "Singapore",
     "airports": ["SIN"]},
    {"season": 4, "episode": 2, "title": "Berlin",
     "air_date": "2008-01-14", "city": "Berlin", "country": "Germany",
     "airports": ["TXL", "BER"],
     "note": "Tegel was Berlin's gateway in 2008; BER replaced it in 2020, "
             "but airports.json (OpenFlights) predates BER so TXL is checked first"},
    {"season": 4, "episode": 3, "title": "Vancouver, BC",
     "air_date": "2008-01-21", "city": "Vancouver", "country": "Canada",
     "airports": ["YVR"]},
    {"season": 4, "episode": 4, "title": "Greek Islands",
     "air_date": "2008-01-28", "city": "Santorini", "country": "Greece",
     "airports": ["JTR", "ATH"],
     "note": "island-hopping episode; Athens is the mainland gateway"},
    {"season": 4, "episode": 5, "title": "New Orleans",
     "air_date": "2008-02-04", "city": "New Orleans", "country": "United States",
     "airports": ["MSY"]},
    {"season": 4, "episode": 6, "title": "London/Edinburgh",
     "air_date": "2008-02-11", "city": "London", "country": "United Kingdom",
     "airports": ["LHR", "LGW"],
     "note": "two-city episode, London and Edinburgh"},
    {"season": 4, "episode": 7, "title": "Jamaica",
     "air_date": "2008-02-18", "city": "Kingston", "country": "Jamaica",
     "airports": ["KIN", "MBJ"]},
    {"season": 4, "episode": 8, "title": "Romania",
     "air_date": "2008-02-25", "city": "Bucharest", "country": "Romania",
     "airports": ["OTP"]},
    {"season": 4, "episode": 9, "title": "Hawaii",
     "air_date": "2008-03-03", "city": "Honolulu", "country": "United States",
     "airports": ["HNL"]},
    {"season": 4, "episode": 10, "title": "Into the Fire",
     "air_date": "2008-03-10", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "Tony back on the line at Brasserie Les Halles in New York"},
    {"season": 4, "episode": 11, "title": "Laos",
     "air_date": "2008-07-07", "city": "Luang Prabang", "country": "Laos",
     "airports": ["LPQ", "VTE"]},
    {"season": 4, "episode": 12, "title": "Colombia",
     "air_date": "2008-07-14", "city": "Bogota", "country": "Colombia",
     "airports": ["BOG"]},
    {"season": 4, "episode": 13, "title": "Saudi Arabia",
     "air_date": "2008-07-21", "city": "Riyadh", "country": "Saudi Arabia",
     "airports": ["RUH", "JED"]},
    {"season": 4, "episode": 14, "title": "Uruguay",
     "air_date": "2008-07-28", "city": "Montevideo", "country": "Uruguay",
     "airports": ["MVD"]},
    {"season": 4, "episode": 15, "title": "U.S. Southwest",
     "air_date": "2008-08-04", "city": None, "country": "United States",
     "airports": [], "exclude": AMBIGUOUS,
     "exclude_note": "road trip across California, New Mexico, Arizona and Texas, no single destination"},
    {"season": 4, "episode": 16, "title": "Tokyo",
     "air_date": "2008-08-11", "city": "Tokyo", "country": "Japan",
     "airports": ["NRT", "HND"]},
    {"season": 4, "episode": 17, "title": "Spain",
     "air_date": "2008-08-18", "city": "Madrid", "country": "Spain",
     "airports": ["MAD", "BCN"]},
    {"season": 4, "episode": 18, "title": "Egypt",
     "air_date": "2008-08-25", "city": "Cairo", "country": "Egypt",
     "airports": ["CAI"]},
    {"season": 4, "episode": 19, "title": "So Long, Summer",
     "air_date": "2008-09-01", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "behind-the-scenes clip show"},
    {"season": 4, "episode": 20, "title": "At the Table with Anthony Bourdain",
     "air_date": "2008-10-20", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "dinner-table special filmed at wd~50 in New York"},

    # ---- Season 5 (2009) ----
    {"season": 5, "episode": 1, "title": "Mexico",
     "air_date": "2009-01-05", "city": "Mexico City", "country": "Mexico",
     "airports": ["MEX", "PBC"],
     "note": "trip built around Carlos's home state of Puebla; Mexico City is its gateway"},
    {"season": 5, "episode": 2, "title": "Venice",
     "air_date": "2009-01-12", "city": "Venice", "country": "Italy",
     "airports": ["VCE"]},
    {"season": 5, "episode": 3, "title": "Washington D.C.",
     "air_date": "2009-01-19", "city": "Washington", "country": "United States",
     "airports": ["DCA", "IAD", "BWI"]},
    {"season": 5, "episode": 4, "title": "Azores",
     "air_date": "2009-01-26", "city": "Ponta Delgada", "country": "Portugal",
     "airports": ["PDL"]},
    {"season": 5, "episode": 5, "title": "Chicago",
     "air_date": "2009-02-02", "city": "Chicago", "country": "United States",
     "airports": ["ORD"]},
    {"season": 5, "episode": 6, "title": "Food Porn",
     "air_date": "2009-02-09", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "montage of food shots from earlier episodes"},
    {"season": 5, "episode": 7, "title": "Philippines",
     "air_date": "2009-02-16", "city": "Manila", "country": "Philippines",
     "airports": ["MNL"]},
    {"season": 5, "episode": 8, "title": "Disappearing Manhattan",
     "air_date": "2009-02-23", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "old-guard Manhattan restaurants, Bourdain's home city"},
    {"season": 5, "episode": 9, "title": "Sri Lanka",
     "air_date": "2009-03-02", "city": "Colombo", "country": "Sri Lanka",
     "airports": ["CMB"]},
    {"season": 5, "episode": 10, "title": "Vietnam: There's No Place Like Home",
     "air_date": "2009-03-09", "city": "Ho Chi Minh City", "country": "Vietnam",
     "airports": ["SGN", "HAN"]},
    {"season": 5, "episode": 11, "title": "Chile",
     "air_date": "2009-07-13", "city": "Santiago", "country": "Chile",
     "airports": ["SCL"]},
    {"season": 5, "episode": 12, "title": "Australia",
     "air_date": "2009-07-20", "city": "Melbourne", "country": "Australia",
     "airports": ["MEL"],
     "note": "synopsis places the episode in Melbourne"},
    {"season": 5, "episode": 13, "title": "Buffalo/Baltimore/Detroit",
     "air_date": "2009-07-27", "city": "Buffalo", "country": "United States",
     "airports": ["BUF", "BWI", "DTW"],
     "note": "three-city rust belt episode"},
    {"season": 5, "episode": 14, "title": "On the Street",
     "air_date": "2009-08-03", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "street-food clips pulled from across the series"},
    {"season": 5, "episode": 15, "title": "San Francisco",
     "air_date": "2009-08-10", "city": "San Francisco", "country": "United States",
     "airports": ["SFO"]},
    {"season": 5, "episode": 16, "title": "Thailand",
     "air_date": "2009-03-16", "city": "Bangkok", "country": "Thailand",
     "airports": ["BKK"]},
    {"season": 5, "episode": 17, "title": "Montana",
     "air_date": "2009-08-24", "city": "Livingston", "country": "United States",
     "airports": ["BZN"],
     "note": "Bozeman is the airport for Livingston, Montana"},
    {"season": 5, "episode": 18, "title": "Burning Questions",
     "air_date": "2009-08-31", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "viewer Q&A special"},
    {"season": 5, "episode": 19, "title": "Outer Boroughs",
     "air_date": "2009-09-07", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "New York's five boroughs, Bourdain's home city"},
    {"season": 5, "episode": 20, "title": "Sardinia",
     "air_date": "2009-09-14", "city": "Cagliari", "country": "Italy",
     "airports": ["CAG", "OLB"]},

    # ---- Season 6 (2010) ----
    {"season": 6, "episode": 1, "title": "Panama",
     "air_date": "2010-01-11", "city": "Panama City", "country": "Panama",
     "airports": ["PTY"]},
    {"season": 6, "episode": 2, "title": "Istanbul",
     "air_date": "2010-01-18", "city": "Istanbul", "country": "Turkey",
     "airports": ["IST"]},
    {"season": 6, "episode": 3, "title": "Brittany",
     "air_date": "2010-01-25", "city": "Rennes", "country": "France",
     "airports": ["RNS", "BES"]},
    {"season": 6, "episode": 4, "title": "Prague",
     "air_date": "2010-02-01", "city": "Prague", "country": "Czech Republic",
     "airports": ["PRG"]},
    {"season": 6, "episode": 5, "title": "Hudson Valley, NY",
     "air_date": "2010-02-08", "city": "Hudson Valley", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "upstate New York, a drive from the city"},
    {"season": 6, "episode": 6, "title": "Ecuador",
     "air_date": "2010-03-01", "city": "Quito", "country": "Ecuador",
     "airports": ["UIO", "GYE"]},
    {"season": 6, "episode": 7, "title": "Obsessed",
     "air_date": "2010-03-08", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "themed clip show about food obsessives"},
    {"season": 6, "episode": 8, "title": "Harbin, China",
     "air_date": "2010-03-15", "city": "Harbin", "country": "China",
     "airports": ["HRB"]},
    {"season": 6, "episode": 9, "title": "Provence",
     "air_date": "2010-03-22", "city": "Marseille", "country": "France",
     "airports": ["MRS", "NCE"]},
    {"season": 6, "episode": 10, "title": "Vietnam Central Highlands",
     "air_date": "2010-03-29", "city": "Da Lat", "country": "Vietnam",
     "airports": ["DLI", "SGN"]},
    {"season": 6, "episode": 11, "title": "Techniques Special",
     "air_date": "2010-04-05", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "chefs demonstrating techniques, no journey"},
    {"season": 6, "episode": 12, "title": "Maine",
     "air_date": "2010-04-12", "city": "Portland", "country": "United States",
     "airports": ["PWM"]},
    {"season": 6, "episode": 13, "title": "Food Porn 2",
     "air_date": "2010-04-19", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "second food-montage special"},
    {"season": 6, "episode": 14, "title": "Caribbean Island Hopping",
     "air_date": "2010-07-05", "city": None, "country": None,
     "airports": [], "exclude": AMBIGUOUS,
     "exclude_note": "multiple islands by boat, no single destination airport"},
    {"season": 6, "episode": 15, "title": "U.S. Heartland",
     "air_date": "2010-07-12", "city": None, "country": "United States",
     "airports": [], "exclude": AMBIGUOUS,
     "exclude_note": "several Midwestern states, no single destination"},
    {"season": 6, "episode": 16, "title": "Liberia",
     "air_date": "2010-07-19", "city": "Monrovia", "country": "Liberia",
     "airports": ["ROB"]},
    {"season": 6, "episode": 17, "title": "Kerala, India",
     "air_date": "2010-07-26", "city": "Kochi", "country": "India",
     "airports": ["COK"]},
    {"season": 6, "episode": 18, "title": "Where It All Began",
     "air_date": "2010-08-02", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "retrospective documentary"},
    {"season": 6, "episode": 19, "title": "Dubai",
     "air_date": "2010-08-09", "city": "Dubai", "country": "United Arab Emirates",
     "airports": ["DXB"]},
    {"season": 6, "episode": 20, "title": "Rome",
     "air_date": "2010-08-16", "city": "Rome", "country": "Italy",
     "airports": ["FCO"]},
    {"season": 6, "episode": 21, "title": "Back to Beirut",
     "air_date": "2010-08-23", "city": "Beirut", "country": "Lebanon",
     "airports": ["BEY"]},
    {"season": 6, "episode": 22, "title": "Making of India",
     "air_date": "2010-08-30", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "how-an-episode-gets-made special"},
    {"season": 6, "episode": 23, "title": "What Were We Thinking Special",
     "air_date": "2010-09-06", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "crew retrospective"},
    {"season": 6, "episode": 24, "title": "Paris",
     "air_date": "2010-09-06", "city": "Paris", "country": "France",
     "airports": ["CDG", "ORY"]},
    {"season": 6, "episode": 25, "title": "Madrid",
     "air_date": "2010-09-13", "city": "Madrid", "country": "Spain",
     "airports": ["MAD"]},
    {"season": 6, "episode": 26, "title": "Holiday Special",
     "air_date": "2010-12-06", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "scripted holiday special, not a journey"},

    # ---- Season 7 (2011) ----
    {"season": 7, "episode": 1, "title": "Haiti",
     "air_date": "2011-02-28", "city": "Port-au-Prince", "country": "Haiti",
     "airports": ["PAP"]},
    {"season": 7, "episode": 2, "title": "Cambodia",
     "air_date": "2011-03-07", "city": "Phnom Penh", "country": "Cambodia",
     "airports": ["PNH", "REP"]},
    {"season": 7, "episode": 3, "title": "Nicaragua",
     "air_date": "2011-03-14", "city": "Managua", "country": "Nicaragua",
     "airports": ["MGA"]},
    {"season": 7, "episode": 4, "title": "Vienna",
     "air_date": "2011-03-21", "city": "Vienna", "country": "Austria",
     "airports": ["VIE"]},
    {"season": 7, "episode": 5, "title": "Ozarks",
     "air_date": "2011-03-28", "city": "Branson", "country": "United States",
     "airports": ["BKG", "SGF"]},
    {"season": 7, "episode": 6, "title": "Brazil",
     "air_date": "2011-04-11", "city": "Manaus", "country": "Brazil",
     "airports": ["MAO"],
     "note": "Amazon episode; Manaus is the river gateway, not Sao Paulo"},
    {"season": 7, "episode": 7, "title": "Boston",
     "air_date": "2011-04-18", "city": "Boston", "country": "United States",
     "airports": ["BOS"]},
    {"season": 7, "episode": 8, "title": "Japan: Hokkaido",
     "air_date": "2011-04-25", "city": "Sapporo", "country": "Japan",
     "airports": ["CTS"]},
    {"season": 7, "episode": 9, "title": "Cuba",
     "air_date": "2011-07-11", "city": "Havana", "country": "Cuba",
     "airports": ["HAV"]},
    {"season": 7, "episode": 10, "title": "Macau",
     "air_date": "2011-07-18", "city": "Macau", "country": "Macau",
     "airports": ["MFM"]},
    {"season": 7, "episode": 11, "title": "Naples",
     "air_date": "2011-07-25", "city": "Naples", "country": "Italy",
     "airports": ["NAP"]},
    {"season": 7, "episode": 12, "title": "El Bulli",
     "air_date": "2011-08-01", "city": "Barcelona", "country": "Spain",
     "airports": ["BCN"],
     "note": "return to elBulli in Roses, Catalonia, before it closed"},
    {"season": 7, "episode": 13, "title": "U.S. Desert",
     "air_date": "2011-08-08", "city": "Palm Springs", "country": "United States",
     "airports": ["PSP"],
     "note": "California High Desert; Palm Springs is the nearest served airport"},
    {"season": 7, "episode": 14, "title": "Ukraine",
     "air_date": "2011-08-15", "city": "Kyiv", "country": "Ukraine",
     "airports": ["KBP"]},
    {"season": 7, "episode": 15, "title": "Kurdistan",
     "air_date": "2011-08-22", "city": "Erbil", "country": "Iraq",
     "airports": ["EBL"]},
    {"season": 7, "episode": 16, "title": "Cajun Country",
     "air_date": "2011-08-29", "city": "Lafayette", "country": "United States",
     "airports": ["LFT", "MSY"]},
    {"season": 7, "episode": 17, "title": "Holiday Special",
     "air_date": "2011-12-12", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "scripted holiday special"},

    # ---- Season 8 (2012) ----
    {"season": 8, "episode": 1, "title": "Mozambique",
     "air_date": "2012-04-09", "city": "Maputo", "country": "Mozambique",
     "airports": ["MPM"]},
    {"season": 8, "episode": 2, "title": "Kansas City",
     "air_date": "2012-04-16", "city": "Kansas City", "country": "United States",
     "airports": ["MCI"]},
    {"season": 8, "episode": 3, "title": "Croatian Coast",
     "air_date": "2012-04-23", "city": "Split", "country": "Croatia",
     "airports": ["SPU", "DBV", "ZAG"]},
    {"season": 8, "episode": 4, "title": "Lisbon",
     "air_date": "2012-04-30", "city": "Lisbon", "country": "Portugal",
     "airports": ["LIS"]},
    {"season": 8, "episode": 5, "title": "Japan: Cook It Raw",
     "air_date": "2012-05-07", "city": "Kanazawa", "country": "Japan",
     "airports": ["KMQ", "NRT"],
     "note": "Cook It Raw was held in Ishikawa; Tokyo is the international gateway"},
    {"season": 8, "episode": 6, "title": "Finland",
     "air_date": "2012-05-14", "city": "Helsinki", "country": "Finland",
     "airports": ["HEL"]},
    {"season": 8, "episode": 7, "title": "Baja",
     "air_date": "2012-05-28", "city": "Tijuana", "country": "Mexico",
     "airports": ["TIJ", "SAN"],
     "note": "Baja California; San Diego is the usual gateway across the border"},
    {"season": 8, "episode": 8, "title": "Penang",
     "air_date": "2012-06-04", "city": "Penang", "country": "Malaysia",
     "airports": ["PEN"]},

    # ---- Season 9 (2012) ----
    {"season": 9, "episode": 1, "title": "Austin",
     "air_date": "2012-09-03", "city": "Austin", "country": "United States",
     "airports": ["AUS"]},
    {"season": 9, "episode": 2, "title": "Sydney",
     "air_date": "2012-09-10", "city": "Sydney", "country": "Australia",
     "airports": ["SYD"]},
    {"season": 9, "episode": 3, "title": "Sex, Drugs and Rock & Roll",
     "air_date": "2012-09-17", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "themed clip special"},
    {"season": 9, "episode": 4, "title": "Emilia Romagna",
     "air_date": "2012-09-24", "city": "Bologna", "country": "Italy",
     "airports": ["BLQ"]},
    {"season": 9, "episode": 5, "title": "Burgundy",
     "air_date": "2012-10-01", "city": "Lyon", "country": "France",
     "airports": ["LYS"],
     "note": "Burgundy road trip; Lyon is the nearest major airport"},
    {"season": 9, "episode": 6, "title": "Seven Deadly Sins",
     "air_date": "2012-10-08", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "themed clip special"},
    {"season": 9, "episode": 7, "title": "Rio",
     "air_date": "2012-10-15", "city": "Rio de Janeiro", "country": "Brazil",
     "airports": ["GIG"]},
    {"season": 9, "episode": 8, "title": "Off the Charts",
     "air_date": "2012-10-22", "city": None, "country": None,
     "airports": [], "exclude": AMBIGUOUS,
     "exclude_note": "unaired segments from several countries stitched together"},
    {"season": 9, "episode": 9, "title": "Dominican Republic",
     "air_date": "2012-10-29", "city": "Santo Domingo", "country": "Dominican Republic",
     "airports": ["SDQ", "PUJ"]},
    {"season": 9, "episode": 10, "title": "Brooklyn",
     "air_date": "2012-11-05", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "series finale in Brooklyn, Bourdain's home city"},
]

# Parts Unknown, CNN, 2013-2018 -- 103 episodes across 12 seasons,
# transcribed from the Wikipedia episode table (which carries titles, air
# dates and a synopsis per episode, so the destination is usually named
# outright: "Southern Italy" -> Apulia and Basilicata, "French Alps" ->
# Chamonix, "Montana" -> Livingston again).
#
# The eight "Prime Cuts" season openers are clip shows of the previous
# season and are excluded as compilations -- note each one AIRED ON THE
# SAME DATE as the real premiere that followed it, which would collide on
# trip_id (prefix + date) if they were ever included.
PARTS_UNKNOWN = [
    # ---- Season 1 (2013) ----
    {"season": 1, "episode": 1, "title": "Myanmar",
     "air_date": "2013-04-14", "city": "Yangon", "country": "Myanmar",
     "airports": ["RGN"]},
    {"season": 1, "episode": 2, "title": "Koreatown, Los Angeles",
     "air_date": "2013-04-21", "city": "Los Angeles", "country": "United States",
     "airports": ["LAX"]},
    {"season": 1, "episode": 3, "title": "Colombia",
     "air_date": "2013-04-28", "city": "Bogota", "country": "Colombia",
     "airports": ["BOG"]},
    {"season": 1, "episode": 4, "title": "Quebec",
     "air_date": "2013-05-05", "city": "Quebec City", "country": "Canada",
     "airports": ["YQB", "YUL"]},
    {"season": 1, "episode": 5, "title": "Morocco (Tangier)",
     "air_date": "2013-05-12", "city": "Tangier", "country": "Morocco",
     "airports": ["TNG", "CMN"]},
    {"season": 1, "episode": 6, "title": "Libya",
     "air_date": "2013-05-19", "city": "Tripoli", "country": "Libya",
     "airports": ["TIP", "BEN"]},
    {"season": 1, "episode": 7, "title": "Peru",
     "air_date": "2013-06-02", "city": "Cusco", "country": "Peru",
     "airports": ["CUZ", "LIM"]},
    {"season": 1, "episode": 8, "title": "Congo",
     "air_date": "2013-06-09", "city": "Brazzaville", "country": "Congo",
     "airports": ["BZV", "FIH"]},

    # ---- Season 2 (2013) ----
    {"season": 2, "episode": 1, "title": "Prime Cuts: Season One",
     "air_date": "2013-09-15", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season one"},
    {"season": 2, "episode": 2, "title": "Jerusalem",
     "air_date": "2013-09-15", "city": "Jerusalem", "country": "Israel",
     "airports": ["TLV"],
     "note": "Tel Aviv is the gateway; the episode covers Jerusalem, Gaza and the West Bank"},
    {"season": 2, "episode": 3, "title": "Spain",
     "air_date": "2013-09-22", "city": "Madrid", "country": "Spain",
     "airports": ["MAD", "BCN"]},
    {"season": 2, "episode": 4, "title": "New Mexico",
     "air_date": "2013-09-29", "city": "Albuquerque", "country": "United States",
     "airports": ["ABQ"]},
    {"season": 2, "episode": 5, "title": "Copenhagen",
     "air_date": "2013-10-06", "city": "Copenhagen", "country": "Denmark",
     "airports": ["CPH"]},
    {"season": 2, "episode": 6, "title": "Sicily",
     "air_date": "2013-10-13", "city": "Palermo", "country": "Italy",
     "airports": ["PMO", "CTA"]},
    {"season": 2, "episode": 7, "title": "South Africa",
     "air_date": "2013-10-20", "city": "Johannesburg", "country": "South Africa",
     "airports": ["JNB", "CPT"]},
    {"season": 2, "episode": 8, "title": "Tokyo",
     "air_date": "2013-11-03", "city": "Tokyo", "country": "Japan",
     "airports": ["NRT", "HND"]},
    {"season": 2, "episode": 9, "title": "Detroit",
     "air_date": "2013-11-10", "city": "Detroit", "country": "United States",
     "airports": ["DTW"]},

    # ---- Season 3 (2014) ----
    {"season": 3, "episode": 1, "title": "Prime Cuts: Season Two",
     "air_date": "2014-04-13", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season two"},
    {"season": 3, "episode": 2, "title": "Punjab, India",
     "air_date": "2014-04-13", "city": "Amritsar", "country": "India",
     "airports": ["ATQ", "DEL"]},
    {"season": 3, "episode": 3, "title": "Las Vegas",
     "air_date": "2014-04-20", "city": "Las Vegas", "country": "United States",
     "airports": ["LAS"]},
    {"season": 3, "episode": 4, "title": "Lyon",
     "air_date": "2014-04-27", "city": "Lyon", "country": "France",
     "airports": ["LYS"]},
    {"season": 3, "episode": 5, "title": "Mexico",
     "air_date": "2014-05-04", "city": "Mexico City", "country": "Mexico",
     "airports": ["MEX"]},
    {"season": 3, "episode": 6, "title": "Russia",
     "air_date": "2014-05-11", "city": "Moscow", "country": "Russia",
     "airports": ["SVO", "DME"]},
    {"season": 3, "episode": 7, "title": "Mississippi Delta",
     "air_date": "2014-05-18", "city": "Memphis", "country": "United States",
     "airports": ["MEM", "JAN"],
     "note": "the Delta is driven from Memphis, its northern gateway"},
    {"season": 3, "episode": 8, "title": "Thailand",
     "air_date": "2014-06-01", "city": "Chiang Mai", "country": "Thailand",
     "airports": ["CNX", "BKK"]},
    {"season": 3, "episode": 9, "title": "Bahia, Brazil",
     "air_date": "2014-06-08", "city": "Salvador", "country": "Brazil",
     "airports": ["SSA", "GRU"]},

    # ---- Season 4 (2014) ----
    {"season": 4, "episode": 1, "title": "Prime Cuts: Season Three",
     "air_date": "2014-09-28", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season three"},
    {"season": 4, "episode": 2, "title": "Shanghai",
     "air_date": "2014-09-28", "city": "Shanghai", "country": "China",
     "airports": ["PVG"]},
    {"season": 4, "episode": 3, "title": "The Bronx",
     "air_date": "2014-10-05", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "a borough of Bourdain's home city"},
    {"season": 4, "episode": 4, "title": "Paraguay",
     "air_date": "2014-10-12", "city": "Asuncion", "country": "Paraguay",
     "airports": ["ASU"]},
    {"season": 4, "episode": 5, "title": "Vietnam",
     "air_date": "2014-10-19", "city": "Ho Chi Minh City", "country": "Vietnam",
     "airports": ["SGN", "HAN"]},
    {"season": 4, "episode": 6, "title": "Tanzania",
     "air_date": "2014-10-26", "city": "Dar es Salaam", "country": "Tanzania",
     "airports": ["DAR", "JRO"]},
    {"season": 4, "episode": 7, "title": "Iran",
     "air_date": "2014-11-02", "city": "Tehran", "country": "Iran",
     "airports": ["IKA"]},
    {"season": 4, "episode": 8, "title": "Massachusetts",
     "air_date": "2014-11-09", "city": "Boston", "country": "United States",
     "airports": ["BOS"],
     "note": "Provincetown, where Bourdain started cooking; Boston is its gateway"},
    {"season": 4, "episode": 9, "title": "Jamaica",
     "air_date": "2014-11-16", "city": "Kingston", "country": "Jamaica",
     "airports": ["KIN", "MBJ"]},

    # ---- Season 5 (2015) ----
    {"season": 5, "episode": 1, "title": "Prime Cuts: Season Four",
     "air_date": "2015-04-26", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season four"},
    {"season": 5, "episode": 2, "title": "Korea",
     "air_date": "2015-04-26", "city": "Seoul", "country": "South Korea",
     "airports": ["ICN"]},
    {"season": 5, "episode": 3, "title": "Miami",
     "air_date": "2015-05-03", "city": "Miami", "country": "United States",
     "airports": ["MIA", "FLL"]},
    {"season": 5, "episode": 4, "title": "Scotland",
     "air_date": "2015-05-10", "city": "Edinburgh", "country": "United Kingdom",
     "airports": ["EDI", "GLA"]},
    {"season": 5, "episode": 5, "title": "Madagascar",
     "air_date": "2015-05-17", "city": "Antananarivo", "country": "Madagascar",
     "airports": ["TNR"]},
    {"season": 5, "episode": 6, "title": "New Jersey",
     "air_date": "2015-05-31", "city": "New Jersey", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "the Jersey shore, a drive from New York"},
    {"season": 5, "episode": 7, "title": "Budapest",
     "air_date": "2015-06-07", "city": "Budapest", "country": "Hungary",
     "airports": ["BUD"]},
    {"season": 5, "episode": 8, "title": "Hawaii",
     "air_date": "2015-06-14", "city": "Honolulu", "country": "United States",
     "airports": ["HNL", "LIH"]},
    {"season": 5, "episode": 9, "title": "Beirut",
     "air_date": "2015-06-21", "city": "Beirut", "country": "Lebanon",
     "airports": ["BEY"]},

    # ---- Season 6 (2015) ----
    {"season": 6, "episode": 1, "title": "Prime Cuts: Season Five",
     "air_date": "2015-09-27", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season five"},
    {"season": 6, "episode": 2, "title": "Cuba",
     "air_date": "2015-09-27", "city": "Havana", "country": "Cuba",
     "airports": ["HAV"]},
    {"season": 6, "episode": 3, "title": "Marseille, France",
     "air_date": "2015-10-04", "city": "Marseille", "country": "France",
     "airports": ["MRS", "NCE"]},
    {"season": 6, "episode": 4, "title": "Okinawa, Japan",
     "air_date": "2015-10-11", "city": "Naha", "country": "Japan",
     "airports": ["OKA"]},
    {"season": 6, "episode": 5, "title": "Bay Area",
     "air_date": "2015-10-18", "city": "San Francisco", "country": "United States",
     "airports": ["SFO", "OAK"]},
    {"season": 6, "episode": 6, "title": "Ethiopia",
     "air_date": "2015-10-25", "city": "Addis Ababa", "country": "Ethiopia",
     "airports": ["ADD"]},
    {"season": 6, "episode": 7, "title": "Borneo",
     "air_date": "2015-11-01", "city": "Kuching", "country": "Malaysia",
     "airports": ["KCH", "BKI", "KUL"]},
    {"season": 6, "episode": 8, "title": "Istanbul",
     "air_date": "2015-11-08", "city": "Istanbul", "country": "Turkey",
     "airports": ["IST"]},
    {"season": 6, "episode": 9, "title": "Charleston, SC",
     "air_date": "2015-11-15", "city": "Charleston", "country": "United States",
     "airports": ["CHS"]},

    # ---- Season 7 (2016) ----
    {"season": 7, "episode": 1, "title": "Prime Cuts: Season Six",
     "air_date": "2016-04-24", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season six"},
    {"season": 7, "episode": 2, "title": "Manila, Philippines",
     "air_date": "2016-04-24", "city": "Manila", "country": "Philippines",
     "airports": ["MNL"]},
    {"season": 7, "episode": 3, "title": "Chicago",
     "air_date": "2016-05-01", "city": "Chicago", "country": "United States",
     "airports": ["ORD", "MDW"]},
    {"season": 7, "episode": 4, "title": "The Greek Islands",
     "air_date": "2016-05-08", "city": "Naxos", "country": "Greece",
     "airports": ["JTR", "ATH"],
     "note": "island episode; Athens is the mainland gateway"},
    {"season": 7, "episode": 5, "title": "Montana",
     "air_date": "2016-05-15", "city": "Livingston", "country": "United States",
     "airports": ["BZN"],
     "note": "a return to Livingston, also the subject of No Reservations S5.E17"},
    {"season": 7, "episode": 6, "title": "Tbilisi, Georgia",
     "air_date": "2016-05-22", "city": "Tbilisi", "country": "Georgia",
     "airports": ["TBS"]},
    {"season": 7, "episode": 7, "title": "Senegal",
     "air_date": "2016-05-29", "city": "Dakar", "country": "Senegal",
     "airports": ["DKR"]},
    {"season": 7, "episode": 8, "title": "Cologne, Germany",
     "air_date": "2016-06-05", "city": "Cologne", "country": "Germany",
     "airports": ["CGN", "DUS", "FRA"]},

    # ---- Season 8 (2016) ----
    {"season": 8, "episode": 1, "title": "Prime Cuts: Season Seven",
     "air_date": "2016-09-24", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season seven"},
    {"season": 8, "episode": 2, "title": "Hanoi",
     "air_date": "2016-09-25", "city": "Hanoi", "country": "Vietnam",
     "airports": ["HAN"],
     "note": "the bun cha dinner with President Obama"},
    {"season": 8, "episode": 3, "title": "Nashville",
     "air_date": "2016-10-02", "city": "Nashville", "country": "United States",
     "airports": ["BNA"]},
    {"season": 8, "episode": 4, "title": "Sichuan",
     "air_date": "2016-10-16", "city": "Chengdu", "country": "China",
     "airports": ["CTU"]},
    {"season": 8, "episode": 5, "title": "London",
     "air_date": "2016-10-23", "city": "London", "country": "United Kingdom",
     "airports": ["LHR", "LGW"]},
    {"season": 8, "episode": 6, "title": "Houston",
     "air_date": "2016-10-30", "city": "Houston", "country": "United States",
     "airports": ["IAH", "HOU"]},
    {"season": 8, "episode": 7, "title": "Japan with Masa",
     "air_date": "2016-11-13", "city": "Tokyo", "country": "Japan",
     "airports": ["NRT", "HND"]},
    {"season": 8, "episode": 8, "title": "Buenos Aires",
     "air_date": "2016-11-20", "city": "Buenos Aires", "country": "Argentina",
     "airports": ["EZE", "AEP"]},
    {"season": 8, "episode": 9, "title": "Minas Gerais, Brazil",
     "air_date": "2016-11-27", "city": "Belo Horizonte", "country": "Brazil",
     "airports": ["CNF", "GRU"]},
    {"season": 8, "episode": 10, "title": "Rome",
     "air_date": "2016-12-04", "city": "Rome", "country": "Italy",
     "airports": ["FCO"]},

    # ---- Season 9 (2017) ----
    {"season": 9, "episode": 1, "title": "Prime Cuts: Season Eight",
     "air_date": "2017-04-23", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "clip show of season eight"},
    {"season": 9, "episode": 2, "title": "Los Angeles",
     "air_date": "2017-04-30", "city": "Los Angeles", "country": "United States",
     "airports": ["LAX"]},
    {"season": 9, "episode": 3, "title": "San Sebastian",
     "air_date": "2017-05-07", "city": "San Sebastian", "country": "Spain",
     "airports": ["EAS", "BIO", "BIQ"]},
    {"season": 9, "episode": 4, "title": "Laos",
     "air_date": "2017-05-14", "city": "Luang Prabang", "country": "Laos",
     "airports": ["LPQ", "VTE"]},
    {"season": 9, "episode": 5, "title": "Queens",
     "air_date": "2017-05-21", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "a borough of Bourdain's home city"},
    {"season": 9, "episode": 6, "title": "Antarctica",
     "air_date": "2017-06-04", "city": "Antarctica", "country": "Antarctica",
     "airports": [], "exclude": NO_NONSTOP,
     "exclude_note": "no scheduled passenger service exists; the crew flew in from Punta Arenas"},
    {"season": 9, "episode": 7, "title": "Oman",
     "air_date": "2017-06-11", "city": "Muscat", "country": "Oman",
     "airports": ["MCT"]},
    {"season": 9, "episode": 8, "title": "Trinidad",
     "air_date": "2017-06-25", "city": "Port of Spain", "country": "Trinidad and Tobago",
     "airports": ["POS"]},
    {"season": 9, "episode": 9, "title": "Porto, Portugal",
     "air_date": "2017-07-02", "city": "Porto", "country": "Portugal",
     "airports": ["OPO"]},

    # ---- Season 10 (2017) ----
    {"season": 10, "episode": 1, "title": "Singapore",
     "air_date": "2017-10-01", "city": "Singapore", "country": "Singapore",
     "airports": ["SIN"]},
    {"season": 10, "episode": 2, "title": "French Alps",
     "air_date": "2017-10-08", "city": "Chamonix", "country": "France",
     "airports": ["GVA", "LYS"],
     "note": "Chamonix is served from Geneva, across the Swiss border"},
    {"season": 10, "episode": 3, "title": "Lagos, Nigeria",
     "air_date": "2017-10-15", "city": "Lagos", "country": "Nigeria",
     "airports": ["LOS"]},
    {"season": 10, "episode": 4, "title": "Pittsburgh",
     "air_date": "2017-10-22", "city": "Pittsburgh", "country": "United States",
     "airports": ["PIT"]},
    {"season": 10, "episode": 5, "title": "Sri Lanka",
     "air_date": "2017-10-29", "city": "Colombo", "country": "Sri Lanka",
     "airports": ["CMB"]},
    {"season": 10, "episode": 6, "title": "Puerto Rico",
     "air_date": "2017-11-05", "city": "San Juan", "country": "Puerto Rico",
     "airports": ["SJU"]},
    {"season": 10, "episode": 7, "title": "Seattle",
     "air_date": "2017-11-19", "city": "Seattle", "country": "United States",
     "airports": ["SEA"]},
    {"season": 10, "episode": 8, "title": "Southern Italy",
     "air_date": "2017-11-26", "city": "Bari", "country": "Italy",
     "airports": ["BRI", "NAP", "FCO"],
     "note": "Apulia and Basilicata; Bari is the regional airport, Rome the intercontinental one"},

    # ---- Season 11 (2018) ----
    {"season": 11, "episode": 1, "title": "West Virginia",
     "air_date": "2018-04-29", "city": "Charleston", "country": "United States",
     "airports": ["CRW", "PIT"],
     "note": "Charleston, West Virginia -- not the South Carolina one"},
    {"season": 11, "episode": 2, "title": "Uruguay",
     "air_date": "2018-05-06", "city": "Montevideo", "country": "Uruguay",
     "airports": ["MVD"]},
    {"season": 11, "episode": 3, "title": "Newfoundland",
     "air_date": "2018-05-13", "city": "St. John's", "country": "Canada",
     "airports": ["YYT"]},
    {"season": 11, "episode": 4, "title": "Armenia",
     "air_date": "2018-05-20", "city": "Yerevan", "country": "Armenia",
     "airports": ["EVN"]},
    {"season": 11, "episode": 5, "title": "Hong Kong",
     "air_date": "2018-06-03", "city": "Hong Kong", "country": "Hong Kong",
     "airports": ["HKG"]},
    {"season": 11, "episode": 6, "title": "Berlin",
     "air_date": "2018-06-10", "city": "Berlin", "country": "Germany",
     "airports": ["TXL", "BER"]},
    {"season": 11, "episode": 7, "title": "Cajun Mardi Gras",
     "air_date": "2018-06-17", "city": "Lafayette", "country": "United States",
     "airports": ["LFT", "MSY"]},
    {"season": 11, "episode": 8, "title": "Bhutan",
     "air_date": "2018-06-24", "city": "Paro", "country": "Bhutan",
     "airports": ["PBH"]},

    # ---- Season 12 (2018) ----
    {"season": 12, "episode": 1, "title": "Kenya",
     "air_date": "2018-09-23", "city": "Nairobi", "country": "Kenya",
     "airports": ["NBO"]},
    {"season": 12, "episode": 2, "title": "Asturias, Spain",
     "air_date": "2018-09-30", "city": "Oviedo", "country": "Spain",
     "airports": ["OVD", "MAD"]},
    {"season": 12, "episode": 3, "title": "Indonesia",
     "air_date": "2018-10-07", "city": "Denpasar", "country": "Indonesia",
     "airports": ["DPS", "CGK"]},
    {"season": 12, "episode": 4, "title": "Tony's Impact",
     "air_date": "2018-10-14", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "tribute special assembled after Bourdain's death"},
    {"season": 12, "episode": 5, "title": "Far West Texas",
     "air_date": "2018-10-21", "city": "El Paso", "country": "United States",
     "airports": ["ELP", "MAF"]},
    {"season": 12, "episode": 6, "title": "Under the Tarp",
     "air_date": "2018-10-28", "city": None, "country": None,
     "airports": [], "exclude": COMPILATION,
     "exclude_note": "behind-the-scenes special"},
    {"season": 12, "episode": 7, "title": "Lower East Side",
     "air_date": "2018-11-11", "city": "New York City", "country": "United States",
     "airports": [], "exclude": GROUND,
     "exclude_note": "series finale in Manhattan, Bourdain's home city"},
]

# Both shows in one table, each row tagged with which show it came from.
# The show code also prefixes episode_code, because "S1.E1" alone is
# ambiguous once there are two series in the file.
EPISODES = (
    [{**ep, "show": "No Reservations", "show_code": "NR"} for ep in NO_RESERVATIONS]
    + [{**ep, "show": "Parts Unknown", "show_code": "PU"} for ep in PARTS_UNKNOWN]
)

CSV_FIELDS = [
    "trip_id",
    "show",
    "season",
    "episode",
    "episode_code",
    "episode_title",
    "episode_destination",
    "air_date",
    "start_date",
    "end_date",
    "duration_days",
    "traveler_name",
    "destination_city",
    "destination_country",
    "destination_airport",
    "destination_airport_name",
    "destination_lat",
    "destination_lng",
    "origin_airport",
    "origin_alternates",
    "nonstop_airlines",
    "nonstop_airline_count",
    "distance_km",
    "is_domestic",
    "notes",
]


def load_airports():
    """IATA -> airport record, from data/reference/airports.json."""
    with AIRPORTS_PATH.open() as fh:
        payload = json.load(fh)
    return {a["iata"]: a for a in payload["airports"] if a.get("iata")}


def load_nyc_routes():
    """
    (origin, destination) -> route facts, for origins in ORIGIN_PREFERENCE
    only. airline_routes_enhanced.csv has one row per airline per route, so
    the airlines are collected into a sorted list and the route's distance
    is taken from the first row that carries one.
    """
    routes = defaultdict(lambda: {"airlines": set(), "distance_km": None, "is_domestic": None})
    with ROUTES_PATH.open(newline="") as fh:
        for row in csv.DictReader(fh):
            origin = row["Departure"]
            if origin not in ORIGIN_PREFERENCE:
                continue
            route = routes[(origin, row["Destination"])]
            route["airlines"].add(row["Airline ID"])
            if route["distance_km"] is None and row.get("distance_km"):
                route["distance_km"] = float(row["distance_km"])
            if route["is_domestic"] is None and row.get("is_domestic"):
                route["is_domestic"] = int(row["is_domestic"])
    return {k: {**v, "airlines": sorted(v["airlines"])} for k, v in routes.items()}


def resolve_flight(candidate_airports, routes):
    """
    Walk the episode's candidate destination airports in order and return
    the first one any New York airport flies to nonstop, together with the
    winning origin (JFK before LGA before EWR) and the other New York
    airports that also serve it. Returns None when nothing is flyable.
    """
    for destination in candidate_airports:
        serving = [o for o in ORIGIN_PREFERENCE if (o, destination) in routes]
        if not serving:
            continue
        origin, alternates = serving[0], serving[1:]
        return {
            "destination_airport": destination,
            "origin_airport": origin,
            "origin_alternates": alternates,
            **routes[(origin, destination)],
        }
    return None


def build_rows():
    airports = load_airports()
    routes = load_nyc_routes()

    trips, excluded = [], []
    trip_id = 0

    for ep in EPISODES:
        code = f"{ep['show_code']} S{ep['season']}.E{ep['episode']}"
        base = {
            "show": ep["show"],
            "season": ep["season"],
            "episode": ep["episode"],
            "episode_code": code,
            "episode_title": ep["title"],
            "air_date": ep["air_date"],
            "destination_city": ep.get("city"),
            "destination_country": ep.get("country"),
        }

        if ep.get("exclude"):
            excluded.append({**base, "reason": ep["exclude"], "reason_note": ep.get("exclude_note", "")})
            continue

        flight = resolve_flight(ep["airports"], routes)
        if flight is None:
            excluded.append({
                **base,
                "reason": NO_NONSTOP,
                "reason_note": "no nonstop from JFK/LGA/EWR to "
                               + "/".join(ep["airports"]) + " in airline_routes_enhanced.csv",
            })
            continue

        start = datetime.strptime(ep["air_date"], "%Y-%m-%d").date()
        end = start + timedelta(days=TRIP_DAYS)
        airport = airports.get(flight["destination_airport"], {})

        notes = []
        if ep.get("note"):
            notes.append(ep["note"])

        # When the episode's first-choice airport has no New York nonstop
        # and a later candidate wins, the trip is really to that second
        # airport's city -- so the destination columns follow the airport
        # (Kolkata -> Mumbai for S2.E10), and the episode's own subject
        # stays visible in episode_destination and the note.
        # The airport can also be in a DIFFERENT COUNTRY from the place the
        # episode is about even when it was the first choice -- Chamonix in
        # the French Alps is flown to via Geneva, in Switzerland. Following
        # the episode there would file a Swiss airport under France and
        # break the country-code join, so the country follows the airport
        # in that case too.
        resolved = dict(base)
        substituted = flight["destination_airport"] != ep["airports"][0]
        crosses_border = bool(airport.get("country")) and airport["country"] != ep["country"]
        if substituted or crosses_border:
            if substituted:
                notes.append(
                    f"{ep['airports'][0]} ({ep['city']}) has no New York nonstop; "
                    f"resolved to {flight['destination_airport']}"
                )
            if crosses_border:
                notes.append(
                    f"{ep['city']}, {ep['country']} is served from "
                    f"{flight['destination_airport']} in {airport['country']}"
                )
            if airport.get("city"):
                resolved["destination_city"] = airport["city"]
                resolved["destination_country"] = airport.get("country", ep["country"])

        trip_id += 1
        trips.append({
            "trip_id": trip_id,
            **resolved,
            "episode_destination": f"{ep['city']}, {ep['country']}",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "duration_days": TRIP_DAYS,
            "traveler_name": TRAVELER["traveler_name"],
            "destination_airport": flight["destination_airport"],
            "destination_airport_name": airport.get("name", ""),
            "destination_lat": airport.get("lat"),
            "destination_lng": airport.get("lng"),
            "origin_airport": flight["origin_airport"],
            "origin_alternates": flight["origin_alternates"],
            "nonstop_airlines": flight["airlines"],
            "nonstop_airline_count": len(flight["airlines"]),
            "distance_km": flight["distance_km"],
            "is_domestic": flight["is_domestic"],
            "notes": "; ".join(notes),
        })

    return trips, excluded


def to_csv_row(trip):
    row = {k: trip.get(k) for k in CSV_FIELDS}
    row["origin_alternates"] = "|".join(trip.get("origin_alternates") or [])
    row["nonstop_airlines"] = "|".join(trip.get("nonstop_airlines") or [])
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-excluded",
        action="store_true",
        help="also write the excluded episodes to the CSV (blank flight columns, reason in notes)",
    )
    args = parser.parse_args()

    trips, excluded = build_rows()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV_PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for trip in trips:
            writer.writerow(to_csv_row(trip))
        if args.include_excluded:
            for ep in excluded:
                writer.writerow(to_csv_row({
                    **ep,
                    "traveler_name": TRAVELER["traveler_name"],
                    "notes": f"EXCLUDED ({ep['reason']}): {ep['reason_note']}",
                }))

    payload = {
        "source": f"IMDb episode list for No Reservations (tt0475900), seasons 1-9 -- {IMDB_URL} "
                  f"-- and Wikipedia's episode table for Parts Unknown (CNN, 2013-2018), "
                  f"seasons 1-12 -- {PARTS_UNKNOWN_URL}",
        "generated": date.today().isoformat(),
        "traveler": TRAVELER,
        "assumptions": {
            "start_date": "episode original air date (the only date these sources publish; "
                          "filming predates it)",
            "duration_days": TRIP_DAYS,
            "trip_shape": "round trip out of New York, nonstop each way",
            "origin_preference": list(ORIGIN_PREFERENCE),
            "flights_only": "an episode is kept only if a nonstop from JFK, LGA or EWR to the "
                            "destination airport exists in airline_routes_enhanced.csv",
            "route_data_vintage": "airline_routes_enhanced.csv is a present-day route snapshot, "
                                  "not a 2005-2007 schedule -- exclusions mean 'no nonstop today'",
        },
        "counts": {
            "episodes": len(EPISODES),
            "trips": len(trips),
            "excluded": len(excluded),
            "by_show": {
                show: {
                    "episodes": sum(1 for ep in EPISODES if ep["show"] == show),
                    "trips": sum(1 for t in trips if t["show"] == show),
                    "excluded": sum(1 for e in excluded if e["show"] == show),
                }
                for show in ("No Reservations", "Parts Unknown")
            },
        },
        "trips": trips,
        "excluded_episodes": excluded,
    }
    with OUT_JSON_PATH.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")

    print(f"Wrote {len(trips)} trips to {OUT_CSV_PATH}")
    print(f"Wrote {len(trips)} trips + {len(excluded)} excluded episodes to {OUT_JSON_PATH}")

    by_origin = defaultdict(int)
    for trip in trips:
        by_origin[trip["origin_airport"]] += 1
    print("Origins: " + ", ".join(f"{k} {v}" for k, v in sorted(by_origin.items())))

    # airports.json is an OpenFlights snapshot and lags new airport codes
    # (BER, for one), so a route can exist for an airport the reference
    # file has never heard of -- that would silently blank the name and
    # coordinates, so say so instead.
    unknown = [(t["episode_code"], t["destination_airport"])
               for t in trips if not t["destination_airport_name"]]
    if unknown:
        print("\nWARNING -- destination airport missing from airports.json "
              "(no name or coordinates): "
              + ", ".join(f"{code} {iata}" for code, iata in unknown))

    for show in ("No Reservations", "Parts Unknown"):
        kept = sum(1 for t in trips if t["show"] == show)
        total = sum(1 for ep in EPISODES if ep["show"] == show)
        print(f"  {show:<16} {kept:>3} trips from {total:>3} episodes")

    print(f"\nExcluded {len(excluded)} episodes:")
    for ep in excluded:
        print(f"  {ep['episode_code']:<12} {ep['episode_title'][:40]:<40} {ep['reason']}")


if __name__ == "__main__":
    main()
