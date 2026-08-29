"""
Plog's psychocentric-allocentric scale, scored from data already in this repo.

Requires: data/reference/airports.json
          data/reference/travel_advisories.json
          data/processed/tourist_cities_enhanced.json
          data/processed/multiple/airline_routes_enhanced.csv

    >>> plog_categorize("Paris")
    (0.97, 0.03)
    >>> plog_categorize("Sudan")
    (0.09, 0.91)

ONE AXIS, RETURNED AS TWO NUMBERS. Plog's scale is a single continuum, so the
pair always sums to 1.0 -- allocentric is just 1 - psychocentric. It is
returned as a tuple because that is the asked-for shape and because it reads
the way the diagram does, not because the two are measured separately.

WHAT IS ACTUALLY BEING MEASURED. Plog's construct is a property of PEOPLE:
psychocentrics prefer the familiar and packaged, allocentrics the novel and
independent. Destinations only acquire a position on the scale second-hand,
from the kind of traveler who goes there -- which is how Plog himself mapped
them. Nothing in this repo observes traveler personality, so this scores the
destination side directly, from four things that CAN be measured:

  us_access     0.45  distinct US airports with a NONSTOP to the place, and
                      distinct carriers flying them. The largest weight,
                      because familiarity is relative to the market you leave
                      from, and every traveler in this dataset is American.
                      Directional: what counts is whether an American can get
                      there without connecting.
  connectivity  0.35  distinct carriers and nonstop routes serving the place,
                      worldwide. Carries the ordering among the two thirds of
                      destinations with no US nonstop at all, where us_access
                      is flat zero and would otherwise leave Bali and the
                      Seychelles indistinguishable.
  scale         0.10  city / country population. Big places are familiar
                      places -- but only a little; see the correction below.
  friction      0.10  an FCDO "advise against travel" notice pushes toward
                      allocentric. Deliberately small: 73 countries carry one
                      and they are not all remote -- Mexico does, and Cancun
                      is psychocentric by every other measure.

THE HONOLULU / BUENOS AIRES CORRECTION. The first version of this file scored
Honolulu at 0.54 allocentric and Buenos Aires at 0.14 -- both backwards, and
Ivan caught it. Two causes, both now fixed:

  * MICHELIN WAS WORTH 0.25 AND POINTED THE WRONG WAY. The Guide does not
    publish in Hawaii, so Honolulu scored 0 restaurants and forfeited a
    quarter of the scale outright; it launched in Argentina in 2023, so
    Buenos Aires scored 50 and collected nearly all of it. That signal
    measures where Michelin publishes, which is not where Americans go. It is
    dropped from the scoring entirely -- explain() still reports the count,
    because it helps diagnose a score, but it carries no weight.
  * POPULATION WAS WORTH 0.20 AND MEASURES THE WRONG THING. Buenos Aires has
    14M people and Honolulu 345k, which says nothing about how many Americans
    have been to either. Cut to 0.10.

The replacement, us_access, gets it right for the same reason the old signals
got it wrong: Honolulu has nonstops from 29 US airports on 13 carriers,
Buenos Aires from 7 on 6. Hawaii is a domestic flight; Argentina is a
long-haul almost nobody in this dataset takes.

SCORES ARE RELATIVE WITHIN KIND, not absolute quantities. A city is scaled
against the other cities, a country against other countries, an airport
against the airports that have at least one scheduled route. Comparing a
city's number with a country's is meaningless, and resolve() records which
kind answered. Normalisation is min-max on the log value, NOT a percentile
rank -- see _rescale() for why the percentile version had to go.

THIS SCALE IS AMERICAN, AND THAT IS A CHOICE. us_access makes the score
answer "how familiar is this to a US traveler", not "how familiar is this in
general". That fits this dataset -- every cohort in it is American -- but Bali
reads as far more allocentric here than it would to an Australian, and this
file should not be reused for a non-US population without revisiting that
weight.

WHAT IS NOT USED. processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv holds real
passenger volumes, which would be the ideal signal -- but it covers 49
countries, and Algeria, Sudan and the Seychelles are not among them. Its
coverage tracks the aviation statistics source, not tourism, so treating an
absence as evidence of remoteness would be inventing data. It is left out
entirely rather than used where it happens to exist.

Usage:
    python plog_categorize.py            # self-check against the worked examples
    python plog_categorize.py Paris ALG  # score specific places
"""

