import { Link, useParams, useSearchParams } from "react-router";
import PreferenceRadarChart from "../components/PreferenceRadarChart";
import StackedShareBar from "../components/StackedShareBar";
import TravelerTags from "../components/TravelerTags";
import { airlineColor, shortenCarrier } from "../lib/airlineColors";
import { formatDateRange } from "../lib/formatDate";
import {
  carrierBreakdown,
  domesticInternationalBreakdown,
  preferenceAxes,
  subregionBreakdown,
} from "../lib/travelerCharts";
import {
  describeEntropy,
  entropyUnitLabel,
  formatAge,
  formatBase,
  formatDestination,
  formatDestinationScore,
  formatFlight,
  formatTripCount,
  formatTripDates,
  sortTripsByDate,
  tripDestinationScores,
  TRIP_ORDER_OPTIONS,
  useTraveler,
  type DestinationEntropy,
  type TravelerTrip,
  type TripOrder,
} from "../lib/travelers";

// One traveler from the /rec-sys grid: who they are, then every trip they've
// taken. Reached at /rec-sys/travelers/:travelerId, where travelerId is
// build_travelers.py's slug (e.g. "john-smith-american").
//
// Note how much of a trip is rendered from *_raw fields rather than the
// parsed ones: costs in this dataset are display strings with no currency
// column, so "£900" has to render as "£900", not as 900. See
// lib/travelers.ts and build_travelers.py -- the parsed numbers exist for
// scoring later, the strings are what a person should read.
function TripCard({ trip }: { trip: TravelerTrip }) {
  const dates = formatTripDates(trip, formatDateRange);

  // Built as a list of present facts rather than a fixed layout with blanks:
  // this dataset has rows missing dates, costs or both, and an empty "Cost:"
  // line reads as broken where a simply-absent line doesn't.
  const facts = [
    dates,
    // Duration is the one field where the PARSED value is preferred over the
    // raw string, because days are unambiguous -- there's no equivalent of
    // the currency problem that makes raw costs the safer thing to show. It
    // also reads better: the source stores this column numerically, so
    // duration_raw comes through as "7.0".
    trip.duration_days === null ? trip.duration_raw : `${trip.duration_days} days`,
    trip.accommodation_type &&
      [trip.accommodation_type, trip.accommodation_cost_raw].filter(Boolean).join(" · "),
    trip.transportation_type &&
      [trip.transportation_type, trip.transportation_cost_raw].filter(Boolean).join(" · "),
    // Only hand-authored trips have an airline and a route; Kaggle rows say
    // nothing about who they flew with, so this line is simply absent there.
    formatFlight(trip),
  ].filter(Boolean) as string[];

  // Kept OUT of `facts` deliberately: those are free-text lines, these are
  // three labelled numbers that need to line up card to card. See
  // tripDestinationScores() for why an absent score is omitted rather than
  // dashed.
  const scores = tripDestinationScores(trip);

  return (
    <li className="destination-detail-stat-card city-detail-nearby-card">
      {/* The cleaned "City, Country", not the source's raw string --
          see formatDestination(). */}
      <span className="city-detail-nearby-name">{formatDestination(trip)}</span>
      {facts.map((fact) => (
        <span key={fact} className="city-detail-nearby-meta">
          {fact}
        </span>
      ))}
      {scores.length > 0 && (
        <span className="trip-card-scores">
          {scores.map((score) => (
            <span key={score.key} className="trip-card-score" title={score.title}>
              <span className="trip-card-score-label">{score.label}</span>
              <span className="trip-card-score-value">{formatDestinationScore(score.value)}</span>
            </span>
          ))}
        </span>
      )}
    </li>
  );
}

