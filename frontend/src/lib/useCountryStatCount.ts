import { useEffect, useState } from "react";
import type { Country } from "./countries";

export type CountryStatLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; count: number };

// Shared fetch-by-country-code pattern behind every DestinationDetail
// stat (Michelin restaurant count, UNESCO site count, ...): call
// loadCounts() once, look up this country's count, and expose a
// loading/error/loaded state React components can render directly.
// loadCounts is expected to be a module-scoped, already-memoized
// function (e.g. getMichelinAwardCounts) so it's stable across renders.
export function useCountryStatCount(
  country: Country | undefined,
  loadCounts: () => Promise<Map<string, number>>,
): CountryStatLoadState {
  const [state, setState] = useState<CountryStatLoadState>({ status: "loading" });

  useEffect(() => {
    if (!country) return;
    let cancelled = false;
    setState({ status: "loading" });

    loadCounts()
      .then((counts) => {
        if (cancelled) return;
        setState({ status: "loaded", count: counts.get(country.code) ?? 0 });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [country, loadCounts]);

  return state;
}
