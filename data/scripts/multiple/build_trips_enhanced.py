"""
Builds data/processed/multiple/trips_enhanced.json from
data/processed/multiple/traveler_trips.csv (see fetch_traveler_trips.py): one
record per trip, cleaned, with the source's single free-text `Destination`
column split into `destination_city` and `destination_country`.

This is the canonical cleaned trip record for this project. Everything
downstream reads it rather than the CSV: build_travelers.py groups these trips
by traveler, build_travelers_anon.py renames those travelers, and the API
serves the result. The CSV stays exactly as fetched (see
fetch_traveler_trips.py), so a cleaning mistake is fixable by re-running this
script alone.

It also MERGES data/processed/multiple/synthetic_trips.json plus the
per-traveler files listed in SYNTHETIC_SOURCES -- the travel-show hosts
(bourdain_traveler.json, ramsay_traveler.json, conan_traveler.json) and
one real person's flight log under a pseudonym (gomez_traveler.json) --
whenever those files exist. They supply the deliberate travel patterns the
Kaggle rows can't (113 of its 124 people have exactly one trip). Every
trip here carries a `synthetic` flag so the origins can always be told
apart, and those ones additionally carry the airline and airport codes
their itinerary was built from. See build_synthetic_trips.py.

NOTE the `synthetic` flag means "not from the Kaggle CSV", not "made up":
the flight log's legs are real. See build_gomez_trips.py.

THE DESTINATION SPLIT IS THE POINT, and it can't be done with str.split(",").
The source's 60 distinct destination strings are inconsistent in five separate
ways, all of which DESTINATIONS below resolves by hand:

  1. City only, country implied -- "Tokyo", "Paris", "Sydney". Resolved from
     the city: Tokyo -> Japan.
  2. Abbreviated or truncated countries -- "Sydney, Aus", "Sydney, AUS",
     "Bangkok, Thai", "Cape Town, SA", "London, UK", "New York, USA".
  3. Country only, no city at all -- "Japan", "Brazil", "Thailand". These get
     destination_city: null rather than a guessed capital: the source says a
     country, so the record says a country.
  4. A sub-national region standing in for a country -- "Honolulu, Hawaii"
     (a US state), "Edinburgh, Scotland" (a UK constituent country). The
     country column has to hold the sovereign state, or joining on it later
     silently fails.
  5. Destinations that aren't cities -- "Bali", "Santorini", "Hawaii",
     "Phuket" are islands, provinces or states. They're kept in
     destination_city (they ARE the destination as this dataset means it) and
     flagged `destination_kind: "region"`, so a later join against a city
     database knows not to expect a match.

`destination_kind` records which of those a row was: "city", "region" or
"country". `destination_raw` keeps the original string verbatim, so every
inference above stays auditable against what the source actually said.

`destination_country_code` (ISO 3166-1 alpha-2) is emitted alongside the
country name because that's the join key every other dataset in this project
is keyed by -- weather, visas, UNESCO, Michelin, prices. Country NAMES are for
display; this is what makes "how good would this trip have been" answerable
later without a name-matching step.

COVERAGE IS ENFORCED, not best-effort: every non-empty destination string in
the CSV must resolve through DESTINATIONS or this script fails with the list
of what didn't. A silently-unmapped destination would become a null country
that quietly drops out of any downstream join, which is exactly the failure
mode that's hardest to notice later. Adding a new destination means adding a
line to DESTINATIONS -- deliberately manual, since the whole value of this
file is that a human decided what "Bangkok, Thai" means.

Usage:
    python build_trips_enhanced.py
    python build_trips_enhanced.py --report   # print the destination mapping and exit
"""

import argparse
import csv
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the destination table is the substance of this script.
# ---------------------------------------------------------------------------

