import { describe, expect, it } from "vitest";
import { getArtMuseumsInCity, type ArtMuseum } from "./artMuseums";

// Covers the city-name join CityDetail's "Art Museums" section depends
// on. The cases below aren't hypothetical -- each is a real mismatch
// between the museum dataset's `city` labels and this project's city
// names, found by comparing the two files directly (see cityMatchKey()'s
// comment for the counts).
describe("getArtMuseumsInCity", () => {
  const museum = (name: string, city: string): ArtMuseum => ({ name, city });

  it("matches a city by its plain name", () => {
    const museums = [museum("Art & History Museum", "Brussels"), museum("Louvre", "Paris")];
    expect(getArtMuseumsInCity(museums, ["Brussels"])).toEqual([museums[0]]);
  });

  it("matches regardless of accents, so the ASCII and accented spellings agree", () => {
    const museums = [museum("The National Museum of Art, Osaka", "Osaka")];
    expect(getArtMuseumsInCity(museums, ["Osaka", "Ōsaka"])).toEqual(museums);
  });

  it("ignores a trailing state/region qualifier on the museum's city", () => {
    const museums = [museum("National Gallery of Art", "Washington, D.C.")];
    expect(getArtMuseumsInCity(museums, ["Washington"])).toEqual(museums);
  });

  it('treats "St." and "Saint" as the same city', () => {
    const museums = [museum("State Hermitage Museum", "St. Petersburg")];
    expect(getArtMuseumsInCity(museums, ["Saint Petersburg"])).toEqual(museums);
  });

  it('matches "New York City" to "New York"', () => {
    const museums = [museum("Metropolitan Museum of Art", "New York City")];
    expect(getArtMuseumsInCity(museums, ["New York"])).toEqual(museums);
  });

  it("does not fall back to other cities in the same country", () => {
    // The whole point of the strict match: a museum 600km away isn't
    // something a trip to this city gives you.
    const museums = [museum("Shandong Art Museum", "Jinan")];
    expect(getArtMuseumsInCity(museums, ["Beijing"])).toEqual([]);
  });

  it("returns an empty list rather than throwing when there's nothing to match", () => {
    expect(getArtMuseumsInCity([], ["Brussels"])).toEqual([]);
  });
});
