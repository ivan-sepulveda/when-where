"""
Derived from: data/processed/multiple/travelers_anon.json (built by
build_travelers_anon.py) and data/processed/tourist_cities_enhanced.json
(built by build_tourist_cities_enhanced.py)

Resolves each DESTINATION a traveler's trips go to onto a city in
tourist_cities_enhanced.json, and writes
data/processed/multiple/trip_city_matches.csv and .json.

The point is to let a trip carry that city's UNESCO / Michelin scores (and
its weather normals) without the API doing any name matching of its own --
see backend/README.md: the API reads what this pipeline already produced and
adds only date-dependent resolution on top. Weather is deliberately NOT
computed here: it depends on each trip's own dates, which is exactly the one
thing the backend resolves per request.

KEYED BY DESTINATION, NOT BY TRIP. There are 2,217 trip rows but only 174
distinct (destination_city, destination_country) pairs, and the mapping from
a place to a city record is a fact about the PLACE -- adding another trip to
Cancun cannot change it. So this file has ~174 rows, is small enough to read
end to end when a match looks wrong, and does not need regenerating when a
trip is added to a destination that is already in it. (It does need
regenerating when a NEW destination appears -- the backend treats an absent
destination as unmatched, so a stale file degrades to "no scores" rather
than to a wrong score.)

MATCHING IS DELIBERATELY CONSERVATIVE. Only four things are tried, in order,
and each one is recorded in `match_method` so a match can be audited:

  exact          normalised city name + country name agree
  ascii          same, against the city's own city_ascii spelling
  city_alias     a hand-listed trip-side spelling (CITY_ALIASES below)
  country_alias  the country is spelled differently on the two sides
                 (COUNTRY_ALIASES below)

There is NO fuzzy/nearest-name fallback and NO nearest-city-by-distance
fallback. Both were considered and rejected: "George Town" exists in the
city list only in MALAYSIA, while the trip that names it means the Cayman
Islands, and a nearest-city rule would quietly attribute Miami's Michelin
density to Punta Cana. An unmatched destination is left unmatched, with a
reason, because a visibly missing score is recoverable and a plausible wrong
one is not.

THE COUNTRY IS MATCHED BY NAME, NOT BY destination_country_code. That is a
workaround, not a preference: five trips in the current data (all in the
Eduardo Gomez flight log) carry the ORIGIN airport's country in
destination_country_code -- CDG->LIS records Lisbon, Portugal with cc=FR,
HKG->SFO records San Francisco, United States with cc=HK, and the three
Volaris Mexico legs record Mexico with cc=US. Matching on the code would
send those five to the wrong country or to nothing. See the README TODO.
When that bug is fixed, matching on the code becomes the better choice --
codes do not have the "Czech Republic" vs "Czechia" problem this file's
COUNTRY_ALIASES exists to paper over.

WHAT AN UNMATCHED DESTINATION MEANS. tourist_cities.json is a
population-ranked list of ~3,069 cities, so resort and small-airport
destinations legitimately are not in it -- Punta Cana, Montego Bay,
Sarasota, Kahului, Palm Springs, Kailua-Kona, Belize City, Cozumel,
Providenciales. These are real places this project simply has no city
record (and therefore no UNESCO/Michelin score) for. `match_status` says
`city_not_in_list` for them, distinct from `no_destination_city` for a
country-only trip. Neither is an error and neither should ever be filled
with a 0 -- see the null-vs-zero rule this project applies everywhere else.

Usage:
    python data/scripts/multiple/match_trip_cities.py
"""

import argparse
import csv
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plog_categorize import psychocentric_for_city_id

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
TRAVELERS_PATH = PROCESSED_DIR / "travelers_anon.json"
TOURIST_CITIES_PATH = DATA_DIR / "processed" / "tourist_cities_enhanced.json"
OUT_JSON = PROCESSED_DIR / "trip_city_matches.json"
OUT_CSV = PROCESSED_DIR / "trip_city_matches.csv"

