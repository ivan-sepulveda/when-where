"""
Derived from: rec_sys_data_prep.py (which is where all the real work lives)

CONTENT-BASED FILTERING -- recommend a destination because it RESEMBLES the
destinations this traveler already chose. No other traveler is consulted.

    "You have been to Lisbon, Porto and Barcelona, all high-Michelin,
     high-weather, Southern Europe. Here is Valencia."

*** THE RECOMMENDER ITSELF IS NOT IMPLEMENTED. ***

Everything below the DATA PREPARATION line runs for real: it loads the
prepared tables, builds this traveler's taste vector in destination-feature
space, assembles their candidate pool, and reports exactly what the model
would be handed. Everything below the MODEL line is pseudocode and a
commented reference sketch -- `recommend()` raises NotImplementedError on
purpose. That split is the point of this pass: get the inputs provably
right, then argue about the algorithm.

WHY CONTENT-BASED IS THE ONE TO BUILD FIRST HERE. This dataset has 263
travelers and 222 destinations at 1.4% density, and 160 of those travelers
have been to exactly one place -- far too thin for collaborative filtering
(see rec_sys_collaborative_filtering.py, which says so at length), but every
destination carries real features from the rest of the pipeline:
UNESCO, Michelin, Plog allocentrism, a 12-month weather curve, an M49
region, and the tag mix of the trips taken there. A content model works from
day one for any traveler with a single trip, and it can rank a destination
nobody in the dataset has ever visited. Collaborative filtering can do
neither.

WHAT IT CANNOT DO, STATED UP FRONT SO IT DOESN'T GET REDISCOVERED LATER:
- **It cannot surprise anyone.** Content similarity returns more of the
  same, forever. Everything it recommends is by construction near what the
  traveler already did. That is a feature for "where next?" and a failure
  for "show me something I would never have thought of" -- the serendipity
  half is rec_sys_hybrid.py's problem.
- **It is blind to the 41 unmatched destinations** (Punta Cana, Kahului,
  Providenciales and the rest of the resort towns below tourist_cities'
  population cutoff). They have no content vector beyond popularity and tag
  shares, so this model can only ever rank them on imputed means. They are
  flagged as `content_cold` in the readiness report and must not be silently
  ranked as if they were fully described.
- **It has no idea what a trip costs anyone**, only what it cost the people
  who took it.

THE MISSINGNESS RULE THIS FILE HAS TO HONOUR. rec_sys_data_prep hands over a
feature matrix AND an observed-mask. A cosine over the raw rows silently
scores imputed cells as if they were measurements. Every similarity here
must be computed over the intersection of the two masks (traveler profile
and candidate), and the overlap size must travel with the score -- a 0.98
similarity computed over three shared features is not the same fact as a
0.98 over forty, and a ranked list that mixes them is lying about its
confidence.

Usage:
    python data/scripts/multiple/rec_sys_content_based_filtering.py
    python data/scripts/multiple/rec_sys_content_based_filtering.py --traveler anthony-bourdain
    python data/scripts/multiple/rec_sys_content_based_filtering.py --traveler dr-valentini --holdout
"""

import argparse

from rec_sys_data_prep import prepare, build_user_content_profiles

# Reported when --traveler is not given. 25 distinct destinations, which is
# enough history for a real taste vector and few enough that the candidate
# pool is still almost the whole catalog. For the opposite case, try
# --traveler dr-valentini: 20 trips, ALL to the same place, so the profile
# is sharp and the model has nothing to generalise from.
DEFAULT_TRAVELER = "stan-getz"

# How many nearest destinations a recommendation would be drawn from, and
# how few shared observed features is too few to trust a similarity.
TOP_N = 10
MIN_SHARED_FEATURES = 8


# ===========================================================================
# DATA PREPARATION -- real, runs today
# ===========================================================================

def candidate_pool(data, traveler_id, exclude_visited=True):
    """The destinations this traveler could be sent to.

    Everything in the catalog minus everywhere they have already been. That
    exclusion is not a detail: without it the top of every ranked list is
    the traveler's own home-region favourites, which scores beautifully on
    any similarity metric and is useless as a recommendation.

    `exclude_visited=False` exists for evaluation, where the held-out
    destination has to stay IN the pool or there is nothing to find."""
    visited = data.user_item.items_for(traveler_id) if exclude_visited else set()
    return [d for d in data.destinations if d["destination_key"] not in visited]


