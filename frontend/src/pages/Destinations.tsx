import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

// Static fallback: build_overarching_trip_scores.py's output (UNESCO +
// Michelin + affordability only, no weather), read straight from GitHub.
// Used when there's no date range to work with -- e.g. the user clicked
// "Destinations" in the nav instead of searching.
const STATIC_SCORES_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.json";

// The real, date-aware ranking -- see backend/README.md. Adds a weather
// score resolved against the trip's actual month(s) on top of the three
// static domains above. VITE_API_BASE_URL is set per-environment (see
// frontend/.env.local.example); falls back to the local dev default so
// this doesn't silently break if the env var isn't set.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

interface RankedDestination {
  code: string;
  name: string;
  score: number;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; destinations: RankedDestination[]; dateAware: boolean };

interface StaticScoresPayload {
  countries: Record<string, { country_name: string; overarching_score: number | null }>;
}

interface TopDestinationsResponse {
  destinations: {
    country: string;
    country_name: string;
    trip_score: number;
  }[];
}

function rankStaticScores(payload: StaticScoresPayload): RankedDestination[] {
  return Object.entries(payload.countries)
    .filter((entry): entry is [string, { country_name: string; overarching_score: number }] => {
      return typeof entry[1].overarching_score === "number";
    })
    .map(([code, country]) => ({ code, name: country.country_name, score: country.overarching_score }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

async function fetchDateAwareTopTen(startDate: string, endDate: string): Promise<RankedDestination[]> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  const res = await fetch(`${API_BASE_URL}/api/destinations/top10?${params.toString()}`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as TopDestinationsResponse;
  return payload.destinations.map((d) => ({ code: d.country, name: d.country_name, score: d.trip_score }));
}

async function fetchStaticTopTen(): Promise<RankedDestination[]> {
  const res = await fetch(STATIC_SCORES_URL);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as StaticScoresPayload;
  return rankStaticScores(payload);
}

export default function Destinations() {
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const interest = searchParams.get("interest");
  const hasDateRange = Boolean(startDate && endDate);

  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setLoadState({ status: "loading" });

    const load = hasDateRange && startDate && endDate
      ? fetchDateAwareTopTen(startDate, endDate).then((destinations) => ({ destinations, dateAware: true }))
      : fetchStaticTopTen().then((destinations) => ({ destinations, dateAware: false }));

    load
      .then(({ destinations, dateAware }) => {
        if (cancelled) return;
        setLoadState({ status: "loaded", destinations, dateAware });
      })
      .catch(() => {
        if (cancelled) return;
        setLoadState({
          status: "error",
          message: hasDateRange
            ? "Couldn't load destination scores for those dates. Try again in a moment."
            : "Couldn't load destination scores. Try again in a moment.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [hasDateRange, startDate, endDate]);

  return (
    <main className="page">
      <h1>Destinations</h1>
      <p className="tagline">
        {hasDateRange
          ? "Ranked for your dates, including seasonal weather. Personalized-by-interest recommendations are coming soon."
          : "Top-scoring destinations overall (no dates given, so this doesn't factor in weather yet). Search with dates for a seasonal ranking."}
      </p>

      {(startDate || endDate || interest) && (
        <ul className="destinations-search-summary">
          {startDate && <li>Start date: {startDate}</li>}
          {endDate && <li>End date: {endDate}</li>}
          {interest && <li>Interest: {interest}</li>}
        </ul>
      )}

      {loadState.status === "loading" && <p>Loading top destinations...</p>}

      {loadState.status === "error" && <p role="alert">{loadState.message}</p>}

      {loadState.status === "loaded" && (
        <ol className="destinations-ranked-list">
          {loadState.destinations.map((destination, index) => (
            <li key={destination.code} className="destinations-ranked-item">
              <span className="destinations-ranked-position">{index + 1}</span>
              <span className="destinations-ranked-name">{destination.name}</span>
              <span className="destinations-ranked-score">{destination.score.toFixed(2)}</span>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
