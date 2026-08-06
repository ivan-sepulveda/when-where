// Travel advisories by country, from data/reference/travel_advisories.json
// (FCDO advisory text, keyed by ISO 3166-1 alpha-2 code -- only countries
// WITH an active advisory are present in that file). Fetched once and
// cached at module scope, same pattern as lib/unesco.ts's
// getUnescoSiteCounts().
import { useEffect, useState } from "react";
import type { Country } from "./countries";

const TRAVEL_ADVISORIES_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/reference/travel_advisories.json";

// iso2 -> advisory text.
export type TravelAdvisoriesByCountry = Record<string, string>;

let advisoriesPromise: Promise<TravelAdvisoriesByCountry> | null = null;

export function getTravelAdvisories(): Promise<TravelAdvisoriesByCountry> {
  if (!advisoriesPromise) {
    advisoriesPromise = fetch(TRAVEL_ADVISORIES_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
        return res.json() as Promise<TravelAdvisoriesByCountry>;
      })
      .catch((err) => {
        // Allow a later retry (e.g. after a transient network error)
        // instead of caching the failure forever.
        advisoriesPromise = null;
        throw err;
      });
  }
  return advisoriesPromise;
}

// Looks up a single country's advisory text out of the full map, matching
// case-insensitively -- same defensive .toUpperCase() the visa lookup in
// Destinations.tsx uses, since not every code source in this app is
// guaranteed to already be uppercase.
export function getTravelAdvisoryForCode(
  advisories: TravelAdvisoriesByCountry,
  code: string,
): string | null {
  return advisories[code.toUpperCase()] ?? null;
}

export type TravelAdvisoryLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; advisory: string | null };

// Same fetch-by-country-code shape as useCountryStatCount(), but resolves
// to the advisory text (or null when this country has none) instead of a
// count.
export function useTravelAdvisory(country: Country | undefined): TravelAdvisoryLoadState {
  const [state, setState] = useState<TravelAdvisoryLoadState>({ status: "loading" });

  useEffect(() => {
    if (!country) return;
    let cancelled = false;
    setState({ status: "loading" });

    getTravelAdvisories()
      .then((advisories) => {
        if (cancelled) return;
        setState({ status: "loaded", advisory: getTravelAdvisoryForCode(advisories, country.code) });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [country]);

  return state;
}
