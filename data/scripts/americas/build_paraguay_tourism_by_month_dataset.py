"""
Data Source: INE (Instituto Nacional de Estadistica de Paraguay), table
14.3 "Turismo receptivo por continente de origen, segun mes" (original
source: Secretaria Nacional de Turismo y Direccion Nacional de
Migraciones)
URL: https://www.ine.gov.py/assets/documento/0/14.3_CE2024.xlsx
Tables Referenced: Sheet '14.3', monthly rows for calendar year 2024

Parses INE's own published spreadsheet (cached locally at
data/raw/paraguay_ine/14.3_CE2024.xlsx, since ine.gov.py isn't reachable
from this sandbox -- re-download from the URL above and overwrite that
path if refreshing) and pulls the "Total" column for each month: total
inbound foreign visitors, across every continent of origin. The sheet
also breaks totals down by continent (America, Europe, Asia, Africa,
Oceania, Caribbean, unspecified) -- kept as extra columns here for
context even though only the total feeds the scoring pipeline elsewhere.
Only calendar year 2024 is published in this export. Row order in the
source uses Paraguay's own month-name spelling ("Setiembre", not
"Septiembre"), handled by MONTH_NAME_TO_NUMBER covering both.

Usage:
    python build_paraguay_tourism_by_month_dataset.py
"""

from pathlib import Path

import openpyxl
import pandas as pd

RAW_PATH = Path(__file__).resolve().parent.parent.parent / "raw" / "paraguay_ine" / "14.3_CE2024.xlsx"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "paraguay_tourism_by_month.csv"

SHEET_NAME = "14.3"
YEAR = 2024

# Column order in the sheet, immediately after the month-name column.
VALUE_COLUMNS = ["total", "americas", "europe", "asia", "africa", "oceania", "caribbean", "unspecified"]

MONTH_NAME_TO_NUMBER = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "setiembre": 9, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def parse_monthly_rows() -> list[dict]:
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"{RAW_PATH} not found -- download the file from the URL above and save it there."
        )
    wb = openpyxl.load_workbook(RAW_PATH, data_only=True)
    ws = wb[SHEET_NAME]

    rows = []
    for row in ws.iter_rows(values_only=True):
        label = row[1]
        if not isinstance(label, str):
            continue
        month_num = MONTH_NAME_TO_NUMBER.get(label.strip().lower())
        if month_num is None:
            continue  # skips the header row, the "Total" (annual) row, and blank rows

        values = row[2:2 + len(VALUE_COLUMNS)]
        # A handful of small continent cells are "-" in the source (no
        # cases that month) rather than 0 -- treat both the same.
        parsed = [0 if v in ("-", None) else int(v) for v in values]
        rows.append({"ref_date": f"{YEAR}-{month_num:02d}", **dict(zip(VALUE_COLUMNS, parsed))})

    if len(rows) != 12:
        print(f"WARNING: parsed {len(rows)} month row(s), expected 12 -- did INE change the sheet layout?")

    return sorted(rows, key=lambda r: r["ref_date"])


def build_dataset() -> pd.DataFrame:
    return pd.DataFrame(parse_monthly_rows())


def write_output(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    return out_path


def main():
    df = build_dataset()
    out_path = write_output(df)
    print(f"Wrote {len(df)} rows ({df['ref_date'].min()} - {df['ref_date'].max()}) -> {out_path}")

    peak = df.loc[df["total"].idxmax()]
    print(f"Sanity check -- peak month: {peak['ref_date']} at {peak['total']:,} visitors")

    annual_sum = df["total"].sum()
    print(f"Sanity check -- sum of 12 months: {annual_sum:,} (source's own 'Total' row reports 1,061,338)")


if __name__ == "__main__":
    main()
