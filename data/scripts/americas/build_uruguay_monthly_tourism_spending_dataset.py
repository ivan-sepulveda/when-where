"""
Data Source: Uruguay Ministerio de Turismo, "Observatorio de Turismo
Inteligente", Turismo Receptivo dashboard, "Evolucion mensual del gasto"
chart (2024)
URL: https://turismo.gub.uy/observatorio/turismoReceptivo.html

Builds a tidy monthly CSV of Uruguay's inbound tourism spending (foreign
currency receipts from non-resident visitors, in USD millions) for
calendar year 2024, hand-transcribed from the observatory's chart (the
dashboard itself is an embedded Tableau visualization with no downloadable
export). Verified against public reporting: the 12 monthly figures here
sum to exactly 1,750 (USD millions), matching Uruguay's own reported 2024
annual tourism foreign-currency receipts of US$1,750 million -- a strong
cross-check that the transcription and units (USD millions, not Uruguayan
pesos) are both correct. Unlike this project's headcount-based country
sources, this is a spending signal, comparable in spirit to Brazil's
share-of-visits percentage or Costa Rica's hotel occupancy in that it
isn't a visitor count.

Usage:
    python build_uruguay_monthly_tourism_spending_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "uruguay_monthly_tourism_spending.csv"

YEAR = 2024

# Transcribed from the "Evolucion mensual del gasto" chart, USD millions.
MONTHLY_SPENDING_USD_MILLIONS = {
    "2024-01": 312,
    "2024-02": 229,
    "2024-03": 169,
    "2024-04": 110,
    "2024-05": 93,
    "2024-06": 87,
    "2024-07": 119,
    "2024-08": 84,
    "2024-09": 106,
    "2024-10": 112,
    "2024-11": 128,
    "2024-12": 201,
}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, spending_usd_millions) for YEAR."""
    rows = [
        {"ref_date": ref_date, "spending_usd_millions": value}
        for ref_date, value in MONTHLY_SPENDING_USD_MILLIONS.items()
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

    annual_sum = df["spending_usd_millions"].sum()
    print(f"Sanity check -- sum of 12 months: US${annual_sum}M (Uruguay's own reported 2024 total: US$1,750M)")

    peak = df.loc[df["spending_usd_millions"].idxmax()]
    print(f"Sanity check -- peak month: {peak['ref_date']} at US${peak['spending_usd_millions']}M")


if __name__ == "__main__":
    main()
