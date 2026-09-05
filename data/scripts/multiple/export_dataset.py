"""
Export the whole traveler/trip dataset as flat files, for exploring outside this repo.

Derived from: rec_sys_data_prep.py (loaders, joins and the item catalog)

WHAT THIS IS FOR, AND HOW IT DIFFERS FROM rec_sys_data_prep.py
--------------------------------------------------------------
rec_sys_data_prep.py builds what a MODEL needs and drops what a model cannot
use: layover legs, the 28 trips that name a country or region but no city, and
the 8 travelers who have nothing else. That is correct for training and wrong
for exploring -- you cannot notice a pattern in rows that were removed before
you saw them.

So this exports EVERYTHING, and adds a `countable` column marking the rows
rec_sys_data_prep would have kept. Filter it yourself:

    trips[trips.countable]            # what the recommender actually trains on
    trips[~trips.countable]           # what it throws away, and why

Written for a notebook. One wide trips table with the traveler, destination,
geography and score joins already done, so the first thing you do is not four
merges.

WHAT COMES OUT (into data/processed/multiple/export/ by default)
----------------------------------------------------------------
    trips.csv          One row per trip, all of them, ~60 columns. The main table.
    travelers.csv      One row per traveler: demographics, base, tags, both
                       entropies, and the seven taste means.
    destinations.csv   The item catalog: content scores, 12 monthly weather
                       columns, region, popularity.
    interactions.csv   (traveler, destination, visits, confidence) -- long form,
                       ready to pivot into a user-item matrix.
    DATA_DICTIONARY.md Every column, what it means, and where null is meaningful.
    manifest.json      Row counts, source files and their mtimes, generated date.

THE THREE THINGS THAT WILL BITE YOU, ALSO IN THE DICTIONARY
-----------------------------------------------------------
1. **null is not zero.** 41 destinations have no city record, so their UNESCO
   and Michelin scores are blank -- unknown, not absent-of-heritage. 73 cities
   have a real 0.0 (Tokyo among them; its nearest World Heritage site is ~71km
   out). `destination_matched` tells the two apart. `pd.read_csv` gives you NaN
   for the first and 0.0 for the second, which is the behaviour you want -- do
   not `fillna(0)`.
2. **`layover` rows are legs, not visits.** Two hours in Atlanta en route to
   Lisbon. Every aggregate in this project excludes them; `countable` already
   accounts for that.
3. **`weather_score` is resolved against each trip's OWN dates**, not the
   destination's annual average -- a July Reykjavik trip and a January one score
   differently. The destination's twelve monthly columns are in
   destinations.csv if you want the whole curve.

Stdlib only, like everything else in this directory -- no pandas needed to RUN
it, though pandas is the obvious thing to read the output with.

Usage:
    python data/scripts/multiple/export_dataset.py
    python data/scripts/multiple/export_dataset.py --out ~/Desktop/when-where-data
    python data/scripts/multiple/export_dataset.py --format both   # csv + json
    python data/scripts/multiple/export_dataset.py --countable-only
"""

import argparse
import csv
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from rec_sys_data_prep import (
    CONFIDENCE_ALPHA,
    MATCHES_PATH,
    MONTHLY_SCORES_PATH,
    PROCESSED_DIR,
    TAGS_PATH,
    TRAVELERS_PATH,
    TRIPS_PATH,
    _is_countable,
    _trip_weather_score,
    build_destination_catalog,
    build_interactions,
    build_traveler_profiles,
    destination_key,
    load_inputs,
)

OUT_DIR = PROCESSED_DIR / "export"

MONTH_NAMES = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

def tag_kinds_present(travelers):
    """Every classify_trip.py tag kind that actually appears, sorted.

    DISCOVERED, NOT LISTED. This was a hardcoded tuple of three, and adding
    "european_summer" upstream silently produced no `is_european_summer`
    column -- the tag was in `tag_kinds` and missing from the one-hots, which
    is the kind of gap you only notice when a model quietly ignores a feature.
    Reading the kinds off the data means a new tag gets a column for free.

    Not imported from classify_trip.TRIP_TAGS, which would be the other way to
    do it: that module needs pandas, and this one is stdlib-only on purpose."""
    return sorted({tag["kind"]
                   for traveler in travelers
                   for trip in (traveler.get("trips") or [])
                   for tag in (trip.get("tags") or [])
                   if tag.get("kind")})


