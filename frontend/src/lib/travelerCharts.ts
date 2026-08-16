// Turns one traveler's trips into the two share breakdowns shown on
// TravelerDetail: which airlines they fly, and how much of their flying is
// domestic vs international.
//
// All pure functions -- no React, no fetching -- so the shape logic is
// testable without rendering a chart (see travelerCharts.test.ts). The
// component in components/StackedShareBar.tsx only draws what these return.
import type { TravelerDetail, TravelerTrip } from "./travelers";

// Each breakdown renders as a single 100% STACKED HORIZONTAL BAR: one bar
// per question, segments sized by share, always summing to the full width.
//
// The cap isn't cosmetic. The categorical palette has 8 slots and hues are
// never cycled or generated past that, so at most MAX_NAMED_SEGMENTS
// categories can carry their own color; anything past that folds into a
// final grey "N others" segment rather than repeating a hue that already
// means another airline. Seven named is also about where a reader stops
// being able to tell adjacent classes apart at a glance -- carrier counts
// here run from 1 (a loyalist like Chet Baker, 100% Delta) to 13 (Hades,
// who flies whatever's convenient).
export const MAX_NAMED_SEGMENTS = 7;

export interface Slice {
  label: string;
  value: number; // trip count
  percent: number; // 0-100, of the breakdown's total
}

export interface ShareBreakdown {
  // Largest first. When a tail was folded, the last entry is the grey
  // "N others" aggregate.
  segments: Slice[];
  // True when the last segment is that aggregate rather than a real
  // category -- the component uses it to pick grey over a categorical hue.
  hasAggregate: boolean;
  total: number; // trips counted, i.e. the denominator behind every percent
}

// Percentages that sum to exactly 100 with no visible rounding drift.
// Largest-remainder: floor everything, then hand the leftover units to
// whoever lost the most in the floor. Straight per-segment rounding makes a
// 3-way even split render as "33% / 33% / 33%", and in a chart that is
// explicitly a part-to-whole a reader can see that it doesn't add up.
export function toPercentages(values: number[], decimals = 0): number[] {
  const total = values.reduce((sum, v) => sum + v, 0);
  if (total <= 0) return values.map(() => 0);

  const scale = 10 ** decimals;
  const exact = values.map((v) => (v / total) * 100 * scale);
  const floored = exact.map(Math.floor);
  let remainder = Math.round(100 * scale) - floored.reduce((sum, v) => sum + v, 0);

  // Index order breaks ties, so the same input always gives the same output
  // -- a percentage that flips between renders would look like a bug.
  const byLoss = exact
    .map((value, index) => ({ index, loss: value - floored[index] }))
    .sort((a, b) => b.loss - a.loss || a.index - b.index);

  const result = [...floored];
  for (let i = 0; remainder > 0 && i < byLoss.length; i += 1, remainder -= 1) {
    result[byLoss[i].index] += 1;
  }
  return result.map((v) => v / scale);
}

// Counts -> the bar's segments. Ties broken by label so two carriers with
// the same trip count don't swap places between renders.
export function buildShareBreakdown(
  counts: Map<string, number>,
  { limit = MAX_NAMED_SEGMENTS }: { limit?: number } = {},
): ShareBreakdown {
  const sorted = [...counts.entries()]
    .filter(([, count]) => count > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  const total = sorted.reduce((sum, [, count]) => sum + count, 0);
  if (total === 0) return { segments: [], hasAggregate: false, total: 0 };

  // Fold only when there IS a tail: an aggregate holding one carrier is
  // worse than just naming it, so the cut is at limit + 1, not limit.
  const named = sorted.length <= limit + 1 ? sorted : sorted.slice(0, limit);
  const rest = sorted.length <= limit + 1 ? [] : sorted.slice(limit);
  const restTotal = rest.reduce((sum, [, count]) => sum + count, 0);

  const entries: [string, number][] = [...named];
  if (restTotal > 0) entries.push([`${rest.length} others`, restTotal]);

  const percents = toPercentages(entries.map(([, count]) => count));
  return {
    segments: entries.map(([label, value], i) => ({ label, value, percent: percents[i] })),
    hasAggregate: restTotal > 0,
    total,
  };
}

// Only hand-authored trips record an airline (see build_synthetic_trips.py);
// every Kaggle-sourced row has carrier_name null, which is 124 of the 206
// travelers. Those trips are EXCLUDED from the denominator rather than
// counted as "Unknown": a traveler with 5 Delta trips and 3 unrecorded ones
// is 100% Delta as far as this dataset can say, and a 62%/38% bar would be
// asserting something the source doesn't contain. The component says how
// many trips the percentages are based on.
export function carrierBreakdown(traveler: TravelerDetail): ShareBreakdown {
  const counts = new Map<string, number>();
  for (const trip of traveler.trips) {
    const carrier = trip.carrier_name;
    if (!carrier) continue;
    counts.set(carrier, (counts.get(carrier) ?? 0) + 1);
  }
  return buildShareBreakdown(counts);
}

// A trip is domestic when its destination country is the traveler's own base
// country. Compared on ISO country CODE, not the display name -- the source
// spells the same country several ways ("USA", "United States"), and
// destination_country_code is the field build_trips_enhanced.py normalises.
export function isDomesticTrip(trip: TravelerTrip, baseCountryCode: string | null | undefined): boolean | null {
  if (!baseCountryCode || !trip.destination_country_code) return null;
  return trip.destination_country_code.toUpperCase() === baseCountryCode.toUpperCase();
}

export const DOMESTIC_LABEL = "Domestic";
export const INTERNATIONAL_LABEL = "International";

// Two segments, in a fixed order rather than sorted by size: Domestic always
// sits on the left. Sorting these by share would make the bar's layout flip
// between one traveler and the next, and a reader comparing two traveler
// pages would have to re-read the legend each time. Everywhere else the
// categories are nominal and descending order is the useful one; here they
// aren't.
export function domesticInternationalBreakdown(traveler: TravelerDetail): ShareBreakdown {
  let domestic = 0;
  let international = 0;

  for (const trip of traveler.trips) {
    const domesticFlag = isDomesticTrip(trip, traveler.base_country_code);
    if (domesticFlag === null) continue; // can't classify; leave it out of the denominator
    if (domesticFlag) domestic += 1;
    else international += 1;
  }

  const total = domestic + international;
  if (total === 0) return { segments: [], hasAggregate: false, total: 0 };

  const present: [string, number][] = [];
  if (domestic > 0) present.push([DOMESTIC_LABEL, domestic]);
  if (international > 0) present.push([INTERNATIONAL_LABEL, international]);

  const percents = toPercentages(present.map(([, count]) => count));
  return {
    segments: present.map(([label, value], i) => ({ label, value, percent: percents[i] })),
    hasAggregate: false,
    total,
  };
}
