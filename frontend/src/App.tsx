import { useMemo, useState } from "react";
import { Route, Routes, useNavigate } from "react-router";
import NavBar from "./components/NavBar";
import About from "./pages/About";
import CityDetail from "./pages/CityDetail";
import CountrySpecificSources from "./pages/CountrySpecificSources";
import Destinations from "./pages/Destinations";
import DestinationDetail from "./pages/DestinationDetail";
import RecSys from "./pages/RecSys";
import TravelerDetail from "./pages/TravelerDetail";
import { DepartureCountryProvider } from "./lib/departureCountry";
import { getNextWeekRange } from "./lib/nextWeek";

const INTERESTS = ["Hiking", "Beaches", "Food & culture", "Nightlife"] as const;
type Interest = (typeof INTERESTS)[number];

function Home() {
  const navigate = useNavigate();
  const [interest, setInterest] = useState<Interest>("Food & culture");

  // Defaults the date range to next Monday-Sunday so the form has a
  // sensible trip already picked out instead of forcing everyone to
  // open the date picker before they can search at all. Computed once
  // per mount (not on every render) since "next week" only changes if
  // the page stays open across a date rollover.
  const defaultDateRange = useMemo(() => getNextWeekRange(), []);

  return (
    <main className="page">
      <h1>when/where</h1>
      <p className="tagline">
        Tell us your dates and what you're into. We'll tell you where to go.
      </p>

      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const startDate = (form.elements.namedItem("start_date") as HTMLInputElement).value;
          const endDate = (form.elements.namedItem("end_date") as HTMLInputElement).value;

          // No backend wired up yet -- for now this just carries the
          // searched dates/interest along as query params to the general
          // destinations page.
          const params = new URLSearchParams();
          if (startDate) params.set("start_date", startDate);
          if (endDate) params.set("end_date", endDate);
          params.set("interest", interest);

          navigate(`/destinations?${params.toString()}`);
        }}
      >
        <label>
          Start date
          <input type="date" name="start_date" defaultValue={defaultDateRange.start} />
        </label>

        <label>
          End date
          <input type="date" name="end_date" defaultValue={defaultDateRange.end} />
        </label>

        <label>
          Interest
          <select
            value={interest}
            onChange={(e) => setInterest(e.target.value as Interest)}
          >
            {INTERESTS.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </label>

        <button type="submit">Find destinations</button>
      </form>
    </main>
  );
}

function App() {
  return (
    <DepartureCountryProvider>
      <NavBar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/about" element={<About />} />
        {/* Deliberately not in NavBar -- reachable directly by URL only. */}
        <Route path="/country-specific-sources" element={<CountrySpecificSources />} />
        {/* Same "URL only, not in the nav yet" treatment as the route above,
            for the same reason: it's a placeholder. See pages/RecSys.tsx. */}
        <Route path="/rec-sys" element={<RecSys />} />
        {/* :travelerId is build_travelers.py's slug (e.g.
            "john-smith-american"), derived from the name and nationality it
            groups trips by -- so the URL shows what decided that this person
            is one person. */}
        <Route path="/rec-sys/travelers/:travelerId" element={<TravelerDetail />} />
        <Route path="/destinations" element={<Destinations />} />
        {/* :cityId is a simplemaps_id (e.g. "1392419823"), the stable
            unique key for a city in this project's data -- city names
            aren't unique (two real cities are both named "Kanpur"), so
            the id is what the ranked list links with. Declared before
            /destinations/:country so "cities" can't be read as a country
            code -- react-router ranks static segments above dynamic ones
            regardless of order, but the explicit ordering documents the
            intent. */}
        <Route path="/destinations/cities/:cityId" element={<CityDetail />} />
        {/* :country is the ISO 3166-1 alpha-2 code (e.g. "JP"). One
            component template renders a page for all ~249 countries --
            the react-router equivalent of a Next.js [country] route,
            since this app is a Vite SPA rather than Next's app router. */}
        <Route path="/destinations/:country" element={<DestinationDetail />} />
      </Routes>
    </DepartureCountryProvider>
  );
}

export default App;
