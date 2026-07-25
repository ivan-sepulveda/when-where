"""
Data Source: Vietnam National Administration of Tourism, "International
visitor arrivals" monthly statistic
URL: https://vietnamtourism.gov.vn/en/statistic/international

Builds a tidy monthly CSV of Vietnam's total international visitor
arrivals, hand-transcribed from the site's own monthly "Total" figure --
no API or downloadable table is published, only this rendered per-month
page. Same no-live-fetch, hand-transcribed pattern as Colombia and
Maldives elsewhere in this project: re-transcribe by hand once a newer
month is published.

Covers the most recent 12 published months (Jul 2025 - Jun 2026) as of
this data pull. January 2026's figure (2,453,724) is itself still marked
"(estimate)" on the source site -- not yet a finalized count -- flagged
via the `is_estimate` column rather than silently treated the same as
the finalized months.

Usage:
    python build_vietnam_monthly_visitors_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "asia"
OUTPUT_FILENAME = "vietnam_monthly_visitors.csv"

# Transcribed directly from https://vietnamtourism.gov.vn/en/statistic/international,
# each month's own "Total" figure (thousands separators in the source use
# periods, e.g. "1.678.281" -- that's 1,678,281, not 1.678281).
TOTAL_ARRIVALS = {
    "2025-07": 1_562_588,
    "2025-08": 1_684_972,
    "2025-09": 1_523_388,
    "2025-10": 1_732_942,
    "2025-11": 1_978_174,
    "2025-12": 2_021_619,
    "2026-01": 2_453_724,  # marked "(estimate)" on the source site
    "2026-02": 2_228_372,
    "2026-03": 2_080_079,
    "2026-04": 2_031_519,
    "2026-05": 1_779_875,
    "2026-06": 1_678_281,
}

# Months whose source figure is still labeled "(estimate)" rather than final.
ESTIMATED_MONTHS = {"2026-01"}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, total_arrivals, is_estimate)."""
    rows = [
        {
            "ref_date": ref_date,
            "total_arrivals": arrivals,
            "is_estimate": ref_date in ESTIMATED_MONTHS,
        }
        for ref_date, arrivals in TOTAL_ARRIVALS.items()
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

    peak = df.loc[df["total_arrivals"].idxmax()]
    print(f"Sanity check -- peak month: {peak['ref_date']} at {peak['total_arrivals']:,} arrivals"
          f"{' (estimate)' if peak['is_estimate'] else ''}")


if __name__ == "__main__":
    main()
