import { describe, expect, it } from "vitest";
import { describeTag } from "./travelerTags";
import type { TravelerTag } from "./travelers";

function tag(overrides: Partial<TravelerTag> = {}): TravelerTag {
  return {
    tag_id: "airline-loyalist:delta-air-lines-inc",
    kind: "airline_loyalist",
    label: "Delta Loyalist",
    carrier_name: "Delta Air Lines Inc.",
    share: 1,
    trips: 42,
    denominator: 42,
    ...overrides,
  };
}

describe("describeTag", () => {
  it("states the count, the denominator and the percentage", () => {
    expect(describeTag(tag())).toBe("42 of 42 trips with a recorded airline (100%)");
  });

  it("always says the denominator is trips WITH A RECORDED AIRLINE", () => {
    // The whole point of the tooltip. Only hand-authored itineraries name a
    // carrier, so this number is smaller than the traveler's trip_count and
    // a bare "38 of 40" would read as a claim about all their travel.
    expect(describeTag(tag({ trips: 38, denominator: 40, share: 0.95 }))).toContain(
      "with a recorded airline",
    );
  });

  it("rounds the share rather than printing its float", () => {
    expect(describeTag(tag({ trips: 38, denominator: 40, share: 0.95 }))).toBe(
      "38 of 40 trips with a recorded airline (95%)",
    );
    expect(describeTag(tag({ trips: 7, denominator: 8, share: 0.875 }))).toBe(
      "7 of 8 trips with a recorded airline (88%)",
    );
  });

  it("singularises a denominator of one", () => {
    expect(describeTag(tag({ trips: 1, denominator: 1 }))).toBe(
      "1 of 1 trip with a recorded airline (100%)",
    );
  });

  it("drops the percentage rather than printing NaN% when share is missing", () => {
    expect(describeTag(tag({ share: null }))).toBe("42 of 42 trips with a recorded airline");
    expect(describeTag(tag({ share: undefined }))).toBe("42 of 42 trips with a recorded airline");
  });

  it("returns undefined when there's no evidence to show", () => {
    // Renders as a chip with no title attribute at all, rather than a
    // tooltip that says nothing.
    expect(describeTag(tag({ trips: null }))).toBeUndefined();
    expect(describeTag(tag({ denominator: undefined }))).toBeUndefined();
  });

  it("returns undefined for a kind it doesn't have wording for", () => {
    // A future rule gets its own branch here; until it does, its chip is
    // silent rather than described in airline terms it has nothing to do
    // with.
    expect(describeTag(tag({ kind: "budget_traveler", carrier_name: null }))).toBeUndefined();
  });
});
