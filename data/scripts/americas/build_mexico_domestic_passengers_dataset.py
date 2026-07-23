"""
Data Source: AFAC Monthly Bulletin of Operational Statistics, December 2025 edition
URL: https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404
Tables Referenced:
    Page 3 - Monthly passengers transported in Scheduled Domestic Operations (millions)

Builds a tidy monthly CSV of Mexico's total DOMESTIC scheduled-operations
air passengers, all Mexican airlines combined. No live fetch -- the chart
is image-only in the bulletin, so 2025 values were hand-transcribed from
its data-point labels and cross-checked against a PDF text extraction and
a user screenshot. Domestic air travel, not international tourism --
compute_peak_tourism_indicator.py no longer uses this dataset (it was
superseded by build_mexico_international_passengers_dataset.py, since
every other country in that script's scoring uses an international
signal), but this file and its output CSV are kept as still-valid data.
Precision is roughly +/-5,000 passengers, since the source chart rounds
to 2 decimal places in millions.

Usage:
    python build_mexico_domestic_passengers_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "mexico_domestic_passengers_monthly.csv"

YEAR = 2025

# Transcribed directly from AFAC's "Monthly passengers transported in
# Scheduled Domestic Operations (millions)" chart -- Monthly Bulletin of
# Operational Statistics, December 2025 edition, page 3. Units: millions
# of passengers.
MONTHLY_PASSENGERS_MILLIONS_2025 = {
    1: 5.07,   # Jan
    2: 4.48,   # Feb
    3: 5.24,   # Mar
    4: 5.44,   # Apr
    5: 5.34,   # May
    6: 5.15,   # Jun
    7: 5.76,   # Jul
    8: 5.67,   # Aug
    9: 4.99,   # Sep
    10: 5.28,  # Oct
    11: 5.42,  # Nov
    12: 5.68,  # Dec
}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, passengers_millions, passengers)
    for YEAR, built from MONTHLY_PASSENGERS_MILLIONS_2025."""
    rows = [
        {
            "ref_date": f"{YEAR}-{month:02d}",
            "passengers_millions": value,
            # Rounded to the nearest passenger -- the source chart only
            # carries 2 decimal places in millions, so this is precise to
            # roughly +/-5,000 passengers, not an exact reported count
            # like most other sources in this project.
            "passengers": round(value * 1_000_000),
        }
        for month, value in MONTHLY_PASSENGERS_MILLIONS_2025.items()
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


if __name__ == "__main__":
    main()
