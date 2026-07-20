"""
Build data/processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv: for each
country and calendar month, how busy air travel is relative to that
country's own peak month -- a 0-1 "seasonality" ratio derived from
processed/eurostat_passengers_transported_by_country_monthly_*.csv (see
fetch_eurostat_dataset.py).

Method, per country:
    MAX_PASSENGERS = max(value) across every month/year currently fetched
    PEAK_RATIO(month) = value(month) / MAX_PASSENGERS

    e.g. for France:
        FRANCE = df[df["geo"] == "FR"]
        FR_MAX_PASSENGERS = FRANCE["value"].max()
        FRANCE["value_scaled"] = FRANCE["value"] / FR_MAX_PASSENGERS

`MONTH` is an integer 1-12 (1 = January), taken directly from the source
`time` column's "YYYY-MM" format.

Eurostat's monthly dataset (TTR00016) doesn't cover one full calendar
year yet -- as of this writing it's Feb 2025 through May 2026, so four
months (Feb-May) have two years of data each and the rest have one. Where
a month has more than one year available, this script keeps only the
MORE RECENT year's observation for that month (e.g. April 2026 over
April 2025) -- so the output has exactly one row per (country, month),
never two, even though the source spans parts of two calendar years.
`SOURCE_YEAR` in the output records which year's observation was kept,
for transparency.

`PEAK_RATIO` is always scaled against MAX_PASSENGERS from the FULL
fetched history (both years), not just the deduplicated rows -- so a
month whose only available year got dropped in favor of a more recent
one can still correctly show as less than 1.0 relative to a true peak
that happened to fall in the dropped year.

Rows for Eurostat's EU/euro-area aggregate `geo` codes (EU27_2020, EA21,
EA20, EA19) are dropped -- they're not countries, so don't belong in a
"peak tourism indicator by country" table.

Usage:
    python compute_peak_tourism_indicator.py
    python compute_peak_tourism_indicator.py --input ../processed/eurostat_passengers_transported_by_country_monthly_TOTAL.csv
    python compute_peak_tourism_indicator.py --tra-cov NAT   # score national-only traffic instead of total
"""

import argparse
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

# Which tra_cov category to score. TOTAL = national + international
# combined, matching the scope of the old yearly dataset (TTR00012). See
# fetch_eurostat_dataset.py / data/README.md for the other tra_cov values.
TRA_COV_FILTER = "TOTAL"

# Eurostat `geo` codes that are EU/euro-area aggregates, not countries --
# excluded from the output.
AGGREGATE_GEO_CODES = {"EU27_2020", "EA21", "EA20", "EA19"}

# Glob pattern used to find the source CSV when --input isn't given
# explicitly. A pattern (not a fixed filename) because
# fetch_eurostat_dataset.py's output filename encodes whichever --filter
# was used (e.g. "..._TOTAL.csv", "..._NAT.csv").
SOURCE_GLOB = "eurostat_passengers_transported_by_country_monthly_*.csv"

OUTPUT_FILENAME = "PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv"  # ALL_CAPS by request, unlike this project's other processed/ outputs

# ---------------------------------------------------------------------------

PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"


def find_source_csv() -> Path:
    matches = sorted(PROCESSED_DIR.glob(SOURCE_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(
            f"No file matching {SOURCE_GLOB!r} in {PROCESSED_DIR}/ -- run "
            f"fetch_eurostat_dataset.py TTR00016 --filter tra_cov={TRA_COV_FILTER} first."
        )
    if len(matches) > 1:
        print(f"Note: multiple files match {SOURCE_GLOB!r} -- using the most recently modified: {matches[0].name}")
    return matches[0]


def load_source(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"geo", "geo_label", "tra_cov", "time", "value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} is missing expected column(s) {missing} -- is this really a TTR00016 export?")
    return df


def build_peak_tourism_indicator(df: pd.DataFrame, tra_cov: str = TRA_COV_FILTER) -> pd.DataFrame:
    df = df[df["tra_cov"] == tra_cov].copy()
    if df.empty:
        raise ValueError(
            f"No rows with tra_cov == {tra_cov!r} in the source data -- check the "
            f"file was fetched with --filter tra_cov={tra_cov}, or pass --tra-cov to match what it has."
        )

    df = df[~df["geo"].isin(AGGREGATE_GEO_CODES)]
    df["year"] = df["time"].str.slice(0, 4).astype(int)
    df["month"] = df["time"].str.slice(5, 7).astype(int)

    rows = []
    skipped_no_data = []
    for geo, group in df.groupby("geo", sort=True):
        max_passengers = group["value"].max()
        if pd.isna(max_passengers) or max_passengers <= 0:
            skipped_no_data.append(geo)
            continue

        country_name = group["geo_label"].iloc[0]

        # Keep only the most recent year's row for each calendar month --
        # sort newest-year-first, then drop_duplicates keeps the first
        # (i.e. most recent) row per month.
        deduped = group.sort_values("year", ascending=False).drop_duplicates(subset="month", keep="first")

        for _, row in deduped.iterrows():
            rows.append({
                "COUNTRY": geo,
                "MONTH": int(row["month"]),
                "PEAK_RATIO": round(row["value"] / max_passengers, 4),
                "COUNTRY_NAME": country_name,
                "SOURCE_YEAR": int(row["year"]),
                "PASSENGERS": int(row["value"]),
            })

    if skipped_no_data:
        print(f"Skipped {len(skipped_no_data)} geo code(s) with no usable data: {sorted(skipped_no_data)}")

    out = pd.DataFrame(rows).sort_values(["COUNTRY", "MONTH"]).reset_index(drop=True)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=f"Path to the source CSV (default: auto-detect via glob {SOURCE_GLOB!r} in data/processed/)",
    )
    parser.add_argument(
        "--tra-cov",
        default=TRA_COV_FILTER,
        help=f"Which tra_cov category to score (default: {TRA_COV_FILTER!r})",
    )
    args = parser.parse_args()

    source_path = args.input or find_source_csv()
    print(f"Reading {source_path}...")
    df = load_source(source_path)

    out = build_peak_tourism_indicator(df, tra_cov=args.tra_cov)

    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    out.to_csv(out_path, index=False)
    print(f"Wrote {len(out)} rows ({out['COUNTRY'].nunique()} countries) -> {out_path}")


if __name__ == "__main__":
    main()
