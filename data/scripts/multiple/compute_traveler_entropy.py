"""
Derived from: data/processed/multiple/travelers_anon.json (built by build_travelers_anon.py)

Computes each traveler's DESTINATION ENTROPY -- how spread out their trips
are across destinations -- and writes
data/processed/multiple/traveler_entropy.csv and .json.

    H = -sum(p_i * ln(p_i))

over p_i = the share of that traveler's trips going to destination i.
Natural log, so the units are nats and the numbers line up with the usual
ln-based formulation.

WHAT COUNTS AS A DESTINATION: the destination AIRPORT. Three cities in this
dataset are served by two airports each (New York EWR/JFK, Washington
DCA/IAD, Tokyo HND/NRT), so airport is strictly finer than city -- but no
single traveler ever uses two airports for the same city, so every
traveler's entropy is identical either way today. Airport is the unit
because the normalisation denominator is a count of airports; if a traveler
ever splits a city across airports, that's the moment the two diverge and
this choice starts to matter.

H = 0 MEANS TWO DIFFERENT THINGS AND THE OUTPUT KEEPS THEM APART. Chet
Baker's 0 is a real finding: 53 trips, every one to JFK. A Kaggle traveler's
0 is an artifact: they have one recorded trip, and one observation can only
ever produce 0. Both are honestly "zero entropy", but only the first says
anything about the person. `trip_count` and `n_destinations` are in the
output so the two are always separable, and `entropy_is_informative` flags
it directly (False when trip_count < 2).

TRAVELERS WITH NO AIRPORT DATA GET null, NOT 0. Only the hand-authored
itineraries record airports; the 124 Kaggle-sourced travelers record a
destination string and nothing else. Writing 0 for them would assert
"never varies their destination" where the truth is "we don't know", and
that lie would propagate into any average taken over the column.

THREE NORMALISATIONS ARE EMITTED. **norm_global is the canonical one**
(Ivan's call) -- the other two are kept for comparison and should not be
used as "the" number without saying so.

  norm_global    CANONICAL. H / ln(K) where K is every distinct destination
                 airport in the whole dataset (106, ln = 4.6634). An
                 absolute scale: 1.0 would mean "spreads trips evenly across
                 every destination anyone in the dataset visits". Nobody
                 comes close -- the highest is Stan Getz at 0.65 -- so
                 expect the numbers to live in the bottom two thirds of the
                 range. Also note K is a property of the whole dataset, so
                 adding a destination airport rescales EVERY traveler's
                 value; it isn't stable across data refreshes the way the
                 raw entropy is.

  norm_observed  H / ln(k) where k is that traveler's OWN distinct
                 destination count -- the textbook normalisation. **Undefined
                 for 29 of the 82 travelers**, who have k = 1 and so divide
                 by ln(1) = 0. Emitted as null there rather than faked as 0
                 or 1, since 0/0 genuinely has no answer.

  norm_capacity  H / ln(min(n_trips, K)). Corrects for opportunity: a
                 traveler with 4 trips cannot exceed ln(4) no matter how
                 varied they are, so comparing their raw H against a
                 53-trip traveler's understates them. 1.0 means "never
                 repeated a destination". Also null when n_trips < 2.

Usage:
    python compute_traveler_entropy.py
    python compute_traveler_entropy.py --by city   # destination city instead
"""

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
TRAVELERS_PATH = PROCESSED_DIR / "travelers_anon.json"
OUT_CSV = PROCESSED_DIR / "traveler_entropy.csv"
OUT_JSON = PROCESSED_DIR / "traveler_entropy.json"


def destination_key(trip: dict, by: str) -> str | None:
    """The destination this trip counts toward, or None if the source doesn't
    say. None is a real answer here -- see the module docstring."""
    if by == "airport":
        return trip.get("destination_airport")
    city, country = trip.get("destination_city"), trip.get("destination_country")
    if city and country:
        return f"{city}, {country}"
    return city or country or None


