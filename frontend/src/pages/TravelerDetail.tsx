import { Link, useParams } from "react-router";
import StackedShareBar from "../components/StackedShareBar";
import TravelerTags from "../components/TravelerTags";
import { airlineColor, shortenCarrier } from "../lib/airlineColors";
import { formatDateRange } from "../lib/formatDate";
import { carrierBreakdown, domesticInternationalBreakdown } from "../lib/travelerCharts";
import {
  describeEntropy,
  formatAge,
  formatBase,
  formatDestination,
  formatFlight,
  formatTripCount,
  formatTripDates,
  useTraveler,
  type TravelerTrip,
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
    </li>
  );
}

export default function TravelerDetail() {
  const { travelerId } = useParams<{ travelerId: string }>();
  const state = useTraveler(travelerId);

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
  const entropy = traveler.destination_entropy;
  const entropySummary = describeEntropy(traveler);
  const carriers = carrierBreakdown(traveler);
  const domesticInternational = domesticInternationalBreakdown(traveler);
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
          a one-bar bar chart would be a stat tile wearing a costume.
          Rendered only when the entropy exists -- for the 124 Kaggle-sourced
          travelers it's null, and a 0 there would claim they never vary
          their destination when the source simply records no airport. */}
      {entropy && entropy.entropy !== null && entropySummary && (
        <>
          <h2>Destination entropy</h2>
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
                {/* The denominator is stated rather than implied: a bare
                    0.652 is meaningless without knowing it's a share of
                    every destination in the dataset, and that count moves
                    whenever the trip data does. */}
                Normalized{" "}
                {entropy.global_distinct_destinations
                  ? `(of ${entropy.global_distinct_destinations} destination ${
                      entropy.destination_unit === "city" ? "cities" : "airports"
                    })`
                  : ""}
              </span>
            </li>
          </ul>
          <p className="tagline entropy-note">
            <strong>{entropySummary.headline}.</strong> {entropySummary.detail} Entropy is 0 when
            every trip goes to the same place and rises the more evenly trips are spread across
            destinations.
          </p>
        </>
      )}

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
      </div>

      <h2>Trips</h2>
      <ul className="destination-detail-stats">
        {traveler.trips.length === 0 ? (
          // Shouldn't happen -- build_travelers.py only creates a traveler
          // from at least one trip -- but a card that links to an empty page
          // should still say something.
          <li className="destination-detail-stat-card">No trips recorded for {traveler.name}.</li>
        ) : (
          traveler.trips.map((trip, index) => (
            // trip_id is nullable in the source, so it can't be the key on
            // its own; the index keeps it unique either way and these lists
            // are never reordered in place.
            <TripCard key={trip.trip_id ?? `${trip.destination_raw}-${index}`} trip={trip} />
          ))
        )}
      </ul>
    </main>
  );
}
