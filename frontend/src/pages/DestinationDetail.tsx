import { Link, useParams } from "react-router";
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

      <ul className="destination-detail-stats">
        {michelin.status === "loading" && <li>Loading Michelin Guide data...</li>}
        {michelin.status === "error" && <li role="alert">Couldn't load Michelin Guide data.</li>}
        {michelin.status === "loaded" && <li>{formatMichelinCount(michelin.count)}</li>}

        {unesco.status === "loading" && <li>Loading UNESCO World Heritage Site data...</li>}
        {unesco.status === "error" && <li role="alert">Couldn't load UNESCO World Heritage Site data.</li>}
        {unesco.status === "loaded" && <li>{formatUnescoCount(unesco.count)}</li>}
      </ul>
    </main>
  );
}
