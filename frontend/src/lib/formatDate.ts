// Formats <input type="date"> values ("YYYY-MM-DD") for display, e.g.
// formatOrdinalDate("2026-07-07") -> "July 7th, 2026".
function ordinalSuffix(day: number): string {
  if (day % 10 === 1 && day % 100 !== 11) return "st";
  if (day % 10 === 2 && day % 100 !== 12) return "nd";
  if (day % 10 === 3 && day % 100 !== 13) return "rd";
  return "th";
}

export function formatOrdinalDate(isoDate: string): string {
  // Built from the Y/M/D parts directly (not `new Date(isoDate)`) so this
  // reads as the calendar date the user picked, not shifted a day by
  // parsing "YYYY-MM-DD" as UTC midnight in a behind-UTC timezone.
  const [year, month, day] = isoDate.split("-").map(Number);
  const monthName = new Date(year, month - 1, day).toLocaleDateString("en-US", { month: "long" });
  return `${monthName} ${day}${ordinalSuffix(day)}, ${year}`;
}

export function formatDateRange(startIsoDate: string, endIsoDate: string): string {
  return `${formatOrdinalDate(startIsoDate)} - ${formatOrdinalDate(endIsoDate)}`;
}
