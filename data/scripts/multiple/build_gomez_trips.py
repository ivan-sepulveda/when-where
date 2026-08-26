"""
Derived from: nothing -- this is a HAND-KEPT FLIGHT LOG, typed in from
              boarding passes and itineraries as the flights happen. Every
              other traveler in this project is derived from a published
              source (an episode list, a Kaggle export); this one is the
              first where the trips are simply true.
Requires: data/reference/airports.json (IATA -> city/country/coords) and
          data/processed/multiple/airline_routes_enhanced.csv (distance,
          domestic flag, and who flies the route) -- both read through
          chef_trips.py.

Writes data/processed/multiple/gomez_trips.csv and .json: one row per
FLIGHT LEG, exactly as flown.

WHY THIS ISN'T build_bourdain_trips.py WITH A DIFFERENT TABLE. The chef
scripts start from "an episode happened somewhere" and have to derive the
flight: which airport serves that place, whether any home airport reaches
it nonstop, how long the trip must have been. Every one of those is an
inference, and half the machinery in chef_trips.py exists to record which
inference was made.

None of that applies here. The leg is the fact. The airports are given,
the date is given, the airline is given, and no episode has to be
resolved to a city. So this script derives exactly three things -- the
city and country each airport is in, the distance, and whether the leg is
domestic -- and copies the rest down verbatim.

    ORIGIN_PREFERENCE = (none)

Ivan's call: legs are logged as given, with no home-airport preference.
The declared base below is a separate thing -- it sets which country the
domestic/international split is measured against, not which airport a
trip is assumed to start from.

DATES, AND THE MIDNIGHT PROBLEM. A leg that departs 20:20 and lands 00:30
crosses a date boundary, so start_date and end_date are genuinely
different days and duration_days is 1. That is not a one-night trip: it's
a red-eye that landed after midnight, and `block_minutes` carries the real
3h10m. Anything reading duration_days here should treat it as "days the
journey touched", which is what the rest of this dataset means by it too.

RETURN LEGS ARE THEIR OWN ROWS. A round trip is two legs and this file
records both, rather than one row with a start and an end -- adding the
return later must never require editing a row that already describes a
flight that already happened.

Usage:
    python build_gomez_trips.py
"""

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

from chef_trips import PROCESSED_DIR, ROUTES_PATH, load_airports  # noqa: E402

OUT_CSV_PATH = PROCESSED_DIR / "gomez_trips.csv"
OUT_JSON_PATH = PROCESSED_DIR / "gomez_trips.json"

TRAVELER = {
    "traveler_id": "gomez",
    "traveler_name": "Eduardo Gomez",
    # A PSEUDONYM, at Ivan's request, and the reason there is no birthdate,
    # age or gender in this file: the other travelers carry those because
    # they are public figures whose biographies are published, and inventing
    # them for a real private person would put fabricated personal data in a
    # dataset that is otherwise true.
    "pseudonym": True,
    "home_city": "Houston",
    "home_country": "United States",
    "source": "hand-kept flight log",
}

# Declared so build_travelers.py doesn't fall back to guessing a home city
# from nationality -- see its infer_base(). Houston because that is where
# the logged flights depart from, not an assumption about where anyone
# lives; change it here if that stops being true.
DECLARED_BASE = {
    "base_city": "Houston",
    "base_country": "United States",
    "base_country_code": "US",
}

