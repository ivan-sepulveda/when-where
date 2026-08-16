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
  destination_entropy?: DestinationEntropy | null;
}

// The two numbers, plus the sentence that stops them being read wrong.
// Entropy is jargon and 0 is ambiguous on its own, so the summary always
// says what produced the value.
export function describeEntropy(
  traveler: TravelerDetail,
): { headline: string; detail: string } | null {
  const e = traveler.destination_entropy;
  if (!e || e.entropy === null) return null;

  const unit = e.destination_unit === "city" ? "cities" : "airports";
  const trips = `${e.trips_with_destination} trip${e.trips_with_destination === 1 ? "" : "s"}`;

  if (!e.is_informative) {
    return {
      headline: "Not enough trips",
      detail: `Entropy needs at least two recorded trips to mean anything; this traveler has ${trips}.`,
    };
  }
  if (e.n_destinations === 1) {
    return {
      headline: "Always the same destination",
      // The whole point of showing 0 rather than hiding it -- name the place,
      // and the trip count, so it reads as a fact about the person.
      detail: `All ${trips} went to ${e.top_destination}.`,
    };
  }
  const share = e.top_destination_share === null ? null : Math.round(e.top_destination_share * 100);
  return {
    headline: `${e.n_destinations} destinations across ${trips}`,
    detail:
      share === null
        ? `Spread across ${e.n_destinations} ${unit}.`
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