# Trip-side city spellings that mean a city the list spells differently.
# Keyed by (normalised trip spelling, trip's country name) so a name can
# mean different things in different countries. Kept here rather than in
# data/reference/city_aliases.json because that file is specifically the
# Michelin-vs-tourist_cities reconciliation (see build_city_aliases.py);
# these are trip-vs-tourist_cities, a different pairing.
CITY_ALIASES = {
    ("new york city", "United States"): "new york",
    ("washington, d.c.", "United States"): "washington",
    ("duesseldorf", "Germany"): "dusseldorf",
    # The trips name the island; the city list has its city. Denpasar is
    # Bali's airport city (DPS) and where the population is.
    ("bali", "Indonesia"): "denpasar",
}

# The two sides spell these countries differently. Verified by confirming
# the city itself is present under the other spelling -- e.g. Seoul exists
# under "Korea, South" (29 trips), Nassau under "Bahamas, The" (14),
# Prague under "Czechia" (2).
COUNTRY_ALIASES = {
    "South Korea": "Korea, South",
    "Bahamas": "Bahamas, The",
    "Czech Republic": "Czechia",
}


def normalise(name: str) -> str:
    """Casefolded, accent-stripped city name for comparison only -- never
    for display. German umlauts are expanded first (ü -> u, ß -> ss)
    because NFKD alone turns "Düsseldorf" into "dusseldorf" while the trip
    data's "Duesseldorf" stays "duesseldorf", and those must compare
    equal."""
    if not isinstance(name, str):
        return ""
    for src, dst in (("ü", "u"), ("ö", "o"), ("ä", "a"), ("ß", "ss")):
        name = name.replace(src, dst)
    decomposed = unicodedata.normalize("NFKD", name)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


def build_city_index(cities: list[dict]) -> tuple[dict, dict]:
    """(normalised city, country name) -> city record, for the city's own
    spelling and for its city_ascii spelling, as two separate indexes so
    `match_method` can say which one hit.

    Country is the NAME here, not iso2 -- see this module's docstring. The
    one city whose iso2 is a float rather than a string (Namibia, the
    documented `NA` -> NaN pandas bug) is unaffected for the same reason.
    """
    exact: dict[tuple[str, str], dict] = {}
    ascii_: dict[tuple[str, str], dict] = {}
    for city in cities:
        country = city.get("country")
        if not isinstance(country, str):
            continue
        if isinstance(city.get("city"), str):
            exact.setdefault((normalise(city["city"]), country), city)
        if isinstance(city.get("city_ascii"), str):
            ascii_.setdefault((normalise(city["city_ascii"]), country), city)
    return exact, ascii_


def match_destination(city_name: str, country_name: str, exact: dict, ascii_: dict) -> dict:
    """Resolve one destination, returning the match plus how it was made.

    Order matters only for reporting -- the four passes are mutually
    exclusive in practice -- but it is fixed so a regenerated file diffs
    cleanly against the last one.
    """
    if not isinstance(city_name, str) or not city_name:
        return {"match_status": "no_destination_city", "match_method": None, "simplemaps_id": None}

    country = country_name if isinstance(country_name, str) else ""
    key_city = normalise(city_name)

    candidates = [
        (key_city, country, "exact"),
        (CITY_ALIASES.get((key_city, country), key_city), country, "city_alias"),
        (key_city, COUNTRY_ALIASES.get(country, country), "country_alias"),
        (
            CITY_ALIASES.get((key_city, country), key_city),
            COUNTRY_ALIASES.get(country, country),
            "city_and_country_alias",
        ),
    ]

    for candidate_city, candidate_country, method in candidates:
        for index, index_name in ((exact, "exact"), (ascii_, "ascii")):
            hit = index.get((candidate_city, candidate_country))
            if hit is None:
                continue
            # An exact hit found in the ascii index is reported as "ascii";
            # an alias hit keeps the alias name, which is the more
            # interesting fact about how it matched.
            resolved = index_name if method == "exact" else method
            return {
                "match_status": "matched",
                "match_method": resolved,
                "simplemaps_id": str(hit["simplemaps_id"]),
                "matched_city": hit.get("city"),
                "matched_city_ascii": hit.get("city_ascii"),
                "matched_country": hit.get("country"),
                "unesco_score": hit.get("unesco_score"),
                "michelin_score": hit.get("michelin_score"),
                # Plog's psychocentric end, 0-1 (plog_categorize.py). Joined
                # here rather than in a file of its own because it is the same
                # kind of thing as the two above -- a property of the matched
                # CITY -- and this record is already the place the API reads
                # those from.
                "plog_score": psychocentric_for_city_id(hit["simplemaps_id"]),
            }

    return {"match_status": "city_not_in_list", "match_method": None, "simplemaps_id": None}


