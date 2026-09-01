"""
Derived from: rec_sys_data_prep.py (which is where all the real work lives)

COLLABORATIVE FILTERING -- recommend a destination because PEOPLE LIKE THIS
TRAVELER went there. Nothing about the destination itself is consulted; a
city is a column of visits and nothing more.

    "Eleven travelers whose history overlaps yours went to Reykjavik.
     You have not."

*** THE RECOMMENDER ITSELF IS NOT IMPLEMENTED. ***

Everything below the DATA PREPARATION line runs for real: it loads the
interaction matrix, computes the co-visit structure, finds a traveler's
nearest neighbours by overlap, and reports the sparsity the model would
actually face. Everything below the MODEL line is pseudocode --
`recommend()` raises NotImplementedError on purpose.

THE HONEST HEADLINE, BEFORE ANY OF THE MATHS: **this dataset is thin for
collaborative filtering and the readiness report is designed to prove it
rather than paper over it.** 263 travelers x 222 destinations at **1.4%
density -- 810 interactions in total**, and 160 travelers have been to
exactly one destination. Worse, the density is not evenly thin: it is one
Bourdain with 131 destinations, a long tail of one-trip travelers, and
hand-authored itineraries whose overlap structure is a consequence of how
build_synthetic_trips.py was written, not of how people travel. Any
neighbourhood model will find its "similar travelers" inside the authored
cohorts, because those are the only travelers who share destinations by
design.

That is not a reason to skip this file. It is the reason to build the
diagnostics FIRST: if user-user overlap medians come back at 1 or 2 shared
destinations, no amount of cosine tuning saves it, and the honest answer is
that this dataset wants a content model with a collaborative prior -- which
is exactly what rec_sys_hybrid.py is for.

IMPLICIT FEEDBACK, NOT RATINGS. Nobody in this dataset ever rated anything
and nobody ever will; the only signal is "went" and "went repeatedly". So:
- **There are no negatives.** A destination a traveler has not visited is
  unknown, not disliked. Any loss function that treats the zeros as
  negatives (plain SVD on the raw matrix does exactly this) is asserting
  something the data never said.
- The confidence weighting from rec_sys_data_prep -- c = 1 + ALPHA *
  ln(1 + visits) -- is the Hu/Koren answer to that, and it is why the
  prepared matrix carries confidence AND raw visits.
- **Popularity is the baseline to beat, and it is a hard one.** Cancun has
  133 trips and Orlando 124. Recommending those to everyone will score
  respectably on hit-rate, which is why the evaluation below insists on
  reporting it alongside.

Usage:
    python data/scripts/multiple/rec_sys_collaborative_filtering.py
    python data/scripts/multiple/rec_sys_collaborative_filtering.py --traveler anthony-bourdain
    python data/scripts/multiple/rec_sys_collaborative_filtering.py --neighbours 15
"""

import argparse
from collections import Counter

from rec_sys_data_prep import prepare

DEFAULT_TRAVELER = "stan-getz"
TOP_N = 10
DEFAULT_NEIGHBOURS = 20

# Below this many shared destinations, two travelers are not neighbours,
# they are a coincidence. One shared destination between two people who have
# each been to Cancun says nothing -- everyone has been to Cancun.
MIN_SHARED_DESTINATIONS = 2


# ===========================================================================
# DATA PREPARATION -- real, runs today
# ===========================================================================

def co_visit_counts(user_item):
    """(destination A, destination B) -> how many travelers visited both.

    The raw material for ITEM-item collaborative filtering, and the more
    promising of the two directions here: there are fewer destinations than
    travelers, each has more interactions than the median traveler, and item
    neighbourhoods stay stable as travelers are added. Computed for real --
    it is a double loop over each traveler's own destinations, which at this
    size is instant."""
    pairs = Counter()
    for items in user_item.by_user.values():
        keys = sorted(items)
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                pairs[(a, b)] += 1
    return pairs


