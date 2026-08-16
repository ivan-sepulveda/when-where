// Art museum data by country, from
// data/processed/multiple/art_museums_by_country.json (see
// build_art_museums_by_country.py). Unlike lib/hiking.ts's still-in-progress
// pull, this dataset is complete -- a country absent from the JSON
// genuinely has no museum in the underlying ~112-museum "largest art
// museums" list, not "not fetched yet." So a missing country resolves to
// a real empty array here, not a null/unknown state.
import { useEffect, useState } from "react";
import type { Country } from "./countries";

const ART_MUSEUMS_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/multiple/art_museums_by_country.json";

export interface ArtMuseum {
  name: string;
  city: string;
}

interface ArtMuseumsByCountryResponse {
  museums_by_country: Record<string, { name: string; city: string }[]>;
}

// code -> museums, already sorted by gallery_space_m2 descending (see
// build_art_museums_by_country.py) -- only name/city are kept client-side,
// per DestinationDetail's card design (no gallery space shown). Cached at
// module scope so every DestinationDetail page fetches the JSON at most
// once per session -- same pattern as lib/michelin.ts/lib/unesco.ts/lib/hiking.ts.
let museumsByCountryPromise: Promise<Map<string, ArtMuseum[]>> | null = null;

export function getArtMuseumsByCountry(): Promise<Map<string, ArtMuseum[]>> {
  if (!museumsByCountryPromise) museumsByCountryPromise = loadArtMuseumsByCountry();
  return museumsByCountryPromise;
}

async function loadArtMuseumsByCountry(): Promise<Map<string, ArtMuseum[]>> {
  const res = await fetch(ART_MUSEUMS_URL);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as ArtMuseumsByCountryResponse;

  const byCountry = new Map<string, ArtMuseum[]>();
  for (const [code, museums] of Object.entries(payload.museums_by_country)) {
    byCountry.set(code, museums.map(({ name, city }) => ({ name, city })));
  }
  return byCountry;
}

// Source data is already sorted by gallery_space_m2 descending, so this
// is just a slice -- kept as a named helper (rather than inlining
// `.slice(0, 5)` at the call site) so the "top N" behavior has one place
// to change.
export function getTopArtMuseums(museums: ArtMuseum[], count = 5): ArtMuseum[] {
  return museums.slice(0, count);
}

// Comparison key for joining a city name across two sources that don't
// share a naming convention: this dataset's `city` labels are whatever
// the underlying "largest art museums" list used, while a CityDetail page
// has SimpleMaps' accented `city` alongside its stripped `city_ascii`.
// Applied to BOTH sides, so each rule only has to be self-consistent.
//
// Measured against the real data at the time this was written: a plain
// lowercase comparison matched 101 of the 112 museums to a city in
// tourist_cities_enhanced.json; the four rules below take that to 107.
// The 5 that still don't match are cities genuinely absent from this
// project's city list (Messina, Gwacheon, North Adams, Beacon) plus the
// Vatican Museums, whose iso2 is VA rather than Rome's IT -- none of
// which more name-munging would fix.
function cityMatchKey(name: string): string {
  return (
    name
      // "Washington, D.C." -> "Washington", "Beacon, New York" -> "Beacon".
      // Only this dataset qualifies names this way; SimpleMaps keeps the
      // state/region in a separate field.
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
// city gives you. Remember the underlying dataset is only the ~112
// LARGEST art museums worldwide (see this module's header), so an empty
// result is the common case and means "none here made that list," not
// "no museums here."
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