def shannon_entropy(counts: Counter) -> float:
    """-sum(p ln p) in nats. Returns exactly 0.0 for a single category rather
    than the -0.0 that falls out of the arithmetic (p=1 -> 1*ln(1) -> -0.0),
    which sorts and prints badly."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = -sum((c / total) * math.log(c / total) for c in counts.values() if c > 0)
    return 0.0 if h == 0 else h


def compute(travelers: list[dict], by: str = "airport") -> tuple[list[dict], dict]:
    """Pure function: travelers in, one row per traveler out (plus the
    dataset-level facts the normalisations depend on). Kept separate from I/O
    for testing."""
    global_destinations: set[str] = set()
    for traveler in travelers:
        for trip in traveler["trips"]:
            key = destination_key(trip, by)
            if key:
                global_destinations.add(key)

    k_global = len(global_destinations)
    ln_k_global = math.log(k_global) if k_global > 1 else None

    rows = []
    for traveler in travelers:
        counts = Counter(
            key for key in (destination_key(t, by) for t in traveler["trips"]) if key
        )
        n_trips = sum(counts.values())
        k = len(counts)

        if n_trips == 0:
            # No destination recorded at all -- every entropy field is
            # unknown, and must not be written as 0.
            rows.append({
                "traveler_id": traveler["traveler_id"],
                "name": traveler["name"],
                "trip_count": traveler["trip_count"],
                "trips_with_destination": 0,
                "n_destinations": 0,
                "top_destination": None,
                "top_destination_share": None,
                "entropy": None,
                "entropy_is_informative": False,
                "norm_global": None,
                "norm_observed": None,
                "norm_capacity": None,
            })
            continue

        h = shannon_entropy(counts)
        top, top_n = counts.most_common(1)[0]

        # ln(1) = 0, so both of these are 0/0 for a traveler with a single
        # destination or a single trip. null, not a made-up number.
        ln_k = math.log(k) if k > 1 else None
        capacity = min(n_trips, k_global)
        ln_capacity = math.log(capacity) if capacity > 1 else None

        rows.append({
            "traveler_id": traveler["traveler_id"],
            "name": traveler["name"],
            "trip_count": traveler["trip_count"],
            "trips_with_destination": n_trips,
            "n_destinations": k,
            "top_destination": top,
            "top_destination_share": round(top_n / n_trips, 4),
            "entropy": round(h, 4),
            # A single trip can only ever give 0. True zero entropy needs at
            # least two observations to mean anything.
            "entropy_is_informative": n_trips >= 2,
            "norm_global": round(h / ln_k_global, 4) if ln_k_global else None,
            "norm_observed": round(h / ln_k, 4) if ln_k else None,
            "norm_capacity": round(h / ln_capacity, 4) if ln_capacity else None,
        })

    meta = {
        "destination_unit": by,
        "log_base": "natural (nats)",
        "global_distinct_destinations": k_global,
        "ln_global_distinct_destinations": round(ln_k_global, 4) if ln_k_global else None,
        "travelers_total": len(travelers),
        "travelers_with_destination_data": sum(1 for r in rows if r["trips_with_destination"] > 0),
        "travelers_with_informative_entropy": sum(1 for r in rows if r["entropy_is_informative"]),
    }
    return rows, meta


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--by",
        choices=["airport", "city"],
        default="airport",
        help="What counts as a distinct destination. Default: airport.",
    )
    args = parser.parse_args()

    if not TRAVELERS_PATH.exists():
        raise SystemExit(f"{TRAVELERS_PATH} not found -- run build_travelers_anon.py first.")
    with open(TRAVELERS_PATH, encoding="utf-8") as f:
        travelers = json.load(f)["travelers"]

    rows, meta = compute(travelers, by=args.by)
    # Most-varied first; unknowns last rather than sorted as if they were 0.
    rows.sort(key=lambda r: (r["entropy"] is None, -(r["entropy"] or 0), r["name"]))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({**meta, "travelers": rows}, f, indent=2, ensure_ascii=False)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Destination unit: {meta['destination_unit']}")
    print("Canonical normalisation: norm_global (H / ln K)")
    print(f"Global distinct destinations K = {meta['global_distinct_destinations']} "
          f"(ln K = {meta['ln_global_distinct_destinations']})")
    print(f"{meta['travelers_with_destination_data']} of {meta['travelers_total']} travelers "
          f"have destination data; {meta['travelers_with_informative_entropy']} have 2+ trips "
          f"so their entropy means something.")
    print()
    print(f"{'traveler':24} {'trips':>5} {'dests':>5} {'H':>7} {'global':>7} {'observed':>8} {'capacity':>8}")
    def fmt(v):
        return "  --  " if v is None else f"{v:6.3f}"
    for r in rows[:10]:
        print(f"{r['name'][:23]:24} {r['trips_with_destination']:5} {r['n_destinations']:5} "
              f"{fmt(r['entropy'])} {fmt(r['norm_global'])} {fmt(r['norm_observed'])} {fmt(r['norm_capacity'])}")
    print(f"  ... {len(rows) - 10} more")
    print()
    print(f"Wrote -> {OUT_CSV}")
    print(f"Wrote -> {OUT_JSON}")


if __name__ == "__main__":
    main()
