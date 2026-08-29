// Travelers and their trips, from the backend's /api/travelers routes (see
// backend/app/main.py). The underlying data is a small Kaggle sample dataset
// -- see data/scripts/multiple/build_travelers.py -- and is generated, not
// committed, so "the dataset isn't here" is a normal state this module models
// explicitly rather than treating as an error.
import { useEffect, useState } from "react";
import { API_BASE_URL } from "./apiBaseUrl";

// Mirrors backend/app/main.py's TravelerTrip. Every cost, date and duration
// comes in two forms: parsed (for future scoring/sorting) and raw (the
// original string from the source). The UI shows the raw one -- costs in this
// dataset are display strings with no currency column, so rendering the
// number alone would silently turn "£900" into "900".
export interface TravelerTrip {
  trip_id: string | null;
  // The source's single free-text destination string, and the hand-resolved
  // split of it (see data/scripts/multiple/build_trips_enhanced.py). Raw is
  // kept so the page can fall back to exactly what the source said if the
  // split ever comes through empty.
  destination_raw: string;
  destination_city: string | null; // null only when destination_kind is "country"
  destination_country: string;
  destination_country_code: string; // ISO 3166-1 alpha-2
  destination_kind: string; // "city" | "region" | "country"
  start_date: string | null; // ISO, null when the source value didn't parse
  start_date_raw: string | null;
  end_date: string | null;
  end_date_raw: string | null;
  duration_days: number | null;
  duration_raw: string | null;
  accommodation_type: string | null;
  accommodation_cost: number | null;
  accommodation_cost_raw: string | null;
  transportation_type: string | null;
  transportation_cost: number | null;
  transportation_cost_raw: string | null;
  // Hand-authored trips only (see build_synthetic_trips.py): their
  // itineraries are built on real airline routes, so they carry the carrier
  // and the airport pair. Null on every Kaggle-sourced trip.
  synthetic?: boolean;
  carrier_name?: string | null;
  origin_airport?: string | null;
  destination_airport?: string | null;
  // True for a leg that's part of a longer journey but wasn't its point --
  // Atlanta and Paris on a Houston-to-Lisbon trip, say (see
  // data/scripts/multiple/chef_traveler.py). Always false/undefined outside
  // a hand-kept flight log. Consumers that count "trips" or "destinations"
  // (the Trips list, the airline/region share charts) should filter it out;
  // it stays in this list because the underlying itinerary is real.
  layover?: boolean;
  // Computed labels on THIS trip, from data/scripts/multiple/classify_trip.py
  // (run over every trip by build_trips_enhanced.py). Same shape as
  // TravelerTag, deliberately: a chip is a chip wherever you meet it. The
  // difference is scope -- a TravelerTag describes a person's whole history
  // ("United Loyalist"), a TripTag describes one journey ("Ski Trip").
  //
  // Absent or empty for a trip with no destination airport or no parsed
  // dates -- the Kaggle rows have no airport, and tagging one would assert
  // something the source never said. Tags are NOT mutually exclusive: a trip
  // can carry several and is meant to.
  tags?: TripTag[];
  // UN M49 geography for this trip's destination country, joined on by the
  // API (see backend/app/data_loader.py's load_m49_regions and
  // data/scripts/multiple/build_m49_regions.py).
  //
  // Null is a real state, not an oversight: it means m49_regions.json hasn't
  // been built in the backend's checkout, or the destination country isn't
  // in M49. The charts drop those trips from their denominator rather than
  // showing an "Unknown" region -- same convention as a trip with no carrier.
  destination_region?: string | null;
  // M49's INTERMEDIATE region where the country has one, else its sub-region
  // -- 22 values. This is the tier that keeps Central America, the Caribbean
  // and South America apart rather than merging them into "Latin America and
  // the Caribbean", which on this dataset would be most of the bar.
  destination_subregion?: string | null;
  // This trip's DESTINATION CITY's scores, joined on by the API from
  // data/scripts/multiple/match_trip_cities.py's output (see
  // backend/app/main.py's _with_destination_scores).
  //
  // Null is a real, common state and is NOT zero. unesco_score /
  // michelin_score are null when the destination has no city record at all
  // -- Punta Cana, Montego Bay, Sarasota and other places below
  // tourist_cities.json's population cutoff. weather_score is null for
  // those too, AND for a matched city with no weather normals (only 1,770
  // of 3,069 cities have them), AND for a trip with no usable start date.
  //
  // A 0.00 that IS present means something specific: no World Heritage
  // site within the 50km scoring radius (true of 73 of the 138 cities in
  // this dataset, Tokyo included), or a country the MICHELIN Guide doesn't
  // publish in. Rendering a null as 0 would collapse those two apart
  // meanings into one.
  unesco_score?: number | null;
  michelin_score?: number | null;
  weather_score?: number | null;
}

