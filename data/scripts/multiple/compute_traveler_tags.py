"""
Derived from: data/processed/multiple/travelers_anon.json (built by build_travelers_anon.py)

Assigns TAGS to each traveler -- short, human-readable labels describing a
pattern that is TRUE OF THE DATA, not asserted by whoever authored the
itinerary -- and writes data/processed/multiple/traveler_tags.csv and .json.

Same relationship to travelers_anon.json as compute_traveler_entropy.py: this
reads that file and writes its own, rather than folding a field back into it,
so no build step ever reads its own output.

RULE 1 -- AIRLINE LOYALIST
--------------------------
A traveler is tagged "{Airline} Loyalist" when at least LOYALIST_THRESHOLD
(80%) of their trips are on a single airline.

THE DENOMINATOR IS TRIPS WITH A RECORDED CARRIER, NOT ALL TRIPS. Only the
hand-authored itineraries name an airline (see build_synthetic_trips.py); the
124 Kaggle-sourced travelers record a destination string and nothing else.
Counting those against the share would mean a traveler loses the tag because
of a gap in the source rather than because of how they fly. This matches the
"Airlines flown" chart on the traveler page exactly -- same denominator, same
exclusion -- so a 100% bar and a Loyalist chip can never contradict each
other. A traveler with NO carrier data gets no tag and no near-miss; the
answer is "unknown", which is not the same as "not loyal".

MINIMUM LOYALIST_MIN_TRIPS (5) CARRIER-RECORDED TRIPS. Two trips that
happened to be on the same airline are a coincidence, not loyalty, and 100%
of 2 would otherwise outrank 85% of 40. The floor changes nothing in the
current data -- the lowest-trip qualifier has 5 -- but it stops the rule from
degenerating the moment a short itinerary is added. Travelers below the floor
are recorded with `below_min_trips: true` so "no tag" is separable from "not
enough evidence", the same way entropy_is_informative works.

WHAT THE CURRENT DATA LOOKS LIKE (2026-08-17): 82 of 206 travelers have
carrier data, and their top-carrier share is strikingly bimodal -- 49 sit at
exactly 100% and the next-highest is 75%. Nobody at all lands between 80% and
100%, so the threshold is currently doing no cutting; anywhere from ~76% to
100% would tag the same 49 people. Worth knowing before reading any meaning
into the exact 80%.

TWO INTENDED LOYALISTS DO NOT GET THE TAG, AND THAT IS THE RULE WORKING.
Pablo Picasso (3 of 4 United, 75%) and Edward Hopper (7 of 10 United, 70%)
were authored as United travelers, but some of their routes -- BCN-ORD,
SFO-HKG, SFO-TPE -- aren't flown by United, so build_synthetic_trips.py put
them on the carrier that does fly them. The tag describes the trips as
recorded, not the author's intent, which is the whole point of computing it
instead of declaring it. Both appear in the output with their real share.

RULE 2 -- HOME HUB
------------------
A traveler whose home city is a hub for exactly one of the airlines in
AIRLINE_HUBS is tagged "{Airline} Hub"; one whose city is a hub for two or
more is tagged "Multi Hub" INSTEAD of the individual tags (Ivan's call: the
interesting fact about Chicago is that no single airline owns it, and three
chips on a 180px card is not a card). Which airlines is still in the JSON,
and the chip draws one colored dot per airline.

THE UNIT IS THE CITY, NOT THE AIRPORT. Every New York resident is Multi Hub,
whether they fly out of EWR (United), JFK or LGA (Delta and American) --
because the question the tag answers is "does this person have a choice of
airline at home?", and a New Yorker does. Splitting by airport would tag
three neighbours three different ways.

DECLARED BASES ONLY (Ivan's call). All 82 hand-authored travelers state where
they live; the other 124 have a base INFERRED from their nationality by
build_travelers.py, and "Washington, D.C." is simply the default US city for
an American -- 20 travelers carry it without the source ever saying where
they live. A hub chip on those would report a guess as a fact about someone's
home. They're recorded here with base_inference so the skip is visible.

THE CITY TABLE IS VERIFIED, NOT TRUSTED. Every declared traveler's trips
depart from exactly one airport -- that airport IS their home airport, stated
by the data rather than by this table -- so every match is checked against it.
`home_airport_is_hub` is False when a traveler matched to, say, Chicago
doesn't depart from a Chicago hub airport. It never suppresses the tag: the
declared city is the fact the rule is about.

A False is not automatically an error, and today all three are real:

    Barry Allen  Chicago -> ORD, flies MDW (Midway)
    Artemis      Chicago -> ORD, flies MDW (Midway)
    Clark Kent   Houston -> IAH, flies HOU (Hobby)

All three are Southwest travelers, and Southwest flies the secondary field in
both metros -- they live in the hub city and use the airport the hub airline
isn't at, which is exactly the kind of thing the tag is worth knowing about.
The check exists because a genuine typo in AIRLINE_HUBS would surface the same
way, so anything ABOVE these three is worth reading as a table bug.

CITY NAMES ARE MATCHED THROUGH AN ALIAS TABLE because the same city is
spelled two ways in the data ("Washington, D.C." and "Washington", both
declared, both really D.C. -- their home airports are IAD and DCA). Matching
is also restricted to base_country_code == "US", so a "Portland" or a
"Manchester" somewhere else can never collide with a US hub.

ADDING A RULE: write a function taking the traveler dict and returning
(tags, diagnostics), and add it to the loop in compute(). Everything
downstream -- the CSV column, the API field, the chips -- is a list of tags
and does not know how many rules produced them.

Usage:
    python compute_traveler_tags.py
    python compute_traveler_tags.py --threshold 0.9 --min-trips 10
"""