# Source header candidates per output field, matched case-insensitively.
# Same defensive resolver as build_travelers.py's, which this file takes over
# the parsing duties from -- see that script's COLUMN_CANDIDATES comment.
COLUMN_CANDIDATES = {
    "trip_id": ("Trip ID", "TripID", "trip_id", "id"),
    "destination": ("Destination", "destination"),
    "start_date": ("Start date", "Start Date", "start_date"),
    "end_date": ("End date", "End Date", "end_date"),
    "duration": ("Duration (days)", "Duration", "duration_days", "duration"),
    "name": ("Traveler name", "Traveler Name", "traveler_name", "Name"),
    "age": ("Traveler age", "Traveler Age", "traveler_age", "Age"),
    "gender": ("Traveler gender", "Traveler Gender", "traveler_gender", "Gender"),
    "nationality": ("Traveler nationality", "Traveler Nationality", "traveler_nationality", "Nationality"),
    "accommodation_type": ("Accommodation type", "Accommodation Type", "accommodation_type"),
    "accommodation_cost": ("Accommodation cost", "Accommodation Cost", "accommodation_cost"),
    "transportation_type": ("Transportation type", "Transportation Type", "transportation_type"),
    "transportation_cost": ("Transportation cost", "Transportation Cost", "transportation_cost"),
}

REQUIRED_FIELDS = ("name", "destination")

# Canonical country name -> ISO 3166-1 alpha-2. Names here are the plain
# English ones a reader expects ("South Korea", "United States"), NOT this
# project's World Bank-derived country_name values ("Korea, South") -- the
# code is what joins to those, so the name is free to be the readable one.
COUNTRIES = {
    "Australia": "AU",
    "Brazil": "BR",
    "Cambodia": "KH",
    "Canada": "CA",
    "Egypt": "EG",
    "France": "FR",
    "Germany": "DE",
    "Greece": "GR",
    "Indonesia": "ID",
    "Italy": "IT",
    "Japan": "JP",
    "Mexico": "MX",
    "Morocco": "MA",
    "Netherlands": "NL",
    "New Zealand": "NZ",
    "South Africa": "ZA",
    "South Korea": "KR",
    "Spain": "ES",
    "Thailand": "TH",
    "United Arab Emirates": "AE",
    "United Kingdom": "GB",
    "United States": "US",
}

