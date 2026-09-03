import { describe, expect, it } from "vitest";
import {
  formatRecommendationSource,
  recommendationsCaveat,
  recommendationsMessage,
  type RecommendationsLoadState,
  type TravelerRecommendation,
  type TravelerRecommendationsResponse,
} from "./travelers";

// The Recommend button's pure logic. Worth pinning now precisely BECAUSE the
// Python recommender is unfinished: every one of these states is reachable
// today, and the one the app actually hits ("not_generated") is the one most
// likely to be quietly broken by a later change, since nobody looking at a
// working recommender would think to check it.

function recommendation(over: Partial<TravelerRecommendation> = {}): TravelerRecommendation {
  return {
    destination_key: "Valencia|Spain",
    destination_city: "Valencia",
    destination_country: "Spain",
    region: "Southern Europe",
    score: 0.87,
    source: "hybrid",
    best_month: "may",
    why: ["Closest to their Lisbon trips"],
    ...over,
  };
}

function response(
  over: Partial<TravelerRecommendationsResponse> = {},
): TravelerRecommendationsResponse {
  return {
    traveler_id: "anthony-bourdain",
    status: "ok",
    detail: "",
    personalised: true,
    route: "both",
    strategy: "hybrid",
    generated: "2026-09-14",
    recommendations: [recommendation()],
    ...over,
  };
}

function loaded(over: Partial<TravelerRecommendationsResponse> = {}): RecommendationsLoadState {
  return { status: "loaded", response: response(over) };
}

describe("recommendationsMessage", () => {
  it("says nothing before the button is pressed", () => {
    expect(recommendationsMessage({ status: "idle" })).toBeNull();
  });

  it("says nothing when there are cards to render instead", () => {
    expect(recommendationsMessage(loaded())).toBeNull();
  });

  it("announces the fetch", () => {
    expect(recommendationsMessage({ status: "loading" })).toContain("Looking");
  });

  it("distinguishes a failed request from an empty result", () => {
    const failed = recommendationsMessage({ status: "error" });
    const empty = recommendationsMessage(
      loaded({ status: "unavailable", detail: "No recommendation could be made.", recommendations: [] }),
    );
    expect(failed).not.toEqual(empty);
    expect(failed).toContain("Try again");
  });

  // The state the app is in today, and will stay in until rec_sys_hybrid.py
  // writes recommendations.json. It has to read as "not built yet", not as a
  // failure -- which is exactly why the backend returns it as HTTP 200.
  it("passes through the backend's explanation when nothing has been generated", () => {
    const message = recommendationsMessage(
      loaded({
        status: "not_generated",
        detail: "Recommendations haven't been generated for this dataset yet. Run data/scripts/multiple/rec_sys_hybrid.py.",
        recommendations: [],
        personalised: false,
      }),
    );
    expect(message).toContain("rec_sys_hybrid.py");
  });

  it("falls back to its own words if the backend sends an empty detail", () => {
    const message = recommendationsMessage(
      loaded({ status: "unavailable", detail: "", recommendations: [] }),
    );
    expect(message).toBeTruthy();
  });

  // A response claiming "ok" with nothing in it is a contradiction the UI
  // still has to render as something rather than as an empty panel.
  it("treats ok-with-no-rows as an empty result, not as cards", () => {
    expect(recommendationsMessage(loaded({ recommendations: [] }))).toBeTruthy();
  });
});

describe("recommendationsCaveat", () => {
  it("is silent on a personalised list", () => {
    expect(recommendationsCaveat(response())).toBeNull();
  });

  // The whole point of `personalised` being separate from `status`: a
  // popularity fallback is a real answer, and mislabelling it "for you" is
  // the failure mode the flag exists to prevent.
  it("labels a popularity fallback as not personalised", () => {
    expect(recommendationsCaveat(response({ personalised: false }))).toContain("Popular");
  });

  it("says nothing when there is nothing to qualify", () => {
    expect(
      recommendationsCaveat(response({ personalised: false, recommendations: [] })),
    ).toBeNull();
    expect(
      recommendationsCaveat(response({ status: "not_generated", personalised: false })),
    ).toBeNull();
  });
});

describe("formatRecommendationSource", () => {
  it("names each model in words", () => {
    expect(formatRecommendationSource("content")).toBe("Matches their taste");
    expect(formatRecommendationSource("collaborative")).toBe("Travelers like them went");
    expect(formatRecommendationSource("hybrid")).toBe("Taste + travelers like them");
    expect(formatRecommendationSource("popularity")).toBe("Popular");
  });

  // Better no chip than a raw enum value shown to a person -- and a source
  // this frontend doesn't know about is exactly what a later model version
  // will send.
  it("draws no chip for an unknown or missing source", () => {
    expect(formatRecommendationSource("bandit-v2")).toBeNull();
    expect(formatRecommendationSource(null)).toBeNull();
    expect(formatRecommendationSource(undefined)).toBeNull();
  });
});
