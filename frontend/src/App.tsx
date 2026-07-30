import { useState } from "react";
import { Route, Routes, useNavigate } from "react-router";
import NavBar from "./components/NavBar";
import Destinations from "./pages/Destinations";
import DestinationDetail from "./pages/DestinationDetail";

const INTERESTS = ["Hiking", "Beaches", "Food & culture", "Nightlife"] as const;
type Interest = (typeof INTERESTS)[number];

function Home() {
  const navigate = useNavigate();
  const [interest, setInterest] = useState<Interest>("Food & culture");

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
          <input type="date" name="start_date" />
        </label>

        <label>
          End date
          <input type="date" name="end_date" />
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
    <>
      <NavBar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/destinations" element={<Destinations />} />
        {/* :country is the ISO 3166-1 alpha-2 code (e.g. "JP"). One
            component template renders a page for all ~249 countries --
            the react-router equivalent of a Next.js [country] route,
            since this app is a Vite SPA rather than Next's app router. */}
        <Route path="/destinations/:country" element={<DestinationDetail />} />
      </Routes>
    </>
  );
}

export default App;
