"""
Build data/processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv: for each
country and calendar month, how busy inbound travel is relative to that
country's own peak month -- a 0-1 "seasonality" ratio.

Two source families feed this, using two different methods (see below):

  - Europe: processed/europe/eurostat_passengers_transported_by_country_monthly_*.csv
    (air passengers transported; see scripts/europe/fetch_eurostat_dataset.py)
  - Australia + New Zealand: processed/oceana/abs_visitor_arrivals_monthly.csv
    and processed/oceana/statsnz_visitor_arrivals_monthly.csv (visitor
    arrivals, not air passengers; see scripts/oceana/fetch_abs_visitor_arrivals.py
    and scripts/oceana/fetch_statsnz_visitor_arrivals.py)

This script itself stays at scripts/ root (and writes its own output to
processed/ root) since it isn't a geography-scoped fetch -- only its
inputs are.

**Method for Europe (Eurostat), per country:**
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

**Method for Australia + New Zealand, per country -- LATEST 12 MONTHS ONLY:**
Unlike the Eurostat side, the ABS series runs back to 1976 and using its
full history would score a month against a decades-old peak that may no
longer be representative (and Stats NZ's Table 1 only carries 5 fiscal
years to begin with, so "full history" isn't really comparable across the
two sources anyway). Instead:

    latest_12 = df.sort_values("ref_date").tail(12)   # most recent 12 rows
    MAX_VALUE = latest_12["value"].max()
    PEAK_RATIO(month) = value(month) / MAX_VALUE

Both sources' processed CSVs happen to run through 2026-05 as of this
writing, so "latest 12 months" is Jun 2025 - May 2026 for both AU and NZ
-- one row per calendar month, no deduplication needed since each source
has exactly one observation per ref_date. `SOURCE_YEAR` records the
calendar year each month's observation actually fell in (so e.g. MONTH=6
is SOURCE_YEAR=2025 while MONTH=5 is SOURCE_YEAR=2026).

The "value" column differs by source: ABS Table 1's `short_term_visitors_
arriving` (short-term overseas visitor arrivals -- the closest ABS column
to "how many tourists arrived this month") and Stats NZ Table 1's
`visitor_arrivals`. Both land in the output's generic `PASSENGERS` column
for schema consistency with the Eurostat rows, even though they're visitor
arrivals counts, not air-passenger counts -- these are two different
proxies for "how much inbound travel is happening," not directly
comparable in magnitude across sources, only within a single country's own
row of PEAK_RATIO values.

Usage:
    python compute_peak_tourism_indicator.py
    python compute_peak_tourism_indicator.py --input ../processed/europe/eurostat_passengers_transported_by_country_monthly_TOTAL.csv
    python compute_peak_tourism_indicator.py --tra-cov NAT   # score national-only traffic instead of total
    python compute_peak_tourism_indicator.py --skip-au-nz    # Eurostat countries only, old behavior
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

# Australia + New Zealand: (source CSV filename in processed/oceana/, value
# column to score, ISO alpha-2 code, display name). Scored on latest-12-months
# only -- see module docstring for why this differs from the Eurostat method.
AU_NZ_SOURCES = [
    ("abs_visitor_arrivals_monthly.csv", "short_term_visitors_arriving", "AU", "Australia"),
    ("statsnz_visitor_arrivals_monthly.csv", "visitor_arrivals", "NZ", "New Zealand"),
]

# ---------------------------------------------------------------------------

# Output stays at processed/ root (this script isn't a geography-scoped
# fetch), but its Eurostat input now lives under processed/europe/, and the
# AU/NZ input lives under processed/oceana/.
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
SOURCE_DIR = PROCESSED_DIR / "europe"
OCEANA_DIR = PROCESSED_DIR / "oceana"


def find_source_csv() -> Path:
    matches = sorted(SOURCE_DIR.glob(SOURCE_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(
            f"No file matching {SOURCE_GLOB!r} in {SOURCE_DIR}/ -- run "
            f"scripts/europe/fetch_eurostat_dataset.py TTR00016 --filter tra_cov={TRA_COV_FILTER} first."
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


def build_latest_12_months_indicator(csv_path: Path, value_col: str, country_code: str, country_name: str) -> pd.DataFrame:
    """Score one AU/NZ-style monthly CSV (columns: ref_date 'YYYY-MM' + a
    value column) against its own latest-12-months peak. See module
    docstring for why this uses a rolling 12-month window instead of the
    Eurostat side's full-history max."""
    df = pd.read_csv(csv_path)
    required = {"ref_date", value_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{csv_path} is missing expected column(s) {missing}")

    df = df.sort_values("ref_date")
    latest_12 = df.tail(12)
    if len(latest_12) < 12:
        print(f"WARNING: {csv_path.name} has only {len(latest_12)} month(s) of data -- expected 12.")

    max_value = latest_12[value_col].max()
    if pd.isna(max_value) or max_value <= 0:
        raise ValueError(f"{csv_path} has no usable data in column {value_col!r} over its latest 12 months.")

    rows = []
    for _, row in latest_12.iterrows():
        year, month = row["ref_date"].split("-")
        rows.append({
            "COUNTRY": country_code,
            "MONTH": int(month),
            "PEAK_RATIO": round(row[value_col] / max_value, 4),
            "COUNTRY_NAME": country_name,
            "SOURCE_YEAR": int(year),
            "PASSENGERS": int(row[value_col]),
        })

    return pd.DataFrame(rows).sort_values("MONTH").reset_index(drop=True)


def build_au_nz_indicator(skip: bool = False) -> pd.DataFrame:
    if skip:
        return pd.DataFrame(columns=["COUNTRY", "MONTH", "PEAK_RATIO", "COUNTRY_NAME", "SOURCE_YEAR", "PASSENGERS"])

    frames = []
    for filename, value_col, country_code, country_name in AU_NZ_SOURCES:
        csv_path = OCEANA_DIR / filename
        if not csv_path.exists():
            print(f"WARNING: {csv_path} not found -- skipping {country_name}. "
                  f"Run the corresponding scripts/oceana/fetch_*.py first.")
            continue
        print(f"Reading {csv_path}...")
        frames.append(build_latest_12_months_indicator(csv_path, value_col, country_code, country_name))

    if not frames:
        return pd.DataFrame(columns=["COUNTRY", "MONTH", "PEAK_RATIO", "COUNTRY_NAME", "SOURCE_YEAR", "PASSENGERS"])
    return pd.concat(frames, ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help=f"Path to the source CSV (default: auto-detect via glob {SOURCE_GLOB!r} in data/processed/europe/)",
    )
    parser.add_argument(
        "--tra-cov",
        default=TRA_COV_FILTER,
        help=f"Which tra_cov category to score (default: {TRA_COV_FILTER!r})",
    )
    parser.add_argument(
        "--skip-au-nz",
        action="store_true",
        help="Score Eurostat countries only, skipping Australia/New Zealand (old behavior).",
    )
    args = parser.parse_args()

    source_path = args.input or find_source_csv()
    print(f"Reading {source_path}...")
    df = load_source(source_path)

    eurostat_out = build_peak_tourism_indicator(df, tra_cov=args.tra_cov)
    au_nz_out = build_au_nz_indicator(skip=args.skip_au_nz)

    out = pd.concat([eurostat_out, au_nz_out], ignore_index=True).sort_values(["COUNTRY", "MONTH"]).reset_index(drop=True)

    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    out.to_csv(out_path, index=False)
    print(f"Wrote {len(out)} rows ({out['COUNTRY'].nunique()} countries) -> {out_path}")


if __name__ == "__main__":
    main()
