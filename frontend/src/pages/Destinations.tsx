import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

// Country-level overarching trip scores from data/scripts/build_overarching_trip_scores.py
// (see data/SCORING.md) -- plain unweighted average of UNESCO/Michelin/
// affordability, not yet traveler-profile-aware, so this page shows the
// same top 10 regardless of the interest/dates the user searched with.
// Fetched at request time from the repo's `main` branch rather than
// bundled, since the frontend has no backend of its own yet.
const SCORES_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.json";

interface CountryScore {
  country_name: string;
  overarching_score: number | null;
}

interface ScoresPayload {
  countries: Record<string, CountryScore>;
}

interface RankedDestination {
  code: string;
  name: string;
  score: number;
}

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; destinations: RankedDestination[] };

function topTenByOverarchingScore(payload: ScoresPayload): RankedDestination[] {
  return Object.entries(payload.countries)
    .filter((entry): entry is [string, CountryScore & { overarching_score: number }] => {
      const score = entry[1].overarching_score;
      return typeof score === "number";
    })
    .map(([code, country]) => ({
      code,
      name: country.country_name,
      score: country.overarching_score,
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

export default function Destinations() {
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const interest = searchParams.get("interest");
  const hasSearch = Boolean(startDate || endDate || interest);

  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    fetch(SCORES_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
        return res.json() as Promise<ScoresPayload>;
      })
      .then((payload) => {
        if (cancelled) return;
        setLoadState({ status: "loaded", destinations: topTenByOverarchingScore(payload) });
      })
      .catch(() => {
        if (cancelled) return;
        setLoadState({
          status: "error",
          message: "Couldn't load destination scores. Try again in a moment.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="page">
      <h1>Destinations</h1>
      <p className="tagline">
        {hasSearch
          ? "Thanks -- here's what you searched for. Full personalized recommendations are coming soon; for now, here are the top-scoring destinations overall."
          : "Top-scoring destinations overall, by our trip score. Personalized recommendations are coming soon."}
      </p>

      {hasSearch && (
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
