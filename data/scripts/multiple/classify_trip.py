"""Trip classifiers: ski season, and beach vacation."""

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent.parent
SHORELINES_PATH = DATA_DIR / "processed" / "multiple" / "shorelines.csv"
BEACHES_PATH = DATA_DIR / "processed" / "multiple" / "geonames_beaches.csv"
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
WEATHER_PATH = DATA_DIR / "processed" / "multiple" / "weather_normals_2025_by_city.json"
CITY_MATCHES_PATH = DATA_DIR / "processed" / "multiple" / "trip_city_matches.json"

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

# Arrival Date is the outbound flight's date, Departure Date the return's.
# Destination City/Country are what the weather join keys on -- see
# _trip_mean_temp_c(); they're the trip's own values, not derived here.
TEST_TRIPS = {
    "Charlie-Brown-Vail-2024": {
        "Destination Airport": "EGE", "Arrival Date": "2024-02-10", "Departure Date": "2024-02-17",
        "Destination City": "Vail", "Destination Country": "United States"},
    "Charlie-Brown-Aspen-2025": {
        "Destination Airport": "ASE", "Arrival Date": "2025-02-08", "Departure Date": "2025-02-15",
        "Destination City": "Aspen", "Destination Country": "United States"},
    "Clark-Kent-Cancun-2023": {
        "Destination Airport": "CUN", "Arrival Date": "2023-02-11", "Departure Date": "2023-02-18",
        "Destination City": "Cancun", "Destination Country": "Mexico"},
    "Clark-Kent-Cancun-2024": {
        "Destination Airport": "CUN", "Arrival Date": "2024-02-10", "Departure Date": "2024-02-17",
        "Destination City": "Cancun", "Destination Country": "Mexico"},
    "Clark-Kent-Cancun-2025": {
        "Destination Airport": "CUN", "Arrival Date": "2025-02-08", "Departure Date": "2025-02-15",
        "Destination City": "Cancun", "Destination Country": "Mexico"},
    "Calvin-JacksonHole-2024": {
        "Destination Airport": "JAC", "Arrival Date": "2024-01-06", "Departure Date": "2024-01-13",
        "Destination City": "Jacksn Hole", "Destination Country": "United States"},
    "Calvin-SaltLakeCity-2024": {
        "Destination Airport": "SLC", "Arrival Date": "2024-03-09", "Departure Date": "2024-03-16",
        "Destination City": "Salt Lake City", "Destination Country": "United States"},
    "Garfield-JacksonHole-2026": {
        "Destination Airport": "JAC", "Arrival Date": "2026-03-21", "Departure Date": "2026-03-28",
        "Destination City": "Jacksn Hole", "Destination Country": "United States"},
    "Rymel-Hawaii-2020": {
        "Destination Airport": "HNL", "Arrival Date": "2020-02-08", "Departure Date": "2020-02-15",
        "Destination City": "Honolulu", "Destination Country": "United States"},
    "Rymel-Iceland-2026": {
        "Destination Airport": "KEF", "Arrival Date": "2026-08-08", "Departure Date": "2026-08-15",
        "Destination City": "Reykjavik", "Destination Country": "Iceland"},
    # Invented, not from the dataset: every real row above sits far from the
    # 80% ski line, so without these two nothing exercises that threshold.
    "Boundary-GJT-over-2026": {
        "Destination Airport": "GJT", "Arrival Date": "2026-03-24", "Departure Date": "2026-03-31",
        "Destination City": "Grand Junction", "Destination Country": "United States"},
    "Boundary-GJT-under-2026": {
        "Destination Airport": "GJT", "Arrival Date": "2026-03-25", "Departure Date": "2026-04-01",
        "Destination City": "Grand Junction", "Destination Country": "United States"},
}

TEST_TRIPS_DF = (
    pd.DataFrame.from_dict(TEST_TRIPS, orient="index")
    .rename_axis("Trip ID")
    .reset_index()
)

SKI_TRIP_THRESHOLD = 0.8
NEAR_SHORE_KM = 100
NEAR_BEACH_KM = 100
BEACH_MIN_TEMP_C = 23.0
EARTH_RADIUS_KM = 6371.0088

MONTHS = ["january", "february", "march", "april", "may", "june",
          "july", "august", "september", "october", "november", "december"]


# --------------------------------------------------------------------------
# Ski season
# --------------------------------------------------------------------------

def _to_mmdd(value):
    month, day = str(value).split("-")
    return int(month) * 100 + int(day)


def _in_window(mmdd, start, end):
    # A season that wraps the new year has start > end (Nov -> Apr), so
    # membership is "after the start OR before the end". A southern-hemisphere
    # season (Jun -> Sep) doesn't wrap and is the plain between.
    if start <= end:
        return start <= mmdd <= end
    return mmdd >= start or mmdd <= end


