"""Trip classifiers: ski season, and beach vacation."""

import csv
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

DATA_DIR = Path(__file__).resolve().parent.parent.parent
SHORELINES_PATH = DATA_DIR / "processed" / "multiple" / "shorelines.csv"
BEACHES_PATH = DATA_DIR / "processed" / "multiple" / "geonames_beaches.csv"
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
WEATHER_PATH = DATA_DIR / "processed" / "multiple" / "weather_normals_2025_by_city.json"
CITY_MATCHES_PATH = DATA_DIR / "processed" / "multiple" / "trip_city_matches.json"
M49_PATH = DATA_DIR / "reference" / "m49_regions.json"

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
# _trip_avg_high_c(); they're the trip's own values, not derived here.
TEST_TRIPS = {
    "Gardner-Vail-2024": {
        "Destination Airport": "EGE", "Arrival Date": "2024-02-10", "Departure Date": "2024-02-17",
        "Destination City": "Vail", "Destination Country": "United States"},
    "Gardner-Aspen-2025": {
        "Destination Airport": "ASE", "Arrival Date": "2025-02-08", "Departure Date": "2025-02-15",
        "Destination City": "Aspen", "Destination Country": "United States"},
    "Valentini-Cancun-2023": {
        "Destination Airport": "CUN", "Arrival Date": "2023-02-11", "Departure Date": "2023-02-18",
        "Destination City": "Cancun", "Destination Country": "Mexico"},
    "Valentini-Cancun-2024": {
        "Destination Airport": "CUN", "Arrival Date": "2024-02-10", "Departure Date": "2024-02-17",
        "Destination City": "Cancun", "Destination Country": "Mexico"},
    "Valentini-Cancun-2025": {
        "Destination Airport": "CUN", "Arrival Date": "2025-02-08", "Departure Date": "2025-02-15",
        "Destination City": "Cancun", "Destination Country": "Mexico"},
    "Moretti-JacksonHole-2024": {
        "Destination Airport": "JAC", "Arrival Date": "2024-01-06", "Departure Date": "2024-01-13",
        "Destination City": "Jacksn Hole", "Destination Country": "United States"},
    "Moretti-SaltLakeCity-2024": {
        "Destination Airport": "SLC", "Arrival Date": "2024-03-09", "Departure Date": "2024-03-16",
        "Destination City": "Salt Lake City", "Destination Country": "United States"},
    "Clyne-JacksonHole-2026": {
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
    # European Summer, both halves of the rule and both edges of the window.
    # Only these rows carry a country code -- the region join needs one, and
    # every case above predates it, so they all correctly score 0.
    "EuroSummer-Paris-July": {          # in region, in window          -> 1
        "Destination Airport": "CDG", "Arrival Date": "2025-07-10", "Departure Date": "2025-07-20",
        "Destination City": "Paris", "Destination Country": "France",
        "Destination Country Code": "FR"},
    "EuroSummer-Paris-September": {     # in region, OUT of window      -> 0
        "Destination Airport": "CDG", "Arrival Date": "2025-09-10", "Departure Date": "2025-09-20",
        "Destination City": "Paris", "Destination Country": "France",
        "Destination Country Code": "FR"},
    "EuroSummer-Barcelona-July": {      # in window, SOUTHERN Europe    -> 0
        "Destination Airport": "BCN", "Arrival Date": "2025-07-10", "Departure Date": "2025-07-20",
        "Destination City": "Barcelona", "Destination Country": "Spain",
        "Destination Country Code": "ES"},
    "EuroSummer-London-July": {         # in window, NORTHERN Europe    -> 0
        "Destination Airport": "LHR", "Arrival Date": "2025-07-10", "Departure Date": "2025-07-20",
        "Destination City": "London", "Destination Country": "United Kingdom",
        "Destination Country Code": "GB"},
    "EuroSummer-Amsterdam-Aug31": {     # last day in                   -> 1
        "Destination Airport": "AMS", "Arrival Date": "2025-08-31", "Departure Date": "2025-09-07",
        "Destination City": "Amsterdam", "Destination Country": "Netherlands",
        "Destination Country Code": "NL"},
    "EuroSummer-Amsterdam-Sep1": {      # first day out                 -> 0
        "Destination Airport": "AMS", "Arrival Date": "2025-09-01", "Departure Date": "2025-09-08",
        "Destination City": "Amsterdam", "Destination Country": "Netherlands",
        "Destination Country Code": "NL"},
    "EuroSummer-Munich-Jun1": {         # first day in                  -> 1
        "Destination Airport": "MUC", "Arrival Date": "2025-06-01", "Departure Date": "2025-06-08",
        "Destination City": "Munich", "Destination Country": "Germany",
        "Destination Country Code": "DE"},
}

TEST_TRIPS_DF = (
    pd.DataFrame.from_dict(TEST_TRIPS, orient="index")
    .rename_axis("Trip ID")
    .reset_index()
)

# European Summer: a fixed calendar window in one M49 detailed region.
#
# WESTERN EUROPE HERE MEANS M49's WESTERN EUROPE, which is narrower than the
# phrase usually implies -- Austria, Belgium, France, Germany, Liechtenstein,
# Luxembourg, Monaco, Netherlands, Switzerland. Spain, Italy, Portugal and
# Greece are SOUTHERN Europe; the UK and Ireland are NORTHERN. That was a
# deliberate call: the alternatives (Western + Southern, or all of Europe)
# were measured at 137 and 179 trips against this rule's 59, and the strict
# region was chosen. Widen by adding to EUROPEAN_SUMMER_REGIONS -- the region
# names come from build_m49_regions.py, so they cannot drift from the values
# every other part of this project charts.
#
# The DATES are fixed rather than per-destination, unlike SKI_SEASONS above.
# A ski season is a property of a mountain; a European summer is a property of
# the calendar, so there is nothing per-city to look up.
EUROPEAN_SUMMER_REGIONS = frozenset({"Western Europe"})
EUROPEAN_SUMMER_START = "06-01"
EUROPEAN_SUMMER_END = "08-31"

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


def _trip_avg_high_c(city_months, arrival, departure):
    """Average daily HIGH over the trip's days, in Celsius.

    THE HIGH, NOT THE MIDPOINT. Ivan's call, and it is the question a
    traveller actually asks -- "does it get warm enough for the beach"
    happens in the afternoon, not at 5am. The midpoint of high and low reads
    colder than the day feels: Honolulu in February averages a 26.3C high and
    an 18.5C low, so it fails a 23C test on the midpoint (22.4) and passes
    comfortably on the high.

    Averaged per DAY rather than per month, so a trip straddling a month
    boundary is weighted by how much of it fell on each side.
    """
    days = pd.date_range(arrival, departure, freq="D")
    if len(days) == 0:
        return None
    highs = []
    for day in days:
        month = city_months.get(MONTHS[day.month - 1])
        if not month:
            continue
        high = month.get("avg_high_c")
        if high is None:
            continue
        highs.append(high)
    return sum(highs) / len(highs) if highs else None


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

    TEMPERATURE IS THE AVERAGE DAILY HIGH over the trip, not the midpoint of
    high and low -- see _trip_avg_high_c(). It is still the binding
    constraint, and it is missing more often than the geography is. Weather normals exist for 1,770 cities; a destination
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
            temp = _trip_avg_high_c(months, row["Arrival Date"], row["Departure Date"])
            temps.append(round(temp, 1) if temp is not None else np.nan)
            coverage.append("ok" if temp is not None else "no monthly normals")
        else:
            temps.append(np.nan)
            coverage.append("no weather for destination")

    out = df.copy()
    out["Distance To Shore KM"] = shore_d
    out["Distance To Beach KM"] = beach_d
    out["Avg Trip High C"] = temps
    out["Weather Coverage"] = coverage
    out["BEACH_VACATION"] = (
        (out["Distance To Shore KM"] <= shore_km)
        & (out["Distance To Beach KM"] <= beach_km)
        & (out["Avg Trip High C"] >= min_temp_c)
    ).fillna(False).astype(int)
    return out


def load_m49_regions(path=M49_PATH):
    """iso2 -> M49 detailed region, or {} when the file has not been built.

    Empty rather than raising: m49_regions.json comes from build_m49_regions.py
    and a checkout may not have run it. A missing file then means no European
    Summer tags, which is the same shape of degradation the other classifiers
    already have when their reference data is absent."""
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    regions = {}
    for entry in list((payload.get("countries") or {}).values()) + \
            list((payload.get("additions") or {}).values()):
        # iso2 is checked for None, not falsiness -- Namibia's code is the
        # string "NA", which is truthy but has been a NaN upstream before.
        if entry.get("iso2") is not None and entry.get("detailed_region"):
            regions[entry["iso2"].upper()] = entry["detailed_region"]
    return regions


def is_european_summer(df, regions=None, wanted=EUROPEAN_SUMMER_REGIONS,
                       start=EUROPEAN_SUMMER_START, end=EUROPEAN_SUMMER_END):
    """Did the trip START inside the summer window, somewhere in the region set?

    Both halves must hold. "Region Matched" records which one qualified, so a 1
    can always be explained -- the same convention is_holiday_trip() uses for
    "Holiday Matched".

    KEYED ON THE ARRIVAL DATE, not on overlap. A trip that starts 28 August and
    runs into September counts; one that starts 2 September does not, even if
    it was booked as a summer holiday. That is the rule as specified, and it is
    the one a reader can check against a single column."""
    regions = load_m49_regions() if regions is None else regions
    out = df.copy()

    if "Destination Country Code" in out.columns:
        matched = out["Destination Country Code"].map(
            lambda code: regions.get(str(code).upper()) if code else None)
    else:
        matched = pd.Series([None] * len(out), index=out.index)

    in_region = matched.isin(wanted)
    # _to_mmdd() parses an "MM-DD" season boundary, not a full ISO date -- the
    # arrival is a real timestamp, so its month/day are read directly, the same
    # way _share_in_season() does it.
    arrival = pd.to_datetime(out["Arrival Date"], errors="coerce")
    in_window = arrival.apply(
        lambda d: _in_window(d.month * 100 + d.day, _to_mmdd(start), _to_mmdd(end))
        if pd.notna(d) else False)

    out["Region Matched"] = matched.where(in_region & in_window)
    out["EUROPEAN_SUMMER"] = (in_region & in_window).astype(int)
    return out


def classify(df):
    """Every classifier, each adding its own independent flag column."""
    return is_european_summer(is_holiday_trip(is_beach_vacation(is_ski_trip(df))))


# --------------------------------------------------------------------------
# Holiday trip
# --------------------------------------------------------------------------

# Thanksgiving is only a reason to travel where it is observed, and the two
# countries that observe it do so on DIFFERENT DAYS: the US on the fourth
# Thursday of November, Canada on the second Monday of October, six weeks
# earlier. Each country is therefore tested against its own date -- a trip to
# Toronto qualifies over Canadian Thanksgiving, a trip to New York over the
# American one, and neither qualifies on the other's date.
THANKSGIVING_COUNTRIES = frozenset({"United States", "Canada"})

# Countries where DECEMBER 25 IS A PUBLIC HOLIDAY, keyed by the country names
# build_trips_enhanced.py writes (which come from its own hand-written table,
# so they are a controlled vocabulary rather than free text).
#
# HAND-MAINTAINED AND WORTH REVIEWING. This is a judgement per country, not a
# fetched dataset. It covers exactly the 95 destination countries currently in
# trips_enhanced.json; a country absent from this set is NOT tagged, so a new
# destination fails safe rather than being assumed Christian-calendar.
#
# DELIBERATELY EXCLUDED, with the reason:
#   Dec 25 not a public holiday: Bhutan, Cambodia, China (mainland; Hong Kong
#     IS included), Iran, Israel, Japan, Laos, Libya, Morocco, Oman, Qatar,
#     Saudi Arabia, Taiwan, Thailand, Turkey, United Arab Emirates,
#     Uzbekistan, Vietnam.
#   Orthodox/other calendar -- Christmas is observed, but NOT on Dec 25:
#     Armenia (Jan 6), Egypt (Jan 7, Coptic), Ethiopia (Jan 7, Genna),
#     Georgia (Jan 7), Russia (Jan 7). These are the ones most likely to be
#     wrong for your purposes: the country plainly celebrates Christmas, just
#     not inside a Dec 25 date window. If you want them counted, they need a
#     second date rather than a move into this set.
#   Recently changed, included but flag-worthy: Iraq (national holiday since
#     2018) and Ukraine (moved from Jan 7 to Dec 25 in 2023 -- so trips before
#     2023 are tagged on a date that was not yet the holiday).
# Christmas Eve and Christmas Day. Both count: in much of CHRISTMAS_COUNTRIES
# the 24th is the main celebration (Germany, the Nordics, Poland, most of
# Latin America), and a trip arriving on the 24th and leaving on the 25th
# should not fall through the gap between them.
CHRISTMAS_DAYS = (24, 25)

CHRISTMAS_COUNTRIES = frozenset({
    "Argentina", "Aruba", "Australia", "Austria", "Bahamas", "Belgium", "Belize",
    "Brazil", "Burma", "Canada", "Cayman Islands", "Chile", "Colombia",
    "Congo (Kinshasa)", "Costa Rica", "Croatia", "Cuba", "Czech Republic",
    "Denmark", "Dominican Republic", "Ecuador", "Finland", "France", "Germany",
    "Ghana", "Greece", "Haiti", "Hong Kong", "Hungary", "Iceland", "India",
    "Indonesia", "Iraq", "Ireland", "Italy", "Jamaica", "Kenya", "Liberia",
    "Madagascar", "Malaysia", "Mexico", "Mozambique", "Namibia", "Netherlands",
    "Netherlands Antilles", "New Zealand", "Nicaragua", "Nigeria", "Norway",
    "Panama", "Paraguay", "Peru", "Philippines", "Portugal", "Puerto Rico",
    "Romania", "Saint Vincent and the Grenadines", "Senegal", "Singapore",
    "South Africa", "South Korea", "Spain", "Sri Lanka", "Sweden",
    "Switzerland", "Tanzania", "Trinidad and Tobago", "Turks and Caicos",
    "Ukraine", "United Kingdom", "United States", "Uruguay",
})


def _us_thanksgiving_dates(years):
    """US Thanksgiving per year, from pandas' federal calendar.

    Thanksgiving is the one federal holiday that never shifts -- it is defined
    as a Thursday -- so the calendar's observed date IS the real date. That is
    not true of Christmas, which is why Christmas is taken as a literal Dec 25
    below rather than from this calendar: in 2027 Dec 25 is a Saturday and the
    calendar reports the observed holiday on Friday the 24th, which is the
    date the offices shut, not the date anyone sits down to dinner. (The
    Christmas test covers the 24th anyway -- see CHRISTMAS_DAYS -- but for
    the right reason, rather than as a side effect of a federal observance
    rule that also moves Christmas to the 26th in other years.)
    """
    if not years:
        return set()
    calendar = USFederalHolidayCalendar()
    holidays = calendar.holidays(start=f"{min(years)}-01-01", end=f"{max(years)}-12-31",
                                 return_name=True)
    return {d.date() for d, name in holidays.items() if name == "Thanksgiving Day"}


def _canadian_thanksgiving_dates(years):
    """Canadian Thanksgiving: the second Monday of October.

    Computed rather than looked up -- pandas' calendar is the US FEDERAL one
    and has no Canadian holidays in it. The rule is a fixed nth-weekday, so
    deriving it is exact, not an approximation.
    """
    dates = set()
    for year in years:
        first = date(year, 10, 1)
        first_monday = first + timedelta(days=(7 - first.weekday()) % 7)
        dates.add(first_monday + timedelta(days=7))
    return dates


def thanksgiving_dates_by_country(years):
    """country -> the dates ITS Thanksgiving falls on, over `years`."""
    return {
        "United States": _us_thanksgiving_dates(years),
        "Canada": _canadian_thanksgiving_dates(years),
    }


def is_holiday_trip(df):
    """Was the trip over a holiday, somewhere that observes it?

    Two independent ways to qualify, and the matched one is recorded in
    "Holiday Matched" so a 1 can always be explained:

      Thanksgiving -- the DESTINATION COUNTRY'S OWN Thanksgiving falls inside
                      the trip's dates. The US and Canada observe it six
                      weeks apart, so each is tested against its own date;
                      being in Toronto over the American one does not count,
                      and vice versa.
      Christmas    -- December 24 OR 25 falls inside the trip's dates AND the
                      destination is in CHRISTMAS_COUNTRIES. Both days,
                      because Christmas Eve is the main event in much of the
                      list -- Germany, the Nordics, Poland, most of Latin
                      America celebrate on the 24th -- and because a trip
                      that lands for the 24th and leaves on the 25th would
                      otherwise be missed entirely.

    Both use the trip's full date range inclusive, the same span the ski and
    beach rules use.
    """
    years = set()
    for _, row in df.iterrows():
        for key in ("Arrival Date", "Departure Date"):
            value = row.get(key)
            if value:
                years.add(pd.Timestamp(value).year)
    thanksgiving = thanksgiving_dates_by_country(years)

    flags, matched = [], []
    for _, row in df.iterrows():
        country = row.get("Destination Country")
        days = pd.date_range(row["Arrival Date"], row["Departure Date"], freq="D")
        hits = []
        country_thanksgiving = thanksgiving.get(country, set())
        if any(d.date() in country_thanksgiving for d in days):
            hits.append("Thanksgiving")
        if country in CHRISTMAS_COUNTRIES and any(d.month == 12 and d.day in CHRISTMAS_DAYS for d in days):
            hits.append("Christmas")
        flags.append(1 if hits else 0)
        matched.append(" + ".join(hits) if hits else "")

    out = df.copy()
    out["Holiday Matched"] = matched
    out["HOLIDAY_TRIP"] = flags
    return out



# --------------------------------------------------------------------------
# Production entry point
# --------------------------------------------------------------------------

# One entry per flag column. Shape mirrors compute_traveler_tags.py's tags so
# a trip chip and a traveler chip are the same kind of object to the UI.
TRIP_TAGS = {
    "IS_SKI_TRIP": {"kind": "ski_trip", "tag_id": "ski-trip", "label": "Ski Trip"},
    "BEACH_VACATION": {"kind": "beach_vacation", "tag_id": "beach-vacation", "label": "Beach Vacation"},
    "HOLIDAY_TRIP": {"kind": "holiday_trip", "tag_id": "holiday-trip", "label": "Holiday Trip"},
    "EUROPEAN_SUMMER": {"kind": "european_summer", "tag_id": "european-summer",
                        "label": "European Summer"},
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
                     "Destination Country": trip.get("destination_country"),
                     # For the M49 region join -- see is_european_summer().
                     "Destination Country Code": trip.get("destination_country_code")})
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
               "Distance To Shore KM", "Distance To Beach KM", "Avg Trip High C",
               "BEACH_VACATION", "Holiday Matched", "HOLIDAY_TRIP",
               "Region Matched", "EUROPEAN_SUMMER"]
    print(result[columns].to_string(index=False))
