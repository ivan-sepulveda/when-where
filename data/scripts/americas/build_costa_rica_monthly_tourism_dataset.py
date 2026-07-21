"""
Build a tidy monthly Costa Rica hotel-occupancy CSV from CUADRO 3 of
data/raw/costa_rica_tourism/COSTA_RICA_TOURISM_2020_2025.pdf -- "Porcentaje
de Ocupación mensual y promedio anual, 2018-2024" (Banco Central de Costa
Rica). Table 3 is on page 5 of the PDF (`pdf.pages[4]`, 0-indexed).

Unlike every other fetch/build script in this project, this one has NO live
source -- Banco Central de Costa Rica doesn't appear to publish this table
through any API this project could find, so the user supplied the PDF
directly (saved to data/raw/costa_rica_tourism/) and the table below was
manually transcribed from it, confirmed against both a direct read of page
5's extracted text and a cropped image of the same table the user posted
inline -- the two matched exactly. There is deliberately no `fetch_*()`
function here; `CUADRO_3_OCCUPANCY_PCT` IS the source of truth, and it
should be re-transcribed by hand if Costa Rica ever publishes an updated
PDF (the doc covers 2020-2026 issue dates, but Cuadro 3 itself only ever
carried 2018-2024 -- Banco Central's own table title, not a limitation of
this script).

**What %OCUP actually measures:** hotel occupancy percentage (surveyed
hotels only), NOT a visitor-arrivals count -- a different kind of signal
than every other country currently in this project (AU/NZ/JP/CA all use
some flavor of arrivals/entries/movements counts; Europe uses air
passengers). It's bounded 0-100 by construction, so a "peak ratio" scored
against occupancy will compress differently than one scored against a
count (a swing from 36.7% to 83.5% occupancy is a ~2.3x ratio, whereas a
swing in raw arrivals for other countries can be much larger) -- worth
keeping in mind if Costa Rica's PEAK_RATIO curve looks flatter than other
countries' once this feeds into compute_peak_tourism_indicator.py.

Note CUADRO 1 (page 3 of the same PDF) also carries a monthly hotel-
activity index (IMAH, "Índice Mensual de la Actividad Hotelera") through
2025/2026 -- a candidate for a future script if a count-style signal
closer to the other countries' is wanted instead of/alongside occupancy.
Not used here since this script was scoped to Cuadro 3 specifically.

Usage:
    python build_costa_rica_monthly_tourism_dataset.py                # 2024 (default)
    python build_costa_rica_monthly_tourism_dataset.py --year 2022
    python build_costa_rica_monthly_tourism_dataset.py --all-years     # every year in the table, 2018-2024
"""

import argparse
from pathlib import Path

import pandas as pd

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "americas"
OUTPUT_FILENAME = "costa_rica_monthly_hotel_occupancy.csv"

DEFAULT_YEAR = 2024

# Transcribed directly from CUADRO 3 ("Porcentaje de Ocupación mensual y
# promedio anual, 2018-2024"), page 5 of
# data/raw/costa_rica_tourism/COSTA_RICA_TOURISM_2020_2025.pdf. Values are
# %OCUP (hotel occupancy percentage), comma-decimal in the source PDF,
# stored here as floats. 2020-2021 show the COVID-19 collapse (occupancy
# as low as 0.5% in May 2020) -- kept as-is, not treated as bad data.
CUADRO_3_OCCUPANCY_PCT = {
    "Enero":     {2018: 81.0, 2019: 76.8, 2020: 77.2, 2021: 29.6, 2022: 61.4, 2023: 76.8, 2024: 76.3},
    "Febrero":   {2018: 87.2, 2019: 82.8, 2020: 82.4, 2021: 27.0, 2022: 64.3, 2023: 80.3, 2024: 83.5},
    "Marzo":     {2018: 84.0, 2019: 82.8, 2020: 39.4, 2021: 39.1, 2022: 70.5, 2023: 76.6, 2024: 81.8},
    "Abril":     {2018: 76.4, 2019: 70.4, 2020: 2.8,  2021: 40.5, 2022: 68.6, 2023: 70.1, 2024: 69.8},
    "Mayo":      {2018: 61.4, 2019: 60.2, 2020: 0.5,  2021: 37.6, 2022: 58.7, 2023: 57.9, 2024: 62.0},
    "Junio":     {2018: 62.0, 2019: 63.6, 2020: 2.6,  2021: 45.9, 2022: 64.2, 2023: 63.0, 2024: 64.4},
    "Julio":     {2018: 69.6, 2019: 68.6, 2020: 3.8,  2021: 54.9, 2022: 67.8, 2023: 68.5, 2024: 65.8},
    "Agosto":    {2018: 63.0, 2019: 63.2, 2020: 6.0,  2021: 47.2, 2022: 63.7, 2023: 60.4, 2024: 57.4},
    "Setiembre": {2018: 42.2, 2019: 48.1, 2020: 13.0, 2021: 38.8, 2022: 44.8, 2023: 46.3, 2024: 36.7},
    "Octubre":   {2018: 45.6, 2019: 47.3, 2020: 9.8,  2021: 38.8, 2022: 49.1, 2023: 44.2, 2024: 42.5},
    "Noviembre": {2018: 65.6, 2019: 68.3, 2020: 17.4, 2021: 54.3, 2022: 67.8, 2023: 67.5, 2024: 68.5},
    "Diciembre": {2018: 70.4, 2019: 70.5, 2020: 28.4, 2021: 65.5, 2022: 71.9, 2023: 71.9, 2024: 69.0},
}

MONTH_TO_NUM = {
    "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4, "Mayo": 5, "Junio": 6,
    "Julio": 7, "Agosto": 8, "Setiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12,
}


def build_dataset(years: list[int] | None = None) -> pd.DataFrame:
    """Return a tidy DataFrame (ref_date, occupancy_pct) for the given
    year(s) -- defaults to every year transcribed if `years` is None."""
    rows = []
    for month_name, month_num in MONTH_TO_NUM.items():
        for year, value in CUADRO_3_OCCUPANCY_PCT[month_name].items():
            if years is not None and year not in years:
                continue
            rows.append({"ref_date": f"{year}-{month_num:02d}", "occupancy_pct": value})

    if not rows:
        raise ValueError(f"No rows for years={years!r} -- CUADRO_3_OCCUPANCY_PCT only covers 2018-2024.")

    return pd.DataFrame(rows).sort_values("ref_date").reset_index(drop=True)


def write_output(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR, help=f"Single year to write (default: {DEFAULT_YEAR}). Ignored if --all-years is set.")
    parser.add_argument("--all-years", action="store_true", help="Write every year in CUADRO_3_OCCUPANCY_PCT (2018-2024) instead of a single year.")
    args = parser.parse_args()

    years = None if args.all_years else [args.year]
    df = build_dataset(years=years)

    out_path = write_output(df)
    print(f"Wrote {len(df)} rows ({df['ref_date'].min()} - {df['ref_date'].max()}) -> {out_path}")


if __name__ == "__main__":
    main()