import csv
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
AIRPORTS_PATH = DATA_DIR / "reference" / "airports.json"
ADVISORIES_PATH = DATA_DIR / "reference" / "travel_advisories.json"
CITIES_PATH = DATA_DIR / "processed" / "tourist_cities_enhanced.json"
ROUTES_PATH = DATA_DIR / "processed" / "multiple" / "airline_routes_enhanced.csv"

# Revised after the first version put Honolulu at 0.54 allocentric and Buenos
# Aires at 0.14 -- see THE HONOLULU / BUENOS AIRES CORRECTION in the module
# docstring. us_access is now the largest single weight and Michelin is gone.
WEIGHTS = {"us_access": 0.45, "connectivity": 0.35, "scale": 0.10, "friction": 0.10}
CARRIER_SHARE = 0.6      # within either connectivity term: carriers vs raw routes
# Michelin counts are still READ and still reported by explain(), because they
# are useful for diagnosing a score. They no longer CARRY any weight -- see the
# correction note in the docstring.
MICHELIN_RADIUS = "within_50km"
CITY_AIRPORT_MAX_KM = 100.0   # an airport further out is not that city's airport

# Countries and cities are commonly written more than one way; resolve() checks
# these before giving up. Not an exhaustive gazetteer -- just the spellings a
# caller is likely to type.
ALIASES = {
    "usa": "United States", "u.s.": "United States", "us": "United States",
    "united states of america": "United States", "america": "United States",
    "uk": "United Kingdom", "great britain": "United Kingdom", "britain": "United Kingdom",
    "england": "United Kingdom", "holland": "Netherlands", "uae": "United Arab Emirates",
    "south korea": "Korea, South", "north korea": "Korea, North",
    "czechia": "Czech Republic", "turkiye": "Turkey", "burma": "Myanmar",
    "nyc": "New York", "new york city": "New York", "the seychelles": "Seychelles",
}


def _norm(text):
    return " ".join(str(text).strip().casefold().split())


def _rescale(values_by_key):
    """Map each key's value onto 0-1 by min-max, on the already-log-scaled
    input.

    NOT a percentile rank, which is what this did first and which was wrong
    for a reason worth keeping written down. Two thirds of the cities in the
    reference set have NO nonstop from the United States, so the rank of any
    non-zero us_access value started at 0.65 and the whole meaningful range
    was squeezed into the top third: Honolulu's 29 US origins ranked 0.94 and
    Buenos Aires' 7 ranked 0.82, a gap of 0.12 standing in for a four-fold
    difference in how reachable the two are. Min-max on the log value keeps
    that gap (0.67 vs 0.46). The cost is that one extreme destination sets the
    top of the scale; log1p upstream is what keeps that from mattering."""
    values = list(values_by_key.values())
    lo, hi = min(values), max(values)
    if hi <= lo:
        return {key: 0.5 for key in values_by_key}
    span = hi - lo
    return {key: (value - lo) / span for key, value in values_by_key.items()}


