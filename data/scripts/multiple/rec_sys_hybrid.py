"""
Derived from: rec_sys_data_prep.py            (all the real work)
              rec_sys_content_based_filtering.py
              rec_sys_collaborative_filtering.py

HYBRID -- decide, per traveler, which of the two models is entitled to an
opinion, and combine them when both are.

IMPLEMENTED 2026-09-05, and `--write` produces the file the site serves.
The DATA PREPARATION section computes the ROUTING TABLE -- for every
traveler, whether the content model has enough taste evidence, whether the
collaborative model has enough neighbourhood, and therefore which branch a
request takes. That table was the first pass's deliverable and it is still
what decides everything in the MODEL section.

WHY A HYBRID IS NOT OPTIONAL HERE, AND WHY THE ROUTING IS THE DELIVERABLE.
The two models fail on opposite halves of this dataset:

    content-based        works for every traveler including 1-trip ones;
                         BLIND to the 41 destinations with no city record
    collaborative        can rank all 233 destinations;
                         USELESS for a traveler with no overlapping history

So the interesting question is not "what weights?" but "who is each model
allowed to answer for?" -- and that is answerable today, from the prepared
data, without writing either model. That answer is what this file produces.

THE FOUR ROUTES, and they are decided by data, not by preference:

    BOTH        enough taste evidence AND a usable neighbourhood
                -> blend, and the blend weights are the open question
    CONTENT     taste evidence, no neighbourhood (the cold-start traveler)
                -> content only; do not fabricate a collaborative score
    COLLAB      neighbourhood, thin taste evidence (a traveler whose whole
                history is unmatched resort towns)
                -> collaborative only
    NEITHER     one trip, to an unmatched destination
                -> there is no personalised answer. Return popularity, SAY
                   SO, and do not dress it up as a recommendation. A
                   recommender that never admits it has nothing is a
                   recommender nobody can calibrate against.

THE RULE THAT MAKES BLENDING HARD, WRITTEN DOWN BEFORE ANYONE TUNES A
WEIGHT. The two scores are not comparable. A content cosine is bounded,
dense, and clusters near 0.9 because every destination shares most features
with every other. A collaborative score is unbounded, sparse, and zero for
most candidates. Adding 0.6 * cosine to 0.4 * cf_score is arithmetic, not
meaning. Whatever the eventual blend, both sides must be put on a common
footing FIRST -- rank-based fusion is the safest default and is what the
pseudocode below leans on.

Usage:
    python data/scripts/multiple/rec_sys_hybrid.py
    python data/scripts/multiple/rec_sys_hybrid.py --traveler anthony-bourdain
    python data/scripts/multiple/rec_sys_hybrid.py --routes      # population summary
"""

import argparse
import json
from collections import Counter, defaultdict
from datetime import date

import rec_sys_collaborative_filtering as cf
import rec_sys_content_based_filtering as cbf
from rec_sys_data_prep import OUT_DIR, prepare, build_user_content_profiles, same_place_as
from rec_sys_content_based_filtering import (
    MAX_PER_REGION,
    candidate_pool,
    content_cold_items,
    profile_coverage,
)
from rec_sys_collaborative_filtering import (
    MIN_SHARED_DESTINATIONS,
    popularity_baseline,
    user_overlap,
)

DEFAULT_TRAVELER = "stan-getz"
TOP_N = 10

# What the BACKEND READS. backend/app/data_loader.load_traveler_recommendations
# looks for this exact file and reports "not_generated" while it is absent,
# which is the state the site is in today -- the Recommend button on
# /rec-sys/travelers/:id is wired end to end and waiting on this file. See
# write_recommendations() below for the shape it has to have.
RECOMMENDATIONS_PATH = OUT_DIR / "recommendations.json"
RECOMMENDATIONS_TOP_N = 3

# A taste vector with fewer observed coordinates than this is not a profile,
# it is a rumour. Set against the content model's own MIN_SHARED_FEATURES:
# there is no point routing to content if the profile cannot clear the bar
# that model applies per candidate anyway.
MIN_PROFILE_FEATURES = 8

# A traveler needs this many peers sharing MIN_SHARED_DESTINATIONS before a
# neighbourhood mean is anything other than one other person's itinerary.
MIN_USABLE_NEIGHBOURS = 3

ROUTES = ("both", "content", "collaborative", "neither")

