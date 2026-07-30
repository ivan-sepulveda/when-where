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

// Above 1000, the exact count reads as false precision, so it's rounded
// to the nearest 50 and prefixed with "Roughly" -- e.g. 2030 -> "Roughly
// 2050 Michelin Guide Restaurants". 1000 and below are shown as-is:
// formatMichelinCount(7) -> "7 Michelin Guide Restaurants",
// formatMichelinCount(1) -> "1 Michelin Guide Restaurant",
// formatMichelinCount(893) -> "893 Michelin Guide Restaurants",
// formatMichelinCount(2030) -> "Roughly 2050 Michelin Guide Restaurants".
export function formatMichelinCount(count: number): string {
  const isRounded = count > 1000;
  const displayCount = isRounded ? Math.round(count / 50) * 50 : count;
  const prefix = isRounded ? "Roughly " : "";
  return `${prefix}${displayCount} Michelin Guide Restaurant${displayCount === 1 ? "" : "s"}`;
}
