"""
Data Source: UN Tourism Dashboard, "Brazil: Share by Month (%)"
URL: https://www.untourism.int/tourism-data/un-tourism-tourism-dashboard
Tables Referenced: Brazil monthly share-of-annual-visits chart, pulled May 2026

Builds a tidy monthly CSV of Brazil's share of annual tourist arrivals by
calendar month (%), hand-transcribed from the dashboard's own bar chart --
no bulk download or API was found for this view. The dashboard doesn't
say which year (or trailing window) the shares are computed over, so YEAR
below is a cosmetic placeholder; only the month-to-month percentages
matter for scoring. Values sum to 100% across the 12 months, which is a
useful transcription check. Unlike passenger-count sources elsewhere in
this project, share_pct isn't a headcount -- treat it like Costa Rica's
occupancy_pct: fine for reading Brazil's own peak-season shape, not a
market-size proxy against other countries.

Usage:
    python build_brazil_monthly_tourism_share_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "brazil_monthly_tourism_share.csv"

YEAR = 2025  # placeholder -- dashboard doesn't specify a year, see module docstring

# Transcribed from the UN Tourism Dashboard's "Brazil: Share by Month (%)"
# bar chart (pulled May 2026). Sums to 100%.
SHARE_BY_MONTH_PCT = {
    1: 16,
    2: 14,
    3: 10,
    4: 7,
    5: 5,
    6: 5,
    7: 7,
    8: 6,
    9: 6,
    10: 6,
    11: 8,
    12: 10,
}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, share_pct) for YEAR."""
    total = sum(SHARE_BY_MONTH_PCT.values())
    if total != 100:
        raise ValueError(f"SHARE_BY_MONTH_PCT sums to {total}, expected 100 -- re-check the transcription.")

    rows = [
        {"ref_date": f"{YEAR}-{month:02d}", "share_pct": pct}
        for month, pct in SHARE_BY_MONTH_PCT.items()
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
    peak = df.loc[df["share_pct"].idxmax()]
    print(f"Sanity check -- peak month: {peak['ref_date']} at {peak['share_pct']}%")


if __name__ == "__main__":
    main()
