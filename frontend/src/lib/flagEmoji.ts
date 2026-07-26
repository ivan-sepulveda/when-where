// Converts an ISO 3166-1 alpha-2 code into its flag emoji.
//
// Flag emoji aren't a fixed image lookup -- each letter A-Z has a
// corresponding "Regional Indicator Symbol" codepoint, and a flag is
// just two of those symbols placed next to each other. Offsetting a
// letter's char code by 127397 lands on its Regional Indicator Symbol
// (127462 for "A" == 0x1F1E6, minus 65 for "A".charCodeAt(0)). So this
// works for any valid 2-letter code without a lookup table -- the
// rendering itself is left entirely to the browser/OS's emoji font.
export function countryCodeToFlagEmoji(countryCode: string): string {
  return countryCode
    .toUpperCase()
    .replace(/./g, (char) => String.fromCodePoint(127397 + char.charCodeAt(0)));
}
