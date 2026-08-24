import { describe, expect, it } from "vitest";
import {
  describeEntropy,
  entropyUnitLabel,
  formatDestinationScore,
  tripDestinationScores,
  type DestinationEntropy,
  type TravelerTrip,
} from "./travelers";

function entropy(overrides: Partial<DestinationEntropy> = {}): DestinationEntropy {
  return {
    entropy: 1.386,
    normalized: 0.297,
    n_destinations: 4,
    trips_with_destination: 36,
    is_informative: true,
    top_destination: "NAS",
    top_destination_share: 0.25,
    global_distinct_destinations: 106,
    destination_unit: "airport",
    ...overrides,
  };
}

const REGION: Partial<DestinationEntropy> = {
  destination_unit: "region",
  global_distinct_destinations: 22,
  n_destinations: 3,
  top_destination: "Northern America",
};

describe("describeEntropy", () => {
  it("names the unit, which is the only thing separating two blocks on one page", () => {
    // The two entropy blocks are otherwise worded identically and sit one
    // above the other, so "4 airports" vs "3 regions" is what tells a reader
    // which number they're looking at.
    expect(describeEntropy(entropy())?.headline).toBe("4 airports across 36 trips");
    expect(describeEntropy(entropy(REGION))?.headline).toBe("3 regions across 36 trips");
  });

  it("names the unit in the single-destination case too", () => {
    // "Always the same destination" is true of someone who used six airports
    // inside one region -- and that traveler is exactly what the two blocks
    // exist to tell apart, so the noun has to be specific.
    expect(describeEntropy(entropy({ n_destinations: 1 }))?.headline).toBe(
      "Always the same airport",
    );
    expect(describeEntropy(entropy({ ...REGION, n_destinations: 1 }))?.headline).toBe(
      "Always the same region",
    );
  });

  it("names the most frequent destination and its share", () => {
    expect(describeEntropy(entropy())?.detail).toBe("Most frequent is NAS at 25% of trips.");
  });

  it("reports a single destination as a finding, with the count behind it", () => {
    const summary = describeEntropy(
      entropy({ entropy: 0, n_destinations: 1, trips_with_destination: 53, top_destination: "JFK" }),
    );
    expect(summary?.detail).toBe("All 53 trips went to JFK.");
  });

  it("separates an uninformative zero from a real one", () => {
    // One observation can only ever produce 0. That says nothing about the
    // traveler, and must not read like "never varies".
    const summary = describeEntropy(
      entropy({ entropy: 0, n_destinations: 1, trips_with_destination: 1, is_informative: false }),
    );
    expect(summary?.headline).toBe("Not enough trips");
    expect(summary?.detail).toContain("1 trip.");
  });

  it("returns null for an entropy that was never computed", () => {
    // Null is not zero: it means the source doesn't say. The page renders
    // nothing rather than a 0 that would claim the traveler never varies.
    expect(describeEntropy(null)).toBeNull();
    expect(describeEntropy(undefined)).toBeNull();
    expect(describeEntropy(entropy({ entropy: null }))).toBeNull();
  });

  it("falls back to readable prose for a unit it hasn't been taught", () => {
    expect(describeEntropy(entropy({ destination_unit: "continent" }))?.headline).toBe(
      "4 destinations across 36 trips",
    );
  });
});

describe("entropyUnitLabel", () => {
  it("reads as a heading suffix", () => {
    expect(entropyUnitLabel(entropy())).toBe("by airport");
    expect(entropyUnitLabel(entropy(REGION))).toBe("by region");
    expect(entropyUnitLabel(entropy({ destination_unit: "city" }))).toBe("by city");
  });

  it("doesn't say 'by undefined'", () => {
    expect(entropyUnitLabel(null)).toBe("by destination");
  });
});


// The per-trip destination scores shown on each card in TravelerDetail.
// What matters here is the null/zero distinction and the rounding, both of
// which are easy to "simplify" into a bug.

function trip(overrides: Partial<TravelerTrip> = {}): TravelerTrip {
  return {
    trip_id: "T-1",
    destination_raw: "Tokyo, Japan",
    destination_city: "Tokyo",
    destination_country: "Japan",
    destination_country_code: "JP",
    destination_kind: "city",
    start_date: "2024-01-08",
    start_date_raw: "2024-01-08",
    end_date: "2024-01-13",
    end_date_raw: "2024-01-13",
    duration_days: 5,
    duration_raw: "5",
    accommodation_type: "Hotel",
    accommodation_cost: null,
    accommodation_cost_raw: null,
    transportation_type: "Flight",
    transportation_cost: null,
    transportation_cost_raw: null,
    ...overrides,
  };
}

describe("tripDestinationScores", () => {
  it("returns the three scores in a fixed order", () => {
    const got = tripDestinationScores(
      trip({ unesco_score: 6.67, michelin_score: 9.99, weather_score: 7.58 }),
    );
    expect(got.map((s) => s.key)).toEqual(["unesco", "michelin", "weather"]);
    expect(got.map((s) => s.value)).toEqual([6.67, 9.99, 7.58]);
  });

  // A 0 is a real score -- "no World Heritage site within 50km", true of
  // most cities in this dataset -- and must survive. Dropping it as falsy
  // is the obvious way to break this function.
  it("keeps a zero score", () => {
    const got = tripDestinationScores(trip({ unesco_score: 0, michelin_score: 0 }));
    expect(got.map((s) => [s.key, s.value])).toEqual([
      ["unesco", 0],
      ["michelin", 0],
    ]);
  });

  it("omits a score that is null or absent, keeping the others", () => {
    expect(
      tripDestinationScores(
        trip({ unesco_score: 3.33, michelin_score: 9.34, weather_score: null }),
      ).map((s) => s.key),
    ).toEqual(["unesco", "michelin"]);
    expect(tripDestinationScores(trip()).length).toBe(0);
  });

  it("gives every score a tooltip naming what it measures", () => {
    const [unesco] = tripDestinationScores(trip({ unesco_score: 0 }));
    expect(unesco.title).toContain("50km");
  });
});

describe("formatDestinationScore", () => {
  // The bug this pins: at 1 decimal, Tokyo's stored 9.99 renders as "10.0"
  // and reads as a capped score.
  it("does not round a near-maximum score up to 10", () => {
    expect(formatDestinationScore(9.99)).toBe("9.99");
  });

  it("shows the stored two-decimal precision", () => {
    expect(formatDestinationScore(0)).toBe("0.00");
    expect(formatDestinationScore(7.58)).toBe("7.58");
    expect(formatDestinationScore(3.3)).toBe("3.30");
  });
});
