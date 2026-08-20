import { Link, useSearchParams } from "react-router";
import TravelerTags from "../components/TravelerTags";
import {
  filterByRegionEntropy,
  formatTripCount,
  maxRegionEntropy,
  useTravelers,
} from "../lib/travelers";

// Whether the grid is filtered to travelers with more than one trip. Kept in
// the URL rather than component state, same as Destinations.tsx's "view" and
// "count" params, so a filtered grid is shareable and survives a refresh.
// Multi-trip-only is the DEFAULT and is never written to the URL -- a plain
// /rec-sys link means "the interesting ones" -- so the param only ever
// appears as ?show=all when the box is unchecked.
const SHOW_ALL_PARAM = "show";
const SHOW_ALL_VALUE = "all";

// The region-entropy floor, in the URL for the same reason: a filtered grid
// should survive a refresh and paste into a message. 0 is the off position
// and is never written, so a plain /rec-sys link means "no entropy filter".
const REGION_ENTROPY_PARAM = "region-entropy";
const REGION_ENTROPY_STEP = 0.01;

function parseRegionEntropy(raw: string | null): number {
  const value = Number(raw);
  // Anything unparseable reads as "off" rather than as an error: this is a
  // shareable URL, and a typo in it should show the whole grid, not a
  // broken page.
  return Number.isFinite(value) && value > 0 ? value : 0;
}

// The recommendation system page (/rec-sys): every traveler in the dataset as
// a clickable card, each linking to that traveler's own page.
//
// Deliberately NOT in NavBar's BROWSE_LINKS yet, same as
// /country-specific-sources: reachable by URL only until there's a real
// recommendation on it. Adding it later is one entry in that array.
//
// Where this is heading: these travelers are the profiles a recommendation
// would be computed FOR -- the project's whole question is "given a
// destination, a date range, and a traveler's interests, how good would this
// trip be?", and this is the first half of it (who is asking) rendered as
// something you can click. Someone with several trips is a far better test
// case for that than someone with one, which is what the filters below are
// for -- trip count, and how evenly a traveler spreads across world regions
// (see compute_traveler_entropy.py --by region).
export default function RecSys() {
  const [searchParams, setSearchParams] = useSearchParams();
  const multiTripOnly = searchParams.get(SHOW_ALL_PARAM) !== SHOW_ALL_VALUE;

  function setMultiTripOnly(next: boolean) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next) {
        params.delete(SHOW_ALL_PARAM);
      } else {
        params.set(SHOW_ALL_PARAM, SHOW_ALL_VALUE);
      }
      return params;
    });
  }

  const minRegionEntropy = parseRegionEntropy(searchParams.get(REGION_ENTROPY_PARAM));

  function setMinRegionEntropy(next: number) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next <= 0) {
        params.delete(REGION_ENTROPY_PARAM);
      } else {
        params.set(REGION_ENTROPY_PARAM, next.toFixed(2));
      }
      return params;
    });
  }

  const travelers = useTravelers();
  const all = travelers.status === "loaded" ? travelers.travelers : [];
  const byTripCount = multiTripOnly ? all.filter((traveler) => traveler.trip_count > 1) : all;
  const shown = filterByRegionEntropy(byTripCount, minRegionEntropy);

  // The slider's range comes from the WHOLE dataset, not from what the other
  // filter currently leaves -- a control whose maximum jumped every time the
  // checkbox moved would be unusable.
  const sliderMax = maxRegionEntropy(all);

  return (
    <main className="page">
      <h1>Travelers</h1>
      <p className="tagline">
        Every traveler in the trip dataset. Pick one to see their details and the trips they've taken.
      </p>

      {travelers.status === "loading" && <p>Loading travelers...</p>}

      {travelers.status === "error" && (
        <p role="alert">Couldn't load travelers. Try again in a moment.</p>
      )}

      {/* Distinct from "loaded, but zero travelers" on purpose: this means
          the data scripts haven't been run in this checkout, which is
          fixable, so the page says how rather than showing an empty grid
          that reads like a bug. */}
      {travelers.status === "unavailable" && (
        <div className="rec-sys-empty">
          <p>The traveler dataset hasn't been generated yet.</p>
          <pre>
            <code>
              python scripts/multiple/fetch_traveler_trips.py{"\n"}
              python scripts/multiple/build_trips_enhanced.py{"\n"}
              python scripts/multiple/build_travelers.py{"\n"}
              python scripts/multiple/build_travelers_anon.py
            </code>
          </pre>
          <p className="rec-sys-empty-note">
            Run these in order from <code>data/</code>, then restart the API. The first needs Kaggle
            credentials -- see <code>data/README.md</code>. The last one is optional: it swaps the
            dataset's filler names for real authors.
          </p>
        </div>
      )}

      {travelers.status === "loaded" && (
        <>
          <div className="destinations-controls">
            <label className="rec-sys-filter">
              <input
                type="checkbox"
                checked={multiTripOnly}
                onChange={(e) => setMultiTripOnly(e.target.checked)}
              />
              Only show travelers with multiple trips
            </label>
            {/* Only rendered when the dataset actually carries region
                entropy: with compute_traveler_entropy.py --by region
                un-run every value is null, and a slider that filtered the
                grid to nothing would look like it was working. */}
            {sliderMax > 0 && (
              <label className="rec-sys-slider">
                <span className="rec-sys-slider-label">
                  Region entropy at least{" "}
                  {/* The number is shown, not implied by the knob position:
                      this is an unfamiliar 0-1 measure, and the value is
                      what makes the control legible. */}
                  <strong>{minRegionEntropy.toFixed(2)}</strong>
                </span>
                <input
                  type="range"
                  min={0}
                  max={sliderMax}
                  step={REGION_ENTROPY_STEP}
                  value={Math.min(minRegionEntropy, sliderMax)}
                  onChange={(e) => setMinRegionEntropy(Number(e.target.value))}
                  aria-label="Minimum destination entropy by region, normalized"
                />
              </label>
            )}
            {/* Says what's hidden as well as what's shown -- with this
                dataset the filters remove most of the grid, and a bare
                count of 11 with no context reads like missing data. */}
            <span className="rec-sys-filter-count">
              {shown.length === all.length
                ? `Showing all ${all.length}`
                : `Showing ${shown.length} of ${all.length}`}
            </span>
          </div>

          {all.length === 0 && <p>The traveler dataset is loaded, but it has no travelers in it.</p>}

          {all.length > 0 && shown.length === 0 && (
            <p>
              {minRegionEntropy > 0
                ? `No traveler spreads their trips across regions that evenly. Slide the region entropy filter back below ${minRegionEntropy.toFixed(2)} to see more.`
                : "No traveler in this dataset has more than one trip. Uncheck the box above to see all of them."}
            </p>
          )}

          {shown.length > 0 && (
            <ul className="traveler-card-grid">
              {shown.map((traveler) => (
                <li key={traveler.traveler_id}>
                  <Link to={`/rec-sys/travelers/${traveler.traveler_id}`} className="traveler-card">
                    <span className="traveler-card-name">{traveler.name}</span>
                    <span className="traveler-card-meta">
                      {/* Nationality is what tells two same-named cards
                          apart in the raw data, and it's what the author
                          personas are matched on -- worth keeping either
                          way. */}
                      {[traveler.nationality, formatTripCount(traveler.trip_count)]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                    {/* Below the meta line, not beside the name: a chip is
                        the most eye-catching thing on the card, and putting
                        it above the trip count would make the 49 tagged
                        travelers look like a different kind of card from
                        the other 157. */}
                    <TravelerTags tags={traveler.tags} />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
