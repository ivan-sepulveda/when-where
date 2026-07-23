"""
Data Source: Migracion Colombia / OEE-MinCIT monthly tourism reports, 12 separate PDFs covering January-December 2025
URL: 12 report URLs -- to be added once provided

Builds a tidy monthly CSV of Colombia's visitor numbers, hand-transcribed
from each month's own PDF report. Numbers were referenced from the
official Colombian report of visitors, adjusting for recent waves of
migration. Each report's featured monthly comparison table covers one
calendar month, and that month is always the one AFTER the report's own
title month -- e.g. the "Octubre" report's table covers November, not
October. January 2025 is the exception: it comes from the December
report's prior-year comparison column (a later, more-revised figure)
rather than a report of its own, since no December-2024 report is
available here. Supersedes build_colombia_recent_foreign_visitors_dataset.py.

Usage:
    python build_colombia_monthly_visitors_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "colombia_monthly_visitors.csv"

# Transcribed from each month's own PDF report. See module docstring for
# which report each month came from and why January is the exception.
MONTHLY_VISITORS = {
    "2025-01": 380740,
    "2025-02": 378819,
    "2025-03": 381520,
    "2025-04": 348889,
    "2025-05": 333070,
    "2025-06": 353566,
    "2025-07": 429128,
    "2025-08": 400774,
    "2025-09": 314351,
    "2025-10": 338481,
    "2025-11": 377712,
    "2025-12": 436955,
}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, visitors) for calendar year 2025."""
    rows = [
        {"ref_date": ref_date, "visitors": count}
        for ref_date, count in MONTHLY_VISITORS.items()
    ]
    return pd.DataFrame(rows).sort_values("ref_date").reset_index(drop=True)


def write_output(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    return out_path


def main():
    df = build_dataset()
    out_path = write_output(df)
    print(f"Wrote {len(df)} rows ({df['ref_date'].min()} - {df['ref_date'].max()}) -> {out_path}")

    jan25 = df.loc[df["ref_date"] == "2025-01", "visitors"].iloc[0]
    print(f"Sanity check -- Jan 2025: {jan25:,} (matches the December 2025 report's own table)")

    peak = df.loc[df["visitors"].idxmax()]
    print(f"Sanity check -- peak month: {peak['ref_date']} at {peak['visitors']:,}")


if __name__ == "__main__":
    main()
