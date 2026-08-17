import { describe, expect, it } from "vitest";
import { describeTag, joinNames, tagCarriers } from "./travelerTags";
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

function hub(overrides: Partial<TravelerTag> = {}): TravelerTag {
  return {
    tag_id: "airline-hub:united-air-lines-inc",
    kind: "airline_hub",
    label: "United Hub",
    carrier_name: "United Air Lines Inc.",
    carrier_names: ["United Air Lines Inc."],
    airlines: ["United"],
    hub_city: "Denver",
    hub_airports: ["DEN"],
    ...overrides,
  };
}

const MULTI_HUB_NYC: TravelerTag = {
  tag_id: "multi-hub",
  kind: "multi_hub",
  label: "Multi Hub",
  carrier_name: null,
  carrier_names: [
    "United Air Lines Inc.",
    "Delta Air Lines Inc.",
    "American Airlines Inc.",
  ],
  airlines: ["United", "Delta", "American"],
  hub_city: "New York City",
  hub_airports: ["EWR", "JFK", "LGA"],
};

describe("describeTag for hub tags", () => {
  it("leads with where the traveler lives, not who they fly", () => {
    // The tag is about geography. Without "Lives in", a "United Hub" chip
    // beside a "Southwest Loyalist" chip reads as a contradiction instead of
    // the real case it is.
    expect(describeTag(hub())).toBe("Lives in Denver, a United hub (DEN).");
  });

  it("lists every airline in a multi-hub city, in words", () => {
    expect(describeTag(MULTI_HUB_NYC)).toBe(
      "Lives in New York City, a hub for United, Delta and American (EWR, JFK, LGA).",
    );
  });

  it("uses 'and' without a comma for exactly two airlines", () => {
    expect(
      describeTag({
        ...MULTI_HUB_NYC,
        airlines: ["United", "American"],
        hub_city: "Chicago",
        hub_airports: ["ORD"],
      }),
    ).toBe("Lives in Chicago, a hub for United and American (ORD).");
  });

  it("still says something useful with no airports listed", () => {
    expect(describeTag(hub({ hub_airports: [] }))).toBe("Lives in Denver, a United hub.");
  });

  it("returns undefined without a city, which is the whole basis of the tag", () => {
    expect(describeTag(hub({ hub_city: null }))).toBeUndefined();
  });
});

describe("tagCarriers", () => {
  it("returns one entry per dot the chip should draw", () => {
    expect(tagCarriers(MULTI_HUB_NYC)).toHaveLength(3);
    expect(tagCarriers(hub())).toEqual(["United Air Lines Inc."]);
  });

  it("falls back to the single carrier_name", () => {
    // A tag written before carrier_names existed still gets its dot.
    expect(tagCarriers({ ...hub(), carrier_names: undefined })).toEqual([
      "United Air Lines Inc.",
    ]);
  });

  it("returns nothing for a tag about no airline", () => {
    // Which draws no dots rather than a grey one -- a dot always means
    // "this color identifies that airline".
    expect(
      tagCarriers({ tag_id: "x", kind: "budget_traveler", label: "Budget", carrier_name: null }),
    ).toEqual([]);
  });
});

describe("joinNames", () => {
  it("handles zero, one, two and three", () => {
    expect(joinNames([])).toBe("");
    expect(joinNames(["United"])).toBe("United");
    expect(joinNames(["United", "American"])).toBe("United and American");
    expect(joinNames(["United", "Delta", "American"])).toBe("United, Delta and American");
  });
});
