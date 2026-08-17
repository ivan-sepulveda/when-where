"""
Derived from: data/processed/multiple/travelers_anon.json (built by build_travelers_anon.py)

Computes each traveler's DESTINATION ENTROPY -- how spread out their trips
are across destinations -- and writes
data/processed/multiple/traveler_entropy.csv and .json.

    H = -sum(p_i * ln(p_i))

over p_i = the share of that traveler's trips going to destination i.
Natural log, so the units are nats and the numbers line up with the usual
ln-based formulation.

WHAT COUNTS AS A DESTINATION depends on --by, and the choice is the whole
point of running this more than once. `--by airport` (default) measures how
much a traveler moves between individual airports; `--by region` measures
whether they move between PARTS OF THE WORLD. They answer different
questions, and a traveler can score high on one and zero on the other: 30
trips split across five New York, Boston and Washington airports is high
airport entropy and zero region entropy, because it never leaves Northern
America.

REGION MEANS UN M49 DETAILED REGION -- the intermediate region where the
destination country has one, else its sub-region. 22 possible values. Joined
from data/reference/m49_regions.json on destination_country_code (see
build_m49_regions.py, and data/README.md for why that tier rather than M49's
literal 17-value `subregion`).

**--by region COVERS EVERY TRAVELER, WHICH --by airport CANNOT.** Only the
hand-authored itineraries record an airport, so airport entropy is null for
124 of the 206 travelers. Every trip in the dataset records a destination
country, and every one of those countries resolves to a region, so region
entropy is defined for all 206. That is the main reason this unit exists and
not just a nice property.

WHAT COUNTS AS A DESTINATION for --by airport: the destination AIRPORT. Three cities in this
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

  norm_global    CANONICAL. H / ln(K).

                 For --by airport and --by city, K is every distinct
                 destination observed in the dataset (106 airports,
                 ln = 4.6634). That makes it an absolute scale -- 1.0 would
                 mean "spreads trips evenly across every destination anyone
                 in the dataset visits" -- but K is a property of the DATA,
                 so adding one destination airport rescales every traveler's
                 value. It isn't stable across refreshes the way raw H is.

                 **For --by region, K is fixed at 22** (ln = 3.0910): the
                 count of M49 detailed regions that EXIST, not the 14 this
                 dataset happens to visit. Ivan's call, and it removes the
                 instability above -- the 22 are a closed set, so a region
                 score means the same thing in this data refresh and the
                 next one. It also means the scale is honest about unvisited
                 parts of the world: a traveler who never leaves the Americas
                 shouldn't score near 1.0 just because nobody in the sample
                 went to Micronesia. Highest today is Stan Getz at 0.477
                 across 5 regions.

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

OUTPUT PATH DEPENDS ON --by, so the units don't overwrite each other:
airport keeps the original traveler_entropy.{csv,json} (the backend and its
tests already know that name), and everything else gets a suffix --
traveler_entropy_region.{csv,json}. Before this, --by city silently clobbered
the airport file.

Usage:
    python compute_traveler_entropy.py
    python compute_traveler_entropy.py --by region  # UN M49 detailed region
    python compute_traveler_entropy.py --by city    # destination city instead
"""

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"
TRAVELERS_PATH = PROCESSED_DIR / "travelers_anon.json"
M49_REGIONS_PATH = DATA_DIR / "reference" / "m49_regions.json"

UNITS = ("airport", "city", "region")

# M49 defines exactly 22 detailed regions and that set is closed, so the
# region normalisation divides by a CONSTANT rather than by whatever the
# dataset happens to contain. See the module docstring.
M49_DETAILED_REGIONS = 22


def out_paths(by: str) -> tuple[Path, Path]:
    """airport keeps the original filenames -- the backend and its tests are
    written against them. Every other unit is suffixed, so two units can
    coexist instead of the second silently overwriting the first."""
    stem = "traveler_entropy" if by == "airport" else f"traveler_entropy_{by}"
    return PROCESSED_DIR / f"{stem}.csv", PROCESSED_DIR / f"{stem}.json"


