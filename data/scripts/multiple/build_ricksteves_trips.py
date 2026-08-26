"""
Derived from: Wikipedia's episode table for Rick Steves' Europe --
              https://en.wikipedia.org/wiki/Rick_Steves%27_Europe
              13 seasons, 162 numbered episodes (2000-2025), syndicated
              travel documentary hosted by Rick Steves out of Edmonds, WA
              (a Seattle suburb -- Ivan's call: SEA is the home airport).

Same machinery as build_bourdain_trips.py / build_ramsay_trips.py /
build_conan_trips.py: one 5-day round trip per episode, departing on the
episode's air date, flying nonstop. Writes
data/processed/multiple/ricksteves_trips.csv and .json.

THE HEADLINE FINDING: SEATTLE BARELY FLIES TO EUROPE.
airline_routes_enhanced.csv has SEA nonstop to exactly six European
airports: Paris CDG, London LHR, Frankfurt FRA, Amsterdam AMS, Dublin DUB
and Reykjavik KEF. Nothing to Italy, Spain, Portugal, Switzerland,
Austria, Scandinavia, the Balkans, Eastern Europe, Turkey, Greece or the
Middle East/Africa legs the show also visits. That is not a research gap
-- it was checked route by route against the same file every other
traveler in this dataset uses -- it is what "no nonstop from home" really
looks like for a Pacific Northwest departure point on a show about all of
Europe. Same spirit as Ramsay's Uncharted losing more than half its
episodes to the flights-only rule: a fact about the departure city, not
about the source material.

WHERE A REGION HAS NO AIRPORT OF ITS OWN, `airports` lists the specific
place's real regional/small airport FIRST, and -- only when a genuine,
commonly-used same-country hub exists -- that hub as a further candidate,
exactly as chef_trips.py's resolve_flight() is designed to use it (see
Conan's Chamonix->Geneva precedent). Bath and York have no international
airport of their own; nobody flies to either nonstop from anywhere. What
a Seattle traveler actually does is fly into London and go by train --
so English/Welsh/Scottish regional episodes carry LHR as a real fallback,
German regional episodes carry FRA, French regional episodes carry CDG.
Where flying via that country's own hub isn't a genuine practice for the
place in question (Rome, Madrid, Vienna, Prague, Athens, Istanbul,
Copenhagen, Zurich -- places with real international airports of their
own that Seattle just doesn't reach), no cross-country fallback is
invented, and the episode is excluded on the flights-only rule like any
other. THE SUBSTITUTION MECHANISM IN chef_trips.py DOES THE REST: when
the first candidate has no SEA nonstop and a later one does, the trip's
destination_city becomes the airport actually flown to (documented
automatically in `notes`) -- so several regional-Germany episodes really
do end up recorded as trips to "Frankfurt", the same way Ramsay's
Queenstown and Hobart episodes already resolve to Auckland and Melbourne.

EXCLUSION REASONS BEYOND THE FLIGHTS-ONLY RULE (marked by hand, since
build_rows() can't infer these from an airport list):
  * COMPILATION -- "Travel Skills" / "European Travel Skills" (6 episodes
    across seasons 1 and 7), "Rick Steves' Europe: The Making Of" (S4),
    "Why We Travel" (S11), "The Story of Fascism in Europe" (S10, a
    multi-country documentary special, not a single destination), and
    ALL of Season 12 (12 episodes, "Art of ..." -- a thematic art-history
    season built from archival footage across many countries and eras,
    not new single-destination journeys).
  * AMBIGUOUS (no_single_destination) -- episodes naming two or more
    countries/cities with no one gateway: Slovenia and Croatia (S1),
    Little Europe's five micro-nations (S5), Andalucia/Gibraltar/Tangier
    spanning Spain-UK-Morocco (S6), Helsinki and Tallinn (S6, two
    capitals), Basque Country (S6, spans the France-Spain border with no
    single named city), Eastern Turkey (S1, too broad a region for one
    gateway), Austrian and Italian Alps (S11), Egypt's Nile/
    Alexandria/Luxor (S11, three cities, no single one is "the"
    destination), and Italy's Highlights (S13, a national survey, not one
    place).

EPISODE NUMBERING GAPS ARE THE SOURCE'S, NOT A FETCH FAILURE. Wikipedia's
own episode numbering jumps from 117 straight to 131 (Season 10, 2018-19,
is a single special -- "The Story of Fascism in Europe" -- plus an
unlisted Mediterranean cruise special the article mentions only in prose,
not in a numbered row) and skips 146 entirely inside Season 12's run.
Nothing is invented to fill either gap -- only episodes the article
actually enumerates with a title and air date appear below.

THE CAPITAL RULE (stated in full in chef_trips.py) applies exactly where
an episode names a country and no city: "Portugal's Heartland" (Lisbon),
"Surprising Bulgaria" and "Bulgaria" (Sofia), "Romania" (Bucharest),
"Ethiopia: A Development Story" (Addis Ababa). Every other episode names
an actual city or region, which wins over the rule per the project
convention.

PALESTINE (S8E100) has no functioning international airport of its own;
the real-world gateway for the West Bank is Tel Aviv's Ben Gurion (TLV)
via the Allenby Bridge crossing, or Amman (AMM) -- both candidates are
listed, and neither has an SEA nonstop, so this excludes on the
flights-only rule like everything else, not on the politics of the
region.

Requires: data/reference/airports.json, and
          data/processed/multiple/airline_routes_enhanced.csv -- both read
          by chef_trips.py, which does the actual resolution.

Usage:
    python build_ricksteves_trips.py
    python build_ricksteves_trips.py --include-excluded   # also write excluded rows to the CSV
"""

