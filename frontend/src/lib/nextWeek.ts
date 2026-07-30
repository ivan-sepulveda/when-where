// Default trip date range for the search form: next Monday through the
// Sunday after it (i.e. the calendar week following the current one).
function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export interface DateRange {
  start: string;
  end: string;
}

// `today` is a param (defaulting to `new Date()`) purely so this is
// testable without mocking the system clock.
export function getNextWeekRange(today: Date = new Date()): DateRange {
  // Date.getDay(): 0 (Sun) - 6 (Sat). Days from `today` back to this
  // week's Monday -- Sunday is a special case since it's day 0 but its
  // Monday is 6 days *before* it, not `1 - 0 = 1` day after.
  const dayOfWeek = today.getDay();
  const diffToThisMonday = dayOfWeek === 0 ? -6 : 1 - dayOfWeek;

  const thisMonday = new Date(today.getFullYear(), today.getMonth(), today.getDate() + diffToThisMonday);

  const nextMonday = new Date(thisMonday.getFullYear(), thisMonday.getMonth(), thisMonday.getDate() + 7);
  const nextSunday = new Date(nextMonday.getFullYear(), nextMonday.getMonth(), nextMonday.getDate() + 6);

  return { start: toIsoDate(nextMonday), end: toIsoDate(nextSunday) };
}