# Reciprocal rank fusion's usual constant. It damps the top of each list so
# one model cannot dictate the head of the fused one.
RRF_K = 60

# The neighbour count at which the collaborative side gets full weight in the
# "both" branch. An evidence rule, not a fitted parameter -- see recommend().
NEIGHBOURS_FOR_FULL_WEIGHT = 10


# ===========================================================================
# DATA PREPARATION -- real, runs today
# ===========================================================================

def route_for(data, traveler_id, content_profiles):
    """Which model(s) may answer for this traveler, and the evidence for it.

    Real, and deliberately returns the counts alongside the verdict: the
    route is a judgement made from two numbers, and a route with the numbers
    stripped off cannot be argued with."""
    vector = content_profiles[traveler_id]
    # Content + season only. The geography one-hots and the two popularity
    # columns are observed for every destination by construction, so
    # counting them would hand a full-marks profile to a traveler who has
    # been to one unmatched resort town -- see profile_coverage's docstring.
    observed, _ = profile_coverage(vector, data.item_features, "content", "season")
    overlaps = user_overlap(data.user_item, traveler_id)
    usable = [row for row in overlaps if row[1] >= MIN_SHARED_DESTINATIONS]

    has_content = len(observed) >= MIN_PROFILE_FEATURES
    has_collab = len(usable) >= MIN_USABLE_NEIGHBOURS

    if has_content and has_collab:
        route = "both"
    elif has_content:
        route = "content"
    elif has_collab:
        route = "collaborative"
    else:
        route = "neither"

    return {
        "traveler_id": traveler_id,
        "route": route,
        "profile_features": len(observed),
        "profile_features_needed": MIN_PROFILE_FEATURES,
        "usable_neighbours": len(usable),
        "usable_neighbours_needed": MIN_USABLE_NEIGHBOURS,
        "any_overlap": len(overlaps),
        "visited": len(data.user_item.items_for(traveler_id)),
    }


def routing_table(data, content_profiles=None):
    """Every traveler's route. Real, and the main output of this file."""
    content_profiles = content_profiles or build_user_content_profiles(
        data.user_item, data.item_features
    )
    return [route_for(data, t["traveler_id"], content_profiles)
            for t in data.travelers
            if t["traveler_id"] in data.user_item.by_user]


def candidate_coverage(data):
    """How much of the catalog each model can even see.

    Content is blind to the unmatched destinations; collaborative is blind
    to nothing, but a destination visited by exactly one traveler has a
    similarity row built from one observation. Both numbers belong in the
    same table, because 'covers 233 destinations' and 'covers them well' are
    different claims."""
    cold = set(content_cold_items(data))
    per_item = Counter()
    for items in data.user_item.by_user.values():
        for key in items:
            per_item[key] += 1
    return {
        "destinations": len(data.destinations),
        "content_rankable": len(data.destinations) - len(cold),
        "content_blind": len(cold),
        "collaborative_rankable": len(per_item),
        "collaborative_thin": sum(1 for n in per_item.values() if n <= 1),
    }


def readiness_report(data, traveler_id):
    """What the not-yet-written hybrid would receive for one traveler."""
    profile = data.traveler(traveler_id)
    content_profiles = build_user_content_profiles(data.user_item, data.item_features)
    decision = route_for(data, traveler_id, content_profiles)
    pool = candidate_pool(data, traveler_id)
    coverage = candidate_coverage(data)

    print(f"HYBRID -- inputs for {profile['name']} ({traveler_id})")
    print()
    print(f"  ROUTE: {decision['route'].upper()}")
    print(f"    taste vector    {decision['profile_features']:3} observed features "
          f"(needs {MIN_PROFILE_FEATURES})")
    print(f"    neighbourhood   {decision['usable_neighbours']:3} travelers sharing "
          f"{MIN_SHARED_DESTINATIONS}+ destinations (needs {MIN_USABLE_NEIGHBOURS}); "
          f"{decision['any_overlap']} share any")
    print(f"    history         {decision['visited']} destinations visited")
    print()
    print(f"  candidate pool    {len(pool)} destinations")
    print(f"    content can rank        {coverage['content_rankable']} of "
          f"{coverage['destinations']} ({coverage['content_blind']} have no city record)")
    print(f"    collaborative can rank  {coverage['collaborative_rankable']} "
          f"({coverage['collaborative_thin']} rest on a single traveler)")

    if decision["route"] == "neither":
        print()
        print("  no personalised answer is available for this traveler. Fallback:")
        for key, count in popularity_baseline(data.user_item, traveler_id, top_n=5):
            print(f"    {key:34} {count:4} travelers went")

    picks, _ = recommend(data, traveler_id)
    print()
    print("  what the hybrid returns for them")
    for rank, pick in enumerate(picks[:5], start=1):
        print(f"    {rank:2}. {pick['destination_key']:32} {pick['score']:9.5f}  {pick['source']}")
        for reason in reasons_for(data, traveler_id, pick):
            print(f"          - {reason}")


