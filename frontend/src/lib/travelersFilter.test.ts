import { describe, expect, it } from "vitest";
import { filterByRegionEntropy, maxRegionEntropy, type TravelerSummary } from "./travelers";

// The /rec-sys region-entropy slider's two pure functions. The behaviour
// worth pinning is what happens at the edges: the off position, a traveler
// whose entropy was never computed, and a dataset where nobody has one.

function traveler(name: string, entropy: number | null | undefined): TravelerSummary {
  return {
    traveler_id: name,
    name,
    nationality: "American",
    gender: "Male",
    age: 40,
    age_range: [40, 40],
    trip_count: 3,
    destinations: [],
    ...(entropy === undefined ? {} : { region_entropy_normalized: entropy }),
  };
}

const PEOPLE = [
  traveler("stay-home", 0),
  traveler("some-range", 0.22),
  traveler("wide-range", 0.73),
  traveler("uncomputed", null),
];

describe("filterByRegionEntropy", () => {
  it("passes everyone at zero, including travelers with no value", () => {
    expect(filterByRegionEntropy(PEOPLE, 0)).toHaveLength(4);
  });

  it("treats a negative threshold as off rather than as a filter", () => {
    expect(filterByRegionEntropy(PEOPLE, -1)).toHaveLength(4);
  });

  it("keeps travelers at or above the threshold", () => {
    expect(filterByRegionEntropy(PEOPLE, 0.22).map((t) => t.name)).toEqual([
      "some-range",
      "wide-range",
    ]);
  });

  // A null is "not computed", which cannot be shown to clear a bar -- but it
  // must not be mistaken for a 0 either, which is why it survives at 0.
  it("drops travelers with no value once the threshold is above zero", () => {
    expect(filterByRegionEntropy(PEOPLE, 0.01).map((t) => t.name)).not.toContain("uncomputed");
    expect(filterByRegionEntropy(PEOPLE, 0.01).map((t) => t.name)).not.toContain("stay-home");
  });

  it("can filter everything out", () => {
    expect(filterByRegionEntropy(PEOPLE, 0.9)).toEqual([]);
  });
});

describe("maxRegionEntropy", () => {
  it("rounds the dataset's highest value up to the next 0.05", () => {
    expect(maxRegionEntropy(PEOPLE)).toBeCloseTo(0.75);
    expect(maxRegionEntropy([traveler("a", 0.2)])).toBeCloseTo(0.2);
    expect(maxRegionEntropy([traveler("a", 0.21)])).toBeCloseTo(0.25);
  });

  // 0 means "no slider": either the entropy file isn't built, or every
  // traveler sits at zero and a slider would only ever empty the grid.
  it("returns 0 when nobody has a value", () => {
    expect(maxRegionEntropy([traveler("a", null), traveler("b", undefined)])).toBe(0);
    expect(maxRegionEntropy([])).toBe(0);
  });

  it("returns 0 when every value is zero", () => {
    expect(maxRegionEntropy([traveler("a", 0), traveler("b", 0)])).toBe(0);
  });

  it("never exceeds 1", () => {
    expect(maxRegionEntropy([traveler("a", 0.99)])).toBe(1);
  });
});
