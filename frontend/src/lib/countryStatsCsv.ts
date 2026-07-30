// Shared plumbing for the country-stat CSVs published under
// data/processed/ (e.g. MICHELIN_SCORE_BY_COUNTRY.csv,
// UNESCO_SCORE_BY_COUNTRY.csv) -- both follow the same
// COUNTRY,COUNTRY_NAME,<count>,<score> shape, so the fetch/parse logic
// lives here once and each stat (src/lib/michelin.ts, src/lib/unesco.ts)
// just points it at its own URL.

// Minimal RFC 4180 CSV parser -- needed because COUNTRY_NAME values can
// contain commas inside quotes (e.g. "Korea, South", "Bahamas, The"), so
// a naive split(",") would misalign columns for those rows.
export function parseCsv(text: string): string[][] {
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

// Fetches a COUNTRY,COUNTRY_NAME,<count>,<score>-shaped CSV and returns
// code -> count (the 3rd column). Shared by every "N of X per country"
// stat sourced from data/processed/.
export async function loadCountryCountCsv(url: string): Promise<Map<string, number>> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Request failed with status ${res.status}`);
  const text = await res.text();

  const [, ...dataRows] = parseCsv(text).filter((row) => row.length >= 3 && row[0]);

  const counts = new Map<string, number>();
  for (const [code, , countRaw] of dataRows) {
    counts.set(code, Number(countRaw) || 0);
  }
  return counts;
}
