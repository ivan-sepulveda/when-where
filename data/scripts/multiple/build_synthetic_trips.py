"""
Builds data/processed/multiple/synthetic_trips.json: hand-authored travelers
who aren't in the Kaggle source at all, in the same trip shape
build_trips_enhanced.py emits, which merges this file into
trips_enhanced.json.

WHY THIS EXISTS. The Kaggle dataset is 137 one-off trips with almost no
repeat travelers -- 113 of its 124 people have exactly one trip. That's fine
for filling a page, and useless for the thing this project is actually
building toward: recommending a destination to someone based on where they've
already been. A recommender needs travelers with a *pattern*. So this script
adds travelers who have one, each a different shape of pattern:

  Joaquin Sorolla     New York City (EWR), United loyalist. Two weeks in
                       Europe every August 2016-2025, never the same city
                       twice, plus Christmas week in Houston every December.
                       -> a seasonal regular with a wide destination spread.
  Edward Hopper        San Francisco (SFO). One long Asia trip every autumn
                       2016-2025, cities repeating freely, carriers varying
                       by route. -> a loyalist to a REGION rather than to an
                       airline or a city.
  Georgia O'Keeffe     Houston (IAH). One week in Mexico every January
                       2021-2025, a different Mexican city each time.
                       -> a tight, short, seasonal habit.
  Pablo Picasso        Barcelona (BCN). Four US trips, one each August
                       2021-2024, a different American city each time.
                       -> the only non-US base here, so the "home country"
                       side of any recommendation isn't all one place.
  Jackson Pollock      Chicago (ORD). Toronto the first week of EVERY month
                       of 2025. -> a high-frequency commuter on one route:
                       twelve trips, one destination, one year.
  Andy Warhol          Houston (IAH), United loyalist. Mexico two or three
                       times a year 2020-2025, working through United's
                       entire Houston-Mexico network. -> broad coverage of
                       ONE country, and a deliberate near-duplicate of
                       O'Keeffe's base and destination country with a
                       completely different rhythm, which is exactly the pair
                       a recommender should be able to tell apart.
  Miles Davis          Boston (BOS), Delta loyalist. Four European trips a
                       year 2020-2025, twice around Delta's entire Boston
                       transatlantic network. -> the same "whole network"
                       shape as Warhol, on a different continent and a
                       different airline.
  Stan Getz            New York City (JFK), Delta loyalist. Four European
                       trips a year 2020-2025 -- all 24 of Delta's JFK
                       transatlantic routes, one apiece -- plus a week in
                       Cancun every July. -> the widest destination spread
                       here, and a second NYC-based traveler who shares
                       nothing with Joaquin Sorolla operationally: he
                       flies Delta from JFK, Sorolla flies United from EWR.
  Chet Baker           Atlanta (ATL), Delta loyalist. New York every other
                       week through 2024-2025, Monday to Friday. -> a pure
                       business commuter: 53 trips, one route, no holidays
                       in it at all.
  Bill Evans           Detroit (DTW), Delta loyalist. Ten days in Amsterdam
                       every April, 2016-2025. Same city, every year, for a
                       decade. -> total destination loyalty, the hardest
                       case to recommend anything new to.
  John Coltrane        Minneapolis (MSP), Delta loyalist. Three Caribbean or
                       Mexican beach trips every winter 2021-2025, never in
                       any other season. -> a pure seasonal escape: the
                       WHEN matters more than the where.
  Thelonious Monk      Los Angeles (LAX), Delta loyalist. Australia and New
                       Zealand twice a year, 2019-2025. -> one region,
                       reached only by ultra-long-haul, on the opposite
                       hemisphere's seasons.
  Wes Montgomery       Seattle (SEA), Delta loyalist. Asia twice a year
                       2016-2019, nothing at all in 2020-2021, then straight
                       back to it 2022-2025. -> the lapsed-and-returned
                       traveler, and the only one here whose calendar
                       reflects that those two years happened.

  And eight domestic-only travelers who fly once to three times a year to
  see family in one US city, and nowhere else -- Pierre-Auguste Renoir,
  Edgar Degas, Claude Monet and Alfred d'Orsay on United; Ella Fitzgerald,
  Duke Ellington, Sarah Vaughan and Charlie Parker on Delta. -> the most
  common travel pattern there is, and one the rest of this file completely
  lacked: no variety, no holidays, one destination chosen by where relatives
  live rather than by anything a recommender could ever suggest. They stay
  with family rather than in hotels, so their trips carry no accommodation
  cost at all -- an absence that is itself a signal worth having in the data.

  Then ten American Airlines loyalists, split three ways so the file has
  every combination of domestic and international rather than only the
  extremes:
    * International only, one destination, forever -- Albert Einstein
      (Dallas-London), Marie Curie (Miami-Buenos Aires), Niels Bohr
      (Philadelphia-Lisbon). The international mirror of Bill Evans.
    * Domestic only, and specifically HOLIDAY travel -- Isaac Newton
      (Chicago-Denver at Christmas and in summer), Galileo Galilei
      (Washington-Orlando three times a year), Louis Pasteur
      (Philadelphia-Palm Beach). Distinct from the family visitors above:
      these are holidays taken somewhere, not relatives visited, so they
      stay in hotels and pay for them.
    * Mixed, domestic AND international in the same year -- Charles Darwin,
      Nikola Tesla, Stephen Hawking, Richard Feynman. Until these four, every
      hand-authored traveler was purely one or the other, which is not how
      most people's travel actually looks -- and a recommender that has only
      ever seen pure cases has no reason to believe someone who flies to Sao
      Paulo also flies to Boston.

  Then ten Southwest loyalists on the same three-way split. Southwest is the
  one carrier here with NO long-haul at all: its whole international network
  in this data is Mexico, Central America and the Caribbean, and it flies
  from the secondary airport in cities that have one. So this group is where
  short-haul international lives, and where Chicago means Midway and Houston
  means Hobby.
    * International only -- Clark Kent (Hobby-Cancun), Bruce Wayne
      (Baltimore-Montego Bay), Diana Prince (Phoenix-Los Cabos).
    * Domestic only, holidays -- Barry Allen (Midway-Tampa), Hal Jordan
      (Denver-San Diego), Arthur Curry (Nashville-Sarasota).
    * Mixed -- Victor Stone, Oliver Queen, Billy Batson, Dick Grayson.

  And ten Alaska loyalists, same split again. Alaska's network splits three
  ways -- transpacific from Seattle, Mexico from the California airports,
  the South Pacific from Honolulu -- and it supplies the two things nothing
  else here does: the only non-mainland base (Steve Rogers in Honolulu) and
  domestic flights that are longer than most of this file's international
  ones (Seattle-Maui, Los Angeles-Kona).
    * International only -- Peter Parker (Seattle-Tokyo), Tony Stark
      (Los Angeles-Guadalajara), Steve Rogers (Honolulu-Sydney).
    * Domestic only, holidays -- Bruce Banner (Seattle-Maui), Thor Odinson
      (Portland-Palm Springs), Natasha Romanoff (San Francisco-Orlando).
    * Mixed -- Clint Barton, Matt Murdock, Logan, Stephen Strange.

  And finally thirty-one travelers who are loyal to NOTHING, spread two per
  city (three in New York) across the fifteen most populous US cities. Every
  other traveler in this file was built around an airline; these were built
  around the absence of one, and they exist because a file of nothing but
  loyalists would teach a recommender that airline choice is a fact about a
  person rather than a fact about a route.

  Not one of their legs names a carrier. Each is ANY_CARRIER, resolved from
  the T-100 data at build time and stepped through that route's operators in
  volume order, so Zeus's four New York-London trips come out on British
  Airways, Virgin Atlantic, American and Delta, and Hera's Columbus-Orlando
  hops on Frontier, Southwest and Spirit. They average nine or ten distinct
  airlines each against exactly one for every loyalist above -- and that
  number is now a real signal in the data rather than a thing this file
  asserts.

  The other reason they exist is geography. Every traveler above departs from
  a hub some airline happens to run; these depart from where Americans
  actually live, which gives Jacksonville, Austin, San Jose, Columbus, San
  Antonio, Fort Worth, San Diego and Charlotte their first residents here.

The names are a convention, not a joke. One category per airline, so which
airline a traveler flies is legible from their name alone while reading the
data:
    United     painters and architects
    Delta      jazz musicians
    American   scientists
    Southwest  DC comics characters
    Alaska     Marvel comics characters
    (no one)   Greek myth
The last three also make the fiction unmissable, which is the point of naming
these people at all. The pairings are deliberately NOT biographical: Marie
Curie flies to Buenos Aires, Galileo to Orlando and Thor to Palm Springs,
because matching each name to the obvious city would imply this file knows
something about real people (or invents something about invented ones) that
it doesn't. Gender is lopsided but no longer nearly-uniform: the Greek group
is 9 women to 22 men, which brings the whole file to 15 women against 67 men.
Still worth knowing before anyone reads a pattern into it.

Two id_prefix collisions are resolved by suffixing rather than renaming, and
the odd-looking prefixes are deliberate: "PPK" (Peter Parker) because Pablo
Picasso holds "PP", "BBN" (Bruce Banner) because Billy Batson holds "BB", and
"CBA" (Clint Barton) because Chet Baker holds "CB". trip_id starts with this
prefix, so a duplicate would silently merge two people's trips.

THE ROUTES ARE REAL, and this script proves it rather than asserting it.
Every leg names a carrier, an origin and a destination that must appear
together in US DOT T-100 data (data/raw/bts_t100/, see data/README.md), or
the script fails. Two files, because BTS splits the world that way:
  * International legs -> T_T100I_MARKET_ALL_CARRIER.csv, which carries
    passenger counts. That's also where each international leg's carrier
    comes from: Hopper flies Cathay Pacific to Hong Kong and EVA Air to
    Taipei because those are the busiest operators on those routes in that
    file, not because it sounded plausible.
  * Domestic legs -> T_T100D_SEGMENT_ALL_CARRIER.csv, which has no passenger
    column at all -- only which carrier flew which segment, in which month,
    on which aircraft. That's enough for what this check does, which is ask
    whether a route is real rather than how busy it is. Sorolla's EWR-IAH
    Christmas hop and Chet Baker's whole ATL-JFK commute went unverified
    until this file arrived; they're checked now.

One honest caveat, left visible rather than smoothed away:
  * 2020 and 2021 entries are in these itineraries because the briefs asked
    for unbroken runs of years, not because those trips could have happened.
    A US traveler taking a European holiday in August 2020, or an Asia trip
    that autumn, ran into entry bans that were very much in force. Treat
    those years as the obviously fictional ones in otherwise plausible
    patterns.

Everything else is fabricated: costs, exact dates, ages. This is fixture data
with a deliberate shape, not a record of anyone. The names are placeholders in
the same spirit as the author personas (build_travelers_anon.py) -- the real
painters' and architects' lives have nothing to do with these trips.

Usage:
    python build_synthetic_trips.py
    python build_synthetic_trips.py --skip-route-check   # don't read the BTS file
"""

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Date helpers -- defined above the config below, which calls them while
# building its itineraries.
# ---------------------------------------------------------------------------

def second_saturday(year: int, month: int) -> date:
    """The second Saturday of the month. Gives each year a slightly different
    departure date the way real holidays fall, without reaching for
    randomness (which would make this script's output change every run)."""
    first = date(year, month, 1)
    days_until_saturday = (5 - first.weekday()) % 7  # Monday=0 ... Saturday=5
    return first + timedelta(days=days_until_saturday + 7)


def first_monday(year: int, month: int) -> date:
    """The first Monday of the month -- the start of the first working week,
    which is what a business traveler means by "the first week"."""
    first = date(year, month, 1)
    return first + timedelta(days=(0 - first.weekday()) % 7)  # Monday=0


def thanksgiving_departure(year: int, month: int) -> date:
    """The Tuesday before Thanksgiving (the fourth Thursday of November) --
    the single busiest travel day of the American year, and the one a holiday
    traveler actually flies on rather than the holiday itself."""
    first = date(year, 11, 1)
    first_thursday = first + timedelta(days=(3 - first.weekday()) % 7)  # Thursday=3
    thanksgiving = first_thursday + timedelta(days=21)
    return thanksgiving - timedelta(days=2)


def last_monday(year: int, month: int) -> date:
    """The last Monday of the month -- Memorial Day in May, Labor Day's
    cousin elsewhere."""
    day = date(year, month, 28 if month == 2 else 30 if month in (4, 6, 9, 11) else 31)
    return day - timedelta(days=(day.weekday() - 0) % 7)


DAY_RULES = {
    "second-saturday": second_saturday,
    "first-monday": first_monday,
    "thanksgiving": thanksgiving_departure,
    "last-monday": last_monday,
}


def start_date(year: int, month: int, day_rule) -> date:
    """`day_rule` is either a named rule from DAY_RULES or a literal day of
    the month (which is how the generated itineraries below pin exact
    dates)."""
    rule = DAY_RULES.get(day_rule)
    return rule(year, month) if rule else date(year, month, int(day_rule))


# ---------------------------------------------------------------------------
# Config -- the itineraries are the substance of this script.
# ---------------------------------------------------------------------------