// One destination score, ready to render. `title` carries the unrounded
// value and what it measures, since the card shows a rounded number and
// "UNESCO 0.0" invites exactly the wrong reading.
export interface TripDestinationScore {
  key: "unesco" | "michelin" | "weather";
  label: string;
  value: number;
  title: string;
}

const SCORE_TITLES: Record<TripDestinationScore["key"], string> = {
  unesco: "UNESCO World Heritage sites within 50km of the destination city, log-scaled to 0-10",
  michelin: "MICHELIN Guide restaurants within 50km of the destination city, log-scaled to 0-10",
  weather: "The destination city's weather normals scored 0-10, averaged over this trip's own dates",
};

// The scores to show on one trip card -- only the ones that are actually
// present, in a fixed order. An absent score is omitted rather than shown
// as a dash: about 1 trip in 7 has no city record at all, and a row of
// three dashes on those cards is noise, not information. The card's shape
// varying is the deliberate trade (Ivan's call), and it matches how this
// page already hides the entropy block when it's null.
export function tripDestinationScores(trip: TravelerTrip): TripDestinationScore[] {
  const raw: [TripDestinationScore["key"], string, number | null | undefined][] = [
    ["unesco", "UNESCO", trip.unesco_score],
    ["michelin", "Michelin", trip.michelin_score],
    ["weather", "Weather", trip.weather_score],
  ];
  return raw
    .filter(([, , value]) => typeof value === "number")
    .map(([key, label, value]) => ({
      key,
      label,
      value: value as number,
      title: `${SCORE_TITLES[key]}.`,
    }));
}

// TWO decimals, which is exactly the precision these scores are stored at
// -- so the card shows the stored number rather than a rounded stand-in.
//
// One decimal was tried first and rejected on sight: Tokyo's michelin_score
// is 9.99, and toFixed(1) renders that as "10.0", which reads as a capped
// or perfect score. Rounding that invents a value the data does not contain
// is worse than one extra character, and 0-10 scores at the top of the
// range are exactly where the rounding lands.
export function formatDestinationScore(value: number): string {
  return value.toFixed(2);
}

// Mirrors backend/app/main.py's TravelerTag. A computed label -- see
// data/scripts/multiple/compute_traveler_tags.py -- describing a pattern in
// the trips AS RECORDED, never something the itinerary's author declared.
//
// `denominator` is not the traveler's trip_count. For an airline_loyalist tag
// it counts only trips that record a carrier, which is the same denominator
// the "Airlines flown" chart uses, so a 100% bar and a Loyalist chip can't
// contradict each other on the same page.
export interface TripTag {
  // "ski-trip", "beach-vacation" -- stable, and what React keys off.
  tag_id: string;
  // The classifier that produced it, e.g. "ski_trip". Branch on this rather
  // than parsing `label`.
  kind: string;
  // What the chip says, e.g. "Ski Trip".
  label: string;
}

export interface TravelerTag {
  // "airline-loyalist:delta-air-lines-inc" -- stable, built from the full
  // legal carrier name.
  tag_id: string;
  // The rule that produced it, e.g. "airline_loyalist". Branch on this rather
  // than parsing `label`, so a second rule can be styled differently without
  // touching the first.
  kind: string;
  // What the chip says, e.g. "Delta Loyalist" -- already shortened by the
  // script.
  label: string;
  // Rule-specific evidence, all optional: a future rule needn't involve an
  // airline, and only tag_id/kind/label are guaranteed.
  //
  // The ONE airline this tag is about, or null when it isn't about one --
  // "Multi Hub" leaves it null rather than naming the first of its airlines.
  carrier_name?: string | null;
  // Every airline the chip draws a dot for, as full legal names (which is
  // what airlineColors.ts is keyed on): one entry for a loyalist or
  // single-airline hub tag, several for Multi Hub.
  carrier_names?: string[] | null;
  // The same airlines shortened ("United", "American"), for wording.
  airlines?: string[] | null;
  // airline_loyalist evidence.
  share?: number | null;
  trips?: number | null;
  denominator?: number | null;
  // airline_hub / multi_hub: the home city that earned the tag, and the hub
  // airports in it. The CITY is what was matched -- every New Yorker is
  // Multi Hub whether they fly EWR, JFK or LGA -- so the airports are
  // context in the tooltip, not the thing the rule keyed on.
  hub_city?: string | null;
  hub_airports?: string[] | null;
}

