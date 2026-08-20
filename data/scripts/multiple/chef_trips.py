"""
Shared machinery for turning a food-and-travel TV series into trip rows.

Used by build_bourdain_trips.py (No Reservations + Parts Unknown, out of
New York) and build_ramsay_trips.py (Uncharted, out of Los Angeles). The
episode tables, the home airports and the traveler live in those scripts;
everything here is the part that doesn't change between chefs:

  * which airport a trip actually departs from, given an ordered list of
    home airports and the candidate airports for a destination
  * the flights-only rule -- a route has to exist in
    airline_routes_enhanced.csv or the episode is excluded
  * the date arithmetic (air date + a fixed number of days)
  * the CSV/JSON shape both shows write

THE CAPITAL RULE (Ivan's). When a source names a country and no city --
an episode simply titled "Norway" or "Vietnam" -- the row records that
country's CAPITAL. Not its busiest airport, not its largest city: the
capital, so the choice is a rule anyone can re-derive rather than a
judgement made per episode. Conan's New Zealand row is Wellington though
Auckland is the gateway; the Netherlands row is Amsterdam, the capital,
rather than The Hague, the seat of government.

Where a source DOES name a place, that always wins over the rule --
Without Borders' Qatar episode is Doha because the article says Al Udeid,
and Parts Unknown's "Southern Italy" is Apulia because the synopsis says
so. The rule only fills a silence.

The capital decides which city the row is ABOUT. Getting there is a
separate question: `airports` may list the capital's airport first and the
country's international gateway after it, and build_rows() below follows
the airport when a later candidate wins, recording the substitution in the
row's notes.

WHY THIS IS SHARED AND THE EPISODES ARE NOT. The episode tables are
research: a title, an air date, and a judgement call about which airport
serves the place the episode is about. That judgement belongs next to
the show it's about. The resolution rules are a policy, and two chefs
disagreeing about how a trip is dated or which airport wins would be a
bug, not a feature.

Requires: data/reference/airports.json (IATA -> name/city/country/coords),
          data/processed/multiple/airline_routes_enhanced.csv (built by
          build_airline_routes_enhanced.py)
"""

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent.parent
REFERENCE_DIR = DATA_DIR / "reference"
PROCESSED_DIR = DATA_DIR / "processed" / "multiple"

AIRPORTS_PATH = REFERENCE_DIR / "airports.json"
ROUTES_PATH = PROCESSED_DIR / "airline_routes_enhanced.csv"

# Exclusion reason codes. An episode carries one of these instead of a
# flight, and every excluded episode keeps it in the output -- "we looked
# and there was no trip here" is a different statement from silence.
GROUND = "ground_trip"          # home turf or driven, no flight involved
COMPILATION = "compilation"     # clip show, not a new journey
AMBIGUOUS = "no_single_destination"  # a region or several countries, no one gateway
NO_NONSTOP = "no_home_nonstop"  # no nonstop from any home airport in the route data

CSV_FIELDS = [
    "trip_id",
    "show",
    "season",
    "episode",
    "episode_code",
    "episode_title",
    "episode_destination",
    "air_date",
    "start_date",
    "end_date",
    "duration_days",
    "traveler_name",
    "destination_city",
    "destination_country",
    "destination_airport",
    "destination_airport_name",
    "destination_lat",
    "destination_lng",
    "origin_airport",
    "origin_alternates",
    "nonstop_airlines",
    "nonstop_airline_count",
    "distance_km",
    "is_domestic",
    "notes",
]


def load_airports():
    """IATA -> airport record, from data/reference/airports.json."""
    with AIRPORTS_PATH.open() as fh:
        payload = json.load(fh)
    return {a["iata"]: a for a in payload["airports"] if a.get("iata")}


