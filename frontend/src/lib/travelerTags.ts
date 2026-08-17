// Pure logic behind the tag chips on a traveler (see
// components/TravelerTags.tsx for the rendering). Same split as
// travelerCharts.ts / StackedShareBar.tsx: no React here, so the wording can
// be tested without mounting anything.
import type { TravelerTag } from "./travelers";

export const AIRLINE_LOYALIST = "airline_loyalist";

// The arithmetic behind a chip, as its tooltip: "42 of 42 trips with a
// recorded airline (100%)".
//
// The chip itself stays two words -- it has to fit a 180px card in the
// /rec-sys grid -- but the number that earned it should never be more than a
// hover away. "WITH A RECORDED AIRLINE" is the load-bearing phrase, not
// padding: only the hand-authored itineraries name a carrier, so this
// denominator is smaller than the traveler's trip_count and a reader who
// assumed otherwise would read 42 of 42 as a claim about all their travel.
// It is the same denominator the "Airlines flown" bar states in its caption.
//
// Returns undefined rather than a string for a tag with no evidence
// attached, so the chip renders with no title attribute at all instead of an
// empty tooltip.
export function describeTag(tag: TravelerTag): string | undefined {
  if (tag.kind !== AIRLINE_LOYALIST) return undefined;
  if (tag.trips === null || tag.trips === undefined) return undefined;
  if (tag.denominator === null || tag.denominator === undefined) return undefined;

  const share = tag.share === null || tag.share === undefined ? null : Math.round(tag.share * 100);
  const trips = `${tag.trips} of ${tag.denominator} trip${tag.denominator === 1 ? "" : "s"}`;
  return share === null
    ? `${trips} with a recorded airline`
    : `${trips} with a recorded airline (${share}%)`;
}
