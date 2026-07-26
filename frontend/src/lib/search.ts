// Range U+0300-U+036F is the "Combining Diacritical Marks" block --
// the accent marks NFD normalization splits off of accented letters
// (e.g. "e" + COMBINING ACUTE ACCENT instead of a single "é").
// Built via String.fromCodePoint instead of a \u escape literal to
// avoid escaping ambiguity in the regex source.
const COMBINING_DIACRITICS = new RegExp(
  `[${String.fromCodePoint(0x0300)}-${String.fromCodePoint(0x036f)}]`,
  "g"
);

// Strips accents/diacritics and lowercases, so searches match regardless
// of case or accent marks (e.g. "curacao" matches "Curacao").
export function normalizeForSearch(text: string): string {
  return text.normalize("NFD").replace(COMBINING_DIACRITICS, "").toLowerCase();
}
