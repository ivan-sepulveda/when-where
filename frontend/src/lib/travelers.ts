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
}

// Mirrors backend/app/main.py's TravelerTag. A computed label -- see
// data/scripts/multiple/compute_traveler_tags.py -- describing a pattern in
// the trips AS RECORDED, never something the itinerary's author declared.
//
// `denominator` is not the traveler's trip_count. For an airline_loyalist tag
// it counts only trips that record a carrier, which is the same denominator
// the "Airlines flown" chart uses, so a 100% bar and a Loyalist chip can't
// contradict each other on the same page.
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
  // filterByRegionEntropy().
  region_entropy_normalized?: number | null;
}

// The /rec-sys region-entropy slider, as two pure functions so the page
// stays about layout.
//
// WHY A MINIMUM AND NOT A RANGE: the question the slider answers is "show me
// the travelers who actually move between regions". A max would only ever be
// used to look at the 154 travelers sitting at 0.0, which the multi-trip
// checkbox already handles better.
export function filterByRegionEntropy(
  travelers: TravelerSummary[],
  min: number,
): TravelerSummary[] {
  // Zero is the off position, and it has to pass EVERYTHING -- including
  // travelers whose entropy was never computed. Filtering them out at 0
  // would make an un-run script look like an empty dataset.
  if (min <= 0) return travelers;
  return travelers.filter(
    (t) =>
      typeof t.region_entropy_normalized === "number" && t.region_entropy_normalized >= min,
  );
}

// The slider's right-hand end: the highest value anyone in THIS dataset has,
// rounded up to the next 0.05. Derived rather than hardcoded, for the same
// reason the entropy charts echo their denominator -- the ceiling moves when
// the data does, and a slider whose top half is permanently empty is a
// slider that lies about the data. Returns 0 when nobody has a value, which
// the page reads as "no slider to show".
export function maxRegionEntropy(travelers: TravelerSummary[]): number {
  const values = travelers
    .map((t) => t.region_entropy_normalized)
    .filter((v): v is number => typeof v === "number");
  if (values.length === 0) return 0;
  const highest = Math.max(...values);
  if (highest <= 0) return 0;
  return Math.min(1, Math.ceil(highest * 20) / 20);
}

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

export interface TravelerDetail extends TravelerSummary {
  trips: TravelerTrip[];
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