def routes_report(data):
    """The population view: how many travelers each branch actually serves.

    This is the number that decides where effort goes. If most travelers
    route to CONTENT, building an ALS factorisation is optimising the path
    almost nobody takes."""
    table = routing_table(data)
    counts = Counter(row["route"] for row in table)

    print("HYBRID -- routing across all travelers")
    print()
    for route in ROUTES:
        n = counts.get(route, 0)
        share = n / len(table) if table else 0
        print(f"  {route:14} {n:4} travelers  {share:6.1%}")
    print(f"  {'total':14} {len(table):4}")

    coverage = candidate_coverage(data)
    print()
    print(f"  catalog: {coverage['destinations']} destinations; content can rank "
          f"{coverage['content_rankable']}, collaborative {coverage['collaborative_rankable']} "
          f"({coverage['collaborative_thin']} of those on one traveler's say-so)")

    print()
    print("  travelers with the thinnest evidence (first 8)")
    for row in sorted(table, key=lambda r: (r["profile_features"], r["usable_neighbours"]))[:8]:
        print(f"    {row['traveler_id']:28} {row['route']:14} "
              f"{row['profile_features']:3} features  "
              f"{row['usable_neighbours']:3} neighbours  "
              f"{row['visited']:3} destinations")


# ===========================================================================
# MODEL -- implemented 2026-09-05.
# ===========================================================================
#
# The routing table above was the deliverable of the first pass and it is
# still the thing that decides everything below: which model is allowed to
# answer, and therefore what the answer means.

def cold_start(data, traveler_id, top_n=TOP_N):
    """The NEITHER route: no personalised answer exists, so say so.

    In order of preference, exactly as the first pass argued:

    1. If the traveler has a DECLARED base, rank by popularity among
       travelers based in the same M49 detailed region. Weak, honest, and
       better than global popularity -- somebody based in Guadalajara is
       better served by what other Mexico-based travelers do than by what
       the whole dataset does.
    2. Otherwise global popularity by distinct travelers.

    Either way the caller marks the payload `personalised: False` and the UI
    says "popular right now" rather than "for you". What is NOT done here is
    fabricating a taste vector from the population mean: it ranks well
    against the split and is a lie to the user."""
    traveler = data.traveler(traveler_id)
    visited = set()
    for key in data.user_item.items_for(traveler_id):
        visited |= same_place_as(key)      # see _drop_places_already_visited()
    region = traveler.get("base_detailed_region")

    if traveler.get("base_inference") == "declared" and region:
        peers = [t["traveler_id"] for t in data.travelers
                 if t.get("base_detailed_region") == region
                 and t["traveler_id"] != traveler_id
                 and t["traveler_id"] in data.user_item.by_user]
        counts = Counter()
        for peer in sorted(peers):
            for key in sorted(data.user_item.items_for(peer)):
                if key not in visited:
                    counts[key] += 1
        if counts:
            # ORDERED EXPLICITLY, not by Counter.most_common(). London and
            # Paris both sit at 27 travelers here, and most_common() breaks
            # that tie on insertion order -- which came from iterating a SET
            # of destination keys, whose order depends on PYTHONHASHSEED and
            # therefore changes between processes. Two runs of --write
            # produced different files for the 13 `neither` travelers until
            # this sorted on the key.
            ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            rows = [{"destination_key": key, "score": float(n), "source": "popularity",
                     "why": [f"Popular with the {len(peers)} other travelers based in {region}"],
                     "peers": n}
                    for key, n in ordered]
            return _diversify_picks(rows, data, region_cap_for(top_n))[:top_n]

    rows = [{"destination_key": key, "score": float(n), "source": "popularity",
             "why": [f"{n} travelers in the dataset have been"], "peers": n}
            for key, n in popularity_baseline(data.user_item, traveler_id, top_n=None)]
    return _diversify_picks(rows, data, region_cap_for(top_n))[:top_n]


