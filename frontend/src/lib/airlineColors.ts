// Colors for the "Airlines flown" bar on a traveler page.
//
// FOUR AIRLINES HAVE A FIXED, MEANINGFUL COLOR. Everything else is assigned
// automatically. That split is deliberate: brand colors read well when a few
// recognizable airlines anchor the chart, and read terribly when every
// airline brings its own, because airline brands are overwhelmingly red and
// blue. Measured on this dataset, the all-brand version put a pair of
// segments a full-color reader could not tell apart on 29 of the 82 charts
// with carrier data -- Delta #E3132C and American #DE1B23 sit 1.3 apart in
// OKLab dE x100, where 15 is the floor.
//
// So: Delta keeps its red, United its blue, Frontier its green, American
// takes the grey from its own brand palette (its red is what collided with
// Delta), and the other ~34 carriers get generated colors chosen to stay out
// of each other's way.
//
// HOW THE ASSIGNED COLORS WERE PICKED -- they are not arbitrary, and
// hand-editing one will quietly undo the property they were chosen for.
// They were solved for against the real charts: every carrier pair that
// actually renders SIDE BY SIDE, weighted by how often, then optimised to
// keep adjacent segments apart. The result, measured over all 82 charts:
//
//   adjacent pairs below dE 15   2 of 82 charts (2%)   worst adjacent dE 13.0
//   worst contrast vs #161b22    3.16                  (3:1 is the floor)
//
// For comparison, the position-assigned validated palette scores 0% on that
// same adjacency measure -- but it can do that only because it recolors by
// slot, which would make Delta a different color on every traveler's page.
// 2% is the price of "Delta is always Delta red", and it is worth paying.
//
// The "any pair anywhere in the chart" figure is 38%, which sounds alarming
// and isn't: the validated 8-slot palette scores 38% on that same measure.
// Eight mutually distinguishable colors do not exist at this contrast --
// the palette's own docs cap all-pairs separation at three slots. Adjacency
// is the measure that matters for a stacked bar, and segments are labelled
// besides.
//
// To re-solve after adding carriers or changing the data, re-run the
// optimiser described above rather than picking colors by eye.

export interface AirlineBrand {
  brand: string; // the published brand hex, where the color IS the brand's
  display: string; // what actually gets drawn on the dark card
  short: string; // what fits inside a bar segment
}

// The four fixed ones. `display` differs from `brand` where the published
// color is unreadable on a dark surface: United's #0033A0 measures 1.6:1
// against the card, so `display` keeps its hue and chroma and lifts the
// lightness until it clears 3:1. Delta's red needs no such help.
export const ANCHOR_AIRLINES: Record<string, AirlineBrand> = {
  "Delta Air Lines Inc.": { brand: "#E3132C", display: "#E3132C", short: "Delta" },
  "United Air Lines Inc.": { brand: "#0033A0", display: "#2D63D3", short: "United" },
  "Frontier Airlines Inc.": { brand: "#0F6744", display: "#267A55", short: "Frontier" },
  // American's grey, not its red -- #DE1B23 is 1.3 dE from Delta's red and
  // the two share a chart 12 times. The grey is from American's own brand
  // palette, so this is still their color, just not their primary one.
  "American Airlines Inc.": { brand: "#A5B5BE", display: "#A5B5BE", short: "American" },
};

// Solved assignments for every other carrier in the dataset. Regionals are in
// here on their own terms rather than inheriting a parent's color -- Envoy is
// not American grey, SkyWest is not Delta red.
export const ASSIGNED_COLORS: Record<string, string> = {
  "Aer Lingus Plc": "#CCAE4E",
  "Aeroenlaces Nacionales, S.A. de C.V. d/b/a VivaAerobus": "#B4446E",
  "Aerolitoral": "#607F00",
  "Aeromexico": "#BD9700",
  "Air Canada": "#EF90AE",
  "Air Canada rouge LP": "#8C6F00",
  "Alaska Airlines Inc.": "#DA8418",
  "Asiana Airlines Inc.": "#EA716D",
  "British Airways Plc": "#B94644",
  "Cathay Pacific Airways Ltd.": "#008942",
  "CommuteAir LLC dba CommuteAir": "#33A3F1",
  "Compagnie Natl Air France": "#009DB5",
  "Concesionaria Vuela Compania De Aviacion SA de CV (Volaris)": "#87C47A",
  "Endeavor Air Inc.": "#898E00",
  "Envoy Air": "#C07100",
  "Eva Airways Corporation": "#69B9F8",
  "Iberia Air Lines Of Spain": "#008C7B",
  "Japan Air Lines Co. Ltd.": "#00B0D6",
  "Jazz Aviation LP": "#5AB35B",
  "JetBlue Airways": "#A55E00",
  "Klm Royal Dutch Airlines": "#37C5DD",
  "Korean Air Lines Co. Ltd.": "#D15B58",
  "Lufthansa German Airlines": "#42CAB4",
  "Mesa Airlines Inc.": "#7495F8",
  "PSA Airlines Inc.": "#599A34",
  "Piedmont Airlines": "#007DB9",
  "Republic Airline": "#CC5A82",
  "SkyWest Airlines Inc.": "#E99E5E",
  "Southwest Airlines Co.": "#E46F97",
  "Spirit Air Lines": "#90A827",
  "Sun Country Airlines d/b/a MN Airlines": "#00B7B3",
  "TAP-TAP Air Portugal": "#0091D3",
  "Virgin Atlantic Airways": "#9CAAFD",
  "ZIPAIR Tokyo Inc.": "#5782E0",
};

