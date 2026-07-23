"""
Build a tidy monthly Mexico INTERNATIONAL air passenger CSV from AFAC's
(Agencia Federal de Aviación Civil) "Monthly Bulletin of Operational
Statistics" -- December 2025 edition -- summing two charts:

  - Page 7: "Monthly passengers transported in Scheduled International
    Operations, Mexican Airlines (millions)"
  - Page 9: "Monthly passengers transported in Scheduled International
    Operations, Foreign Airlines (millions)"

Both from data/raw/mexico_afac/boletin-en-dic-2025-27012026.pdf.

**This supersedes build_mexico_domestic_passengers_dataset.py for scoring
purposes.** That script transcribed the bulletin's SCHEDULED DOMESTIC
Operations chart (page 3) -- domestic Mexican air travel, not
international. compute_peak_tourism_indicator.py originally used that
domestic series as Mexico's "how much travel is happening" signal, but
every other country in this project's EXTRA_COUNTRY_SOURCES/CANADA_SOURCE
uses an INTERNATIONAL signal (arrivals, border entries, transborder
movements, overnight stays by foreign+resident visitors combined), so the
domestic-only series was the wrong chart for consistency with the rest of
the table -- this script's `passengers` column (Mexican + Foreign
airlines, international, summed) is the corrected replacement.
build_mexico_domestic_passengers_dataset.py and its output CSV are left
in place (the domestic data is still real and may be useful elsewhere),
just no longer wired into compute_peak_tourism_indicator.py.

Like both Costa Rica's and the domestic Mexico script, this has NO live
fetch behind it -- AFAC publishes both charts as images with data-point
labels, not downloadable tables, so the values below were hand-
transcribed from each chart's own labels. Cross-checked against a direct
`pdftotext -layout` extraction of the source PDF (the chart layout
scrambles the labels' reading order, but every value below appears
verbatim in that extraction) and against the user's own screenshots of
both charts -- all matched exactly, including the user's independent
spot-check that December 2025's two values sum to 5.90M (1.80 + 4.10).
MONTHLY_PASSENGERS_MILLIONS_2025 (the combined dict built from the two
transcribed source dicts below) IS the source of truth here; there is
deliberately no fetch_*() function.

**What this measures:** total passengers on SCHEDULED INTERNATIONAL
flights to/from Mexico, Mexican airlines' international operations plus
foreign airlines' operations into Mexico combined, in millions per
month. This is a much closer match to "international travel volume" than
the domestic series it replaces -- comparable in spirit to Canada's
StatCan Transborder-movements series or Eurostat's air-passenger figures
elsewhere in this project (all air-passenger counts, not visitor-arrivals
counts, so still not identical in kind to e.g. ABS/Stats NZ's visitor
arrivals or Chile's overnight stays -- see compute_peak_tourism_
indicator.py's "Mexico specifically" note for the full caveat).

Only 2025 is transcribed (the year requested for this project's scoring),
though both charts also show 2023/2024 lines with their own data-point
labels and could be added later if more history is wanted.

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