@lru_cache(maxsize=1)
def _tables():
    """Everything, built once: per-kind raw signals, then percentile ranks."""
    airports = {a["iata"]: a for a in json.load(open(AIRPORTS_PATH, encoding="utf-8"))["airports"]
                if a.get("iata")}
    cities = json.load(open(CITIES_PATH, encoding="utf-8"))["cities"]
    advisories = json.load(open(ADVISORIES_PATH, encoding="utf-8"))

    # --- connectivity, per airport -------------------------------------
    us_codes = {code for code, a in airports.items() if a["country"] == "United States"}
    routes, carriers = {}, {}
    us_origins, us_carriers = {}, {}
    with ROUTES_PATH.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            origin, destination = row["Departure"], row["Destination"]
            for code in (origin, destination):
                routes[code] = routes.get(code, 0) + 1
                carriers.setdefault(code, set()).add(row["Airline ID"])
            # Nonstops REACHING this place from the United States. Directional
            # on purpose: what matters is whether an American can get there
            # without connecting, not the route's existence in the abstract.
            if origin in us_codes:
                us_origins.setdefault(destination, set()).add(origin)
                us_carriers.setdefault(destination, set()).add(row["Airline ID"])

    def _blend(n_carriers, n_units):
        """log1p keeps this from being a contest between the two or three
        largest hubs: JFK has 25x Seychelles' routes, and untransformed that
        one gap would swamp every other difference in the file."""
        return CARRIER_SHARE * math.log1p(n_carriers) + (1 - CARRIER_SHARE) * math.log1p(n_units)

    def connectivity(codes):
        n_routes = sum(routes.get(c, 0) for c in codes)
        n_carriers = len(set().union(*[carriers.get(c, set()) for c in codes])) if codes else 0
        return _blend(n_carriers, n_routes)

    def us_access(codes):
        """How reachable this place is from the United States without
        connecting: distinct US airports with a nonstop, and distinct carriers
        flying them. THE LARGEST WEIGHT, because every traveler in this
        dataset is American and Plog's familiarity pole is relative to the
        market a traveler departs from -- see the module docstring."""
        origins = set().union(*[us_origins.get(c, set()) for c in codes]) if codes else set()
        airlines = set().union(*[us_carriers.get(c, set()) for c in codes]) if codes else set()
        return _blend(len(airlines), len(origins))

    # --- per-city rows --------------------------------------------------
    city_rows, city_by_name, city_by_key, city_by_id = {}, {}, {}, {}
    country_airports, country_pop, country_michelin = {}, {}, {}
    for city in cities:
        codes = [a["iata"] for a in city["airports"]["airports"]
                 if a.get("iata") and a.get("distance_km", 0) <= CITY_AIRPORT_MAX_KM]
        counts = (city.get("michelin_restaurants") or {}).get("counts") or {}
        michelin = counts.get(MICHELIN_RADIUS, 0) or 0
        population = city.get("population") or 0
        iso2 = city.get("iso2")
        key = (city["city"], city["country"])

        city_rows[key] = {
            "kind": "city", "name": city["city"], "country": city["country"], "iso2": iso2,
            "airports": codes,
            "connectivity": connectivity(codes),
            "us_access": us_access(codes),
            "scale": math.log1p(population),
            "friction": 1.0 if iso2 in advisories else 0.0,
            "michelin": michelin, "population": population,
        }
        city_by_key[key] = key
        city_by_id[str(city["simplemaps_id"])] = key
        city_by_name.setdefault(_norm(city["city"]), []).append(key)
        city_by_name.setdefault(_norm(city.get("city_ascii") or ""), []).append(key)

        country_airports.setdefault(city["country"], set()).update(codes)
        country_pop[city["country"]] = country_pop.get(city["country"], 0) + population
        country_michelin[city["country"]] = country_michelin.get(city["country"], 0) + michelin

    # Countries get every airport the airport file places in them, not just the
    # ones near a scored city -- otherwise a country whose tourism is not in its
    # big cities reads as unreachable.
    for code, airport in airports.items():
        country_airports.setdefault(airport["country"], set()).add(code)

    country_iso2 = {}
    for city in cities:
        country_iso2.setdefault(city["country"], city.get("iso2"))

    country_rows = {}
    for country, codes in country_airports.items():
        iso2 = country_iso2.get(country)
        country_rows[country] = {
            "kind": "country", "name": country, "country": country, "iso2": iso2,
            "airports": sorted(codes),
            "connectivity": connectivity(codes),
            "us_access": us_access(codes),
            "scale": math.log1p(country_pop.get(country, 0)),
            "friction": 1.0 if iso2 in advisories else 0.0,
            "michelin": country_michelin.get(country, 0),
            "population": country_pop.get(country, 0),
        }

    # Airports inherit their country's friction and their nearest scored city's
    # infrastructure/scale -- an airport has no Michelin count of its own.
    city_for_airport = {}
    for key, row in city_rows.items():
        for code in row["airports"]:
            best = city_for_airport.get(code)
            if best is None or row["population"] > city_rows[best]["population"]:
                city_for_airport[code] = key

    # Only airports with at least one scheduled route are ranked. The airport
    # file carries 5,879 IATA codes and just 3,704 appear in any route; the
    # other 2,175 are airfields with no commercial service. Leaving them in the
    # reference population would push every served airport up the percentile
    # for beating a pile of places nothing flies to -- the Seychelles' SEZ came
    # out at the 51st percentile that way, which says more about the airfields
    # below it than about the Seychelles.
    airport_rows = {}
    for code, airport in airports.items():
        if code not in routes:
            continue
        home = city_for_airport.get(code)
        home_row = city_rows.get(home) if home else None
        iso2 = country_iso2.get(airport["country"])
        airport_rows[code] = {
            "kind": "airport", "name": f"{airport['city']} ({code})",
            "country": airport["country"], "iso2": iso2, "airports": [code],
            "connectivity": connectivity([code]),
            "us_access": us_access([code]),
            "scale": home_row["scale"] if home_row else 0.0,
            "friction": 1.0 if iso2 in advisories else 0.0,
            "michelin": home_row["michelin"] if home_row else 0,
            "population": home_row["population"] if home_row else 0,
            "city_key": home,
        }

    scored = {}
    for kind, rows in (("city", city_rows), ("country", country_rows), ("airport", airport_rows)):
        ranks = {signal: _rescale({k: r[signal] for k, r in rows.items()})
                 for signal in ("us_access", "connectivity", "scale")}
        for key, row in rows.items():
            parts = {
                "us_access": ranks["us_access"][key],
                "connectivity": ranks["connectivity"][key],
                "scale": ranks["scale"][key],
                # The only signal that is not a rank: it is a flag, and it
                # subtracts. 1.0 friction means "advised against", which is
                # allocentric, so it enters as its complement.
                "friction": 1.0 - row["friction"],
            }
            row["parts"] = parts
            row["psychocentric"] = round(sum(WEIGHTS[s] * v for s, v in parts.items()), 4)
        scored[kind] = rows

    return {
        "city": scored["city"], "country": scored["country"], "airport": scored["airport"],
        "city_by_name": city_by_name,
        "city_by_id": city_by_id,
        "country_by_name": {_norm(c): c for c in country_rows},
    }


