import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { formatDateRange } from "../lib/formatDate";
import { getCountryByCode } from "../lib/countries";
import { countryCodeToFlagEmoji } from "../lib/flagEmoji";
import { formatMichelinCount, getMichelinAwardCounts } from "../lib/michelin";
import { formatUnescoCount, getUnescoSiteCounts } from "../lib/unesco";
import { useCountryStatCount } from "../lib/useCountryStatCount";
import { fetchCountryWeather, formatWeatherStats, type WeatherMetrics } from "../lib/weather";

type WeatherLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; metrics: WeatherMetrics | null };

// Placeholder page for /destinations/:country. One template serves every
// ISO 3166-1 alpha-2 code -- real content (overarching score, monthly
// breakdown, factor detail) lands here once that data is wired up.
export default function DestinationDetail() {
  const { country: countryParam } = useParams<{ country: string }>();
  const country = countryParam ? getCountryByCode(countryParam) : undefined;

  // Carried over from the Destinations search (see Destinations.tsx's
  // Link, which forwards its own searchParams). Displayed as-is, and
  // also used below to fetch date-weighted weather for this country.
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const hasDateRange = Boolean(startDate && endDate);

  const michelin = useCountryStatCount(country, getMichelinAwardCounts);
  const unesco = useCountryStatCount(country, getUnescoSiteCounts);

  const [weather, setWeather] = useState<WeatherLoadState>({ status: "loading" });

  useEffect(() => {
    if (!country || !startDate || !endDate) return;
    let cancelled = false;
    setWeather({ status: "loading" });

    fetchCountryWeather(country.code, startDate, endDate)
      .then((metrics) => {
        if (cancelled) return;
        setWeather({ status: "loaded", metrics });
      })
      .catch(() => {
        if (cancelled) return;
        setWeather({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [country, startDate, endDate]);

  if (!country) {
    return (
      <main className="page">
        <h1>Destination not found</h1>
        <p className="tagline">
          "{countryParam}" isn't a recognized country code.{" "}
          <Link to="/destinations">Back to destinations</Link>
        </p>
      </main>
    );
  }

  return (
    <main className="page">
      <h1>
        {countryCodeToFlagEmoji(country.code)} {country.name}
      </h1>
      <p className="tagline">
        Trip scores and monthly breakdowns for {country.name} are coming
        soon. <Link to="/destinations">Back to destinations</Link>
      </p>

      {hasDateRange && startDate && endDate && (
        <p className="destination-detail-dates">Your dates: {formatDateRange(startDate, endDate)}</p>
      )}

      <ul className="destination-detail-stats">
        <li className="destination-detail-stat-card">
          {michelin.status === "loading" && "Loading Michelin Guide data..."}
          {michelin.status === "error" && <span role="alert">Couldn't load Michelin Guide data.</span>}
          {michelin.status === "loaded" && formatMichelinCount(michelin.count)}
        </li>

        <li className="destination-detail-stat-card">
          {unesco.status === "loading" && "Loading UNESCO World Heritage Site data..."}
          {unesco.status === "error" && (
            <span role="alert">Couldn't load UNESCO World Heritage Site data.</span>
          )}
          {unesco.status === "loaded" && formatUnescoCount(unesco.count)}
        </li>
      </ul>

      {hasDateRange && (
        <>
          <h2>Weather for your dates</h2>
          <ul className="destination-detail-stats">
            {weather.status === "loading" && (
              <li className="destination-detail-stat-card">Loading weather data...</li>
            )}
            {weather.status === "error" && (
              <li className="destination-detail-stat-card" role="alert">
                Couldn't load weather data for those dates.
              </li>
            )}
            {weather.status === "loaded" && weather.metrics === null && (
              <li className="destination-detail-stat-card">
                No weather data available for {country.name} yet.
              </li>
            )}
            {weather.status === "loaded" &&
              weather.metrics !== null &&
              formatWeatherStats(weather.metrics).map((stat) => (
                <li key={stat.label} className="destination-detail-stat-card">
                  {stat.label}: {stat.value}
                </li>
              ))}
          </ul>
        </>
      )}
    </main>
  );
}