def profile_coverage(profile_vector, item_features, *groups):
    """Which features this traveler's taste vector actually has evidence for.

    Returns (observed_names, missing_names). A coordinate is None when every
    destination they visited had that feature imputed -- e.g. a traveler
    whose entire history is unmatched resort towns has no Michelin
    coordinate at all. That is a real state and the model must be able to
    see it, not discover it as a crash.

    PASS THE GROUPS YOU MEAN. With no arguments this counts every column,
    including the one-hot region block and the two popularity columns, which
    are observed for every destination by construction -- so an unqualified
    count says 30-ish for a traveler who has been to one unmatched resort
    town and knows nothing. `profile_coverage(v, m, "content", "season")` is
    the count that reflects real evidence, and it is what
    rec_sys_hybrid.py's routing gate uses."""
    return item_features.observed_in_groups(profile_vector, *groups)


def content_cold_items(data):
    """Destinations with no city record, i.e. no content features to match
    on. Content filtering cannot rank these honestly; collaborative
    filtering can. rec_sys_hybrid.py is where that gets resolved."""
    return [d["destination_key"] for d in data.destinations if not d["matched"]]


def readiness_report(data, traveler_id, holdout=False):
    """Print exactly what the not-yet-written model would receive.

    This is the deliverable of this pass. If any of these numbers look
    wrong, the fix belongs in rec_sys_data_prep.py, not in a model tuned
    around bad inputs."""
    profile = data.traveler(traveler_id)
    profiles = build_user_content_profiles(
        data.user_item, data.item_features, split=data.split if holdout else None
    )
    vector = profiles[traveler_id]
    observed, missing = profile_coverage(vector, data.item_features, "content", "season")
    all_observed, _ = profile_coverage(vector, data.item_features)
    pool = candidate_pool(data, traveler_id)
    cold = set(content_cold_items(data))
    visited = data.user_item.items_for(traveler_id)

    print(f"CONTENT-BASED FILTERING -- inputs for {profile['name']} ({traveler_id})")
    print(f"  profile built from {'TRAIN interactions only' if holdout else 'all interactions'}")
    print()
    describable = len(data.item_features.names_in_groups("content", "season"))
    print(f"  history          {profile['trip_count']} trips to {len(visited)} destinations")
    print(f"  taste vector     {len(observed)} of {describable} content/season features observed "
          f"({len(all_observed)} of {len(data.item_features.names)} columns overall -- the "
          f"region one-hots are always observed, which is why the first number is the real one)")
    if missing:
        print(f"                   no evidence for: {', '.join(missing[:6])}"
              f"{' ...' if len(missing) > 6 else ''}")
    print(f"  candidate pool   {len(pool)} destinations "
          f"({sum(1 for d in pool if d['destination_key'] in cold)} of them content-cold)")

    if holdout:
        held = next((t for t in data.split["test"] if t["traveler_id"] == traveler_id), None)
        print(f"  holdout target   {held['destination_key'] if held else 'none -- cold-start user'}")

    print()
    print("  strongest coordinates in this traveler's taste vector")
    ranked = sorted(
        ((n, v) for n, v in zip(data.item_features.names, vector) if v is not None),
        key=lambda pair: -pair[1],
    )
    for name, value in ranked[:8]:
        print(f"    {name:34} {value:.3f}")

    print()
    print("  a few candidates, with the shared-feature count a similarity would rest on")
    for dest in sorted(pool, key=lambda d: -d["trips"])[:6]:
        row_index = data.item_features.ids.index(dest["destination_key"])
        shared = sum(
            1 for j, value in enumerate(vector)
            if value is not None and data.item_features.mask[row_index][j]
        )
        flag = "  content-cold" if dest["destination_key"] in cold else ""
        print(f"    {dest['destination_key']:34} {dest['trips']:4} trips  "
              f"{shared:3} shared features{flag}")

    print()
    print(f"  NOT IMPLEMENTED: recommend() -- see the pseudocode below this line.")


# ===========================================================================
# MODEL -- pseudocode only. Nothing below this line runs.
# ===========================================================================