def user_overlap(user_item, traveler_id):
    """Every other traveler who shares at least one destination, with the
    overlap size. Real, and the single most important diagnostic in this
    file: it is the number that decides whether collaborative filtering is
    viable at all here."""
    mine = user_item.items_for(traveler_id)
    overlaps = []
    for other_id, items in user_item.by_user.items():
        if other_id == traveler_id:
            continue
        shared = mine & set(items)
        if shared:
            overlaps.append((other_id, len(shared), sorted(shared)))
    overlaps.sort(key=lambda row: (-row[1], row[0]))
    return overlaps


def sparsity_profile(user_item):
    """The shape of the interaction matrix, said plainly.

    Reported rather than assumed because every collaborative method's
    failure mode is a function of these five numbers."""
    per_user = sorted(len(items) for items in user_item.by_user.values())
    per_item = Counter()
    for items in user_item.by_user.values():
        for key in items:
            per_item[key] += 1
    per_item_counts = sorted(per_item.values())

    def median(values):
        if not values:
            return 0
        mid = len(values) // 2
        return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2

    return {
        "users": len(user_item.user_ids),
        "items": len(user_item.item_ids),
        "density": user_item.density(),
        "median_destinations_per_user": median(per_user),
        "max_destinations_per_user": per_user[-1] if per_user else 0,
        "users_with_one_destination": sum(1 for n in per_user if n == 1),
        "median_users_per_destination": median(per_item_counts),
        "items_with_one_user": sum(1 for n in per_item_counts if n == 1),
        "popularity": per_item,
    }


def popularity_baseline(user_item, traveler_id, top_n=TOP_N):
    """The baseline any of this has to beat: rank unvisited destinations by
    how many DISTINCT travelers went, not by trip count.

    Distinct travelers, deliberately -- Bourdain's 201 trips would otherwise
    define the popularity ranking single-handed. This one is real because a
    baseline that is only pseudocode cannot be beaten by anything."""
    visited = user_item.items_for(traveler_id)
    counts = Counter()
    for other_id, items in user_item.by_user.items():
        if other_id == traveler_id:
            continue
        for key in items:
            counts[key] += 1
    ranked = [(key, n) for key, n in counts.most_common() if key not in visited]
    return ranked[:top_n]


def readiness_report(data, traveler_id, neighbours=DEFAULT_NEIGHBOURS):
    """Print exactly what the not-yet-written model would receive -- and, in
    this file's case, whether it should be written at all."""
    profile = data.traveler(traveler_id)
    ui = data.user_item
    shape = sparsity_profile(ui)

    print(f"COLLABORATIVE FILTERING -- inputs for {profile['name']} ({traveler_id})")
    print()
    print("  matrix")
    print(f"    {shape['users']} travelers x {shape['items']} destinations, "
          f"{shape['density']:.2%} dense")
    print(f"    destinations per traveler: median {shape['median_destinations_per_user']}, "
          f"max {shape['max_destinations_per_user']}, "
          f"{shape['users_with_one_destination']} travelers have exactly one")
    print(f"    travelers per destination: median {shape['median_users_per_destination']}, "
          f"{shape['items_with_one_user']} destinations were visited by exactly one traveler")

    overlaps = user_overlap(ui, traveler_id)
    usable = [row for row in overlaps if row[1] >= MIN_SHARED_DESTINATIONS]
    print()
    print(f"  neighbourhood for this traveler")
    print(f"    {len(overlaps)} travelers share at least 1 destination; "
          f"{len(usable)} share at least {MIN_SHARED_DESTINATIONS}")
    for other_id, count, shared in usable[:neighbours][:6]:
        sample = ", ".join(k.split("|")[0] for k in shared[:3])
        print(f"    {other_id:28} {count:3} shared   {sample}"
              f"{' ...' if len(shared) > 3 else ''}")
    if not usable:
        print("    NONE -- user-user CF cannot serve this traveler at all. "
              "This is the cold-start path rec_sys_hybrid.py routes to content.")

    pairs = co_visit_counts(ui)
    print()
    print(f"  item-item structure: {len(pairs)} destination pairs co-visited by someone")
    for (a, b), count in pairs.most_common(5):
        print(f"    {a.split('|')[0]:18} + {b.split('|')[0]:18} {count:4} travelers")

    print()
    print("  popularity baseline (the thing to beat), for this traveler")
    for key, count in popularity_baseline(ui, traveler_id, top_n=5):
        print(f"    {key:34} {count:4} other travelers went")

    print()
    print("  NOT IMPLEMENTED: recommend() -- see the pseudocode below this line.")


