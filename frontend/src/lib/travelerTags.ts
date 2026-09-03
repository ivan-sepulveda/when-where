// Pure logic behind the tag chips on a traveler (see
// components/TravelerTags.tsx for the rendering). Same split as
// travelerCharts.ts / StackedShareBar.tsx: no React here, so the wording can
// be tested without mounting anything.
import type { TravelerTag } from "./travelers";

export const AIRLINE_LOYALIST = "airline_loyalist";
export const AIRLINE_HUB = "airline_hub";
export const MULTI_HUB = "multi_hub";
export const TRIP_PATTERN = "trip_pattern";

// The airlines a chip draws a dot for, as full legal names -- which is what
// airlineColors.ts is keyed on. Falls back to the single `carrier_name` so a
// tag written before `carrier_names` existed still gets its dot, and returns
// [] for a tag about no airline at all (which draws no dots rather than a
// grey one, keeping "a dot means that airline" true).
export function tagCarriers(tag: TravelerTag): string[] {
  if (tag.carrier_names && tag.carrier_names.length > 0) return tag.carrier_names;
  return tag.carrier_name ? [tag.carrier_name] : [];
}

// "United", "United and American", "United, Delta and American". Written out
// rather than joined with commas throughout, because these appear mid-
// sentence in a tooltip.
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? "";
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

// The evidence behind a chip, as its tooltip. The chip itself stays two
// words -- it has to fit a 180px card in the /rec-sys grid -- but what earned
// it should never be more than a hover away.
//
// Returns undefined for a tag with no evidence attached, so the chip renders
// with no title attribute at all instead of an empty tooltip.
export function describeTag(tag: TravelerTag): string | undefined {
  if (tag.kind === AIRLINE_LOYALIST) return describeLoyalist(tag);
  if (tag.kind === AIRLINE_HUB || tag.kind === MULTI_HUB) return describeHub(tag);
  if (tag.kind === TRIP_PATTERN) return describeTripPattern(tag);
  return undefined;
}

// "53 of 53 trips with a recorded airline (100%)".
//
// "WITH A RECORDED AIRLINE" is the load-bearing phrase, not padding: only the
// hand-authored itineraries name a carrier, so this denominator is smaller
// than the traveler's trip_count and a reader who assumed otherwise would
// read 53 of 53 as a claim about all their travel. It is the same denominator
// the "Airlines flown" bar states in its caption.
function describeLoyalist(tag: TravelerTag): string | undefined {
  if (tag.trips === null || tag.trips === undefined) return undefined;
  if (tag.denominator === null || tag.denominator === undefined) return undefined;

  const share = tag.share === null || tag.share === undefined ? null : Math.round(tag.share * 100);
  const trips = `${tag.trips} of ${tag.denominator} trip${tag.denominator === 1 ? "" : "s"}`;
  return share === null
    ? `${trips} with a recorded airline`
    : `${trips} with a recorded airline (${share}%)`;
}

// "Lives in Denver, a United hub (DEN)." / "Lives in Chicago, a hub for
// United and American (ORD)."
//
// Leads with "Lives in" because that is the entire basis of the tag -- it
// says nothing about who this person actually flies with, and a chip reading
// "United Hub" next to a "Southwest Loyalist" chip would otherwise look like
// a contradiction rather than the (real, interesting) case of someone who
// lives at United's hub and flies Southwest out of Midway.
function describeHub(tag: TravelerTag): string | undefined {
  if (!tag.hub_city) return undefined;

  const airlines = tag.airlines ?? [];
  const airports = tag.hub_airports?.length ? ` (${tag.hub_airports.join(", ")})` : "";
  if (airlines.length === 0) return `Lives in ${tag.hub_city}, an airline hub${airports}.`;
  if (airlines.length === 1) return `Lives in ${tag.hub_city}, a ${airlines[0]} hub${airports}.`;
  return `Lives in ${tag.hub_city}, a hub for ${joinNames(airlines)}${airports}.`;
}

// What each classify_trip.py tag kind is called in a sentence. A kind that
// isn't in here gets NO tooltip rather than a guessed one built by
// string-mangling the enum -- "beach_vacation" would come out fine that way
// and some future kind would not, and a chip with no tooltip is a smaller
// failure than a chip with a wrong one.
const TRIP_KIND_NOUNS: Record<string, string> = {
  ski_trip: "ski trip",
  beach_vacation: "beach vacation",
  holiday_trip: "holiday trip",
};

// "3 ski trips, out of 32 trips with dates and a route."
//
// LEADS WITH THE COUNT, because the count is what earned the chip -- this
// rule is a floor (3+), not a threshold on a share, so opening with "9%"
// the way the loyalist tooltip opens with "100%" would describe the tag as
// something it isn't. Sisyphus skis 3 times in 32 trips and Isaac Newton 20
// times in 20; both are Skiers, and the sentence has to read correctly for
// both.
//
// "WITH DATES AND A ROUTE" is the honest name for the denominator, not
// filler: classify_trip.py can only tag a trip that records a destination
// airport and both dates, so this is smaller than the traveler's trip_count
// and a reader who assumed otherwise would read "3 of 32" as a claim about
// all their travel.
function describeTripPattern(tag: TravelerTag): string | undefined {
  const noun = tag.trip_kind ? TRIP_KIND_NOUNS[tag.trip_kind] : undefined;
  if (!noun) return undefined;
  if (tag.trips === null || tag.trips === undefined) return undefined;

  const counted = `${tag.trips} ${noun}${tag.trips === 1 ? "" : "s"}`;
  if (tag.denominator === null || tag.denominator === undefined) return `${counted}.`;
  const total = `${tag.denominator} trip${tag.denominator === 1 ? "" : "s"} with dates and a route`;
  return `${counted}, out of ${total}.`;
}
