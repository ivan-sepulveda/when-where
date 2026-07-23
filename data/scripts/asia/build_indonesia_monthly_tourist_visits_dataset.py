"""
Data Source: BPS-Statistics Indonesia, "Number of Foreign Tourist Visits per Month by Passport" (original source: Ministry of Immigration and Corrections, Directorate General of Immigration, and Mobile Positioning Data, processed)
URL: https://www.bps.go.id/en/statistics-table/2/MTQ3MCMy/tourist-visits-abroad-by-month.html
Tables Referenced: GRAND TOTAL row, "Number of Foreign Tourist Visits per Month by Passport (Visit)", 2025

Parses BPS's own downloaded CSV export (data/raw/indonesia_bps/
tourist_visits_by_passport_2025.csv, saved locally since gov.id domains
are unreachable from this sandbox) and pulls just the GRAND TOTAL row --
total foreign tourist visits across every passport nationality, not the
by-country breakdown, matching the country-level granularity used
elsewhere in this project. Figures already blend immigration counts with
mobile-positioning-based estimates per BPS's own source note, so they
aren't a pure border-crossing count. Only 2025 is published in this
export; re-download the CSV from the URL above once BPS adds more months.

Usage:
    python build_indonesia_monthly_tourist_visits_dataset.py
"""

import csv
from pathlib import Path

import pandas as pd

RAW_PATH = Path(__file__).resolve().parent.parent.parent / "raw" / "indonesia_bps" / "tourist_visits_by_passport_2025.csv"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "asia"
OUTPUT_FILENAME = "indonesia_bps_tourist_visits_monthly.csv"

YEAR = 2025
ROW_LABEL = "GRAND TOTAL"
# Column 0 is the row label (country/passport name), columns 1-12 are
# Jan-Dec, column 13 is BPS's own "Annually" total -- not used here since
# we sum the 12 months ourselves as a cross-check instead (see main()).
MONTH_COLUMNS = list(range(1, 13))


def parse_grand_total_row() -> list[int]:
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"{RAW_PATH} not found -- download the CSV from the BPS URL above and save it there."
        )
    with open(RAW_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    for row in rows:
        if row and row[0].strip() == ROW_LABEL:
            return [int(row[i].replace(",", "")) for i in MONTH_COLUMNS]

    raise ValueError(f"No row labeled {ROW_LABEL!r} found in {RAW_PATH} -- did BPS change the export layout?")


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, total_visits) for YEAR."""
    monthly_totals = parse_grand_total_row()
    rows = [
        {"ref_date": f"{YEAR}-{month:02d}", "total_visits": total}
        for month, total in zip(range(1, 13), monthly_totals)
    ]
    return pd.DataFrame(rows)


def write_output(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    return out_path


def main():
    df = build_dataset()
    out_path = write_output(df)
    print(f"Wrote {len(df)} rows ({df['ref_date'].min()} - {df['ref_date'].max()}) -> {out_path}")

    peak = df.loc[df["total_visits"].idxmax()]
    print(f"Sanity check -- peak month: {peak['ref_date']} at {peak['total_visits']:,} visits")

    annual_sum = df["total_visits"].sum()
    print(f"Sanity check -- sum of 12 months: {annual_sum:,} (BPS 'Annually' column reports 15,386,646)")


if __name__ == "__main__":
    main()