def load_region_by_iso2() -> dict[str, str]:
    """iso2 -> M49 detailed region, from build_m49_regions.py's output.

    Includes that file's `additions` (M49 has no Taiwan entry and this dataset
    visits Taipei) -- without them those trips would drop out of the
    denominator and quietly understate the traveler's spread."""
    if not M49_REGIONS_PATH.exists():
        raise SystemExit(
            f"{M49_REGIONS_PATH} not found -- run build_m49_regions.py first.\n"
            f"--by region needs it to turn a destination country into a region."
        )
    with open(M49_REGIONS_PATH, encoding="utf-8") as f:
        payload = json.load(f)

    records = list(payload.get("countries", {}).values()) + list(payload.get("additions", {}).values())
    # Namibia's iso2 is the string "NA" -- compare against None, not falsy.
    return {
        r["iso2"].upper(): r["detailed_region"]
        for r in records
        if r.get("iso2") is not None and r.get("detailed_region")
    }


def destination_key(trip: dict, by: str, regions: dict[str, str] | None = None) -> str | None:
    """The destination this trip counts toward, or None if the source doesn't
    say. None is a real answer here -- see the module docstring."""
    if by == "airport":
        return trip.get("destination_airport")
    if by == "region":
        # Keyed on the country CODE, not the country name: the source spells
        # the same country several ways and only the code is normalised.
        code = (trip.get("destination_country_code") or "").upper()
        return (regions or {}).get(code)
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


def compute(travelers: list[dict], by: str = "airport",
            regions: dict[str, str] | None = None) -> tuple[list[dict], dict]:
    """Pure function: travelers in, one row per traveler out (plus the
    dataset-level facts the normalisations depend on). Kept separate from I/O
    for testing."""
    global_destinations: set[str] = set()
    for traveler in travelers:
        for trip in traveler["trips"]:
            key = destination_key(trip, by, regions)
            if key:
                global_destinations.add(key)

    observed_global = len(global_destinations)
    # For region, K is the SIZE OF THE STANDARD (22), not what this data
    # happens to contain (14 today) -- so scores don't rescale when a trip to
    # a 15th region is added, and a traveler who never leaves the Americas
    # can't approach 1.0 just because nobody in the sample visited Polynesia.
    k_global = M49_DETAILED_REGIONS if by == "region" else observed_global
    ln_k_global = math.log(k_global) if k_global > 1 else None

    rows = []
    for traveler in travelers:
        counts = Counter(
            key for key in (destination_key(t, by, regions) for t in traveler["trips"]) if key
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
        # What norm_global divides by. For region this is the fixed 22, which
        # is deliberately NOT the same as observed_distinct_destinations.
        "global_distinct_destinations": k_global,
        "global_distinct_destinations_source": (
            "UN M49: every detailed region that exists, whether or not this "
            "dataset visits it" if by == "region" else "observed in this dataset"
        ),
        "observed_distinct_destinations": observed_global,
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
        choices=list(UNITS),
        default="airport",
        help="What counts as a distinct destination. Default: airport.",
    )
    args = parser.parse_args()
    out_csv, out_json = out_paths(args.by)
    regions = load_region_by_iso2() if args.by == "region" else None

    if not TRAVELERS_PATH.exists():
        raise SystemExit(f"{TRAVELERS_PATH} not found -- run build_travelers_anon.py first.")
    with open(TRAVELERS_PATH, encoding="utf-8") as f:
        travelers = json.load(f)["travelers"]

    rows, meta = compute(travelers, by=args.by, regions=regions)
    # Most-varied first; unknowns last rather than sorted as if they were 0.
    rows.sort(key=lambda r: (r["entropy"] is None, -(r["entropy"] or 0), r["name"]))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({**meta, "travelers": rows}, f, indent=2, ensure_ascii=False)
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Destination unit: {meta['destination_unit']}")
    print("Canonical normalisation: norm_global (H / ln K)")
    print(f"K = {meta['global_distinct_destinations']} "
          f"(ln K = {meta['ln_global_distinct_destinations']}) -- "
          f"{meta['global_distinct_destinations_source']}")
    if meta["observed_distinct_destinations"] != meta["global_distinct_destinations"]:
        print(f"  ({meta['observed_distinct_destinations']} of them actually appear in this data)")
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
    print(f"Wrote -> {out_csv}")
    print(f"Wrote -> {out_json}")


if __name__ == "__main__":
    main()
