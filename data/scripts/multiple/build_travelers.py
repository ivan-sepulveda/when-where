"""
Builds data/processed/multiple/travelers.json from
data/processed/multiple/trips_enhanced.json (see build_trips_enhanced.py):
one entry per traveler, holding every trip that traveler took, which is what
the /rec-sys page renders as a grid of clickable cards.

This script used to read traveler_trips.csv and do its own parsing. It doesn't
any more -- build_trips_enhanced.py owns the CSV and all of the cleaning
(dates, currency strings, "7 days" durations, and the destination city/country
split), and this script does exactly one thing: decide who counts as the same
person and group their trips. The pipeline is now linear, each step with a
single job:

    fetch_traveler_trips.py   Kaggle           -> traveler_trips.csv
    build_trips_enhanced.py   clean + split    -> trips_enhanced.json
    build_travelers.py        group by person  -> travelers.json
    build_travelers_anon.py   author personas  -> travelers_anon.json

IT ALSO INFERS A HOME BASE, for everyone whose base isn't declared outright.
A hand-authored traveler (see build_synthetic_trips.py) can state their own
home, and a stated one always wins -- inference is for travelers whose home is
unknown, and overriding a known one with a guess would be strictly worse. For
everyone else, base_city / base_country are derived from the two things the
source does say: their nationality, and where they went.

    base_country = the country of their nationality.
    base_city    = the first city in that country's BASE_CITIES list that
                   they did NOT visit on any of their trips.

The "did not visit" step is the whole trick. Someone Australian who flew to
Sydney three times is evidently not based in Sydney, so they fall through to
Melbourne; a Spanish traveler whose only domestic trip was to Barcelona falls
through to Madrid. A traveler with no domestic trips at all just gets the
first entry, which is why the ordering of BASE_CITIES matters more than its
length.

This is a guess, and it's labelled as one: base_inference records whether the
city was the country's default ("primary"), a fallback after skipping somewhere
they visited ("avoided_visited"), or unavailable ("unmapped"). It is NOT
research about any real person -- travelers_anon.json later renames these
travelers after real authors, and their actual biographies have nothing to do
with these bases (see build_travelers_anon.py).

GROUPING IS A DECISION, NOT A LOOKUP. There is no traveler ID in the source,
so two trips belong to the same traveler when the name AND nationality both
match (case- and accent-insensitively). Name alone would merge two different
people sharing a common name; adding age would split one traveler across trips
taken in different years, since age is recorded per trip. The rule can still be
wrong in both directions on this data -- it's a small sample dataset with
repeated generic names -- which is why traveler_id is derived from exactly
those two fields and nothing else, so the grouping is legible from the URL
rather than hidden in an opaque hash.

CAVEAT INHERITED FROM THE SOURCE: this is sample/teaching data, not a real
booking log (see fetch_traveler_trips.py). It's here to build the
recommendation UI against, not to support any claim about real travel
behavior.

Output shape:
  {"travelers": [
     {"traveler_id": "john-smith-american",
      "name": "John Smith", "nationality": "American", "gender": "Male",
      "age": 35, "age_range": [35, 37], "trip_count": 3,
      "destinations": ["London, United Kingdom", ...],
      "trips": [ ...every field from trips_enhanced.json except the
                 traveler_* ones, which live on the traveler... ]}]}
Travelers are sorted by trip count descending then name, so the /rec-sys grid
leads with the people who actually have something to look at.

Usage:
    python build_travelers.py
"""

import argparse
import json
import re
import unicodedata
from collections import OrderedDict
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
TRIPS_PATH = PROCESSED_DIR / "trips_enhanced.json"
OUTPUT_PATH = PROCESSED_DIR / "travelers.json"

# Fields that describe the PERSON rather than the trip. They ride along on
# every trip record in trips_enhanced.json (that file is a flat table); here
# they're lifted onto the traveler and removed from each trip, so the same
# fact isn't repeated on every one of their trips.
TRAVELER_FIELDS = ("traveler_name", "traveler_age", "traveler_gender", "traveler_nationality")

# ---------------------------------------------------------------------------
# Home base inference -- see this module's docstring for the rule.
# ---------------------------------------------------------------------------