export interface TravelerSummary {
  // build_travelers.py's slug, e.g. "john-smith-american" -- derived from the
  // name and nationality it grouped on, so the URL shows what decided that
  // this person is one person.
  traveler_id: string;
  name: string;
  nationality: string | null;
  // Inferred, not stated by the source: their nationality's country, and the
  // first plausible home city in it they didn't visit (see
  // data/scripts/multiple/build_travelers.py). base_inference says how it was
  // picked -- "primary", "avoided_visited", "visited_all_candidates" or
  // "unmapped" -- and is why the page labels this as an estimate.
  base_city?: string | null;
  base_country?: string | null;
  base_country_code?: string | null;
  base_inference?: string | null;
  gender: string | null;
  age: number | null;
  // [youngest, oldest] across their trips -- age is per-trip in the source.
  age_range: [number, number] | null;
  trip_count: number;
  destinations: string[];
  // Set only when the backend is serving travelers_anon.json, where each
  // sample name is replaced by a deceased author of the same nationality and
  // gender (see data/scripts/multiple/build_travelers_anon.py): how exact
  // that nationality match is. Provenance for inspecting the data, not
  // something the UI renders -- and absent entirely when the raw names are
  // being served.
  persona_match?: string | null;
  // Mirrors backend/app/main.py's REAL_PERSON_TRAVELER_IDS: true only for
  // the handful of travelers who are a real, named person (Anthony
  // Bourdain, Gordon Ramsay, Conan O'Brien, Rick Steves, Eduardo Gomez)
  // rather than a fictional persona or an anonymized Kaggle row. Distinct from the
  // backend's own `synthetic` field (not carried on this interface), which
  // means something narrower -- "not from the Kaggle CSV" -- and is true for
  // the 82 fictional hand-authored characters too. See
  // filterByTravelerType(). Optional only so an older cached response still
  // typechecks.
  real_person?: boolean;
  // Always an array, never null -- the API sends [] both for "no rule
  // matched" and for a checkout where compute_traveler_tags.py hasn't run.
  // Optional here only so an older cached response still typechecks.
  tags?: TravelerTag[];
  // Mirrors backend/app/main.py's TravelerSummary.region_entropy_normalized:
  // the same figure the traveler's own page shows as region entropy,
  // normalized over all 22 M49 detailed regions. Carried on the card so the
  // grid can be filtered on it without loading anyone's trips.
  //
  // null means NOT COMPUTED (the region entropy file isn't built in this
  // checkout), which the filter treats differently from a real 0 -- see
  // filterByEntropy().
  region_entropy_normalized?: number | null;
  // The full DestinationEntropy blocks -- BY AIRPORT and the RAW (non-
  // normalized) side of region -- that only the detail route sends (see
  // TravelerDetail below). Absent/undefined on a plain summary row; filled
  // in by useTravelersWithEntropy()'s per-traveler enrichment fetch once
  // /rec-sys needs to filter on one of those three metrics. Distinct from
  // `null`, which means the backend itself has no entropy for this
  // traveler -- same convention as everywhere else entropy appears.
  destination_entropy?: DestinationEntropy | null;
  region_entropy?: DestinationEntropy | null;
}

// The /rec-sys entropy filter: pick a metric (airport vs region, raw vs
// normalized), a comparator, and a threshold. Replaces the old region-only
// "at least" slider -- added so low-entropy travelers (the ones whose "next
// destination" is closer to a lookup than a prediction, see the loyalist-
// template discussion in the project) can be hand-inspected directly, at any
// of the four entropy figures the traveler detail page already computes,
// with any of the five comparisons, not just a minimum on one of them.
export type EntropyMetric = "airport" | "airport_normalized" | "region" | "region_normalized";
export type EntropyComparator = "gte" | "lte" | "gt" | "lt" | "eq";