# Every distinct destination string in the source, lowercased, mapped by hand
# to (city or None, canonical country, kind). Written out in full rather than
# derived from a rule, because these ARE the judgment calls -- see this
# module's docstring for the five patterns being resolved.
#
# kind:
#   "city"    -- destination_city is a city proper
#   "region"  -- it's an island/state/province used as a destination (Bali,
#                Hawaii, Santorini, Phuket); kept in destination_city because
#                that's what the traveler went to, flagged so a later
#                city-database join knows not to expect a hit
#   "country" -- the source named no city at all; destination_city is null,
#                NOT a guessed capital
DESTINATIONS = {
    # --- city, country spelled out correctly -------------------------------
    "amsterdam, netherlands": ("Amsterdam", "Netherlands", "city"),
    "athens, greece": ("Athens", "Greece", "city"),
    "auckland, new zealand": ("Auckland", "New Zealand", "city"),
    "bali, indonesia": ("Bali", "Indonesia", "region"),
    "bangkok, thailand": ("Bangkok", "Thailand", "city"),
    "barcelona, spain": ("Barcelona", "Spain", "city"),
    "berlin, germany": ("Berlin", "Germany", "city"),
    "cancun, mexico": ("Cancun", "Mexico", "city"),
    "cape town, south africa": ("Cape Town", "South Africa", "city"),
    "dubai, united arab emirates": ("Dubai", "United Arab Emirates", "city"),
    "marrakech, morocco": ("Marrakech", "Morocco", "city"),
    "paris, france": ("Paris", "France", "city"),
    "phuket, thailand": ("Phuket", "Thailand", "region"),
    "rio de janeiro, brazil": ("Rio de Janeiro", "Brazil", "city"),
    "rome, italy": ("Rome", "Italy", "city"),
    "seoul, south korea": ("Seoul", "South Korea", "city"),
    "sydney, australia": ("Sydney", "Australia", "city"),
    "tokyo, japan": ("Tokyo", "Japan", "city"),
    "vancouver, canada": ("Vancouver", "Canada", "city"),

    # --- city, country abbreviated or truncated ----------------------------
    "bangkok, thai": ("Bangkok", "Thailand", "city"),
    "phuket, thai": ("Phuket", "Thailand", "region"),
    "cape town, sa": ("Cape Town", "South Africa", "city"),
    "sydney, aus": ("Sydney", "Australia", "city"),
    "london, uk": ("London", "United Kingdom", "city"),
    "los angeles, usa": ("Los Angeles", "United States", "city"),
    "new york, usa": ("New York", "United States", "city"),
    # Canonicalized to "New York" so it groups with the "New York" and
    # "New York, USA" rows rather than sitting apart as a third spelling.
    "new york city, usa": ("New York", "United States", "city"),

    # --- city, sub-national region in the country slot ---------------------
    # Hawaii is a US state and Scotland a UK constituent country. Both have to
    # resolve to the sovereign state or every downstream join on country
    # silently misses them.
    "honolulu, hawaii": ("Honolulu", "United States", "city"),
    "edinburgh, scotland": ("Edinburgh", "United Kingdom", "city"),

    # --- city only, country inferred ---------------------------------------
    "amsterdam": ("Amsterdam", "Netherlands", "city"),
    "bangkok": ("Bangkok", "Thailand", "city"),
    "barcelona": ("Barcelona", "Spain", "city"),
    "cape town": ("Cape Town", "South Africa", "city"),
    "dubai": ("Dubai", "United Arab Emirates", "city"),
    "london": ("London", "United Kingdom", "city"),
    "new york": ("New York", "United States", "city"),
    "paris": ("Paris", "France", "city"),
    "phnom penh": ("Phnom Penh", "Cambodia", "city"),
    "rio de janeiro": ("Rio de Janeiro", "Brazil", "city"),
    "rome": ("Rome", "Italy", "city"),
    "seoul": ("Seoul", "South Korea", "city"),
    "sydney": ("Sydney", "Australia", "city"),
    "tokyo": ("Tokyo", "Japan", "city"),

    # --- region only, country inferred -------------------------------------
    "bali": ("Bali", "Indonesia", "region"),
    "hawaii": ("Hawaii", "United States", "region"),
    "phuket": ("Phuket", "Thailand", "region"),
    "santorini": ("Santorini", "Greece", "region"),

    # --- country only, no city named ---------------------------------------
    "australia": (None, "Australia", "country"),
    "brazil": (None, "Brazil", "country"),
    "canada": (None, "Canada", "country"),
    "egypt": (None, "Egypt", "country"),
    "france": (None, "France", "country"),
    "greece": (None, "Greece", "country"),
    "italy": (None, "Italy", "country"),
    "japan": (None, "Japan", "country"),
    "mexico": (None, "Mexico", "country"),
    "spain": (None, "Spain", "country"),
    "thailand": (None, "Thailand", "country"),
}

# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
TRIPS_CSV_PATH = PROCESSED_DIR / "traveler_trips.csv"
SYNTHETIC_PATH = PROCESSED_DIR / "synthetic_trips.json"
BOURDAIN_PATH = PROCESSED_DIR / "bourdain_traveler.json"
RAMSAY_PATH = PROCESSED_DIR / "ramsay_traveler.json"
CONAN_PATH = PROCESSED_DIR / "conan_traveler.json"
GOMEZ_PATH = PROCESSED_DIR / "gomez_traveler.json"
OUTPUT_PATH = PROCESSED_DIR / "trips_enhanced.json"

# Every file that contributes fabricated trips in trips_enhanced.json's own
# record shape. Each is optional and merged the same way; add a path here
# when a new generator starts producing travelers.
SYNTHETIC_SOURCES = (SYNTHETIC_PATH, BOURDAIN_PATH, RAMSAY_PATH, CONAN_PATH, GOMEZ_PATH)