def load_home_routes(origins):
    """
    (origin, destination) -> route facts, for the given home airports only.
    airline_routes_enhanced.csv has one row per airline per route, so the
    airlines are collected into a sorted list and the route's distance is
    taken from the first row that carries one.
    """
    routes = defaultdict(lambda: {"airlines": set(), "distance_km": None, "is_domestic": None})
    with ROUTES_PATH.open(newline="") as fh:
        for row in csv.DictReader(fh):
            origin = row["Departure"]
            if origin not in origins:
                continue
            route = routes[(origin, row["Destination"])]
            route["airlines"].add(row["Airline ID"])
            if route["distance_km"] is None and row.get("distance_km"):
                route["distance_km"] = float(row["distance_km"])
            if route["is_domestic"] is None and row.get("is_domestic"):
                route["is_domestic"] = int(row["is_domestic"])
    return {k: {**v, "airlines": sorted(v["airlines"])} for k, v in routes.items()}


def resolve_flight(candidate_airports, routes, origins):
    """
    Walk the episode's candidate destination airports in order and return
    the first one any home airport flies to nonstop, together with the
    winning origin (first in `origins` wins) and the other home airports
    that also serve it. Returns None when nothing is flyable.

    The two orderings do different jobs and the destination one is outer on
    purpose: which airport SERVES the place is a fact about the place, and
    only once that's settled does it matter which of the traveler's home
    airports can get there.
    """
    for destination in candidate_airports:
        serving = [o for o in origins if (o, destination) in routes]
        if not serving:
            continue
        origin, alternates = serving[0], serving[1:]
        return {
            "destination_airport": destination,
            "origin_airport": origin,
            "origin_alternates": alternates,
            **routes[(origin, destination)],
        }
    return None


def build_rows(episodes, origins, traveler_name, trip_days):
    """
    (trips, excluded) for one chef's episode table.

    Each episode is a dict of season / episode / title / air_date / city /
    country / airports, optionally `note`, and optionally `exclude` +
    `exclude_note` when it never was a flight. `show` and `show_code` tag
    which series it came from.
    """
    airports = load_airports()
    routes = load_home_routes(origins)

    trips, excluded = [], []
    trip_id = 0

    for ep in episodes:
        code = f"{ep['show_code']} S{ep['season']}.E{ep['episode']}"
        base = {
            "show": ep["show"],
            "season": ep["season"],
            "episode": ep["episode"],
            "episode_code": code,
            "episode_title": ep["title"],
            "air_date": ep["air_date"],
            "destination_city": ep.get("city"),
            "destination_country": ep.get("country"),
        }

        if ep.get("exclude"):
            excluded.append({**base, "reason": ep["exclude"], "reason_note": ep.get("exclude_note", "")})
            continue

        flight = resolve_flight(ep["airports"], routes, origins)
        if flight is None:
            excluded.append({
                **base,
                "reason": NO_NONSTOP,
                "reason_note": f"no nonstop from {'/'.join(origins)} to "
                               + "/".join(ep["airports"]) + " in airline_routes_enhanced.csv",
            })
            continue

        start = datetime.strptime(ep["air_date"], "%Y-%m-%d").date()
        end = start + timedelta(days=trip_days)
        airport = airports.get(flight["destination_airport"], {})

        notes = []
        if ep.get("note"):
            notes.append(ep["note"])

        # When the episode's first-choice airport has no nonstop and a later
        # candidate wins, the trip is really to that second airport's city --
        # so the destination columns follow the airport, and the episode's
        # own subject stays visible in episode_destination and the note.
        #
        # The airport can also be in a DIFFERENT COUNTRY from the place the
        # episode is about even when it was the first choice -- Chamonix in
        # the French Alps is flown to via Geneva, in Switzerland. Following
        # the episode there would file a Swiss airport under France and
        # break the country-code join, so the country follows the airport in
        # that case too.
        resolved = dict(base)
        substituted = flight["destination_airport"] != ep["airports"][0]
        crosses_border = bool(airport.get("country")) and airport["country"] != ep["country"]
        if substituted or crosses_border:
            if substituted:
                notes.append(
                    f"{ep['airports'][0]} ({ep['city']}) has no nonstop from "
                    f"{'/'.join(origins)}; resolved to {flight['destination_airport']}"
                )
            if crosses_border:
                notes.append(
                    f"{ep['city']}, {ep['country']} is served from "
                    f"{flight['destination_airport']} in {airport['country']}"
                )
            if airport.get("city"):
                resolved["destination_city"] = airport["city"]
                resolved["destination_country"] = airport.get("country", ep["country"])

        trip_id += 1
        trips.append({
            "trip_id": trip_id,
            **resolved,
            "episode_destination": f"{ep['city']}, {ep['country']}",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "duration_days": trip_days,
            "traveler_name": traveler_name,
            "destination_airport": flight["destination_airport"],
            "destination_airport_name": airport.get("name", ""),
            "destination_lat": airport.get("lat"),
            "destination_lng": airport.get("lng"),
            "origin_airport": flight["origin_airport"],
            "origin_alternates": flight["origin_alternates"],
            "nonstop_airlines": flight["airlines"],
            "nonstop_airline_count": len(flight["airlines"]),
            "distance_km": flight["distance_km"],
            "is_domestic": flight["is_domestic"],
            "notes": "; ".join(notes),
        })

    return trips, excluded