export const ENTROPY_METRIC_OPTIONS: { value: EntropyMetric; label: string }[] = [
  { value: "airport", label: "Airport entropy" },
  { value: "airport_normalized", label: "Airport entropy (normalized)" },
  { value: "region", label: "Region entropy" },
  { value: "region_normalized", label: "Region entropy (normalized)" },
];

export const ENTROPY_COMPARATOR_OPTIONS: { value: EntropyComparator; label: string }[] = [
  { value: "gte", label: "≥" },
  { value: "lte", label: "≤" },
  { value: "gt", label: ">" },
  { value: "lt", label: "<" },
  { value: "eq", label: "=" },
];

// Comparators as data, not a switch buried inside the filter -- reused
// as-is by filterByEntropy below.
const ENTROPY_COMPARATORS: Record<EntropyComparator, (value: number, threshold: number) => boolean> = {
  gte: (v, t) => v >= t,
  lte: (v, t) => v <= t,
  gt: (v, t) => v > t,
  lt: (v, t) => v < t,
  // These are JSON floats, not values arithmetic was done on in JS, so exact
  // equality would usually be fine -- but a threshold TYPED by hand is
  // fuzzed to a tolerance far finer than these entropy values are ever
  // meaningfully distinguished at (the smallest digit the UI shows is
  // thousandths), rather than relying on that.
  eq: (v, t) => Math.abs(v - t) < 1e-6,
};

// One extractor per metric, so entropyMetricValue is a lookup rather than a
// branch. `airport` and the raw side of `region` only resolve once
// useTravelersWithEntropy() below has enriched the row from its detail route
// (see the two new fields on TravelerSummary) -- absent there reads as "not
// known yet", which filterByEntropy treats the same as "not computed" at
// all. `region_normalized` is the one metric with a fallback: it also reads
// `region_entropy_normalized`, which IS on the plain /api/travelers summary,
// so that metric alone keeps working before enrichment finishes.
const ENTROPY_EXTRACTORS: Record<EntropyMetric, (t: TravelerSummary) => number | null> = {
  airport: (t) => t.destination_entropy?.entropy ?? null,
  airport_normalized: (t) => t.destination_entropy?.normalized ?? null,
  region: (t) => t.region_entropy?.entropy ?? null,
  region_normalized: (t) => t.region_entropy?.normalized ?? t.region_entropy_normalized ?? null,
};

export function entropyMetricValue(traveler: TravelerSummary, metric: EntropyMetric): number | null {
  return ENTROPY_EXTRACTORS[metric](traveler);
}

// The /rec-sys traveler-type filter: real, named people (Bourdain, Ramsay,
// Conan, Rick Steves, Gomez -- see TravelerSummary.real_person) vs everyone
// else. "All"
// is the default and is never written to the URL, same convention as the
// multi-trip checkbox and the entropy filter above -- a plain /rec-sys link
// means "no traveler-type filter".
//
// "Synthetic" here means "not a real named person" -- it's the 82 fictional
// hand-authored characters AND the 124 Kaggle-derived rows alike, which is
// coarser than (and NOT the same set as) the backend's own `synthetic`
// field, which is true for the fictional characters too but false for the
// Kaggle rows.
export type TravelerTypeFilter = "all" | "real" | "synthetic";

export const TRAVELER_TYPE_OPTIONS: { value: TravelerTypeFilter; label: string }[] = [
  { value: "all", label: "Show all" },
  { value: "synthetic", label: "Show only synthetic travelers" },
  { value: "real", label: "Show only real travelers" },
];

export function filterByTravelerType(
  travelers: TravelerSummary[],
  type: TravelerTypeFilter,
): TravelerSummary[] {
  if (type === "all") return travelers;
  return travelers.filter((t) => (type === "real" ? t.real_person === true : t.real_person !== true));
}