def resolve(query):
    """The row this query names, or None. Precedence is alias, then airport
    code, then country, then city -- so a bare 'ALG' is Algiers airport rather
    than a fuzzy country match, but 'USA' is the United States rather than
    Concord Regional, which really does hold that code. A city name shared by several countries resolves to
    the most populous, which is what a bare 'Paris' or 'Melbourne' means in
    practice; pass ('Paris', 'France') as a tuple to be explicit."""
    tables = _tables()

    if isinstance(query, (tuple, list)) and len(query) == 2:
        key = (str(query[0]), str(query[1]))
        if key in tables["city"]:
            return tables["city"][key]
        for (name, country), row in tables["city"].items():
            if _norm(name) == _norm(query[0]) and _norm(country) == _norm(query[1]):
                return row
        return None

    text = str(query).strip()
    key = _norm(text)
    # Aliases are resolved BEFORE the airport branch, because some of them
    # collide with real IATA codes: USA is Concord Regional in North Carolina,
    # and someone typing "USA" means the country every time.
    aliased = ALIASES.get(key)
    if aliased is not None:
        key = _norm(aliased)
    elif len(text) == 3 and text.isalpha() and text.upper() in tables["airport"]:
        return tables["airport"][text.upper()]

    country = tables["country_by_name"].get(key)
    if country:
        return tables["country"][country]

    candidates = tables["city_by_name"].get(key)
    if candidates:
        return max((tables["city"][c] for c in dict.fromkeys(candidates)),
                   key=lambda r: r["population"])
    return None


def plog_categorize(query):
    """(psychocentric, allocentric) for a city, country or airport code.

    Both are 0-1 and sum to 1.0. Each is a PERCENTILE RANK within the query's
    own kind -- a city among cities, a country among countries -- so the pair
    says "more psychocentric than N% of comparable destinations", not that the
    place is N% psychocentric in the absolute.

    Raises LookupError when the place is not in the reference data. That is
    deliberate: a neutral (0.5, 0.5) would be an invented answer, and this
    project does not invent."""
    row = resolve(query)
    if row is None:
        raise LookupError(
            f"{query!r} is not a city, country or IATA code in the reference data. "
            f"Pass a 3-letter airport code, a country name, or ('City', 'Country')."
        )
    psychocentric = row["psychocentric"]
    return (psychocentric, round(1.0 - psychocentric, 4))


def psychocentric_for_city_id(simplemaps_id):
    """Psychocentric score (0-1) for a tourist_cities simplemaps_id, or None.

    The id path exists for callers that have already matched a destination to
    a city -- match_trip_cities.py above all. Going back through the city NAME
    would re-run a fuzzy resolution that has already been done properly, and
    would have to survive accents ("Cancun" vs "Cancún") on the way. The id is
    the same key both files are built on, so it cannot drift."""
    tables = _tables()
    key = tables["city_by_id"].get(str(simplemaps_id))
    if key is None:
        return None
    return tables["city"][key]["psychocentric"]


