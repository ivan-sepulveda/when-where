"""
Derived from: rec_sys_data_prep.py (which is where all the real work lives)

COLLABORATIVE FILTERING -- recommend a destination because PEOPLE LIKE THIS
TRAVELER went there. Nothing about the destination itself is consulted; a
city is a column of visits and nothing more.

    "Eleven travelers whose history overlaps yours went to Reykjavik.
     You have not."

IMPLEMENTED 2026-09-05: user-user kNN, item-item kNN and implicit ALS, all
three measured against the popularity baseline by --evaluate. The
diagnostics in the DATA PREPARATION section were built first, and they were
right about what they predicted -- read them before reading a score.

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
import math
import random
from collections import Counter, defaultdict

from rec_sys_data_prep import prepare

DEFAULT_TRAVELER = "stan-getz"
TOP_N = 10
DEFAULT_NEIGHBOURS = 20

# Below this many shared destinations, two travelers are not neighbours,
# they are a coincidence. One shared destination between two people who have
# each been to Cancun says nothing -- everyone has been to Cancun.
MIN_SHARED_DESTINATIONS = 2

# Which similarity each direction uses. Named constants rather than buried
# defaults because the choice IS the model -- see user_similarity() and
# item_similarity() for what each one does to the popular columns.
USER_METRIC = "idf_cosine"     # idf_cosine | cosine | jaccard
ITEM_METRIC = "cosine"         # cosine | jaccard

# Implicit ALS. Eight factors on ~840 interactions is already generous;
# raising it fits the authored cohorts rather than learning taste.
ALS_FACTORS = 8
ALS_ITERATIONS = 15
ALS_REGULARISATION = 0.05

# Item-item shrinkage. A similarity resting on ONE shared visitor is not a
# similarity, and on this dataset that case is not rare: Bourdain alone
# accounts for 131 destinations, so hundreds of pairs co-occur exactly once
# and every one of them scores identically. Without this the item-item list
# came back as a block of tied scores in alphabetical order -- Addis Ababa,
# Albuquerque, Antananarivo -- which is the alphabet, not a recommendation.
# sim is multiplied by co / (co + SHRINKAGE), so a single co-visit keeps
# about a sixth of its weight and ten keep two thirds.
ITEM_SHRINKAGE = 5.0


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
    # Sorted on (-count, key), NOT Counter.most_common(): ties are common at
    # the head of a popularity ranking and most_common() breaks them on
    # insertion order, which is not stable across processes wherever a set
    # fed the counter. A baseline that reorders itself between runs is not a
    # baseline. See rec_sys_hybrid.cold_start() for the bug this caught.
    ranked = [(key, n) for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
              if key not in visited]
    return ranked[:top_n] if top_n is not None else ranked


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
# MODEL -- implemented 2026-09-05.
# ===========================================================================
#
# The diagnostics above were built first on purpose, and they were right: the
# neighbourhood is thin, item-item is the stronger of the two directions, and
# the popularity baseline is hard to beat. All three are now measured rather
# than predicted -- run --evaluate.

def idf_weights(user_item):
    """log(n_users / users_who_went) per destination.

    THE CHOICE THE PSEUDOCODE SAID TO MAKE FIRST, and it is the right one
    here. Cancun has 133 trips and Orlando 124; under a plain cosine, two
    travelers who have both been to Cancun look similar to everyone, because
    everyone has been to Cancun. IDF makes the popular columns cheap and the
    rare ones expensive, so sharing Erbil counts for more than sharing a
    resort town -- which is what "similar taste" actually means."""
    n_users = len(user_item.user_ids) or 1
    seen = Counter()
    for items in user_item.by_user.values():
        for key in items:
            seen[key] += 1
    return {key: math.log(n_users / count) for key, count in seen.items() if count}


def user_similarity(user_item, a, b, idf=None, metric=USER_METRIC):
    """How alike two travelers are. `metric` is one of the three the
    pseudocode laid out, and the default is stated rather than assumed.

        idf_cosine  cosine over IDF-weighted confidences  (DEFAULT)
        cosine      cosine over raw confidences
        jaccard     |shared| / |union| over destination sets

    WHY idf_cosine IS THE DEFAULT: see idf_weights(). WHY jaccard IS KEPT:
    it ignores visit counts entirely, and on this dataset that may be a
    feature -- Bourdain's 201 trips against a Kaggle traveler's 5 is a
    difference in DATA COLLECTION, not in enthusiasm, and cosine cannot tell
    those apart. It is one flag away for anyone who wants to measure it."""
    row_a = user_item.by_user.get(a, {})
    row_b = user_item.by_user.get(b, {})
    shared = set(row_a) & set(row_b)
    if not shared:
        return 0.0

    if metric == "jaccard":
        union = len(set(row_a) | set(row_b))
        return len(shared) / union if union else 0.0

    weight = (lambda key: 1.0) if metric == "cosine" else (lambda key: idf.get(key, 0.0))
    dot = sum((weight(k) ** 2) * row_a[k] * row_b[k] for k in shared)
    na = math.sqrt(sum((weight(k) * v) ** 2 for k, v in row_a.items()))
    nb = math.sqrt(sum((weight(k) * v) ** 2 for k, v in row_b.items()))
    return dot / (na * nb) if na and nb else 0.0


def user_user_recommend(data, traveler_id, k=DEFAULT_NEIGHBOURS, top_n=TOP_N,
                        idf=None, metric=USER_METRIC, exclude_visited=True):
    """User-user kNN over implicit feedback.

    score(candidate) = sum over neighbours of similarity * confidence,
    DIVIDED BY the sum of similarities -- without that division the score is
    a neighbour count wearing a similarity's clothes, and every traveler
    with more neighbours outranks every traveler with better ones.

    The contributing neighbours travel with each row: those names ARE the
    explanation ("three travelers with your Denver-ski pattern went to
    Chamonix")."""
    if idf is None:
        idf = idf_weights(data.user_item)
    mine = data.user_item.items_for(traveler_id) if exclude_visited else set()

    neighbours = []
    for other_id, count, _shared in user_overlap(data.user_item, traveler_id):
        if count < MIN_SHARED_DESTINATIONS:
            continue
        sim = user_similarity(data.user_item, traveler_id, other_id, idf, metric)
        if sim > 0:
            neighbours.append((other_id, sim))
    neighbours.sort(key=lambda row: (-row[1], row[0]))
    neighbours = neighbours[:k]
    if not neighbours:
        return []

    numer, denom, contributors = defaultdict(float), defaultdict(float), defaultdict(list)
    for other_id, sim in neighbours:
        for key, confidence in data.user_item.by_user[other_id].items():
            if key in mine:
                continue
            numer[key] += sim * confidence
            denom[key] += sim
            contributors[key].append((other_id, sim))

    scored = [{
        "destination_key": key,
        "score": numer[key] / denom[key] if denom[key] else 0.0,
        "support": len(contributors[key]),
        "because": [n for n, _ in sorted(contributors[key], key=lambda r: -r[1])[:3]],
    } for key in numer]
    scored.sort(key=lambda r: (-r["score"], -r["support"], r["destination_key"]))
    return scored if top_n is None else scored[:top_n]


def user_item_rows(data):
    """The interaction rows, one small indirection so item_item_recommend can
    count distinct travelers per destination without reaching past `data`."""
    return data.user_item.by_user


def item_similarity(user_item, metric=ITEM_METRIC, shrinkage=ITEM_SHRINKAGE):
    """destination -> {destination: similarity}, from the co-visit counts.

    RAW CO-VISIT COUNTS ARE A POPULARITY RANKING IN DISGUISE -- Cancun
    co-occurs with everything because Cancun occurs with everything -- so
    they are normalised by how often each destination appears at all:

        cosine   co(a,b) / sqrt(users(a) * users(b))          (DEFAULT)
        jaccard  co(a,b) / (users(a) + users(b) - co(a,b))

    Cosine is the default because it penalises the popular column less
    harshly than Jaccard and this catalog's long tail is already thin.

    Both are then SHRUNK by co / (co + shrinkage) -- see ITEM_SHRINKAGE for
    why that is not optional here."""
    pairs = co_visit_counts(user_item)
    per_item = Counter()
    for items in user_item.by_user.values():
        for key in items:
            per_item[key] += 1

    sim = defaultdict(dict)
    for (a, b), count in pairs.items():
        if metric == "jaccard":
            denom = per_item[a] + per_item[b] - count
            value = count / denom if denom else 0.0
        else:
            denom = math.sqrt(per_item[a] * per_item[b])
            value = count / denom if denom else 0.0
        # Shrink toward zero by how many people actually support the pair.
        value *= count / (count + shrinkage)
        if value > 0:
            sim[a][b] = value
            sim[b][a] = value
    return sim


def item_item_recommend(data, traveler_id, top_n=TOP_N, sim=None,
                        metric=ITEM_METRIC, exclude_visited=True, history=None):
    """Item-item kNN. The better bet of the two, and the measurements agree.

    score(candidate) = sum over the traveler's own destinations of
                       similarity(visited, candidate) * confidence(u, visited)

    WHY THIS ONE DEGRADES BETTER. Item neighbourhoods are computed over all
    263 travelers at once, so a destination with 40 visitors has 40
    observations behind its row while a traveler with 4 trips has 4. And one
    visited destination is enough to produce a ranking, where user-user
    needs an overlap a 1-trip traveler does not have.

    `history` overrides which of the traveler's destinations to reason from
    -- the evaluation passes TRAIN-only history so the held-out destination
    cannot vote for itself."""
    if sim is None:
        sim = item_similarity(data.user_item, metric)
    row = data.user_item.by_user.get(traveler_id, {})
    if history is not None:
        row = {k: v for k, v in row.items() if k in history}
    if not row:
        return []
    visited = set(data.user_item.items_for(traveler_id)) if exclude_visited else set()

    scores, because = defaultdict(float), defaultdict(list)
    for source, confidence in row.items():
        for other, weight in sim.get(source, {}).items():
            if other in visited or other in row:
                continue
            scores[other] += weight * confidence
            because[other].append((source, weight * confidence))

    # How many distinct travelers stand behind each destination -- the
    # tie-break. Ties are common here (see ITEM_SHRINKAGE) and breaking them
    # on the destination key sorts the alphabet; breaking them on evidence
    # puts the better-supported candidate first, which is what a reader
    # would assume the order already meant.
    travelers_per_item = Counter()
    for items in user_item_rows(data).values():
        for key in items:
            travelers_per_item[key] += 1

    scored = [{
        "destination_key": key,
        "score": value,
        "support": len(because[key]),
        "travelers": travelers_per_item.get(key, 0),
        "because": [s for s, _ in sorted(because[key], key=lambda r: -r[1])[:3]],
    } for key, value in scores.items()]
    scored.sort(key=lambda r: (-r["score"], -r["support"], -r["travelers"],
                               r["destination_key"]))
    return scored if top_n is None else scored[:top_n]


# ---------------------------------------------------------------------------
# implicit ALS
# ---------------------------------------------------------------------------

def _solve(matrix, vector):
    """Gaussian elimination with partial pivoting, for the f x f system ALS
    solves once per user and once per item. f is 8 here, so a dependency on
    numpy to invert an 8x8 would be the tail wagging the dog -- and nothing
    else in data/scripts/ imports numpy either."""
    n = len(vector)
    a = [row[:] + [vector[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            continue
        a[col], a[pivot] = a[pivot], a[col]
        inv = 1.0 / a[col][col]
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col] * inv
            if factor:
                for j in range(col, n + 1):
                    a[row][j] -= factor * a[col][j]
    return [a[i][n] / a[i][i] if abs(a[i][i]) > 1e-12 else 0.0 for i in range(n)]


def matrix_factorisation(data, factors=ALS_FACTORS, iterations=ALS_ITERATIONS,
                         regularisation=ALS_REGULARISATION, seed=7):
    """Implicit ALS (Hu, Koren & Volinsky 2008) -- the version that is correct
    for data with no negatives.

        P = binary preference (1 where visited)
        C = confidence, c = 1 + ALPHA * ln(1 + visits), already built by
            rec_sys_data_prep

        x_u = (Y' Cu Y + lambda I)^-1 Y' Cu p_u
        y_i = (X' Ci X + lambda I)^-1 X' Ci p_i

    The sum runs over ALL cells, not just the observed ones -- that is the
    whole trick. Unvisited cells enter with preference 0 and confidence 1,
    i.e. "probably not, weakly", which is the honest reading of an implicit
    zero. It is computed the standard cheap way: Y'Y once per iteration,
    then Y'(Cu - I)Y accumulated over the user's own items only.

    SIZED HONESTLY. 263 x 224 with ~840 interactions supports very few
    factors before it is memorising; ALS_FACTORS is 8 and raising it is
    fitting the authored cohorts, not learning taste. --evaluate reports it
    beside the others precisely so that claim stays checkable rather than
    becoming folklore. Deterministic: the init is a seeded PRNG, so two runs
    give the same model."""
    rng = random.Random(seed)
    users = list(data.user_item.user_ids)
    items = list(data.user_item.item_ids)
    ui = {u: i for i, u in enumerate(users)}
    ii = {k: i for i, k in enumerate(items)}

    X = [[rng.gauss(0, 0.01) for _ in range(factors)] for _ in users]
    Y = [[rng.gauss(0, 0.01) for _ in range(factors)] for _ in items]

    by_user = {u: [(ii[k], c) for k, c in row.items() if k in ii]
               for u, row in data.user_item.by_user.items()}
    by_item = defaultdict(list)
    for u, row in by_user.items():
        for j, c in row:
            by_item[j].append((ui[u], c))

    def gram(matrix):
        g = [[0.0] * factors for _ in range(factors)]
        for row in matrix:
            for a in range(factors):
                ra = row[a]
                if not ra:
                    continue
                for b in range(factors):
                    g[a][b] += ra * row[b]
        return g

    def step(source, target, links, index):
        base = gram(source)
        for key, rows in links.items():
            t = index(key)
            if t is None:
                continue
            A = [[base[a][b] + (regularisation if a == b else 0.0)
                  for b in range(factors)] for a in range(factors)]
            rhs = [0.0] * factors
            for other, confidence in rows:
                vec = source[other]
                extra = confidence - 1.0
                for a in range(factors):
                    va = vec[a]
                    if extra:
                        for b in range(factors):
                            A[a][b] += extra * va * vec[b]
                    rhs[a] += confidence * va
            target[t] = _solve(A, rhs)

    for _ in range(iterations):
        step(Y, X, {u: rows for u, rows in by_user.items()}, lambda u: ui.get(u))
        step(X, Y, dict(by_item), lambda j: j)

    return {"users": users, "items": items, "user_factors": X, "item_factors": Y,
            "factors": factors, "iterations": iterations,
            "regularisation": regularisation}


def als_recommend(data, traveler_id, model, top_n=TOP_N, exclude_visited=True,
                  history=None):
    """Rank by the dot product of the learned factors."""
    if traveler_id not in model["users"]:
        return []
    x = model["user_factors"][model["users"].index(traveler_id)]
    skip = set(data.user_item.items_for(traveler_id)) if exclude_visited else set()
    if history is not None:
        skip = set(history)
    scored = [{"destination_key": key,
               "score": sum(x[f] * model["item_factors"][j][f] for f in range(model["factors"])),
               "support": 0, "because": []}
              for j, key in enumerate(model["items"]) if key not in skip]
    scored.sort(key=lambda r: (-r["score"], r["destination_key"]))
    return scored if top_n is None else scored[:top_n]


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def evaluate(data, top_n=TOP_N):
    """Leave-last-out, every collaborative variant beside the baseline.

    THE SPLIT BY AUTHORED VS KAGGLE IS THE POINT, not a nicety. The
    hand-authored travelers were built in cohorts that share itineraries by
    construction, so a neighbourhood model will rediscover those cohorts and
    look accurate while having learned build_synthetic_trips.py rather than
    travel behaviour. If it only works on the authored ones, it does not
    work.

    COVERAGE IS REPORTED FOR THE SAME REASON. A model that recommends Cancun
    to 263 people has a hit-rate and no value.

    WHAT THIS CAN AND CANNOT SETTLE: offline hit-rate on mostly synthetic
    travelers measures whether the model reproduces the generator. It is a
    regression test, not evidence that a recommendation is good. Nothing
    here should be described as accuracy outside this file."""
    train_seen = defaultdict(set)
    for row in data.split["train"]:
        train_seen[row["traveler_id"]].add(row["destination_key"])

    popularity = Counter()
    for row in data.split["train"]:
        popularity[row["destination_key"]] += 1

    idf = idf_weights(data.user_item)
    sim = item_similarity(data.user_item)
    als = matrix_factorisation(data)

    def ranked_for(name, traveler_id, seen):
        if name == "item_item":
            rows = item_item_recommend(data, traveler_id, top_n=None, sim=sim,
                                       exclude_visited=False, history=seen)
        elif name == "user_user":
            rows = user_user_recommend(data, traveler_id, top_n=None, idf=idf,
                                       exclude_visited=False)
        elif name == "als":
            rows = als_recommend(data, traveler_id, als, top_n=None,
                                 exclude_visited=False, history=seen)
        else:
            return [k for k, _ in popularity.most_common() if k not in seen]
        return [r["destination_key"] for r in rows if r["destination_key"] not in seen]

    names = ("item_item", "user_user", "als", "popularity")
    ranks = {n: [] for n in names}
    by_source = {n: {"authored": [], "kaggle": []} for n in names}
    coverage = {n: set() for n in names}

    for case in data.split["test"]:
        traveler_id, target = case["traveler_id"], case["destination_key"]
        seen = train_seen[traveler_id]
        bucket = "authored" if data.traveler(traveler_id).get("synthetic") else "kaggle"
        for name in names:
            order = ranked_for(name, traveler_id, seen)
            coverage[name].update(order[:top_n])
            rank = order.index(target) + 1 if target in order else None
            ranks[name].append(rank)
            by_source[name][bucket].append(rank)

    def score(values):
        if not values:
            return {"n": 0, "hit_rate": 0.0, "mrr": 0.0}
        return {"n": len(values),
                "hit_rate": sum(1 for r in values if r and r <= top_n) / len(values),
                "mrr": sum(1 / r for r in values if r) / len(values)}

    return {
        "top_n": top_n,
        "models": {n: {"overall": score(ranks[n]),
                       "authored": score(by_source[n]["authored"]),
                       "kaggle": score(by_source[n]["kaggle"]),
                       "coverage": len(coverage[n])} for n in names},
        "catalog_size": len(data.destinations),
        "als": {"factors": als["factors"], "iterations": als["iterations"]},
    }


def print_evaluation(result):
    print(f"COLLABORATIVE FILTERING -- leave-last-out evaluation, top-{result['top_n']}")
    print()
    print(f"  {'model':14} {'n':>4} {'hit@' + str(result['top_n']):>8} {'MRR':>8} {'coverage':>10}")
    for name, row in result["models"].items():
        o = row["overall"]
        print(f"  {name:14} {o['n']:4} {o['hit_rate']:8.3f} {o['mrr']:8.3f} "
              f"{row['coverage']:6} /{result['catalog_size']:4}")
    print()
    print("  split by where the traveler came from -- a model that only works on the")
    print("  authored cohorts has learned the generator, not travel behaviour")
    print(f"  {'model':14} {'authored hit':>13} {'kaggle hit':>12} {'kaggle n':>9}")
    for name, row in result["models"].items():
        print(f"  {name:14} {row['authored']['hit_rate']:13.3f} "
              f"{row['kaggle']['hit_rate']:12.3f} {row['kaggle']['n']:9}")


def main():
    parser = argparse.ArgumentParser(description="Collaborative filtering.")
    parser.add_argument("--traveler", default=DEFAULT_TRAVELER)
    parser.add_argument("--neighbours", type=int, default=DEFAULT_NEIGHBOURS)
    parser.add_argument("--recommend", action="store_true",
                        help="print item-item and user-user rankings for this traveler")
    parser.add_argument("--evaluate", action="store_true",
                        help="leave-last-out for all three variants plus popularity")
    args = parser.parse_args()

    data = prepare()
    if args.evaluate:
        print_evaluation(evaluate(data))
        return
    if args.recommend:
        profile = data.traveler(args.traveler)
        print(f"COLLABORATIVE -- {profile['name']} ({args.traveler})")
        for label, rows in (
            ("item-item", item_item_recommend(data, args.traveler)),
            ("user-user", user_user_recommend(data, args.traveler, k=args.neighbours)),
        ):
            print()
            print(f"  {label}")
            if not rows:
                print("    nothing -- no usable neighbourhood for this traveler")
            for rank, pick in enumerate(rows[:5], start=1):
                why = ", ".join(b.split("|")[0] for b in pick["because"])
                print(f"    {rank:2}. {pick['destination_key']:32} {pick['score']:9.4f}"
                      f"   because {why}")
        return
    readiness_report(data, args.traveler, neighbours=args.neighbours)


if __name__ == "__main__":
    main()
