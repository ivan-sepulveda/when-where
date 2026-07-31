// Hiking trail counts (OpenStreetMap Overpass API route=hiking relation
// count) by country, from
// data/processed/multiple/HIKING_TRAILS_BY_COUNTRY.csv (see
// fetch_hiking_trails.py).
//
// Unlike MICHELIN_SCORE_BY_COUNTRY.csv/UNESCO_SCORE_BY_COUNTRY.csv (which
// cover every country with a real number, including real zeros),
// fetch_hiking_trails.py is a resumable, still-in-progress pull -- as of
// this writing under half the countries this project tracks have been
// fetched at all. A country can show up here three different ways:
// absent from the CSV entirely (not attempted yet), present with a blank
// HIKING_ROUTE_COUNT (attempted, but the Overpass query failed -- see
// that script's docstring), or present with a real count, including a
// real 0 (attempted, query succeeded, OSM just has no tagged hiking
// routes there). Only the third case is a real number here -- the first
// two both mean "no data," not "zero trails," so both are left out of
// the returned map rather than defaulting to 0 the way
// countryStatsCsv.loadCountryCountCsv() would.
import { useEffect, useState } from "react";
import type { Country } from "./countries";
import { parseCsv } from "./countryStatsCsv";

const HIKING_TRAILS_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/multiple/HIKING_TRAILS_BY_COUNTRY.csv";

// code -> hiking trail count, omitting countries with no data yet (see
// above). Cached at module scope so every DestinationDetail page fetches
// the CSV at most once per session -- same pattern as
// lib/michelin.ts/lib/unesco.ts.
let trailCountsPromise: Promise<Map<string, number>> | null = null;

export function getHikingTrailCounts(): Promise<Map<string, number>> {
  if (!trailCountsPromise) trailCountsPromise = loadHikingTrailCounts();
  return trailCountsPromise;
}

async function loadHikingTrailCounts(): Promise<Map<string, number>> {
  const res = await fetch(HIKING_TRAILS_URL);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const text = await res.text();

  const [, ...dataRows] = parseCsv(text).filter((row) => row.length >= 3 && row[0]);

  const counts = new Map<string, number>();
  for (const [code, , countRaw] of dataRows) {
    if (countRaw === "") continue; // not fetched yet or the query failed -- no data, not a real zero
    counts.set(code, Number(countRaw));
  }
  return counts;
}

// formatHikingTrailCount(1) -> "1 Hiking Trail",
// formatHikingTrailCount(555) -> "555 Hiking Trails". No rounding --
// Overpass relation counts don't have Michelin's false-precision-at-scale
// problem (the biggest count so far, Germany's 53,390, is still an exact
// tag count, not an estimate).
export function formatHikingTrailCount(count: number): string {
  return `${count} Hiking Trail${count === 1 ? "" : "s"}`;
}

export type HikingTrailLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; count: number | null }; // null = no data yet for this country, not a real zero

// Deliberately not built on the shared useCountryStatCount() hook
// (src/lib/useCountryStatCount.ts) -- that hook defaults a country
// missing from the map to a count of 0, which is correct for
// Michelin/UNESCO (every real country has a genuine number there) but
// would misrepresent "not fetched yet" as "OSM has zero hiking trails"
// here. Same loaded-but-nullable shape as lib/weather.ts's
// CountryWeather, for the same "unknown, not zero" reason.
export function useHikingTrailCount(country: Country | undefined): HikingTrailLoadState {
  const [state, setState] = useState<HikingTrailLoadState>({ status: "loading" });

  useEffect(() => {
    if (!country) return;
    let cancelled = false;
    setState({ status: "loading" });

    getHikingTrailCounts()
      .then((counts) => {
        if (cancelled) return;
        setState({ status: "loaded", count: counts.get(country.code) ?? null });
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