# Cost tier -> (hotel base, hotel annual rate, flight base, flight annual
# rate), in the traveler's first year. Costs are invented, but not arbitrary:
# a plausible baseline compounded and rounded to the nearest $25, so a decade
# of trips shows the drift you'd expect instead of ten identical numbers.
# Written out as "$2,400"-style strings, the same display-string form the
# Kaggle source uses.
COST_TIERS = {
    "transatlantic_2w": (2400, 0.05, 780, 0.04),
    "transatlantic_1w": (1600, 0.05, 820, 0.04),
    "transatlantic_10d": (2200, 0.05, 820, 0.04),
    "transpacific_2w": (2600, 0.05, 950, 0.04),
    "mexico_1w": (950, 0.04, 420, 0.03),
    # Four nights in a Mexican city rather than a week at a beach resort --
    # less hotel, much the same airfare.
    "mexico_city_break": (600, 0.04, 400, 0.03),
    # A week at a Caribbean or Pacific-coast resort -- more hotel than a
    # Mexican city break, shorter flight than a transatlantic one.
    "caribbean_1w": (1100, 0.04, 480, 0.03),
    "domestic_1w": (900, 0.04, 280, 0.03),
    "shorthaul_1w": (850, 0.03, 260, 0.03),
    # Four nights in a New York hotel on business -- the priciest per-night
    # accommodation here, on the cheapest flight.
    "domestic_workweek": (1200, 0.04, 340, 0.03),
    # Visiting family: a hotel base of 0 means they stay with relatives, and
    # build_trips() turns that into accommodation_type "Family home" with no
    # cost at all rather than a $0 hotel bill. Short vs long is just flight
    # distance -- Dulles to Pittsburgh isn't Denver to Boston.
    "family_visit_short": (0, 0.0, 220, 0.03),
    "family_visit_long": (0, 0.0, 340, 0.03),
    # Latin America out of Miami: shorter and cheaper than a transatlantic
    # trip, longer and dearer than a Caribbean hop.
    "latin_america_1w": (1200, 0.04, 620, 0.04),
    # A holiday taken somewhere domestic -- a ski week, a theme park, a
    # Florida fortnight. Unlike the family visits above, these people pay
    # for a hotel.
    "domestic_holiday": (1000, 0.04, 320, 0.03),
}

# Airports named for the metro they serve rather than their own municipality,
# because that's what a traveler means by "where I went": EWR is Newark but
# the trip is to New York; IAD is in Virginia but the trip is to Washington.
# Kept as a comment rather than a lookup table since each itinerary below
# spells out its own destination city.

# Every route mainline United flies from its Houston hub into Mexico in the
# T-100 data, busiest first -- the whole network, which is the brief: he takes
# whatever United flies to Mexico. `nights` splits beach destinations (a week)
# from city ones (a long weekend), which is the difference between the two
# kinds of trip these routes actually carry.
WARHOL_ROTATION = [
    ("CUN", "Cancun", 7, "mexico_1w"),
    ("MEX", "Mexico City", 4, "mexico_city_break"),
    ("SJD", "San Jose del Cabo", 7, "mexico_1w"),
    ("QRO", "Queretaro", 4, "mexico_city_break"),
    ("GDL", "Guadalajara", 4, "mexico_city_break"),
    ("PVR", "Puerto Vallarta", 7, "mexico_1w"),
    ("MID", "Merida", 4, "mexico_city_break"),
    ("CZM", "Cozumel", 7, "mexico_1w"),
    ("VER", "Veracruz", 4, "mexico_city_break"),
    ("MTY", "Monterrey", 4, "mexico_city_break"),
    ("BJX", "Leon/Guanajuato", 4, "mexico_city_break"),
    ("SLP", "San Luis Potosi", 4, "mexico_city_break"),
]

# Which months he flies each year: two trips some years, three others, spread
# across the calendar rather than clustered. Fifteen trips over six years --
# enough to work through all twelve routes above and come back round to the
# three busiest.
WARHOL_YEARS = [
    (2020, [3, 10]),
    (2021, [2, 6, 11]),
    (2022, [4, 9]),
    (2023, [2, 7, 11]),
    (2024, [3, 6, 10]),
    (2025, [4, 9]),
]


def warhol_itinerary() -> list[tuple]:
    """His trips, taking WARHOL_ROTATION in order and wrapping around when it
    runs out -- so the first twelve are twelve different Mexican cities and
    the last three revisit the busiest routes. Written as a loop rather than
    a list of fifteen literals because the rotation IS the pattern; spelling
    it out would hide the rule inside the data."""
    itinerary = []
    index = 0
    for year, months in WARHOL_YEARS:
        for month in months:
            airport, city, nights, tier = WARHOL_ROTATION[index % len(WARHOL_ROTATION)]
            index += 1
            itinerary.append(
                (year, month, "second-saturday", nights, "United Air Lines Inc.", airport, city, "Mexico", "MX", tier)
            )
    return itinerary


# Delta's entire transatlantic network out of Boston, busiest first, exactly
# as the T-100 file records it -- twelve routes. Miles Davis flies four trips
# a year for six years, so he goes round this list twice.
DELTA_BOS_EUROPE = [
    ("AMS", "Amsterdam", "Netherlands", "NL"),
    ("CDG", "Paris", "France", "FR"),
    ("LHR", "London", "United Kingdom", "GB"),
    ("LIS", "Lisbon", "Portugal", "PT"),
    ("FCO", "Rome", "Italy", "IT"),
    ("DUB", "Dublin", "Ireland", "IE"),
    ("ATH", "Athens", "Greece", "GR"),
    ("MAD", "Madrid", "Spain", "ES"),
    ("BCN", "Barcelona", "Spain", "ES"),
    ("EDI", "Edinburgh", "United Kingdom", "GB"),
    ("MXP", "Milan", "Italy", "IT"),
    ("NCE", "Nice", "France", "FR"),
]

# The same thing from JFK, which is a far bigger transatlantic operation --
# twenty-four routes. Stan Getz flies four a year for six years, so he does
# each of them exactly once and repeats nothing.
DELTA_JFK_EUROPE = [
    ("CDG", "Paris", "France", "FR"),
    ("LHR", "London", "United Kingdom", "GB"),
    ("AMS", "Amsterdam", "Netherlands", "NL"),
    ("FCO", "Rome", "Italy", "IT"),
    ("MXP", "Milan", "Italy", "IT"),
    ("MAD", "Madrid", "Spain", "ES"),
    ("BCN", "Barcelona", "Spain", "ES"),
    ("LIS", "Lisbon", "Portugal", "PT"),
    ("DUB", "Dublin", "Ireland", "IE"),
    ("ATH", "Athens", "Greece", "GR"),
    ("ZRH", "Zurich", "Switzerland", "CH"),
    ("VCE", "Venice", "Italy", "IT"),
    ("FRA", "Frankfurt", "Germany", "DE"),
    ("EDI", "Edinburgh", "United Kingdom", "GB"),
    ("NCE", "Nice", "France", "FR"),
    ("NAP", "Naples", "Italy", "IT"),
    ("KEF", "Reykjavik", "Iceland", "IS"),
    ("CPH", "Copenhagen", "Denmark", "DK"),
    ("BER", "Berlin", "Germany", "DE"),
    ("ARN", "Stockholm", "Sweden", "SE"),
    ("PRG", "Prague", "Czech Republic", "CZ"),
    ("OPO", "Porto", "Portugal", "PT"),
    ("SNN", "Shannon", "Ireland", "IE"),
    ("BRU", "Brussels", "Belgium", "BE"),
]


# Delta's Caribbean and Mexican beach network out of Minneapolis, busiest
# first -- eleven routes, all of them warm places to be in a Minnesota
# January, which is the entire logic of John Coltrane's itinerary.
DELTA_MSP_WINTER = [
    ("CUN", "Cancun", "Mexico", "MX"),
    ("PUJ", "Punta Cana", "Dominican Republic", "DO"),
    ("SJD", "San Jose del Cabo", "Mexico", "MX"),
    ("PVR", "Puerto Vallarta", "Mexico", "MX"),
    ("LIR", "Liberia", "Costa Rica", "CR"),
    ("MBJ", "Montego Bay", "Jamaica", "JM"),
    ("CZM", "Cozumel", "Mexico", "MX"),
    ("AUA", "Oranjestad", "Aruba", "AW"),
    ("GCM", "George Town", "Cayman Islands", "KY"),
    ("PLS", "Providenciales", "Turks and Caicos", "TC"),
    ("BZE", "Belize City", "Belize", "BZ"),
]

# Delta's South Pacific routes from Los Angeles. Only four, which is the
# point: Thelonious Monk's world is small and very far away.
DELTA_LAX_PACIFIC = [
    ("SYD", "Sydney", "Australia", "AU"),
    ("AKL", "Auckland", "New Zealand", "NZ"),
    ("MEL", "Melbourne", "Australia", "AU"),
    ("BNE", "Brisbane", "Australia", "AU"),
]

# Delta's Asian routes from Seattle, busiest first.
DELTA_SEA_ASIA = [
    ("HND", "Tokyo", "Japan", "JP"),
    ("ICN", "Seoul", "South Korea", "KR"),
    ("TPE", "Taipei", "Taiwan", "TW"),
    ("PVG", "Shanghai", "China", "CN"),
]


def rotating_itinerary(rotation, years, months, nights, tier, carrier="Delta Air Lines Inc."):
    """`len(months)` trips a year, taking `rotation` in order and wrapping
    when it runs out. The general form of european_itinerary() below, which
    predates it and stays as it is because its callers pass a fixed tier."""
    itinerary = []
    index = 0
    for year in years:
        for month in months:
            airport, city, country, code = rotation[index % len(rotation)]
            index += 1
            itinerary.append(
                (year, month, "second-saturday", nights, carrier, airport, city, country, code, tier)
            )
    return itinerary


# A leg whose carrier is this sentinel gets one resolved from the T-100 data
# at build time instead of being named here -- see resolve_carriers(). It's
# how the non-loyalists are expressed: they don't have an airline, they have
# a route, and the airline is whoever flies it.
ANY_CARRIER = "*"

