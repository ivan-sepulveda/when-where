// Art museum data by country, from
// data/processed/multiple/worldwide_museums.json (see
// build_worldwide_museums.py), filtered to category === "art_museum".
// worldwide_museums.json is the only museums dataset the frontend
// fetches. Unlike lib/hiking.ts's
// still-in-progress pull, this dataset is complete -- a country absent
// here genuinely has no art museum in either merged source, not "not
// fetched yet." So a missing country resolves to a real empty array, not
// a null/unknown state.
import { useEffect, useState } from "react";
import type { Country } from "./countries";

const WORLDWIDE_MUSEUMS_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/multiple/worldwide_museums.json";

export interface ArtMuseum {
  name: string;
  city: string;
  // Only populated for museums from the Kaggle "largest art museums"
  // source (see build_worldwide_museums.py) -- null/absent for
  // JNTO-sourced Japan entries, which don't carry gallery space data.
  // Optional (not just nullable) so existing test fixtures that only set
  // name/city -- see artMuseums.test.ts -- stay valid. Used here only to
  // sort; DestinationDetail's card design doesn't display it.
  gallerySpaceM2?: number | null;
}

interface WorldwidePlace {
  name: string;
  category: string;
  iso2: string;
  city: string | null;
  gallery_space_m2: number | null;
}

interface WorldwideMuseumsResponse {
  places: WorldwidePlace[];
}

// code -> art museums, sorted by gallery_space_m2 descending (nulls last,
// stable within each group) -- worldwide_museums.json concatenates
// per-country files in country order, not by size, so the sort happens
// here rather than being inherited from the source file. Cached at
// module scope so every
// DestinationDetail page fetches the JSON at most once per session --
// same pattern as lib/michelin.ts/lib/unesco.ts/lib/hiking.ts.
let museumsByCountryPromise: Promise<Map<string, ArtMuseum[]>> | null = null;

export function getArtMuseumsByCountry(): Promise<Map<string, ArtMuseum[]>> {
  if (!museumsByCountryPromise) museumsByCountryPromise = loadArtMuseumsByCountry();
  return museumsByCountryPromise;
}

async function loadArtMuseumsByCountry(): Promise<Map<string, ArtMuseum[]>> {
  const res = await fetch(WORLDWIDE_MUSEUMS_URL);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as WorldwideMuseumsResponse;

  const byCountry = new Map<string, ArtMuseum[]>();
  for (const place of payload.places) {
    if (place.category !== "art_museum") continue;
    const museum: ArtMuseum = {
      name: place.name,
      city: place.city ?? "",
      gallerySpaceM2: place.gallery_space_m2,
    };
    const list = byCountry.get(place.iso2);
    if (list) list.push(museum);
    else byCountry.set(place.iso2, [museum]);
  }

  for (const list of byCountry.values()) {
    list.sort((a, b) => (b.gallerySpaceM2 ?? -1) - (a.gallerySpaceM2 ?? -1));
  }

  return byCountry;
}

// Source data is sorted by gallery_space_m2 descending (see
// loadArtMuseumsByCountry above), so this is just a slice -- kept as a
// named helper (rather than inlining `.slice(0, 5)` at the call site) so
// the "top N" behavior has one place to change.
export function getTopArtMuseums(museums: ArtMuseum[], count = 5): ArtMuseum[] {
  return museums.slice(0, count);
}

// Comparison key for joining a city name across two sources that don't
// share a naming convention: this dataset's `city` labels are whatever
// the underlying source used (Kaggle city names, or null for JNTO's Japan
// entries -- see the ArtMuseum.city comment above), while a CityDetail
// page has SimpleMaps' accented `city` alongside its stripped
// `city_ascii`. Applied to BOTH sides, so each rule only has to be
// self-consistent.
//
// Measured at the time this was written, against the 112 rows that carry
// a city: a plain lowercase comparison matched 101 of them to a city in
// tourist_cities_enhanced.json; the four rules below take that to 107.
// The 5 that still don't match are cities genuinely absent from this
// project's city list (Messina, Gwacheon, North Adams, Beacon) plus the
// Vatican Museums, whose iso2 is VA rather than Rome's IT -- none of
// which more name-munging would fix. Rows whose source recorded no city
// (city is "") simply don't match anything here, by design.
function cityMatchKey(name: string): string {
  return (
    name
      // "Washington, D.C." -> "Washington", "Beacon, New York" -> "Beacon".
      .split(",")[0]
      // NFD splits an accented character into base letter + combining
      // mark, so stripping the marks leaves "Ōsaka" and "Osaka" equal.
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "")
      .trim()
      .toLowerCase()
      // "St. Petersburg" vs SimpleMaps' "Saint Petersburg".
      .replace(/^st\.? /, "saint ")
      // "New York City" vs "New York". Safe to apply to both sides: a
      // city SimpleMaps itself calls "... City" (Quezon City, Ho Chi Minh
      // City) loses the suffix on both sides and still matches.
      .replace(/ city$/, "")
      .trim()
  );
}

// The museums in one specific city, matched by name against any of the
// spellings that city is known by (accented and ASCII). A strict city
// match by design -- deliberately NOT falling back to "elsewhere in this
// country," since a museum 600km away isn't something a trip to this
// city gives you. Coverage is uneven by country and no country is
// exhaustive (see data/raw/museums/README.md), so an empty result is the
// common case and means "none recorded here," not "no museums here."
export function getArtMuseumsInCity(museums: ArtMuseum[], cityNames: string[]): ArtMuseum[] {
  const wanted = new Set(cityNames.map(cityMatchKey));
  return museums.filter((museum) => wanted.has(cityMatchKey(museum.city)));
}

export type ArtMuseumsLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; museums: ArtMuseum[] }; // [] = genuinely no museum in this dataset for this country

export function useArtMuseums(country: Country | undefined): ArtMuseumsLoadState {
  const [state, setState] = useState<ArtMuseumsLoadState>({ status: "loading" });

  useEffect(() => {
    if (!country) return;
    let cancelled = false;
    setState({ status: "loading" });

    getArtMuseumsByCountry()
      .then((byCountry) => {
        if (cancelled) return;
        setState({ status: "loaded", museums: byCountry.get(country.code) ?? [] });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [country]);

  return state;
}