# ===========================================================================
# MODEL -- pseudocode only. Nothing below this line runs.
# ===========================================================================

def user_user_recommend(data, traveler_id, k=DEFAULT_NEIGHBOURS, top_n=TOP_N):
    """PSEUDOCODE. Classic user-user kNN over implicit feedback.

        1. neighbours = user_overlap(data.user_item, traveler_id)
           filtered to overlap >= MIN_SHARED_DESTINATIONS       (already real)

        2. similarity between two travelers -- pick ONE and write down why:

           a. COSINE over the confidence vectors. Standard, but dominated by
              the popular columns: two travelers who have both been to
              Cancun and Orlando look similar to everyone.

           b. JACCARD over destination sets. Ignores visit counts entirely,
              which for this dataset may be a feature -- 201 Bourdain trips
              vs 5 Kaggle trips is a difference in DATA COLLECTION, not in
              enthusiasm, and cosine cannot tell those apart.

           c. Cosine over IDF-WEIGHTED confidences: weight each destination
              by log(n_users / users_who_went). Cancun stops carrying the
              similarity and Erbil starts to. Given the popularity skew
              here, this is the one to try first.

        3. score(candidate) = sum over neighbours n of
               similarity(u, n) * confidence(n, candidate)
           divided by sum of similarities (else the score is really a
           neighbour count wearing a similarity's clothes)

        4. drop everything the traveler has already visited, return top_n
           with the neighbours who contributed most -- those names ARE the
           explanation ("three travelers with your Denver-ski pattern went
           to Chamonix").

    KNOWN PROBLEM ON THIS DATASET, WRITE IT DOWN BEFORE MEASURING: the
    hand-authored travelers were built in cohorts that share itineraries by
    construction. A neighbourhood model will rediscover those cohorts and
    look accurate while having learned build_synthetic_trips.py rather than
    travel behaviour. Compare hit-rate on authored vs Kaggle-sourced
    travelers separately -- if it only works on the authored ones, it does
    not work.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def item_item_recommend(data, traveler_id, top_n=TOP_N):
    """PSEUDOCODE. Item-item kNN. The better bet of the two here.

        1. pairs = co_visit_counts(data.user_item)                (already real)

        2. normalise co-visits into a similarity -- raw counts are a
           popularity ranking in disguise:

               sim(a, b) = co_visits(a, b) /
                           sqrt(users(a) * users(b))        # cosine
           or
               sim(a, b) = co_visits(a, b) /
                           (users(a) + users(b) - co_visits(a, b))   # Jaccard

        3. score(candidate) = sum over the traveler's own visited items i of
               sim(i, candidate) * confidence(u, i)

        4. return top_n, each with the traveler's own visited destination
           that contributed most: "because you went to Reykjavik".

    WHY THIS ONE IS MORE PROMISING HERE. Item neighbourhoods are computed
    over all 263 travelers at once, so a destination with 40 visitors has 40
    observations behind its similarity row, while a traveler with 4 trips
    has 4. It also degrades gracefully for a new traveler: one visited
    destination is enough to produce a ranking, where user-user needs an
    overlap that a 1-trip traveler does not have.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def matrix_factorisation(data, factors=16, iterations=15, regularisation=0.05):
    """PSEUDOCODE. Implicit ALS (Hu, Koren & Volinsky 2008), the version that
    is correct for data with no negatives.

        P = binary preference   (1 where visited, 0 elsewhere)
        C = confidence          (data.user_item.by_user -- ALREADY BUILT,
                                 c = 1 + ALPHA * ln(1 + visits))

        minimise  sum over all (u, i) of
                    C[u][i] * (P[u][i] - x_u . y_i)^2
                  + regularisation * (||x_u||^2 + ||y_i||^2)

        alternate:
            for each user u:  x_u = (Y' Cu Y + lambda I)^-1 Y' Cu p_u
            for each item i:  y_i = (X' Ci X + lambda I)^-1 X' Ci p_i

        Note the sum runs over ALL cells, not just the observed ones -- that
        is the whole trick: unvisited cells enter with preference 0 and
        confidence 1, i.e. "probably not, weakly", which is the honest
        reading of an implicit zero.

    SIZING, HONESTLY. 263 x 222 with 810 interactions supports maybe 4-8
    factors before it is memorising. Anything more is fitting the authored
    cohorts. If this is built, `implicit` or plain numpy is the right tool
    and the first thing to check is whether the learned factors reproduce
    the M49 regions -- if they do, the content model already had that for
    free and this added a training step.

    SIDE INFORMATION IS AVAILABLE and this is where it would go: data.
    user_features (taste, cadence, base region) and data.item_features
    (UNESCO, Michelin, weather curve, region) are both prepared already, so
    a factorisation-machine / LightFM-style hybrid that folds features into
    the factors is a strictly better use of the same 15 minutes than plain
    ALS. That crossover is rec_sys_hybrid.py's territory.
    """
    raise NotImplementedError("pseudocode -- see docstring")


