"""
Derived from: rec_sys_data_prep.py (which is where all the real work lives)

CONTENT-BASED FILTERING -- recommend a destination because it RESEMBLES the
destinations this traveler already chose. No other traveler is consulted.

    "You have been to Lisbon, Porto and Barcelona, all high-Michelin,
     high-weather, Southern Europe. Here is Valencia."

IMPLEMENTED 2026-09-05. The DATA PREPARATION section loads the prepared
tables, builds this traveler's taste vector in destination-feature space and
reports what the model is handed; the MODEL section ranks with it. The
ordering was deliberate -- the inputs were made provably right first, and
the readiness report is still the thing to read when a recommendation looks
wrong, because the fix is almost always upstream in rec_sys_data_prep.py.

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
import math
from collections import Counter, defaultdict

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

# Cap per M49 detailed region in a returned list. Two, because without a
# cap every list here is Southern Europe and the Caribbean -- that is
# where the trips are -- and one would throw away real signal for a
# traveler whose history genuinely is one region.
MAX_PER_REGION = 2


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
    top = recommend(data, traveler_id, top_n=3)
    print("  what recommend() returns for them right now")
    for pick in top:
        print(f"    {pick['destination_key']:34} {pick['score']:.4f}  "
              f"{pick['shared_features']:3} shared")


# ===========================================================================
# MODEL -- implemented 2026-09-05.
# ===========================================================================
#
# Everything below used to be pseudocode. The decisions the pseudocode argued
# for are the decisions that got built; where a docstring offered a choice,
# the one taken is named and the reason is kept.

def feature_weights(item_features, groups=("content", "season", "geography", "popularity")):
    """Per-column weight = how much that column actually SEPARATES destinations.

    THE PROBLEM THIS SOLVES, which the pseudocode flagged and left open: an
    unweighted cosine gives `log_trips` the same vote as `ski_share`, and
    every destination in this catalog scores high on the undifferentiated
    columns. The result is a similarity that says "both are cities".

    The weight is the standard deviation of the column's OBSERVED values,
    normalised so the mean weight is 1.0. Observed only -- imputed cells all
    sit at the column mean, so counting them would shrink the variance of
    exactly the columns with the least evidence and quietly promote them.

    Measured on this catalog: ski_share and the region one-hots come out
    heaviest, log_trips and median_duration_days lightest, which is the
    intended direction."""
    weights = []
    wanted = set(item_features.names_in_groups(*groups))
    for j, name in enumerate(item_features.names):
        if name not in wanted:
            weights.append(0.0)
            continue
        observed = [item_features.rows[i][j]
                    for i in range(len(item_features.rows)) if item_features.mask[i][j]]
        if len(observed) < 2:
            weights.append(0.0)
            continue
        mean = sum(observed) / len(observed)
        var = sum((v - mean) ** 2 for v in observed) / (len(observed) - 1)
        weights.append(math.sqrt(var))
    live = [w for w in weights if w > 0]
    scale = (sum(live) / len(live)) if live else 1.0
    return [w / scale if scale else 0.0 for w in weights]


def masked_cosine(profile_vector, item_row, item_mask, weights=None):
    """Cosine similarity over observed coordinates only.

    Returns (score, overlap) -- and returns the overlap ALWAYS, because a
    0.98 computed over three shared features is not the same fact as a 0.98
    over forty, and a ranked list that mixes them is lying about its
    confidence.

    Below MIN_SHARED_FEATURES the score is None, not 0.0. Unknown is not
    dissimilar; a candidate we cannot compare has to be excluded by the
    caller, not ranked last."""
    shared = [j for j, value in enumerate(profile_vector)
              if value is not None and item_mask[j]
              and (weights is None or weights[j] > 0)]
    if len(shared) < MIN_SHARED_FEATURES:
        return None, len(shared)

    if weights is None:
        dot = sum(profile_vector[j] * item_row[j] for j in shared)
        n1 = math.sqrt(sum(profile_vector[j] ** 2 for j in shared))
        n2 = math.sqrt(sum(item_row[j] ** 2 for j in shared))
    else:
        dot = sum(weights[j] ** 2 * profile_vector[j] * item_row[j] for j in shared)
        n1 = math.sqrt(sum((weights[j] * profile_vector[j]) ** 2 for j in shared))
        n2 = math.sqrt(sum((weights[j] * item_row[j]) ** 2 for j in shared))
    if not n1 or not n2:
        return None, len(shared)
    return dot / (n1 * n2), len(shared)


def seasonal_fit(destination, month):
    """How good this destination is in `month`, as a 0-1 ranking multiplier.

    A MULTIPLIER, NOT A FEATURE, and the distinction is the whole reason the
    site has its name. The twelve weather columns are already in the vector,
    so cosine prefers places whose ANNUAL SHAPE matches where this traveler
    goes -- that answers "would they like this place". It does not answer
    "should they go in March". Keeping the target month out at scoring time
    and applying it here lets one profile serve twelve answers.

    NO CURVE MULTIPLIES BY 1.0, NEVER 0. 59 of 222 destinations have no
    weather normals; zeroing them would delete a quarter of the catalog on
    the strength of a missing file."""
    if not month:
        return 1.0
    curve = destination.get("weather_by_month")
    if not curve:
        return 1.0
    value = curve.get(month.lower())
    if value is None:
        return 1.0
    return max(0.0, min(1.0, value / 10.0))


def _raw_contributions(profile_vector, item_row, item_mask, names, weights):
    """Every coordinate's weighted product, i.e. what actually entered the
    dot product. What the reader is told has to be what the model used."""
    out = {}
    for j, value in enumerate(profile_vector):
        if value is None or not item_mask[j] or weights[j] <= 0:
            continue
        out[names[j]] = (weights[j] ** 2) * value * item_row[j]
    return out


def _distinctive(contributions, baseline, limit=3):
    """The coordinates that separate THIS candidate from the rest of the list.

    RANKED BY EXCESS OVER THE POOL MEAN, not by absolute size, and that is a
    correction to what the pseudocode originally asked for. Ranking by the
    raw dot-product term produced a real but useless explanation: for a
    high-Michelin traveler, `michelin_score` is the largest term for EVERY
    candidate, so all ten rows came back saying "the Michelin coverage they
    travel for". True of each, and no help choosing between them.

    Subtracting each feature's mean contribution across the scored pool
    turns "why did this rank at all" into "why did this rank HERE", which is
    the question a person reading a list of ten is actually asking."""
    ranked = sorted(
        ((name, value, value - baseline.get(name, 0.0))
         for name, value in contributions.items()),
        key=lambda row: -row[2],
    )
    return [(name, value) for name, value, _excess in ranked[:limit]]


def _diversify(scored, data, per_region=MAX_PER_REGION):
    """Cap the list at `per_region` per M49 detailed region, order preserved.

    Without this every list is Southern Europe and the Caribbean, because
    that is where the trips are. Ten Southern European cities is a ranking,
    not a recommendation. Destinations with no region are never capped --
    unknown is not a bucket."""
    kept, seen = [], Counter()
    for row in scored:
        region = data.destination(row["destination_key"]).get("detailed_region")
        if region:
            if seen[region] >= per_region:
                continue
            seen[region] += 1
        kept.append(row)
    return kept


def recommend(data, traveler_id, top_n=TOP_N, month=None, profiles=None,
              exclude_visited=True, diversify=True, weights=None):
    """Rank the candidate pool by similarity to the traveler's taste vector.

    Returns a list of dicts, best first, each carrying the score, the
    shared-feature count it rests on, and the coordinates that produced it.
    `top_n=None` returns the whole ranked pool, which is what the evaluation
    and the hybrid's rank fusion need.

    `exclude_visited=False` keeps the held-out destination in the pool for
    evaluation -- with it excluded there is nothing to find."""
    if profiles is None:
        profiles = build_user_content_profiles(data.user_item, data.item_features)
    vector = profiles.get(traveler_id)
    if vector is None:
        return []
    if weights is None:
        weights = feature_weights(data.item_features)

    index = {key: i for i, key in enumerate(data.item_features.ids)}
    names = data.item_features.names
    scored = []
    for dest in candidate_pool(data, traveler_id, exclude_visited=exclude_visited):
        key = dest["destination_key"]
        i = index.get(key)
        if i is None:
            continue
        row, mask = data.item_features.rows[i], data.item_features.mask[i]
        similarity, overlap = masked_cosine(vector, row, mask, weights)
        if similarity is None:
            continue
        season = seasonal_fit(dest, month)
        scored.append({
            "destination_key": key,
            "score": similarity * season,
            "similarity": similarity,
            "seasonal_multiplier": season,
            "shared_features": overlap,
            "_raw_contributions": _raw_contributions(vector, row, mask, names, weights),
            "content_cold": not dest["matched"],
        })

    # The pool mean per feature, so an explanation can say what makes each
    # candidate different rather than repeating the traveler's strongest
    # taste on every row. See _distinctive().
    totals, counts = defaultdict(float), Counter()
    for row in scored:
        for name, value in row["_raw_contributions"].items():
            totals[name] += value
            counts[name] += 1
    baseline = {name: totals[name] / counts[name] for name in totals}
    for row in scored:
        row["contributions"] = _distinctive(row.pop("_raw_contributions"), baseline)

    scored.sort(key=lambda r: (-r["score"], r["destination_key"]))
    if diversify:
        scored = _diversify(scored, data)
    return scored if top_n is None else scored[:top_n]


def nearest_visited(data, traveler_id, destination_key, weights=None):
    """The traveler's OWN destination most like this candidate.

    The anchor an explanation should cite. "Closest to your Lisbon trips" is
    checkable by the person reading it; "cosine 0.94" is not."""
    if weights is None:
        weights = feature_weights(data.item_features)
    index = {key: i for i, key in enumerate(data.item_features.ids)}
    target = index.get(destination_key)
    if target is None:
        return None
    row, mask = data.item_features.rows[target], data.item_features.mask[target]
    best, best_score = None, None
    for visited in sorted(data.user_item.items_for(traveler_id)):
        i = index.get(visited)
        if i is None:
            continue
        other = [v if data.item_features.mask[i][j] else None
                 for j, v in enumerate(data.item_features.rows[i])]
        score, _ = masked_cosine(other, row, mask, weights)
        if score is not None and (best_score is None or score > best_score):
            best, best_score = visited, score
    return best


def _feature_phrase(name, data, traveler_id):
    """One feature name, in words a trip card can hold."""
    if name.startswith("weather_"):
        return f"{name.split('_', 1)[1].capitalize()} weather like the places they go"
    if name.startswith("region_"):
        region = name.split("_", 1)[1]
        visited = data.user_item.items_for(traveler_id)
        # detailed_region, NOT region. The one-hot block is built from the M49
        # DETAILED regions (build_item_feature_matrix takes detailed_regions),
        # so "Southern Europe" is a detailed_region value and never matches
        # the broad `region` field -- comparing against `region` made this
        # count 0 for every traveler and silently dropped the clause.
        here = sum(1 for key in visited
                   if (data.destination(key).get("detailed_region") == region))
        if not here:
            return f"in {region}"
        # Each of these has to stand alone as a bullet on a card, so the
        # clause cannot dangle. Singular matters at this size: 160 travelers
        # have been to exactly one destination, so "1 of their 1 destinations
        # are" was the common case rather than the edge one.
        if here == len(visited):
            return f"in {region}, the only region they have travelled to"
        return f"in {region}, where {here} of their {len(visited)} destinations are"
    return {
        "unesco_score": "as much UNESCO heritage as the places they choose",
        "michelin_score": "the Michelin coverage they travel for",
        "allocentric_score": "off the beaten track, the way they travel",
        "beach_share": "the kind of beach trip they take",
        "ski_share": "a ski destination, like their winter trips",
        "holiday_share": "the kind of place they go for holidays",
        "median_duration_days": "trips the length they take",
        "median_accommodation_cost": "lodging in their range",
        "median_transportation_cost": "flights in their range",
        "log_trips": "somewhere well travelled",
        "log_travelers": "somewhere many travelers go",
    }.get(name, name.replace("_", " "))


def explain(data, traveler_id, destination_key, pick=None, weights=None, limit=3):
    """Why this destination, in short checkable sentences.

    The top contributing coordinates, translated, plus the traveler's own
    most similar destination as the anchor. An explanation that cites the
    user's own history can be checked by the user; one that cites a cosine
    cannot."""
    if pick is None:
        ranked = recommend(data, traveler_id, top_n=None, weights=weights, diversify=False)
        pick = next((r for r in ranked if r["destination_key"] == destination_key), None)
    if pick is None:
        return []

    reasons = []
    anchor = nearest_visited(data, traveler_id, destination_key, weights)
    if anchor:
        reasons.append(f"Closest to their {anchor.split('|')[0]} trips")
    for name, _ in pick["contributions"][:limit]:
        phrase = _feature_phrase(name, data, traveler_id)
        # NOT str.capitalize() -- it lowercases the rest of the string, which
        # turned "the Michelin coverage they travel for" into "michelin".
        reasons.append(phrase[:1].upper() + phrase[1:])
    if pick.get("content_cold"):
        reasons.append("Ranked on popularity and trip patterns only -- no city record for it")
    elif pick["shared_features"] < MIN_SHARED_FEATURES + 4:
        reasons.append(f"Based on only {pick['shared_features']} shared features")
    return reasons[:limit + 1]


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------

def evaluate(data, top_n=TOP_N, weights=None):
    """Leave-last-out hit-rate and MRR, against the baselines that matter.

    THE BASELINE IS REPORTED EVERY TIME AND NEVER ALONE. A content model
    that cannot beat most-popular on this dataset is measuring popularity
    through a longer pipe, and the only way to notice is to print both.

    Profiles are rebuilt from TRAIN interactions only. The held-out
    destination stays IN the candidate pool, or there is nothing to find."""
    profiles = build_user_content_profiles(data.user_item, data.item_features,
                                           split=data.split)
    if weights is None:
        weights = feature_weights(data.item_features)
    train_seen = defaultdict(set)
    for row in data.split["train"]:
        train_seen[row["traveler_id"]].add(row["destination_key"])

    popularity = Counter()
    for row in data.split["train"]:
        popularity[row["destination_key"]] += 1

    results = {"model": [], "popularity": []}
    authored = {"model": [], "popularity": []}
    kaggle = {"model": [], "popularity": []}
    recommended_items = set()

    for case in data.split["test"]:
        traveler_id, target = case["traveler_id"], case["destination_key"]
        seen = train_seen[traveler_id]

        ranked = [r["destination_key"] for r in recommend(
            data, traveler_id, top_n=None, profiles=profiles,
            exclude_visited=False, diversify=False, weights=weights)
            if r["destination_key"] not in seen]
        recommended_items.update(ranked[:top_n])
        model_rank = ranked.index(target) + 1 if target in ranked else None

        pop_ranked = [key for key, _ in popularity.most_common() if key not in seen]
        pop_rank = pop_ranked.index(target) + 1 if target in pop_ranked else None

        results["model"].append(model_rank)
        results["popularity"].append(pop_rank)
        bucket = authored if data.traveler(traveler_id).get("synthetic") else kaggle
        bucket["model"].append(model_rank)
        bucket["popularity"].append(pop_rank)

    def score(ranks):
        if not ranks:
            return {"n": 0, "hit_rate": 0.0, "mrr": 0.0}
        return {
            "n": len(ranks),
            "hit_rate": sum(1 for r in ranks if r and r <= top_n) / len(ranks),
            "mrr": sum(1 / r for r in ranks if r) / len(ranks),
        }

    return {
        "top_n": top_n,
        "overall": {"model": score(results["model"]),
                    "popularity": score(results["popularity"])},
        "authored": {"model": score(authored["model"]),
                     "popularity": score(authored["popularity"])},
        "kaggle": {"model": score(kaggle["model"]),
                   "popularity": score(kaggle["popularity"])},
        # A model that recommends Cancun to 263 people has a hit-rate and no
        # value. This is the number that catches that.
        "catalog_coverage": len(recommended_items),
        "catalog_size": len(data.destinations),
    }


def print_evaluation(result, label="CONTENT-BASED"):
    print(f"{label} -- leave-last-out evaluation, top-{result['top_n']}")
    print()
    print(f"  {'':10} {'n':>5} {'hit@' + str(result['top_n']):>8} {'MRR':>8}"
          f"   {'hit (pop)':>10} {'MRR (pop)':>10}")
    for group in ("overall", "authored", "kaggle"):
        m, p = result[group]["model"], result[group]["popularity"]
        print(f"  {group:10} {m['n']:5} {m['hit_rate']:8.3f} {m['mrr']:8.3f}"
              f"   {p['hit_rate']:10.3f} {p['mrr']:10.3f}")
    print()
    print(f"  catalog coverage {result['catalog_coverage']} of {result['catalog_size']} "
          f"destinations appear in some traveler's top-{result['top_n']}")


def main():
    parser = argparse.ArgumentParser(description="Content-based filtering.")
    parser.add_argument("--traveler", default=DEFAULT_TRAVELER)
    parser.add_argument("--holdout", action="store_true",
                        help="build the taste profile from TRAIN interactions only")
    parser.add_argument("--month", default=None,
                        help="apply the seasonal multiplier for this month (e.g. march)")
    parser.add_argument("--recommend", action="store_true",
                        help="print a ranked list with explanations instead of the report")
    parser.add_argument("--evaluate", action="store_true",
                        help="leave-last-out hit-rate and MRR against the popularity baseline")
    args = parser.parse_args()

    data = prepare()
    if args.evaluate:
        print_evaluation(evaluate(data))
        return
    if args.recommend:
        weights = feature_weights(data.item_features)
        profile = data.traveler(args.traveler)
        picks = recommend(data, args.traveler, month=args.month, weights=weights)
        month = f" for {args.month}" if args.month else ""
        print(f"CONTENT-BASED -- {profile['name']} ({args.traveler}){month}")
        print()
        for rank, pick in enumerate(picks, start=1):
            print(f"  {rank:2}. {pick['destination_key']:34} {pick['score']:.4f}"
                  f"   {pick['shared_features']:3} shared features")
            for reason in explain(data, args.traveler, pick["destination_key"],
                                  pick=pick, weights=weights):
                print(f"        - {reason}")
        return
    readiness_report(data, args.traveler, holdout=args.holdout)


if __name__ == "__main__":
    main()
