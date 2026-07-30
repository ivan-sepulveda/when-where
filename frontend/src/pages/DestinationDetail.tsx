import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { getCountryByCode } from "../lib/countries";
import { countryCodeToFlagEmoji } from "../lib/flagEmoji";
import { formatMichelinCount, getMichelinAwardCounts } from "../lib/michelin";

type MichelinLoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; count: number };

// Placeholder page for /destinations/:country. One template serves every
// ISO 3166-1 alpha-2 code -- real content (overarching score, monthly
// breakdown, factor detail) lands here once that data is wired up.
export default function DestinationDetail() {
  const { country: countryParam } = useParams<{ country: string }>();
  const country = countryParam ? getCountryByCode(countryParam) : undefined;

  const [michelin, setMichelin] = useState<MichelinLoadState>({ status: "loading" });

  useEffect(() => {
    if (!country) return;
    let cancelled = false;
    setMichelin({ status: "loading" });

    getMichelinAwardCounts()
      .then((counts) => {
        if (cancelled) return;
        setMichelin({ status: "loaded", count: counts.get(country.code) ?? 0 });
      })
      .catch(() => {
        if (cancelled) return;
        setMichelin({ status: "error" });
      });

    return () => {
      cancelled = true;
    };
  }, [country]);

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
      </ul>
    </main>
  );
}