def explain(query):
    """The same answer with its working shown -- which kind matched, the raw
    counts, and each weighted component. Use this before trusting a number."""
    row = resolve(query)
    if row is None:
        raise LookupError(f"{query!r} not found")
    return {
        "query": query, "matched": row["name"], "kind": row["kind"],
        "country": row["country"], "airports": len(row["airports"]),
        "michelin_50km": row["michelin"], "population": row["population"],
        "advisory": bool(row["friction"]),
        "components": {s: round(v, 4) for s, v in row["parts"].items()},
        "weighted": {s: round(WEIGHTS[s] * v, 4) for s, v in row["parts"].items()},
        "psychocentric": row["psychocentric"],
        "allocentric": round(1.0 - row["psychocentric"], 4),
    }


# The examples that defined the brief, kept as an executable check rather than
# a comment. Every ALLOCENTRIC entry must score below every PSYCHOCENTRIC one.
ALLOCENTRIC_EXAMPLES = ["Algeria", "Sudan", "Seychelles"]
PSYCHOCENTRIC_EXAMPLES = ["Milan", "Paris", "New York City", "Cancun"]

# Pairwise judgements the absolute lists above cannot express:
# (should be MORE psychocentric, should be MORE allocentric). The first is a
# real correction to a real mistake this file made, kept executable so the
# mistake cannot come back quietly.
ORDERING_EXAMPLES = [
    ("Honolulu", "Buenos Aires"),   # v1 had these backwards: 0.54 vs 0.14 allocentric
    ("Cancun", "Phnom Penh"),
    ("Paris", "Algeria"),
]


def self_check():
    allo = {q: plog_categorize(q)[0] for q in ALLOCENTRIC_EXAMPLES}
    psycho = {q: plog_categorize(q)[0] for q in PSYCHOCENTRIC_EXAMPLES}
    worst_psycho = min(psycho.items(), key=lambda kv: kv[1])
    best_allo = max(allo.items(), key=lambda kv: kv[1])
    ok = best_allo[1] < worst_psycho[1]

    pairs = []
    for more_psycho, more_allo in ORDERING_EXAMPLES:
        a, b = plog_categorize(more_psycho)[0], plog_categorize(more_allo)[0]
        passed = a > b
        pairs.append((more_psycho, a, more_allo, b, passed))
        ok = ok and passed
    return ok, allo, psycho, best_allo, worst_psycho, pairs


def main():
    if len(sys.argv) > 1:
        for query in sys.argv[1:]:
            try:
                detail = explain(query)
            except LookupError as exc:
                print(f"{query}: {exc}")
                continue
            p, a = detail["psychocentric"], detail["allocentric"]
            print(f"{query} -> ({p}, {a})  [{detail['kind']}: {detail['matched']}]")
            print(f"    components {detail['components']}")
        return

    ok, allo, psycho, best_allo, worst_psycho, pairs = self_check()
    print("ALLOCENTRIC examples (want low psychocentric):")
    for q, v in sorted(allo.items(), key=lambda kv: kv[1]):
        print(f"  {q:16} ({v}, {round(1-v, 4)})")
    print("PSYCHOCENTRIC examples (want high psychocentric):")
    for q, v in sorted(psycho.items(), key=lambda kv: kv[1]):
        print(f"  {q:16} ({v}, {round(1-v, 4)})")
    print("ORDERING (left must be more psychocentric than right):")
    for more_psycho, a, more_allo, b, passed in pairs:
        print(f"  {'ok  ' if passed else 'FAIL'} {more_psycho} ({a:.3f}) > {more_allo} ({b:.3f})")
    print()
    if ok:
        print(f"SELF-CHECK PASSED -- highest allocentric example {best_allo[0]} "
              f"({best_allo[1]}) < lowest psychocentric example {worst_psycho[0]} "
              f"({worst_psycho[1]})")
    else:
        failures = [f"{mp} ({a:.3f}) is not above {ma} ({b:.3f})"
                    for mp, a, ma, b, passed in pairs if not passed]
        if best_allo[1] >= worst_psycho[1]:
            failures.insert(0, f"{best_allo[0]} ({best_allo[1]}) is not below "
                               f"{worst_psycho[0]} ({worst_psycho[1]})")
        raise SystemExit("SELF-CHECK FAILED -- the weights no longer reproduce the "
                         "worked examples:\n  " + "\n  ".join(failures))


if __name__ == "__main__":
    main()