def masked_cosine(profile_vector, item_row, item_mask):
    """PSEUDOCODE. Cosine similarity over observed coordinates only.

        shared = [j for j where profile_vector[j] is not None and item_mask[j]]
        if len(shared) < MIN_SHARED_FEATURES:
            return None, len(shared)      # not "0.0" -- unknown is not dissimilar

        dot   = sum(profile_vector[j] * item_row[j] for j in shared)
        norm1 = sqrt(sum(profile_vector[j] ** 2 for j in shared))
        norm2 = sqrt(sum(item_row[j] ** 2 for j in shared))
        return dot / (norm1 * norm2), len(shared)

    RETURNS THE OVERLAP ALONGSIDE THE SCORE, always. The caller needs both
    to rank honestly -- see the module docstring.

    An alternative worth measuring before settling: weight each coordinate
    by how much it VARIES across the catalog (inverse-variance, or plain
    TF-IDF over the one-hot region block). Every destination in this dataset
    scores high on "is a city", so undifferentiated features currently get
    the same vote as the ones that actually separate Reykjavik from Cancun.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def recommend(data, traveler_id, top_n=TOP_N, month=None):
    """PSEUDOCODE. Rank the candidate pool by similarity to the traveler's
    taste vector.

        1. profile = build_user_content_profiles(...)[traveler_id]
           (already real -- rec_sys_data_prep.py builds it)

        2. pool = candidate_pool(data, traveler_id)
           (already real)

        3. for each candidate in pool:
               score, overlap = masked_cosine(profile, row, mask)
               skip if score is None                    # too little overlap
               if month is given:
                   score *= seasonal_fit(candidate, month)
               record (candidate, score, overlap)

        4. WHY SEASONALITY IS A MULTIPLIER AND NOT A FEATURE. The 12 monthly
           weather columns are in the vector, so cosine already prefers
           places whose ANNUAL SHAPE matches where this traveler goes. That
           answers "would they like this place". It does not answer "should
           they go in March", which is the question the site is named after.
           Applying the target month as a multiplier at ranking time keeps
           the two separable and lets one profile serve twelve answers.

               seasonal_fit(candidate, month):
                   score = candidate["weather_by_month"][month]  (0-10)
                   return score / 10 if the curve exists else 1.0
                                 # 1.0, NOT 0 -- an unknown curve must not
                                 # push a destination off the list

        5. penalise near-duplicates before returning: if two candidates are
           in the same detailed_region AND within epsilon of each other,
           keep the better one. Ten Southern European cities is a ranking,
           not a recommendation.

        6. return top_n, each with:
               destination_key, score, shared_feature_count,
               the 3 features that contributed most to the dot product
               (that list IS the explanation -- see explain())

    EVALUATION, when there is something to evaluate:
        for each user in data.split["test"]:
            build the profile from TRAIN only (build_user_content_profiles
            takes split= for exactly this), rank the pool WITH the held-out
            destination left in, record the rank it lands at.
        report hit-rate@10 and MRR against two baselines that must be beaten
        before any of this is worth keeping:
            - most-popular (rank everything by `trips`, ignore the user)
            - same-region-random
        A content model that cannot beat most-popular on this dataset is
        measuring popularity through a longer pipe.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def explain(data, traveler_id, destination_key):
    """PSEUDOCODE. Why this destination, in words a trip card can hold.

        shared = observed coordinates common to profile and candidate
        contributions = [(name, profile[j] * item[j]) for j in shared]
        take the top 3 by contribution, translate the feature names:

            michelin_score          -> "as much Michelin coverage as ..."
            weather_july            -> "July weather like ..."
            region_Southern Europe  -> "in Southern Europe, where N of their
                                        M trips went"
            beach_share             -> "the kind of beach trip they take"

        then name the traveler's own most similar visited destination as the
        anchor: "closest to your Lisbon trips". An explanation that cites
        the user's own history is checkable by the user; one that cites a
        cosine is not.
    """
    raise NotImplementedError("pseudocode -- see docstring")


# --- reference sketch, deliberately commented out --------------------------
#
# Roughly what step 3 looks like once the decisions above are settled. Left
# here as a sketch, not as code: it has no seasonality, no de-duplication
# and no overlap floor, so running it would produce a ranked list that looks
# plausible and is not the thing this file describes.
#
# def _sketch_rank(data, traveler_id):
#     profiles = build_user_content_profiles(data.user_item, data.item_features)
#     profile = profiles[traveler_id]
#     scored = []
#     for dest in candidate_pool(data, traveler_id):
#         i = data.item_features.ids.index(dest["destination_key"])
#         row, mask = data.item_features.rows[i], data.item_features.mask[i]
#         shared = [j for j, v in enumerate(profile) if v is not None and mask[j]]
#         if len(shared) < MIN_SHARED_FEATURES:
#             continue
#         dot = sum(profile[j] * row[j] for j in shared)
#         n1 = math.sqrt(sum(profile[j] ** 2 for j in shared))
#         n2 = math.sqrt(sum(row[j] ** 2 for j in shared))
#         if n1 and n2:
#             scored.append((dot / (n1 * n2), len(shared), dest["destination_key"]))
#     return sorted(scored, reverse=True)[:TOP_N]


def main():
    parser = argparse.ArgumentParser(description="Content-based filtering -- data prep only.")
    parser.add_argument("--traveler", default=DEFAULT_TRAVELER)
    parser.add_argument("--holdout", action="store_true",
                        help="build the taste profile from TRAIN interactions only")
    args = parser.parse_args()

    data = prepare()
    readiness_report(data, args.traveler, holdout=args.holdout)


if __name__ == "__main__":
    main()
