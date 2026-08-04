import { Link } from "react-router";

const DATA_SOURCES = [
  { name: "Michelin Guide", url: "https://guide.michelin.com/en" },
  { name: "UNESCO", url: "https://www.unesco.org/en" },
  { name: "World Bank Open Data", url: "https://data.worldbank.org" },
  { name: "Weather from Open-Meteo", url: "https://open-meteo.com" },
  { name: "Visa requirements from Passport Index", url: "https://www.passportindex.org" },
  // Airport data (OpenFlights) is pulled in data/ but isn't wired into
  // any score or shown anywhere on the site yet -- re-enable once it
  // actually feeds something user-facing.
  // { name: "Airports from OpenFlights", url: "https://openflights.org/" },
] as const;

export default function About() {
  return (
    <main className="page">
      <h1>About</h1>
      <p className="tagline">
        This site helps recommend destinations based on your travel dates
        and other preferences.
      </p>

      <h2>Data used</h2>
      <ul className="about-sources">
        {DATA_SOURCES.map((source) => (
          <li key={source.name}>
            <a href={source.url} target="_blank" rel="noreferrer">
              {source.name}
            </a>
          </li>
        ))}
        {/* Internal route, not an external source -- kept last since it's
            a secondary/deeper-dive link rather than a top-level source. */}
        <li>
          <Link to="/country-specific-sources">Country Specific sources</Link>
        </li>
      </ul>
    </main>
  );
}
