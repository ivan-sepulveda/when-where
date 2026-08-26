import { describe, expect, it } from "vitest";
import {
  ENTROPY_STEP,
  entropyMetricRange,
  entropyMetricValue,
  filterByEntropy,
  filterByTravelerType,
  formatEntropyValue,
  type DestinationEntropy,
  type TravelerSummary,
} from "./travelers";

// The /rec-sys entropy filter's pure functions. The behaviour worth pinning
// is the same edges the old region-only slider cared about (the off
// position, a traveler whose entropy was never computed, a dataset where
// nobody has one) PLUS what's new: four metrics instead of one, five
// comparators instead of a bare minimum, and a threshold of zero now being a
// real, meaningful query rather than "off".

function entropyBlock(entropy: number | null, normalized: number | null): DestinationEntropy {
  return {
    entropy,
    normalized,
    n_destinations: entropy === null ? 0 : 1,
    trips_with_destination: entropy === null ? 0 : 1,
    is_informative: entropy !== null,
    top_destination: null,
    top_destination_share: null,
    global_distinct_destinations: null,
    destination_unit: null,
  };
}

function traveler(
  name: string,
  opts: {
    destinationEntropy?: number | null;
    destinationNormalized?: number | null;
    regionEntropy?: number | null;
    regionNormalized?: number | null;
    // The old summary-only field -- present even without a full
    // region_entropy block, since that's what /api/travelers itself sends.
    regionEntropySummary?: number | null;
  } = {},
): TravelerSummary {
  const base: TravelerSummary = {
    traveler_id: name,
    name,
    nationality: "American",
    gender: "Male",
    age: 40,
    age_range: [40, 40],
    trip_count: 3,
    destinations: [],
  };
  if (opts.regionEntropySummary !== undefined) {
    base.region_entropy_normalized = opts.regionEntropySummary;
  }
  if (opts.destinationEntropy !== undefined || opts.destinationNormalized !== undefined) {
    base.destination_entropy = entropyBlock(
      opts.destinationEntropy ?? null,
      opts.destinationNormalized ?? null,
    );
  }
  if (opts.regionEntropy !== undefined || opts.regionNormalized !== undefined) {
    base.region_entropy = entropyBlock(opts.regionEntropy ?? null, opts.regionNormalized ?? null);
  }
  return base;
}

const PEOPLE = [
  traveler("stay-home", { regionEntropySummary: 0, regionEntropy: 0, regionNormalized: 0 }),
  traveler("some-range", { regionEntropySummary: 0.22, regionEntropy: 1.1, regionNormalized: 0.22 }),
  traveler("wide-range", { regionEntropySummary: 0.73, regionEntropy: 2.3, regionNormalized: 0.73 }),
  // Not enriched at all -- a plain /api/travelers row with no region entropy
  // computed either.
  traveler("uncomputed"),
  // Enriched (has destination_entropy / region_entropy blocks from the
  // detail fetch), but the airport side is genuinely unknown -- a
  // Kaggle-sourced traveler who records no destination airport.
  traveler("no-airport-data", {
    destinationEntropy: null,
    destinationNormalized: null,
    regionEntropySummary: 0.4,
    regionEntropy: 1.5,
    regionNormalized: 0.4,
  }),
];

describe("filterByEntropy", () => {
  it("passes everyone when no metric is selected", () => {
    expect(filterByEntropy(PEOPLE, null, "gte", 0)).toHaveLength(PEOPLE.length);
    expect(filterByEntropy(PEOPLE, null, "gte", 999)).toHaveLength(PEOPLE.length);
  });

  it("filters on airport (raw) entropy with >=", () => {
    const withAirport = [
      traveler("a", { destinationEntropy: 0 }),
      traveler("b", { destinationEntropy: 2.5 }),
      traveler("c"), // never enriched -- excluded from every threshold
    ];
    expect(filterByEntropy(withAirport, "airport", "gte", 1).map((t) => t.name)).toEqual(["b"]);
  });

  it("a threshold of zero is a real filter now, not the off position", () => {
    // "=" 0 finds exactly the deterministic-destination travelers -- the
    // whole reason this filter exists. The old min-only slider couldn't ask
    // this question at all.
    expect(filterByEntropy(PEOPLE, "region_normalized", "eq", 0).map((t) => t.name)).toEqual([
      "stay-home",
    ]);
  });

  it("supports all five comparators", () => {
    // "no-airport-data" sits at region_normalized 0.4 -- it's part of these
    // expectations wherever 0.4 falls in range, same as any other traveler.
    const byName = (list: TravelerSummary[]) => list.map((t) => t.name);
    expect(byName(filterByEntropy(PEOPLE, "region_normalized", "gte", 0.22))).toEqual([
      "some-range",
      "wide-range",
      "no-airport-data",
    ]);
    expect(byName(filterByEntropy(PEOPLE, "region_normalized", "lte", 0.22))).toEqual([
      "stay-home",
      "some-range",
    ]);
    expect(byName(filterByEntropy(PEOPLE, "region_normalized", "gt", 0.22))).toEqual([
      "wide-range",
      "no-airport-data",
    ]);
    expect(byName(filterByEntropy(PEOPLE, "region_normalized", "lt", 0.22))).toEqual(["stay-home"]);
    expect(byName(filterByEntropy(PEOPLE, "region_normalized", "eq", 0.73))).toEqual(["wide-range"]);
  });

  // A null is "not known" -- either not enriched yet, or the backend
  // genuinely has no entropy for this traveler -- and it must never satisfy
  // ANY comparator, including "<": unknown is not the same as low.
  it("never matches a null value, for any comparator", () => {
    const comparators = ["gte", "lte", "gt", "lt", "eq"] as const;
    for (const comparator of comparators) {
      const names = filterByEntropy(PEOPLE, "region_normalized", comparator, 0).map((t) => t.name);
      expect(names).not.toContain("uncomputed");
    }
  });

  it("falls back to the summary's region_entropy_normalized before the full block is enriched", () => {
    const notYetEnriched = traveler("pending");
    notYetEnriched.region_entropy_normalized = 0.5;
    expect(filterByEntropy([notYetEnriched], "region_normalized", "gte", 0.5)).toHaveLength(1);
  });

  it("treats airport and region metrics independently -- a traveler can clear one and not the other", () => {
    expect(filterByEntropy(PEOPLE, "airport", "gte", 0)).not.toContain(
      PEOPLE.find((t) => t.name === "no-airport-data"),
    );
    expect(filterByEntropy(PEOPLE, "region", "gte", 0).map((t) => t.name)).toContain("no-airport-data");
  });

  it("can filter everything out", () => {
    expect(filterByEntropy(PEOPLE, "region_normalized", "gte", 0.9)).toEqual([]);
  });
});