# The source writes nationalities inconsistently ("Brazil" and "Brazilian",
# "USA" and "American", three spellings of Korean), so everything is normalized
# through this before the lookup below. Deliberately duplicated from
# build_travelers_anon.py rather than shared: this project keeps its data
# scripts self-contained, and the two tables answer different questions (that
# one maps nationality -> author roster, this one -> home country).
NATIONALITY_ALIASES = {
    "usa": "american",
    "us": "american",
    "united states": "american",
    "uk": "british",
    "united kingdom": "british",
    "england": "british",
    "great britain": "british",
    "australia": "australian",
    "brazil": "brazilian",
    "cambodia": "cambodian",
    "canada": "canadian",
    "china": "chinese",
    "france": "french",
    "germany": "german",
    "greece": "greek",
    "hong kong": "hongkonger",
    "hongkong": "hongkonger",
    "india": "indian",
    "indonesia": "indonesian",
    "italy": "italian",
    "japan": "japanese",
    "korea": "korean",
    "south korea": "korean",
    "south korean": "korean",
    "mexico": "mexican",
    "morocco": "moroccan",
    "netherlands": "dutch",
    "holland": "dutch",
    "new zealand": "new zealander",
    "scotland": "scottish",
    "singapore": "singaporean",
    "south africa": "south african",
    "spain": "spanish",
    "taiwan": "taiwanese",
    "thailand": "thai",
    "united arab emirates": "emirati",
    "uae": "emirati",
    "vietnam": "vietnamese",
}

# nationality -> (country name, ISO 3166-1 alpha-2, [candidate home cities]).
#
# The city list is ordered "most plausible place a traveler from here lives,
# first" -- which is usually the capital, but NOT always, and the exceptions
# are the interesting part:
#   * Australia leads with Sydney, not Canberra. Canberra is the capital and
#     almost nobody's answer to "where in Australia are you from" -- so an
#     Australian who keeps flying to Sydney falls through to Melbourne, not to
#     an administrative city nobody lives in for this dataset's purposes.
#   * Canada leads with Toronto over Ottawa, and Brazil with Sao Paulo over
#     Brasilia, for the same reason.
#   * The United States is the deliberate counter-example: Washington, D.C.
#     leads rather than New York, because New York is one of this dataset's
#     most-visited destinations and reading "based in New York" off a trip
#     list that flies to New York would be exactly the inference this script
#     is trying to avoid.
# Lists run 3-5 deep so a traveler who has visited the first choice still has
# somewhere to fall through to. Country names match trips_enhanced.py's
# COUNTRIES spellings, and the ISO2 code is included for the same reason it is
# there: it's the join key the rest of this project uses.
BASE_CITIES = {
    "american": ("United States", "US", ["Washington, D.C.", "Chicago", "Boston", "Seattle", "Denver"]),
    "australian": ("Australia", "AU", ["Sydney", "Melbourne", "Brisbane", "Perth", "Adelaide"]),
    "brazilian": ("Brazil", "BR", ["Sao Paulo", "Rio de Janeiro", "Brasilia", "Belo Horizonte"]),
    "british": ("United Kingdom", "GB", ["London", "Manchester", "Birmingham", "Bristol"]),
    "cambodian": ("Cambodia", "KH", ["Phnom Penh", "Siem Reap", "Battambang"]),
    "canadian": ("Canada", "CA", ["Toronto", "Montreal", "Vancouver", "Ottawa", "Calgary"]),
    "chinese": ("China", "CN", ["Beijing", "Shanghai", "Guangzhou", "Chengdu"]),
    "dutch": ("Netherlands", "NL", ["Amsterdam", "Rotterdam", "The Hague", "Utrecht"]),
    "emirati": ("United Arab Emirates", "AE", ["Dubai", "Abu Dhabi", "Sharjah"]),
    "french": ("France", "FR", ["Paris", "Lyon", "Marseille", "Toulouse"]),
    "german": ("Germany", "DE", ["Berlin", "Munich", "Hamburg", "Frankfurt"]),
    "greek": ("Greece", "GR", ["Athens", "Thessaloniki", "Patras"]),
    # One city, so a Hongkonger who visited Hong Kong falls through to nothing
    # and keeps it anyway -- the alternative (inventing a district) would be
    # worse than a base that's simply the city-state.
    "hongkonger": ("Hong Kong", "HK", ["Hong Kong"]),
    "indian": ("India", "IN", ["Mumbai", "Delhi", "Bengaluru", "Chennai"]),
    "indonesian": ("Indonesia", "ID", ["Jakarta", "Surabaya", "Bandung", "Yogyakarta"]),
    "italian": ("Italy", "IT", ["Rome", "Milan", "Naples", "Turin"]),
    "japanese": ("Japan", "JP", ["Tokyo", "Osaka", "Nagoya", "Fukuoka"]),
    "korean": ("South Korea", "KR", ["Seoul", "Busan", "Incheon", "Daegu"]),
    "mexican": ("Mexico", "MX", ["Mexico City", "Guadalajara", "Monterrey", "Puebla"]),
    "moroccan": ("Morocco", "MA", ["Casablanca", "Rabat", "Marrakech", "Fez"]),
    "new zealander": ("New Zealand", "NZ", ["Auckland", "Wellington", "Christchurch"]),
    "scottish": ("United Kingdom", "GB", ["Edinburgh", "Glasgow", "Aberdeen"]),
    "singaporean": ("Singapore", "SG", ["Singapore"]),
    "south african": ("South Africa", "ZA", ["Johannesburg", "Cape Town", "Durban", "Pretoria"]),
    "spanish": ("Spain", "ES", ["Madrid", "Barcelona", "Valencia", "Seville"]),
    "taiwanese": ("Taiwan", "TW", ["Taipei", "Kaohsiung", "Taichung"]),
    "thai": ("Thailand", "TH", ["Bangkok", "Chiang Mai", "Phuket"]),
    "vietnamese": ("Vietnam", "VN", ["Ho Chi Minh City", "Hanoi", "Da Nang"]),
}


