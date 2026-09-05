import {
  formatRecommendationSource,
  recommendationsCaveat,
  recommendationsMessage,
  type RecommendationsLoadState,
  type TravelerRecommendation,
} from "../lib/travelers";

// The collapsible panel behind the "Recommend 3 places" button on a traveler
// page. The button itself lives in TravelerDetail's heading row, beside the
// name; this is only what unfolds underneath it.
//
// IT RENDERS NOTHING TODAY, AND THAT IS THE POINT. The recommender's data
// prep is real (data/scripts/multiple/rec_sys_data_prep.py) but its ranking
// logic is still pseudocode, so nothing writes recommendations.json and the
// API answers every call with status "not_generated". Every other state --
// loading, error, empty, a real list of cards -- is written and wired here so
// that finishing the Python side is the only remaining step. See
// backend/app/main.py's TravelerRecommendationsResponse for the contract.
//
// One message, or cards, never both: recommendationsMessage() returns null
// exactly when there are rows to show, so the two are mutually exclusive by
// construction rather than by two conditions that could drift apart.

// The API sends month names lowercase, because that is how they are keyed all
// the way back through monthly_scores_2025_by_city.json and the weather
// columns -- lowercase is the right choice for a KEY and the wrong one for a
// sentence, so it is fixed here at the point of display rather than in the
// data.
function titleCaseMonth(month: string): string {
  return month.charAt(0).toUpperCase() + month.slice(1);
}

function RecommendationCard({ recommendation }: { recommendation: TravelerRecommendation }) {
  // Same card shape as a trip card: name on top, a dim meta line, then the
  // detail. A recommendation and a trip are the same kind of object to a
  // reader -- a place, with facts about it -- so they should not look like
  // two different systems.
  const source = formatRecommendationSource(recommendation.source);
  const meta = [
    recommendation.region,
    // "Best in may" rather than a bare month, since a month on its own next
    // to a region reads as a date the trip is booked for. Null best_month
    // means the city has no weather normals -- unknown, so the line is
    // simply absent, matching how trip cards omit an absent score.
    recommendation.best_month && `Best in ${titleCaseMonth(recommendation.best_month)}`,
    source,
  ].filter(Boolean) as string[];

  return (
    <li className="destination-detail-stat-card city-detail-nearby-card">
      <span className="city-detail-nearby-name">
        {recommendation.destination_city}, {recommendation.destination_country}
      </span>
      {meta.length > 0 && <span className="city-detail-nearby-meta">{meta.join(" · ")}</span>}
      {/* The evidence. A travel recommendation with no stated reason is one
          nobody acts on, so this is rendered as its own list rather than
          folded into the meta line -- it is the content, not a footnote. */}
      {recommendation.why.length > 0 && (
        <ul className="traveler-recommendation-why">
          {recommendation.why.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function TravelerRecommendations({
  id,
  state,
  onRetry,
}: {
  id: string;
  state: RecommendationsLoadState;
  onRetry: () => void;
}) {
  const message = recommendationsMessage(state);
  const response = state.status === "loaded" ? state.response : null;
  const caveat = response && recommendationsCaveat(response);
  const recommendations = response?.recommendations ?? [];

  return (
    // aria-live so a screen reader hears the result of pressing the button;
    // the panel appears where nothing was, which is otherwise silent.
    <section id={id} className="traveler-recommendations" aria-live="polite">
      {message && (
        <p className="traveler-recommendations-message" role={state.status === "error" ? "alert" : undefined}>
          {message}
        </p>
      )}

      {state.status === "error" && (
        <button type="button" className="traveler-recommendations-retry" onClick={onRetry}>
          Try again
        </button>
      )}

      {caveat && <p className="traveler-recommendations-caveat">{caveat}</p>}

      {recommendations.length > 0 && (
        <ul className="destination-detail-stats">
          {recommendations.map((recommendation) => (
            <RecommendationCard
              key={recommendation.destination_key}
              recommendation={recommendation}
            />
          ))}
        </ul>
      )}
    </section>
  );
}
