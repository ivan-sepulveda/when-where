"""
Build data/processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv: for each
country and calendar month, how busy travel is relative to that
country's own peak month (0-1 ratio).

Eurostat countries are scored against their full monthly air-passenger
history. Australia, New Zealand, Japan, Costa Rica, Canada, Chile,
Mexico, Maldives, Indonesia, Brazil, and Colombia (EXTRA_COUNTRY_SOURCES
/ CANADA_SOURCE / CHILE_SOURCE) are scored against only their own latest
12 months, since their sources' full histories aren't long or comparable
enough to use directly. Each non-Eurostat source uses a different
underlying signal -- visitor arrivals, hotel occupancy %, border entries,
transborder flights, overnight stays, share of annual visits, or
international air passengers -- so PEAK_RATIO is comparable only within
a country's own row, never in magnitude across countries. See
data/README.md for full per-source details and caveats, including the
Mexico domestic-vs-international correction.

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

# AU / NZ / Japan / Costa Rica / Mexico: each entry is (subdirectory under
# processed/, source CSV filename, name of its "YYYY-MM" date column, value
# column to score, ISO alpha-2 code, display name). Scored on
# latest-12-months only -- see module docstring for why this differs from
# the Eurostat method. The date column name varies by source (ref_date vs
# MONTH), hence it's part of the config rather than assumed.
EXTRA_COUNTRY_SOURCES = [
    ("oceana", "abs_visitor_arrivals_monthly.csv", "ref_date", "short_term_visitors_arriving", "AU", "Australia"),
    ("oceana", "statsnz_visitor_arrivals_monthly.csv", "ref_date", "visitor_arrivals", "NZ", "New Zealand"),
    ("asia", "japan_tourism_indicators_by_month.csv", "MONTH", "NUM_ENTRIES", "JP", "Japan"),
    ("americas", "costa_rica_monthly_hotel_occupancy.csv", "ref_date", "occupancy_pct", "CR", "Costa Rica"),
    # International (Mexican + Foreign airlines combined), NOT the domestic
    # series -- see data/README.md for why domestic would've been wrong here.
    ("americas", "mexico_international_passengers_monthly.csv", "ref_date", "passengers", "MX", "Mexico"),
    # Hand-transcribed latest-12-months (see build_maldives_recent_arrivals_dataset.py),
    # not the full-history API pull -- data/README.md has the caveat.
    ("asia", "maldives_recent_tourist_arrivals_monthly.csv", "ref_date", "total_arrivals", "MV", "Maldives"),
    # BPS GRAND TOTAL row (all passport nationalities combined), only 2025
    # is published -- see build_indonesia_monthly_tourist_visits_dataset.py.
    ("asia", "indonesia_bps_tourist_visits_monthly.csv", "ref_date", "total_visits", "ID", "Indonesia"),
    # Share of annual visits (%), not a headcount -- see
    # build_brazil_monthly_tourism_share_dataset.py.
    ("americas", "brazil_monthly_tourism_share.csv", "ref_date", "share_pct", "BR", "Brazil"),
    # Hand-transcribed latest-12-months (see
    # build_colombia_recent_foreign_visitors_dataset.py), not a full history.
    ("americas", "colombia_recent_foreign_visitors_monthly.csv", "ref_date", "foreign_visitors", "CO", "Colombia"),
]

# Canada: unlike EXTRA_COUNTRY_SOURCES above, the source CSV (StatCan table
# 23-10-0304-01) isn't a pre-filtered single series -- it needs these three
# equality filters applied first to isolate one row per month. See
# data/README.md for why each filter is needed.
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

# Chile: like CANADA_SOURCE, the source CSV (INE's EMAT survey export) isn't
# a pre-filtered single series -- these two equality filters isolate the
# national-total row of Table 1 (overnight stays) for every month. See
# data/README.md for why overnight stays and why the value is non-integer.
CHILE_SOURCE = {
    "subdir": "americas",
    "filename": "chile_ine_tourism_monthly.csv",
    "date_col": "ref_date",
    "value_col": "value",
    "filters": {
        "table_number": 1,
        "level": "national",
    },
    "country_code": "CL",
    "country_name": "Chile",
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
    # Object dtype so a later pd.concat() with Costa Rica's float PASSENGERS
    # column doesn't upcast every other country's clean int counts to float
    # (e.g. 716680 -> 716680.0) -- see score_latest_12_months for the same fix.
    out["PASSENGERS"] = out["PASSENGERS"].astype(object)
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
        value = row[value_col]
        # Most sources here are whole-number counts (visitors, entries,
        # movements) and get written as plain ints, matching the Eurostat
        # side's output. Costa Rica's occupancy_pct is a percentage with a
        # meaningful decimal (e.g. 36.7) -- int() would silently truncate
        # it, so only round non-integral values instead of flooring them.
        passengers_value = int(value) if float(value).is_integer() else round(float(value), 2)
        rows.append({
            "COUNTRY": country_code,
            "MONTH": int(month),
            "PEAK_RATIO": round(value / max_value, 4),
            "COUNTRY_NAME": country_name,
            "SOURCE_YEAR": int(year),
            "PASSENGERS": passengers_value,
        })

    out = pd.DataFrame(rows).sort_values("MONTH").reset_index(drop=True)
    # Object dtype so concatenating this with other sources' PASSENGERS
    # columns (some int, some float) doesn't upcast everything to float --
    # see the matching comment in build_peak_tourism_indicator.
    out["PASSENGERS"] = out["PASSENGERS"].astype(object)
    return out


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


def load_chile_source() -> pd.DataFrame | None:
    """Load Chile INE's EMAT export and apply CHILE_SOURCE's two equality
    filters to isolate the national monthly overnight-stays series (Table
    1). Returns None (with a warning printed) if the source file is
    missing, same graceful-skip behavior as load_canada_source()."""
    csv_path = PROCESSED_DIR / CHILE_SOURCE["subdir"] / CHILE_SOURCE["filename"]
    if not csv_path.exists():
        print(f"WARNING: {csv_path} not found -- skipping Chile. "
              f"Run scripts/americas/fetch_chile_ine_tourism_accommodation.py first.")
        return None

    print(f"Reading {csv_path}...")
    df = pd.read_csv(csv_path)

    missing_cols = set(CHILE_SOURCE["filters"]) - set(df.columns)
    if missing_cols:
        raise ValueError(f"{csv_path} is missing expected column(s) {missing_cols} -- is this really the EMAT export?")

    for col, expected_value in CHILE_SOURCE["filters"].items():
        df = df[df[col] == expected_value]

    if df.empty:
        raise ValueError(
            f"{csv_path}: filtering to {CHILE_SOURCE['filters']} left zero rows -- "
            f"check Table 1 / level='national' rows are still present (e.g. re-run "
            f"fetch_chile_ine_tourism_accommodation.py without --table pointed elsewhere)."
        )

    df[CHILE_SOURCE["date_col"]] = df[CHILE_SOURCE["date_col"]].astype(str)
    dupes = df[CHILE_SOURCE["date_col"]].duplicated()
    if dupes.any():
        raise ValueError(
            f"{csv_path}: {dupes.sum()} duplicate {CHILE_SOURCE['date_col']} value(s) after filtering -- "
            f"the filters in CHILE_SOURCE no longer isolate a single row per month."
        )

    return df


def build_extra_country_indicator(skip: bool = False) -> pd.DataFrame:
    """Build AU/NZ/Japan/Canada/Chile rows via the latest-12-months method
    (see EXTRA_COUNTRY_SOURCES, CANADA_SOURCE, and CHILE_SOURCE)."""
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

    chile_df = load_chile_source()
    if chile_df is not None:
        frames.append(score_latest_12_months(
            chile_df, CHILE_SOURCE["filename"], CHILE_SOURCE["date_col"], CHILE_SOURCE["value_col"],
            CHILE_SOURCE["country_code"], CHILE_SOURCE["country_name"],
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
        help="Score Eurostat countries only, skipping Australia/New Zealand/Japan/Costa Rica/Canada (old behavior).",
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
