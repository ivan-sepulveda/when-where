"""
Derived from: rec_sys_data_prep.py            (all the real work)
              rec_sys_content_based_filtering.py
              rec_sys_collaborative_filtering.py

HYBRID -- decide, per traveler, which of the two models is entitled to an
opinion, and combine them when both are.

*** THE RECOMMENDER ITSELF IS NOT IMPLEMENTED. ***

Everything below the DATA PREPARATION line runs for real: it computes the
ROUTING TABLE -- for every traveler, whether the content model has enough
taste evidence, whether the collaborative model has enough neighbourhood,
and therefore which branch a request would take -- and reports the coverage
across the whole population. Everything below the MODEL line is pseudocode;
`recommend()` raises NotImplementedError on purpose.

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
from collections import Counter

from rec_sys_data_prep import OUT_DIR, prepare, build_user_content_profiles
from rec_sys_content_based_filtering import candidate_pool, content_cold_items, profile_coverage
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

    print()
    print("  NOT IMPLEMENTED: recommend() -- see the pseudocode below this line.")


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
# MODEL -- pseudocode only. Nothing below this line runs.
# ===========================================================================

def recommend(data, traveler_id, top_n=TOP_N, month=None, strategy="switching"):
    """PSEUDOCODE. The hybrid entry point.

        decision = route_for(data, traveler_id, content_profiles)   # already real

        SWITCHING (build this one first -- it needs no tuning and it is
        the honest reading of the routing table):

            if decision["route"] == "both":            -> blend(...)
            if decision["route"] == "content":         -> content.recommend(...)
            if decision["route"] == "collaborative":   -> collaborative.item_item_recommend(...)
            if decision["route"] == "neither":         -> popularity_baseline(...)
                                                          tagged source="popularity",
                                                          personalised=False

        WEIGHTED, for the "both" branch -- and NOT by adding raw scores.
        The two scales are incomparable (module docstring), so fuse RANKS:

            rrf(candidate) = w_content      / (K + rank_content(candidate))
                           + w_collaborative / (K + rank_collab(candidate))
            with K ~= 60 (reciprocal rank fusion's usual constant; it damps
            the top of each list so one model cannot dictate the head)

            A candidate ranked by only ONE model still scores -- it simply
            gets one term. That is the correct behaviour for the 52
            content-blind destinations: collaborative can still surface
            them, at a discount, instead of them vanishing.

        CASCADE, the variant worth measuring against SWITCHING:
            collaborative proposes the top ~50 (it is better at "would
            anyone go there"), content re-ranks those 50 (it is better at
            "would YOU like it"). Cheaper, and it makes the explanation
            two-part and readable: "travelers like you went; it also matches
            your Michelin/weather pattern".

        WEIGHTS ARE NOT A CONSTANT. w_content should rise as the
        traveler's evidence thins -- roughly
            w_collaborative = min(1, usable_neighbours / 10)
            w_content       = 1 - w_collaborative
        so a traveler with three neighbours leans on content and one with
        thirty leans on their peers. Fit this on the split, do not pick it.

    THE POST-PROCESSING THAT MATTERS MORE THAN THE BLEND:

        1. DIVERSITY. Cap the list at 2 per detailed_region. Without it
           every list here is Southern Europe and the Caribbean, because
           that is where the trips are.
        2. SEASONALITY. If `month` is given, multiply by the destination's
           own weather score for that month (see the content model's
           seasonal_fit) -- and a destination with no weather curve
           multiplies by 1.0, never 0.
        3. DISTANCE FROM HOME. `base_detailed_region` is on every traveler
           row for exactly this: a Houston traveler being sent to Cancun for
           the fourth time is different from being sent to Ljubljana, and
           the model should be able to say which it is doing.
        4. EXPLANATION IS MANDATORY, and its source must be named -- which
           model produced the candidate, and what evidence. An unexplained
           travel recommendation is unactionable; nobody books a flight
           because a number was high.

    EVALUATION: run the same leave-last-out loop as the collaborative file,
    report the hybrid AND both components AND popularity in one table. The
    hybrid must beat both parents on hit-rate@10 AND on catalog coverage,
    or it is complexity with no return.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def blend(content_ranked, collaborative_ranked, w_content, w_collaborative, k=60):
    """PSEUDOCODE. Reciprocal rank fusion of two ranked lists.

        scores = {}
        for rank, (key, _) in enumerate(content_ranked, start=1):
            scores[key] += w_content / (k + rank)
        for rank, (key, _) in enumerate(collaborative_ranked, start=1):
            scores[key] += w_collaborative / (k + rank)
        return sorted(scores by value, descending)

    RANKS, NOT SCORES, ON PURPOSE. Rank fusion needs no calibration, no
    shared scale, and no assumption that either model's numbers mean
    anything in absolute terms -- all of which are false here. The cost is
    that it throws away the MARGIN between first and second place; if that
    margin turns out to matter, the upgrade is per-model score
    normalisation (z-score within the candidate pool) and not a return to
    raw addition.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def cold_start(data, traveler_id, top_n=TOP_N):
    """PSEUDOCODE. What to do for the NEITHER route.

        There is no personalised answer, and the design decision is to say
        so rather than to imitate one. In order of preference:

        1. If the traveler has a declared base (base_inference == "declared"
           -- already on every traveler row), rank by popularity AMONG
           TRAVELERS SHARING THAT BASE REGION. Weak, honest, and better than
           global popularity.
        2. Otherwise global popularity by distinct travelers
           (popularity_baseline -- already real).
        3. Either way, return `personalised: False` in the payload and let
           the UI say "popular right now" rather than "for you". The
           difference between those two labels is the difference between a
           product that is trusted and one that is not.

        What NOT to do: fabricate a taste vector from the population mean
        and present its output as personalised. It ranks well against the
        split and is a lie to the user.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def write_recommendations(data, top_n=RECOMMENDATIONS_TOP_N, path=RECOMMENDATIONS_PATH):
    """PSEUDOCODE. Run recommend() for every traveler and write the file the
    API serves.

    THIS IS THE HANDOFF POINT between the offline recommender and the running
    site, and it already has a consumer: the "Recommend 3 places" button on
    the traveler detail page fetches
    GET /api/travelers/{id}/recommendations, which reads nothing but this
    file. Nothing in the backend computes a recommendation -- same
    offline/online split this project already uses for tags and entropy, for
    the same reason (ranking 222 candidates per request is pipeline work).
    So finishing recommend() and calling this is the ONLY remaining step;
    no server or frontend change is needed.

        rows = []
        for traveler in data.travelers:
            if traveler["traveler_id"] not in data.user_item.by_user:
                continue                    # the 8 with no countable trip
            decision = route_for(data, traveler["traveler_id"], profiles)
            picks = recommend(data, traveler["traveler_id"], top_n=top_n)
            rows.append({
                "traveler_id": traveler["traveler_id"],
                "route": decision["route"],
                # False on the popularity fallback. The UI labels those
                # "popular right now" instead of "for you" -- see cold_start().
                "personalised": decision["route"] != "neither",
                "recommendations": [
                    {"destination_key":     pick.key,
                     "destination_city":    ...,
                     "destination_country": ...,
                     "region":              detailed_region or None,
                     "score":               round(pick.score, 4),
                     "source":              "content" | "collaborative"
                                            | "hybrid" | "popularity",
                     "best_month":          argmax of weather_by_month, or None
                                            when the city has no curve,
                     "why":                 [short, checkable strings]}
                    for pick in picks
                ],
            })

        json.dump({"generated": date.today().isoformat(),
                   "strategy": "hybrid: switching + reciprocal rank fusion",
                   "top_n": top_n,
                   "travelers": rows}, ...)

    TWO FIELDS THAT ARE NOT OPTIONAL, whatever the model ends up being:
    `why`, because a recommendation nobody can check is one nobody books; and
    `source`, because a mixed list should read as the mixture it is. The
    frontend renders both and drops a row's chip entirely if `source` is a
    value it does not recognise, so adding a fourth model later is safe.

    `best_month` is null for the ~quarter of destinations with no weather
    normals. Null means UNKNOWN, not "any month" -- the frontend omits the
    line rather than printing a guess, matching the trip cards.
    """
    raise NotImplementedError("pseudocode -- see docstring")


