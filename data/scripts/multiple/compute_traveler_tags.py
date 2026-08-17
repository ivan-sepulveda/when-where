"""
Derived from: data/processed/multiple/travelers_anon.json (built by build_travelers_anon.py)

Assigns TAGS to each traveler -- short, human-readable labels describing a
pattern that is TRUE OF THE DATA, not asserted by whoever authored the
itinerary -- and writes data/processed/multiple/traveler_tags.csv and .json.

Same relationship to travelers_anon.json as compute_traveler_entropy.py: this
reads that file and writes its own, rather than folding a field back into it,
so no build step ever reads its own output.

FIRST AND SO FAR ONLY RULE -- AIRLINE LOYALIST
----------------------------------------------
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

ADDING A SECOND RULE: write a function that takes the traveler dict and
returns a list of Tag dicts, and add it alongside airline_loyalist() in
compute(). Everything downstream -- the CSV column, the API field, the chips
-- is a list of tags and does not know how many rules produced them.

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
# Rules
# --------------------------------------------------------------------------

def carrier_counts(traveler: dict) -> Counter:
    """Trips per airline. Trips with no carrier are absent entirely rather
    than counted under a "None" key -- they are outside the denominator."""
    return Counter(
        trip["carrier_name"] for trip in traveler["trips"] if trip.get("carrier_name")
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
        "share": round(share, 4),
        "trips": top_n,
        "denominator": n,
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
        tags, diagnostics = airline_loyalist(traveler, threshold, min_trips)
        rows.append({
            "traveler_id": traveler["traveler_id"],
            "name": traveler["name"],
            "trip_count": traveler["trip_count"],
            **diagnostics,
            "tags": tags,
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
        },
        "travelers_total": len(travelers),
        "travelers_with_carrier_data": sum(1 for r in rows if r["trips_with_carrier"] > 0),
        "travelers_tagged": sum(1 for r in rows if r["tags"]),
        "tag_counts": dict(sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "near_misses_below_min_trips": sum(1 for r in rows if r["below_min_trips"]),
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
    # The CSV flattens tags to a "; "-joined label list -- it's for reading,
    # not for round-tripping. The JSON is the structured output.
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        fieldnames = [k for k in rows[0] if k != "tags"] + ["tags"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({**{k: v for k, v in row.items() if k != "tags"},
                             "tags": "; ".join(t["label"] for t in row["tags"])})

    rule = meta["rules"]["airline_loyalist"]
    print(f"Rule: >= {rule['threshold']:.0%} of a traveler's trips on one airline, "
          f"min {rule['min_trips']} trips, over {rule['denominator']}.")
    print(f"{meta['travelers_with_carrier_data']} of {meta['travelers_total']} travelers have "
          f"carrier data; {meta['travelers_tagged']} tagged.")
    if meta["near_misses_below_min_trips"]:
        print(f"{meta['near_misses_below_min_trips']} would qualify on share but have "
              f"fewer than {rule['min_trips']} trips.")
    print()
    for label, count in meta["tag_counts"].items():
        print(f"  {label:24} {count:3}")
    print()
    print(f"{'traveler':24} {'trips':>5} {'carriers':>8} {'top share':>9}  tags")
    for r in rows[:10]:
        share = "  --  " if r["top_carrier_share"] is None else f"{r['top_carrier_share']:6.1%}"
        print(f"{r['name'][:23]:24} {r['trips_with_carrier']:5} {r['distinct_carriers']:8} "
              f"{share:>9}  {'; '.join(t['label'] for t in r['tags'])}")
    print(f"  ... {len(rows) - 10} more")
    print()
    print(f"Wrote -> {OUT_CSV}")
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