# Every destination a non-loyalist flies to, and the shape of the trip when
# they go: (city, country, ISO code, nights, cost tier). Putting the shape on
# the DESTINATION rather than on the traveler is the whole reason this table
# exists -- a week in Cancun and a long weekend in Toronto are properties of
# those places, not of who booked them, and stating each one once means
# thirty-one itineraries can be written as bare lists of airport codes.
PLACES = {
    # --- Europe -----------------------------------------------------------
    "LHR": ("London", "United Kingdom", "GB", 7, "transatlantic_1w"),
    "CDG": ("Paris", "France", "FR", 8, "transatlantic_10d"),
    "FCO": ("Rome", "Italy", "IT", 9, "transatlantic_10d"),
    "BCN": ("Barcelona", "Spain", "ES", 8, "transatlantic_10d"),
    "MAD": ("Madrid", "Spain", "ES", 8, "transatlantic_10d"),
    "LIS": ("Lisbon", "Portugal", "PT", 9, "transatlantic_10d"),
    "DUB": ("Dublin", "Ireland", "IE", 7, "transatlantic_1w"),
    "AMS": ("Amsterdam", "Netherlands", "NL", 7, "transatlantic_1w"),
    "FRA": ("Frankfurt", "Germany", "DE", 6, "transatlantic_1w"),
    "MUC": ("Munich", "Germany", "DE", 7, "transatlantic_1w"),
    # --- Asia and the Pacific ---------------------------------------------
    "HND": ("Tokyo", "Japan", "JP", 12, "transpacific_2w"),
    "NRT": ("Tokyo", "Japan", "JP", 12, "transpacific_2w"),
    "ICN": ("Seoul", "South Korea", "KR", 11, "transpacific_2w"),
    "SYD": ("Sydney", "Australia", "AU", 14, "transpacific_2w"),
    # --- Mexico: beaches get a week, inland cities get a long weekend ------
    "CUN": ("Cancun", "Mexico", "MX", 7, "mexico_1w"),
    "SJD": ("San Jose del Cabo", "Mexico", "MX", 7, "mexico_1w"),
    "PVR": ("Puerto Vallarta", "Mexico", "MX", 6, "mexico_1w"),
    "MEX": ("Mexico City", "Mexico", "MX", 5, "mexico_city_break"),
    "GDL": ("Guadalajara", "Mexico", "MX", 5, "mexico_city_break"),
    "MTY": ("Monterrey", "Mexico", "MX", 4, "mexico_city_break"),
    "QRO": ("Queretaro", "Mexico", "MX", 4, "mexico_city_break"),
    "BJX": ("Leon", "Mexico", "MX", 4, "mexico_city_break"),
    # --- Caribbean and Central America ------------------------------------
    "NAS": ("Nassau", "Bahamas", "BS", 5, "caribbean_1w"),
    "PUJ": ("Punta Cana", "Dominican Republic", "DO", 7, "caribbean_1w"),
    "MBJ": ("Montego Bay", "Jamaica", "JM", 7, "caribbean_1w"),
    "SJO": ("San Jose", "Costa Rica", "CR", 8, "latin_america_1w"),
    "LIR": ("Liberia", "Costa Rica", "CR", 8, "latin_america_1w"),
    "BZE": ("Belize City", "Belize", "BZ", 7, "latin_america_1w"),
    # --- Canada -----------------------------------------------------------
    "YYZ": ("Toronto", "Canada", "CA", 4, "shorthaul_1w"),
    "YUL": ("Montreal", "Canada", "CA", 4, "shorthaul_1w"),
    "YVR": ("Vancouver", "Canada", "CA", 5, "shorthaul_1w"),
    # --- United States ----------------------------------------------------
    "ATL": ("Atlanta", "United States", "US", 3, "shorthaul_1w"),
    "AUS": ("Austin", "United States", "US", 4, "shorthaul_1w"),
    "BNA": ("Nashville", "United States", "US", 4, "shorthaul_1w"),
    "BOS": ("Boston", "United States", "US", 4, "shorthaul_1w"),
    "CLT": ("Charlotte", "United States", "US", 3, "shorthaul_1w"),
    "DCA": ("Washington", "United States", "US", 4, "shorthaul_1w"),
    "DEN": ("Denver", "United States", "US", 5, "domestic_1w"),
    "DFW": ("Dallas", "United States", "US", 4, "shorthaul_1w"),
    "EWR": ("Newark", "United States", "US", 4, "shorthaul_1w"),
    "HNL": ("Honolulu", "United States", "US", 9, "domestic_holiday"),
    "IAD": ("Washington", "United States", "US", 4, "shorthaul_1w"),
    "IAH": ("Houston", "United States", "US", 4, "shorthaul_1w"),
    "JFK": ("New York City", "United States", "US", 5, "domestic_1w"),
    "LAS": ("Las Vegas", "United States", "US", 4, "domestic_1w"),
    "LAX": ("Los Angeles", "United States", "US", 6, "domestic_1w"),
    "MCO": ("Orlando", "United States", "US", 6, "domestic_1w"),
    "MIA": ("Miami", "United States", "US", 5, "domestic_1w"),
    "MSP": ("Minneapolis", "United States", "US", 4, "shorthaul_1w"),
    "MSY": ("New Orleans", "United States", "US", 4, "shorthaul_1w"),
    "ORD": ("Chicago", "United States", "US", 4, "shorthaul_1w"),
    "PDX": ("Portland", "United States", "US", 5, "domestic_1w"),
    "PHL": ("Philadelphia", "United States", "US", 4, "shorthaul_1w"),
    "PHX": ("Phoenix", "United States", "US", 5, "domestic_1w"),
    "SAT": ("San Antonio", "United States", "US", 4, "shorthaul_1w"),
    "SEA": ("Seattle", "United States", "US", 5, "domestic_1w"),
    "SFO": ("San Francisco", "United States", "US", 5, "domestic_1w"),
    "SLC": ("Salt Lake City", "United States", "US", 4, "shorthaul_1w"),
    "TPA": ("Tampa", "United States", "US", 5, "domestic_1w"),
}

# Departure days for the wanderers, cycled through in order. Not the second
# Saturday of the month like every loyalist above: someone who books on
# convenience leaves on a Tuesday as readily as a weekend, and a file where
# every single departure falls on a Saturday would teach a model that
# day-of-week carries no information at all.
WANDER_DAYS = (7, 15, 22, 11, 18, 4)


def wandering_itinerary(rotation, years, months, days=WANDER_DAYS):
    """A few trips a year, cycling through `rotation` (bare airport codes,
    looked up in PLACES) and never naming an airline -- every leg is
    ANY_CARRIER, resolved from the T-100 data at build time.

    This is the generator for travelers who are loyal to nothing. The other
    generators in this file take a carrier because their travelers HAVE one;
    the point of these thirty-one is that they don't, and expressing that as
    an absence in the config rather than as a list of airlines is what stops
    it from quietly becoming another hand-made choice."""
    itinerary = []
    slot = 0
    for year in years:
        for month in months:
            code = rotation[slot % len(rotation)]
            city, country, cc, nights, tier = PLACES[code]
            itinerary.append(
                (year, month, days[slot % len(days)], nights, ANY_CARRIER, code, city, country, cc, tier)
            )
            slot += 1
    return itinerary


def annual_pattern(years, legs, carrier="American Airlines Inc."):
    """The same set of trips every year. `legs` is
    [(month, day_rule, nights, airport, city, country, code, tier), ...] --
    the general form the other generators here are special cases of, used for
    travelers whose year mixes destinations, trip lengths and even continents
    rather than rotating through one list."""
    return [
        (year, month, day_rule, nights, carrier, airport, city, country, code, tier)
        for year in years
        for month, day_rule, nights, airport, city, country, code, tier in legs
    ]


def family_visits(years, months_and_nights, carrier, airport, city, tier):
    """One to three trips a year to the same US city, on the same airline,
    forever. `months_and_nights` is [(month, nights), ...]; December is
    pinned to the 20th rather than a floating Saturday, because a Christmas
    visit is scheduled around the holiday and not around a convenient
    weekend.

    Deliberately the least varied generator here. Visiting family is the most
    common reason people fly and the least tractable for a recommender: the
    destination isn't chosen, so nothing about it can be suggested. A dataset
    of nothing but wandering aesthetes would hide that problem completely."""
    return [
        (
            year,
            month,
            20 if month == 12 else "second-saturday",
            nights,
            carrier,
            airport,
            city,
            "United States",
            "US",
            tier,
        )
        for year in years
        for month, nights in months_and_nights
    ]


def european_itinerary(rotation, years, months, nights, carrier="Delta Air Lines Inc."):
    """Four trips a year, taking `rotation` in order and wrapping when it runs
    out. Same generated-from-a-rule approach as warhol_itinerary(): the
    rotation IS the pattern, and writing out two dozen literals would hide
    that."""
    itinerary = []
    index = 0
    for year in years:
        for month in months:
            airport, city, country, code = rotation[index % len(rotation)]
            index += 1
            itinerary.append(
                (year, month, "second-saturday", nights, carrier, airport, city, country, code, "transatlantic_1w")
            )
    return itinerary


def biweekly_commute(start_year: int, end_year: int, carrier, airport, city, country, code, nights, tier):
    """A trip every other week from the first Monday of `start_year` through
    the end of `end_year`, each departing Monday.

    Every fortnight rather than "the 1st and 15th": the brief was every other
    week, and a real commuter's calendar runs on weekdays, not on dates. The
    fortnight is anchored once at the start and then stepped, so the whole
    two-year run stays on Mondays instead of drifting."""
    itinerary = []
    day = first_monday(start_year, 1)
    while day.year <= end_year:
        itinerary.append(
            (day.year, day.month, day.day, nights, carrier, airport, city, country, code, tier)
        )
        day += timedelta(days=14)
    return itinerary


