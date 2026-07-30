import { Link, useParams, useSearchParams } from "react-router";
import { formatDateRange } from "../lib/formatDate";
import { getCountryByCode } from "../lib/countries";
import { countryCodeToFlagEmoji } from "../lib/flagEmoji";
import { formatMichelinCount, getMichelinAwardCounts } from "../lib/michelin";
import { formatUnescoCount, getUnescoSiteCounts } from "../lib/unesco";
import { useCountryStatCount } from "../lib/useCountryStatCount";

// Placeholder page for /destinations/:country. One template serves every
// ISO 3166-1 alpha-2 code -- real content (overarching score, monthly
// breakdown, factor detail) lands here once that data is wired up.
export default function DestinationDetail() {
  const { country: countryParam } = useParams<{ country: string }>();
  const country = countryParam ? getCountryByCode(countryParam) : undefined;

  // Carried over from the Destinations search (see Destinations.tsx's
  // Link, which forwards its own searchParams) -- not used to fetch
  // anything on this page yet, just displayed back to the user.
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const hasDateRange = Boolean(startDate && endDate);

  const michelin = useCountryStatCount(country, getMichelinAwardCounts);
  const unesco = useCountryStatCount(country, getUnescoSiteCounts);

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
    </main>
  );
}
