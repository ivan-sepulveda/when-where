// Yellow "!" badge shown next to a destination's name when
// data/reference/travel_advisories.json has an entry for it (see
// lib/travelAdvisories.ts). Rendered as an inline SVG (filled circle, not
// the triangle "hazard sign" shape) rather than an emoji glyph (U+2757
// etc.), for two reasons: (1) emoji glyphs are color-locked per platform
// and ignore CSS `color`, and (2) this exact circle-badge look is what
// was asked for after the triangle version.
//
// The advisory text is NOT surfaced via the native `title` attribute --
// that was tried first and native tooltips turned out to be unreliable
// (some environments show the "help" cursor but never render the tooltip
// text). Instead it's a CSS-only tooltip driven by the data-tooltip
// attribute + .travel-advisory-icon::after in index.css, which is
// visible immediately on hover/focus and doesn't depend on browser
// tooltip timing. aria-label carries the same text for screen readers.
interface TravelAdvisoryIconProps {
  advisory: string;
}

export default function TravelAdvisoryIcon({ advisory }: TravelAdvisoryIconProps) {
  return (
    <span
      className="travel-advisory-icon"
      data-tooltip={advisory}
      tabIndex={0}
      role="img"
      aria-label={`Travel advisory: ${advisory}`}
    >
      <svg viewBox="0 0 24 24" width="1em" height="1em" aria-hidden="true" focusable="false">
        <circle cx="12" cy="12" r="11" fill="#eab308" />
        <rect x="10.85" y="5.5" width="2.3" height="8.75" rx="1.15" fill="#161b22" />
        <circle cx="12" cy="17.5" r="1.35" fill="#161b22" />
      </svg>
    </span>
  );
}
