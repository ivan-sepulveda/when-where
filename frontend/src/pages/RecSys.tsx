import { Link, useSearchParams } from "react-router";
import TravelerTags from "../components/TravelerTags";
import {
  ENTROPY_COMPARATOR_OPTIONS,
  ENTROPY_METRIC_OPTIONS,
  ENTROPY_STEP,
  entropyMetricRange,
  entropyMetricValue,
  filterByEntropy,
  filterByTravelerType,
  formatEntropyValue,
  formatTripCount,
  TRAVELER_TYPE_OPTIONS,
  useTravelersWithEntropy,
  type EntropyComparator,
  type EntropyMetric,
  type TravelerTypeFilter,
} from "../lib/travelers";

// Whether the grid is filtered to travelers with more than one trip. Kept in
// the URL rather than component state, same as Destinations.tsx's "view" and
// "count" params, so a filtered grid is shareable and survives a refresh.
// Multi-trip-only is the DEFAULT and is never written to the URL -- a plain
// /rec-sys link means "the interesting ones" -- so the param only ever
// appears as ?show=all when the box is unchecked.
const SHOW_ALL_PARAM = "show";
const SHOW_ALL_VALUE = "all";

// Which travelers count as "real" vs "synthetic" for the dropdown -- see
// lib/travelers.ts's filterByTravelerType and TravelerSummary.real_person.
// "all" is the default and, like SHOW_ALL_VALUE above, is never written to
// the URL.
const TRAVELER_TYPE_PARAM = "traveler-type";
const TRAVELER_TYPE_VALUES: TravelerTypeFilter[] = ["real", "synthetic"];

function parseTravelerType(raw: string | null): TravelerTypeFilter {
  return raw !== null && (TRAVELER_TYPE_VALUES as string[]).includes(raw) ? (raw as TravelerTypeFilter) : "all";
}

// The entropy filter, in the URL for the same reason: a filtered grid should
// survive a refresh and paste into a message. No metric selected is the off
// position and is never written, so a plain /rec-sys link means "no entropy
// filter" -- see lib/travelers.ts's filterByEntropy for why "off" is a
// missing metric rather than a threshold of zero.
const ENTROPY_METRIC_PARAM = "entropy-metric";
const ENTROPY_CMP_PARAM = "entropy-cmp";
const ENTROPY_VALUE_PARAM = "entropy-value";
const DEFAULT_COMPARATOR: EntropyComparator = "gte";

const ENTROPY_METRIC_VALUES: EntropyMetric[] = ["airport", "airport_normalized", "region", "region_normalized"];
const ENTROPY_COMPARATOR_VALUES: EntropyComparator[] = ["gte", "lte", "gt", "lt", "eq"];

function parseEntropyMetric(raw: string | null): EntropyMetric | null {
  // Anything this build doesn't recognise reads as "off" rather than as an
  // error: this is a shareable URL, and a typo (or an old link from before a
  // metric was renamed) should show the whole grid, not a broken page.
  return raw !== null && (ENTROPY_METRIC_VALUES as string[]).includes(raw) ? (raw as EntropyMetric) : null;
}

function parseEntropyComparator(raw: string | null): EntropyComparator {
  return raw !== null && (ENTROPY_COMPARATOR_VALUES as string[]).includes(raw)
    ? (raw as EntropyComparator)
    : DEFAULT_COMPARATOR;
}

function parseEntropyValue(raw: string | null): number {
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}

function entropyMetricLabel(metric: EntropyMetric): string {
  return ENTROPY_METRIC_OPTIONS.find((opt) => opt.value === metric)?.label ?? metric;
}