# ---------------------------------------------------------------------------
# row builders
# ---------------------------------------------------------------------------

def trip_rows(inputs, catalog_by_key):
    """One row per trip, nothing dropped, every join already done.

    Iterates travelers_anon.json's NESTED trips rather than
    trips_enhanced.json's flat list, because only the nested ones sit under a
    traveler_id -- the flat file carries `traveler_name`, which is not a key
    (a traveler is name + nationality). The nested copies also carry
    `layover`, `carrier_code` and the show/episode provenance that the flat
    file drops."""
    regions = inputs["regions_by_iso2"]
    matches = inputs["matches"]

    kinds = tag_kinds_present(inputs["travelers"])
    rows = []
    for traveler in inputs["travelers"]:
        for trip in traveler.get("trips") or []:
            city, country = trip.get("destination_city"), trip.get("destination_country")
            key = destination_key(city, country) if city and country else None
            match = matches.get(key) or {} if key else {}
            iso2 = (trip.get("destination_country_code") or "").upper()
            region = regions.get(iso2) or {}
            catalog = catalog_by_key.get(key) or {}
            tag_kinds = [t.get("kind") for t in (trip.get("tags") or []) if t.get("kind")]
            start = trip.get("start_date") or ""

            plog = match.get("plog_score")
            rows.append({
                # --- identity ---------------------------------------------
                "trip_id": trip.get("trip_id"),
                "traveler_id": traveler["traveler_id"],
                # --- what kind of row this is -----------------------------
                "countable": int(_is_countable(trip)),
                "layover": int(bool(trip.get("layover"))),
                "synthetic": int(bool(trip.get("synthetic"))),
                "destination_kind": trip.get("destination_kind"),
                # --- when -------------------------------------------------
                "start_date": start or None,
                "end_date": trip.get("end_date"),
                "year": int(start[:4]) if len(start) >= 4 and start[:4].isdigit() else None,
                "month": int(start[5:7]) if len(start) >= 7 and start[5:7].isdigit() else None,
                "month_name": (MONTH_NAMES[int(start[5:7]) - 1]
                               if len(start) >= 7 and start[5:7].isdigit() else None),
                "duration_days": trip.get("duration_days"),
                # --- where ------------------------------------------------
                "destination_key": key,
                "destination_city": city,
                "destination_country": country,
                "destination_country_code": trip.get("destination_country_code"),
                "destination_airport": trip.get("destination_airport"),
                "origin_airport": trip.get("origin_airport"),
                "region": region.get("region"),
                "detailed_region": region.get("detailed_region"),
                # --- how --------------------------------------------------
                "carrier_name": trip.get("carrier_name"),
                "flight_class": trip.get("flight_class"),
                # --- what kind of trip ------------------------------------
                "tag_kinds": "|".join(sorted(tag_kinds)) or None,
                **{f"is_{kind}": int(kind in tag_kinds) for kind in kinds},
                # --- destination scores -----------------------------------
                # Blank means UNKNOWN. See the module docstring, point 1.
                "destination_matched": int(bool(match)),
                "unesco_score": match.get("unesco_score"),
                "michelin_score": match.get("michelin_score"),
                "plog_score": plog,
                "allocentric_score": (round(1.0 - plog, 4)
                                      if isinstance(plog, (int, float)) else None),
                # Against this trip's OWN dates, not the annual mean. Takes the
                # DESTINATION'S curve, not the city index -- same call
                # build_traveler_profiles() makes, so the numbers agree.
                "weather_score": _trip_weather_score(trip, catalog.get("weather_by_month")),
                "destination_trips": catalog.get("trips"),
                "destination_travelers": catalog.get("travelers"),
                # The source's original free-text destination, kept because the
                # city/country split was done by hand and this is what it was
                # split FROM. `show` and `episode_title` are deliberately not
                # exported -- they exist on the five travel-show itineraries
                # only, so they are 97% empty and carry nothing a model uses.
                "destination_raw": trip.get("destination_raw"),
            })
    rows.sort(key=lambda r: (r["traveler_id"], r["start_date"] or "", r["trip_id"] or ""))
    return rows