import argparse
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
TRAVELERS_PATH = PROCESSED_DIR / "travelers_anon.json"
OUT_CSV = PROCESSED_DIR / "traveler_tags.csv"
OUT_JSON = PROCESSED_DIR / "traveler_tags.json"

LOYALIST_THRESHOLD = 0.80
LOYALIST_MIN_TRIPS = 5

# --------------------------------------------------------------------------
# Carrier name shortening.
#
# PORT OF frontend/src/lib/airlineColors.ts shortenCarrier(). Kept in sync by
# hand -- if you add an override or a noise word in one, add it in the other.
# The duplication is deliberate: the chart labels its segments in the browser
# from data the API already sends, and this script has to be runnable and
# readable on its own (someone reading traveler_tags.csv needs "Delta
# Loyalist", not "Delta Air Lines Inc. Loyalist"). The full legal name is
# carried alongside every label, so anything joining on the carrier joins on
# that and never on the short form.
# --------------------------------------------------------------------------

# Trailing noise is stripped word by word, not by one regex: "Inc\.?\b" leaves
# the dot on "Example Airways Inc." (no word boundary after a final period),
# and a rule that strips "Airlines" misses the bare "Air" in "Envoy Air".
TRAILING_NOISE = {
    "inc", "co", "corp", "ltd", "plc", "llc", "lp", "limited", "group",
    "sa", "cv", "airlines", "airline", "airways", "air", "lines",
}

# Carriers whose legal name shortens to something unhelpful, plus the four
# anchor airlines from airlineColors.ts (whose `short` values these repeat).
SHORT_NAME_OVERRIDES = {
    "Delta Air Lines Inc.": "Delta",
    "United Air Lines Inc.": "United",
    "American Airlines Inc.": "American",
    "Frontier Airlines Inc.": "Frontier",
    "Concesionaria Vuela Compania De Aviacion SA de CV (Volaris)": "Volaris",
    "Aeroenlaces Nacionales, S.A. de C.V. d/b/a VivaAerobus": "VivaAerobus",
    "Compagnie Natl Air France": "Air France",
    "Klm Royal Dutch Airlines": "KLM",
    "All Nippon Airways Co.": "ANA",
    "Iberia Air Lines Of Spain": "Iberia",
    "TAP-TAP Air Portugal": "TAP",
    "Sun Country Airlines d/b/a MN Airlines": "Sun Country",
    "Porter Airlines Limited (PACL)": "Porter",
    "Eva Airways Corporation": "EVA Air",
    "Japan Air Lines Co. Ltd.": "Japan Airlines",
    "Korean Air Lines Co. Ltd.": "Korean Air",
    "Cathay Pacific Airways Ltd.": "Cathay Pacific",
}


def shorten_carrier(carrier_name: str) -> str:
    """"Southwest Airlines Co." -> "Southwest". Never returns empty: a carrier
    named entirely with noise words keeps its last word."""
    override = SHORT_NAME_OVERRIDES.get(carrier_name)
    if override:
        return override

    # Everything after a "dba"/"d/b/a" restates the same operator
    # ("CommuteAir LLC dba CommuteAir"), so only the first half is useful.
    head = re.split(r"\bd/?b/?a\b", carrier_name, flags=re.IGNORECASE)[0]
    head = re.sub(r"\s*\(.*?\)\s*", " ", head)
    words = re.sub(r"\s{2,}", " ", head).strip().split()
    if not words:
        return carrier_name

    while len(words) > 1 and words[-1].lower().rstrip(".,") in TRAILING_NOISE:
        words.pop()
    return " ".join(words).rstrip(".,") or carrier_name


