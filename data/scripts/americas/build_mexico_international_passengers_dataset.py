"""
Data Source: AFAC Monthly Bulletin of Operational Statistics, December 2025 edition
URL: https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404
Tables Referenced:
    Page 7 - Monthly passengers transported in Scheduled International Operations, Mexican Airlines (millions)
    Page 9 - Monthly passengers transported in Scheduled International Operations, Foreign Airlines (millions)

Builds a tidy monthly CSV of Mexico's total INTERNATIONAL scheduled-
operations air passengers (Mexican + Foreign airlines summed). No live
fetch -- both charts are image-only in the bulletin, so 2025 values were
hand-transcribed from each chart's data-point labels and cross-checked
against a PDF text extraction and the user's screenshots (December sums
to 5.90M = 1.80 + 4.10, confirmed). Supersedes the earlier DOMESTIC-
operations version of this dataset (build_mexico_domestic_passengers_
dataset.py), which used the wrong chart for consistency with every other
country's international signal in compute_peak_tourism_indicator.py.
Precision is roughly +/-10,000 passengers, since both source charts round
to 2 decimal places in millions.

Usage:
    python build_mexico_international_passengers_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "mexico_international_passengers_monthly.csv"

YEAR = 2025

# Transcribed directly from AFAC's "Monthly passengers transported in
# Scheduled International Operations, Mexican Airlines (millions)" chart --
# Monthly Bulletin of Operational Statistics, December 2025 edition, page 7.
MEXICAN_AIRLINES_MILLIONS_2025 = {
    1: 1.63,   # Jan
    2: 1.24,   # Feb
    3: 1.43,   # Mar
    4: 1.48,   # Apr
    5: 1.40,   # May
    6: 1.44,   # Jun
    7: 1.73,   # Jul
    8: 1.62,   # Aug
    9: 1.33,   # Sep
    10: 1.45,  # Oct
    11: 1.48,  # Nov
    12: 1.80,  # Dec
}

# Transcribed directly from AFAC's "Monthly passengers transported in
# Scheduled International Operations, Foreign Airlines (millions)" chart --
# Monthly Bulletin of Operational Statistics, December 2025 edition, page 9.
FOREIGN_AIRLINES_MILLIONS_2025 = {
    1: 4.02,   # Jan
    2: 3.65,   # Feb
    3: 4.34,   # Mar
    4: 3.59,   # Apr
    5: 3.05,   # May
    6: 3.29,   # Jun
    7: 3.49,   # Jul
    8: 2.92,   # Aug
    9: 2.21,   # Sep
    10: 2.79,  # Oct
    11: 3.50,  # Nov
    12: 4.10,  # Dec
}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, mexican_airlines_millions,
    foreign_airlines_millions, passengers_millions, passengers) for YEAR --
    passengers_millions is the sum of both airline groups, matching how
    AFAC itself frames "Scheduled International Operations" as Mexican +
    Foreign airlines combined."""
    months = sorted(MEXICAN_AIRLINES_MILLIONS_2025)
    assert months == sorted(FOREIGN_AIRLINES_MILLIONS_2025), (
        "MEXICAN_AIRLINES_MILLIONS_2025 and FOREIGN_AIRLINES_MILLIONS_2025 must cover the same months"
    )

    rows = []
    for month in months:
        mx = MEXICAN_AIRLINES_MILLIONS_2025[month]
        foreign = FOREIGN_AIRLINES_MILLIONS_2025[month]
        total_millions = round(mx + foreign, 2)
        rows.append({
            "ref_date": f"{YEAR}-{month:02d}",
            "mexican_airlines_millions": mx,
            "foreign_airlines_millions": foreign,
            "passengers_millions": total_millions,
            # Rounded to the nearest passenger -- both source charts only
            # carry 2 decimal places in millions, so this is precise to
            # roughly +/-10,000 passengers (the two sources' rounding
            # errors compound), not an exact reported count.
            "passengers": round(total_millions * 1_000_000),
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
    dec = df[df["ref_date"] == f"{YEAR}-12"].iloc[0]
    print(f"Sanity check -- Dec {YEAR}: {dec['mexican_airlines_millions']} + {dec['foreign_airlines_millions']} = {dec['passengers_millions']}M")


if __name__ == "__main__":
    main()
