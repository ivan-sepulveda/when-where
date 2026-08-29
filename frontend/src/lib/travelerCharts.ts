// Turns one traveler's trips into the two share breakdowns shown on
// TravelerDetail: which airlines they fly, and how much of their flying is
// domestic vs international.
//
// All pure functions -- no React, no fetching -- so the shape logic is
// testable without rendering a chart (see travelerCharts.test.ts). The
// component in components/StackedShareBar.tsx only draws what these return.
import type { TravelerDetail, TravelerPreferences, TravelerTrip } from "./travelers";

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
    // A layover leg is a real flight but not "which airline this person
    // flies" any more than it's a place they went -- same exclusion
    // compute_traveler_tags.py's Loyalist tag makes, so this bar and that
    // chip can't disagree about the same trips.
    if (trip.layover) continue;
    const carrier = trip.carrier_name;
    if (!carrier) continue;
    counts.set(carrier, (counts.get(carrier) ?? 0) + 1);
  }
  return buildShareBreakdown(counts);
}

// Which parts of the world this traveler's trips go to, by UN M49 detailed
// region -- the intermediate region where the country has one (Caribbean,
// Central America, South America, and the four African ones), else the
// sub-region. 22 possible values.
//
// WHY THAT TIER AND NOT M49's LITERAL `subregion`: the literal one has just
// 17 values and folds Mexico, Costa Rica, Belize, Jamaica, the Bahamas and
// every South American country into a single "Latin America and the
// Caribbean". With 341 Mexico trips in this dataset that one segment would
// be most of the non-domestic bar and the chart would say almost nothing.
// The join and the choice both happen server-side -- see
// data/scripts/multiple/build_m49_regions.py.
//
// Trips whose destination has no region are EXCLUDED from the denominator,
// not counted as "Unknown" -- the same treatment carrierBreakdown gives a
// trip with no airline, and for the same reason: a category invented to
// cover a gap in the data reads as a finding about the traveler.
//
// This bar leans on buildShareBreakdown's fold harder than the others do: 22
// categories against MAX_NAMED_SEGMENTS means a well-travelled person can
// genuinely produce a "N others" tail, which is the intended behaviour rather
// than a cap to raise.
export function subregionBreakdown(traveler: TravelerDetail): ShareBreakdown {
  const counts = new Map<string, number>();
  for (const trip of traveler.trips) {
    // Same layover exclusion as carrierBreakdown above: Atlanta and Paris on
    // a Houston-to-Lisbon trip aren't places this traveler went.
    if (trip.layover) continue;
    const subregion = trip.destination_subregion;
    if (!subregion) continue;
    counts.set(subregion, (counts.get(subregion) ?? 0) + 1);
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
    // Same layover exclusion as the other breakdowns above: a layover isn't
    // a trip this traveler took to that country, domestic or not.
    if (trip.layover) continue;
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


// This traveler's destination preference profile, reshaped for the radar
// chart in components/PreferenceRadarChart.tsx. Unlike the share breakdowns
// above, there's no aggregation to do here -- the backend already computed
// the mean per dimension (see backend/app/main.py's _preferences) -- this
// just picks the axes that actually have a value.
//
// A dimension with no scored trips is DROPPED, not plotted as 0: the same
// "nothing invented" rule as tripDestinationScores. A radar chart has no
// way to mark one axis "no data" the way a trip card can simply omit a
// line, so the only honest option is to not draw that axis at all. In
// practice most travelers have all three (a matched city's UNESCO and
// Michelin scores come from the same lookup), and weather is the one most
// likely to be missing alone (only 1,770 of 3,069 cities have weather
// normals).
export interface PreferenceAxis {
  key: "unesco" | "michelin" | "weather" | "holiday" | "beach" | "allocentric";
  label: string;
  value: number; // 0-1
  trips: number; // the denominator this was computed over
  // The two kinds of number on this chart. "mean" is the average of a
  // destination's 0-10 quality score across the trips that HAVE one --
  // "how much UNESCO is where this person goes". "share" is the fraction
  // of this person's classifiable trips carrying a classify_trip tag --
  // "how much of this person's travel is a beach holiday".
  //
  // They coexist on one radar because both are 0-1 revealed preference
  // read off the same trip history. They are kept distinguishable because
  // the tooltip must not call a proportion an average: "60% avg over 5
  // trips" is a different claim from "60% -- 3 of 5 trips", and only the
  // second one is true of a share.
  kind: "mean" | "share";
}

const PREFERENCE_AXIS_LABELS: Record<PreferenceAxis["key"], string> = {
  unesco: "UNESCO",
  michelin: "Michelin",
  weather: "Weather",
  holiday: "Holiday",
  beach: "Beachgoer",
  allocentric: "Allocentric",
};

// How many dimensions a complete profile has. Exported so the chart can say
// "only N of M" without hardcoding a number that goes stale the next time a
// dimension is added -- which is exactly what happened to the "of 3" copy.
export const PREFERENCE_DIMENSION_COUNT = 6;

export function preferenceAxes(
  preferences: TravelerPreferences | null | undefined,
): PreferenceAxis[] {
  if (!preferences) return [];
  const raw: [PreferenceAxis["key"], number | null, number, PreferenceAxis["kind"]][] = [
    ["unesco", preferences.unesco, preferences.unesco_trips, "mean"],
    ["michelin", preferences.michelin, preferences.michelin_trips, "mean"],
    ["weather", preferences.weather, preferences.weather_trips, "mean"],
    ["holiday", preferences.holiday, preferences.holiday_trips, "share"],
    ["beach", preferences.beach, preferences.beach_trips, "share"],
    // ONE AXIS, NOT TWO. Plog's psychocentric and allocentric poles always
    // sum to 1, and a radar's spokes read as independent dimensions --
    // plotting both would draw one fact twice and hand every traveler a
    // symmetry that comes from the encoding rather than from their trips.
    // The allocentric pole is the one plotted because the other axes all
    // read "more is more of a trait", and because most travel goes to
    // well-connected places, so a polygon that reaches out here is saying
    // something unusual.
    ["allocentric", preferences.allocentric, preferences.allocentric_trips, "mean"],
  ];
  return raw
    .filter(
      (entry): entry is [PreferenceAxis["key"], number, number, PreferenceAxis["kind"]] =>
        typeof entry[1] === "number",
    )
    .map(([key, value, trips, kind]) => ({
      key,
      label: PREFERENCE_AXIS_LABELS[key],
      value,
      trips,
      kind,
    }));
}
