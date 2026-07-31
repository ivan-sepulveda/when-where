// Shortest known flight between two countries, from
// data/processed/multiple/shortest_route_connecting_countries.json (see
// build_shortest_route_connecting_countries.py). That file is a
// finished, one-time derivation from a static Kaggle routes snapshot
// (not an in-progress pull like lib/hiking.ts's OSM data) -- so a
// country pair missing from it is treated as a real "no route recorded
// between these two countries in this dataset" fact, not "check back
// later."
import { useEffect, useState } from "react";
import type { Country } from "./countries";

const SHORTEST_ROUTE_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/multiple/shortest_route_connecting_countries.json";

export interface ShortestFlight {
  distanceKm: number;
  departureAirport: string;
  destinationAirport: string;
}

interface ShortestRouteResponse {
  countries: Record<
    string,
    Record<string, { distance_km: number; departure_airport: string; destination_airport: string }>
  >;
}

// departure country -> destination country -> shortest flight. Cached at
// module scope so every DestinationDetail page fetches the JSON at most
// once per session -- same pattern as lib/michelin.ts/lib/hiking.ts/etc.
let shortestRoutesPromise: Promise<
  Map<string, Map<string, ShortestFlight>>
> | null = null;

export function getShortestRoutes(): Promise<Map<string, Map<string, ShortestFlight>>> {
  if (!shortestRoutesPromise) shortestRoutesPromise = loadShortestRoutes();
  return shortestRoutesPromise;
}

async function loadShortestRoutes(): Promise<Map<string, Map<string, ShortestFlight>>> {
  const res = await fetch(SHORTEST_ROUTE_URL);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as ShortestRouteResponse;

  const byDeparture = new Map<string, Map<string, ShortestFlight>>();
  for (const [departureCode, destinations] of Object.entries(payload.countries)) {
    const byDestination = new Map<string, ShortestFlight>();
    for (const [destinationCode, route] of Object.entries(destinations)) {
      byDestination.set(destinationCode, {
        distanceKm: route.distance_km,
        departureAirport: route.departure_airport,
        destinationAirport: route.destination_airport,
      });
    }
    byDeparture.set(departureCode, byDestination);
  }
  return byDeparture;
}

// formatShortestFlight({distanceKm: 8071.4, departureAirport: "IAH",
// destinationAirport: "CDG"}) -> "Shortest Flight: IAH to CDG 8071km"
export function formatShortestFlight(flight: ShortestFlight): string {
  return `Shortest Flight: ${flight.departureAirport} to ${flight.destinationAirport} ${Math.round(flight.distanceKm)}km`;
}

export type ShortestFlightLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; flight: ShortestFlight | null }; // null = no route recorded for this country pair

// departureCountry is the "Departing from" country picked in NavBar (see
// lib/departureCountry.tsx), destinationCountry is whichever
// DestinationDetail page this is.
export function useShortestFlight(
  departureCountry: Country | undefined,
  destinationCountry: Country | undefined,
): ShortestFlightLoadState {
  const [state, setState] = useState<ShortestFlightLoadState>({ status: "loading" });

  useEffect(() => {
    if (!departureCountry || !destinationCountry) return;
    let cancelled = false;
    setState({ status: "loading" });

    getShortestRoutes()
      .then((byDeparture) => {
        if (cancelled) return;
        const flight = byDeparture.get(departureCountry.code)?.get(destinationCountry.code) ?? null;
        setState({ status: "loaded", flight });
      })
      .catch(() => {
        if (cancelled) return;
        setState({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [departureCountry, destinationCountry]);

  return state;
}