def _share_in_season(row):
    if pd.isna(row["Ski Season Start"]) or pd.isna(row["Ski Season End"]):
        return 0.0
    start, end = _to_mmdd(row["Ski Season Start"]), _to_mmdd(row["Ski Season End"])
    days = pd.date_range(row["Arrival Date"], row["Departure Date"], freq="D")
    if len(days) == 0:
        return 0.0
    inside = sum(_in_window(d.month * 100 + d.day, start, end) for d in days)
    return inside / len(days)


def is_ski_trip(df, seasons=SKI_SEASONS_DF, threshold=SKI_TRIP_THRESHOLD):
    """Left join the season windows onto `df` and flag each trip.

    IS_SKI_TRIP is its own 0/1 column rather than a category: a trip can be
    several things at once, and a July trip to Chile should be able to come
    back both a ski trip and summer travel.
    """
    merged = df.merge(seasons, how="left", left_on="Destination Airport", right_on="Airport")
    merged["Share In Season"] = merged.apply(_share_in_season, axis=1)
    merged["IS_SKI_TRIP"] = (merged["Share In Season"] >= threshold).astype(int)
    return merged


# --------------------------------------------------------------------------
# Beach vacation
# --------------------------------------------------------------------------

def _load_points(path, lat_key="lat", lon_key="lon"):
    with open(path, encoding="utf-8", newline="") as fh:
        pts = np.array([[float(r[lat_key]), float(r[lon_key])] for r in csv.DictReader(fh)])
    return np.radians(pts[:, 0]), np.radians(pts[:, 1])


def load_shorelines(path=SHORELINES_PATH):
    return _load_points(path)


def load_beaches(path=BEACHES_PATH):
    """Beaches only -- a strict subset of shorelines.csv, which also carries
    the NetCDF transects. That subset relationship is why the shore test can
    never fail while the beach test passes; see is_beach_vacation()."""
    return _load_points(path)


def load_airport_coords(path=AIRPORTS_PATH):
    with open(path, encoding="utf-8") as fh:
        airports = json.load(fh)["airports"]
    return {a["iata"]: (a["lat"], a["lng"]) for a in airports if a.get("iata")}


def load_weather():
    """(city_id -> months, "City|Country" -> city_id).

    The city id comes from trip_city_matches.json, which is the project's own
    destination-to-city resolution (match_trip_cities.py) -- this does no name
    matching of its own. Both files are optional: without them every trip
    simply has no temperature, and BEACH_VACATION falls to 0.
    """
    if not WEATHER_PATH.exists() or not CITY_MATCHES_PATH.exists():
        return {}, {}
    with open(WEATHER_PATH, encoding="utf-8") as fh:
        cities = json.load(fh)["cities"]
    with open(CITY_MATCHES_PATH, encoding="utf-8") as fh:
        matches = json.load(fh)["by_destination"]
    by_destination = {k: v.get("simplemaps_id") for k, v in matches.items() if v.get("simplemaps_id")}
    return cities, by_destination


def _min_distance_km(lat, lon, points_lat, points_lon):
    p, l = np.radians(lat), np.radians(lon)
    hav = (np.sin((points_lat - p) / 2) ** 2
           + np.cos(p) * np.cos(points_lat) * np.sin((points_lon - l) / 2) ** 2)
    return float((EARTH_RADIUS_KM * 2 * np.arcsin(np.sqrt(hav))).min())


def _trip_mean_temp_c(city_months, arrival, departure):
    """Mean temperature over the trip's days, in Celsius.

    MEAN, not high. The source gives avg_high_c and avg_low_c per month, and
    "average temperature" is the midpoint of those -- which is a stricter test
    than avg_high and the honest reading of the brief. Averaging per DAY
    rather than per month weights a trip that straddles a month boundary by
    how much of it fell on each side.
    """
    days = pd.date_range(arrival, departure, freq="D")
    if len(days) == 0:
        return None
    temps = []
    for day in days:
        month = city_months.get(MONTHS[day.month - 1])
        if not month:
            continue
        high, low = month.get("avg_high_c"), month.get("avg_low_c")
        if high is None or low is None:
            continue
        temps.append((high + low) / 2)
    return sum(temps) / len(temps) if temps else None