// `metric: null` is the off position -- explicit, rather than overloading a
// threshold of zero the way the old region-only slider did, because zero is
// now a real, useful threshold to filter ON: "=" 0 is exactly the
// deterministic-destination travelers this filter was built to surface.
//
// A traveler whose value for this metric is null -- not yet enriched, or the
// backend genuinely has no entropy for them -- never satisfies any
// comparator, including "<". Unknown is not the same as low.
export function filterByEntropy(
  travelers: TravelerSummary[],
  metric: EntropyMetric | null,
  comparator: EntropyComparator,
  threshold: number,
): TravelerSummary[] {
  if (metric === null) return travelers;
  const test = ENTROPY_COMPARATORS[comparator];
  return travelers.filter((t) => {
    const value = entropyMetricValue(t, metric);
    return value !== null && test(value, threshold);
  });
}

// The observed range for one metric across a set of travelers -- shown next
// to the filter as a hint ("data ranges 0.000-4.372") rather than driving a
// slider's bounds the way the old control did: a typed number has no
// natural max the way a range input does, and a hint stays honest under any
// comparator, not just "at least". Null when nobody in the set has a value
// for this metric yet -- an un-enriched page load, or an un-run entropy
// script.
export function entropyMetricRange(
  travelers: TravelerSummary[],
  metric: EntropyMetric,
): { min: number; max: number } | null {
  const values = travelers
    .map((t) => entropyMetricValue(t, metric))
    .filter((v): v is number => typeof v === "number");
  if (values.length === 0) return null;
  return { min: Math.min(...values), max: Math.max(...values) };
}

// THREE decimals for every metric, normalized ones included. Not a cosmetic
// choice: it's the precision the filter's threshold input accepts, and the
// two have to agree. At 2 places a normalized range rendered "0.00-0.87"
// while the values behind it ran 0.001-0.8697, so a threshold typed at
// 0.007 -- a perfectly good query, and a discriminating one down where most
// of this dataset's travelers sit -- looked like it was outside the data.
// One function, one precision, so the range hint, the per-card value and
// what you can type into the box can't disagree.
const ENTROPY_DECIMALS = 3;

export function formatEntropyValue(value: number): string {
  return value.toFixed(ENTROPY_DECIMALS);
}

// The threshold input's `step`, matching ENTROPY_DECIMALS. A coarser step
// (0.01) makes the browser mark 0.007 as a step mismatch -- the value still
// reads, but the field renders as invalid, which is a confusing way to
// refuse a query the filter handles fine.
export const ENTROPY_STEP = 0.001;

// "United Air Lines Inc. · EWR - CDG" for a hand-authored trip, null for a
// Kaggle one (which records no airline at all). Shown as its own line on the
// trip card rather than folded into the transport line, which already carries
// the mode and the fare.
export function formatFlight(trip: TravelerTrip): string | null {
  const route = trip.origin_airport && trip.destination_airport
    ? `${trip.origin_airport} - ${trip.destination_airport}`
    : null;
  return [trip.carrier_name, route].filter(Boolean).join(" · ") || null;
}

// Mirrors backend/app/main.py's DestinationEntropy. How spread out this
// traveler's trips are across destination airports -- see
// data/scripts/multiple/compute_traveler_entropy.py.
//
// `entropy` being null is a real, common case (the 124 Kaggle-sourced
// travelers record no destination airport) and is NOT the same as 0. Zero
// means "every trip went to the same place", which is a finding; null means
// the source doesn't say. The UI has to render them differently, so this is
// `number | null`, never defaulted to 0.
export interface DestinationEntropy {
  entropy: number | null;
  // entropy / ln(global_distinct_destinations).
  normalized: number | null;
  n_destinations: number;
  trips_with_destination: number;
  // False when fewer than 2 trips carried a destination -- entropy from one
  // observation can only be 0 and says nothing about the traveler.
  is_informative: boolean;
  top_destination: string | null;
  top_destination_share: number | null;
  // The denominator behind `normalized`, sent by the API rather than
  // hardcoded here: it's a property of the whole dataset and changes whenever
  // the trip data does.
  global_distinct_destinations: number | null;
  destination_unit: string | null;
}

