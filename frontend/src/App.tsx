import { useState } from "react";
import NavBar from "./components/NavBar";

const INTERESTS = ["Hiking", "Beaches", "Food & culture", "Nightlife"] as const;
type Interest = (typeof INTERESTS)[number];

function App() {
  const [interest, setInterest] = useState<Interest>("Food & culture");

  return (
    <>
      <NavBar />
      <main className="page">
      <h1>when/where</h1>
      <p className="tagline">
        Tell us your dates and what you're into. We'll tell you where to go.
      </p>

      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault();
          // No backend wired up yet -- this is just the placeholder shell
          // deployed to confirm the Vercel pipeline works end to end.
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

        <button type="submit" disabled>
          Find destinations (coming soon)
        </button>
      </form>
      </main>
    </>
  );
}

export default App;