def slugify(value: str) -> str:
    """"Delta Air Lines Inc." -> "delta-air-lines-inc". Used for the tag id,
    which is built from the FULL carrier name so two carriers that shorten to
    the same word can never collide on it."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


# --------------------------------------------------------------------------
# Hub geography.
#
# HAND-CURATED, from Ivan's own lists -- not derived from the T-100 data, and
# not a computed "which airline flies the most seats here" ranking. A hub is a
# network-design fact (an airline banks connecting flights through it), which
# schedule volume alone doesn't establish; two of these cities have an airline
# with a big share and no hub operation. If this ever needs to be derived
# rather than declared, that's a different rule with a different name, not an
# edit to this table.
#
# Airports are here so the match can be CHECKED against each traveler's actual
# departure airport (see home_hub()), not just to be printed.
# --------------------------------------------------------------------------

# Airline short name -> {city as it appears in base_city: (hub airports,)}.
# Declaration order is the order airlines appear in a Multi Hub tag.
AIRLINE_HUBS: dict[str, dict[str, tuple[str, ...]]] = {
    "United": {
        "Chicago": ("ORD",),
        "Denver": ("DEN",),
        "Houston": ("IAH",),
        "New York City": ("EWR",),  # Newark Liberty -- the New York/Newark metro
        "San Francisco": ("SFO",),
        "Washington, D.C.": ("IAD",),  # Dulles
        "Los Angeles": ("LAX",),
    },
    "Delta": {
        "Atlanta": ("ATL",),
        "Detroit": ("DTW",),
        "Minneapolis": ("MSP",),
        "Salt Lake City": ("SLC",),
        "New York City": ("JFK", "LGA"),
    },
    "American": {
        "Charlotte": ("CLT",),
        "Chicago": ("ORD",),
        # DFW is one airport serving both cities, and travelers in this
        # dataset declare each of them -- so both map to it.
        "Dallas": ("DFW",),
        "Fort Worth": ("DFW",),
        "Los Angeles": ("LAX",),
        "Miami": ("MIA",),
        "New York City": ("JFK", "LGA"),
        "Philadelphia": ("PHL",),
        "Phoenix": ("PHX",),
        "Washington, D.C.": ("DCA",),  # Reagan National
    },
    "Alaska": {
        "Seattle": ("SEA",),
        "Portland": ("PDX",),
        "Anchorage": ("ANC",),
    },
}

# Full legal carrier names, so a hub tag can carry the same join key and the
# same brand color as a loyalist tag -- airlineColors.ts is keyed on the legal
# name, and "United" alone would draw no color.
HUB_AIRLINE_CARRIERS = {
    "United": "United Air Lines Inc.",
    "Delta": "Delta Air Lines Inc.",
    "American": "American Airlines Inc.",
    "Alaska": "Alaska Airlines Inc.",
}

# base_city spellings that mean a city already in AIRLINE_HUBS. The data
# carries "Washington" and "Washington, D.C." for the same place (both
# declared; their home airports are DCA and IAD), and normalising punctuation
# alone wouldn't merge them. Keys are compared after normalise_city().
CITY_ALIASES = {
    "washington": "Washington, D.C.",
    "washington dc": "Washington, D.C.",
    "new york": "New York City",
    "newark": "New York City",
    "nyc": "New York City",
    "dallas fort worth": "Dallas",
    "st paul": "Minneapolis",
    "minneapolis st paul": "Minneapolis",
}


def normalise_city(name: str) -> str:
    """"Washington, D.C." -> "washington dc". Punctuation-insensitive, so the
    alias table only has to carry genuinely different spellings."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", name.lower())).strip()


# city -> [airline, ...] and city -> {airports}, inverted from AIRLINE_HUBS so
# the table above stays written the way an airline's hubs are actually listed.
HUBS_BY_CITY: dict[str, list[str]] = {}
HUB_AIRPORTS_BY_CITY: dict[str, list[str]] = {}
for _airline, _cities in AIRLINE_HUBS.items():
    for _city, _airports in _cities.items():
        HUBS_BY_CITY.setdefault(_city, []).append(_airline)
        for _airport in _airports:
            HUB_AIRPORTS_BY_CITY.setdefault(_city, [])
            if _airport not in HUB_AIRPORTS_BY_CITY[_city]:
                HUB_AIRPORTS_BY_CITY[_city].append(_airport)