def compute(travelers: list[dict], cities: list[dict]) -> tuple[list[dict], dict]:
    exact, ascii_ = build_city_index(cities)

    # Layovers are counted here (the trip_count column is "how many trip
    # rows name this destination"), but flagged separately, because the
    # project's rule is that a layover is not a place someone went -- see
    # the layover notes in build_travelers.py / compute_traveler_entropy.py.
    seen: dict[tuple[str, str], dict] = {}
    for traveler in travelers:
        for trip in traveler.get("trips", []):
            city = trip.get("destination_city")
            country = trip.get("destination_country")
            key = (city if isinstance(city, str) else "", country if isinstance(country, str) else "")
            row = seen.setdefault(
                key,
                {
                    "destination_city": city,
                    "destination_country": country,
                    "trips": 0,
                    "layover_trips": 0,
                },
            )
            row["trips"] += 1
            if trip.get("layover"):
                row["layover_trips"] += 1

    rows = []
    for (city, country), row in seen.items():
        rows.append({**row, **match_destination(city, country, exact, ascii_)})

    status_counts = Counter(r["match_status"] for r in rows)
    method_counts = Counter(r["match_method"] for r in rows if r["match_method"])
    matched_trips = sum(r["trips"] for r in rows if r["match_status"] == "matched")

    meta = {
        "source": "travelers_anon.json + tourist_cities_enhanced.json",
        "note": (
            "Keyed by destination, not by trip. simplemaps_id is null for any "
            "destination this project has no city record for -- treat that as "
            "unknown, never as a zero score."
        ),
        "total_destinations": len(rows),
        "total_trips": sum(r["trips"] for r in rows),
        "matched_destinations": status_counts.get("matched", 0),
        "matched_trips": matched_trips,
        "status_counts": dict(status_counts),
        "match_method_counts": dict(method_counts),
    }
    return rows, meta


def main() -> None:
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()

    if not TRAVELERS_PATH.exists():
        raise SystemExit(f"{TRAVELERS_PATH} not found -- run build_travelers_anon.py first.")
    if not TOURIST_CITIES_PATH.exists():
        raise SystemExit(
            f"{TOURIST_CITIES_PATH} not found -- run build_tourist_cities_enhanced.py first."
        )

    with open(TRAVELERS_PATH, encoding="utf-8") as f:
        travelers = json.load(f)["travelers"]
    with open(TOURIST_CITIES_PATH, encoding="utf-8") as f:
        cities = json.load(f)["cities"]

    rows, meta = compute(travelers, cities)
    # Most-visited first, unmatched last -- the unmatched tail is the part
    # worth reading, so it sits together at the bottom rather than scattered.
    rows.sort(key=lambda r: (r["match_status"] != "matched", -r["trips"], r["destination_city"] or ""))

    # The backend looks a trip up by its own (destination_city,
    # destination_country); "city|country" is that key, joined. Emitted
    # alongside the list so the API does no scanning.
    by_destination = {
        f"{r['destination_city']}|{r['destination_country']}": r
        for r in rows
        if r["match_status"] == "matched"
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({**meta, "by_destination": by_destination, "destinations": rows}, f, indent=2, ensure_ascii=False)
    fieldnames = [
        "destination_city", "destination_country", "trips", "layover_trips",
        "match_status", "match_method", "simplemaps_id", "matched_city",
        "matched_city_ascii", "matched_country", "unesco_score", "michelin_score",
        "plog_score",
    ]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"{meta['matched_destinations']} of {meta['total_destinations']} destinations matched "
          f"({meta['matched_trips']} of {meta['total_trips']} trip rows).")
    print(f"By method: {meta['match_method_counts']}")
    print(f"By status: {meta['status_counts']}")
    print()
    unmatched = [r for r in rows if r["match_status"] != "matched"]
    if unmatched:
        print(f"UNMATCHED ({len(unmatched)}) -- no city record, so no UNESCO/Michelin score:")
        for r in unmatched:
            print(f"  {r['trips']:4}  {r['destination_city']} / {r['destination_country']}  [{r['match_status']}]")
        print()
    print(f"Wrote -> {OUT_CSV}")
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
