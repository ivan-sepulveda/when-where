import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import TravelAdvisoryIcon from "../components/TravelAdvisoryIcon";
import { API_BASE_URL } from "../lib/apiBaseUrl";
import { useDepartureCountry } from "../lib/departureCountry";
import {
  getTravelAdvisories,
  getTravelAdvisoryForCode,
  type TravelAdvisoriesByCountry,
} from "../lib/travelAdvisories";

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
// named .../top10), which is also the ceiling the "Top 5 / Top 10" count
// dropdown offers below -- so switching to Top 10 is just a wider slice()
// of data already in hand, never a new fetch.
type DestinationsCount = 5 | 10;
const DEFAULT_COUNT: DestinationsCount = 5;

function parseCount(raw: string | null): DestinationsCount {
  return raw === "10" ? 10 : DEFAULT_COUNT;
}

// Which section(s) the "Show" dropdown displays. Kept in the "view" URL
// search param (like start_date/end_date/interest) rather than plain
// component state, so a filtered view is shareable/bookmarkable and
// survives a refresh. "countries" is the default and is never actually
// written to the URL -- see setView() below -- so a plain /destinations
// link still means "countries only". Cities are temporarily de-emphasized
// (the data and the /api/destinations/cities/top10 endpoint are
// unchanged), so seeing them is now an explicit opt-in via this dropdown;
// flipping DEFAULT_VIEW back to "both" is the whole revert.
type DestinationsView = "both" | "countries" | "cities";
const DEFAULT_VIEW: DestinationsView = "countries";

function parseView(raw: string | null): DestinationsView {
  return raw === "both" || raw === "cities" ? raw : DEFAULT_VIEW;
}

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
  // iso2 -- needed to look up this city's country in VISA_REQUIREMENTS
  // (keyed by iso2, not countryName -- see visaLabel()'s comment below
  // for why a name-string join wouldn't work here).
  countryCode: string;
  score: number;
}

// destination iso2 -> requirement string (e.g. "VISA-FREE 30"), for the
// CURRENT departure country only -- see fetchVisaRequirements() below.
type VisaRequirementsByDestination = Record<string, string>;

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
    country_code: string;
    trip_score: number;
  }[];
}

interface VisaRequirementsResponse {
  requirements: Record<string, string>;
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
    countryCode: d.country_code,
    score: d.trip_score,
  }));
}

// All of the current departure country's visa requirements in one call
// (backend/app/main.py's visa_requirements()), rather than one request
// per destination row -- 10 rows, one fetch. Empty object (not a throw)
// for a departure country with no visa data at all, same "unknown, not
// an error" convention the rest of this file's fetchers follow for
// missing data.
async function fetchVisaRequirements(departureCountryCode: string): Promise<VisaRequirementsByDestination> {
  const res = await fetch(`${API_BASE_URL}/api/destinations/${departureCountryCode}/visa-requirements`);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const payload = (await res.json()) as VisaRequirementsResponse;
  return payload.requirements;
}