# Every hub city keyed the way base_city will arrive after normalisation.
HUB_CITY_BY_KEY = {normalise_city(city): city for city in HUBS_BY_CITY}
HUB_CITY_BY_KEY.update({key: city for key, city in CITY_ALIASES.items() if city in HUBS_BY_CITY})

# Cheap guards on the tables above, run at import so a typo fails loudly
# rather than silently producing one fewer tag.
assert set(HUB_AIRLINE_CARRIERS) == set(AIRLINE_HUBS), "every hub airline needs a legal name"
assert all(
    shorten_carrier(legal) == short for short, legal in HUB_AIRLINE_CARRIERS.items()
), "a hub airline's short name must match what shorten_carrier() produces"


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------

def carrier_counts(traveler: dict) -> Counter:
    """Trips per airline. Trips with no carrier are absent entirely rather
    than counted under a "None" key -- they are outside the denominator.
    A layover leg is excluded too, by the same rule as trip_count and
    destination entropy: Atlanta and Paris on a Houston-to-Lisbon trip
    shouldn't move the needle on which airline someone "flies", any more than
    they should count as places visited. See gomez_flight_log.md."""
    return Counter(
        trip["carrier_name"] for trip in traveler["trips"]
        if trip.get("carrier_name") and not trip.get("layover")
    )


def airline_loyalist(
    traveler: dict,
    threshold: float = LOYALIST_THRESHOLD,
    min_trips: int = LOYALIST_MIN_TRIPS,
) -> tuple[list[dict], dict]:
    """Returns (tags, diagnostics). Diagnostics are emitted for every
    traveler, tagged or not, so the file answers "why doesn't this person
    have the tag?" without re-deriving anything."""
    counts = carrier_counts(traveler)
    n = sum(counts.values())

    if n == 0:
        # No trip of theirs names an airline. Unknown, not disloyal.
        return [], {
            "trips_with_carrier": 0,
            "distinct_carriers": 0,
            "top_carrier": None,
            "top_carrier_share": None,
            "below_min_trips": False,
        }

    # Ties broken by name so a traveler split evenly between two carriers
    # always reports the same one, rather than whichever hashed first.
    top_carrier, top_n = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    share = top_n / n
    diagnostics = {
        "trips_with_carrier": n,
        "distinct_carriers": len(counts),
        "top_carrier": top_carrier,
        "top_carrier_share": round(share, 4),
        # True only when the share WOULD have qualified but the evidence is
        # too thin -- so this flags a near-miss worth revisiting, not every
        # traveler with few trips.
        "below_min_trips": share >= threshold and n < min_trips,
    }

    if share < threshold or n < min_trips:
        return [], diagnostics

    return [{
        "kind": "airline_loyalist",
        "tag_id": f"airline-loyalist:{slugify(top_carrier)}",
        "label": f"{shorten_carrier(top_carrier)} Loyalist",
        # The full legal name, for anything joining back to the trip data.
        "carrier_name": top_carrier,
        # One entry per airline the chip draws a dot for. A list even here,
        # so every tag kind renders through the same code path.
        "carrier_names": [top_carrier],
        "share": round(share, 4),
        "trips": top_n,
        "denominator": n,
    }], diagnostics


def home_airport(traveler: dict) -> str | None:
    """The single airport all this traveler's trips depart from, or None if
    their trips record several (or none).

    Every hand-authored traveler currently has exactly one -- their itinerary
    is built from a declared home base -- which is what makes this usable as
    an independent check on the city table. None is the honest answer for a
    Kaggle traveler, whose trips record no airport at all."""
    origins = {trip["origin_airport"] for trip in traveler["trips"] if trip.get("origin_airport")}
    return origins.pop() if len(origins) == 1 else None


def hub_city_for(traveler: dict) -> str | None:
    """The hub city this traveler lives in, or None. US bases only -- every
    city in the table is American, and matching worldwide would let a
    "Portland" or a "Manchester" elsewhere collide with one."""
    if (traveler.get("base_country_code") or "").upper() != "US":
        return None
    base_city = traveler.get("base_city")
    if not base_city:
        return None
    return HUB_CITY_BY_KEY.get(normalise_city(base_city))