def traveler_rows(profiles, inputs):
    """One row per traveler, with tags and both entropies flattened.

    build_traveler_profiles() already computes the seven taste means the API
    serves, so they are taken from there rather than recomputed -- if the radar
    chart on the site and this export disagreed about what someone likes, one
    of them would be wrong."""
    tags_by_id = inputs["tags_by_id"]
    rows = []
    for profile in profiles:
        tags = tags_by_id.get(profile["traveler_id"], {}).get("tags") or []
        row = dict(profile)
        row["tag_labels"] = "|".join(t.get("label", "") for t in tags) or None
        row["tag_count"] = len(tags)
        row.pop("month_mix", None)          # a dict; expanded into columns below
        for month, share in (profile.get("month_mix") or {}).items():
            row[f"month_share_{month}"] = share
        rows.append(row)
    rows.sort(key=lambda r: (-(r.get("trip_count") or 0), r["traveler_id"]))
    return rows


def destination_rows(catalog):
    """The item catalog, with the 12-month weather curve expanded into columns.

    A nested dict is fine in JSON and useless in a CSV, so `weather_by_month`
    becomes weather_january .. weather_december. Blank where the city has no
    normals -- 61 of them do not, which is a null and not a zero."""
    rows = []
    for dest in catalog:
        row = {k: v for k, v in dest.items() if k not in ("weather_by_month", "airports")}
        row["airports"] = "|".join(dest.get("airports") or []) or None
        # Renamed out of the weather_* namespace. It is a STRING among twelve
        # numbers, and the obvious notebook move --
        # `[c for c in df if c.startswith("weather_")]` -- otherwise picks it up
        # and every arithmetic op on the curve raises. Caught doing exactly that.
        row["best_month"] = row.pop("weather_best_month", None)
        # annual_weather_mean, not weather_mean_annual: the point is that
        # `weather_*` selects the twelve monthly columns and NOTHING else, so
        # the mean has to leave that namespace rather than sort to the front of
        # it. A 13-column "curve" does not raise -- it just quietly returns a
        # mean that counted the mean.
        row["annual_weather_mean"] = row.pop("weather_mean", None)
        curve = dest.get("weather_by_month") or {}
        for month in MONTH_NAMES:
            row[f"weather_{month}"] = curve.get(month)
        rows.append(row)
    rows.sort(key=lambda r: -(r.get("trips") or 0))
    return rows


# ---------------------------------------------------------------------------
# writing
# ---------------------------------------------------------------------------

def _cell(value):
    """CSV cell. None -> empty (which pandas reads as NaN); lists -> pipe-joined."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, tuple)):
        return "|".join(str(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return value


def write_csv(path, rows):
    """Union of every row's keys as the header, in first-seen order.

    Not rows[0].keys(): a row that gained a column would silently lose it, and
    an export that drops a column without failing is the worst kind of bug in a
    file somebody is about to trust."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    columns = list(dict.fromkeys(k for row in rows for k in row))
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _cell(row.get(k)) for k in columns})
    return len(columns)


def write_json(path, rows, key):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"generated": date.today().isoformat(), "count": len(rows), key: rows},
                  f, ensure_ascii=False, indent=1)