// One entropy measure: two numbers and the sentence that stops them being
// misread. Rendered once per unit -- destination airport and UN M49 detailed
// region -- because the two answer different questions and a traveler can be
// high on one and zero on the other (six New York-area airports is high
// airport entropy and zero region entropy).
//
// THE TWO ARE NOT COMPARABLE and the markup works to prevent that reading:
// each block names its unit in the heading, each states the denominator its
// own normalisation used, and each carries its own summary sentence. Showing
// them as four bare numbers under one heading would invite exactly the
// cross-unit comparison that means nothing.
function EntropyBlock({ entropy }: { entropy: DestinationEntropy | null | undefined }) {
  const summary = describeEntropy(entropy);
  // Rendered only when the entropy exists. For the airport unit it's null on
  // the 124 Kaggle-sourced travelers, and a 0 there would claim they never
  // vary their destination when the source simply records no airport.
  if (!entropy || entropy.entropy === null || !summary) return null;

  const plural = entropy.destination_unit === "city" ? "cities" : `${entropy.destination_unit}s`;

  return (
    <>
      <h2>Destination entropy ({entropyUnitLabel(entropy)})</h2>
      <ul className="destination-detail-stats entropy-stats">
        <li className="destination-detail-stat-card entropy-card">
          <span className="entropy-value">{entropy.entropy.toFixed(3)}</span>
          <span className="entropy-label">Shannon entropy (nats)</span>
        </li>
        <li className="destination-detail-stat-card entropy-card">
          <span className="entropy-value">
            {entropy.normalized === null ? "--" : entropy.normalized.toFixed(3)}
          </span>
          <span className="entropy-label">
            {/* The denominator is stated rather than implied: a bare 0.652
                is meaningless without knowing what it's a share OF, and the
                two blocks on this page divide by different things -- the
                airport one by however many airports the dataset happens to
                contain, the region one by all 22 M49 regions whether or not
                anyone visits them. */}
            Normalized{" "}
            {entropy.global_distinct_destinations
              ? `(of ${entropy.global_distinct_destinations} ${
                  entropy.destination_unit === "region" ? "possible " : ""
                }destination ${plural})`
              : ""}
          </span>
        </li>
      </ul>
      <p className="tagline entropy-note">
        <strong>{summary.headline}.</strong> {summary.detail} Entropy is 0 when every trip goes to
        the same {entropy.destination_unit ?? "place"} and rises the more evenly trips are spread
        across {plural}.
      </p>
    </>
  );
}

// The Trips section's sort order, held in the URL like /rec-sys's own
// filters (see lib/travelers.ts's TripOrder) -- so a traveler's page, viewed
// oldest-first, survives a refresh and pastes into a message the same way.
// "recent" is the default and is never written to the URL.
const TRIP_ORDER_PARAM = "trip-order";

function parseTripOrder(raw: string | null): TripOrder {
  return raw === "oldest" ? "oldest" : "recent";
}