def to_csv_row(trip):
    row = {k: trip.get(k) for k in CSV_FIELDS}
    row["origin_alternates"] = "|".join(trip.get("origin_alternates") or [])
    row["nonstop_airlines"] = "|".join(trip.get("nonstop_airlines") or [])
    return row


def write_outputs(csv_path, json_path, trips, excluded, episodes, meta, include_excluded=False):
    """Write both files and return the payload that went into the JSON."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for trip in trips:
            writer.writerow(to_csv_row(trip))
        if include_excluded:
            for ep in excluded:
                writer.writerow(to_csv_row({
                    **ep,
                    "traveler_name": meta["traveler"]["traveler_name"],
                    "notes": f"EXCLUDED ({ep['reason']}): {ep['reason_note']}",
                }))

    shows = []
    for ep in episodes:
        if ep["show"] not in shows:
            shows.append(ep["show"])

    payload = {
        **meta,
        "generated": date.today().isoformat(),
        "counts": {
            "episodes": len(episodes),
            "trips": len(trips),
            "excluded": len(excluded),
            "by_show": {
                show: {
                    "episodes": sum(1 for ep in episodes if ep["show"] == show),
                    "trips": sum(1 for t in trips if t["show"] == show),
                    "excluded": sum(1 for e in excluded if e["show"] == show),
                }
                for show in shows
            },
        },
        "trips": trips,
        "excluded_episodes": excluded,
    }
    with json_path.open("w") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return payload


def print_summary(trips, excluded, episodes, csv_path, json_path):
    print(f"Wrote {len(trips)} trips to {csv_path}")
    print(f"Wrote {len(trips)} trips + {len(excluded)} excluded episodes to {json_path}")

    by_origin = defaultdict(int)
    for trip in trips:
        by_origin[trip["origin_airport"]] += 1
    print("Origins: " + ", ".join(f"{k} {v}" for k, v in sorted(by_origin.items())))

    # airports.json is an OpenFlights snapshot and lags new airport codes
    # (BER, for one), so a route can exist for an airport the reference file
    # has never heard of -- that would silently blank the name and
    # coordinates, so say so instead.
    unknown = [(t["episode_code"], t["destination_airport"])
               for t in trips if not t["destination_airport_name"]]
    if unknown:
        print("\nWARNING -- destination airport missing from airports.json "
              "(no name or coordinates): "
              + ", ".join(f"{code} {iata}" for code, iata in unknown))

    shows = []
    for ep in episodes:
        if ep["show"] not in shows:
            shows.append(ep["show"])
    for show in shows:
        kept = sum(1 for t in trips if t["show"] == show)
        total = sum(1 for ep in episodes if ep["show"] == show)
        print(f"  {show:<16} {kept:>3} trips from {total:>3} episodes")

    print(f"\nExcluded {len(excluded)} episodes:")
    for ep in excluded:
        print(f"  {ep['episode_code']:<12} {ep['episode_title'][:40]:<40} {ep['reason']}")