def home_hub(traveler: dict) -> tuple[list[dict], dict]:
    """"{Airline} Hub" for a one-airline hub city, "Multi Hub" for a city with
    two or more -- the individual tags are NOT also emitted in that case.

    Declared bases only: an inferred base is build_travelers.py's guess from
    nationality, and a chip saying where someone lives should not be built on
    one."""
    base_inference = traveler.get("base_inference")
    airport = home_airport(traveler)
    diagnostics = {
        "base_city": traveler.get("base_city"),
        "base_inference": base_inference,
        "home_airport": airport,
        "hub_city": None,
        "hub_airlines": [],
        # None when there's nothing to check against -- distinct from False,
        # which means the check ran and disagreed with the table.
        "home_airport_is_hub": None,
    }

    if base_inference != "declared":
        return [], diagnostics

    city = hub_city_for(traveler)
    if city is None:
        return [], diagnostics

    airlines = HUBS_BY_CITY[city]
    airports = HUB_AIRPORTS_BY_CITY[city]
    diagnostics["hub_city"] = city
    diagnostics["hub_airlines"] = list(airlines)
    if airport is not None:
        diagnostics["home_airport_is_hub"] = airport in airports

    carriers = [HUB_AIRLINE_CARRIERS[airline] for airline in airlines]
    if len(airlines) == 1:
        airline = airlines[0]
        return [{
            "kind": "airline_hub",
            "tag_id": f"airline-hub:{slugify(HUB_AIRLINE_CARRIERS[airline])}",
            "label": f"{airline} Hub",
            "carrier_name": HUB_AIRLINE_CARRIERS[airline],
            "carrier_names": carriers,
            "airlines": list(airlines),
            "hub_city": city,
            "hub_airports": list(airports),
        }], diagnostics

    return [{
        "kind": "multi_hub",
        # One id for every multi-hub city: the tag says "more than one airline
        # hubs where this person lives", and that's the same statement in
        # Chicago and in New York. The city is a field, not part of the id.
        "tag_id": "multi-hub",
        "label": "Multi Hub",
        # No single carrier -- deliberately null rather than the first of
        # them, so nothing downstream can treat a Multi Hub tag as being
        # about one airline. The dots come from carrier_names.
        "carrier_name": None,
        "carrier_names": carriers,
        "airlines": list(airlines),
        "hub_city": city,
        "hub_airports": list(airports),
    }], diagnostics