describe("entropyMetricValue", () => {
  it("reads each of the four metrics independently", () => {
    const t = traveler("full", {
      destinationEntropy: 4.37,
      destinationNormalized: 0.65,
      regionEntropy: 2.27,
      regionNormalized: 0.48,
    });
    expect(entropyMetricValue(t, "airport")).toBeCloseTo(4.37);
    expect(entropyMetricValue(t, "airport_normalized")).toBeCloseTo(0.65);
    expect(entropyMetricValue(t, "region")).toBeCloseTo(2.27);
    expect(entropyMetricValue(t, "region_normalized")).toBeCloseTo(0.48);
  });

  it("returns null for an unenriched traveler on every metric except region_normalized's summary fallback", () => {
    const t = traveler("bare");
    expect(entropyMetricValue(t, "airport")).toBeNull();
    expect(entropyMetricValue(t, "airport_normalized")).toBeNull();
    expect(entropyMetricValue(t, "region")).toBeNull();
    expect(entropyMetricValue(t, "region_normalized")).toBeNull();
  });
});

describe("entropyMetricRange", () => {
  it("reports the min and max actually present for a metric", () => {
    expect(entropyMetricRange(PEOPLE, "region_normalized")).toEqual({ min: 0, max: 0.73 });
  });

  it("is null when nobody in the set has a value for that metric", () => {
    expect(entropyMetricRange([traveler("uncomputed")], "airport")).toBeNull();
    expect(entropyMetricRange([], "region_normalized")).toBeNull();
  });

  it("is not clamped to [0, 1] -- raw entropy can exceed it", () => {
    const t = traveler("wide", { destinationEntropy: 4.37 });
    expect(entropyMetricRange([t], "airport")).toEqual({ min: 4.37, max: 4.37 });
  });
});

describe("formatEntropyValue", () => {
  // Three places for EVERY metric -- normalized included. The precision the
  // threshold input accepts and the precision the range hint prints have to
  // be the same number, or a typeable query (0.007) reads as out of range
  // against a hint that rounded it away.
  it("shows normalized metrics to 3 places", () => {
    expect(formatEntropyValue(0.4372)).toBe("0.437");
    expect(formatEntropyValue(0.5)).toBe("0.500");
    expect(formatEntropyValue(0.8697)).toBe("0.870");
  });

  it("shows raw metrics to 3 places", () => {
    expect(formatEntropyValue(2.268)).toBe("2.268");
    expect(formatEntropyValue(4.372)).toBe("4.372");
  });

  // The values this filter exists to find sit near zero, and they must stay
  // distinguishable from each other and from a true 0.
  it("keeps small values distinct from zero", () => {
    expect(formatEntropyValue(0)).toBe("0.000");
    expect(formatEntropyValue(0.001)).toBe("0.001");
    expect(formatEntropyValue(0.007)).toBe("0.007");
  });
});

describe("ENTROPY_STEP", () => {
  // Pinned against formatEntropyValue's precision: a coarser step marks a
  // typed 0.007 as a step mismatch, so the field renders invalid while the
  // filter handles the query fine.
  it("is fine enough to type every value the hint can print", () => {
    expect(ENTROPY_STEP).toBe(0.001);
    expect(formatEntropyValue(ENTROPY_STEP)).toBe("0.001");
  });
});


// filterByTravelerType: the real/synthetic dropdown. "Real" is exactly
// real_person === true; "synthetic" is everyone else, including a traveler
// who has never been enriched with the field at all (an older cached
// response, or a summary row from before this field existed) -- unset must
// read as synthetic, not as a third state.
function typedTraveler(id: string, realPerson?: boolean): TravelerSummary {
  return {
    traveler_id: id,
    name: id,
    nationality: "American",
    gender: "Male",
    age: 40,
    age_range: [40, 40],
    trip_count: 3,
    destinations: [],
    ...(realPerson === undefined ? {} : { real_person: realPerson }),
  };
}

describe("filterByTravelerType", () => {
  const people = [typedTraveler("real-one", true), typedTraveler("fake-one", false), typedTraveler("unset-one")];

  it("passes everyone when the type is 'all'", () => {
    expect(filterByTravelerType(people, "all")).toEqual(people);
  });

  it("keeps only real_person === true travelers for 'real'", () => {
    expect(filterByTravelerType(people, "real").map((t) => t.traveler_id)).toEqual(["real-one"]);
  });

  it("keeps real_person === false AND unset travelers for 'synthetic'", () => {
    expect(filterByTravelerType(people, "synthetic").map((t) => t.traveler_id)).toEqual([
      "fake-one",
      "unset-one",
    ]);
  });
});