import argparse

from chef_trips import (  # noqa: E402
    AMBIGUOUS,
    COMPILATION,
    PROCESSED_DIR,
    build_rows,
    print_summary,
    write_outputs,
)

OUT_CSV_PATH = PROCESSED_DIR / "ricksteves_trips.csv"
OUT_JSON_PATH = PROCESSED_DIR / "ricksteves_trips.json"

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/Rick_Steves%27_Europe"

# Rick Steves lives in Edmonds, WA (a Seattle suburb) and the show's
# company is headquartered there -- Ivan's call was "Seattle", and SEA is
# the only home airport, unlike the three-airport preferences the New
# York and LA travelers use.
ORIGIN_PREFERENCE = ("SEA",)

TRIP_DAYS = 5

TRAVELER = {
    "traveler_id": "rick-steves",
    "traveler_name": "Rick Steves",
    "home_city": "Seattle",
    "home_country": "United States",
    "source_series": "Rick Steves' Europe",
}

SHOW = "Rick Steves' Europe"
SHOW_CODE = "RSE"

CAPITAL_RULE_NOTE = "the title names only the country, so the row is the capital"

EPISODES_RAW = [
    # ---- Season 1 (2000) ----
    {"season": 1, "episode": 1, "title": "Portugal's Heartland",
     "air_date": "2000-09-03", "city": "Lisbon", "country": "Portugal",
     "airports": ["LIS"], "note": CAPITAL_RULE_NOTE},
    {"season": 1, "episode": 2, "title": "Paris: Grand and Intimate",
     "air_date": "2000-09-10", "city": "Paris", "country": "France",
     "airports": ["CDG"]},
    {"season": 1, "episode": 3, "title": "South England: Dovers to Land's End",
     "air_date": "2000-09-17", "city": "South England", "country": "United Kingdom",
     "airports": ["LGW", "LHR"],
     "note": "no international airport serves this coastal region directly; "
             "London is the real-world gateway"},
    {"season": 1, "episode": 4, "title": "Heart of England and South Wales",
     "air_date": "2000-09-24", "city": "Heart of England and South Wales", "country": "United Kingdom",
     "airports": ["BHX", "CWL", "LHR"]},
    {"season": 1, "episode": 5, "title": "Caesar's Rome",
     "air_date": "2000-10-01", "city": "Rome", "country": "Italy",
     "airports": ["FCO", "CIA"]},
    {"season": 1, "episode": 6, "title": "Germany's Black Forest and Cologne",
     "air_date": "2000-10-08", "city": "Black Forest and Cologne", "country": "Germany",
     "airports": ["CGN", "FKB", "FRA"]},
    {"season": 1, "episode": 7, "title": "Scotland's Islands and Highlands",
     "air_date": "2000-10-15", "city": "Scottish Highlands and Islands", "country": "United Kingdom",
     "airports": ["INV", "GLA", "EDI", "LHR"]},
    {"season": 1, "episode": 8, "title": "Surprising Bulgaria",
     "air_date": "2000-10-22", "city": "Sofia", "country": "Bulgaria",
     "airports": ["SOF"], "note": CAPITAL_RULE_NOTE},
    {"season": 1, "episode": 9, "title": "Rome: Baroque After Dark",
     "air_date": "2000-10-29", "city": "Rome", "country": "Italy",
     "airports": ["FCO", "CIA"]},
    {"season": 1, "episode": 10, "title": "Eastern Turkey",
     "air_date": "2000-11-05",
     "exclude": AMBIGUOUS, "exclude_note": "region too broad for one gateway city"},
    {"season": 1, "episode": 11, "title": "London: Royal and Rambunctious",
     "air_date": "2000-11-12", "city": "London", "country": "United Kingdom",
     "airports": ["LHR"]},
    {"season": 1, "episode": 12, "title": "Slovenia and Croatia",
     "air_date": "2000-11-19",
     "exclude": AMBIGUOUS, "exclude_note": "two countries named, no single gateway"},
    {"season": 1, "episode": 13, "title": "The Best of Sicily",
     "air_date": "2000-11-26", "city": "Sicily", "country": "Italy",
     "airports": ["CTA", "PMO"]},
    {"season": 1, "episode": 14, "title": "Travel Skills, Part One",
     "air_date": "2000-12-03",
     "exclude": COMPILATION, "exclude_note": "instructional episode, not a destination"},
    {"season": 1, "episode": 15, "title": "Travel Skills, Part Two",
     "air_date": "2000-12-10",
     "exclude": COMPILATION, "exclude_note": "instructional episode, not a destination"},
    {"season": 1, "episode": 16, "title": "Travel Skills, Part Three",
     "air_date": "2000-12-17",
     "exclude": COMPILATION, "exclude_note": "instructional episode, not a destination"},

    # ---- Season 2 (2002) ----
    {"season": 2, "episode": 17, "title": "Venice: Serene, Decadent, and Still Kicking",
     "air_date": "2002-09-07", "city": "Venice", "country": "Italy", "airports": ["VCE"]},
    {"season": 2, "episode": 18, "title": "Venice Sidetrips: The Best of Veneto",
     "air_date": "2002-09-14", "city": "Veneto", "country": "Italy", "airports": ["VCE", "VRN"]},
    {"season": 2, "episode": 19, "title": "Florence: City of Art",
     "air_date": "2002-09-21", "city": "Florence", "country": "Italy", "airports": ["FLR", "PSA"]},
    {"season": 2, "episode": 20, "title": "Siena and Assisi: Italy's Grand Hill Towns",
     "air_date": "2002-09-28", "city": "Siena and Assisi", "country": "Italy",
     "airports": ["FLR", "PSA", "PEG"]},
    {"season": 2, "episode": 21, "title": "Cinque Terre: Italy's Hidden Riviera",
     "air_date": "2002-10-05", "city": "Cinque Terre", "country": "Italy", "airports": ["PSA", "GOA"]},
    {"season": 2, "episode": 22, "title": "Amsterdam and Dutch Sidetrips",
     "air_date": "2002-10-12", "city": "Amsterdam", "country": "Netherlands", "airports": ["AMS"]},
    {"season": 2, "episode": 23, "title": "Prague and the Czech Republic",
     "air_date": "2002-10-19", "city": "Prague", "country": "Czech Republic", "airports": ["PRG"]},
    {"season": 2, "episode": 24, "title": "Dublin and Mystical Sidetrips",
     "air_date": "2002-10-26", "city": "Dublin", "country": "Ireland", "airports": ["DUB"]},
    {"season": 2, "episode": 25, "title": "South Ireland: Waterford to the Ring of Kerry",
     "air_date": "2002-11-02", "city": "South Ireland", "country": "Ireland",
     "airports": ["ORK", "DUB"]},
    {"season": 2, "episode": 26, "title": "The Best of West Ireland: Dingle, Galway, and the Aran Islands",
     "air_date": "2002-11-09", "city": "West Ireland", "country": "Ireland",
     "airports": ["SNN", "DUB"], "note": "Shannon checked as the western gateway"},
    {"season": 2, "episode": 27, "title": "Berlin: Resilient, Reunited, and Reborn",
     "air_date": "2002-11-16", "city": "Berlin", "country": "Germany", "airports": ["TXL", "FRA"],
     "note": "Tegel was Berlin's gateway in this era; airports.json (OpenFlights) predates BER"},
    {"season": 2, "episode": 28, "title": "Germany's Romantic Rhine and Rothenburg",
     "air_date": "2002-11-23", "city": "Rhine and Rothenburg", "country": "Germany", "airports": ["FRA"]},
    {"season": 2, "episode": 29, "title": "Munich and the Foothills of the Alps",
     "air_date": "2002-11-30", "city": "Munich", "country": "Germany", "airports": ["MUC", "FRA"]},
    {"season": 2, "episode": 30, "title": "Switzerland's Jungfrau Region: Best of the Alps",
     "air_date": "2002-12-07", "city": "Jungfrau Region", "country": "Switzerland",
     "airports": ["ZRH", "BRN"]},

    # ---- Season 3 (2004) ----
    {"season": 3, "episode": 31, "title": "Majesty of Madrid",
     "air_date": "2004-09-04", "city": "Madrid", "country": "Spain", "airports": ["MAD"]},
    {"season": 3, "episode": 32, "title": "Highlights of Castille: Toledo and Salamanca",
     "air_date": "2004-09-11", "city": "Toledo and Salamanca", "country": "Spain", "airports": ["MAD"]},
    {"season": 3, "episode": 33, "title": "Normandy: War-Torn, Yet Full of Life",
     "air_date": "2004-09-18", "city": "Normandy", "country": "France", "airports": ["CFR", "CDG"]},
    {"season": 3, "episode": 34, "title": "Belfast and the Best of Northern Ireland",
     "air_date": "2004-09-25", "city": "Belfast", "country": "United Kingdom",
     "airports": ["BFS", "LHR"], "note": "Northern Ireland is part of the United Kingdom"},
    {"season": 3, "episode": 35, "title": "London: Mod and Trad",
     "air_date": "2004-10-02", "city": "London", "country": "United Kingdom", "airports": ["LHR"]},
    {"season": 3, "episode": 36, "title": "Highlights of Paris: Eiffel and Monet to Crème Brulée",
     "air_date": "2004-10-09", "city": "Paris", "country": "France", "airports": ["CDG"]},
    {"season": 3, "episode": 37, "title": "Belgium: Bruges and Brussels",
     "air_date": "2004-10-16", "city": "Bruges and Brussels", "country": "Belgium", "airports": ["BRU"]},
    {"season": 3, "episode": 38, "title": "Provence: Legendary Light, Wind, and Wine",
     "air_date": "2004-10-23", "city": "Provence", "country": "France", "airports": ["MRS", "AVN", "CDG"]},
    {"season": 3, "episode": 39, "title": "French Riviera: Uniquely Chic",
     "air_date": "2004-10-30", "city": "French Riviera", "country": "France", "airports": ["NCE", "CDG"]},
    {"season": 3, "episode": 40, "title": "Poland Rediscovered: Krakow, Auschwitz, and Warsaw",
     "air_date": "2004-11-06", "city": "Krakow", "country": "Poland", "airports": ["KRK", "WAW"]},
    {"season": 3, "episode": 41, "title": "Budapest: The Best of Hungary",
     "air_date": "2004-11-13", "city": "Budapest", "country": "Hungary", "airports": ["BUD"]},
    {"season": 3, "episode": 42, "title": "Lisbon and the Algarve",
     "air_date": "2004-11-20", "city": "Lisbon", "country": "Portugal", "airports": ["LIS", "FAO"]},
    {"season": 3, "episode": 43, "title": "Sevilla and Andalusia",
     "air_date": "2004-11-27", "city": "Sevilla", "country": "Spain", "airports": ["SVQ"]},

    # ---- Season 4 (2006) ----
    {"season": 4, "episode": 44, "title": "England's Bath and York",
     "air_date": "2006-10-07", "city": "Bath and York", "country": "United Kingdom",
     "airports": ["BRS", "LBA", "LHR"]},
    {"season": 4, "episode": 45, "title": "North Wales: Feisty and Poetic",
     "air_date": "2006-10-14", "city": "North Wales", "country": "United Kingdom",
     "airports": ["LPL", "CWL", "LHR"]},
    {"season": 4, "episode": 46, "title": "Edinburgh",
     "air_date": "2006-10-21", "city": "Edinburgh", "country": "United Kingdom", "airports": ["EDI", "LHR"]},
    {"season": 4, "episode": 47, "title": "Naples and Pompeii",
     "air_date": "2006-10-28", "city": "Naples", "country": "Italy", "airports": ["NAP"]},
    {"season": 4, "episode": 48, "title": "Italy's Amalfi Coast",
     "air_date": "2006-11-04", "city": "Amalfi Coast", "country": "Italy", "airports": ["NAP"]},
    {"season": 4, "episode": 49, "title": "Milan and Lake Como",
     "air_date": "2006-11-11", "city": "Milan", "country": "Italy", "airports": ["MXP", "LIN"]},
    {"season": 4, "episode": 50, "title": "Tuscany's Dolce Vita",
     "air_date": "2006-11-18", "city": "Tuscany", "country": "Italy", "airports": ["FLR", "PSA"]},
    {"season": 4, "episode": 51, "title": "Italy's Great Hill Towns",
     "air_date": "2006-11-25", "city": "Tuscany and Umbria hill towns", "country": "Italy",
     "airports": ["FLR", "PSA", "PEG"]},
    {"season": 4, "episode": 52, "title": "Vienna",
     "air_date": "2006-12-02", "city": "Vienna", "country": "Austria", "airports": ["VIE"]},
    {"season": 4, "episode": 53, "title": "Salzburg and Surroundings",
     "air_date": "2006-12-09", "city": "Salzburg", "country": "Austria", "airports": ["SZG", "MUC"]},
    {"season": 4, "episode": 54, "title": "Rick Steves' Europe: The Making Of",
     "air_date": "2006-12-16",
     "exclude": COMPILATION, "exclude_note": "behind-the-scenes retrospective, not a destination"},

    # ---- Season 5 (2008-2009) ----
    {"season": 5, "episode": 55, "title": "Burgundy: Profoundly French",
     "air_date": "2008-10-04", "city": "Burgundy", "country": "France", "airports": ["LYS", "CDG"]},
    {"season": 5, "episode": 56, "title": "France's Dordogne",
     "air_date": "2008-10-11", "city": "Dordogne", "country": "France", "airports": ["EGC", "BOD", "CDG"]},
    {"season": 5, "episode": 57, "title": "Barcelona and Catalunya",
     "air_date": "2008-10-18", "city": "Barcelona", "country": "Spain", "airports": ["BCN"]},
    {"season": 5, "episode": 58, "title": "Little Europe: Five Micro-Nations",
     "air_date": "2008-10-25",
     "exclude": AMBIGUOUS, "exclude_note": "five micro-nations named, no single gateway"},
    {"season": 5, "episode": 59, "title": "Switzerland's Great Cities",
     "air_date": "2008-11-01", "city": "Switzerland's cities", "country": "Switzerland",
     "airports": ["ZRH", "GVA"]},
    {"season": 5, "episode": 60, "title": "Vienna and the Danube",
     "air_date": "2008-11-08", "city": "Vienna", "country": "Austria", "airports": ["VIE"]},
    {"season": 5, "episode": 61, "title": "The Czech Republic Beyond Prague",
     "air_date": "2008-11-15", "city": "Czech Republic", "country": "Czech Republic", "airports": ["PRG"]},
    {"season": 5, "episode": 62, "title": "Athens and Sidetrips",
     "air_date": "2008-11-22", "city": "Athens", "country": "Greece", "airports": ["ATH"]},
    {"season": 5, "episode": 63, "title": "Athens and the Peloponnese",
     "air_date": "2008-11-29", "city": "Athens", "country": "Greece", "airports": ["ATH"]},
    {"season": 5, "episode": 64, "title": "Copenhagen",
     "air_date": "2008-12-06", "city": "Copenhagen", "country": "Denmark", "airports": ["CPH"]},
    {"season": 5, "episode": 65, "title": "Denmark Beyond Copenhagen",
     "air_date": "2008-12-13", "city": "Denmark", "country": "Denmark", "airports": ["CPH"]},
    {"season": 5, "episode": 66, "title": "Istanbul",
     "air_date": "2008-12-20", "city": "Istanbul", "country": "Turkey", "airports": ["IST"]},
    {"season": 5, "episode": 67, "title": "Iran: Tehran and Sidetrips",
     "air_date": "2008-12-27", "city": "Tehran", "country": "Iran", "airports": ["IKA"]},
    {"season": 5, "episode": 68, "title": "Iran's Historic Capitals",
     "air_date": "2009-02-28", "city": "Tehran", "country": "Iran", "airports": ["IKA", "SYZ"]},

    # ---- Season 6 (2010) ----
    {"season": 6, "episode": 69, "title": "The Best of Southern Spain",
     "air_date": "2010-10-02", "city": "Southern Spain", "country": "Spain", "airports": ["AGP"]},
    {"season": 6, "episode": 70, "title": "Croatia: Adriatic Delights",
     "air_date": "2010-10-09", "city": "Croatia's coast", "country": "Croatia", "airports": ["ZAG", "SPU"]},
    {"season": 6, "episode": 71, "title": "Dubrovnik and Balkan Sidetrips",
     "air_date": "2010-10-16", "city": "Dubrovnik", "country": "Croatia", "airports": ["DBV"]},
    {"season": 6, "episode": 72, "title": "The Best of Slovenia",
     "air_date": "2010-10-23", "city": "Slovenia", "country": "Slovenia", "airports": ["LJU"]},
    {"season": 6, "episode": 73, "title": "Granada, Córdoba, and Spain's Costa del Sol",
     "air_date": "2010-10-30", "city": "Granada, Córdoba, and Costa del Sol", "country": "Spain",
     "airports": ["AGP"]},
    {"season": 6, "episode": 74, "title": "Andalucia, Gibraltar, and Tangier",
     "air_date": "2010-11-06",
     "exclude": AMBIGUOUS, "exclude_note": "spans Spain, Gibraltar (UK) and Morocco, no single gateway"},
    {"season": 6, "episode": 75, "title": "Oslo",
     "air_date": "2010-11-13", "city": "Oslo", "country": "Norway", "airports": ["OSL"]},
    {"season": 6, "episode": 76, "title": "Norway West: Fjords, Mountains, and Bergen",
     "air_date": "2010-11-20", "city": "Bergen", "country": "Norway", "airports": ["BGO"]},
    {"season": 6, "episode": 77, "title": "Stockholm",
     "air_date": "2010-11-27", "city": "Stockholm", "country": "Sweden", "airports": ["ARN"]},
    {"season": 6, "episode": 78, "title": "Helsinki and Tallinn: Baltic Sisters",
     "air_date": "2010-12-04",
     "exclude": AMBIGUOUS, "exclude_note": "two capitals of two different countries, no single gateway"},
    {"season": 6, "episode": 79, "title": "Northern Spain and the Camino de Santiago",
     "air_date": "2010-12-11", "city": "Santiago de Compostela", "country": "Spain", "airports": ["SCQ"]},
    {"season": 6, "episode": 80, "title": "Basque Country",
     "air_date": "2010-12-18",
     "exclude": AMBIGUOUS, "exclude_note": "the Basque Country spans the France-Spain border with no "
                                            "single city named"},

    # ---- Season 7 (2012-2013) ----
    {"season": 7, "episode": 81, "title": "Rome: Ancient Glory",
     "air_date": "2012-10-06", "city": "Rome", "country": "Italy", "airports": ["FCO", "CIA"]},
    {"season": 7, "episode": 82, "title": "Rome: Baroque Brilliance",
     "air_date": "2012-10-13", "city": "Rome", "country": "Italy", "airports": ["FCO", "CIA"]},
    {"season": 7, "episode": 83, "title": "Rome: Back-Street Riches",
     "air_date": "2012-10-20", "city": "Rome", "country": "Italy", "airports": ["FCO", "CIA"]},
    {"season": 7, "episode": 84, "title": "Florence: Heart of the Renaissance",
     "air_date": "2012-10-27", "city": "Florence", "country": "Italy", "airports": ["FLR", "PSA"]},
    {"season": 7, "episode": 85, "title": "Florentine Delights and Tuscan Sidetrips",
     "air_date": "2012-11-03", "city": "Florence", "country": "Italy", "airports": ["FLR", "PSA"]},
    {"season": 7, "episode": 86, "title": "Paris: Regal and Intimate",
     "air_date": "2012-11-10", "city": "Paris", "country": "France", "airports": ["CDG"]},
    {"season": 7, "episode": 87, "title": "Paris: Embracing Life and Art",
     "air_date": "2012-11-17", "city": "Paris", "country": "France", "airports": ["CDG"]},
    {"season": 7, "episode": 88, "title": "London: Historic and Dynamic",
     "air_date": "2012-11-24", "city": "London", "country": "United Kingdom", "airports": ["LHR"]},
    {"season": 7, "episode": 89, "title": "North England's Lake District and Durham",
     "air_date": "2012-12-01", "city": "Lake District and Durham", "country": "United Kingdom",
     "airports": ["MAN", "NCL", "LHR"]},
    {"season": 7, "episode": 90, "title": "Venice: City of Dreams",
     "air_date": "2012-12-08", "city": "Venice", "country": "Italy", "airports": ["VCE"]},
    {"season": 7, "episode": 91, "title": "Venice's Lagoon",
     "air_date": "2012-12-15", "city": "Venice", "country": "Italy", "airports": ["VCE"]},
    {"season": 7, "episode": 92, "title": "European Travel Skills, Part One",
     "air_date": "2012-12-29",
     "exclude": COMPILATION, "exclude_note": "instructional episode, not a destination"},
    {"season": 7, "episode": 93, "title": "European Travel Skills, Part Two",
     "air_date": "2013-01-05",
     "exclude": COMPILATION, "exclude_note": "instructional episode, not a destination"},
    {"season": 7, "episode": 94, "title": "European Travel Skills, Part Three",
     "air_date": "2013-01-12",
     "exclude": COMPILATION, "exclude_note": "instructional episode, not a destination"},

    # ---- Season 8 (2014) ----
    {"season": 8, "episode": 95, "title": "Western Turkey",
     "air_date": "2014-10-04", "city": "Western Turkey", "country": "Turkey", "airports": ["ADB", "IST"]},
    {"season": 8, "episode": 96, "title": "Central Turkey",
     "air_date": "2014-10-11", "city": "Cappadocia", "country": "Turkey", "airports": ["ASR", "NAV"]},
    {"season": 8, "episode": 97, "title": "France's Loire: Château Country",
     "air_date": "2014-10-18", "city": "Loire Valley", "country": "France", "airports": ["TUF", "CDG"]},
    {"season": 8, "episode": 98, "title": "Paris Side Trips",
     "air_date": "2014-10-25", "city": "Paris", "country": "France", "airports": ["CDG"]},
    {"season": 8, "episode": 99, "title": "The Best of Israel",
     "air_date": "2014-11-01", "city": "Tel Aviv", "country": "Israel", "airports": ["TLV"]},
    {"season": 8, "episode": 100, "title": "Palestine",
     "air_date": "2014-11-08", "city": "West Bank", "country": "Palestine", "airports": ["TLV", "AMM"],
     "note": "the West Bank has no international airport of its own; Tel Aviv (via the Allenby "
             "Bridge crossing) and Amman are the real-world gateways"},
    {"season": 8, "episode": 101, "title": "Italy's Riviera: Cinque Terre",
     "air_date": "2014-11-15", "city": "Cinque Terre", "country": "Italy", "airports": ["PSA", "GOA"]},
    {"season": 8, "episode": 102, "title": "Italy's Veneto: Verona, Padua, and Ravenna",
     "air_date": "2014-11-22", "city": "Verona", "country": "Italy", "airports": ["VRN", "VCE"]},
    {"season": 8, "episode": 103, "title": "Amsterdam",
     "air_date": "2014-11-29", "city": "Amsterdam", "country": "Netherlands", "airports": ["AMS"]},
    {"season": 8, "episode": 104, "title": "The Netherlands: Beyond Amsterdam",
     "air_date": "2014-12-06", "city": "Amsterdam", "country": "Netherlands", "airports": ["AMS"],
     "note": "Amsterdam Schiphol is the Netherlands' only major international gateway regardless "
             "of which region the episode tours"},
    {"season": 8, "episode": 105, "title": "Prague",
     "air_date": "2014-12-13", "city": "Prague", "country": "Czech Republic", "airports": ["PRG"]},
    {"season": 8, "episode": 106, "title": "Berlin",
     "air_date": "2014-12-20", "city": "Berlin", "country": "Germany", "airports": ["TXL", "FRA"],
     "note": "airports.json (OpenFlights) predates BER, same as the Berlin episode above"},

    # ---- Season 9 (2016) ----
    {"season": 9, "episode": 107, "title": "Germany's Hamburg and the Luther Trail",
     "air_date": "2016-10-08", "city": "Hamburg", "country": "Germany", "airports": ["HAM", "FRA"]},
    {"season": 9, "episode": 108, "title": "Germany's Dresden and Leipzig",
     "air_date": "2016-10-15", "city": "Dresden", "country": "Germany", "airports": ["DRS", "LEJ", "FRA"]},
    {"season": 9, "episode": 109, "title": "Germany's Frankfurt and Nürnberg",
     "air_date": "2016-10-22", "city": "Frankfurt", "country": "Germany", "airports": ["FRA", "NUE"]},
    {"season": 9, "episode": 110, "title": "Bulgaria",
     "air_date": "2016-10-29", "city": "Sofia", "country": "Bulgaria", "airports": ["SOF"],
     "note": CAPITAL_RULE_NOTE},
    {"season": 9, "episode": 111, "title": "Romania",
     "air_date": "2016-11-05", "city": "Bucharest", "country": "Romania", "airports": ["OTP"],
     "note": CAPITAL_RULE_NOTE},
    {"season": 9, "episode": 112, "title": "Assisi and Italian Country Charm",
     "air_date": "2016-11-12", "city": "Assisi", "country": "Italy", "airports": ["PEG", "FLR", "FCO"]},
    {"season": 9, "episode": 113, "title": "Siena and Tuscany's Wine Country",
     "air_date": "2016-11-19", "city": "Siena", "country": "Italy", "airports": ["FLR", "PSA"]},
    {"season": 9, "episode": 114, "title": "West England",
     "air_date": "2016-11-26", "city": "West England", "country": "United Kingdom",
     "airports": ["BRS", "LHR"]},
    {"season": 9, "episode": 115, "title": "Southeast England",
     "air_date": "2016-12-03", "city": "Southeast England", "country": "United Kingdom",
     "airports": ["LGW", "LHR"]},
    {"season": 9, "episode": 116, "title": "England's Cornwall",
     "air_date": "2016-12-10", "city": "Cornwall", "country": "United Kingdom", "airports": ["NQY", "LHR"]},

    # ---- Season 10 (2018-2019) -- a single special; Wikipedia's numbering
    # jumps from 117 straight to 131, and the article's own text notes an
    # unlisted Mediterranean-cruise special that never got a numbered row ----
    {"season": 10, "episode": 117, "title": "The Story of Fascism in Europe",
     "air_date": "2018-09-01",
     "exclude": COMPILATION, "exclude_note": "multi-country documentary special, not one destination"},

    # ---- Season 11 (2020) ----
    {"season": 11, "episode": 131, "title": "Austrian and Italian Alps",
     "air_date": "2020-10-15",
     "exclude": AMBIGUOUS, "exclude_note": "two countries named, no single gateway"},
    {"season": 11, "episode": 132, "title": "Swiss Alps",
     "air_date": "2020-10-22", "city": "Swiss Alps", "country": "Switzerland",
     "airports": ["ZRH", "GVA", "BRN"]},
    {"season": 11, "episode": 133, "title": "French Alps and Lyon",
     "air_date": "2020-10-29", "city": "Lyon", "country": "France", "airports": ["LYS", "GVA", "CDG"]},
    {"season": 11, "episode": 134, "title": "Germany's Fascist Story",
     "air_date": "2020-11-05", "city": "Frankfurt", "country": "Germany", "airports": ["FRA"],
     "note": "a single-country historical-theme episode touring multiple German sites, unlike the "
             "multi-country 'Story of Fascism in Europe' special in Season 10; Frankfurt is the "
             "nearest SEA gateway, same treatment as the other German regional episodes"},
    {"season": 11, "episode": 135, "title": "Egypt's Cairo",
     "air_date": "2020-11-12", "city": "Cairo", "country": "Egypt", "airports": ["CAI"]},
    {"season": 11, "episode": 136, "title": "Egypt's Nile, Alexandria, and Luxor",
     "air_date": "2020-11-19",
     "exclude": AMBIGUOUS, "exclude_note": "three Egyptian cities named, no single gateway"},
    {"season": 11, "episode": 137, "title": "Ethiopia: A Development Story",
     "air_date": "2020-11-26", "city": "Addis Ababa", "country": "Ethiopia", "airports": ["ADD"],
     "note": CAPITAL_RULE_NOTE},
    {"season": 11, "episode": 138, "title": "Why We Travel",
     "air_date": "2020-12-03",
     "exclude": COMPILATION, "exclude_note": "philosophical retrospective, not a destination"},

    # ---- Season 12 (2023) -- entirely archival art-history episodes, built
    # from footage spanning many countries and eras, not new single-
    # destination journeys. Episode 146 is skipped in Wikipedia's own table. ----
    {"season": 12, "episode": 139, "title": "Art of Prehistoric Europe", "air_date": "2023-10-01",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 140, "title": "Art of Ancient Greece", "air_date": "2023-10-08",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 141, "title": "Ancient Roman Art", "air_date": "2023-10-15",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 142, "title": "Art of the Roman Empire", "air_date": "2023-10-22",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 143, "title": "Art of the Early Middle Ages", "air_date": "2023-10-29",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 144, "title": "Art of the High Middle Ages", "air_date": "2023-11-05",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 145, "title": "Art of the Florentine Renaissance", "air_date": "2023-11-12",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 147, "title": "Art of the Renaissance Beyond Florence", "air_date": "2023-11-19",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 148, "title": "Baroque Art", "air_date": "2023-11-26",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 149, "title": "Art of the Impressionists and Beyond", "air_date": "2023-12-03",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 150, "title": "Art of the 20th Century", "air_date": "2023-12-10",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},
    {"season": 12, "episode": 151, "title": "Art of the Neoclassical and Romantic Ages", "air_date": "2023-12-17",
     "exclude": COMPILATION, "exclude_note": "archival art-history season, not a destination"},

    # ---- Season 13 (2025) ----
    {"season": 13, "episode": 152, "title": "Iceland's Reykjavík and the Golden Circle",
     "air_date": "2025-10-04", "city": "Reykjavík", "country": "Iceland", "airports": ["KEF"]},
    {"season": 13, "episode": 153, "title": "Iceland's Ring Road",
     "air_date": "2025-10-11", "city": "Iceland's Ring Road", "country": "Iceland", "airports": ["KEF"]},
    {"season": 13, "episode": 154, "title": "Kraków: Poland's Historic Capital",
     "air_date": "2025-10-18", "city": "Kraków", "country": "Poland", "airports": ["KRK"]},
    {"season": 13, "episode": 155, "title": "Poland's Warsaw and Gdańsk",
     "air_date": "2025-10-25", "city": "Warsaw", "country": "Poland", "airports": ["WAW", "GDN"]},
    {"season": 13, "episode": 156, "title": "Italy's Highlights",
     "air_date": "2025-10-29",
     "exclude": AMBIGUOUS, "exclude_note": "a national survey episode, not one destination"},
    {"season": 13, "episode": 157, "title": "Burgundy: A Gourmet Barge Cruise",
     "air_date": "2025-11-05", "city": "Burgundy", "country": "France", "airports": ["LYS", "CDG"]},
    {"season": 13, "episode": 158, "title": "Paris of the Parisians",
     "air_date": "2025-11-12", "city": "Paris", "country": "France", "airports": ["CDG"]},
    {"season": 13, "episode": 159, "title": "Istanbul: Capital of Emperors and Sultans",
     "air_date": "2025-11-19", "city": "Istanbul", "country": "Turkey", "airports": ["IST"]},
    {"season": 13, "episode": 160, "title": "Istanbul: Turkish Delights",
     "air_date": "2025-11-19", "city": "Istanbul", "country": "Turkey", "airports": ["IST"],
     "note": "released the same day as episode 159, same as Conan Must Go's season-1 quadruple "
             "release -- kept as its own row, and chef_traveler.py suffixes the trip_id"},
    {"season": 13, "episode": 161, "title": "London: A Royal Tour",
     "air_date": "2025-11-26", "city": "London", "country": "United Kingdom", "airports": ["LHR"]},
    {"season": 13, "episode": 162, "title": "London: Yesterday and Today",
     "air_date": "2025-12-03", "city": "London", "country": "United Kingdom", "airports": ["LHR"]},
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
        "source": f"Wikipedia episode table for Rick Steves' Europe (2000-2025) -- {WIKIPEDIA_URL}",
        "traveler": TRAVELER,
        "assumptions": {
            "start_date": "episode original air date (the only date the source publishes; "
                          "filming predates it)",
            "duration_days": TRIP_DAYS,
            "trip_shape": "round trip out of Seattle, nonstop each way",
            "origin_preference": list(ORIGIN_PREFERENCE),
            "flights_only": "an episode is kept only if a nonstop from SEA to the destination "
                            "airport exists in airline_routes_enhanced.csv",
            "route_data_vintage": "airline_routes_enhanced.csv is a present-day route snapshot, "
                                  "not a 2000-2025 schedule -- exclusions mean 'no nonstop today'",
            "seattle_europe_gap": "SEA has a present-day nonstop to exactly six European airports "
                                  "(CDG, LHR, FRA, AMS, DUB, KEF), which is why most of this show's "
                                  "destinations are excluded -- see this script's docstring",
            "capital_rule_episodes": "episodes titled by COUNTRY only get that country's CAPITAL as "
                                     "the destination -- see the capital rule in chef_trips.py",
            "single_home_airport": "SEA only, unlike the three-airport preferences the New York and "
                                   "Los Angeles travelers use -- Rick Steves' declared base has one "
                                   "major airport",
            "home_airport": "Seattle-Tacoma (SEA) -- Rick Steves lives in Edmonds, WA and the show's "
                            "company is headquartered there, per Ivan's instruction to use Seattle",
        },
    }
    write_outputs(OUT_CSV_PATH, OUT_JSON_PATH, trips, excluded, EPISODES, meta,
                  include_excluded=args.include_excluded)
    print_summary(trips, excluded, EPISODES, OUT_CSV_PATH, OUT_JSON_PATH)


if __name__ == "__main__":
    main()