DICTIONARY = """# Data dictionary

Generated by `data/scripts/multiple/export_dataset.py`. Read this before
trusting a column.

## The rules that apply to every file

- **Blank means unknown, never zero.** A blank UNESCO score means the
  destination has no city record; a `0.0` means a real city with no World
  Heritage site inside the 50km scoring radius. 41 destinations are the first
  case, 73 cities are the second. `destination_matched` separates them. Do not
  `fillna(0)`.
- **Money has no currency.** The source dataset never recorded one, so
  destinations.csv's `median_*_cost` columns are comparable between
  destinations and meaningless as an absolute. Per-trip costs are not exported.
- **`synthetic` means "not from the Kaggle CSV", not "made up".** The chef and
  flight-log itineraries are real trips on real routes.

## trips.csv -- one row per trip, nothing dropped

Trip-level cost, lodging and transport-type columns are deliberately not here:
the costs carry no currency and the types are near-constant. Per-destination
medians are in destinations.csv if you want them. `traveler_name` is not here
either -- join `traveler_id` to travelers.csv rather than carrying the name on
3,084 rows.

**`trip_id` is one shape everywhere: `PREFIX-YYYY-MM-DD`.** A traveler prefix
plus the departure date, occasionally with a `-2` suffix where somebody flew
twice in a day (13 rows — Eduardo Gomez's and Lord Rymel's real flight logs,
and a few multi-leg show itineraries). All 3,084 are unique.

The prefix is the traveler's initials, numbered where two travelers share them,
ordered by surname: `EW1` Emily Watson, `EW2` Emma Watson, `EW3` Emma Wilson,
`EW4` Emily Wong. 60 of the 124 CSV-sourced travelers fall in a colliding group,
so numbered prefixes are the common case.

**Do not persist a trip id.** The prefix numbering is positional, so adding a
traveler with colliding initials renumbers that group on the next rebuild.

| column | meaning |
|---|---|
| `trip_id`, `traveler_id` | keys. `traveler_id` joins to travelers.csv for the name and everything else about the person |
| `countable` | 1 if rec_sys_data_prep.py would keep this row: not a layover, and has both a city and a country. **Start here.** |
| `layover` | 1 for a leg that was part of a longer journey but not its point |
| `destination_kind` | `city`, `country` or `region`. The last two have no `destination_key` |
| `year`, `month`, `month_name` | parsed from `start_date` for grouping |
| `destination_key` | `"City\\|Country"` -- the item id, joins to destinations.csv |
| `region`, `detailed_region` | UN M49. `detailed_region` is the 22-value tier worth charting |
| `is_*` | one column per classify_trip.py tag kind, as 0/1 — `is_beach_vacation`, `is_ski_trip`, `is_holiday_trip`, `is_european_summer`. Discovered from the data, so a new tag upstream gets a column automatically. Not mutually exclusive |
| `unesco_score`, `michelin_score` | 0-10, of the destination CITY. Blank = no city record |
| `plog_score` / `allocentric_score` | one continuum, two poles: allocentric = 1 - plog. Use one |
| `weather_score` | 0-10, resolved against **this trip's own dates**, not the annual mean |
| `destination_trips`, `destination_travelers` | popularity of the destination, for a baseline |
| `destination_raw` | the source's original free-text destination, before the hand-written city/country split |

## travelers.csv -- one row per traveler

`pref_unesco`, `pref_michelin`, `pref_weather`, `pref_allocentric` are means
over that traveler's own non-layover trips, on 0-1. `pref_beach`, `pref_ski`
and `pref_holiday` are **shares of classifiable trips**, not means -- a
different denominator, because a trip with no airport gets no tags at all and
counting it would read a missing airport as evidence of not liking beaches.

`entropy_norm_global` divides by the observed destination count;
`region_entropy_norm_global` divides by a fixed 22, so it does not rescale when
a new region is visited. `month_share_*` is the traveler's month-of-year mix.

## destinations.csv -- the item catalog

One row per `destination_key`.

`weather_january` .. `weather_december` are the 12-point curve and are the ONLY
`weather_*` columns -- the annual mean is `annual_weather_mean` and the peak is
`best_month`, both deliberately outside that namespace so this selects cleanly:

```python
curve = [f"weather_{m}" for m in
         "january february march april may june july august "
         "september october november december".split()]
d[curve].mean(axis=1)

[c for c in d.columns if c.startswith("weather_")] == curve   # True, by design
```

Blank where the city has no normals (61 of them). `beach_share`, `ski_share` and
`holiday_share` describe the trips taken there, not the place itself.

## interactions.csv -- ready to pivot

`(traveler_id, destination_key, visits, first_visit, last_visit, confidence)`.
`confidence` is Hu/Koren implicit feedback, `1 + {alpha} * ln(1 + visits)` --
the log is what stops one traveler's 201 trips dominating a factorisation.

```python
import pandas as pd
i = pd.read_csv("interactions.csv")
matrix = i.pivot(index="traveler_id", columns="destination_key", values="confidence")
matrix.notna().mean().mean()   # density -- it is about 1.4%
```
"""


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Export the dataset as flat files.")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help=f"output directory (default {OUT_DIR})")
    parser.add_argument("--format", choices=("csv", "json", "both"), default="csv")
    parser.add_argument("--countable-only", action="store_true",
                        help="drop layover and city-less rows from trips.csv")
    args = parser.parse_args()

    inputs = load_inputs()
    catalog = build_destination_catalog(
        inputs["trips"], inputs["matches"], inputs["weather_by_city_id"],
        inputs["regions_by_iso2"])
    catalog_by_key = {d["destination_key"]: d for d in catalog}
    profiles = build_traveler_profiles(
        inputs["travelers"], catalog, inputs["tags_by_id"], inputs["entropy_by_id"],
        inputs["region_entropy_by_id"], inputs["regions_by_iso2"])
    interactions = build_interactions(inputs["travelers"])

    trips = trip_rows(inputs, catalog_by_key)
    dropped = 0
    if args.countable_only:
        before = len(trips)
        trips = [t for t in trips if t["countable"]]
        dropped = before - len(trips)

    tables = {
        "trips": (trips, "trips"),
        "travelers": (traveler_rows(profiles, inputs), "travelers"),
        "destinations": (destination_rows(catalog), "destinations"),
        "interactions": (interactions, "interactions"),
    }

    out = args.out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, (rows, key) in tables.items():
        if args.format in ("csv", "both"):
            n_cols = write_csv(out / f"{name}.csv", rows)
            written.append((f"{name}.csv", len(rows), n_cols))
        if args.format in ("json", "both"):
            write_json(out / f"{name}.json", rows, key)
            written.append((f"{name}.json", len(rows), "-"))

    # .replace(), not .format(): the dictionary holds Python examples, and a
    # brace in one of them made str.format raise KeyError on a code sample.
    (out / "DATA_DICTIONARY.md").write_text(
        DICTIONARY.replace("{alpha}", str(CONFIDENCE_ALPHA)), encoding="utf-8")

    def stamp(path):
        return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") \
            if path.exists() else None

    manifest = {
        "generated": date.today().isoformat(),
        "generated_by": "data/scripts/multiple/export_dataset.py",
        "countable_only": args.countable_only,
        "counts": {name: len(rows) for name, (rows, _) in tables.items()},
        # So a stale export is provable rather than suspected.
        "sources": {p.name: stamp(p) for p in
                    (TRAVELERS_PATH, TRIPS_PATH, TAGS_PATH, MATCHES_PATH, MONTHLY_SCORES_PATH)},
        "notes": {
            "null_is_not_zero": "Blank scores mean unknown. See DATA_DICTIONARY.md.",
            "countable": "1 where rec_sys_data_prep.py would keep the row.",
            "confidence": f"1 + {CONFIDENCE_ALPHA} * ln(1 + visits)",
        },
    }
    with open(out / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print(f"Exported to {out}")
    for name, n_rows, n_cols in written:
        cols = f"{n_cols} cols" if n_cols != "-" else ""
        print(f"  {name:22} {n_rows:6} rows  {cols}")
    print(f"  {'DATA_DICTIONARY.md':22}")
    print(f"  {'manifest.json':22}")

    kinds = Counter(t["destination_kind"] for t in trips)
    print()
    print(f"  {sum(t['countable'] for t in trips)} of {len(trips)} trips are countable"
          + (f" ({dropped} dropped by --countable-only)" if dropped else ""))
    print(f"  trip kinds: " + ", ".join(f"{k}:{v}" for k, v in kinds.most_common()))
    print(f"  {sum(1 for t in trips if t['destination_matched'])} trips carry destination scores; "
          f"{sum(1 for t in trips if t['weather_score'] is not None)} carry a weather score")


if __name__ == "__main__":
    main()