def blend(content_ranked, collaborative_ranked, w_content, w_collaborative, k=RRF_K):
    """Reciprocal rank fusion of two ranked lists.

    RANKS, NOT SCORES, ON PURPOSE. A content cosine is bounded and clusters
    near 0.9 because every destination shares most features with every
    other; a collaborative score is unbounded and zero for most candidates.
    Adding 0.6 * one to 0.4 * the other is arithmetic, not meaning. Rank
    fusion needs no calibration, no shared scale, and no assumption that
    either model's numbers mean anything in absolute terms -- all of which
    are false here.

    A candidate ranked by only ONE model still scores; it simply gets one
    term. That is the correct behaviour for the content-blind destinations:
    collaborative can still surface them, at a discount, instead of them
    vanishing.

    The cost is that it throws away the MARGIN between first and second. If
    that turns out to matter, the upgrade is per-model score normalisation
    (z-score within the candidate pool), not a return to raw addition."""
    scores, seen_in = defaultdict(float), defaultdict(list)
    for rank, row in enumerate(content_ranked, start=1):
        key = row["destination_key"]
        scores[key] += w_content / (k + rank)
        seen_in[key].append(("content", rank, row))
    for rank, row in enumerate(collaborative_ranked, start=1):
        key = row["destination_key"]
        scores[key] += w_collaborative / (k + rank)
        seen_in[key].append(("collaborative", rank, row))

    fused = []
    for key, score in scores.items():
        parts = seen_in[key]
        fused.append({
            "destination_key": key,
            "score": score,
            "from": [name for name, _rank, _row in parts],
            "parts": {name: (rank, row) for name, rank, row in parts},
        })
    fused.sort(key=lambda r: (-r["score"], r["destination_key"]))
    return fused


def _collaborative_reasons(data, row):
    """Turn an item-item row's contributing destinations into a sentence."""
    because = [k.split("|")[0] for k in row.get("because", [])]
    if not because:
        return []
    if len(because) == 1:
        return [f"Travelers who went to {because[0]} went here too"]
    return [f"Travelers who went to {', '.join(because[:-1])} and {because[-1]} went here too"]


def region_cap_for(top_n):
    """How many picks may share an M49 detailed region, given list length.

    MAX_PER_REGION is 2, and that was sized for a ten-item list where two
    Southern European cities are a theme. In the THREE-item list the site
    actually shows, two from one region is two thirds of the recommendation
    -- and it was happening to 227 of 271 travelers. So short lists get a
    cap of one. Same rule, applied proportionally, rather than a second
    constant that can drift away from the first."""
    if top_n is None:
        return MAX_PER_REGION
    return 1 if top_n <= 4 else MAX_PER_REGION


