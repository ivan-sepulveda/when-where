import { describe, expect, it } from "vitest";
import {
  buildShareBreakdown,
  carrierBreakdown,
  domesticInternationalBreakdown,
  isDomesticTrip,
  toPercentages,
} from "./travelerCharts";
import type { TravelerDetail, TravelerTrip } from "./travelers";

// The fixtures below are the real shapes in this dataset, not invented
// ones: Chet Baker really is 53 identical Delta ATL-JFK legs, Hades really
// flies 13 distinct carriers, and 124 of the 206 travelers really do have
// no carrier recorded at all. Those three are what the charts have to
// survive.
function trip(overrides: Partial<TravelerTrip> = {}): TravelerTrip {
  return {
    trip_id: null,
    destination_raw: "New York, United States",
    destination_city: "New York",
    destination_country: "United States",
    destination_country_code: "US",
    destination_kind: "city",
    start_date: null,
    start_date_raw: null,
    end_date: null,
    end_date_raw: null,
    duration_days: null,
    duration_raw: null,
    accommodation_type: null,
    accommodation_cost: null,
    accommodation_cost_raw: null,
    transportation_type: null,
    transportation_cost: null,
    transportation_cost_raw: null,
    ...overrides,
  };
}

function traveler(trips: TravelerTrip[], overrides: Partial<TravelerDetail> = {}): TravelerDetail {
  return {
    traveler_id: "chet-baker",
    name: "Chet Baker",
    nationality: "American",
    base_country_code: "US",
    gender: "Male",
    age: 47,
    age_range: [46, 47],
    trip_count: trips.length,
    destinations: [],
    trips,
    ...overrides,
  };
}

describe("toPercentages", () => {
  it("sums to exactly 100 where naive rounding would not", () => {
    // 1/3 each rounds to 33 three times = 99, and in a bar that is
    // explicitly a part-to-whole that gap is visible.
    const percents = toPercentages([1, 1, 1]);
    expect(percents.reduce((sum, p) => sum + p, 0)).toBe(100);
    expect(percents).toEqual([34, 33, 33]);
  });

  it("sums to 100 for a long tail of tiny shares", () => {
    const percents = toPercentages([50, 1, 1, 1, 1, 1, 1, 1]);
    expect(percents.reduce((sum, p) => sum + p, 0)).toBe(100);
  });

  it("returns zeros rather than dividing by zero on an empty total", () => {
    expect(toPercentages([0, 0])).toEqual([0, 0]);
  });
});

describe("buildShareBreakdown", () => {
  it("orders segments largest first and fills the bar", () => {
    const data = buildShareBreakdown(new Map([["United", 1], ["Delta", 3]]));
    expect(data.segments.map((s) => s.label)).toEqual(["Delta", "United"]);
    expect(data.segments.map((s) => s.percent)).toEqual([75, 25]);
    expect(data.hasAggregate).toBe(false);
  });

  it("names everything when it fits without folding", () => {
    const counts = new Map(
      ["A", "B", "C", "D", "E", "F", "G"].map((k, i) => [k, 10 - i] as [string, number]),
    );
    const data = buildShareBreakdown(counts);
    expect(data.segments).toHaveLength(7);
    expect(data.hasAggregate).toBe(false);
  });

  it("names an 8th category rather than folding a single one into an aggregate", () => {
    // An aggregate holding one carrier is worse than just naming it, so the
    // cut is at limit + 1.
    const counts = new Map(
      ["A", "B", "C", "D", "E", "F", "G", "H"].map((k, i) => [k, 10 - i] as [string, number]),
    );
    const data = buildShareBreakdown(counts);
    expect(data.segments).toHaveLength(8);
    expect(data.hasAggregate).toBe(false);
    expect(data.segments[7].label).toBe("H");
  });

  it("folds the tail into one grey aggregate so no hue is ever reused", () => {
    const counts = new Map(
      ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"].map((k, i) => [k, 20 - i] as [string, number]),
    );
    const data = buildShareBreakdown(counts);
    expect(data.segments).toHaveLength(8); // 7 named + the aggregate
    expect(data.hasAggregate).toBe(true);
    const last = data.segments[7];
    expect(last.label).toBe("3 others");
    expect(last.value).toBe(13 + 12 + 11); // H + I + J
  });

  it("keeps percentages summing to 100 once a tail is folded", () => {
    const counts = new Map(
      Array.from({ length: 13 }, (_, i) => [`Carrier ${i}`, 13 - i] as [string, number]),
    );
    const data = buildShareBreakdown(counts);
    expect(data.segments.reduce((sum, s) => sum + s.percent, 0)).toBe(100);
  });

  it("orders ties by label so segments don't swap between renders", () => {
    const first = buildShareBreakdown(new Map([["Zeta", 2], ["Alpha", 2]]));
    const second = buildShareBreakdown(new Map([["Alpha", 2], ["Zeta", 2]]));
    expect(first.segments.map((s) => s.label)).toEqual(["Alpha", "Zeta"]);
    expect(second.segments).toEqual(first.segments);
  });

  it("returns an empty chart rather than throwing when there's nothing to plot", () => {
    expect(buildShareBreakdown(new Map())).toEqual({ segments: [], hasAggregate: false, total: 0 });
  });
});