def is_beach_vacation(df, shore_km=NEAR_SHORE_KM, beach_km=NEAR_BEACH_KM,
                      min_temp_c=BEACH_MIN_TEMP_C):
    """Three conditions, all required: near a shore, near a beach, and warm.

    NOTE ON THE FIRST TWO. geonames_beaches.csv is a strict subset of
    shorelines.csv, so distance-to-shore is always <= distance-to-beach and
    the beach test therefore implies the shore test. Both are computed and
    reported anyway: they are separate questions ("is there coast here" vs
    "is there a beach here"), they will diverge the moment a shoreline source
    is added that isn't beaches, and a reader comparing the two columns
    learns something -- a rocky coast shows a small shore distance and a large
    beach one.

    TEMPERATURE IS THE BINDING CONSTRAINT, and it is missing more often than
    the geography is. Weather normals exist for 1,770 cities; a destination
    that doesn't resolve to one of them has no temperature and scores 0 here.
    That is a false negative, not a cold destination -- Honolulu is one. The
    "Weather Coverage" column separates the two so the zero can be read
    correctly.
    """
    shore_lat, shore_lon = load_shorelines()
    beach_lat, beach_lon = load_beaches()
    coords = load_airport_coords()
    weather_cities, city_by_destination = load_weather()

    # Distances are per AIRPORT, not per trip: ~200 distinct airports against
    # 2,459 trips, and an airport does not move between trips.
    shore_cache, beach_cache = {}, {}

    shore_d, beach_d, temps, coverage = [], [], [], []
    for _, row in df.iterrows():
        code = row["Destination Airport"]
        if code in coords:
            if code not in shore_cache:
                lat, lon = coords[code]
                shore_cache[code] = round(_min_distance_km(lat, lon, shore_lat, shore_lon), 1)
                beach_cache[code] = round(_min_distance_km(lat, lon, beach_lat, beach_lon), 1)
            shore_d.append(shore_cache[code])
            beach_d.append(beach_cache[code])
        else:
            shore_d.append(np.nan)
            beach_d.append(np.nan)

        key = f"{row.get('Destination City')}|{row.get('Destination Country')}"
        city_id = city_by_destination.get(key)
        months = (weather_cities.get(city_id) or {}).get("months") if city_id else None
        if months:
            temp = _trip_mean_temp_c(months, row["Arrival Date"], row["Departure Date"])
            temps.append(round(temp, 1) if temp is not None else np.nan)
            coverage.append("ok" if temp is not None else "no monthly normals")
        else:
            temps.append(np.nan)
            coverage.append("no weather for destination")

    out = df.copy()
    out["Distance To Shore KM"] = shore_d
    out["Distance To Beach KM"] = beach_d
    out["Avg Trip Temp C"] = temps
    out["Weather Coverage"] = coverage
    out["BEACH_VACATION"] = (
        (out["Distance To Shore KM"] <= shore_km)
        & (out["Distance To Beach KM"] <= beach_km)
        & (out["Avg Trip Temp C"] >= min_temp_c)
    ).fillna(False).astype(int)
    return out


def classify(df):
    """Every classifier, each adding its own independent flag column."""
    return is_beach_vacation(is_ski_trip(df))


# --------------------------------------------------------------------------
# Production entry point
# --------------------------------------------------------------------------

# One entry per flag column. Shape mirrors compute_traveler_tags.py's tags so
# a trip chip and a traveler chip are the same kind of object to the UI.
TRIP_TAGS = {
    "IS_SKI_TRIP": {"kind": "ski_trip", "tag_id": "ski-trip", "label": "Ski Trip"},
    "BEACH_VACATION": {"kind": "beach_vacation", "tag_id": "beach-vacation", "label": "Beach Vacation"},
}


def tag_trips(trips):
    """Tags for each trip record, aligned with `trips`.

    Takes the trip dicts build_trips_enhanced.py assembles and returns a list
    of tag lists, one per input trip. A trip with no destination airport or no
    parsed dates gets an empty list rather than a guess -- the 137 Kaggle rows
    have no airport, and a tag there would assert something the source never
    made.
    """
    rows, positions = [], []
    for i, trip in enumerate(trips):
        airport = trip.get("destination_airport")
        start, end = trip.get("start_date"), trip.get("end_date")
        if not airport or not start or not end:
            continue
        rows.append({"Trip ID": trip.get("trip_id") or f"row-{i}",
                     "Destination Airport": airport,
                     "Arrival Date": start,
                     "Departure Date": end,
                     "Destination City": trip.get("destination_city"),
                     "Destination Country": trip.get("destination_country")})
        positions.append(i)

    tags = [[] for _ in trips]
    if not rows:
        return tags

    classified = classify(pd.DataFrame(rows))
    for position, (_, row) in zip(positions, classified.iterrows()):
        tags[position] = [dict(TRIP_TAGS[flag]) for flag in TRIP_TAGS if row[flag] == 1]
    return tags


if __name__ == "__main__":
    print(SKI_SEASONS_DF.to_string(index=False))
    print()
    result = classify(TEST_TRIPS_DF)
    columns = ["Trip ID", "Destination Airport", "Arrival Date", "Departure Date",
               "Share In Season", "IS_SKI_TRIP",
               "Distance To Shore KM", "Distance To Beach KM", "Avg Trip Temp C",
               "BEACH_VACATION", "Weather Coverage"]
    print(result[columns].to_string(index=False))