// Mirrors backend/app/main.py's TravelerPreferences: this traveler's
// DESTINATION PREFERENCE PROFILE, a rollup of the same per-trip UNESCO /
// Michelin / weather scores TravelerTrip already carries (see
// tripDestinationScores above), not a new score computed here. Three
// dimensions today -- the README TODO this implements names more (food,
// architecture, nightlife...) that need datasets this project doesn't have
// yet, so they're left for later.
//
// Each present dimension is the MEAN of that trip-level 0-10 score across
// every non-layover trip that has one, rescaled to 0-1. null, not 0, when no
// trip has a score for that dimension -- same "nothing invented" rule as
// unesco_score/michelin_score/weather_score on TravelerTrip. The *_trips
// count alongside each dimension is how many trips it was averaged over, so
// a profile drawn from one trip is inspectable rather than reading the same
// as one drawn from fifty.
export interface TravelerPreferences {
  unesco: number | null;
  michelin: number | null;
  weather: number | null;
  unesco_trips: number;
  michelin_trips: number;
  weather_trips: number;
}

export interface TravelerDetail extends TravelerSummary {
  trips: TravelerTrip[];
  // This traveler's destination preference profile (see
  // TravelerPreferences), computed server-side from the trips above.
  // Always an object, never null itself -- individual dimensions inside it
  // are null when no trip has that score. Optional only so an older cached
  // response still typechecks.
  preferences?: TravelerPreferences | null;
  // Null when compute_traveler_entropy.py hasn't been run in the backend's
  // checkout -- distinct from "computed, but unknown for this traveler".
  //
  // BY DESTINATION AIRPORT. `entropy` being null inside it is the common
  // case, not an error: 124 of 206 travelers record no airport at all.
  destination_entropy?: DestinationEntropy | null;
  // THE SAME MEASURE BY UN M49 DETAILED REGION -- a separate field, not a
  // variant, because the two are on different scales and answer different
  // questions: "does this person use different airports?" versus "does this
  // person visit different parts of the world?". A traveler can be high on
  // one and zero on the other, so the page shows both, labelled.
  //
  // Defined for every traveler, unlike the airport one: every trip records a
  // destination country and every country resolves to a region.
  region_entropy?: DestinationEntropy | null;
}

// What each unit is called in prose. The page shows two entropy blocks whose
// numbers are NOT comparable, so every sentence names its own unit -- "4
// airports" and "3 regions" are the only thing distinguishing two otherwise
// identically-worded summaries sitting one above the other.
const UNIT_NOUNS: Record<string, { one: string; many: string }> = {
  airport: { one: "airport", many: "airports" },
  city: { one: "city", many: "cities" },
  region: { one: "region", many: "regions" },
};

function unitNouns(unit: string | null | undefined) {
  // A unit this UI hasn't been taught still gets readable prose rather than
  // "undefineds".
  return UNIT_NOUNS[unit ?? ""] ?? { one: "destination", many: "destinations" };
}

// Which unit produced a block, for its heading: "by airport" / "by region".
export function entropyUnitLabel(entropy: DestinationEntropy | null | undefined): string {
  return `by ${unitNouns(entropy?.destination_unit).one}`;
}

// The two numbers, plus the sentence that stops them being read wrong.
// Entropy is jargon and 0 is ambiguous on its own, so the summary always
// says what produced the value.
//
// Takes the entropy block itself rather than the traveler, because there is
// more than one of them per traveler now and they render identically.
export function describeEntropy(
  entropy: DestinationEntropy | null | undefined,
): { headline: string; detail: string } | null {
  const e = entropy;
  if (!e || e.entropy === null) return null;

  const noun = unitNouns(e.destination_unit);
  const trips = `${e.trips_with_destination} trip${e.trips_with_destination === 1 ? "" : "s"}`;

  if (!e.is_informative) {
    return {
      headline: "Not enough trips",
      detail: `Entropy needs at least two recorded trips to mean anything; this traveler has ${trips}.`,
    };
  }
  if (e.n_destinations === 1) {
    return {
      // Names the unit, because "always the same destination" is true of a
      // person who flew to six different airports in one region, and that is
      // exactly the traveler these two blocks exist to tell apart.
      headline: `Always the same ${noun.one}`,
      // The whole point of showing 0 rather than hiding it -- name the place,
      // and the trip count, so it reads as a fact about the person.
      detail: `All ${trips} went to ${e.top_destination}.`,
    };
  }
  const share = e.top_destination_share === null ? null : Math.round(e.top_destination_share * 100);
  return {
    headline: `${e.n_destinations} ${noun.many} across ${trips}`,
    detail:
      share === null
        ? `Spread across ${e.n_destinations} ${noun.many}.`
        : `Most frequent is ${e.top_destination} at ${share}% of trips.`,
  };
}