def compute(
    travelers: list[dict],
    threshold: float = LOYALIST_THRESHOLD,
    min_trips: int = LOYALIST_MIN_TRIPS,
) -> tuple[list[dict], dict]:
    """Pure function: travelers in, one row per traveler out. Every traveler
    gets a row -- an empty `tags` list is an answer."""
    rows = []
    for traveler in travelers:
        loyalist_tags, loyalist_diagnostics = airline_loyalist(traveler, threshold, min_trips)
        hub_tags, hub_diagnostics = home_hub(traveler)
        rows.append({
            "traveler_id": traveler["traveler_id"],
            "name": traveler["name"],
            "trip_count": traveler["trip_count"],
            **loyalist_diagnostics,
            **hub_diagnostics,
            # Rule order, not importance order -- but it does decide chip
            # order on the page, and loyalty (how they fly) reads better
            # first than geography (where they live).
            "tags": loyalist_tags + hub_tags,
        })

    tag_counts = Counter(tag["label"] for row in rows for tag in row["tags"])
    meta = {
        "source": "travelers_anon.json (built by build_travelers_anon.py)",
        "generated": date.today().isoformat(),
        "rules": {
            "airline_loyalist": {
                "threshold": threshold,
                "min_trips": min_trips,
                # Named explicitly because it is the one thing about this rule
                # someone will otherwise assume wrong.
                "denominator": "trips with a recorded carrier_name",
                "label_format": "{Airline} Loyalist",
            },
            "home_hub": {
                "unit": "base_city (US only), matched through CITY_ALIASES",
                "requires": "base_inference == 'declared'",
                "multi_hub": "replaces the individual {Airline} Hub tags",
                "airlines": {a: sorted(c) for a, c in AIRLINE_HUBS.items()},
                "hub_cities": {c: list(a) for c, a in sorted(HUBS_BY_CITY.items())},
            },
        },
        "travelers_total": len(travelers),
        "travelers_with_carrier_data": sum(1 for r in rows if r["trips_with_carrier"] > 0),
        "travelers_with_declared_base": sum(1 for r in rows if r["base_inference"] == "declared"),
        "travelers_tagged": sum(1 for r in rows if r["tags"]),
        "tag_counts": dict(sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "near_misses_below_min_trips": sum(1 for r in rows if r["below_min_trips"]),
        # 3 today, all real (see the module docstring): travelers who live
        # in a hub city and use its secondary airport. A jump here is the
        # signal that AIRLINE_HUBS has a wrong city or airport in it.
        "hub_city_airport_mismatches": sum(1 for r in rows if r["home_airport_is_hub"] is False),
    }
    return rows, meta


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--threshold", type=float, default=LOYALIST_THRESHOLD,
        help=f"Share of carrier-recorded trips on one airline. Default: {LOYALIST_THRESHOLD}.",
    )
    parser.add_argument(
        "--min-trips", type=int, default=LOYALIST_MIN_TRIPS,
        help=f"Carrier-recorded trips needed to qualify. Default: {LOYALIST_MIN_TRIPS}.",
    )
    args = parser.parse_args()

    if not TRAVELERS_PATH.exists():
        raise SystemExit(f"{TRAVELERS_PATH} not found -- run build_travelers_anon.py first.")
    with open(TRAVELERS_PATH, encoding="utf-8") as f:
        travelers = json.load(f)["travelers"]

    rows, meta = compute(travelers, threshold=args.threshold, min_trips=args.min_trips)
    # Tagged first, then by how concentrated their flying is; travelers with
    # no carrier data last rather than sorted as if their share were 0.
    rows.sort(key=lambda r: (
        not r["tags"], r["top_carrier_share"] is None, -(r["top_carrier_share"] or 0), r["name"],
    ))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({**meta, "travelers": rows}, f, indent=2, ensure_ascii=False)
    # The CSV flattens every list column to "; "-joined text -- it's for
    # reading, not for round-tripping. The JSON is the structured output.
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        fieldnames = [k for k in rows[0] if k != "tags"] + ["tags"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            flat = {k: "; ".join(map(str, v)) if isinstance(v, list) else v
                    for k, v in row.items() if k != "tags"}
            writer.writerow({**flat, "tags": "; ".join(t["label"] for t in row["tags"])})

    loyalist = meta["rules"]["airline_loyalist"]
    print(f"Loyalist rule: >= {loyalist['threshold']:.0%} of a traveler's trips on one airline, "
          f"min {loyalist['min_trips']} trips, over {loyalist['denominator']}.")
    print(f"  {meta['travelers_with_carrier_data']} of {meta['travelers_total']} travelers have "
          f"carrier data.")
    if meta["near_misses_below_min_trips"]:
        print(f"  {meta['near_misses_below_min_trips']} would qualify on share but have "
              f"fewer than {loyalist['min_trips']} trips.")
    print(f"Hub rule: home city in {len(HUBS_BY_CITY)} hub cities across "
          f"{len(AIRLINE_HUBS)} airlines; declared bases only.")
    print(f"  {meta['travelers_with_declared_base']} of {meta['travelers_total']} travelers "
          f"declare where they live.")
    if meta["hub_city_airport_mismatches"]:
        # Not an error on its own -- see the module docstring. Printed every
        # run so a NEW one is noticeable against the known three.
        print(f"  {meta['hub_city_airport_mismatches']} traveler(s) live in a hub city but "
              f"depart from another airport in it:")
        for r in rows:
            if r["home_airport_is_hub"] is False:
                print(f"    {r['name']:16} {r['hub_city']} "
                      f"{'/'.join(HUB_AIRPORTS_BY_CITY[r['hub_city']])} -> flies "
                      f"{r['home_airport']}")
    print()
    print(f"{meta['travelers_tagged']} travelers tagged:")
    for label, count in meta["tag_counts"].items():
        print(f"  {label:24} {count:3}")
    print()
    print(f"{'traveler':24} {'base':18} {'trips':>5} {'top share':>9}  tags")
    for r in rows[:12]:
        share = "  --  " if r["top_carrier_share"] is None else f"{r['top_carrier_share']:6.1%}"
        base = (r["base_city"] or "--")[:17]
        print(f"{r['name'][:23]:24} {base:18} {r['trips_with_carrier']:5} "
              f"{share:>9}  {'; '.join(t['label'] for t in r['tags'])}")
    print(f"  ... {len(rows) - 12} more")
    print()
    print(f"Wrote -> {OUT_CSV}")
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