def resolve_base(name: str, nationality: str | None, trips: list[dict], declared_bases: dict) -> dict:
    """A declared base if this traveler has one, otherwise an inferred one.

    Declared wins outright, and is marked base_inference: "declared" so it's
    never confused with a guess. Frank Lloyd Wright is the case this exists
    for: he's American and based in New York City, and infer_base() would put
    him in Washington, D.C. -- the right answer for someone whose home is
    unknown, and the wrong one for someone whose home is the whole point of
    the record."""
    declared = declared_bases.get(name)
    if declared:
        return {
            "base_city": declared.get("base_city"),
            "base_country": declared.get("base_country"),
            "base_country_code": declared.get("base_country_code"),
            "base_inference": "declared",
        }
    return infer_base(nationality, trips)


def normalize_nationality(nationality: str | None) -> str:
    if not nationality:
        return ""
    key = " ".join(str(nationality).strip().lower().split())
    return NATIONALITY_ALIASES.get(key, key)


def infer_base(nationality: str | None, trips: list[dict]) -> dict:
    """{base_city, base_country, base_country_code, base_inference} for one
    traveler -- see this module's docstring for the rule and its limits.

    Matching against visited cities is case- and accent-insensitive on the
    city name alone, not (city, country): every candidate is in the
    traveler's own country anyway, and a "Sydney" in the trip list is Sydney
    Australia in this dataset. All-None with base_inference "unmapped" for a
    nationality BASE_CITIES doesn't cover, rather than a guess -- a wrong base
    is worse than an absent one, since anything downstream would treat it as
    fact."""
    entry = BASE_CITIES.get(normalize_nationality(nationality))
    if entry is None:
        return {
            "base_city": None,
            "base_country": None,
            "base_country_code": None,
            "base_inference": "unmapped",
        }

    country, country_code, candidates = entry

    def key(text: str) -> str:
        stripped = "".join(
            ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
        )
        return " ".join(stripped.lower().split())

    visited = {key(trip["destination_city"]) for trip in trips if trip.get("destination_city")}

    for index, city in enumerate(candidates):
        if key(city) not in visited:
            return {
                "base_city": city,
                "base_country": country,
                "base_country_code": country_code,
                # "primary" means the country's default answer; anything else
                # means this traveler visited the cities ahead of it.
                "base_inference": "primary" if index == 0 else "avoided_visited",
            }

    # Every candidate is somewhere they've been -- possible for a one-city
    # entry like Singapore. Keep the first rather than inventing a new city,
    # and say so.
    return {
        "base_city": candidates[0],
        "base_country": country,
        "base_country_code": country_code,
        "base_inference": "visited_all_candidates",
    }