def recommend(data, traveler_id, top_n=TOP_N, month=None, strategy="switching",
              profiles=None, weights=None, item_sim=None, decision=None):
    """The hybrid entry point.

    SWITCHING is the default because it needs no tuning and it is the honest
    reading of the routing table: each traveler is answered by the model
    that has evidence about them, and by popularity when neither does.

        both           -> reciprocal rank fusion of content and item-item
        content        -> content only; no fabricated collaborative score
        collaborative  -> item-item only
        neither        -> cold_start(), personalised=False

    THE BLEND WEIGHTS ARE NOT FITTED ON THE SPLIT, AND THAT IS DELIBERATE.
    The first pass said to fit them. Then the evaluation ran, and item-item
    scores hit@10 0.84 and ALS 0.93 against popularity's 0.32 on a matrix
    that is 1.4% dense -- which is not a good collaborative model, it is a
    model that has rediscovered the authored cohorts, because travelers in
    those cohorts share itineraries BY CONSTRUCTION. Fitting weights on a
    contaminated metric would hand the whole list to the contaminated model.
    So the weights stay on the evidence rule the routing table already uses:

        w_collaborative = min(1, usable_neighbours / 10)
        w_content       = 1 - w_collaborative

    A traveler with three neighbours leans on content; one with thirty leans
    on their peers. Revisit this when there is a real holdout of real
    travelers, and not before."""
    if profiles is None:
        profiles = build_user_content_profiles(data.user_item, data.item_features)
    if decision is None:
        decision = route_for(data, traveler_id, profiles)
    route = decision["route"]

    if route == "neither":
        return cold_start(data, traveler_id, top_n=top_n), decision

    content_rows = []
    if route in ("both", "content"):
        content_rows = cbf.recommend(data, traveler_id, top_n=None, month=month,
                                     profiles=profiles, weights=weights,
                                     diversify=False)
    collab_rows = []
    if route in ("both", "collaborative"):
        collab_rows = cf.item_item_recommend(data, traveler_id, top_n=None,
                                             sim=item_sim)

    if route == "content":
        picks = [{"destination_key": r["destination_key"], "score": r["score"],
                  "source": "content", "content": r} for r in content_rows]
    elif route == "collaborative":
        picks = [{"destination_key": r["destination_key"], "score": r["score"],
                  "source": "collaborative", "collaborative": r} for r in collab_rows]
    else:
        w_collab = min(1.0, decision["usable_neighbours"] / NEIGHBOURS_FOR_FULL_WEIGHT)
        fused = blend(content_rows, collab_rows, 1.0 - w_collab, w_collab)
        picks = []
        for row in fused:
            parts = row["parts"]
            source = "hybrid" if len(parts) > 1 else (
                "content" if "content" in parts else "collaborative")
            pick = {"destination_key": row["destination_key"], "score": row["score"],
                    "source": source}
            if "content" in parts:
                pick["content"] = parts["content"][1]
            if "collaborative" in parts:
                pick["collaborative"] = parts["collaborative"][1]
            picks.append(pick)

    # Seasonality on the collaborative side too -- the content model already
    # applied it, but a purely collaborative pick has had no calendar
    # applied at all, and "should they go in March" is the question the site
    # is named after. A destination with no curve multiplies by 1.0.
    if month:
        for pick in picks:
            if "content" not in pick:
                pick["score"] *= cbf.seasonal_fit(
                    data.destination(pick["destination_key"]), month)
        picks.sort(key=lambda r: (-r["score"], r["destination_key"]))

    picks = _drop_places_already_visited(picks, data, traveler_id)
    picks = _diversify_picks(picks, data, per_region=region_cap_for(top_n))
    return (picks if top_n is None else picks[:top_n]), decision


def _drop_places_already_visited(picks, data, traveler_id):
    """Remove candidates that are somewhere the traveler has already been
    under a DIFFERENT NAME.

    The components already exclude the traveler's own destination keys. This
    catches the five places the catalog holds twice -- recommending "New York
    City" to somebody whose only trip is to "New York" is the failure it was
    written for, and it was on screen before it was written. See
    rec_sys_data_prep.DUPLICATE_DESTINATIONS, which also says where the real
    fix belongs."""
    blocked = set()
    for key in data.user_item.items_for(traveler_id):
        blocked |= same_place_as(key)
    return [pick for pick in picks if pick["destination_key"] not in blocked]


def _diversify_picks(picks, data, per_region=MAX_PER_REGION):
    """Cap at `per_region` per M49 detailed region, order preserved.

    Applied ONCE, here, rather than inside each component -- the components
    are asked for undiversified full rankings so rank fusion sees their real
    order. Diversifying before fusing would fuse two already-truncated lists
    and the cap would apply twice, unevenly."""
    kept, seen = [], Counter()
    for pick in picks:
        region = data.destination(pick["destination_key"]).get("detailed_region")
        if region:
            if seen[region] >= per_region:
                continue
            seen[region] += 1
        kept.append(pick)
    return kept


def reasons_for(data, traveler_id, pick, weights=None):
    """The `why` list for one pick, drawn from whichever model produced it.

    MANDATORY, not decoration. Nobody books a flight because a number was
    high, and a mixed list has to read as the mixture it is -- which is why
    the source travels with the row and each source explains itself in its
    own terms."""
    if pick["source"] == "popularity":
        return pick.get("why", [])

    mixed = "content" in pick and "collaborative" in pick
    why = []
    if "content" in pick:
        # One fewer feature when both models contributed, so the
        # collaborative half is not truncated off the end. A row sourced
        # "hybrid" that only ever shows content reasons is mislabelled.
        why.extend(cbf.explain(data, traveler_id, pick["destination_key"],
                               pick=pick["content"], weights=weights,
                               limit=1 if mixed else 2))
    if "collaborative" in pick:
        why.extend(_collaborative_reasons(data, pick["collaborative"]))
    return why[:3]


