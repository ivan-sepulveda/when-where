import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { API_BASE_URL } from "../lib/apiBaseUrl";

// Static fallback: build_overarching_trip_scores.py's output (UNESCO +
// Michelin + affordability only, no weather), read straight from GitHub.
// Used when there's no date range to work with -- e.g. the user clicked
// "Destinations" in the nav instead of searching. Cities don't have an
// equivalent static-fallback file to fetch directly (their equivalent,
// tourist_cities_enhanced.json, is 27MB -- see
// backend/app/data_loader.py's load_static_city_scores() docstring), so
// the city section below always goes through the backend instead, dates
// or not.
const STATIC_COUNTRY_SCORES_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.json";

// Both backend endpoints return up to 10 ranked results (they're literally
// named .../top10) -- this just trims to the 5 actually displayed here,
// rather than changing what the API returns. Easy to bump back up later;
// change this one constant, not the API.
const DISPLAY_COUNT = 5;

interface RankedCountryDestination {
  code: string;
  name: string;
  score: number;
}

interface RankedCityDestination {
  cityId: string;
  // city_ascii, not the properly-accented `city` field -- per project
  // decision, this is the name the frontend should default to
  // displaying (see backend/app/data_loader.py's
  // load_static_city_scores() docstring).
  name: string;
  countryName: string;
  score: number;
}

type CountryLoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; destinations: RankedCountryDestination[] };

type CityLoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; destinations: RankedCityDestination[] };

interface StaticCountryScoresPayload {
  countries: Record<string, { country_name: string; overarching_score: number | null }>;
}

interface TopCountryDestinationsResponse {
  destinations: {
    country: string;
    country_name: string;
    trip_score: number;
  }[];
}

interface TopCityDestinationsResponse {
  destinations: {
    city_id: string;
    city_ascii: string;
    country_name: string;
    trip_score: number;
  }[];
}

function rankStaticCountryScores(payload: StaticCountryScoresPayload): RankedCountryDestination[] {
  return Object.entries(payload.countries)
    .filter((entry): entry is [string, { country_name: string; overarching_score: number }] => {
      return typeof entry[1].overarching_score === "number";
    })
    .map(([code, country]) => ({ code, name: country.country_name, score: country.overarching_score }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 10);
}

async function fetchCountryDateAwareTopTen(startDate: string, endDate: string): Promise<RankedCountryDestination[]> {
  const params = new URLSearchParams({ start_date: startDate, end_date: endDate });
  const res = await fetch(`${API_BASE_URL}/api/destinations/top10?${params.toString()}`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as TopCountryDestinationsResponse;
  return payload.destinations.map((d) => ({ code: d.country, name: d.country_name, score: d.trip_score }));
}

async function fetchCountryStaticTopTen(): Promise<RankedCountryDestination[]> {
  const res = await fetch(STATIC_COUNTRY_SCORES_URL);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as StaticCountryScoresPayload;
  return rankStaticCountryScores(payload);
}

// Unlike the country fetchers above, this is the ONLY way cities/top10
// gets fetched -- start/end are optional query params (both included
// together, or neither), since the backend endpoint itself handles both
// the static and date-aware cases (see main.py's top_city_destinations()
// docstring for why, in short: no small static file to fetch directly
// the way countries have one).
async function fetchCityTopTen(startDate: string | null, endDate: string | null): Promise<RankedCityDestination[]> {
  const params = new URLSearchParams();
  if (startDate && endDate) {
    params.set("start_date", startDate);
    params.set("end_date", endDate);
  }
  const query = params.toString();
  const res = await fetch(`${API_BASE_URL}/api/destinations/cities/top10${query ? `?${query}` : ""}`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as TopCityDestinationsResponse;
  return payload.destinations.map((d) => ({
    cityId: d.city_id,
    name: d.city_ascii,
    countryName: d.country_name,
    score: d.trip_score,
  }));
}

export default function Destinations() {
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const interest = searchParams.get("interest");
  const hasDateRange = Boolean(startDate && endDate);

  const [countryLoadState, setCountryLoadState] = useState<CountryLoadState>({ status: "loading" });
  const [cityLoadState, setCityLoadState] = useState<CityLoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setCountryLoadState({ status: "loading" });

    const load =
      hasDateRange && startDate && endDate
        ? fetchCountryDateAwareTopTen(startDate, endDate)
        : fetchCountryStaticTopTen();

    load
      .then((destinations) => {
        if (cancelled) return;
        setCountryLoadState({ status: "loaded", destinations });
      })
      .catch(() => {
        if (cancelled) return;
        setCountryLoadState({
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

  useEffect(() => {
    let cancelled = false;
    setCityLoadState({ status: "loading" });

    fetchCityTopTen(startDate, endDate)
      .then((destinations) => {
        if (cancelled) return;
        setCityLoadState({ status: "loaded", destinations });
      })
      .catch(() => {
        if (cancelled) return;
        setCityLoadState({
          status: "error",
          message: hasDateRange
            ? "Couldn't load top cities for those dates. Try again in a moment."
            : "Couldn't load top cities. Try again in a moment.",
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

      <h2>Top 5 Cities</h2>

      {cityLoadState.status === "loading" && <p>Loading top cities...</p>}

      {cityLoadState.status === "error" && <p role="alert">{cityLoadState.message}</p>}

      {cityLoadState.status === "loaded" && (
        <ol className="destinations-ranked-list">
          {cityLoadState.destinations.slice(0, DISPLAY_COUNT).map((destination, index) => (
            <li key={destination.cityId} className="destinations-ranked-item">
              {/* Not a Link -- there's no per-city detail page yet, so
                  these rows are display-only for now (see
                  .destinations-ranked-static in index.css for the
                  non-interactive styling variant). */}
              <div className="destinations-ranked-static">
                <span className="destinations-ranked-position">{index + 1}</span>
                <span className="destinations-ranked-name">
                  {destination.name}, {destination.countryName}
                </span>
                <span className="destinations-ranked-score">{destination.score.toFixed(2)}</span>
              </div>
            </li>
          ))}
        </ol>
      )}

      <h2>Top 5 Countries</h2>

      {countryLoadState.status === "loading" && <p>Loading top destinations...</p>}

      {countryLoadState.status === "error" && <p role="alert">{countryLoadState.message}</p>}

      {countryLoadState.status === "loaded" && (
        <ol className="destinations-ranked-list">
          {countryLoadState.destinations.slice(0, DISPLAY_COUNT).map((destination, index) => (
            <li key={destination.code} className="destinations-ranked-item">
              <Link
                to={{
                  pathname: `/destinations/${destination.code}`,
                  search: searchParams.toString(),
                }}
                className="destinations-ranked-link"
              >
                <span className="destinations-ranked-position">{index + 1}</span>
                <span className="destinations-ranked-name">{destination.name}</span>
                <span className="destinations-ranked-score">{destination.score.toFixed(2)}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
