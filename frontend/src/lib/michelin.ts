// Michelin Guide restaurant counts by country, from
// data/processed/MICHELIN_SCORE_BY_COUNTRY.csv (see
// compute_michelin_score.py) -- AWARD_COUNT is every Michelin award
// (Stars + Bib Gourmand + Selected Restaurants) in that country, i.e.
// the number of Michelin Guide restaurants.
import { loadCountryCountCsv } from "./countryStatsCsv";

const MICHELIN_SCORE_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/MICHELIN_SCORE_BY_COUNTRY.csv";

// code -> Michelin Guide restaurant count. Cached at module scope so
// every DestinationDetail page fetches the CSV at most once per session.
let awardCountsPromise: Promise<Map<string, number>> | null = null;

export function getMichelinAwardCounts(): Promise<Map<string, number>> {
  if (!awardCountsPromise) awardCountsPromise = loadCountryCountCsv(MICHELIN_SCORE_URL);
  return awardCountsPromise;
}

// Below 200, the exact count is shown as-is. From 200 to 499, it reads as
// false precision, so it's rounded to the nearest 25. At 500 and above,
// rounded to the nearest 50 instead -- a $25 granularity would just be
// more (still-false) precision at that scale. Both rounded tiers get a
// "Roughly" prefix.
// formatMichelinCount(7) -> "7 Michelin Guide Restaurants",
// formatMichelinCount(1) -> "1 Michelin Guide Restaurant",
// formatMichelinCount(477) -> "Roughly 475 Michelin Guide Restaurants",
// formatMichelinCount(495) -> "Roughly 500 Michelin Guide Restaurants",
// formatMichelinCount(561) -> "Roughly 550 Michelin Guide Restaurants",
// formatMichelinCount(2030) -> "Roughly 2050 Michelin Guide Restaurants".
export function formatMichelinCount(count: number): string {
  const roundingIncrement = count >= 500 ? 50 : count >= 200 ? 25 : null;
  const displayCount = roundingIncrement ? Math.round(count / roundingIncrement) * roundingIncrement : count;
  const prefix = roundingIncrement ? "Roughly " : "";
  return `${prefix}${displayCount} Michelin Guide Restaurant${displayCount === 1 ? "" : "s"}`;
}

// The MICHELIN Guide's own site keys its restaurant listing pages by
// lowercased ISO 3166-1 alpha-2 code, e.g. "CN" -> "cn" ->
// https://guide.michelin.com/en/cn/restaurants. Same code this project
// already uses everywhere else (DestinationDetail's `country.code`), just
// lowercased for their URL convention.
export function getMichelinGuideUrl(iso2: string): string {
  return `https://guide.michelin.com/en/${iso2.toLowerCase()}/restaurants`;
}
