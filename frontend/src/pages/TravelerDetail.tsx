import { Link, useParams } from "react-router";
import { formatDateRange } from "../lib/formatDate";
import {
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