def evaluate(data, recommender, top_n=TOP_N):
    """PSEUDOCODE. Offline evaluation against the prepared leave-last-out
    split.

        hits = 0; reciprocal_ranks = []
        for case in data.split["test"]:
            ranked = recommender(train_only_view_of(data), case["traveler_id"], top_n=None)
            #        ^ the held-out destination MUST remain in the pool
            rank = position of case["destination_key"] in ranked
            hits += 1 if rank <= top_n
            reciprocal_ranks.append(1 / rank if rank else 0)

        report, side by side and never alone:
            hit_rate@10, MRR
            the SAME two for popularity_baseline()              (already real)
            the same two split by authored vs Kaggle travelers
            coverage: how many distinct destinations ever appear in a top-10
                      across all users -- a model that recommends Cancun to
                      263 people has a hit-rate and no value

    A NOTE ON WHAT THIS CAN AND CANNOT SETTLE. Offline hit-rate on 263
    synthetic travelers measures whether the model reproduces the generator.
    It is a regression test, not evidence that a recommendation is good.
    Nothing here should be described as accuracy outside this file.
    """
    raise NotImplementedError("pseudocode -- see docstring")


# --- reference sketch, deliberately commented out --------------------------
#
# Item-item scoring, minus the normalisation choice in step 2 -- which is
# exactly the decision that matters, so this is a sketch and not code.
#
# def _sketch_item_item(data, traveler_id):
#     pairs = co_visit_counts(data.user_item)
#     sim = defaultdict(dict)
#     for (a, b), count in pairs.items():
#         sim[a][b] = sim[b][a] = count        # <- raw counts: popularity, not similarity
#     mine = data.user_item.by_user.get(traveler_id, {})
#     scores = Counter()
#     for visited, confidence in mine.items():
#         for other, weight in sim.get(visited, {}).items():
#             if other not in mine:
#                 scores[other] += weight * confidence
#     return scores.most_common(TOP_N)


def main():
    parser = argparse.ArgumentParser(description="Collaborative filtering -- data prep only.")
    parser.add_argument("--traveler", default=DEFAULT_TRAVELER)
    parser.add_argument("--neighbours", type=int, default=DEFAULT_NEIGHBOURS)
    args = parser.parse_args()

    data = prepare()
    readiness_report(data, args.traveler, neighbours=args.neighbours)


if __name__ == "__main__":
    main()
