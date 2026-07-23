"""
Data Source: MMA Statistics Database (Maldives Monetary Authority), Total tourist arrivals series (ID 104)
URL: https://database.mma.gov.mv/viya/series/104
Tables Referenced: Table 3.1 Tourism Indicators, 2020 - 2026, column 1 (Total arrivals, thousands)

Builds a tidy monthly CSV of Maldives total tourist arrivals for the most
recent 12 published months (Jun 2025 - May 2026). Values were read
directly off the public Viya series page for series 104, which needs no
API token, and cross-checked against Table 3.1's own published HTML table
for the same months (matches to the nearest whole thousand). Complements
fetch_maldives_mma_tourism_indicators.py, which pulls the full history via
the authenticated API but is unverified live in this sandbox -- this
script's numbers are hand-transcribed from the currently published figures
rather than fetched programmatically, so re-transcribe by hand once a
newer month is published.

Usage:
    python build_maldives_recent_arrivals_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "asia"
OUTPUT_FILENAME = "maldives_recent_tourist_arrivals_monthly.csv"

# Transcribed directly from https://database.mma.gov.mv/viya/series/104
# ("Total tourist arrivals"), the most recent 12 published months as of
# this data pull. Values are thousands of tourists; cross-checked against
# Table 3.1's own HTML rendering (https://database.mma.gov.mv/mosac/latest/3.1.html),
# which rounds to the nearest whole thousand and matched on every month.
TOTAL_ARRIVALS_THOUSANDS = {
    "2025-06": 141.77,
    "2025-07": 186.74,
    "2025-08": 192.06,
    "2025-09": 149.56,
    "2025-10": 190.45,
    "2025-11": 195.13,
    "2025-12": 224.46,
    "2026-01": 224.79,
    "2026-02": 247.72,
    "2026-03": 161.26,
    "2026-04": 147.60,
    "2026-05": 139.75,
}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, total_arrivals_thousands,
    total_arrivals) covering TOTAL_ARRIVALS_THOUSANDS."""
    rows = []
    for ref_date, thousands in TOTAL_ARRIVALS_THOUSANDS.items():
        rows.append({
            "ref_date": ref_date,
            "total_arrivals_thousands": thousands,
            # Rounded to the nearest tourist -- the source page only
            # carries 2 decimal places in thousands, so this is precise to
            # roughly +/-10 tourists, not an exact reported count.
            "total_arrivals": round(thousands * 1000),
        })

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
    peak = df.loc[df["total_arrivals"].idxmax()]
    print(f"Sanity check -- peak month: {peak['ref_date']} at {peak['total_arrivals']:,} arrivals")


if __name__ == "__main__":
    main()