interface TravelersResponse {
  // False when travelers.json hasn't been generated in the backend's
  // checkout. Kept distinct from "an empty list of travelers" so /rec-sys can
  // say which scripts to run instead of implying the dataset is empty.
  dataset_available: boolean;
  travelers: TravelerSummary[];
}

export class TravelerNotFoundError extends Error {}

export async function fetchTravelers(): Promise<TravelersResponse> {
  const res = await fetch(`${API_BASE_URL}/api/travelers`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  return (await res.json()) as TravelersResponse;
}

export async function fetchTraveler(travelerId: string): Promise<TravelerDetail> {
  const res = await fetch(`${API_BASE_URL}/api/travelers/${encodeURIComponent(travelerId)}`);
  if (res.status === 404) throw new TravelerNotFoundError(`No traveler with id ${travelerId}`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  return (await res.json()) as TravelerDetail;
}

export type TravelersLoadState =
  | { status: "loading" }
  | { status: "error" }
  // Distinct from "loaded with zero travelers": this one means the data
  // scripts haven't been run, which is a fixable, explainable state rather
  // than a fact about travelers.
  | { status: "unavailable" }
  | { status: "loaded"; travelers: TravelerSummary[] };

export function useTravelers(): TravelersLoadState {
  const [state, setState] = useState<TravelersLoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetchTravelers()
      .then((payload) => {
        if (cancelled) return;
        setState(
          payload.dataset_available
            ? { status: "loaded", travelers: payload.travelers }
            : { status: "unavailable" },
        );
      })
      .catch(() => {
        if (cancelled) return;
        setState({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

// /rec-sys's data source once the entropy filter needs more than
// region_entropy_normalized: the plain summary list, then every traveler's
// own detail fetched in parallel to pick up destination_entropy (airport)
// and the raw side of region_entropy -- neither is on /api/travelers (see
// TravelerSummary above). This is the frontend-only way to get there: it
// re-fetches per traveler (currently ~210 requests) rather than the backend
// growing a richer summary route, which is heavier than the design comment
// on region_entropy_normalized wants -- accepted because this filter is a
// one-person analysis tool, not the page most visitors land on.
//
// "enriching" is a real, renderable state, not just a spinner: the grid can
// and does render during it -- the multi-trip checkbox and
// region_normalized both already work off the summary alone -- it's only
// the other three metrics that are incomplete until every detail fetch
// lands.
export type EnrichedTravelersLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "unavailable" }
  | { status: "enriching"; travelers: TravelerSummary[] }
  | { status: "loaded"; travelers: TravelerSummary[] };

export function useTravelersWithEntropy(): EnrichedTravelersLoadState {
  const base = useTravelers();
  const [enriched, setEnriched] = useState<TravelerSummary[] | null>(null);

  useEffect(() => {
    if (base.status !== "loaded") {
      setEnriched(null);
      return;
    }
    let cancelled = false;
    setEnriched(null);

    Promise.allSettled(base.travelers.map((t) => fetchTraveler(t.traveler_id))).then((results) => {
      if (cancelled) return;
      // A failed detail fetch (a stale id, a dropped connection) falls back
      // to the summary row unchanged, rather than dropping the traveler --
      // they just won't clear a filter on the two fields that request would
      // have supplied.
      setEnriched(
        base.travelers.map((summary, i) => {
          const result = results[i];
          if (result.status !== "fulfilled") return summary;
          return {
            ...summary,
            destination_entropy: result.value.destination_entropy,
            region_entropy: result.value.region_entropy,
          };
        }),
      );
    });

    return () => {
      cancelled = true;
    };
  }, [base]);

  if (base.status !== "loaded") return base;
  return enriched === null
    ? { status: "enriching", travelers: base.travelers }
    : { status: "loaded", travelers: enriched };
}

export type TravelerLoadState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error" }
  | { status: "loaded"; traveler: TravelerDetail };

export function useTraveler(travelerId: string | undefined): TravelerLoadState {
  const [state, setState] = useState<TravelerLoadState>({ status: "loading" });

  useEffect(() => {
    if (!travelerId) return;
    let cancelled = false;
    setState({ status: "loading" });

    fetchTraveler(travelerId)
      .then((traveler) => {
        if (cancelled) return;
        setState({ status: "loaded", traveler });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ status: err instanceof TravelerNotFoundError ? "not-found" : "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [travelerId]);

  return state;
}

// "3 trips" / "1 trip". Trip count is the one number on a card that isn't a
// name, so it carries its own unit rather than sitting there as a bare digit.
export function formatTripCount(count: number): string {
  return `${count} trip${count === 1 ? "" : "s"}`;
}

// "Melbourne, Australia", or just the country if there's no city, or null
// when this traveler's nationality has no base mapping at all.
export function formatBase(traveler: TravelerSummary): string | null {
  if (traveler.base_city && traveler.base_country) return `${traveler.base_city}, ${traveler.base_country}`;
  return traveler.base_city || traveler.base_country || null;
}

// "35" for a traveler whose trips all record the same age, "35-37" when they
// span years. Null when no trip of theirs recorded an age at all.
export function formatAge(traveler: TravelerSummary): string | null {
  if (!traveler.age_range) return traveler.age === null ? null : String(traveler.age);
  const [youngest, oldest] = traveler.age_range;
  return youngest === oldest ? String(youngest) : `${youngest}-${oldest}`;
}

// "London, United Kingdom" for a city trip, "Japan" for a country-only one.
// Built from the cleaned fields rather than destination_raw so the page shows
// one spelling per place -- the source has "Sydney", "Sydney, Aus" and
// "Sydney, Australia" for the same city. Falls back to the raw string if a
// trip somehow arrives with neither piece.
export function formatDestination(trip: TravelerTrip): string {
  if (trip.destination_city && trip.destination_country) {
    return `${trip.destination_city}, ${trip.destination_country}`;
  }
  return trip.destination_city || trip.destination_country || trip.destination_raw;
}

// "May 1st, 2023 - May 8th, 2023" when both dates parsed, the raw strings
// when they didn't (so a date this project failed to parse still shows what
// the source actually said), and null when the source had no dates at all.
export function formatTripDates(trip: TravelerTrip, formatRange: (start: string, end: string) => string): string | null {
  if (trip.start_date && trip.end_date) return formatRange(trip.start_date, trip.end_date);
  const raw = [trip.start_date_raw, trip.end_date_raw].filter(Boolean);
  return raw.length ? raw.join(" - ") : null;
}

// TravelerDetail's "Show by" control for the Trips section: most-recent
// trip first (the default) or oldest first. "oldest" happens to match the
// order /api/travelers already returns trips in -- build_travelers.py sorts
// each traveler's trips ascending by start_date, undated trips last -- so
// "oldest" is effectively "as the API sent them" and "recent" is that same
// order reversed among the DATED trips.
export type TripOrder = "recent" | "oldest";

export const TRIP_ORDER_OPTIONS: { value: TripOrder; label: string }[] = [
  { value: "recent", label: "Most recent first" },
  { value: "oldest", label: "Oldest first" },
];

// Undated trips (start_date null -- the source value didn't parse) always
// sort to the END, in EITHER direction: a missing date must never read as
// "oldest" just because it sorts first ascending, or as "most recent" just
// because it sorts first descending -- same reasoning build_travelers.py
// itself gives for keeping them last in the API's own order. Dated trips
// with the same start_date, and the undated trips among themselves,
// tie-break on destination name for a stable, readable order regardless of
// which order they arrived in.
export function sortTripsByDate(trips: TravelerTrip[], order: TripOrder): TravelerTrip[] {
  return [...trips].sort((a, b) => {
    if (a.start_date === null || b.start_date === null) {
      if (a.start_date === null && b.start_date === null) {
        return formatDestination(a).localeCompare(formatDestination(b));
      }
      return a.start_date === null ? 1 : -1;
    }
    if (a.start_date !== b.start_date) {
      const ascending = a.start_date < b.start_date ? -1 : 1;
      return order === "recent" ? -ascending : ascending;
    }
    return formatDestination(a).localeCompare(formatDestination(b));
  });
}