# One entry per leg, in the order flown.
#
#   date / depart      local departure date and time, as printed on the ticket
#   arrive_date        the local date it LANDS -- different when it lands
#                      after midnight, which is the whole reason this is a
#                      separate field rather than something computed
#   block_minutes      gate to gate, as the itinerary states it
#   carrier            IATA code; the airline actually flown, not a preference
FLIGHTS = [
    {
        "date": "2024-09-07",
        "depart": "20:10",
        "arrive": "08:00",
        "arrive_date": "2024-09-08",
        "block_minutes": 590,
        "origin": "IAH",
        "destination": "EZE",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-05-24",
        "depart": "20:15",
        "arrive": "09:35",
        "arrive_date": "2025-05-25",
        "block_minutes": 560,
        "origin": "IAH",
        "destination": "LHR",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-07-31",
        "depart": "13:00",
        "arrive": "15:21",
        "arrive_date": "2025-07-31",
        "block_minutes": 141,
        "origin": "EWR",
        "destination": "ATL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-08-05",
        "depart": "19:29",
        "arrive": "21:55",
        "arrive_date": "2025-08-05",
        "block_minutes": 146,
        "origin": "ATL",
        "destination": "EWR",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-11-07",
        "depart": "16:54",
        "arrive": "18:24",
        "arrive_date": "2025-11-07",
        "block_minutes": 210,
        "origin": "IAH",
        "destination": "SAN",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-10-30",
        "depart": "17:00",
        "arrive": "21:10",
        "arrive_date": "2026-10-31",
        "block_minutes": 790,
        "origin": "LAX",
        "destination": "HND",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-11-13",
        "depart": "22:30",
        "arrive": "18:55",
        "arrive_date": "2026-11-13",
        "block_minutes": 745,
        "origin": "HKG",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-09-26",
        "depart": "20:20",
        "arrive": "00:30",
        "arrive_date": "2026-09-27",
        "block_minutes": 190,
        "origin": "IAH",
        "destination": "IAD",
        "carrier": "UA",
        "note": "United is the only carrier on IAH-IAD in the route data -- both ends are its hubs",
        "layover": False,
    },
    {
        "date": "2026-05-22",
        "depart": "18:21",
        "arrive": "19:47",
        "arrive_date": "2026-05-22",
        "block_minutes": 86,
        "origin": "GDL",
        "destination": "PBC",
        "carrier": "Y4",
        "note": "Volaris flight 1396",
        "layover": False,
    },
    {
        "date": "2026-03-06",
        "depart": "10:29",
        "arrive": "11:57",
        "arrive_date": "2026-03-06",
        "block_minutes": 88,
        "origin": "GDL",
        "destination": "MTY",
        "carrier": "Y4",
        "note": "Volaris flight 1082",
        "layover": False,
    },
    {
        "date": "2026-03-08",
        "depart": "12:38",
        "arrive": "14:08",
        "arrive_date": "2026-03-08",
        "block_minutes": 90,
        "origin": "MTY",
        "destination": "GDL",
        "carrier": "Y4",
        "note": "Volaris flight 1083",
        "layover": False,
    },
    {
        "date": "2024-06-14",
        "depart": "13:15",
        "arrive": "16:40",
        "arrive_date": "2024-06-14",
        "block_minutes": 145,
        "origin": "LIS",
        "destination": "NCE",
        "carrier": "U2",
        "note": "easyJet flight EJU6731",
        "layover": False,
    },
    {
        "date": "2024-06-07",
        "depart": "09:15",
        "arrive": "12:19",
        "arrive_date": "2024-06-07",
        "block_minutes": 124,
        "origin": "IAH",
        "destination": "ATL",
        "carrier": "DL",
        "note": "Delta flight 1585 -- layover, final destination is Lisbon (see the CDG-LIS leg)",
        "layover": True,
    },
    {
        "date": "2024-06-07",
        "depart": "15:25",
        "arrive": "06:10",
        "arrive_date": "2024-06-08",
        "block_minutes": 525,
        "origin": "ATL",
        "destination": "CDG",
        "carrier": "DL",
        "note": "Delta flight 82 -- layover, final destination is Lisbon (see the CDG-LIS leg)",
        "layover": True,
    },
    {
        "date": "2024-06-08",
        "depart": "09:35",
        "arrive": "11:15",
        "arrive_date": "2024-06-08",
        "block_minutes": 160,
        "origin": "CDG",
        "destination": "LIS",
        "carrier": "DL",
        "note": "Delta flight 8440, marked * on the itinerary (codeshare) -- no operating carrier "
                "given, logged as Delta as flown/ticketed",
        "layover": False,
    },
    {
        "date": "2026-08-21",
        "depart": "12:02",
        "arrive": "13:45",
        "arrive_date": "2026-08-21",
        "block_minutes": 103,
        "origin": "GDL",
        "destination": "MEX",
        "carrier": "AM",
        "note": "Aeromexico flight 225, marked * on the itinerary (codeshare) -- no operating "
                "carrier given, logged as Aeromexico as flown/ticketed",
        "layover": False,
    },
    {
        "date": "2026-08-24",
        "depart": "20:10",
        "arrive": "21:39",
        "arrive_date": "2026-08-24",
        "block_minutes": 89,
        "origin": "MEX",
        "destination": "GDL",
        "carrier": "AM",
        "note": "Aeromexico flight 256, marked * on the itinerary (codeshare) -- no operating "
                "carrier given, logged as Aeromexico as flown/ticketed",
        "layover": False,
    },
    {
        "date": "2021-06-11",
        "depart": None,
        "arrive": None,
        "arrive_date": "2021-06-11",
        "block_minutes": None,
        "origin": "SNA",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2021-06-13",
        "depart": None,
        "arrive": None,
        "arrive_date": "2021-06-13",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "SNA",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2021-09-18",
        "depart": None,
        "arrive": None,
        "arrive_date": "2021-09-18",
        "block_minutes": None,
        "origin": "SNA",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2021-10-02",
        "depart": None,
        "arrive": None,
        "arrive_date": "2021-10-02",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SNA",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2021-11-05",
        "depart": None,
        "arrive": None,
        "arrive_date": "2021-11-05",
        "block_minutes": None,
        "origin": "SNA",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2021-11-07",
        "depart": None,
        "arrive": None,
        "arrive_date": "2021-11-07",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SNA",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-02-20",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-02-20",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-02-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-02-27",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-06-23",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-06-23",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SAN",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-06-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-06-27",
        "block_minutes": None,
        "origin": "SAN",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-09-05",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-09-05",
        "block_minutes": None,
        "origin": "MIA",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-09-16",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-09-16",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "ATL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-10-07",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-10-07",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SNA",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-10-09",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-10-09",
        "block_minutes": None,
        "origin": "SNA",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-10-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-10-27",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-10-30",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-10-30",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-11-14",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-11-14",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "HAV",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-11-20",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-11-20",
        "block_minutes": None,
        "origin": "HAV",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-12-18",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-12-18",
        "block_minutes": None,
        "origin": "MEX",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2022-12-22",
        "depart": None,
        "arrive": None,
        "arrive_date": "2022-12-22",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2023-01-01",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-01-01",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2023-05-26",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-05-26",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SAN",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2023-05-29",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-05-29",
        "block_minutes": None,
        "origin": "SAN",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2023-11-22",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-11-22",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2023-11-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-11-27",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2023-12-06",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-12-06",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2023-12-10",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-12-10",
        "block_minutes": None,
        "origin": "GDL",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-01-11",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-01-11",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-01-18",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-01-18",
        "block_minutes": None,
        "origin": "GDL",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-03-12",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-03-12",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-03-17",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-03-17",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-03-30",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-03-30",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-04-13",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-04-13",
        "block_minutes": None,
        "origin": "GDL",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-07-04",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-07-04",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SAN",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-07-07",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-07-07",
        "block_minutes": None,
        "origin": "SAN",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-09-21",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-09-21",
        "block_minutes": None,
        "origin": "EZE",
        "destination": "IAH",
        "carrier": "UA",
        "note": "UA 818 -- no time on the MileagePlus activity export; arrival date assumed same-day, though a flight this long plausibly lands the next day local time",
        "layover": False,
    },
    {
        "date": "2024-09-23",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-09-23",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-09-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-09-27",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "SAN",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-09-29",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-09-29",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "EZE",
        "carrier": "UA",
        "note": "UA 819 -- no time on the MileagePlus activity export; arrival date assumed same-day, though a flight this long plausibly lands the next day local time",
        "layover": False,
    },
    {
        "date": "2024-09-29",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-09-29",
        "block_minutes": None,
        "origin": "SAN",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-11-23",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-11-23",
        "block_minutes": None,
        "origin": "EZE",
        "destination": "IAH",
        "carrier": "UA",
        "note": "UA 818 -- no time on the MileagePlus activity export; arrival date assumed same-day, though a flight this long plausibly lands the next day local time",
        "layover": False,
    },
    {
        "date": "2024-11-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-11-27",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-11-30",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-11-30",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2024-12-07",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-12-07",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "EZE",
        "carrier": "UA",
        "note": "UA 831 -- no time on the MileagePlus activity export; arrival date assumed same-day, though a flight this long plausibly lands the next day local time",
        "layover": False,
    },
    {
        "date": "2024-12-29",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-12-29",
        "block_minutes": None,
        "origin": "SDU",
        "destination": "GRU",
        "carrier": "AD",
        "note": "Azul flight 4311 -- domestic Brazil connection to Sao Paulo (GRU) on the way home from Rio de Janeiro; the outbound leg to Rio isn't in this activity export, layover, not a destination of its own",
        "layover": True,
    },
    {
        "date": "2024-12-29",
        "depart": None,
        "arrive": None,
        "arrive_date": "2024-12-29",
        "block_minutes": None,
        "origin": "GRU",
        "destination": "IAH",
        "carrier": "UA",
        "note": "UA 63 -- connects from the SDU-GRU Azul leg above, final leg home to Houston",
        "layover": False,
    },
    {
        "date": "2025-02-17",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-02-17",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SLC",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-02-21",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-02-21",
        "block_minutes": None,
        "origin": "SLC",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-04-24",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-04-24",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-04-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-04-27",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-07-27",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-07-27",
        "block_minutes": None,
        "origin": "BIO",
        "destination": "EWR",
        "carrier": "UA",
        "note": "UA 634 -- no time on the MileagePlus activity export; arrival date assumed same-day, though a flight this long plausibly lands the next day local time",
        "layover": False,
    },
    {
        "date": "2025-08-09",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-08-09",
        "block_minutes": None,
        "origin": "EWR",
        "destination": "HND",
        "carrier": "UA",
        "note": "UA 131 -- no time on the MileagePlus activity export; arrival date assumed same-day, though a flight this long plausibly lands the next day local time",
        "layover": False,
    },
    {
        "date": "2025-08-31",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-08-31",
        "block_minutes": None,
        "origin": "NRT",
        "destination": "IAH",
        "carrier": "UA",
        "note": "UA 6 -- no time on the MileagePlus activity export; arrival date assumed same-day, though a flight this long plausibly lands the next day local time",
        "layover": False,
    },
    {
        "date": "2025-10-23",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-10-23",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "SFO",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-10-26",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-10-26",
        "block_minutes": None,
        "origin": "SFO",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-11-11",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-11-11",
        "block_minutes": None,
        "origin": "SAN",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-11-30",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-11-30",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2025-12-25",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-12-25",
        "block_minutes": None,
        "origin": "GDL",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-01-01",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-01-01",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-01-12",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-01-12",
        "block_minutes": None,
        "origin": "GDL",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-01-31",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-01-31",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-02-13",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-02-13",
        "block_minutes": None,
        "origin": "GDL",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-02-15",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-02-15",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-07-03",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-07-03",
        "block_minutes": None,
        "origin": "GDL",
        "destination": "IAH",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-07-05",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-07-05",
        "block_minutes": None,
        "origin": "IAH",
        "destination": "GDL",
        "carrier": "UA",
        "note": "",
        "layover": False,
    },
    {
        "date": "2026-05-03",
        "depart": None,
        "arrive": None,
        "arrive_date": "2026-05-03",
        "block_minutes": None,
        "origin": "MEX",
        "destination": "GDL",
        "carrier": "AM",
        "note": "Aeromexico flight 218 -- from Ivan's Delta SkyMiles account activity (MQD "
                "earned for the flown leg, ticket# 0062404774201, certificate # "
                "0060900306685 redeemed 2026-02-14; the outbound leg isn't in this activity "
                "export, so only this return leg is logged), no times given",
        "layover": False,
    },
    {
        "date": "2026-11-08",
        "depart": "16:55",
        "arrive": "20:25",
        "arrive_date": "2026-11-08",
        "block_minutes": 270,
        "origin": "KIX",
        "destination": "HKG",
        "carrier": "CX",
        "note": "Cathay Pacific flight 561, Airbus A350-900, Economy Flex Class M -- from a "
                "confirmed booking screenshot. 270 min (4h30m) is the itinerary's own stated "
                "total duration, not the 3h30m wall-clock diff -- Hong Kong is 1 hour behind "
                "Osaka. Mid-trip leg on the LAX-HND...HKG-SFO Asia trip already logged.",
        "layover": False,
    },
    {
        "date": "2025-07-04",
        "depart": None,
        "arrive": None,
        "arrive_date": "2025-07-04",
        "block_minutes": None,
        "origin": "BCN",
        "destination": "ATL",
        "carrier": "DL",
        "note": "Delta ticket# 0062345531843 -- from a receipt with no flight number and no "
                "times given. BCN-ATL is a Delta mainline route (not a marked codeshare), "
                "logged as Delta as ticketed.",
        "layover": False,
    },
    {
        "date": "2023-09-16",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-09-16",
        "block_minutes": None,
        "origin": "ATL",
        "destination": "ORD",
        "carrier": "DL",
        "note": "No flight number or times given.",
        "layover": False,
    },
    {
        "date": "2023-09-19",
        "depart": None,
        "arrive": None,
        "arrive_date": "2023-09-19",
        "block_minutes": None,
        "origin": "ORD",
        "destination": "IAH",
        "carrier": "UA",
        "note": "No flight number or times given.",
        "layover": False,
    },
    {
        "date": "2022-09-19",
        "depart": "08:20",
        "arrive": "09:57",
        "arrive_date": "2022-09-19",
        "block_minutes": 97,
        "origin": "ATL",
        "destination": "PIT",
        "carrier": "DL",
        "note": "Delta flight 2074, seat 34C.",
        "layover": False,
    },
    {
        "date": "2022-09-20",
        "depart": "17:59",
        "arrive": "19:45",
        "arrive_date": "2022-09-20",
        "block_minutes": 106,
        "origin": "PIT",
        "destination": "ATL",
        "carrier": "DL",
        "note": "Delta flight 2770, seat 31D -- layover, final destination is Houston "
                "(Hobby) (see the ATL-HOU leg).",
        "layover": True,
    },
    {
        "date": "2022-09-20",
        "depart": "20:55",
        "arrive": "21:58",
        "arrive_date": "2022-09-20",
        "block_minutes": 123,
        "origin": "ATL",
        "destination": "HOU",
        "carrier": "DL",
        "note": "Delta flight 2201, seat 27D -- lands at Houston's Hobby (HOU), not the "
                "usual IAH. 123 min (2h03m) accounts for Houston being 1 hour behind "
                "Atlanta, not the 63-minute wall-clock diff.",
        "layover": False,
    },
    {
        "date": "2025-06-09",
        "depart": "09:15",
        "arrive": "12:50",
        "arrive_date": "2025-06-09",
        "block_minutes": 155,
        "origin": "DUB",
        "destination": "MAD",
        "carrier": "IB",
        "note": "Iberia flight 1882. 155 min (2h35m) accounts for Madrid being 1 hour "
                "ahead of Dublin, not the 215-minute wall-clock diff.",
        "layover": False,
    },
    {
        "date": "2025-07-13",
        "depart": "08:00",
        "arrive": "09:20",
        "arrive_date": "2025-07-13",
        "block_minutes": 80,
        "origin": "VLC",
        "destination": "BIO",
        "carrier": "IB",
        "note": "Iberia flight 2312.",
        "layover": False,
    },
]