TRAVELERS = [
    {
        "name": "Joaquín Sorolla",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "JS",
        "first_year": 2016,
        "age_in_first_year": 49,
        "base": {
            "city": "New York City",
            "country": "United States",
            "country_code": "US",
            "airport": "EWR",  # United's New York hub -- hence EWR, not JFK
        },
        # (year, month, day_rule, nights, carrier, airport, city, country, code, tier)
        # day_rule: "second-saturday" or an integer day of the month.
        "itinerary": [
            # Two weeks in Europe every August, never the same city twice.
            # These ten are United's ten busiest EWR routes into France,
            # Italy, Spain and Portugal, ordered so he doesn't repeat a
            # country two years running wherever that was possible.
            *[
                (year, 8, "second-saturday", 14, "United Air Lines Inc.", airport, city, country, code, "transatlantic_2w")
                for year, airport, city, country, code in [
                    (2016, "CDG", "Paris", "France", "FR"),
                    (2017, "FCO", "Rome", "Italy", "IT"),
                    (2018, "BCN", "Barcelona", "Spain", "ES"),
                    (2019, "LIS", "Lisbon", "Portugal", "PT"),
                    (2020, "MXP", "Milan", "Italy", "IT"),
                    (2021, "MAD", "Madrid", "Spain", "ES"),
                    (2022, "NCE", "Nice", "France", "FR"),
                    (2023, "VCE", "Venice", "Italy", "IT"),
                    (2024, "OPO", "Porto", "Portugal", "PT"),
                    (2025, "NAP", "Naples", "Italy", "IT"),
                ]
            ],
            # Christmas week in Houston, same dates every year. Domestic, so
            # unverifiable here -- see this module's docstring.
            *[
                (year, 12, 21, 7, "United Air Lines Inc.", "IAH", "Houston", "United States", "US", "domestic_1w")
                for year in range(2016, 2026)
            ],
        ],
    },
    {
        "name": "Edward Hopper",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "EH",
        "first_year": 2016,
        "age_in_first_year": 52,
        "base": {
            "city": "San Francisco",
            "country": "United States",
            "country_code": "US",
            "airport": "SFO",
        },
        # One long Asia trip every autumn, cities repeating freely (Tokyo
        # three times, Hong Kong twice) -- the brief was a region, not a
        # checklist. The carrier on each leg is that route's busiest operator
        # out of SFO in the T-100 data, which is why this itinerary isn't
        # all one airline: Cathay Pacific dominates SFO-Hong Kong and EVA Air
        # dominates SFO-Taipei, while United leads the rest.
        "itinerary": [
            (year, 10, "second-saturday", 12, carrier, airport, city, country, code, "transpacific_2w")
            for year, carrier, airport, city, country, code in [
                (2016, "United Air Lines Inc.", "HND", "Tokyo", "Japan", "JP"),
                (2017, "Cathay Pacific Airways Ltd.", "HKG", "Hong Kong", "Hong Kong", "HK"),
                (2018, "United Air Lines Inc.", "ICN", "Seoul", "South Korea", "KR"),
                (2019, "Eva Airways Corporation", "TPE", "Taipei", "Taiwan", "TW"),
                (2020, "United Air Lines Inc.", "HND", "Tokyo", "Japan", "JP"),
                (2021, "United Air Lines Inc.", "SIN", "Singapore", "Singapore", "SG"),
                (2022, "United Air Lines Inc.", "KIX", "Osaka", "Japan", "JP"),
                (2023, "Cathay Pacific Airways Ltd.", "HKG", "Hong Kong", "Hong Kong", "HK"),
                (2024, "United Air Lines Inc.", "PVG", "Shanghai", "China", "CN"),
                (2025, "United Air Lines Inc.", "HND", "Tokyo", "Japan", "JP"),
            ]
        ],
    },
    {
        "name": "Georgia O'Keeffe",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "GOK",
        "first_year": 2021,
        "age_in_first_year": 44,
        "base": {
            "city": "Houston",
            "country": "United States",
            "country_code": "US",
            "airport": "IAH",
        },
        # One week in Mexico every January, a different city each time. All
        # five are United routes from its Houston hub; IAH-CUN and IAH-MEX
        # are the two busiest US-Mexico routes United flies in this data.
        "itinerary": [
            (year, 1, "second-saturday", 7, "United Air Lines Inc.", airport, city, "Mexico", "MX", "mexico_1w")
            for year, airport, city in [
                (2021, "MEX", "Mexico City"),
                (2022, "CUN", "Cancun"),
                (2023, "SJD", "San Jose del Cabo"),
                (2024, "GDL", "Guadalajara"),
                (2025, "MID", "Merida"),
            ]
        ],
    },
    {
        "name": "Pablo Picasso",
        "nationality": "Spanish",
        "gender": "Male",
        "id_prefix": "PP",
        "first_year": 2021,
        "age_in_first_year": 39,
        "base": {
            "city": "Barcelona",
            "country": "Spain",
            "country_code": "ES",
            "airport": "BCN",
        },
        # Four US trips, one each August. The only non-US base among these
        # travelers, which matters for a recommender: without it every
        # hand-authored home country is the same one. American Airlines on
        # the Chicago leg because it outflies United on BCN-ORD in this data
        # (13,957 passengers to 9,137); United on the other three.
        "itinerary": [
            (year, 8, "second-saturday", 7, carrier, airport, city, "United States", "US", "transatlantic_1w")
            for year, carrier, airport, city in [
                (2021, "United Air Lines Inc.", "EWR", "New York"),
                (2022, "United Air Lines Inc.", "IAD", "Washington, D.C."),
                (2023, "American Airlines Inc.", "ORD", "Chicago"),
                (2024, "United Air Lines Inc.", "SFO", "San Francisco"),
            ]
        ],
    },
    {
        "name": "Jackson Pollock",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "JP",
        "first_year": 2025,
        "age_in_first_year": 35,
        "base": {
            "city": "Chicago",
            "country": "United States",
            "country_code": "US",
            "airport": "ORD",
        },
        # Toronto the first WORKING week of every month of 2025 -- departing
        # the first Monday, five days. Twelve trips, one route, one year:
        # what a recommender should recognize as a commute rather than as
        # twelve holidays. United is the busiest of the eight carriers flying
        # ORD-YYZ in this data.
        "itinerary": [
            (2025, month, "first-monday", 5, "United Air Lines Inc.", "YYZ", "Toronto", "Canada", "CA", "shorthaul_1w")
            for month in range(1, 13)
        ],
    },
    {
        "name": "Andy Warhol",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "AW",
        "first_year": 2020,
        "age_in_first_year": 41,
        "base": {
            "city": "Houston",
            "country": "United States",
            "country_code": "US",
            "airport": "IAH",
        },
        # Mexico two or three times a year, every year, working through all
        # twelve routes mainline United flies from Houston -- see
        # warhol_itinerary(). He shares both a base and a destination country
        # with Georgia O'Keeffe on purpose: same IAH, same Mexico, but she
        # goes once a year in January and he goes two or three times spread
        # across it. Two travelers who look identical in aggregate and
        # nothing alike in rhythm is a useful thing for a recommender to have
        # to distinguish.
        "itinerary": warhol_itinerary(),
    },
    {
        "name": "Miles Davis",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "MD",
        "first_year": 2020,
        "age_in_first_year": 44,
        "base": {
            "city": "Boston",
            "country": "United States",
            "country_code": "US",
            "airport": "BOS",
        },
        # Four European trips a year, six nights each, twice around Delta's
        # whole Boston transatlantic network -- see DELTA_BOS_EUROPE. Months
        # avoid high summer, which is when this itinerary's destinations are
        # most crowded and most expensive.
        "itinerary": european_itinerary(DELTA_BOS_EUROPE, range(2020, 2026), [3, 6, 9, 11], 6),
    },
    {
        "name": "Stan Getz",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "SG",
        "first_year": 2020,
        "age_in_first_year": 38,
        "base": {
            "city": "New York City",
            "country": "United States",
            "country_code": "US",
            # JFK, not EWR: he flies Delta, and Delta's New York
            # transatlantic operation is at JFK. Joaquin Sorolla is also
            # New York-based and shares none of this -- United, out of
            # Newark. Two travelers, one city, no overlap in how they fly.
            "airport": "JFK",
        },
        "itinerary": [
            # Four European trips a year -- all 24 of Delta's JFK
            # transatlantic routes, one apiece, no repeats.
            *european_itinerary(DELTA_JFK_EUROPE, range(2020, 2026), [2, 5, 9, 11], 6),
            # Plus a week in Cancun every July. Delta flies JFK-CUN (44,664
            # passengers in this data), so the summer habit is on the same
            # airline as everything else he does.
            *[
                (year, 7, "second-saturday", 7, "Delta Air Lines Inc.", "CUN", "Cancun", "Mexico", "MX", "mexico_1w")
                for year in range(2020, 2026)
            ],
        ],
    },
    {
        "name": "Chet Baker",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CB",
        "first_year": 2024,
        "age_in_first_year": 46,
        "base": {
            "city": "Atlanta",
            "country": "United States",
            "country_code": "US",
            "airport": "ATL",
        },
        # New York every other week for two years, Monday to Friday: 52 trips
        # on one route with no holiday in any of them. The only purely
        # business traveler here, and the reason the set isn't all leisure
        # patterns. ATL-JFK is domestic, so it's exempt from the route check
        # (see this module's docstring) -- Atlanta is Delta's largest hub and
        # New York its second-largest transatlantic one, so the route is real
        # regardless.
        "itinerary": biweekly_commute(
            2024, 2025, "Delta Air Lines Inc.", "JFK", "New York", "United States", "US", 4, "domestic_workweek"
        ),
    },
    {
        "name": "Bill Evans",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "BE",
        "first_year": 2016,
        "age_in_first_year": 51,
        "base": {
            "city": "Detroit",
            "country": "United States",
            "country_code": "US",
            "airport": "DTW",
        },
        # Ten days in Amsterdam every April for a decade, and nowhere else.
        # DTW-AMS is Delta's busiest Detroit route (93,829 passengers) and
        # its longest-running transatlantic one, so the habit is at least a
        # plausible one to have. Deliberately the narrowest profile here:
        # a traveler with ten trips and one destination is the hardest case
        # to recommend anything new to, which makes him worth having.
        "itinerary": [
            (year, 4, "second-saturday", 10, "Delta Air Lines Inc.", "AMS", "Amsterdam", "Netherlands", "NL", "transatlantic_10d")
            for year in range(2016, 2026)
        ],
    },
    {
        "name": "John Coltrane",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "JC",
        "first_year": 2021,
        "age_in_first_year": 47,
        "base": {
            "city": "Minneapolis",
            "country": "United States",
            "country_code": "US",
            "airport": "MSP",
        },
        # Three winter beach trips a year and nothing in any other season --
        # January, February, March, every year, working through Delta's
        # Caribbean and Mexican network out of Minneapolis. The only traveler
        # here whose pattern is defined by WHEN rather than where: eight
        # different countries, all of them warm, all of them in the same
        # three months.
        "itinerary": rotating_itinerary(DELTA_MSP_WINTER, range(2021, 2026), [1, 2, 3], 7, "caribbean_1w"),
    },
    {
        "name": "Thelonious Monk",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "TM",
        "first_year": 2019,
        "age_in_first_year": 55,
        "base": {
            "city": "Los Angeles",
            "country": "United States",
            "country_code": "US",
            "airport": "LAX",
        },
        # Australia and New Zealand, twice a year, fourteen nights at a time
        # -- February and October, which are the southern hemisphere's late
        # summer and spring rather than ours. Delta flies only four South
        # Pacific routes from LAX, so his world is four cities wide and
        # roughly 7,500 miles away.
        "itinerary": rotating_itinerary(DELTA_LAX_PACIFIC, range(2019, 2026), [2, 10], 14, "transpacific_2w"),
    },
    {
        "name": "Wes Montgomery",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "WM",
        "first_year": 2016,
        "age_in_first_year": 43,
        "base": {
            "city": "Seattle",
            "country": "United States",
            "country_code": "US",
            "airport": "SEA",
        },
        # Asia twice a year -- and then a two-year hole. Every other traveler
        # here flies straight through 2020 and 2021 because their briefs
        # asked for unbroken runs of years; this one doesn't, and that's the
        # point. A traveler who stops for two years and then resumes exactly
        # as before is a shape any recommender working on real travel data
        # will meet constantly, and this is the only place in this dataset it
        # exists.
        "itinerary": rotating_itinerary(
            DELTA_SEA_ASIA, [2016, 2017, 2018, 2019, 2022, 2023, 2024, 2025], [5, 10], 12, "transpacific_2w"
        ),
    },
    # -----------------------------------------------------------------------
    # Domestic-only travelers: one US city, one to three times a year, to see
    # family, 2018-2025. Four on United (painters) and four on Delta (jazz
    # musicians), keeping this file's naming convention -- see the module
    # docstring. Every route is one its airline really flies, checked against
    # the T-100 domestic segment file.
    # -----------------------------------------------------------------------
    {
        "name": "Edgar Degas",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ED",
        "first_year": 2018,
        "age_in_first_year": 57,
        "base": {"city": "Denver", "country": "United States", "country_code": "US", "airport": "DEN"},
        # Boston twice a year: a summer week and Christmas.
        "itinerary": family_visits(
            range(2018, 2026), [(7, 6), (12, 6)], "United Air Lines Inc.", "BOS", "Boston", "family_visit_long"
        ),
    },
    {
        "name": "Alfred d'Orsay",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "AD",
        "first_year": 2018,
        "age_in_first_year": 44,
        "base": {"city": "Washington, D.C.", "country": "United States", "country_code": "US", "airport": "IAD"},
        # Pittsburgh once a year at Christmas, and that is his entire travel
        # history -- the sparsest traveler in the dataset, on purpose.
        "itinerary": family_visits(
            range(2018, 2026), [(12, 5)], "United Air Lines Inc.", "PIT", "Pittsburgh", "family_visit_short"
        ),
    },
    {
        "name": "Pierre-Auguste Renoir",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "PAR",
        "first_year": 2018,
        "age_in_first_year": 61,
        "base": {"city": "San Francisco", "country": "United States", "country_code": "US", "airport": "SFO"},
        # San Diego three times a year -- spring, summer, Christmas. Short
        # enough to do often, which is exactly why he does.
        "itinerary": family_visits(
            range(2018, 2026),
            [(4, 4), (8, 5), (12, 6)],
            "United Air Lines Inc.",
            "SAN",
            "San Diego",
            "family_visit_short",
        ),
    },
    {
        "name": "Claude Monet",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CM",
        "first_year": 2018,
        "age_in_first_year": 52,
        "base": {"city": "Chicago", "country": "United States", "country_code": "US", "airport": "ORD"},
        # Cleveland for Thanksgiving and Christmas. Jackson Pollock is also
        # Chicago-based and also flies United: one goes to Toronto monthly on
        # business, the other to Cleveland twice a year for the holidays.
        # Same city, same airline, nothing else in common.
        "itinerary": family_visits(
            range(2018, 2026), [(11, 4), (12, 5)], "United Air Lines Inc.", "CLE", "Cleveland", "family_visit_short"
        ),
    },
    {
        "name": "Duke Ellington",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "DE",
        "first_year": 2018,
        "age_in_first_year": 48,
        "base": {"city": "Salt Lake City", "country": "United States", "country_code": "US", "airport": "SLC"},
        "itinerary": family_visits(
            range(2018, 2026), [(6, 6), (12, 6)], "Delta Air Lines Inc.", "PDX", "Portland", "family_visit_short"
        ),
    },
    {
        "name": "Ella Fitzgerald",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "EF",
        "first_year": 2018,
        "age_in_first_year": 33,
        "base": {"city": "Cincinnati", "country": "United States", "country_code": "US", "airport": "CVG"},
        # Orlando three times a year -- the most-travelled of the domestic
        # eight, and still only ever to one place.
        "itinerary": family_visits(
            range(2018, 2026), [(3, 5), (7, 6), (12, 6)], "Delta Air Lines Inc.", "MCO", "Orlando", "family_visit_short"
        ),
    },
    {
        "name": "Sarah Vaughan",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "SV",
        "first_year": 2018,
        "age_in_first_year": 59,
        "base": {"city": "New York City", "country": "United States", "country_code": "US", "airport": "LGA"},
        # New Orleans twice a year. Third New York-based traveler here and
        # the third distinct New York airport: Sorolla flies United from EWR,
        # Stan Getz flies Delta from JFK, this one flies Delta from LGA.
        "itinerary": family_visits(
            range(2018, 2026), [(5, 5), (11, 5)], "Delta Air Lines Inc.", "MSY", "New Orleans", "family_visit_long"
        ),
    },
    {
        "name": "Charlie Parker",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CP",
        "first_year": 2018,
        "age_in_first_year": 41,
        "base": {"city": "Nashville", "country": "United States", "country_code": "US", "airport": "BNA"},
        "itinerary": family_visits(
            range(2018, 2026), [(12, 5)], "Delta Air Lines Inc.", "DTW", "Detroit", "family_visit_short"
        ),
    },
    # --- American Airlines, group 1: international only, one destination ---
    # The hardest travelers to recommend anything to, and deliberately so:
    # a decade of data that says nothing except "London, again". Each one's
    # route is among American's busiest from that hub in the T-100 file, so
    # the single destination is at least the obvious one to be loyal to.
    {
        "name": "Albert Einstein",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "AE",
        "first_year": 2016,
        "age_in_first_year": 47,
        "base": {
            "city": "Dallas",
            "country": "United States",
            "country_code": "US",
            "airport": "DFW",  # American's largest hub
        },
        # London twice a year for ten years: 20 trips, one destination.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [
                (3, "second-saturday", 7, "LHR", "London", "United Kingdom", "GB", "transatlantic_1w"),
                (9, "second-saturday", 7, "LHR", "London", "United Kingdom", "GB", "transatlantic_1w"),
            ],
        ),
    },
    {
        "name": "Marie Curie",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "MC",
        "first_year": 2018,
        "age_in_first_year": 41,
        "base": {
            "city": "Miami",
            "country": "United States",
            "country_code": "US",
            "airport": "MIA",
        },
        # April and October -- autumn and spring in Buenos Aires, which is
        # the one thing in this file that only makes sense south of the
        # equator, and a case any seasonal scoring should get right.
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (4, "second-saturday", 8, "EZE", "Buenos Aires", "Argentina", "AR", "latin_america_1w"),
                (10, "second-saturday", 8, "EZE", "Buenos Aires", "Argentina", "AR", "latin_america_1w"),
            ],
        ),
    },
    {
        "name": "Niels Bohr",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "NB",
        "first_year": 2016,
        "age_in_first_year": 55,
        "base": {
            "city": "Philadelphia",
            "country": "United States",
            "country_code": "US",
            "airport": "PHL",
        },
        # Ten days in Lisbon every June, once a year, for a decade -- the
        # lowest-frequency traveler in the file who still has a pattern.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [(6, "second-saturday", 10, "LIS", "Lisbon", "Portugal", "PT", "transatlantic_10d")],
        ),
    },
    # --- American Airlines, group 2: domestic only, holiday travel --------
    # Superficially the same shape as the eight family visitors above, and
    # meant to be told apart from them: these trips are pinned to holidays
    # (Thanksgiving, Christmas, Memorial Day, July 4th) and they're paid for.
    # A traveler with no accommodation cost is visiting relatives; one with a
    # hotel bill chose the destination. That distinction is the whole reason
    # both groups exist.
    {
        "name": "Isaac Newton",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "IN",
        "first_year": 2016,
        "age_in_first_year": 44,
        "base": {
            "city": "Chicago",
            "country": "United States",
            "country_code": "US",
            "airport": "ORD",
        },
        # Denver at Thanksgiving and again over Christmas. The Thanksgiving
        # departure is computed from the fourth Thursday of November (see
        # thanksgiving_departure) rather than pinned to a date, so it lands
        # on the Tuesday before, where it actually falls, in every year.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [
                (11, "thanksgiving", 5, "DEN", "Denver", "United States", "US", "domestic_holiday"),
                (12, 22, 8, "DEN", "Denver", "United States", "US", "domestic_holiday"),
            ],
        ),
    },
    {
        "name": "Galileo Galilei",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "GG",
        "first_year": 2018,
        "age_in_first_year": 38,
        "base": {
            "city": "Washington",
            "country": "United States",
            "country_code": "US",
            "airport": "DCA",
        },
        # Orlando three times a year, on the three long weekends Americans
        # actually take: Memorial Day (the last Monday in May, hence the
        # last-monday rule), the 4th of July, and Christmas.
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (5, "last-monday", 4, "MCO", "Orlando", "United States", "US", "domestic_holiday"),
                (7, 2, 6, "MCO", "Orlando", "United States", "US", "domestic_holiday"),
                (12, 22, 7, "MCO", "Orlando", "United States", "US", "domestic_holiday"),
            ],
        ),
    },
    {
        "name": "Louis Pasteur",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "LP",
        "first_year": 2016,
        "age_in_first_year": 61,
        "base": {
            "city": "Philadelphia",
            "country": "United States",
            "country_code": "US",
            "airport": "PHL",
        },
        # Palm Beach in February and again at Christmas -- the snowbird
        # pattern, and the second traveler based at PHL, which is the point:
        # Niels Bohr flies the same airline out of the same airport and
        # never once leaves for the same reason.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [
                (2, 14, 7, "PBI", "West Palm Beach", "United States", "US", "domestic_holiday"),
                (12, 23, 9, "PBI", "West Palm Beach", "United States", "US", "domestic_holiday"),
            ],
        ),
    },
    # --- American Airlines, group 3: mixed domestic and international -----
    # The only travelers in this file whose year contains both. Each flies
    # two international routes and two domestic ones out of one hub, all
    # four verified against the two T-100 files -- which means these four are
    # also the only ones whose route check exercises both files at once.
    {
        "name": "Charles Darwin",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CD",
        "first_year": 2017,
        "age_in_first_year": 50,
        "base": {
            "city": "Miami",
            "country": "United States",
            "country_code": "US",
            "airport": "MIA",
        },
        # South America twice a year, plus two domestic weeks. Shares a base
        # and an airline with Marie Curie and overlaps her on nothing else.
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (3, "second-saturday", 10, "GRU", "Sao Paulo", "Brazil", "BR", "latin_america_1w"),
                (5, "second-saturday", 5, "BOS", "Boston", "United States", "US", "domestic_1w"),
                (9, "second-saturday", 10, "LIM", "Lima", "Peru", "PE", "latin_america_1w"),
                (11, "second-saturday", 5, "LAX", "Los Angeles", "United States", "US", "domestic_1w"),
            ],
        ),
    },
    {
        "name": "Nikola Tesla",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "NT",
        "first_year": 2017,
        "age_in_first_year": 43,
        "base": {
            "city": "Dallas",
            "country": "United States",
            "country_code": "US",
            "airport": "DFW",
        },
        # Cancun in winter, London in summer, San Antonio and Nashville in
        # between: American's two busiest international routes from DFW and
        # two of its busiest domestic ones.
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (2, "second-saturday", 7, "CUN", "Cancun", "Mexico", "MX", "mexico_1w"),
                (4, "second-saturday", 4, "SAT", "San Antonio", "United States", "US", "domestic_1w"),
                (7, "second-saturday", 9, "LHR", "London", "United Kingdom", "GB", "transatlantic_10d"),
                (10, "second-saturday", 4, "BNA", "Nashville", "United States", "US", "domestic_1w"),
            ],
        ),
    },
    {
        "name": "Stephen Hawking",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "SH",
        "first_year": 2018,
        "age_in_first_year": 36,
        "base": {
            "city": "Los Angeles",
            "country": "United States",
            "country_code": "US",
            "airport": "LAX",
        },
        # Tokyo and Sydney -- the two longest legs anyone flies in this file
        # -- against two transcontinental domestic hops. The widest spread
        # of trip lengths of any single traveler here.
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (3, "second-saturday", 5, "JFK", "New York City", "United States", "US", "domestic_1w"),
                (6, "second-saturday", 14, "SYD", "Sydney", "Australia", "AU", "transpacific_2w"),
                (9, "second-saturday", 4, "MIA", "Miami", "United States", "US", "domestic_1w"),
                (11, "second-saturday", 14, "HND", "Tokyo", "Japan", "JP", "transpacific_2w"),
            ],
        ),
    },
    {
        "name": "Richard Feynman",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "RF",
        "first_year": 2019,
        "age_in_first_year": 39,
        "base": {
            "city": "Charlotte",
            "country": "United States",
            "country_code": "US",
            "airport": "CLT",
        },
        # One international trip a year and two domestic ones -- the least
        # international of the mixed four, which is what makes it the mix
        # most people would recognise.
        "itinerary": annual_pattern(
            range(2019, 2026),
            [
                (4, "second-saturday", 4, "MSY", "New Orleans", "United States", "US", "shorthaul_1w"),
                (6, "second-saturday", 9, "MAD", "Madrid", "Spain", "ES", "transatlantic_10d"),
                (10, "second-saturday", 4, "PIT", "Pittsburgh", "United States", "US", "shorthaul_1w"),
            ],
        ),
    },
    # --- Southwest, group 1: international only, one destination ----------
    # Southwest flies no long-haul at all: its entire international network
    # in this data is Mexico, Central America and the Caribbean. So these
    # three are the file's short-haul international loyalists -- a shape no
    # United, Delta or American traveler here has, and one that matters,
    # because "flies abroad twice a year" means something completely
    # different at four hours than at ten.
    {
        "name": "Clark Kent",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CK",
        "first_year": 2016,
        "age_in_first_year": 34,
        "base": {
            "city": "Houston",
            "country": "United States",
            "country_code": "US",
            "airport": "HOU",  # Hobby, Southwest's Houston base -- not IAH
        },
        # Southwest's single busiest international route in this data.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [
                (2, "second-saturday", 7, "CUN", "Cancun", "Mexico", "MX", "mexico_1w"),
                (9, "second-saturday", 7, "CUN", "Cancun", "Mexico", "MX", "mexico_1w"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    {
        "name": "Bruce Wayne",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "BW",
        "first_year": 2018,
        "age_in_first_year": 45,
        "base": {
            "city": "Baltimore",
            "country": "United States",
            "country_code": "US",
            "airport": "BWI",
        },
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (1, "second-saturday", 7, "MBJ", "Montego Bay", "Jamaica", "JM", "caribbean_1w"),
                (8, "second-saturday", 7, "MBJ", "Montego Bay", "Jamaica", "JM", "caribbean_1w"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    {
        "name": "Diana Prince",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "DP",
        "first_year": 2017,
        "age_in_first_year": 37,
        "base": {
            "city": "Phoenix",
            "country": "United States",
            "country_code": "US",
            "airport": "PHX",
        },
        # Fourth woman in the file, out of forty-one travelers. Worth saying
        # plainly rather than leaving to be discovered in a group-by.
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (3, "second-saturday", 6, "SJD", "San Jose del Cabo", "Mexico", "MX", "mexico_1w"),
                (11, "second-saturday", 6, "SJD", "San Jose del Cabo", "Mexico", "MX", "mexico_1w"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    # --- Southwest, group 2: domestic only, holiday travel ----------------
    {
        "name": "Barry Allen",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "BA",
        "first_year": 2016,
        "age_in_first_year": 29,
        "base": {
            "city": "Chicago",
            "country": "United States",
            "country_code": "US",
            "airport": "MDW",  # Midway, Southwest's Chicago base -- not ORD
        },
        # Second Chicago-based traveler, and deliberately the other airport:
        # Jackson Pollock and Claude Monet fly out of O'Hare, this one flies
        # out of Midway, which is what a Southwest loyalist in Chicago does.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [
                (5, "last-monday", 4, "TPA", "Tampa", "United States", "US", "domestic_holiday"),
                (12, 22, 8, "TPA", "Tampa", "United States", "US", "domestic_holiday"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    {
        "name": "Hal Jordan",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "HJ",
        "first_year": 2017,
        "age_in_first_year": 42,
        "base": {
            "city": "Denver",
            "country": "United States",
            "country_code": "US",
            "airport": "DEN",
        },
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (7, 2, 6, "SAN", "San Diego", "United States", "US", "domestic_holiday"),
                (11, "thanksgiving", 5, "SAN", "San Diego", "United States", "US", "domestic_holiday"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    {
        "name": "Arthur Curry",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "AC",
        "first_year": 2018,
        "age_in_first_year": 36,
        "base": {
            "city": "Nashville",
            "country": "United States",
            "country_code": "US",
            "airport": "BNA",
        },
        # Three holidays a year to the same Gulf coast town. Shares Nashville
        # with Charlie Parker, who flies Delta to see relatives in Detroit --
        # same city, same frequency, nothing else in common.
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (5, "last-monday", 4, "SRQ", "Sarasota", "United States", "US", "domestic_holiday"),
                (7, 2, 6, "SRQ", "Sarasota", "United States", "US", "domestic_holiday"),
                (12, 22, 8, "SRQ", "Sarasota", "United States", "US", "domestic_holiday"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    # --- Southwest, group 3: mixed domestic and international -------------
    {
        "name": "Victor Stone",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "VS",
        "first_year": 2017,
        "age_in_first_year": 31,
        "base": {
            "city": "Orlando",
            "country": "United States",
            "country_code": "US",
            "airport": "MCO",
        },
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (2, "second-saturday", 5, "NAS", "Nassau", "Bahamas", "BS", "caribbean_1w"),
                (5, "second-saturday", 4, "BWI", "Baltimore", "United States", "US", "shorthaul_1w"),
                (9, "second-saturday", 8, "SJO", "San Jose", "Costa Rica", "CR", "latin_america_1w"),
                (11, "second-saturday", 4, "STL", "St. Louis", "United States", "US", "shorthaul_1w"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    {
        "name": "Oliver Queen",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "OQ",
        "first_year": 2017,
        "age_in_first_year": 40,
        "base": {
            "city": "Denver",
            "country": "United States",
            "country_code": "US",
            "airport": "DEN",
        },
        # Second Denver traveler on the same airline as Hal Jordan, and the
        # pair a recommender should be able to separate: same hub, same
        # carrier, one never leaves the country and the other does twice a
        # year.
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (1, "second-saturday", 7, "SJD", "San Jose del Cabo", "Mexico", "MX", "mexico_1w"),
                (4, "second-saturday", 4, "SAT", "San Antonio", "United States", "US", "domestic_1w"),
                (8, "second-saturday", 5, "SEA", "Seattle", "United States", "US", "domestic_1w"),
                (10, "second-saturday", 7, "CUN", "Cancun", "Mexico", "MX", "mexico_1w"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    {
        "name": "Billy Batson",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "BB",
        "first_year": 2019,
        "age_in_first_year": 26,
        "base": {
            "city": "St. Louis",
            "country": "United States",
            "country_code": "US",
            "airport": "STL",
        },
        # The youngest traveler in the file, and the only one whose single
        # international trip a year is outnumbered two-to-one by domestic
        # ones -- the most common mix there is.
        "itinerary": annual_pattern(
            range(2019, 2026),
            [
                (3, "second-saturday", 7, "CUN", "Cancun", "Mexico", "MX", "mexico_1w"),
                (6, "second-saturday", 4, "MCO", "Orlando", "United States", "US", "domestic_1w"),
                (10, "second-saturday", 4, "PHX", "Phoenix", "United States", "US", "domestic_1w"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    {
        "name": "Dick Grayson",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "DG",
        "first_year": 2018,
        "age_in_first_year": 28,
        "base": {
            "city": "Kansas City",
            "country": "United States",
            "country_code": "US",
            "airport": "MCI",
        },
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (2, "second-saturday", 7, "CUN", "Cancun", "Mexico", "MX", "mexico_1w"),
                (5, "second-saturday", 4, "LAS", "Las Vegas", "United States", "US", "domestic_1w"),
                (9, "second-saturday", 5, "TPA", "Tampa", "United States", "US", "domestic_1w"),
            ],
            carrier="Southwest Airlines Co.",
        ),
    },
    # --- Alaska, group 1: international only, one destination -------------
    # Alaska's international network in this data splits cleanly in three:
    # transpacific out of Seattle, Mexico and Central America out of the
    # California airports, and the South Pacific out of Honolulu. These
    # three take one branch each.
    {
        "name": "Peter Parker",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "PPK",  # not "PP" -- Pablo Picasso already has that
        "first_year": 2016,
        "age_in_first_year": 25,
        "base": {
            "city": "Seattle",
            "country": "United States",
            "country_code": "US",
            "airport": "SEA",
        },
        # Tokyo twice a year for a decade. Wes Montgomery also flies to Asia
        # out of Seattle, on Delta, with gaps -- this one never varies and
        # never stops, which is the contrast worth having.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [
                (4, "second-saturday", 12, "NRT", "Tokyo", "Japan", "JP", "transpacific_2w"),
                (10, "second-saturday", 12, "NRT", "Tokyo", "Japan", "JP", "transpacific_2w"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    {
        "name": "Tony Stark",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "TS",
        "first_year": 2017,
        "age_in_first_year": 48,
        "base": {
            "city": "Los Angeles",
            "country": "United States",
            "country_code": "US",
            "airport": "LAX",
        },
        # Short trips, twice a year, always to the same inland Mexican city
        # -- the one international loyalist here whose trips are shorter than
        # most people's domestic ones.
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (3, "second-saturday", 5, "GDL", "Guadalajara", "Mexico", "MX", "mexico_city_break"),
                (9, "second-saturday", 5, "GDL", "Guadalajara", "Mexico", "MX", "mexico_city_break"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    {
        "name": "Steve Rogers",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "SR",
        "first_year": 2016,
        "age_in_first_year": 52,
        "base": {
            "city": "Honolulu",
            "country": "United States",
            "country_code": "US",
            "airport": "HNL",
        },
        # The only traveler in the file based outside the mainland, which
        # makes his "domestic" and his "international" both unusual: Sydney
        # is a shorter flight from here than New York is.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [(2, "second-saturday", 14, "SYD", "Sydney", "Australia", "AU", "transpacific_2w")],
            carrier="Alaska Airlines Inc.",
        ),
    },
    # --- Alaska, group 2: domestic only, holiday travel -------------------
    {
        "name": "Bruce Banner",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "BBN",  # not "BB" -- Billy Batson already has that
        "first_year": 2016,
        "age_in_first_year": 44,
        "base": {
            "city": "Seattle",
            "country": "United States",
            "country_code": "US",
            "airport": "SEA",
        },
        # Maui at Christmas and again in high summer. Domestic by passport
        # and a six-hour flight over open ocean by any other measure -- the
        # clearest case in the file that "domestic" says nothing about
        # distance.
        "itinerary": annual_pattern(
            range(2016, 2026),
            [
                (7, 2, 7, "OGG", "Kahului", "United States", "US", "domestic_holiday"),
                (12, 22, 9, "OGG", "Kahului", "United States", "US", "domestic_holiday"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    {
        "name": "Thor Odinson",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "TO",
        "first_year": 2017,
        "age_in_first_year": 39,
        "base": {
            "city": "Portland",
            "country": "United States",
            "country_code": "US",
            "airport": "PDX",
        },
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (2, 14, 7, "PSP", "Palm Springs", "United States", "US", "domestic_holiday"),
                (11, "thanksgiving", 5, "PSP", "Palm Springs", "United States", "US", "domestic_holiday"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    {
        "name": "Natasha Romanoff",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "NR",
        "first_year": 2018,
        "age_in_first_year": 35,
        "base": {
            "city": "San Francisco",
            "country": "United States",
            "country_code": "US",
            "airport": "SFO",
        },
        # Fifth and last woman in the file. Orlando is also Ella Fitzgerald's
        # and Galileo Galilei's destination, on two other airlines from two
        # other coasts -- the most-visited city here that nobody lives in.
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (5, "last-monday", 4, "MCO", "Orlando", "United States", "US", "domestic_holiday"),
                (12, 22, 7, "MCO", "Orlando", "United States", "US", "domestic_holiday"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    # --- Alaska, group 3: mixed domestic and international ----------------
    {
        "name": "Clint Barton",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CBA",  # not "CB" -- Chet Baker already has that
        "first_year": 2017,
        "age_in_first_year": 43,
        "base": {
            "city": "Seattle",
            "country": "United States",
            "country_code": "US",
            "airport": "SEA",
        },
        # Seoul and Toronto abroad, Anchorage and Spokane at home: the
        # widest spread of flight lengths of anyone here, from 280 miles to
        # 5,200, all on one airline out of one airport.
        "itinerary": annual_pattern(
            range(2017, 2026),
            [
                (3, "second-saturday", 4, "GEG", "Spokane", "United States", "US", "shorthaul_1w"),
                (6, "second-saturday", 7, "ANC", "Anchorage", "United States", "US", "domestic_1w"),
                (9, "second-saturday", 12, "ICN", "Seoul", "South Korea", "KR", "transpacific_2w"),
                (11, "second-saturday", 4, "YYZ", "Toronto", "Canada", "CA", "shorthaul_1w"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    {
        "name": "Matt Murdock",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "MM",
        "first_year": 2018,
        "age_in_first_year": 37,
        "base": {
            "city": "San Francisco",
            "country": "United States",
            "country_code": "US",
            "airport": "SFO",
        },
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (1, "second-saturday", 7, "SJD", "San Jose del Cabo", "Mexico", "MX", "mexico_1w"),
                (4, "second-saturday", 4, "JFK", "New York City", "United States", "US", "domestic_1w"),
                (8, "second-saturday", 6, "PVR", "Puerto Vallarta", "Mexico", "MX", "mexico_1w"),
                (11, "second-saturday", 5, "MCO", "Orlando", "United States", "US", "domestic_1w"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    {
        "name": "Logan",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "LG",
        "first_year": 2019,
        "age_in_first_year": 46,
        "base": {
            "city": "Los Angeles",
            "country": "United States",
            "country_code": "US",
            "airport": "LAX",
        },
        # The only single-name traveler in the file, which is worth knowing
        # before anything downstream tries to split a name on a space.
        "itinerary": annual_pattern(
            range(2019, 2026),
            [
                (2, "second-saturday", 8, "LIR", "Liberia", "Costa Rica", "CR", "latin_america_1w"),
                (5, "second-saturday", 7, "KOA", "Kailua-Kona", "United States", "US", "domestic_holiday"),
                (9, "second-saturday", 7, "BZE", "Belize City", "Belize", "BZ", "latin_america_1w"),
                (11, "second-saturday", 4, "EWR", "Newark", "United States", "US", "domestic_1w"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    {
        "name": "Stephen Strange",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "SS",
        "first_year": 2018,
        "age_in_first_year": 47,
        "base": {
            "city": "San Diego",
            "country": "United States",
            "country_code": "US",
            "airport": "SAN",
        },
        "itinerary": annual_pattern(
            range(2018, 2026),
            [
                (1, "second-saturday", 7, "SJD", "San Jose del Cabo", "Mexico", "MX", "mexico_1w"),
                (4, "second-saturday", 4, "BOI", "Boise", "United States", "US", "shorthaul_1w"),
                (7, "second-saturday", 8, "HNL", "Honolulu", "United States", "US", "domestic_holiday"),
                (10, "second-saturday", 6, "PVR", "Puerto Vallarta", "Mexico", "MX", "mexico_1w"),
            ],
            carrier="Alaska Airlines Inc.",
        ),
    },
    # --- The wanderers: thirty-one travelers loyal to no airline ----------
    # Everything above this line is somebody's loyalist. These thirty-one are
    # the control group -- they fly whatever serves the route, so not one leg
    # below names an airline. ANY_CARRIER resolves each from the T-100 data
    # at build time, stepping through that route's operators in volume order,
    # so a New Yorker who flies to London four times turns up on British
    # Airways, then Virgin Atlantic, then American, then Delta.
    #
    # They're spread two per city (three in New York) across the fifteen most
    # populous US cities, which does two things nothing above does: it makes
    # the home-city side of the data look roughly like where Americans
    # actually live, and it gives eight cities their FIRST resident here, so
    # a recommender can no longer assume every traveler departs from a hub
    # some airline happens to run.
    {
        "name": "Zeus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ZEU",
        "first_year": 2016,
        "age_in_first_year": 58,
        "base": {
            "city": "New York City",
            "country": "United States",
            "country_code": "US",
            "airport": "JFK",
        },
        "itinerary": wandering_itinerary(
            ['LHR', 'CDG', 'MCO', 'LAX', 'CUN', 'SFO'],
            range(2016, 2026),
            (4, 8, 11),
        ),
    },
    {
        "name": "Hermes",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "HRM",
        "first_year": 2018,
        "age_in_first_year": 31,
        "base": {
            "city": "New York City",
            "country": "United States",
            "country_code": "US",
            "airport": "LGA",
        },
        "itinerary": wandering_itinerary(
            ['YYZ', 'MIA', 'ORD', 'NAS', 'DFW', 'ATL'],
            range(2018, 2026),
            (2, 5, 9, 11),
        ),
    },
    {
        "name": "Narcissus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "NAR",
        "first_year": 2019,
        "age_in_first_year": 27,
        "base": {
            "city": "New York City",
            "country": "United States",
            "country_code": "US",
            "airport": "EWR",
        },
        "itinerary": wandering_itinerary(
            ['LIS', 'MCO', 'DUB', 'CLT', 'CUN', 'SFO'],
            range(2019, 2026),
            (3, 7, 10),
        ),
    },
    {
        "name": "Apollo",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "APO",
        "first_year": 2017,
        "age_in_first_year": 34,
        "base": {
            "city": "Los Angeles",
            "country": "United States",
            "country_code": "US",
            "airport": "LAX",
        },
        "itinerary": wandering_itinerary(
            ['HND', 'LAS', 'GDL', 'SEA', 'SYD', 'DEN'],
            range(2017, 2026),
            (3, 6, 10),
        ),
    },
    {
        "name": "Pandora",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "PAN",
        "first_year": 2019,
        "age_in_first_year": 29,
        "base": {
            "city": "Los Angeles",
            "country": "United States",
            "country_code": "US",
            "airport": "LAX",
        },
        "itinerary": wandering_itinerary(
            ['MEX', 'SFO', 'ICN', 'PHX', 'CUN', 'PDX'],
            range(2019, 2026),
            (2, 6, 9, 12),
        ),
    },
    {
        "name": "Hades",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "HAD",
        "first_year": 2016,
        "age_in_first_year": 52,
        "base": {
            "city": "Chicago",
            "country": "United States",
            "country_code": "US",
            "airport": "ORD",
        },
        "itinerary": wandering_itinerary(
            ['CUN', 'DEN', 'LHR', 'MCO', 'YYZ', 'SEA'],
            range(2016, 2026),
            (1, 5, 9),
        ),
    },
    {
        "name": "Artemis",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "ART",
        "first_year": 2018,
        "age_in_first_year": 26,
        "base": {
            "city": "Chicago",
            "country": "United States",
            "country_code": "US",
            "airport": "MDW",
        },
        "itinerary": wandering_itinerary(
            ['CUN', 'ATL', 'PHX', 'GDL', 'LAS', 'MCO'],
            range(2018, 2026),
            (3, 7, 11),
        ),
    },
    {
        "name": "Poseidon",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "POS",
        "first_year": 2016,
        "age_in_first_year": 55,
        "base": {
            "city": "Houston",
            "country": "United States",
            "country_code": "US",
            "airport": "IAH",
        },
        "itinerary": wandering_itinerary(
            ['MEX', 'DEN', 'SJO', 'LAX', 'AMS', 'MIA'],
            range(2016, 2026),
            (2, 6, 10),
        ),
    },
    {
        "name": "Circe",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "CIR",
        "first_year": 2019,
        "age_in_first_year": 38,
        "base": {
            "city": "Houston",
            "country": "United States",
            # Intercontinental, same as Poseidon, and NOT Hobby -- which is
            # worth recording, because Hobby was the first choice and the
            # data vetoed it. Every single destination Hobby serves has
            # exactly one operator above the floors above: Southwest. A
            # traveler based there can't help being a Southwest loyalist, so
            # a traveler defined by not being one can't be based there.
            "country_code": "US",
            "airport": "IAH",
        },
        "itinerary": wandering_itinerary(
            ['CUN', 'ATL', 'GDL', 'AUS', 'FRA', 'PHX'],
            range(2019, 2026),
            (1, 4, 8, 11),
        ),
    },
    {
        "name": "Prometheus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "PRO",
        "first_year": 2017,
        "age_in_first_year": 47,
        "base": {
            "city": "Phoenix",
            "country": "United States",
            "country_code": "US",
            "airport": "PHX",
        },
        "itinerary": wandering_itinerary(
            ['SJD', 'DEN', 'LHR', 'SEA', 'PVR', 'SFO'],
            range(2017, 2026),
            (3, 7, 10),
        ),
    },
    {
        "name": "Persephone",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "PSE",
        "first_year": 2020,
        "age_in_first_year": 24,
        "base": {
            "city": "Phoenix",
            "country": "United States",
            "country_code": "US",
            "airport": "PHX",
        },
        "itinerary": wandering_itinerary(
            ['CUN', 'LAX', 'YVR', 'MSP', 'MEX', 'PDX'],
            range(2020, 2026),
            (2, 5, 9, 12),
        ),
    },
    {
        "name": "Athena",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "ATH",
        "first_year": 2016,
        "age_in_first_year": 41,
        "base": {
            "city": "Philadelphia",
            "country": "United States",
            "country_code": "US",
            "airport": "PHL",
        },
        "itinerary": wandering_itinerary(
            ['LHR', 'MCO', 'DUB', 'DEN', 'CUN', 'TPA'],
            range(2016, 2026),
            (4, 8, 12),
        ),
    },
    {
        "name": "Odysseus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ODY",
        "first_year": 2018,
        "age_in_first_year": 49,
        "base": {
            "city": "Philadelphia",
            "country": "United States",
            "country_code": "US",
            "airport": "PHL",
        },
        "itinerary": wandering_itinerary(
            ['FCO', 'MIA', 'BCN', 'ORD', 'PUJ', 'BOS'],
            range(2018, 2026),
            (3, 6, 9, 11),
        ),
    },
    {
        "name": "Ares",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ARE",
        "first_year": 2019,
        "age_in_first_year": 36,
        "base": {
            "city": "San Antonio",
            "country": "United States",
            "country_code": "US",
            "airport": "SAT",
        },
        "itinerary": wandering_itinerary(
            ['MEX', 'DEN', 'MTY', 'LAS', 'CUN', 'ORD'],
            range(2019, 2026),
            (2, 7, 10),
        ),
    },
    {
        "name": "Medusa",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "MED",
        "first_year": 2020,
        "age_in_first_year": 33,
        "base": {
            "city": "San Antonio",
            "country": "United States",
            "country_code": "US",
            "airport": "SAT",
        },
        "itinerary": wandering_itinerary(
            ['GDL', 'PHX', 'CUN', 'MCO', 'QRO', 'ATL'],
            range(2020, 2026),
            (1, 5, 8, 11),
        ),
    },
    {
        "name": "Aphrodite",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "APH",
        "first_year": 2017,
        "age_in_first_year": 30,
        "base": {
            "city": "San Diego",
            "country": "United States",
            "country_code": "US",
            "airport": "SAN",
        },
        "itinerary": wandering_itinerary(
            ['SJD', 'DEN', 'LHR', 'SEA', 'PVR', 'JFK'],
            range(2017, 2026),
            (4, 7, 11),
        ),
    },
    {
        "name": "Sisyphus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "SIS",
        "first_year": 2018,
        "age_in_first_year": 44,
        "base": {
            "city": "San Diego",
            "country": "United States",
            "country_code": "US",
            "airport": "SAN",
        },
        "itinerary": wandering_itinerary(
            ['SFO', 'PHX', 'NRT', 'SLC', 'YVR', 'ORD'],
            range(2018, 2026),
            (2, 6, 9, 12),
        ),
    },
    {
        "name": "Cronus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CRO",
        "first_year": 2016,
        "age_in_first_year": 63,
        "base": {
            "city": "Dallas",
            "country": "United States",
            "country_code": "US",
            "airport": "DFW",
        },
        "itinerary": wandering_itinerary(
            ['LHR', 'DEN', 'MEX', 'ORD', 'SJD', 'MIA'],
            range(2016, 2026),
            (3, 8, 11),
        ),
    },
    {
        "name": "Demeter",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "DEM",
        "first_year": 2019,
        "age_in_first_year": 45,
        "base": {
            "city": "Dallas",
            "country": "United States",
            "country_code": "US",
            "airport": "DFW",
        },
        "itinerary": wandering_itinerary(
            ['CUN', 'LAX', 'MAD', 'MSP', 'GDL', 'SLC'],
            range(2019, 2026),
            (1, 5, 9, 12),
        ),
    },
    {
        "name": "Hercules",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "HER",
        "first_year": 2017,
        "age_in_first_year": 32,
        "base": {
            "city": "Fort Worth",
            "country": "United States",
            "country_code": "US",
            "airport": "DFW",
        },
        "itinerary": wandering_itinerary(
            ['ICN', 'ATL', 'MTY', 'IAD', 'PVR', 'EWR'],
            range(2017, 2026),
            (2, 6, 10),
        ),
    },
    {
        "name": "Theseus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "THE",
        "first_year": 2020,
        "age_in_first_year": 28,
        "base": {
            "city": "Fort Worth",
            "country": "United States",
            "country_code": "US",
            "airport": "DFW",
        },
        "itinerary": wandering_itinerary(
            ['HND', 'SAT', 'YYZ', 'MCO', 'CDG', 'IAH'],
            range(2020, 2026),
            (4, 8, 11),
        ),
    },
    {
        "name": "Perseus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "PER",
        "first_year": 2018,
        "age_in_first_year": 25,
        "base": {
            "city": "Jacksonville",
            "country": "United States",
            "country_code": "US",
            "airport": "JAX",
        },
        "itinerary": wandering_itinerary(
            ['ATL', 'ORD', 'MCO', 'DEN', 'JFK', 'IAD'],
            range(2018, 2026),
            (3, 7, 10),
        ),
    },
    {
        "name": "Chiron",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "CHI",
        "first_year": 2016,
        "age_in_first_year": 60,
        "base": {
            "city": "Jacksonville",
            "country": "United States",
            "country_code": "US",
            "airport": "JAX",
        },
        "itinerary": wandering_itinerary(
            ['PHL', 'MIA', 'DCA', 'CLT', 'BOS', 'DFW'],
            range(2016, 2026),
            (2, 5, 9, 12),
        ),
    },
    {
        "name": "Dionysus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "DIO",
        "first_year": 2019,
        "age_in_first_year": 35,
        "base": {
            "city": "Austin",
            "country": "United States",
            "country_code": "US",
            "airport": "AUS",
        },
        "itinerary": wandering_itinerary(
            ['LHR', 'ORD', 'CUN', 'LAX', 'AMS', 'DEN'],
            range(2019, 2026),
            (1, 6, 9),
        ),
    },
    {
        "name": "Icarus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ICA",
        "first_year": 2021,
        "age_in_first_year": 22,
        "base": {
            "city": "Austin",
            "country": "United States",
            "country_code": "US",
            "airport": "AUS",
        },
        "itinerary": wandering_itinerary(
            ['MEX', 'SFO', 'FRA', 'MCO', 'SJD', 'PHX'],
            range(2021, 2026),
            (3, 7, 11),
        ),
    },
    {
        "name": "Daedalus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "DAE",
        "first_year": 2016,
        "age_in_first_year": 54,
        "base": {
            "city": "San Jose",
            "country": "United States",
            "country_code": "US",
            "airport": "SJC",
        },
        "itinerary": wandering_itinerary(
            ['NRT', 'LAX', 'GDL', 'SEA', 'PVR', 'DEN'],
            range(2016, 2026),
            (4, 8, 12),
        ),
    },
    {
        "name": "Atlas",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ATS",
        "first_year": 2018,
        "age_in_first_year": 40,
        "base": {
            "city": "San Jose",
            "country": "United States",
            "country_code": "US",
            "airport": "SJC",
        },
        "itinerary": wandering_itinerary(
            ['SJD', 'PHX', 'BJX', 'ORD', 'HNL', 'LAS'],
            range(2018, 2026),
            (2, 6, 10),
        ),
    },
    {
        "name": "Orpheus",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ORP",
        "first_year": 2017,
        "age_in_first_year": 37,
        "base": {
            "city": "Columbus",
            "country": "United States",
            "country_code": "US",
            "airport": "CMH",
        },
        "itinerary": wandering_itinerary(
            ['YYZ', 'MCO', 'CUN', 'DEN', 'ATL', 'DFW'],
            range(2017, 2026),
            (3, 7, 11),
        ),
    },
    {
        "name": "Hera",
        "nationality": "American",
        "gender": "Female",
        "id_prefix": "HRA",
        "first_year": 2019,
        "age_in_first_year": 50,
        "base": {
            "city": "Columbus",
            "country": "United States",
            "country_code": "US",
            "airport": "CMH",
        },
        "itinerary": wandering_itinerary(
            ['CUN', 'ORD', 'YUL', 'PHX', 'MCO', 'IAD'],
            range(2019, 2026),
            (1, 5, 8, 12),
        ),
    },
    {
        "name": "Achilles",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "ACH",
        "first_year": 2016,
        "age_in_first_year": 29,
        "base": {
            "city": "Charlotte",
            "country": "United States",
            "country_code": "US",
            "airport": "CLT",
        },
        "itinerary": wandering_itinerary(
            ['LHR', 'ORD', 'MBJ', 'MIA', 'MUC', 'DEN'],
            range(2016, 2026),
            (2, 6, 9),
        ),
    },
    {
        "name": "King Midas",
        "nationality": "American",
        "gender": "Male",
        "id_prefix": "MID",
        "first_year": 2018,
        "age_in_first_year": 57,
        "base": {
            "city": "Charlotte",
            "country": "United States",
            "country_code": "US",
            "airport": "CLT",
        },
        "itinerary": wandering_itinerary(
            ['CUN', 'PHL', 'MAD', 'EWR', 'PUJ', 'BNA'],
            range(2018, 2026),
            (4, 8, 11),
        ),
    },
]

# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
BTS_PATH = DATA_DIR / "raw" / "bts_t100" / "T_T100I_MARKET_ALL_CARRIER.csv"
BTS_DOMESTIC_PATH = DATA_DIR / "raw" / "bts_t100" / "T_T100D_SEGMENT_ALL_CARRIER.csv"
OUTPUT_PATH = PROCESSED_DIR / "synthetic_trips.json"

# Domestic legs (both airports in the US) can't appear in an INTERNATIONAL
# market file, so they're exempt from the route check rather than failing it.
# Airports this file treats as US domestic, which routes a leg to the
# domestic T-100 file rather than the international one.
US_AIRPORTS = {
    "EWR", "IAH", "SFO", "ORD", "IAD", "JFK", "LGA", "LAX", "DEN", "BOS", "SEA", "ATL",
    "DTW", "MSP", "SLC", "CVG", "BNA", "PIT", "SAN", "CLE", "PDX", "MCO", "MSY",
    "DFW", "CLT", "PHL", "PHX", "DCA", "MIA", "PBI", "SAT",
    "HOU", "MDW", "BWI", "STL", "MCI", "TPA", "SRQ", "LAS",
    "HNL", "OGG", "KOA", "ANC", "GEG", "PSP", "BOI",
    "JAX", "AUS", "SJC", "CMH", "DCA",
}


def money(base: float, annual_rate: float, years_elapsed: int) -> tuple[float, str]:
    """(1225.0, "$1,225") -- the compounded value and the display string that
    goes in the *_raw field. Rounded to the nearest $25 so these read as
    prices somebody paid rather than as the output of a formula."""
    value = base * ((1 + annual_rate) ** years_elapsed)
    rounded = round(value / 25) * 25
    return float(rounded), f"${rounded:,.0f}"


def load_bts_routes() -> dict[tuple[str, str, str], float]:
    """(carrier, origin, dest) -> total passengers, from the T-100
    International Market extract. Empty dict (with a warning) if the file
    isn't in this checkout -- the check is then skipped rather than blocking
    the build, since these are reference downloads and the itineraries above
    don't change without a human editing them."""
    if not BTS_PATH.exists():
        print(f"WARNING: {BTS_PATH} not found -- skipping the international route check.")
        return {}

    import csv

    routes: dict[tuple[str, str, str], float] = {}
    with open(BTS_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["CARRIER_NAME"], row["ORIGIN"], row["DEST"])
            routes[key] = routes.get(key, 0.0) + float(row["PASSENGERS"] or 0)
    print(f"{BTS_PATH.name}: {len(routes)} carrier/origin/destination routes")
    return routes


def load_bts_domestic_routes() -> dict[tuple[str, str, str], tuple[int, int]]:
    """(carrier, origin, dest) -> (segment records, distinct months flown),
    from the T-100 Domestic Segment extract.

    No passenger counts here -- that export carries carrier, airports,
    aircraft type and month, and nothing about how full the aircraft was.
    That's fine for what this check does: "did this airline really fly this
    route" is a question about existence, not volume. The month count stands
    in for regularity, so a route flown in one month out of five reads
    differently from one flown in all five."""
    if not BTS_DOMESTIC_PATH.exists():
        print(f"WARNING: {BTS_DOMESTIC_PATH} not found -- domestic legs will be exempted, not checked.")
        return {}

    import csv

    months: dict[tuple[str, str, str], set] = {}
    counts: dict[tuple[str, str, str], int] = {}
    with open(BTS_DOMESTIC_PATH, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["CARRIER_NAME"], row["ORIGIN"], row["DEST"])
            months.setdefault(key, set()).add(row["MONTH"])
            counts[key] = counts.get(key, 0) + 1
    print(f"{BTS_DOMESTIC_PATH.name}: {len(counts)} carrier/origin/destination segments")
    return {key: (count, len(months[key])) for key, count in counts.items()}


# Floors for resolve_carriers(). Both T-100 files include business-jet and
# charter operators, so an unfiltered "who flies this route" turns up
# VistaJet on San Antonio-Madrid and Chartright on Jacksonville-Toronto --
# technically flown, absurd as an answer to "which airline would you book".
# These cut-offs keep the answer to scheduled service, and a route where
# nothing clears them is a hard failure rather than a silent oddity.
MIN_INTL_PASSENGERS = 1000
MIN_DOMESTIC_SEGMENTS = 5

# The volume floors above catch charter and business-jet operators, but not
# CARGO airlines -- those fly plenty of scheduled segments on exactly the
# trunk routes these travelers use, so they clear MIN_DOMESTIC_SEGMENTS
# comfortably and get handed out as if you could book a seat. United Parcel
# Service picked up 12 legs that way (Odysseus flew it three times) before
# this list existed.
#
# Excluded by name rather than by a "does it carry passengers" test because
# T-100's domestic segment file has no passenger column at all -- existence
# is the only thing it can prove, which is the whole reason
# MIN_DOMESTIC_SEGMENTS counts segments instead. Matched case-insensitively
# on the full carrier name, NOT as a substring: "Swiss International
# Airlines" contains the letters of "national air" and a loose pattern would
# quietly drop a real passenger airline.
#
# All five clear the floors on routes currently in use. Adding one is safe
# -- resolve_carriers() treats a route with nothing left as a hard failure,
# so an over-broad entry breaks the build loudly instead of silently
# reshuffling somebody's airline.
CARGO_CARRIERS = frozenset(
    {
        "united parcel service",
        "federal express corporation",
        "atlas air inc.",
        "abx air inc",
        "air transport international",
    }
)


def resolve_carriers(origin: str, dest: str, routes: dict, domestic_routes: dict) -> list[str]:
    """Every airline that really flies origin -> dest, busiest first.

    Cargo airlines are dropped here rather than in the caller (see
    CARGO_CARRIERS) -- they belong to the same question this function
    answers, "which airline would you actually book on this route".

    Returns a LIST, not one carrier, because the travelers who use this take
    whatever's convenient: someone flying New York-London four times should
    turn up on British Airways, Virgin Atlantic, American and Delta, which is
    what the data says actually serves that route. Picking only the busiest
    would hand them an airline loyalty they're specifically defined not to
    have."""
    domestic = origin in US_AIRPORTS and dest in US_AIRPORTS
    if domestic:
        found = [
            (segments, carrier)
            for (carrier, o, d), (segments, _months) in domestic_routes.items()
            if o == origin
            and d == dest
            and segments >= MIN_DOMESTIC_SEGMENTS
            and carrier.casefold() not in CARGO_CARRIERS
        ]
    else:
        found = [
            (passengers, carrier)
            for (carrier, o, d), passengers in routes.items()
            if o == origin
            and d == dest
            and passengers >= MIN_INTL_PASSENGERS
            and carrier.casefold() not in CARGO_CARRIERS
        ]
    # Sorted by volume then name, so the order -- and therefore which airline
    # a given trip ends up on -- is identical on every run.
    found.sort(key=lambda pair: (-pair[0], pair[1]))
    return [carrier for _volume, carrier in found]


def check_routes(routes: dict, domestic_routes: dict) -> None:
    """Every leg must be a route its named carrier actually flies -- checked
    against the international file when it crosses a border and the domestic
    one when it doesn't. Fatal if not: the whole claim this file makes is
    that its itineraries sit on real routes, and one unflown leg would
    quietly make that false.

    A domestic leg is exempted only when the domestic file is missing from
    the checkout. That used to be the permanent state of affairs, which is
    why Sorolla's Christmas hop and Chet Baker's entire commute went unchecked
    for a while."""
    if not routes and not domestic_routes:
        return

    missing = []
    for traveler in TRAVELERS:
        origin = traveler["base"]["airport"]
        print(f"\nRoute check -- {traveler['name']} (from {origin}):")
        seen: set[tuple[str, str]] = set()
        for entry in traveler["itinerary"]:
            _, _, _, _, carrier, airport, city, country, _, _ = entry
            if (carrier, airport) in seen:
                continue  # a repeated route only needs checking once
            seen.add((carrier, airport))
            label = f"{city}, {country}"

            # An ANY_CARRIER leg names no airline, so there's nothing to
            # verify about one. What still has to be true is that somebody
            # flies the route at all -- otherwise resolve_carriers() would
            # come back empty at build time and the trip would have no
            # airline. Checked here so it fails loudly now rather than
            # silently producing a flight nobody operates.
            if carrier == ANY_CARRIER:
                if not routes and not domestic_routes:
                    continue
                options = resolve_carriers(origin, airport, routes, domestic_routes)
                if not options:
                    missing.append((traveler["name"], "any carrier", origin, airport))
                    print(f"  {origin} -> {airport}  {label:<28} NO SCHEDULED CARRIER")
                else:
                    shown = ", ".join(options[:3])
                    more = f" (+{len(options) - 3} more)" if len(options) > 3 else ""
                    print(f"  {origin} -> {airport}  {label:<28} {len(options)} carrier(s): {shown}{more}")
                continue

            if origin in US_AIRPORTS and airport in US_AIRPORTS:
                if not domestic_routes:
                    print(f"  {origin} -> {airport}  {label:<28} domestic, no file to check against")
                    continue
                found = domestic_routes.get((carrier, origin, airport))
                if not found:
                    missing.append((traveler["name"], carrier, origin, airport))
                    print(f"  {origin} -> {airport}  {label:<28} {carrier}: NOT FOUND (domestic)")
                else:
                    segments, month_count = found
                    print(
                        f"  {origin} -> {airport}  {label:<28} {carrier:<32} "
                        f"{segments:>5} segments in {month_count} month(s)"
                    )
                continue

            if not routes:
                continue
            passengers = routes.get((carrier, origin, airport), 0.0)
            if passengers <= 0:
                missing.append((traveler["name"], carrier, origin, airport))
                print(f"  {origin} -> {airport}  {label:<28} {carrier}: NOT FOUND")
            else:
                print(f"  {origin} -> {airport}  {label:<28} {carrier:<32} {passengers:>10,.0f} passengers")

    if missing:
        raise SystemExit(
            f"\n{len(missing)} leg(s) aren't flown by the named carrier on that route in the T-100 "
            f"data: {missing}. Fix the itinerary (or pass --skip-route-check if you're deliberately "
            "inventing a route)."
        )


def build_trips(traveler: dict, routes: dict, domestic_routes: dict) -> list[dict]:
    """One traveler's itinerary, in exactly the shape build_trips_enhanced.py
    emits, plus the four synthetic-only fields. Same keys in the same order,
    so the merged trips_enhanced.json is homogeneous and nothing downstream
    has to know which rows came from where -- except by the `synthetic` flag,
    which is there precisely so it can."""
    trips: list[dict] = []
    origin = traveler["base"]["airport"]
    # How many times this traveler has already flown each route, so an
    # ANY_CARRIER leg can step through that route's airlines instead of
    # landing on the busiest one every time. Per traveler, not global: two
    # people who both fly Chicago-Cancun should each start from the top of
    # the list, not take turns with each other.
    flown: dict[tuple[str, str], int] = {}

    for year, month, day_rule, nights, carrier, airport, city, country, code, tier in traveler["itinerary"]:
        if carrier == ANY_CARRIER:
            options = resolve_carriers(origin, airport, routes, domestic_routes)
            if options:
                nth = flown.get((origin, airport), 0)
                flown[(origin, airport)] = nth + 1
                carrier = options[nth % len(options)]
            else:
                # Only reachable with --skip-route-check, where there's no
                # data to resolve against. carrier_name is nullable in the
                # output schema, so an unknown airline is recorded as
                # unknown rather than guessed at.
                carrier = None
        start = start_date(year, month, day_rule)
        end = start + timedelta(days=nights)
        elapsed = year - traveler["first_year"]
        hotel_base, hotel_rate, flight_base, flight_rate = COST_TIERS[tier]
        flight = money(flight_base, flight_rate, elapsed)
        # A tier with no hotel base means staying with family, not a $0
        # hotel -- so the trip says so and carries no accommodation cost at
        # all. The absence is the informative part: these are the only trips
        # in the dataset with no place-to-sleep spend.
        staying_with_family = hotel_base == 0
        accommodation_type = "Family home" if staying_with_family else "Hotel"
        hotel = (None, None) if staying_with_family else money(hotel_base, hotel_rate, elapsed)

        trips.append(
            {
                # Keyed by the full departure date, not year-month: Tom
                # Petty flies twice in most months and three times in some,
                # so a year-month id would collide.
                "trip_id": f"{traveler['id_prefix']}-{start.isoformat()}",
                # A synthesized trip has no messy source string to preserve,
                # so destination_raw is just the clean form. Kept so every
                # trip in trips_enhanced.json has the same keys.
                "destination_raw": f"{city}, {country}",
                "destination_city": city,
                "destination_country": country,
                "destination_country_code": code,
                "destination_kind": "city",
                "start_date": start.isoformat(),
                "start_date_raw": start.isoformat(),
                "end_date": end.isoformat(),
                "end_date_raw": end.isoformat(),
                "duration_days": nights,
                "duration_raw": f"{nights} days",
                "accommodation_type": accommodation_type,
                "accommodation_cost": hotel[0],
                "accommodation_cost_raw": hotel[1],
                "transportation_type": "Flight",
                "transportation_cost": flight[0],
                "transportation_cost_raw": flight[1],
                "traveler_name": traveler["name"],
                "traveler_age": traveler["age_in_first_year"] + elapsed,
                "traveler_gender": traveler["gender"],
                "traveler_nationality": traveler["nationality"],
                # --- synthetic-only fields, null on every Kaggle trip ------
                "synthetic": True,
                "carrier_name": carrier,
                "origin_airport": origin,
                "destination_airport": airport,
            }
        )

    trips.sort(key=lambda t: t["start_date"])
    return trips


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--skip-route-check",
        action="store_true",
        help="Don't read the T-100 file to verify each carrier actually flies each international route.",
    )
    args = parser.parse_args()

    # Loaded once and used twice: to verify the legs that name a carrier,
    # and to CHOOSE one for the legs that don't (see resolve_carriers).
    # --skip-route-check therefore also means "leave the wanderers' airlines
    # null", which is why it warns rather than just being quieter.
    routes: dict = {}
    domestic_routes: dict = {}
    if args.skip_route_check:
        if any(leg[4] == ANY_CARRIER for t in TRAVELERS for leg in t["itinerary"]):
            print(
                "WARNING: --skip-route-check means there's no data to resolve ANY_CARRIER legs "
                "against, so travelers who fly no particular airline will have carrier_name: null."
            )
    else:
        routes = load_bts_routes()
        domestic_routes = load_bts_domestic_routes()
        check_routes(routes, domestic_routes)

    trips: list[dict] = []
    # Read by build_travelers.py, which prefers a declared base over its own
    # nationality-based guess -- see resolve_base() there.
    declared_bases = {}
    for traveler in TRAVELERS:
        trips.extend(build_trips(traveler, routes, domestic_routes))
        declared_bases[traveler["name"]] = {
            "base_city": traveler["base"]["city"],
            "base_country": traveler["base"]["country"],
            "base_country_code": traveler["base"]["country_code"],
        }

    trips.sort(key=lambda t: (t["traveler_name"], t["start_date"]))

    payload = {
        "source": (
            "Hand-authored travelers with deliberate travel patterns, for the recommendation work "
            "the Kaggle sample data is too thin to support -- see build_synthetic_trips.py. Every "
            "international leg is verified against the US DOT T-100 International Market extract in "
            "data/raw/bts_t100/, which is also where each leg's carrier comes from."
        ),
        "generated": date.today().isoformat(),
        "note": (
            "These trips are FABRICATED (costs, dates, ages) on top of real airline routes. Merged "
            "into trips_enhanced.json by build_trips_enhanced.py, where every trip carries "
            "synthetic: true so they can always be told apart from the Kaggle rows. Domestic legs "
            "can't be checked against an international file. 2020/2021 entries exist because the "
            "briefs asked for unbroken runs of years, not because those trips could have happened."
        ),
        "declared_bases": declared_bases,
        "total_travelers": len(TRAVELERS),
        "total_trips": len(trips),
        "trips": trips,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\nWrote {len(trips)} synthetic trips from {len(TRAVELERS)} travelers -> {OUTPUT_PATH}")
    for traveler in TRAVELERS:
        mine = [t for t in trips if t["traveler_name"] == traveler["name"]]
        cities = {t["destination_city"] for t in mine}
        countries = {t["destination_country"] for t in mine}
        carriers = {t["carrier_name"] for t in mine}
        years = {t["start_date"][:4] for t in mine}
        print(
            f"  {traveler['name']:<20} {len(mine):>2} trips  {min(years)}-{max(years)}  "
            f"from {traveler['base']['airport']}  "
            f"{len(cities)} cit{'y' if len(cities) == 1 else 'ies'} / {len(countries)} "
            f"countr{'y' if len(countries) == 1 else 'ies'} / {len(carriers)} carrier(s)"
        )
    print("\nNext: python scripts/multiple/build_trips_enhanced.py")


if __name__ == "__main__":
    main()