export default function TravelerDetail() {
  const { travelerId } = useParams<{ travelerId: string }>();
  const state = useTraveler(travelerId);
  const [searchParams, setSearchParams] = useSearchParams();
  const tripOrder = parseTripOrder(searchParams.get(TRIP_ORDER_PARAM));

  function setTripOrder(next: TripOrder) {
    setSearchParams((prev) => {
      const params = new URLSearchParams(prev);
      if (next === "recent") {
        params.delete(TRIP_ORDER_PARAM);
      } else {
        params.set(TRIP_ORDER_PARAM, next);
      }
      return params;
    });
  }

  if (state.status === "loading") {
    return (
      <main className="page">
        <h1>Loading...</h1>
      </main>
    );
  }

  if (state.status === "not-found") {
    return (
      <main className="page">
        <h1>Traveler not found</h1>
        <p className="tagline">
          "{travelerId}" isn't a traveler in this dataset. <Link to="/rec-sys">Back to travelers</Link>
        </p>
      </main>
    );
  }

  if (state.status === "error") {
    return (
      <main className="page">
        <h1>Couldn't load this traveler</h1>
        <p className="tagline" role="alert">
          Something went wrong. Try again in a moment. <Link to="/rec-sys">Back to travelers</Link>
        </p>
      </main>
    );
  }

  const traveler = state.traveler;
  const age = formatAge(traveler);
  const base = formatBase(traveler);
  const carriers = carrierBreakdown(traveler);
  const domesticInternational = domesticInternationalBreakdown(traveler);
  const subregions = subregionBreakdown(traveler);
  // The destination preference profile (UNESCO / Michelin / weather today --
  // see preferenceAxes) is already computed server-side per traveler, unlike
  // the three breakdowns above which this page builds from raw trips.
  const preferences = preferenceAxes(traveler.preferences);
  // A layover isn't a trip of its own -- Atlanta and Paris on a
  // Houston-to-Lisbon trip, say (see data/scripts/multiple/chef_traveler.py)
  // -- so it's excluded here the same way build_travelers.py's trip_count
  // excludes it. The full itinerary (layovers included) still exists in
  // traveler.trips for anything that wants it; this page just doesn't list
  // a layover as if it were a destination.
  const realTrips = traveler.trips.filter((trip) => !trip.layover);
  const orderedTrips = sortTripsByDate(realTrips, tripOrder);
  // Same "only render what's actually there" approach as TripCard's facts.
  const details = [
    traveler.nationality && { label: "Nationality", value: traveler.nationality },
    base && {
      // "Likely base" for an inferred one -- the source never says where
      // anyone lives, so it's derived from nationality plus which cities they
      // flew to (see build_travelers.py), and that one word stops a guess
      // from reading as a fact. A hand-authored traveler's base is declared
      // outright, so hedging it would be the opposite mistake.
      label: traveler.base_inference === "declared" ? "Base" : "Likely base",
      value: base,
    },
    traveler.gender && { label: "Gender", value: traveler.gender },
    age && {
      label: "Age",
      // A range rather than a single number means their trips span years --
      // worth explaining inline, since "35-37" in an Age field otherwise
      // looks like a data problem.
      value: traveler.age_range && traveler.age_range[0] !== traveler.age_range[1]
        ? `${age} (recorded per trip)`
        : age,
    },
    { label: "Trips", value: formatTripCount(traveler.trip_count) },
  ].filter(Boolean) as { label: string; value: string }[];

  return (
    <main className="page">
      <h1>{traveler.name}</h1>
      {/* Directly under the name, above the stats: the tags are the one thing
          on this page that's a conclusion rather than a field, and they're
          what the "Airlines flown" bar further down is the evidence for. */}
      <TravelerTags tags={traveler.tags} className="traveler-tags-detail" />
      <p className="tagline">
        <Link to="/rec-sys">Back to travelers</Link>
      </p>

      <ul className="destination-detail-stats">
        {details.map((detail) => (
          <li key={detail.label} className="destination-detail-stat-card">
            {detail.label}: {detail.value}
          </li>
        ))}
      </ul>

      {/* Two 100% stacked bars: which airlines this person flies, and how
          much of their flying leaves the country. They deliberately have
          DIFFERENT denominators -- only hand-authored trips record a
          carrier, while domestic/international can be decided for any trip
          with a destination country -- so each chart states its own, and
          neither pads its total with trips the source is silent about. */}
      {/* Two numbers, not a chart: this is a single scalar per traveler, and
          a one-bar bar chart would be a stat tile wearing a costume. Two
          blocks, one per unit -- see EntropyBlock for why they aren't merged
          into one. The airport block simply doesn't render for a traveler
          whose trips record no airport; the region one renders for everyone,
          since every trip records a destination country. */}
      <EntropyBlock entropy={traveler.destination_entropy} />
      <EntropyBlock entropy={traveler.region_entropy} />

      <h2>Flying patterns</h2>
      <div className="traveler-charts">
        <StackedShareBar
          title="Airlines flown"
          data={carriers}
          // Brand colors, plus the airline's short name drawn inside each
          // segment. The label isn't decoration: airline brands are almost
          // all red or blue, so on a crowded chart the colors alone can't be
          // told apart -- see lib/airlineColors.ts for the measurements.
          colorOf={airlineColor}
          shortLabelOf={shortenCarrier}
          caption={
            carriers.total === traveler.trip_count
              ? `Share of all ${formatTripCount(traveler.trip_count)}.`
              : `Share of the ${formatTripCount(carriers.total)} with a recorded airline, of ${traveler.trip_count}.`
          }
          emptyMessage={`No airline is recorded on any of ${traveler.name}'s trips, so there's nothing to break down. Only the hand-authored itineraries carry a carrier.`}
        />
        <StackedShareBar
          title="Domestic vs international"
          data={domesticInternational}
          // Domestic is pinned to the left rather than sorted by size, so
          // the bar doesn't flip layout between one traveler and the next.
          caption={
            base
              ? `Relative to ${base}, this traveler's home country.`
              : "Share of trips leaving the traveler's home country."
          }
          emptyMessage={`${traveler.name} has no trip whose destination country can be compared against a home country, so this split can't be computed.`}
        />
        <StackedShareBar
          title="Destination subregion"
          data={subregions}
          // No colorOf: a region has no brand, so this falls back to the
          // categorical palette assigned by position. Airlines are the
          // exception on this page, not the rule -- see lib/airlineColors.ts.
          caption={
            subregions.total === traveler.trip_count
              ? `Share of all ${formatTripCount(traveler.trip_count)}, by UN M49 subregion.`
              : `Share of the ${formatTripCount(subregions.total)} whose destination country is in the UN M49 list, of ${traveler.trip_count}.`
          }
          emptyMessage={`No destination on ${traveler.name}'s trips could be placed in a UN M49 subregion. If that's every traveler, data/reference/m49_regions.json probably hasn't been built yet.`}
        />
      </div>

      <h2>Destination preferences</h2>
      {/* A single radar/spider chart, in the same .traveler-charts grid as
          the bars above so it reads as part of the same family. Three
          dimensions today (UNESCO, Michelin, weather) -- the same
          UNESCO/Michelin/weather scores each trip card already shows,
          averaged across every non-layover trip that has one. The README
          TODO this implements names more dimensions (food, architecture,
          nightlife...) that need datasets this project doesn't have yet;
          those are left for later rather than guessed at. */}
      <div className="traveler-charts">
        <PreferenceRadarChart
          title="Preference profile"
          axes={preferences}
          // The component itself states which/how-many dimensions are
          // shown (the full chart's axis labels for 3, the "Only N of 3"
          // line for fewer) -- this caption only needs to say what the
          // numbers ARE, not repeat that count a second time.
          caption="UNESCO, Michelin and weather scores, averaged across this traveler's own trips and rescaled to 0-1."
          emptyMessage={`None of ${traveler.name}'s trips matched a city with a UNESCO, Michelin or weather score, so there's nothing to plot.`}
        />
      </div>

      <h2>Trips</h2>
      {/* Hidden when there's nothing to reorder, same reasoning as the
          entropy comparator/value inputs on /rec-sys: a control that does
          nothing on a one-trip page just invites fiddling with it. */}
      {orderedTrips.length > 1 && (
        <label className="trip-order-filter">
          <span>Show by</span>
          <select value={tripOrder} onChange={(e) => setTripOrder(e.target.value as TripOrder)}>
            {TRIP_ORDER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
      )}
      <ul className="destination-detail-stats">
        {orderedTrips.length === 0 ? (
          // Shouldn't happen -- build_travelers.py only creates a traveler
          // from at least one non-layover trip -- but a card that links to an
          // empty page should still say something.
          <li className="destination-detail-stat-card">No trips recorded for {traveler.name}.</li>
        ) : (
          orderedTrips.map((trip, index) => (
            // trip_id is nullable in the source, so it can't be the key on
            // its own; the index keeps it unique either way. Every trip in
            // the current dataset has one, so in practice this key stays
            // trip_id and is stable across a re-sort -- React moves each
            // <TripCard> instead of remounting it -- with the index fallback
            // only there for a source row that somehow arrives without one.
            <TripCard key={trip.trip_id ?? `${trip.destination_raw}-${index}`} trip={trip} />
          ))
        )}
      </ul>
    </main>
  );
}