CSV_FIELDS = [
    "leg",
    "trip_id",
    "traveler_name",
    "start_date",
    "depart_local",
    "end_date",
    "arrive_local",
    "block_minutes",
    "duration_days",
    "origin_airport",
    "origin_city",
    "origin_country",
    "destination_airport",
    "destination_airport_name",
    "destination_city",
    "destination_country",
    "destination_lat",
    "destination_lng",
    "carrier_code",
    "distance_km",
    "is_domestic",
    "layover",
    "notes",
]


def load_route_facts(origin, destination):
    """(distance_km, is_domestic, carriers) for one route, or (None, None, [])
    when airline_routes_enhanced.csv has never seen it. A missing route is NOT
    fatal here: the log records a flight that was actually taken, and a route
    file that doesn't know about it is the route file's gap, not the log's."""
    distance = domestic = None
    carriers = []
    with ROUTES_PATH.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["Departure"] != origin or row["Destination"] != destination:
                continue
            carriers.append(row["Airline ID"])
            if distance is None and row.get("distance_km"):
                distance = float(row["distance_km"])
            if domestic is None and row.get("is_domestic"):
                domestic = int(row["is_domestic"])
    return distance, domestic, sorted(set(carriers))


def build_rows():
    airports = load_airports()
    rows, warnings = [], []

    for index, leg in enumerate(FLIGHTS, start=1):
        origin, destination = leg["origin"], leg["destination"]
        start = date.fromisoformat(leg["date"])
        end = date.fromisoformat(leg.get("arrive_date") or leg["date"])
        distance, domestic, carriers = load_route_facts(origin, destination)

        for code in (origin, destination):
            if code not in airports:
                warnings.append(f"{code} is not in airports.json -- no city, country or coordinates")
        if leg["carrier"] and carriers and leg["carrier"] not in carriers:
            # Not an error: the route file is a snapshot and the log is the
            # truth. Worth saying out loud, though -- it usually means a typo
            # in the code, and occasionally means the route data is stale.
            warnings.append(
                f"leg {index}: {leg['carrier']} is not listed on {origin}-{destination} "
                f"in {ROUTES_PATH.name} (it lists {', '.join(carriers) or 'nobody'})"
            )

        origin_airport = airports.get(origin, {})
        destination_airport = airports.get(destination, {})
        rows.append({
            "leg": index,
            # Prefix + date, matching every other traveler in this project.
            # build_gomez_traveler.py suffixes a repeat, which is what two
            # legs on one day would be.
            "trip_id": f"EG-{leg['date']}",
            "traveler_name": TRAVELER["traveler_name"],
            "start_date": leg["date"],
            "depart_local": leg["depart"],
            "end_date": end.isoformat(),
            "arrive_local": leg["arrive"],
            "block_minutes": leg["block_minutes"],
            "duration_days": (end - start).days,
            "origin_airport": origin,
            "origin_city": origin_airport.get("city"),
            "origin_country": origin_airport.get("country"),
            "destination_airport": destination,
            "destination_airport_name": destination_airport.get("name", ""),
            "destination_city": destination_airport.get("city"),
            "destination_country": destination_airport.get("country"),
            "destination_lat": destination_airport.get("lat"),
            "destination_lng": destination_airport.get("lng"),
            "carrier_code": leg["carrier"],
            "distance_km": distance,
            "is_domestic": domestic,
            # Real leg, still recorded in full -- just not the point of the
            # journey. Downstream scripts (build_travelers.py's trip_count,
            # compute_traveler_tags.py's airline share, compute_traveler_
            # entropy.py's destination counts) exclude layover=true rows from
            # "places visited" and "trips taken", by Ivan's call -- see
            # gomez_flight_log.md. The raw log keeps every leg regardless.
            "layover": bool(leg.get("layover", False)),
            "notes": leg.get("note", ""),
        })

    return rows, warnings


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()

    rows, warnings = build_rows()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_CSV_PATH.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "source": "hand-kept flight log -- legs typed in from itineraries, not derived "
                  "from any published dataset",
        "generated": date.today().isoformat(),
        "note": "REAL trips for a real person under a pseudonym. The legs, dates, times, "
                "airports and airlines are as flown. No age, gender or nationality is "
                "recorded, and costs are null -- nothing here is invented.",
        "traveler": TRAVELER,
        "declared_base": DECLARED_BASE,
        "counts": {"legs": len(rows)},
        "legs": rows,
    }
    with OUT_JSON_PATH.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")

    print(f"Wrote {len(rows)} leg(s) to {OUT_CSV_PATH}")
    print(f"Wrote {len(rows)} leg(s) to {OUT_JSON_PATH}")
    for row in rows:
        overnight = " (lands next day)" if row["end_date"] != row["start_date"] else ""
        layover = " (layover)" if row["layover"] else ""
        print(f"  {row['start_date']} {row['depart_local']} {row['origin_airport']}->"
              f"{row['destination_airport']} {row['arrive_local']}{overnight}  "
              f"{row['carrier_code']}  {row['block_minutes']}m  "
              f"{row['destination_city']}, {row['destination_country']}{layover}")
    for warning in warnings:
        print(f"WARNING -- {warning}")


if __name__ == "__main__":
    main()
