// Michelin Guide restaurant counts by country, from
// data/processed/MICHELIN_SCORE_BY_COUNTRY.csv (see
// compute_michelin_score.py) -- AWARD_COUNT is every Michelin award
// (Stars + Bib Gourmand + Selected Restaurants) in that country, i.e.
// the number of Michelin Guide restaurants.
const MICHELIN_SCORE_URL =
  "https://raw.githubusercontent.com/ivan-sepulveda/when-where/refs/heads/main/data/processed/MICHELIN_SCORE_BY_COUNTRY.csv";

// Minimal RFC 4180 CSV parser -- needed because COUNTRY_NAME values can
// contain commas inside quotes (e.g. "Korea, South", "Bahamas, The"), so
// a naive split(",") would misalign columns for those rows.
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      row.push(field);
      field = "";
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (char === "\r") {
      // skip -- \r\n line endings are handled by the \n branch above
    } else {
      field += char;
    }
  }

  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows;
}

// code -> Michelin Guide restaurant count. Cached at module scope so
// every DestinationDetail page fetches the CSV at most once per session.
let awardCountsPromise: Promise<Map<string, number>> | null = null;

async function loadMichelinAwardCounts(): Promise<Map<string, number>> {
  const res = await fetch(MICHELIN_SCORE_URL);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const text = await res.text();

  const [, ...dataRows] = parseCsv(text).filter((row) => row.length >= 3 && row[0]);

  const counts = new Map<string, number>();
  for (const [code, , awardCountRaw] of dataRows) {
    counts.set(code, Number(awardCountRaw) || 0);
  }
  return counts;
}

export function getMichelinAwardCounts(): Promise<Map<string, number>> {
  if (!awardCountsPromise) awardCountsPromise = loadMichelinAwardCounts();
  return awardCountsPromise;
}

// Above 1000, the exact count reads as false precision, so it's rounded
// to the nearest 50 and prefixed with "Roughly" -- e.g. 2030 -> "Roughly
// 2050 Michelin Guide Restaurants". 1000 and below are shown as-is:
// formatMichelinCount(7) -> "7 Michelin Guide Restaurants",
// formatMichelinCount(1) -> "1 Michelin Guide Restaurant",
// formatMichelinCount(893) -> "893 Michelin Guide Restaurants",
// formatMichelinCount(2030) -> "Roughly 2050 Michelin Guide Restaurants".
export function formatMichelinCount(count: number): string {
  const isRounded = count > 1000;
  const displayCount = isRounded ? Math.round(count / 50) * 50 : count;
  const prefix = isRounded ? "Roughly " : "";
  return `${prefix}${displayCount} Michelin Guide Restaurant${displayCount === 1 ? "" : "s"}`;
}