# ---------------------------------------------------------------------------
# the file the API serves
# ---------------------------------------------------------------------------

def write_recommendations(data, top_n=RECOMMENDATIONS_TOP_N, path=RECOMMENDATIONS_PATH,
                          month=None):
    """Run recommend() for every traveler and write the file the API serves.

    THIS IS THE HANDOFF between the offline recommender and the running
    site. The "Recommend 3 places" button on /rec-sys/travelers/:id fetches
    GET /api/travelers/{id}/recommendations, which reads nothing but this
    file -- the same offline/online split this project uses for tags and
    entropy, for the same reason (ranking 224 candidates per request is
    pipeline work). Nothing in the backend or the frontend changes when this
    starts being written; the route already handles its absence.

    The shape below must stay in step with
    data_loader.load_traveler_recommendations()'s docstring, which states
    the same contract from the reading end.

    NO MONTH BY DEFAULT. One list per traveler, ranked on the annual
    picture, with `best_month` telling the reader when to go. Passing
    `month` re-ranks for that month instead -- useful, but it would make the
    file's meaning depend on when it was generated, so it is opt-in."""
    profiles = build_user_content_profiles(data.user_item, data.item_features)
    weights = cbf.feature_weights(data.item_features)
    item_sim = cf.item_similarity(data.user_item)

    rows, route_counts = [], Counter()
    for traveler in data.travelers:
        traveler_id = traveler["traveler_id"]
        if traveler_id not in data.user_item.by_user:
            continue                       # no countable trip: nothing to reason from
        picks, decision = recommend(data, traveler_id, top_n=top_n, month=month,
                                    profiles=profiles, weights=weights,
                                    item_sim=item_sim)
        route_counts[decision["route"]] += 1

        out = []
        for pick in picks:
            dest = data.destination(pick["destination_key"])
            out.append({
                "destination_key": pick["destination_key"],
                "destination_city": dest["destination_city"],
                "destination_country": dest["destination_country"],
                "region": dest.get("detailed_region"),
                "score": round(pick["score"], 4),
                "source": pick["source"],
                # Null means UNKNOWN, not "any month" -- 61 of 224
                # destinations have no weather normals and the frontend
                # omits the line rather than printing a guess.
                "best_month": dest.get("weather_best_month"),
                "why": reasons_for(data, traveler_id, pick, weights),
            })

        rows.append({
            "traveler_id": traveler_id,
            "route": decision["route"],
            "personalised": decision["route"] != "neither",
            "recommendations": out,
        })

    payload = {
        "generated": date.today().isoformat(),
        "strategy": "hybrid: switching + reciprocal rank fusion",
        "top_n": top_n,
        "month": month,
        "routes": dict(route_counts),
        "travelers": rows,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    return payload


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def evaluate(data, top_n=TOP_N):
    """The hybrid and both parents and popularity, in one table.

    THE HYBRID MUST BEAT BOTH PARENTS ON hit@N AND ON CATALOG COVERAGE, or
    it is complexity with no return. Read the coverage column first: on this
    dataset the collaborative parent posts a hit-rate it has not earned (see
    recommend()'s note on cohort contamination), and coverage is the number
    that is harder to fake."""
    profiles = build_user_content_profiles(data.user_item, data.item_features,
                                           split=data.split)
    weights = cbf.feature_weights(data.item_features)
    item_sim = cf.item_similarity(data.user_item)

    train_seen = defaultdict(set)
    for row in data.split["train"]:
        train_seen[row["traveler_id"]].add(row["destination_key"])
    popularity = Counter()
    for row in data.split["train"]:
        popularity[row["destination_key"]] += 1

    names = ("hybrid", "content", "item_item", "popularity")
    ranks = {n: [] for n in names}
    coverage = {n: set() for n in names}

    for case in data.split["test"]:
        traveler_id, target = case["traveler_id"], case["destination_key"]
        seen = train_seen[traveler_id]
        decision = route_for(data, traveler_id, profiles)

        orders = {}
        content_rows = cbf.recommend(data, traveler_id, top_n=None, profiles=profiles,
                                     exclude_visited=False, diversify=False,
                                     weights=weights)
        content_rows = [r for r in content_rows if r["destination_key"] not in seen]
        collab_rows = cf.item_item_recommend(data, traveler_id, top_n=None, sim=item_sim,
                                             exclude_visited=False, history=seen)
        collab_rows = [r for r in collab_rows if r["destination_key"] not in seen]

        orders["content"] = [r["destination_key"] for r in content_rows]
        orders["item_item"] = [r["destination_key"] for r in collab_rows]
        orders["popularity"] = [k for k, _ in popularity.most_common() if k not in seen]

        if decision["route"] == "neither":
            orders["hybrid"] = [r["destination_key"]
                                for r in cold_start(data, traveler_id, top_n=None or 999)]
        elif decision["route"] == "content":
            orders["hybrid"] = orders["content"]
        elif decision["route"] == "collaborative":
            orders["hybrid"] = orders["item_item"]
        else:
            w = min(1.0, decision["usable_neighbours"] / NEIGHBOURS_FOR_FULL_WEIGHT)
            orders["hybrid"] = [r["destination_key"]
                                for r in blend(content_rows, collab_rows, 1.0 - w, w)]

        for name in names:
            order = orders[name]
            coverage[name].update(order[:top_n])
            rank = order.index(target) + 1 if target in order else None
            ranks[name].append(rank)

    def score(values):
        if not values:
            return {"n": 0, "hit_rate": 0.0, "mrr": 0.0}
        return {"n": len(values),
                "hit_rate": sum(1 for r in values if r and r <= top_n) / len(values),
                "mrr": sum(1 / r for r in values if r) / len(values)}

    return {"top_n": top_n,
            "models": {n: dict(score(ranks[n]), coverage=len(coverage[n])) for n in names},
            "catalog_size": len(data.destinations)}


def print_evaluation(result):
    print(f"HYBRID -- leave-last-out evaluation, top-{result['top_n']}")
    print()
    print(f"  {'model':14} {'n':>4} {'hit@' + str(result['top_n']):>8} {'MRR':>8} {'coverage':>12}")
    for name, row in result["models"].items():
        print(f"  {name:14} {row['n']:4} {row['hit_rate']:8.3f} {row['mrr']:8.3f} "
              f"{row['coverage']:7} /{result['catalog_size']:4}")
    print()
    print("  Read coverage first. On this dataset the collaborative parent posts a")
    print("  hit-rate it has not earned -- the authored cohorts share itineraries by")
    print("  construction, so a neighbourhood model rediscovers the generator. See")
    print("  recommend()'s note on why the blend weights are NOT fitted on this table.")


def main():
    parser = argparse.ArgumentParser(description="Hybrid recommender.")
    parser.add_argument("--traveler", default=DEFAULT_TRAVELER)
    parser.add_argument("--routes", action="store_true",
                        help="report routing across all travelers instead of one")
    parser.add_argument("--month", default=None,
                        help="re-rank for this month (e.g. march)")
    parser.add_argument("--evaluate", action="store_true",
                        help="leave-last-out for the hybrid, both parents and popularity")
    parser.add_argument("--write", action="store_true",
                        help="write recommendations.json -- the file the API serves")
    args = parser.parse_args()

    data = prepare()
    if args.evaluate:
        print_evaluation(evaluate(data))
        return
    if args.write:
        payload = write_recommendations(data, month=args.month)
        total = sum(len(row["recommendations"]) for row in payload["travelers"])
        print(f"{len(payload['travelers'])} travelers, {total} recommendations "
              f"({payload['top_n']} each)")
        print("  routes: " + "  ".join(f"{k}:{v}" for k, v in sorted(payload["routes"].items())))
        sources = Counter(rec["source"] for row in payload["travelers"]
                          for rec in row["recommendations"])
        print("  sources: " + "  ".join(f"{k}:{v}" for k, v in sources.most_common()))
        distinct = {rec["destination_key"] for row in payload["travelers"]
                    for rec in row["recommendations"]}
        print(f"  {len(distinct)} distinct destinations recommended, of "
              f"{len(data.destinations)} in the catalog")
        no_month = sum(1 for row in payload["travelers"] for rec in row["recommendations"]
                       if rec["best_month"] is None)
        print(f"  {no_month} rows have best_month null (no weather normals for that city)")
        print()
        print(f"Wrote -> {RECOMMENDATIONS_PATH}")
        return
    if args.routes:
        routes_report(data)
    else:
        readiness_report(data, args.traveler)


if __name__ == "__main__":
    main()