# --- reference sketch, deliberately commented out --------------------------
#
# The switching skeleton, once the two component models exist. Commented
# because it imports functions that currently raise, and because the weight
# rule in the "both" branch is a guess until it is fitted on the split.
#
# def _sketch_recommend(data, traveler_id, month=None, top_n=TOP_N):
#     import rec_sys_content_based_filtering as cbf
#     import rec_sys_collaborative_filtering as cf
#     profiles = build_user_content_profiles(data.user_item, data.item_features)
#     decision = route_for(data, traveler_id, profiles)
#     if decision["route"] == "content":
#         return cbf.recommend(data, traveler_id, top_n=top_n, month=month)
#     if decision["route"] == "collaborative":
#         return cf.item_item_recommend(data, traveler_id, top_n=top_n)
#     if decision["route"] == "neither":
#         return cold_start(data, traveler_id, top_n=top_n)
#     w_collab = min(1.0, decision["usable_neighbours"] / 10)
#     return blend(
#         cbf.recommend(data, traveler_id, top_n=None, month=month),
#         cf.item_item_recommend(data, traveler_id, top_n=None),
#         w_content=1 - w_collab, w_collaborative=w_collab,
#     )[:top_n]


def main():
    parser = argparse.ArgumentParser(description="Hybrid recommender -- data prep only.")
    parser.add_argument("--traveler", default=DEFAULT_TRAVELER)
    parser.add_argument("--routes", action="store_true",
                        help="report routing across all travelers instead of one")
    args = parser.parse_args()

    data = prepare()
    if args.routes:
        routes_report(data)
    else:
        readiness_report(data, args.traveler)


if __name__ == "__main__":
    main()