describe("carrierBreakdown", () => {
  it("renders a single-carrier loyalist as one full-width segment", () => {
    // Chet Baker: 53 Delta legs, nothing else.
    const trips = Array.from({ length: 53 }, () => trip({ carrier_name: "Delta Air Lines Inc." }));
    const data = carrierBreakdown(traveler(trips));
    expect(data.segments).toEqual([{ label: "Delta Air Lines Inc.", value: 53, percent: 100 }]);
    expect(data.total).toBe(53);
  });

  it("excludes trips with no carrier from the denominator instead of calling them Unknown", () => {
    // 124 of 206 travelers are Kaggle rows with carrier_name null. Counting
    // those as a category would assert something the source doesn't say.
    const trips = [
      trip({ carrier_name: "Delta Air Lines Inc." }),
      trip({ carrier_name: "Delta Air Lines Inc." }),
      trip({ carrier_name: null }),
      trip({}),
    ];
    const data = carrierBreakdown(traveler(trips));
    expect(data.total).toBe(2);
    expect(data.segments).toEqual([{ label: "Delta Air Lines Inc.", value: 2, percent: 100 }]);
  });

  it("gives an empty chart for a traveler with no carrier data at all", () => {
    const data = carrierBreakdown(traveler([trip({}), trip({})]));
    expect(data.total).toBe(0);
    expect(data.segments).toEqual([]);
  });

  it("handles a 13-carrier non-loyalist without exceeding the 8 colored categories", () => {
    // Hades flies 13 distinct airlines.
    const carriers = Array.from({ length: 13 }, (_, i) => `Carrier ${String.fromCharCode(65 + i)}`);
    const trips = carriers.flatMap((carrier, i) =>
      Array.from({ length: 13 - i }, () => trip({ carrier_name: carrier })),
    );
    const data = carrierBreakdown(traveler(trips));
    expect(data.segments).toHaveLength(8);
    expect(data.hasAggregate).toBe(true);
    expect(data.total).toBe(trips.length);
  });

  it("no longer surfaces cargo carriers, which are excluded upstream at build time", () => {
    // United Parcel Service used to pick up 12 legs via ANY_CARRIER; it and
    // four other freight operators are now dropped in
    // build_synthetic_trips.py's CARGO_CARRIERS, so nothing here has to
    // filter them and no traveler's chart should show one.
    const trips = Array.from({ length: 3 }, () => trip({ carrier_name: "American Airlines Inc." }));
    const data = carrierBreakdown(traveler(trips));
    expect(data.segments.map((s) => s.label)).toEqual(["American Airlines Inc."]);
  });
});

describe("isDomesticTrip", () => {
  it("compares ISO codes, not country display names", () => {
    // The source spells the same country several ways; the code is the
    // field build_trips_enhanced.py normalises.
    expect(isDomesticTrip(trip({ destination_country_code: "us" }), "US")).toBe(true);
    expect(isDomesticTrip(trip({ destination_country_code: "FR" }), "US")).toBe(false);
  });

  it("returns null when either side is missing, so it can be left out of the count", () => {
    expect(isDomesticTrip(trip({ destination_country_code: "US" }), null)).toBeNull();
    expect(isDomesticTrip(trip({ destination_country_code: "" }), "US")).toBeNull();
  });
});

