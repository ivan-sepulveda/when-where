// Dot colors for the per-trip chips (see classify_trip.py, TripTag).
//
// The traveler chips color their dot by AIRLINE, via airlineColors.ts, so a
// dot there always means "this color identifies that carrier". No trip tag
// is about an airline, so these are keyed by the tag's `kind` instead: the
// dot identifies the classifier, not a brand.
//
// CONTRAST, NOT LITERAL SHADE. The brief was "white" and "dark blue"; the
// blue here is measured, not picked by eye. The chips sit on #0d1117 (card)
// and #161b22 (detail page), and airlineColors.ts sets the house floor at
// 3:1 against that background. A literal navy fails it badly:
//
//   #001f3f  1.14:1   invisible
//   #1e3a8a  1.83:1
//   #1e40af  2.17:1
//   #1d4ed8  2.82:1   still under
//   #2563eb  3.66:1   <- darkest blue that clears the floor
//   #ffffff 18.92:1
//
// So "dark blue" resolves to #2563eb: the darkest it can be and still be a
// dot rather than a hole. Going darker means the chip reads as having no dot
// at all, which is exactly the state that's supposed to mean "no tag".
const TRIP_TAG_COLORS: Record<string, string> = {
  ski_trip: "#ffffff",
  beach_vacation: "#2563eb",
};

// Null rather than a grey default: a future classifier with no color should
// draw NO dot, the same way a traveler tag about no airline draws none. A
// grey dot would imply a color that means something.
export function tripTagColor(kind: string): string | null {
  return TRIP_TAG_COLORS[kind] ?? null;
}