// For a carrier that appears after this table was solved -- a new route, a
// new airline in the T-100 data. Evenly spaced around the hue wheel at three
// lightness steps, every entry verified to clear 3:1 on the card (worst
// 3.01), so a stranger still gets a readable color instead of falling back
// to grey. It won't be adjacency-optimised; re-run the optimiser to fold it
// in properly.
const FALLBACK_RING = [
  "#C75371", "#E47B79", "#B14423", "#C3610D", "#D48D39", "#965F00",
  "#9A7E00", "#A1A63A", "#547A00", "#43963C", "#4CB67D", "#008662",
  "#009B8F", "#00B5C1", "#007EA3", "#008DC9", "#54A5EA", "#3967C1",
  "#6B74D8", "#A18EE8", "#834FAE", "#A95EB5", "#D17DBC", "#A93F75",
];

// FNV-1a. Any stable hash works; the requirement is only that the same
// carrier name always lands on the same ring entry, so an unmapped airline
// doesn't change color between renders.
function hashName(name: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < name.length; i += 1) {
    h ^= name.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h >>> 0;
}

export function airlineBrand(carrierName: string): AirlineBrand | null {
  return ANCHOR_AIRLINES[carrierName] ?? null;
}

export function airlineColor(carrierName: string): string {
  const anchor = ANCHOR_AIRLINES[carrierName];
  if (anchor) return anchor.display;
  const assigned = ASSIGNED_COLORS[carrierName];
  if (assigned) return assigned;
  return FALLBACK_RING[hashName(carrierName) % FALLBACK_RING.length];
}

// "Envoy Air" -> "Envoy". Drawn inside each bar segment, which is what lets
// two similar colors still be told apart, so this needs to produce something
// short and recognisable for every carrier -- not just the mapped ones.
//
// Trailing noise is stripped word by word rather than by one regex. A single
// pattern kept getting this subtly wrong: `Inc\.?\b` leaves the dot behind on
// "Example Airways Inc." (there is no word boundary after a final period),
// and a rule that strips "Airlines" does not strip the bare "Air" in "Envoy
// Air". Popping tokens off the end handles both, and stacks -- "Endeavor Air
// Inc." loses "Inc." then "Air".
const TRAILING_NOISE = new Set([
  "inc", "co", "corp", "ltd", "plc", "llc", "lp", "limited", "group",
  "sa", "cv", "airlines", "airline", "airways", "air", "lines",
]);

// Carriers whose legal name shortens to something unhelpful or unrecognisable.
const SHORT_NAME_OVERRIDES: Record<string, string> = {
  "Concesionaria Vuela Compania De Aviacion SA de CV (Volaris)": "Volaris",
  "Aeroenlaces Nacionales, S.A. de C.V. d/b/a VivaAerobus": "VivaAerobus",
  "Compagnie Natl Air France": "Air France",
  "Klm Royal Dutch Airlines": "KLM",
  "All Nippon Airways Co.": "ANA",
  "Iberia Air Lines Of Spain": "Iberia",
  "TAP-TAP Air Portugal": "TAP",
  "Sun Country Airlines d/b/a MN Airlines": "Sun Country",
  "Porter Airlines Limited (PACL)": "Porter",
  "Eva Airways Corporation": "EVA Air",
  "Japan Air Lines Co. Ltd.": "Japan Airlines",
  "Korean Air Lines Co. Ltd.": "Korean Air",
  "Cathay Pacific Airways Ltd.": "Cathay",
  "easyJet Airline Company Limited": "easyJet",
};

export function shortenCarrier(carrierName: string): string {
  const override = SHORT_NAME_OVERRIDES[carrierName];
  if (override) return override;
  const anchor = ANCHOR_AIRLINES[carrierName];
  if (anchor) return anchor.short;

  const words = carrierName
    // Everything after a "dba"/"d/b/a" restates the same operator
    // ("CommuteAir LLC dba CommuteAir"), so only the first half is useful.
    .split(/\bd\/?b\/?a\b/i)[0]
    .replace(/\s*\(.*?\)\s*/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim()
    .split(/\s+/);

  // Keep at least one word -- a carrier named only with noise words would
  // otherwise shorten to nothing.
  while (
    words.length > 1 &&
    TRAILING_NOISE.has(words[words.length - 1].toLowerCase().replace(/[.,]+$/, ""))
  ) {
    words.pop();
  }
  return words.join(" ").replace(/[.,]+$/, "") || carrierName;
}