function entropyComparatorLabel(comparator: EntropyComparator): string {
  return ENTROPY_COMPARATOR_OPTIONS.find((opt) => opt.value === comparator)?.label ?? comparator;
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
// case for that than someone with one, which is what the trip-count
// checkbox is for. The entropy filter below it exists for a narrower,
// deliberate purpose: finding travelers whose recorded trips barely vary --
// same airport, same region, over and over -- which is worth inspecting by
// hand, since for exactly those travelers a "next destination" prediction
// risks being a lookup rather than something the system actually learned.
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

  const travelerType = parseTravelerType(searchParams.get(TRAVELER_TYPE_PARAM));

  function setTravelerType(next: TravelerTypeFilter) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next === "all") {
        params.delete(TRAVELER_TYPE_PARAM);
      } else {
        params.set(TRAVELER_TYPE_PARAM, next);
      }
      return params;
    });
  }

  const entropyMetric = parseEntropyMetric(searchParams.get(ENTROPY_METRIC_PARAM));
  const entropyComparator = parseEntropyComparator(searchParams.get(ENTROPY_CMP_PARAM));
  const entropyValue = parseEntropyValue(searchParams.get(ENTROPY_VALUE_PARAM));

  function setEntropyMetric(next: EntropyMetric | null) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next === null) {
        // Turning the filter off clears the comparator and value too --
        // they're meaningless without a metric, and leaving them in the URL
        // would resurrect a stale threshold the moment a metric is picked
        // again.
        params.delete(ENTROPY_METRIC_PARAM);
        params.delete(ENTROPY_CMP_PARAM);
        params.delete(ENTROPY_VALUE_PARAM);
      } else {
        params.set(ENTROPY_METRIC_PARAM, next);
      }
      return params;
    });
  }

  function setEntropyComparator(next: EntropyComparator) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next === DEFAULT_COMPARATOR) {
        params.delete(ENTROPY_CMP_PARAM);
      } else {
        params.set(ENTROPY_CMP_PARAM, next);
      }
      return params;
    });
  }

  function setEntropyValue(next: number) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (!Number.isFinite(next) || next === 0) {
        params.delete(ENTROPY_VALUE_PARAM);
      } else {
        params.set(ENTROPY_VALUE_PARAM, String(next));
      }
      return params;
    });
  }

  const travelers = useTravelersWithEntropy();
  // The grid renders during "enriching" too -- the multi-trip checkbox and
  // region entropy (normalized) both already work off the plain summary, so
  // there's no reason to block the whole page on ~210 detail fetches whose
  // only job is filling in the other three metrics.
  const dataReady = travelers.status === "loaded" || travelers.status === "enriching";
  const all = dataReady ? travelers.travelers : [];
  const byTripCount = multiTripOnly ? all.filter((traveler) => traveler.trip_count > 1) : all;
  const byType = filterByTravelerType(byTripCount, travelerType);
  const shown = filterByEntropy(byType, entropyMetric, entropyComparator, entropyValue);

  // The hint text next to the filter -- what this metric actually ranges
  // over in the currently-loaded data, not a fixed 0-1 assumption (raw
  // entropy isn't bounded at 1). Computed from the whole dataset, not from
  // what the trip-count checkbox currently leaves, so it doesn't jump around
  // as that checkbox is toggled.
  const entropyRange = entropyMetric ? entropyMetricRange(all, entropyMetric) : null;

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

      {dataReady && (
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

            {/* Real, named people (Bourdain, Ramsay, Conan, Gomez) vs
                everyone else -- see TravelerSummary.real_person and
                filterByTravelerType. A dropdown rather than a checkbox like
                the one above: it's a three-way choice (all / real /
                synthetic), not an on/off toggle. */}
            <label className="rec-sys-type-filter">
              <span>Traveler type</span>
              <select
                value={travelerType}
                onChange={(e) => setTravelerType(e.target.value as TravelerTypeFilter)}
              >
                {TRAVELER_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>

            <div className="rec-sys-entropy-filter">
              <label className="rec-sys-entropy-field">
                <span>Entropy</span>
                <select
                  value={entropyMetric ?? ""}
                  onChange={(e) =>
                    setEntropyMetric(e.target.value === "" ? null : (e.target.value as EntropyMetric))
                  }
                >
                  <option value="">No filter</option>
                  {ENTROPY_METRIC_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>

              {/* Comparator and threshold only mean anything once a metric is
                  picked -- rendering them disabled instead of hiding them
                  would invite fiddling with a value that does nothing yet. */}
              {entropyMetric !== null && (
                <>
                  <select
                    className="rec-sys-entropy-comparator"
                    value={entropyComparator}
                    onChange={(e) => setEntropyComparator(e.target.value as EntropyComparator)}
                    aria-label="Entropy comparator"
                  >
                    {ENTROPY_COMPARATOR_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <input
                    type="number"
                    className="rec-sys-entropy-value"
                    step={ENTROPY_STEP}
                    value={entropyValue}
                    onChange={(e) => setEntropyValue(Number(e.target.value))}
                    aria-label="Entropy threshold"
                  />
                  {entropyRange && (
                    <span className="rec-sys-entropy-hint">
                      data ranges {formatEntropyValue(entropyRange.min)}–
                      {formatEntropyValue(entropyRange.max)}
                    </span>
                  )}
                </>
              )}
            </div>

            {/* Says what's hidden as well as what's shown -- with this
                dataset the filters remove most of the grid, and a bare
                count of 11 with no context reads like missing data. */}
            <span className="rec-sys-filter-count">
              {shown.length === all.length
                ? `Showing all ${all.length}`
                : `Showing ${shown.length} of ${all.length}`}
            </span>
          </div>

          {/* Airport entropy and raw region entropy come from a per-traveler
              detail fetch that hasn't finished yet -- flagged rather than
              left to silently under-filter, since "enriching" can otherwise
              look identical to "this metric legitimately has few matches". */}
          {travelers.status === "enriching" &&
            entropyMetric !== null &&
            entropyMetric !== "region_normalized" && (
              <p className="rec-sys-entropy-loading">
                Loading detailed entropy for every traveler -- this filter will fill in as that finishes.
              </p>
            )}

          {all.length === 0 && <p>The traveler dataset is loaded, but it has no travelers in it.</p>}

          {all.length > 0 && shown.length === 0 && (
            <p>
              {entropyMetric !== null
                ? `No traveler's ${entropyMetricLabel(entropyMetric)} is ${entropyComparatorLabel(entropyComparator)} ${formatEntropyValue(entropyValue)}. Adjust the filter above to see more.`
                : travelerType !== "all"
                  ? `No ${travelerType} traveler matches the other filters above. Try "Show all" in the traveler type dropdown.`
                  : "No traveler in this dataset has more than one trip. Uncheck the box above to see all of them."}
            </p>
          )}

          {shown.length > 0 && (
            <ul className="traveler-card-grid">
              {shown.map((traveler) => {
                const metricValue = entropyMetric !== null ? entropyMetricValue(traveler, entropyMetric) : null;
                return (
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
                      {/* The exact figure the active filter is testing, so
                          "manually inspect the low-entropy ones" doesn't
                          require opening each card. Omitted rather than
                          shown as "--" when it's null: a card silently
                          missing a line reads better than one asserting an
                          unknown value looks like zero. */}
                      {entropyMetric !== null && metricValue !== null && (
                        <span className="traveler-card-entropy">
                          {entropyMetricLabel(entropyMetric)}: {formatEntropyValue(metricValue)}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