def resolve_columns(columns) -> dict[str, str]:
    """Output field -> the real header in this CSV. Raises only for
    REQUIRED_FIELDS; a missing optional column just leaves that field null on
    every trip, which still produces a usable file."""
    normalized = {str(c).strip().casefold(): str(c) for c in columns}

    resolved: dict[str, str] = {}
    missing: list[str] = []
    for field, candidates in COLUMN_CANDIDATES.items():
        for candidate in candidates:
            actual = normalized.get(candidate.casefold())
            if actual is not None:
                resolved[field] = actual
                break
        else:
            missing.append(field)

    print(f"resolved columns: {resolved}")
    if missing:
        print(f"NO MATCH for: {missing} (left blank -- add the real header to COLUMN_CANDIDATES)")

    required_missing = [f for f in REQUIRED_FIELDS if f not in resolved]
    if required_missing:
        raise KeyError(
            f"Required field(s) {required_missing} matched no column. Headers present: "
            f"{list(columns)} -- add the right ones to COLUMN_CANDIDATES and re-run."
        )
    return resolved


def clean_text(value) -> str | None:
    """Trimmed string, or None for anything blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_money(value) -> float | None:
    """"$1,200" / "1200 USD" / "1,200" -> 1200.0, None when there's no number.

    Currency-BLIND on purpose: this source has no currency column, and it
    really does mix formats ("800 USD" and "1200" both appear). The original
    string is kept alongside as *_raw so the UI can show "£900" as "£900"
    rather than an unlabeled 900, and nothing downstream sums these across
    trips."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^\d.\-]", "", text.replace(",", ""))
    if not cleaned or cleaned in ("-", ".", "-."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_int(value) -> int | None:
    """First integer in the string: "7 days" -> 7, "7.0" -> 7, "" -> None.
    Used for both duration and age, which have the same shape of noise."""
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else None


def parse_date(value) -> str | None:
    """"5/1/2023" or "2023-05-01" -> "2023-05-01", None if neither parses.

    Month-first for the slash form, matching this source's US-style dates.
    Hand-rolled rather than pandas, so this whole pipeline stays
    standard-library only -- and the raw string is kept alongside, so a
    misread (a D/M/YYYY source would be wrong for days 1-12) stays visible.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None

    iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso:
        year, month, day = (int(g) for g in iso.groups())
    else:
        slash = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
        if not slash:
            return None
        month, day, year = (int(g) for g in slash.groups())
        if year < 100:
            year += 2000

    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None  # e.g. 2/30 -- a real date string that isn't a real date


def split_destination(raw: str | None) -> tuple[str | None, str | None, str | None, str | None]:
    """"Sydney, Aus" -> ("Sydney", "Australia", "AU", "city").

    Pure table lookup against DESTINATIONS -- no comma-splitting fallback on
    purpose. A fallback would let "Bangkok, Thai" through as country="Thai",
    which is worse than failing: it looks resolved, joins to nothing, and
    nobody notices. Returns all-None for a blank destination; anything
    non-blank and unmapped is caught by the caller and reported."""
    text = clean_text(raw)
    if text is None:
        return None, None, None, None

    entry = DESTINATIONS.get(text.casefold())
    if entry is None:
        return None, None, None, None

    city, country, kind = entry
    return city, country, COUNTRIES[country], kind


def load_rows() -> tuple[list[dict], dict]:
    if not TRIPS_CSV_PATH.exists():
        raise FileNotFoundError(
            f"{TRIPS_CSV_PATH} not found -- run scripts/multiple/fetch_traveler_trips.py first."
        )

    with open(TRIPS_CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames or []

    print(f"{TRIPS_CSV_PATH.name}: {len(rows)} rows, {len(columns)} columns")
    return rows, resolve_columns(columns)


def build_trips() -> tuple[list[dict], dict]:
    rows, resolved = load_rows()

    def cell(row, field):
        column = resolved.get(field)
        return row.get(column) if column is not None else None

    trips: list[dict] = []
    skipped = 0
    unmapped: Counter = Counter()

    for row in rows:
        name = clean_text(cell(row, "name"))
        destination_raw = clean_text(cell(row, "destination"))
        if not name or not destination_raw:
            skipped += 1
            continue

        city, country, country_code, kind = split_destination(destination_raw)
        if country is None:
            unmapped[destination_raw] += 1
            continue

        trips.append(
            {
                "trip_id": clean_text(cell(row, "trip_id")),
                "destination_raw": destination_raw,
                "destination_city": city,
                "destination_country": country,
                "destination_country_code": country_code,
                "destination_kind": kind,
                "start_date": parse_date(cell(row, "start_date")),
                "start_date_raw": clean_text(cell(row, "start_date")),
                "end_date": parse_date(cell(row, "end_date")),
                "end_date_raw": clean_text(cell(row, "end_date")),
                "duration_days": parse_int(cell(row, "duration")),
                "duration_raw": clean_text(cell(row, "duration")),
                "accommodation_type": clean_text(cell(row, "accommodation_type")),
                "accommodation_cost": parse_money(cell(row, "accommodation_cost")),
                "accommodation_cost_raw": clean_text(cell(row, "accommodation_cost")),
                "transportation_type": clean_text(cell(row, "transportation_type")),
                "transportation_cost": parse_money(cell(row, "transportation_cost")),
                "transportation_cost_raw": clean_text(cell(row, "transportation_cost")),
                # Traveler fields ride along on every trip: this file is the
                # canonical trip record, and build_travelers.py needs exactly
                # these to group by. Keeping them here means nothing
                # downstream has to re-read the CSV.
                "traveler_name": name,
                "traveler_age": parse_int(cell(row, "age")),
                "traveler_gender": clean_text(cell(row, "gender")),
                "traveler_nationality": clean_text(cell(row, "nationality")),
                # Present on every trip, not just the synthetic ones, so the
                # merged file is homogeneous -- a consumer never has to check
                # whether a key exists, only what it says.
                "synthetic": False,
                "carrier_name": None,
                "origin_airport": None,
                "destination_airport": None,
                # This source records one destination per trip with no notion
                # of a connecting leg, so it's never a layover -- see
                # chef_traveler.py's build_trips() for where a real one can be
                # True.
                "layover": False,
            }
        )

    if unmapped:
        listing = "\n".join(f"    {count:>3}x  {dest!r}" for dest, count in sorted(unmapped.items()))
        raise SystemExit(
            f"\n{len(unmapped)} destination string(s) aren't in DESTINATIONS:\n{listing}\n\n"
            "Add each one (with the city, canonical country and kind you want it to mean) to "
            "DESTINATIONS in this script and re-run. This is deliberately fatal -- an unmapped "
            "destination would become a null country that quietly drops out of every downstream join."
        )

    stats = {
        "rows_in_csv": len(rows),
        "skipped_rows": skipped,
        "trips": len(trips),
    }
    return trips, stats


def load_synthetic_trips() -> tuple[list[dict], dict]:
    """(trips, declared_bases) from every generator in SYNTHETIC_SOURCES --
    build_synthetic_trips.py's 82 authored travelers, plus one each from
    the travel-show builders (Bourdain, Ramsay, Conan) -- or ([], {}) if
    none has been run.
    Optional by design: the Kaggle half of this pipeline has to work on its
    own in a fresh checkout, and a missing synthetic file means "no
    hand-authored travelers", not an error.

    declared_bases is passed straight through to trips_enhanced.json for
    build_travelers.py, which prefers a declared home base over its own
    nationality-based guess."""
    trips: list[dict] = []
    bases: dict = {}

    for path in SYNTHETIC_SOURCES:
        if not path.exists():
            print(f"{path.name} not found -- nothing merged from it.")
            continue

        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

        found = payload.get("trips", [])
        names = sorted({t.get("traveler_name") for t in found if t.get("traveler_name")})
        print(f"{path.name}: {len(found)} trips from {len(names)} hand-authored traveler(s): {names}")
        trips.extend(found)
        bases.update(payload.get("declared_bases", {}))

    return trips, bases


def print_report() -> None:
    """Every destination string in the CSV and what it resolves to, sorted by
    frequency -- the fastest way to eyeball whether the table above is saying
    what you meant."""
    rows, resolved = load_rows()
    column = resolved["destination"]
    counts = Counter(clean_text(row.get(column)) or "(blank)" for row in rows)

    print(f"\n{len(counts)} distinct destination strings:\n")
    for raw, count in counts.most_common():
        if raw == "(blank)":
            print(f"  {count:>3}x  (blank)  ->  skipped")
            continue
        city, country, code, kind = split_destination(raw)
        arrow = f"{city or '--'} | {country} ({code}) [{kind}]" if country else "UNMAPPED"
        print(f"  {count:>3}x  {raw:<30} ->  {arrow}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--report", action="store_true", help="Print how every destination string resolves, then exit."
    )
    args = parser.parse_args()

    if args.report:
        print_report()
        return

    trips, stats = build_trips()

    synthetic_trips, declared_bases = load_synthetic_trips()
    if synthetic_trips:
        # Appended, then the whole file is sorted by traveler and date below,
        # so synthetic trips aren't segregated at the end of the file.
        trips.extend(synthetic_trips)
        trips.sort(key=lambda t: (t.get("traveler_name") or "", t.get("start_date") or ""))

    by_kind = Counter(t["destination_kind"] for t in trips)
    by_country = Counter(t["destination_country"] for t in trips)
    inferred_country = sum(1 for t in trips if "," not in t["destination_raw"] and t["destination_kind"] != "country")

    payload = {
        "source": (
            "data/processed/multiple/traveler_trips.csv (Kaggle rkiattisak/traveler-trip-data), "
            "cleaned and with Destination split into city/country by hand -- see "
            "build_trips_enhanced.py and data/README.md"
        ),
        "attribution": "Traveler Trip Data (rkiattisak) via Kaggle -- CC BY 4.0",
        "generated": date.today().isoformat(),
        "note": (
            "destination_city/destination_country are resolved from a hand-written table, not by "
            "splitting on a comma: the source abbreviates countries ('Sydney, Aus'), omits them "
            "('Tokyo'), names a region instead ('Honolulu, Hawaii') and sometimes gives only a "
            "country. destination_kind says which case a row was; destination_raw keeps the "
            "original string. Costs are currency-blind numbers plus the original string -- the "
            "source has no currency column, so nothing here should be summed across trips."
        ),
        "rows_in_csv": stats["rows_in_csv"],
        "skipped_rows": stats["skipped_rows"],
        "trips_from_csv": stats["trips"],
        "trips_synthetic": len(synthetic_trips),
        "declared_bases": declared_bases,
        "total_trips": len(trips),
        "destinations_with_country_inferred": inferred_country,
        "trips_by_destination_kind": dict(by_kind),
        "trips": trips,
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    print(f"\nWrote {len(trips)} trips ({stats['trips']} from the CSV + {len(synthetic_trips)} synthetic) -> {OUTPUT_PATH}")
    print(f"  skipped {stats['skipped_rows']} row(s) with no traveler name or no destination")
    print(f"  by kind: {dict(by_kind)}")
    print(f"  {inferred_country} trip(s) had their country inferred from a city-only destination")
    print(f"  {len(by_country)} distinct countries: {', '.join(f'{c} ({n})' for c, n in by_country.most_common())}")
    print("\nNext: python scripts/multiple/build_travelers.py")


if __name__ == "__main__":
    main()