def identity_key(name: str, nationality: str | None) -> str:
    """The grouping key: accent- and case-insensitive name + nationality. See
    the module docstring for why those two fields and not more or fewer."""

    def normalize(text: str) -> str:
        stripped = "".join(
            ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
        )
        return " ".join(stripped.lower().split())

    return f"{normalize(name)}|{normalize(nationality or '')}"


def slugify(text: str) -> str:
    """URL-safe, lowercase, hyphenated -- "John Smith" -> "john-smith". Used
    to build traveler_id, which is what /rec-sys/travelers/:travelerId routes
    on, so it has to survive a round trip through a URL unchanged."""
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )
    slug = re.sub(r"[^a-z0-9]+", "-", stripped.lower()).strip("-")
    return slug or "traveler"


def format_destination(trip: dict) -> str:
    """"London, United Kingdom" for a city trip, "Japan" for a country-only
    one -- the cleaned destination, not the source's raw string. Used for the
    traveler's `destinations` summary list, where "Sydney", "Sydney, Aus" and
    "Sydney, Australia" should collapse into one entry rather than look like
    three different places."""
    city = trip.get("destination_city")
    country = trip.get("destination_country")
    if city and country:
        return f"{city}, {country}"
    return city or country or trip.get("destination_raw") or ""


def load_trips() -> tuple[list[dict], dict]:
    if not TRIPS_PATH.exists():
        raise FileNotFoundError(
            f"{TRIPS_PATH} not found -- run scripts/multiple/build_trips_enhanced.py first "
            "(which in turn needs fetch_traveler_trips.py's CSV)."
        )
    with open(TRIPS_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    trips = payload.get("trips", [])
    # Hand-authored travelers can state their own home base; see this
    # module's docstring for why a stated base beats an inferred one.
    declared_bases = payload.get("declared_bases", {})
    synthetic = sum(1 for t in trips if t.get("synthetic"))
    print(f"{TRIPS_PATH.name}: {len(trips)} trips ({synthetic} synthetic), {len(declared_bases)} declared base(s)")
    return trips, declared_bases


def group_travelers(trips: list[dict], declared_bases: dict | None = None) -> list[dict]:
    declared_bases = declared_bases or {}
    grouped: "OrderedDict[str, dict]" = OrderedDict()
    skipped = 0

    for trip in trips:
        name = trip.get("traveler_name")
        if not name:
            # build_trips_enhanced.py already drops these, so this is a
            # belt-and-braces check rather than an expected path.
            skipped += 1
            continue

        nationality = trip.get("traveler_nationality")
        key = identity_key(name, nationality)
        traveler = grouped.get(key)
        if traveler is None:
            traveler = {
                # First spelling seen wins for display -- the grouping key is
                # already normalized, so "john smith" and "John Smith" land
                # together and show as whichever appeared first.
                "name": name,
                "nationality": nationality,
                "gender": trip.get("traveler_gender"),
                "ages": [],
                "trips": [],
                # True only if EVERY one of their trips is synthetic. A
                # traveler who somehow had both would not be a hand-authored
                # traveler any more, and shouldn't be labelled as one.
                "synthetic": True,
            }
            grouped[key] = traveler

        # Fill in details a later trip has and an earlier one didn't, rather
        # than overwriting -- a blank gender on trip 1 shouldn't erase the
        # value trip 2 provides.
        traveler["gender"] = traveler["gender"] or trip.get("traveler_gender")
        traveler["nationality"] = traveler["nationality"] or nationality
        traveler["synthetic"] = traveler["synthetic"] and bool(trip.get("synthetic"))
        if trip.get("traveler_age") is not None:
            traveler["ages"].append(trip["traveler_age"])
        traveler["trips"].append({k: v for k, v in trip.items() if k not in TRAVELER_FIELDS})

    if skipped:
        print(f"skipped {skipped} trip(s) with no traveler name")

    travelers: list[dict] = []
    used_ids: set[str] = set()
    for traveler in grouped.values():
        base_id = slugify(f"{traveler['name']} {traveler['nationality'] or ''}")
        traveler_id = base_id
        # Two travelers can only collide here if their names and nationalities
        # differ solely by characters slugify() strips -- rare, but a duplicate
        # id would make one of them unreachable by URL, so disambiguate.
        suffix = 2
        while traveler_id in used_ids:
            traveler_id = f"{base_id}-{suffix}"
            suffix += 1
        used_ids.add(traveler_id)

        ages = sorted(traveler["ages"])
        trips_sorted = sorted(
            traveler["trips"],
            # Undated trips sort last rather than first, so a missing date
            # doesn't push a trip to the top of the list as if it were oldest.
            key=lambda t: (t["start_date"] is None, t["start_date"] or "", format_destination(t)),
        )

        travelers.append(
            {
                "traveler_id": traveler_id,
                "name": traveler["name"],
                "nationality": traveler["nationality"],
                # A declared base if this traveler has one, otherwise
                # inferred -- see infer_base(). Computed from the sorted trip
                # list so it depends only on which cities they visited, not
                # the order they're listed in.
                **resolve_base(traveler["name"], traveler["nationality"], trips_sorted, declared_bases),
                "gender": traveler["gender"],
                # `age` is the most recent one seen (ages are per-trip in the
                # source); `age_range` keeps the spread so a page can show
                # "35-37" where trips span years.
                "age": ages[-1] if ages else None,
                "age_range": [ages[0], ages[-1]] if ages else None,
                "synthetic": traveler["synthetic"],
                "trip_count": len(trips_sorted),
                "destinations": sorted({format_destination(t) for t in trips_sorted}),
                "trips": trips_sorted,
            }
        )

    # Most-travelled first -- the /rec-sys grid leads with the people who
    # actually have something to look at.
    travelers.sort(key=lambda t: (-t["trip_count"], t["name"]))
    return travelers


def main():
    argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    ).parse_args()

    trips, declared_bases = load_trips()
    travelers = group_travelers(trips, declared_bases)

    payload = {
        "source": (
            "data/processed/multiple/trips_enhanced.json (itself built from the Kaggle "
            "traveler-trip dataset -- see build_trips_enhanced.py), grouped by traveler -- "
            "see build_travelers.py and data/README.md"
        ),
        "attribution": "Traveler Trip Data (rkiattisak) via Kaggle -- CC BY 4.0",
        "generated": date.today().isoformat(),
        "note": (
            "Sample/teaching data, not a real booking log. Travelers are grouped by name + "
            "nationality (the source has no traveler ID). Trip fields come through from "
            "trips_enhanced.json unchanged, including the hand-resolved destination_city / "
            "destination_country split; costs carry both a parsed number and the original "
            "string, and there is no currency column, so nothing is summed across trips."
        ),
        "total_travelers": len(travelers),
        "total_trips": sum(t["trip_count"] for t in travelers),
        "travelers": travelers,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    repeat_travelers = [t for t in travelers if t["trip_count"] > 1]
    base_counts: dict[str, int] = {}
    for traveler in travelers:
        base_counts[traveler["base_inference"]] = base_counts.get(traveler["base_inference"], 0) + 1

    print(f"\nWrote {len(travelers)} travelers ({payload['total_trips']} trips) -> {OUTPUT_PATH}")
    print(f"  {len(repeat_travelers)} traveler(s) have more than one trip")
    print(f"  inferred bases: {base_counts}")
    unmapped = sorted({t["nationality"] for t in travelers if t["base_inference"] == "unmapped"})
    if unmapped:
        print(f"  no base for nationality: {unmapped} -- add them to BASE_CITIES and re-run.")
    for traveler in travelers[:5]:
        base = traveler["base_city"] or "?"
        print(
            f"    {traveler['trip_count']:>2} trips  {traveler['name']} ({traveler['nationality']})"
            f" -- based in {base} [{traveler['base_inference']}]"
        )
    print("\nNext: python scripts/multiple/build_travelers_anon.py")


if __name__ == "__main__":
    main()