describe("domesticInternationalBreakdown", () => {
  it("gives an all-domestic traveler one full-width segment", () => {
    const trips = Array.from({ length: 53 }, () => trip({ destination_country_code: "US" }));
    const data = domesticInternationalBreakdown(traveler(trips));
    expect(data.segments).toEqual([{ label: "Domestic", value: 53, percent: 100 }]);
  });

  it("puts Domestic first even when International is the bigger share", () => {
    // Fixed order, not sorted by size -- otherwise the bar's layout would
    // flip between one traveler page and the next.
    const trips = [
      ...Array.from({ length: 2 }, () => trip({ destination_country_code: "US" })),
      ...Array.from({ length: 8 }, () => trip({ destination_country_code: "FR" })),
    ];
    const data = domesticInternationalBreakdown(traveler(trips));
    expect(data.segments.map((s) => s.label)).toEqual(["Domestic", "International"]);
    expect(data.segments.map((s) => s.percent)).toEqual([20, 80]);
  });

  it("handles a traveler who only ever flies abroad", () => {
    const trips = Array.from({ length: 4 }, () => trip({ destination_country_code: "FR" }));
    const data = domesticInternationalBreakdown(traveler(trips));
    expect(data.segments).toEqual([{ label: "International", value: 4, percent: 100 }]);
  });

  it("skips trips it can't classify rather than guessing", () => {
    const trips = [
      trip({ destination_country_code: "US" }),
      trip({ destination_country_code: "" }),
    ];
    const data = domesticInternationalBreakdown(traveler(trips, { base_country_code: "US" }));
    expect(data.total).toBe(1);
  });
});

describe("airline colors", () => {
  it("gives the four anchor airlines their fixed color", async () => {
    const { ANCHOR_AIRLINES, airlineColor } = await import("./airlineColors");
    // Delta's red is bright enough to use as published.
    expect(ANCHOR_AIRLINES["Delta Air Lines Inc."].brand).toBe("#E3132C");
    expect(airlineColor("Delta Air Lines Inc.")).toBe("#E3132C");
    // United's navy is 1.6:1 on the dark card -- unreadable untouched, so the
    // drawn color is the same hue lifted into range while `brand` records the
    // real value.
    expect(ANCHOR_AIRLINES["United Air Lines Inc."].brand).toBe("#0033A0");
    expect(airlineColor("United Air Lines Inc.")).not.toBe("#0033A0");
    expect(airlineColor("Frontier Airlines Inc.")).toBe("#267A55");
  });

  it("gives American its brand grey, not its brand red", async () => {
    const { airlineColor } = await import("./airlineColors");
    // American's red (#DE1B23) sits 1.3 dE from Delta's and the two share a
    // chart 12 times. The grey is also American's, just not their primary.
    expect(airlineColor("American Airlines Inc.")).toBe("#A5B5BE");
    expect(airlineColor("American Airlines Inc.")).not.toBe(airlineColor("Delta Air Lines Inc."));
  });

  it("gives regionals their own color rather than a parent's", async () => {
    const { airlineColor } = await import("./airlineColors");
    // Envoy flies in American livery and SkyWest partly in Delta's, but on a
    // chart they're separate operators and get separate colors.
    expect(airlineColor("Envoy Air")).not.toBe(airlineColor("American Airlines Inc."));
    expect(airlineColor("SkyWest Airlines Inc.")).not.toBe(airlineColor("Delta Air Lines Inc."));
    expect(airlineColor("Mesa Airlines Inc.")).not.toBe(airlineColor("United Air Lines Inc."));
  });

  it("assigns every carrier in the dataset a distinct color", async () => {
    const { ASSIGNED_COLORS, ANCHOR_AIRLINES } = await import("./airlineColors");
    const all = [
      ...Object.values(ASSIGNED_COLORS),
      ...Object.values(ANCHOR_AIRLINES).map((a) => a.display),
    ];
    // Two airlines sharing a hex would be indistinguishable in the legend as
    // well as the bar, which the segment labels can't rescue.
    expect(new Set(all).size).toBe(all.length);
  });

  it("gives an unmapped carrier a stable readable color, not grey", async () => {
    const { airlineColor } = await import("./airlineColors");
    const first = airlineColor("Some New Airline Inc.");
    // Stable across calls -- a color that changed between renders would look
    // like a bug.
    expect(airlineColor("Some New Airline Inc.")).toBe(first);
    expect(first).toMatch(/^#[0-9A-F]{6}$/i);
    expect(airlineColor("A Different Carrier Ltd.")).toMatch(/^#[0-9A-F]{6}$/i);
  });

  it("shortens corporate carrier names to something that fits in a bar segment", async () => {
    const { shortenCarrier } = await import("./airlineColors");
    expect(shortenCarrier("American Airlines Inc.")).toBe("American");
    expect(shortenCarrier("Concesionaria Vuela Compania De Aviacion SA de CV (Volaris)")).toBe("Volaris");
    expect(shortenCarrier("Piedmont Airlines")).toBe("Piedmont");
    expect(shortenCarrier("Envoy Air")).toBe("Envoy");
    expect(shortenCarrier("CommuteAir LLC dba CommuteAir")).toBe("CommuteAir");
    // Unmapped names go through the trimmer rather than rendering in full.
    expect(shortenCarrier("Example Airways Inc.")).toBe("Example");
  });
});
