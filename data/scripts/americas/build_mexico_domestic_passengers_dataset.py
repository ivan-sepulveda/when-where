"""
Build a tidy monthly Mexico scheduled-domestic-operations passenger CSV
from AFAC's (Agencia Federal de Aviación Civil) "Monthly Bulletin of
Operational Statistics" -- December 2025 edition -- "Monthly passengers
transported in Scheduled Domestic Operations (millions)" chart, page 3 of
data/raw/mexico_afac/boletin-en-dic-2025-27012026.pdf.

Like build_costa_rica_monthly_tourism_dataset.py, this has NO live fetch
behind it -- AFAC publishes this bulletin as a PDF with the monthly series
shown only as a chart (2023/2024/2025 lines), not as a downloadable table,
so the values below were hand-transcribed directly from the chart's own
data-point labels. Confirmed against a direct `pdftotext -layout`
extraction of the source PDF: the chart's layout scrambles the reading
order of the labels, but every 2025 value below appears verbatim
somewhere in that extraction, and the user separately confirmed them
against a screenshot of the same chart -- both matched exactly.
MONTHLY_PASSENGERS_MILLIONS_2025 IS the source of truth here; there is
deliberately no fetch_*() function. Landing page for future bulletins:
https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404
(the direct PDF URL for this specific edition is
https://www.gob.mx/cms/uploads/attachment/file/1051970/boletin-es-dic-2025-27012026.pdf
for the Spanish edition -- AFAC publishes matching "-es-" and "-en-"
PDFs each month).

**What this measures:** total passengers transported on SCHEDULED
DOMESTIC flights within Mexico, all Mexican airlines combined (see the
bulletin's "MEXICAN AIRLINES" breakdown for the per-carrier split, not
used here), in millions, per month. This is domestic air travel volume,
NOT inbound international tourism -- the same caveat noted for Canada's
StatCan Transborder-movements series elsewhere in this project (see
compute_peak_tourism_indicator.py's "Canada specifically" note): a busy
month for Mexican domestic flying isn't the same signal as a busy month
for international visitor arrivals, though the two likely correlate
(domestic leisure travel still clusters around the same holiday/vacation
periods as inbound tourism).

Only 2025 is transcribed here (the year requested for this project's
scoring), even though the chart also shows 2023 and 2024 lines -- 2024's
line does carry its own data-point labels in the source chart and could
be transcribed later if a second year is wanted, but 2023's line has no
data-point labels at all, so it isn't recoverable from this source.

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
