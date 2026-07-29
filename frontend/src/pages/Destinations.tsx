import { useSearchParams } from "react-router";

// General/placeholder destinations page -- no backend or scoring engine
// wired up to the frontend yet (that work lives in data/scripts, see the
// top-level README). This just confirms the route works end to end and
// echoes back whatever was searched for, if anything.
export default function Destinations() {
  const [searchParams] = useSearchParams();
  const startDate = searchParams.get("start_date");
  const endDate = searchParams.get("end_date");
  const interest = searchParams.get("interest");
  const hasSearch = Boolean(startDate || endDate || interest);

  return (
    <main className="page">
      <h1>Destinations</h1>
      <p className="tagline">
        {hasSearch
          ? "Thanks -- here's what you searched for. Real recommendations are coming soon."
          : "Browse destinations. Recommendations aren't wired up yet -- check back soon."}
      </p>

      {hasSearch && (
        <ul className="destinations-search-summary">
          {startDate && <li>Start date: {startDate}</li>}
          {endDate && <li>End date: {endDate}</li>}
          {interest && <li>Interest: {interest}</li>}
        </ul>
      )}
    </main>
  );
}
