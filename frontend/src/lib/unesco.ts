// UNESCO World Heritage Site counts by country, from
// data/processed/UNESCO_SCORE_BY_COUNTRY.csv (see compute_unesco_score.py).
// Note SITE_COUNT can double-count transboundary sites across every
// country they span -- see data/processed/multiple/unesco_by_country.json's
// own note -- so country totals don't sum to the global site count.
import { loadCountryCountCsv } from "./countryStatsCsv";

const UNESCO_SCORE_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/UNESCO_SCORE_BY_COUNTRY.csv";

// code -> UNESCO World Heritage Site count. Cached at module scope so
// every DestinationDetail page fetches the CSV at most once per session.
let siteCountsPromise: Promise<Map<string, number>> | null = null;

export function getUnescoSiteCounts(): Promise<Map<string, number>> {
  if (!siteCountsPromise) siteCountsPromise = loadCountryCountCsv(UNESCO_SCORE_URL);
  return siteCountsPromise;
}

// e.g. formatUnescoCount(3) -> "3 UNESCO World Heritage Sites",
// formatUnescoCount(1) -> "1 UNESCO World Heritage Site". Counts here
// top out at 62 (Italy), nowhere near Michelin's scale, so no
// "Roughly"/rounding treatment is needed.
export function formatUnescoCount(count: number): string {
  return `${count} UNESCO World Heritage Site${count === 1 ? "" : "s"}`;
}

// UNESCO's own World Heritage Centre site keys its per-country "States
// Parties" page by lowercased ISO 3166-1 alpha-2 code too, e.g. "CN" ->
// "cn" -> https://whc.unesco.org/en/statesparties/cn. Same code this
// project already uses everywhere else, just lowercased for their URL
// convention -- same pattern as lib/michelin.ts's getMichelinGuideUrl().
export function getUnescoStatesPartyUrl(iso2: string): string {
  return `https://whc.unesco.org/en/statesparties/${iso2.toLowerCase()}`;
}
