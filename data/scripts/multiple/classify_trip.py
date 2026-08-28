"""Ski season windows by arrival airport."""

import pandas as pd

# MM-DD, so the window is year-agnostic and wraps the new year.
# Approximate typical opening/closing, not published resort calendars.
SKI_SEASONS = {
    # Colorado
    "DEN": {"Ski Season Start": "10-15", "Ski Season End": "06-01"},
    "EGE": {"Ski Season Start": "11-15", "Ski Season End": "04-20"},
    "ASE": {"Ski Season Start": "11-25", "Ski Season End": "04-20"},
    "MTJ": {"Ski Season Start": "11-25", "Ski Season End": "04-06"},
    "HDN": {"Ski Season Start": "11-25", "Ski Season End": "04-13"},
    "GUC": {"Ski Season Start": "11-25", "Ski Season End": "04-06"},
    "GJT": {"Ski Season Start": "12-10", "Ski Season End": "03-30"},
    "COS": {"Ski Season Start": "11-20", "Ski Season End": "04-06"},
    # Wyoming / Utah / Idaho
    "JAC": {"Ski Season Start": "11-25", "Ski Season End": "04-06"},
    "SLC": {"Ski Season Start": "11-20", "Ski Season End": "04-20"},
    "PVU": {"Ski Season Start": "11-20", "Ski Season End": "04-13"},
    "SUN": {"Ski Season Start": "11-25", "Ski Season End": "04-13"},
    "BOI": {"Ski Season Start": "12-01", "Ski Season End": "04-06"},
}

SKI_SEASONS_DF = (
    pd.DataFrame.from_dict(SKI_SEASONS, orient="index")
    .rename_axis("Airport")
    .reset_index()
)

# Arrival Date is the trip's start date -- these are same-day flights.
#
# Charlie Brown / Calvin / Garfield: ski trips, from skiers_traveler.json
# (build_skiers_trips.py).
# Clark Kent: Cancun, from trips_enhanced.json. He flies HOU-CUN every
# February and September; the February legs are here on purpose -- they fall
# inside the ski-season date window but land at an airport that isn't in it,
# and Clark-Kent-Cancun-2024 shares an exact arrival date with
# Charlie-Brown-Vail-2024. Anything keying off the date alone will call these
# ski trips.
TEST_TRIPS = {
    "Charlie-Brown-Vail-2024": {"Destination Airport": "EGE", "Arrival Date": "2024-02-10"},
    "Charlie-Brown-Aspen-2025": {"Destination Airport": "ASE", "Arrival Date": "2025-02-08"},
    "Charlie-Brown-Vail-2026": {"Destination Airport": "EGE", "Arrival Date": "2026-02-07"},
    "Clark-Kent-Cancun-2023": {"Destination Airport": "CUN", "Arrival Date": "2023-02-11"},
    "Clark-Kent-Cancun-2024": {"Destination Airport": "CUN", "Arrival Date": "2024-02-10"},
    "Clark-Kent-Cancun-2025": {"Destination Airport": "CUN", "Arrival Date": "2025-02-08"},
    "Calvin-JacksonHole-2024": {"Destination Airport": "JAC", "Arrival Date": "2024-01-06"},
    "Calvin-SaltLakeCity-2024": {"Destination Airport": "SLC", "Arrival Date": "2024-03-09"},
    "Garfield-JacksonHole-2026": {"Destination Airport": "JAC", "Arrival Date": "2026-03-21"},
}

TEST_TRIPS_DF = (
    pd.DataFrame.from_dict(TEST_TRIPS, orient="index")
    .rename_axis("Trip ID")
    .reset_index()
)


if __name__ == "__main__":
    print(SKI_SEASONS_DF.to_string(index=False))
    print()
    print(TEST_TRIPS_DF.to_string(index=False))
