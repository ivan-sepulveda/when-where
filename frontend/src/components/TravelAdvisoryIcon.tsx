// Yellow exclamation mark shown next to a destination's name when
// data/reference/travel_advisories.json has an entry for it (see
// lib/travelAdvisories.ts). Rendered as an inline SVG rather than the "!"
// emoji glyph (U+2757 etc.) so the yellow fill is guaranteed regardless of
// platform emoji font -- those glyphs are color-locked and ignore CSS
// `color`. The advisory text itself surfaces as a native tooltip and via
// aria-label -- the icon alone conveys nothing to screen readers.
interface TravelAdvisoryIconProps {
  advisory: string;
}

export default function TravelAdvisoryIcon({ advisory }: TravelAdvisoryIconProps) {
  return (
    <span className="travel-advisory-icon" title={advisory} role="img" aria-label={`Travel advisory: ${advisory}`}>
      <svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" focusable="false">
        <path
          d="M12 2.5 22.5 21H1.5Z"
          fill="#eab308"
          stroke="#eab308"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <rect x="11.1" y="9" width="1.8" height="6.5" rx="0.9" fill="#161b22" />
        <circle cx="12" cy="18" r="1.1" fill="#161b22" />
      </svg>
    </span>
  );
}