export default function Destinations() {
  const [searchParams, setSearchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const interest = searchParams.get("interest");
  const hasDateRange = Boolean(startDate && endDate);

  const view = parseView(searchParams.get("view"));
  const showCities = view === "both" || view === "cities";
  const showCountries = view === "both" || view === "countries";

  function setView(next: DestinationsView) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next === DEFAULT_VIEW) {
        params.delete("view");
      } else {
        params.set("view", next);
      }
      return params;
    });
  }

  // Per-section count -- Top 5 or Top 10 EACH, not a combined total. With
  // both sections showing, Top 5 is 5 countries + 5 cities (10 total) and
  // Top 10 is 10 + 10 (20 total); with just one section showing, it's
  // just that section's 5 or 10.
  const count = parseCount(searchParams.get("count"));

  function setCount(next: DestinationsCount) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next === DEFAULT_COUNT) {
        params.delete("count");
      } else {
        params.set("count", String(next));
      }
      return params;
    });
  }

  const { countryCode: departureCountryCode } = useDepartureCountry();

  const [countryLoadState, setCountryLoadState] = useState<CountryLoadState>({ status: "loading" });
  const [cityLoadState, setCityLoadState] = useState<CityLoadState>({ status: "loading" });
  // Not modeled as a loading/error state like the two above -- a failed
  // or still-in-flight fetch just means no parenthetical shows yet,
  // which shouldn't block or error out the country/city lists it
  // annotates. Empty object is also the correct "no data" state, not
  // just the loading placeholder.
  const [visaRequirements, setVisaRequirements] = useState<VisaRequirementsByDestination>({});
  // Same "empty object is a valid no-data state, not an error" convention
  // as visaRequirements above -- fetched once (doesn't depend on
  // departure country), so no dependency array churn needed.
  const [travelAdvisories, setTravelAdvisories] = useState<TravelAdvisoriesByCountry>({});

  useEffect(() => {
    let cancelled = false;
    setVisaRequirements({});

    fetchVisaRequirements(departureCountryCode)
      .then((requirements) => {
        if (cancelled) return;
        setVisaRequirements(requirements);
      })
      .catch(() => {
        // Silently leave visaRequirements empty -- see comment on the
        // state declaration above.
      });

    return () => {
      cancelled = true;
    };
  }, [departureCountryCode]);

  useEffect(() => {
    let cancelled = false;

    getTravelAdvisories()
      .then((advisories) => {
        if (cancelled) return;
        setTravelAdvisories(advisories);
      })
      .catch(() => {
        // Silently leave travelAdvisories empty -- see comment on the
        // state declaration above.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // "(VISA-FREE 30)" for a destination this project has visa data for,
  // "" (nothing rendered) otherwise -- e.g. no visa data for that
  // departure/destination pair yet, or the departure country itself
  // isn't one visa_requirements.json covers.
  function visaLabel(destinationCountryCode: string): string {
    const requirement = visaRequirements[destinationCountryCode.toUpperCase()];
    return requirement ? ` (${requirement})` : "";
  }

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
    // Runs on every load, including the countries-only default view where
    // the city list isn't rendered -- deliberately kept warm so switching
    // the dropdown to "cities" or "both" shows results immediately
    // instead of a loading flash. Deps stay off `showCities` for the same
    // reason: toggling the view should never refetch.
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

      <div className="destinations-controls">
        <label className="destinations-view-control">
          Show:{" "}
          <select
            value={view}
            onChange={(e) => setView(e.target.value as DestinationsView)}
            className="destinations-view-select"
          >
            <option value="countries">See Countries (Default)</option>
            <option value="cities">See Cities</option>
            <option value="both">Both</option>
          </select>
        </label>

        <label className="destinations-view-control">
          Results:{" "}
          <select
            value={count}
            onChange={(e) => setCount(Number(e.target.value) as DestinationsCount)}
            className="destinations-view-select"
          >
            <option value={5}>Top 5{view === "both" ? " (each)" : ""}</option>
            <option value={10}>Top 10{view === "both" ? " (each)" : ""}</option>
          </select>
        </label>
      </div>

      {showCities && (
        <>
          <h2>Top {count} Cities</h2>

          {cityLoadState.status === "loading" && <p>Loading top cities...</p>}

          {cityLoadState.status === "error" && <p role="alert">{cityLoadState.message}</p>}

          {cityLoadState.status === "loaded" && (
            <ol className="destinations-ranked-list">
              {cityLoadState.destinations.slice(0, count).map((destination, index) => (
                <li key={destination.cityId} className="destinations-ranked-item">
                  {/* Links by cityId (a simplemaps_id), never by name --
                      city names aren't unique in this dataset (two real
                      cities are both named "Kanpur"). Forwards the
                      current searchParams the same way the country rows
                      below do, so CityDetail inherits the searched dates
                      and can show weather for them. */}
                  <Link
                    to={{
                      pathname: `/destinations/cities/${destination.cityId}`,
                      search: searchParams.toString(),
                    }}
                    className="destinations-ranked-link"
                  >
                    <span className="destinations-ranked-position">{index + 1}</span>
                    <span className="destinations-ranked-name">
                      {destination.name}, {destination.countryName}
                      {getTravelAdvisoryForCode(travelAdvisories, destination.countryCode) && (
                        <TravelAdvisoryIcon
                          advisory={getTravelAdvisoryForCode(travelAdvisories, destination.countryCode)!}
                        />
                      )}
                      <span className="destinations-ranked-visa">{visaLabel(destination.countryCode)}</span>
                    </span>
                    <span className="destinations-ranked-score">{destination.score.toFixed(2)}</span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </>
      )}

      {showCountries && (
        <>
          <h2>Top {count} Countries</h2>

          {countryLoadState.status === "loading" && <p>Loading top destinations...</p>}

          {countryLoadState.status === "error" && <p role="alert">{countryLoadState.message}</p>}

          {countryLoadState.status === "loaded" && (
            <ol className="destinations-ranked-list">
              {countryLoadState.destinations.slice(0, count).map((destination, index) => (
                <li key={destination.code} className="destinations-ranked-item">
                  <Link
                    to={{
                      pathname: `/destinations/${destination.code}`,
                      search: searchParams.toString(),
                    }}
                    className="destinations-ranked-link"
                  >
                    <span className="destinations-ranked-position">{index + 1}</span>
                    <span className="destinations-ranked-name">
                      {destination.name}
                      {getTravelAdvisoryForCode(travelAdvisories, destination.code) && (
                        <TravelAdvisoryIcon
                          advisory={getTravelAdvisoryForCode(travelAdvisories, destination.code)!}
                        />
                      )}
                      <span className="destinations-ranked-visa">{visaLabel(destination.code)}</span>
                    </span>
                    <span className="destinations-ranked-score">{destination.score.toFixed(2)}</span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </main>
  );
}
