// One city's detail data, from the backend's
// GET /api/destinations/cities/{city_id} (see backend/app/main.py's
// city_destination_detail()).
//
// Unlike the country equivalents in lib/unesco.ts / lib/michelin.ts --
// which fetch small country-keyed CSVs straight from GitHub and cache
// them at module scope -- this goes through the API. Cities have no
// small static file to fetch: their source (tourist_cities_enhanced.json)
// is 27MB, which is fine to hold in server memory once and not fine to
// ship to a browser per page load. Same reason
// /api/destinations/cities/top10 exists as a route at all.
import { useEffect, useState } from "react";
import { API_BASE_URL } from "./apiBaseUrl";

export interface NearbyUnescoSite {
  name: string;
  category: string; // "Cultural" / "Natural" / "Mixed"
  distance_km: number;
}

export interface NearbyMichelinRestaurant {
  name: string;
  award: string; // "3 Stars" / "2 Stars" / "1 Star" / "Bib Gourmand" / "Selected Restaurants"
  cuisine: string;
  distance_km: number;
}

// One zoo / aquarium / botanical garden / US art museum near a city.
// Mirrors backend/app/main.py's NearbyPlace.
export interface NearbyPlace {
  name: string;
  // Narrower than the section it appears under, e.g. "Safari Park" inside
  // Aquariums & Zoos.
  kind: string;
  // "OpenStreetMap" or "IMLS" -- shown in the UI because the two aren't
  // equivalent in scope (IMLS is US-only, curated, and includes nature
  // centers; OSM is worldwide but community-mapped, so a sparse result may
  // mean under-mapping rather than nothing there).
  source: string;
  distance_km: number;
}

export interface NearbyPlaces {
  // True total within the radius; places[] is capped by the backend.
  count: number;
  places: NearbyPlace[];
}

// Mirrors backend/app/main.py's CityDetailResponse.
export interface CityDetail {
  city_id: string;
  // Properly-accented name (e.g. "Ōsaka") and its ASCII counterpart
  // ("Osaka"). Per project decision the UI displays city_ascii by
  // default -- see backend/app/data_loader.py's load_static_city_scores().
  city: string;
  city_ascii: string;
  country_name: string;
  country_code: string;
  admin_name: string | null;
  lat: number;
  lng: number;
  population: number | null;
  // The radius the two nearby lists below were filtered to (100), read
  // from the response rather than hardcoded here so headings can't drift
  // from what the backend actually returned.
  radius_km: number;
  // Full count within radius_km -- michelin_count in particular is
  // usually LARGER than michelin_restaurants.length, which the backend
  // caps at the nearest 10 (see CITY_DETAIL_MICHELIN_LIMIT).
  unesco_site_count: number;
  unesco_sites: NearbyUnescoSite[];
  michelin_count: number;
  michelin_restaurants: NearbyMichelinRestaurant[];
  unesco_score: number | null;
  michelin_score: number | null;
  price_score: number | null;
  // These four are null TOGETHER, and only when city_attractions.json hasn't
  // been generated in the backend's checkout (it comes from sources that
  // can't be pulled everywhere -- see
  // data/scripts/multiple/build_city_attractions.py). CityDetail hides those
  // sections entirely in that case, rather than telling someone a city has
  // no zoo when nobody has looked. A present-but-empty NearbyPlaces means
  // the opposite: we looked, there's nothing within the radius.
  attractions_radius_km: number | null;
  zoos_and_aquariums: NearbyPlaces | null;
  botanical_gardens: NearbyPlaces | null;
  // US-only (IMLS) -- merged into the Art Museums section alongside the
  // worldwide list from worldwide_museums.json, not shown as its own section.
  local_art_museums: NearbyPlaces | null;
}

// A 404 here means a city_id this project has never heard of (the
// backend's one deliberate exception to its "unknown -> null, not a 404"
// convention), which is what CityDetail.tsx renders its "City not found"
// state from -- so it's distinguished from a generic network/500 failure
// rather than collapsed into one error state.
export class CityNotFoundError extends Error {}

export async function fetchCityDetail(cityId: string): Promise<CityDetail> {
  const res = await fetch(`${API_BASE_URL}/api/destinations/cities/${encodeURIComponent(cityId)}`);
  if (res.status === 404) throw new CityNotFoundError(`No city with id ${cityId}`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  return (await res.json()) as CityDetail;
}

export type CityDetailLoadState =
  | { status: "loading" }
  | { status: "not-found" }
  | { status: "error" }
  | { status: "loaded"; city: CityDetail };

export function useCityDetail(cityId: string | undefined): CityDetailLoadState {
  const [state, setState] = useState<CityDetailLoadState>({ status: "loading" });

  useEffect(() => {
    if (!cityId) return;
    let cancelled = false;
    setState({ status: "loading" });

    fetchCityDetail(cityId)
      .then((city) => {
        if (cancelled) return;
        setState({ status: "loaded", city });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ status: err instanceof CityNotFoundError ? "not-found" : "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [cityId]);

  return state;
}

// e.g. "6 UNESCO World Heritage Sites within 100km". Counts here are
// small (the most any city has within 100km is 16), so unlike
// formatMichelinCountWithinRadius() below there's no rounding treatment
// -- same split lib/unesco.ts and lib/michelin.ts already make at the
// country level.
export function formatUnescoCountWithinRadius(count: number, radiusKm: number): string {
  return `${count} UNESCO World Heritage Site${count === 1 ? "" : "s"} within ${radiusKm}km`;
}

// Same rounding tiers as lib/michelin.ts's formatMichelinCount() (exact
// below 200, nearest 25 to 499, nearest 50 above that, both rounded
// tiers prefixed "Roughly"), with the radius appended -- city counts run
// into the hundreds just like country ones, so showing "556" would be
// the same false precision that rule exists to avoid.
export function formatMichelinCountWithinRadius(count: number, radiusKm: number): string {
  const roundingIncrement = count >= 500 ? 50 : count >= 200 ? 25 : null;
  const displayCount = roundingIncrement ? Math.round(count / roundingIncrement) * roundingIncrement : count;
  const prefix = roundingIncrement ? "Roughly " : "";
  return `${prefix}${displayCount} Michelin Guide Restaurant${displayCount === 1 ? "" : "s"} within ${radiusKm}km`;
}

// e.g. "3 within 100km", "1 within 100km". Used as the headline card above
// the Aquariums & Zoos / Botanical Gardens lists, where -- unlike the UNESCO
// and Michelin cards -- there's no single well-known name for the category to
// repeat, since the section heading already says it.
// Accent-, case- and punctuation-insensitive key for deciding whether two
// place names refer to the same place, e.g. "Musée d'Orsay" and "Musee
// d'Orsay" -> "musee d orsay". Same normalization as
// build_city_attractions.py's dedupe_key(), deliberately: that script merges
// OSM and IMLS entries for the same zoo, and CityDetail merges the
// worldwide_museums.json list with IMLS art museums, so both sides of the
// stack should agree on what "the same name" means.
export function placeNameKey(name: string): string {
  return name
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase()
    .replace(/[^\p{Letter}\p{Number}]+/gu, " ")
    .trim();
}

export function formatNearbyCount(count: number, radiusKm: number): string {
  return `${count} within ${radiusKm}km`;
}

// e.g. 17.6 -> "18km away", 0.2 -> "under 1km away". Distances come back
// with one decimal place, which reads as false precision for a
// day-trip-planning number -- and a restaurant 0.2km out shouldn't
// display as "0km away".
export function formatDistance(distanceKm: number): string {
  return distanceKm < 1 ? "under 1km away" : `${Math.round(distanceKm)}km away`;
}
