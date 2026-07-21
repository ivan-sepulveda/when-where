"""
Build data/processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv: for each
country and calendar month, how busy inbound travel is relative to that
country's own peak month -- a 0-1 "seasonality" ratio.

Two source families feed this, using two different methods (see below):

  - Europe: processed/europe/eurostat_passengers_transported_by_country_monthly_*.csv
    (air passengers transported; see scripts/europe/fetch_eurostat_dataset.py)
  - Australia, New Zealand, Japan (the "EXTRA_COUNTRY_SOURCES" countries):
    processed/oceana/abs_visitor_arrivals_monthly.csv,
    processed/oceana/statsnz_visitor_arrivals_monthly.csv, and
    processed/asia/japan_tourism_indicators_by_month.csv (visitor arrivals /
    border entries, not air passengers; see scripts/oceana/fetch_abs_visitor_arrivals.py,
    scripts/oceana/fetch_statsnz_visitor_arrivals.py, and
    scripts/asia/fetch_japan_tourism_indicators.py)
  - Canada: processed/americas/statcan_airport_movements.csv, filtered to
    GEO == "Canada", Airports == "Total, all airports", "Domestic and
    international itinerant movements" == "Transborder movements" (flight
    movements between Canada and the US only -- see below; see
    scripts/americas/fetch_statcan_airport_movements.py)

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

**Method for AU / NZ / Japan / Canada, per country -- LATEST 12 MONTHS ONLY:**
Unlike the Eurostat side, the ABS series runs back to 1976 and using its
full history would score a month against a decades-old peak that may no
longer be representative (and Stats NZ's Table 1 only carries 5 fiscal
years, e-Stat's Dashboard pull only 16 months, to begin with -- so "full
history" isn't comparable across these sources anyway). Instead, each
source's own most recent 12 monthly rows are used:

    latest_12 = df.sort_values(date_col).tail(12)   # most recent 12 rows
    MAX_VALUE = latest_12[value_col].max()
    PEAK_RATIO(month) = value(month) / MAX_VALUE

As of this writing the four sources' processed CSVs run through 2026-05
(ABS), 2026-05 (Stats NZ), 2026-04 (e-Stat), and 2026-04 (StatCan)
respectively, so "latest 12 months" works out to Jun 2025 - May 2026 for
AU/NZ and May 2025 - Apr 2026 for Japan/Canada -- one row per calendar
month, no deduplication needed since each source has exactly one
observation per month once filtered down (Canada's StatCan table needs
filtering first -- see below). `SOURCE_YEAR` records the calendar year
each month's observation actually fell in (so e.g. for AU/NZ, MONTH=6 is
SOURCE_YEAR=2025 while MONTH=5 is SOURCE_YEAR=2026).

The value column, and the column holding the "YYYY-MM" date, differ by
source (see `EXTRA_COUNTRY_SOURCES`): ABS Table 1's `short_term_visitors_
arriving` (short-term overseas visitor arrivals -- the closest ABS column
to "how many tourists arrived this month"), Stats NZ Table 1's
`visitor_arrivals`, Japan's e-Stat Dashboard pull's `NUM_ENTRIES`
(foreign-national border entries -- see scripts/asia/fetch_japan_tourism_
indicators.py's docstring: this counts ALL foreign-national entries, not
filtered to tourism purpose, so it runs a bit higher than a true
visitor-arrivals count would, e.g. it includes work-visa holders), and
StatCan table 23-10-0304-01's `VALUE` column, filtered per
`CANADA_SOURCE` below. All land in the output's generic `PASSENGERS`
column for schema consistency with the Eurostat rows, even though none of
them are actually air-passenger counts -- these are different proxies for
"how much inbound travel is happening," not directly comparable in
magnitude across sources, only within a single country's own row of
PEAK_RATIO values.

**Canada specifically** -- StatCan table 23-10-0304-01 is one long table
with several breakdown dimensions in the same file (see
fetch_statcan_airport_movements.py's docstring), not a pre-filtered
single series like the AU/NZ/Japan sources, so it needs three equality
filters applied before it becomes a clean one-row-per-month series:
`GEO == "Canada"` (the national total row -- the table also carries the
same "Total, all airports" breakdown per province/territory, which would
silently multiply the row count if not excluded), `Airports == "Total,
all airports"` (vs. individual airports), and `"Domestic and
international itinerant movements" == "Transborder movements"` (flight
movements between Canada and the United States specifically -- NOT
"Domestic movements" or "Other international movements", the table's
other two categories in that dimension). This is a narrower slice than
the AU/NZ/Japan sources: it only captures Canada-US air traffic, not
overseas international arrivals, since that's the category requested for
this table -- worth keeping in mind if Canada's PEAK_RATIO curve looks
different in character from the other countries'.

Usage:
    python compute_peak_tourism_indicator.py
    python compute_peak_tourism_indicator.py --input ../processed/europe/eurostat_passengers_transported_by_country_monthly_TOTAL.csv
    python compute_peak_tourism_indicator.py --tra-cov NAT     # score national-only traffic instead of total
    python compute_peak_tourism_indicator.py --skip-extra      # Eurostat countries only, old behavior
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

# AU / NZ / Japan: each entry is (subdirectory under processed/, source CSV
# filename, name of its "YYYY-MM" date column, value column to score, ISO
# alpha-2 code, display name). Scored on latest-12-months only -- see module
# docstring for why this differs from the Eurostat method. The date column
# name varies by source (ref_date vs MONTH), hence it's part of the config
# rather than assumed.
EXTRA_COUNTRY_SOURCES = [
    ("oceana", "abs_visitor_arrivals_monthly.csv", "ref_date", "short_term_visitors_arriving", "AU", "Australia"),
    ("oceana", "statsnz_visitor_arrivals_monthly.csv", "ref_date", "visitor_arrivals", "NZ", "New Zealand"),
    ("asia", "japan_tourism_indicators_by_month.csv", "MONTH", "NUM_ENTRIES", "JP", "Japan"),
]

# Canada: unlike EXTRA_COUNTRY_SOURCES above, the source CSV (StatCan table
# 23-10-0304-01) isn't a pre-filtered single series -- it needs these three
# equality filters applied first to isolate one row per month. See module
# docstring's "Canada specifically" section for why each filter is needed.
CANADA_SOURCE = {
    "subdir": "americas",
    "filename": "statcan_airport_movements.csv",
    "date_col": "REF_DATE",
    "value_col": "VALUE",
    "filters": {
        "GEO": "Canada",
        "Airports": "Total, all airports",
        "Domestic and international itinerant movements": "Transborder movements",
    },
    "country_code": "CA",
    "country_name": "Canada",
}

# ---------------------------------------------------------------------------

# Output stays at processed/ root (this script isn't a geography-scoped
# fetch), but its Eurostat input lives under processed/europe/, and the
# AU/NZ/Japan/Canada inputs live under processed/oceana/, processed/asia/,
# and processed/americas/ respectively (see EXTRA_COUNTRY_SOURCES and
# CANADA_SOURCE).
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"
SOURCE_DIR = PROCESSED_DIR / "europe"


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


def score_latest_12_months(df: pd.DataFrame, source_label: str, date_col: str, value_col: str, country_code: str, country_name: str) -> pd.DataFrame:
    """Score an already-loaded (and, for Canada, already-filtered) monthly
    DataFrame -- a 'YYYY-MM' date column + a value column -- against its
    own latest-12-months peak. See module docstring for why this uses a
    rolling 12-month window instead of the Eurostat side's full-history
    max. `source_label` is just for the too-few-months warning message."""
    required = {date_col, value_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{source_label} is missing expected column(s) {missing}")

    df = df.sort_values(date_col)
    latest_12 = df.tail(12)
    if len(latest_12) < 12:
        print(f"WARNING: {source_label} has only {len(latest_12)} month(s) of data -- expected 12.")

    max_value = latest_12[value_col].max()
    if pd.isna(max_value) or max_value <= 0:
        raise ValueError(f"{source_label} has no usable data in column {value_col!r} over its latest 12 months.")

    rows = []
    for _, row in latest_12.iterrows():
        year, month = row[date_col].split("-")
        rows.append({
            "COUNTRY": country_code,
            "MONTH": int(month),
            "PEAK_RATIO": round(row[value_col] / max_value, 4),
            "COUNTRY_NAME": country_name,
            "SOURCE_YEAR": int(year),
            "PASSENGERS": int(row[value_col]),
        })

    return pd.DataFrame(rows).sort_values("MONTH").reset_index(drop=True)


def load_canada_source() -> pd.DataFrame | None:
    """Load StatCan table 23-10-0304-01 and apply CANADA_SOURCE's three
    equality filters to isolate the national monthly Transborder-movements
    series. Returns None (with a warning printed) if the source file is
    missing, so callers can skip Canada gracefully like the other sources."""
    csv_path = PROCESSED_DIR / CANADA_SOURCE["subdir"] / CANADA_SOURCE["filename"]
    if not csv_path.exists():
        print(f"WARNING: {csv_path} not found -- skipping Canada. "
              f"Run scripts/americas/fetch_statcan_airport_movements.py first.")
        return None

    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path, low_memory=False)

    missing_cols = set(CANADA_SOURCE["filters"]) - set(df.columns)
    if missing_cols:
        raise ValueError(f"{csv_path} is missing expected column(s) {missing_cols} -- is this really table 23-10-0304-01?")

    for col, expected_value in CANADA_SOURCE["filters"].items():
        df = df[df[col] == expected_value]

    if df.empty:
        raise ValueError(
            f"{csv_path}: filtering to {CANADA_SOURCE['filters']} left zero rows -- "
            f"check the filter values still match this table's current category spellings."
        )

    df[CANADA_SOURCE["date_col"]] = df[CANADA_SOURCE["date_col"]].astype(str)
    dupes = df[CANADA_SOURCE["date_col"]].duplicated()
    if dupes.any():
        raise ValueError(
            f"{csv_path}: {dupes.sum()} duplicate {CANADA_SOURCE['date_col']} value(s) after filtering -- "
            f"the filters in CANADA_SOURCE no longer isolate a single row per month."
        )

    return df


def build_extra_country_indicator(skip: bool = False) -> pd.DataFrame:
    """Build AU/NZ/Japan/Canada rows via the latest-12-months method (see
    EXTRA_COUNTRY_SOURCES and CANADA_SOURCE)."""
    empty = pd.DataFrame(columns=["COUNTRY", "MONTH", "PEAK_RATIO", "COUNTRY_NAME", "SOURCE_YEAR", "PASSENGERS"])
    if skip:
        return empty

    frames = []
    for subdir, filename, date_col, value_col, country_code, country_name in EXTRA_COUNTRY_SOURCES:
        csv_path = PROCESSED_DIR / subdir / filename
        if not csv_path.exists():
            print(f"WARNING: {csv_path} not found -- skipping {country_name}. "
                  f"Run the corresponding scripts/{subdir}/fetch_*.py first.")
            continue
        print(f"Reading {csv_path}...")
        df = pd.read_csv(csv_path)
        frames.append(score_latest_12_months(df, csv_path.name, date_col, value_col, country_code, country_name))

    canada_df = load_canada_source()
    if canada_df is not None:
        frames.append(score_latest_12_months(
            canada_df, CANADA_SOURCE["filename"], CANADA_SOURCE["date_col"], CANADA_SOURCE["value_col"],
            CANADA_SOURCE["country_code"], CANADA_SOURCE["country_name"],
        ))

    if not frames:
        return empty
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
        "--skip-extra",
        action="store_true",
        help="Score Eurostat countries only, skipping Australia/New Zealand/Japan/Canada (old behavior).",
    )
    args = parser.parse_args()

    source_path = args.input or find_source_csv()
    print(f"Reading {source_path}...")
    df = load_source(source_path)

    eurostat_out = build_peak_tourism_indicator(df, tra_cov=args.tra_cov)
    extra_out = build_extra_country_indicator(skip=args.skip_extra)

    out = pd.concat([eurostat_out, extra_out], ignore_index=True).sort_values(["COUNTRY", "MONTH"]).reset_index(drop=True)

    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    out.to_csv(out_path, index=False)
    print(f"Wrote {len(out)} rows ({out['COUNTRY'].nunique()} countries) -> {out_path}")


if __name__ == "__main__":
    main()
