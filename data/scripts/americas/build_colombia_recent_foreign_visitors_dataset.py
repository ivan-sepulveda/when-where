"""
Data Source: Migracion Colombia / OEE-MinCIT, "Extranjeros no residentes - Mensual" (Grafico 1)
URL: https://www.mincit.gov.co/getattachment/estudios-economicos/estadisticas-e-informes/informes-de-turismo/2025/diciembre/oee-nl-turismo-diciembre-2025.pdf.aspx
Tables Referenced: Grafico 1. Extranjeros no residentes mensual, January 2022 - January 2026

Builds a tidy monthly CSV of Colombia's non-resident foreign visitors
(Migracion Colombia's border-crossing count, the country's standard
tourism-arrivals proxy) for the most recent 12 published months (Feb 2025
- Jan 2026), hand-transcribed since each bar in the source chart has its
value printed directly on it rather than being available as a download.
January 2026's value (408,525) and its -11.3% month-over-month drop from
December 2025 (460,572) both match the report's own callout text, a
useful cross-check on the transcription. Comparable in spirit to the
Maldives and Indonesia arrivals figures used elsewhere in this project.

Usage:
    python build_colombia_recent_foreign_visitors_dataset.py
"""

from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "colombia_recent_foreign_visitors_monthly.csv"

# Transcribed directly from Grafico 1's per-bar labels -- most recent 12
# published months as of this data pull (through January 2026).
FOREIGN_VISITORS = {
    "2025-02": 395445,
    "2025-03": 397879,
    "2025-04": 364830,
    "2025-05": 348119,
    "2025-06": 367588,
    "2025-07": 444898,
    "2025-08": 420001,
    "2025-09": 329824,
    "2025-10": 354982,
    "2025-11": 394929,
    "2025-12": 460572,
    "2026-01": 408525,
}


def build_dataset() -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, foreign_visitors) covering FOREIGN_VISITORS."""
    rows = [{"ref_date": ref_date, "foreign_visitors": count} for ref_date, count in FOREIGN_VISITORS.items()]
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

    jan26 = df.loc[df["ref_date"] == "2026-01", "foreign_visitors"].iloc[0]
    dec25 = df.loc[df["ref_date"] == "2025-12", "foreign_visitors"].iloc[0]
    pct_change = (jan26 / dec25 - 1) * 100
    print(f"Sanity check -- Jan 2026 vs Dec 2025: {pct_change:.1f}% (report says -11.3%)")


if __name__ == "__main__":
    main()
