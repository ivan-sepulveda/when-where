"""
Build data/processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv: for each
country and calendar month, how busy inbound travel is relative to that
country's own peak month -- a 0-1 "seasonality" ratio.

Two source families feed this, using two different methods (see below):

  - Europe: processed/europe/eurostat_passengers_transported_by_country_monthly_*.csv
    (air passengers transported; see scripts/europe/fetch_eurostat_dataset.py)
  - Australia, New Zealand, Japan, Costa Rica, Mexico (the
    "EXTRA_COUNTRY_SOURCES" countries): processed/oceana/abs_visitor_arrivals_monthly.csv,
    processed/oceana/statsnz_visitor_arrivals_monthly.csv,
    processed/asia/japan_tourism_indicators_by_month.csv,
    processed/americas/costa_rica_monthly_hotel_occupancy.csv, and
    processed/americas/mexico_international_passengers_monthly.csv
    (visitor arrivals / border entries / hotel occupancy / international
    air passengers -- NOT all the same kind of signal, see below; see
    scripts/oceana/fetch_abs_visitor_arrivals.py,
    scripts/oceana/fetch_statsnz_visitor_arrivals.py,
    scripts/asia/fetch_japan_tourism_indicators.py,
    scripts/americas/build_costa_rica_monthly_tourism_dataset.py, and
    scripts/americas/build_mexico_international_passengers_dataset.py --
    NOTE: an earlier version of this script used
    build_mexico_domestic_passengers_dataset.py's DOMESTIC passenger
    series instead, which was the wrong chart for consistency with every
    other country here (all international signals) -- corrected to the
    international series, see "Mexico specifically" below)
  - Canada: processed/americas/statcan_airport_movements.csv, filtered to
    GEO == "Canada", Airports == "Total, all airports", "Domestic and
    international itinerant movements" == "Transborder movements" (flight
    movements between Canada and the US only -- see below; see
    scripts/americas/fetch_statcan_airport_movements.py)
  - Chile: processed/americas/chile_ine_tourism_monthly.csv, filtered to
    table_number == 1, level == "national" (national-total overnight
    stays -- see below; see
    scripts/americas/fetch_chile_ine_tourism_accommodation.py)

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

**Method for AU / NZ / Japan / Costa Rica / Canada / Chile / Mexico, per
country -- LATEST 12 MONTHS ONLY:** Unlike the Eurostat side, the ABS
series runs back to 1976 and using its full history would score a month
against a decades-old peak that may no longer be representative (and
Stats NZ's Table 1 only carries 5 fiscal years, e-Stat's Dashboard pull
only 16 months, Costa Rica's transcribed table only 2018-2024, Mexico's
transcribed chart only calendar 2025, to begin with -- so "full history"
isn't comparable across these sources anyway). Instead, each source's own
most recent 12 monthly rows are used:

    latest_12 = df.sort_values(date_col).tail(12)   # most recent 12 rows
    MAX_VALUE = latest_12[value_col].max()
    PEAK_RATIO(month) = value(month) / MAX_VALUE

As of this writing the seven sources' processed CSVs run through 2026-05
(ABS), 2026-05 (Stats NZ), 2026-04 (e-Stat), 2024-12 (Costa Rica -- its
source table simply stops at 2024, see build_costa_rica_monthly_tourism_
dataset.py), 2026-04 (StatCan), 2026-05 (Chile INE), and 2025-12 (Mexico
AFAC -- its source chart simply stops at December 2025, see
build_mexico_domestic_passengers_dataset.py) respectively, so "latest 12
months" is Jun 2025 - May 2026 for AU/NZ/Chile, May 2025 - Apr 2026 for
Japan/Canada, all of calendar 2024 for Costa Rica, and all of calendar
2025 for Mexico -- one row per calendar month, no deduplication needed
since each source has exactly one observation per month once filtered
down (Canada's StatCan table and Chile's INE table both need filtering
first -- see below; Mexico's is already a clean single series, no
filtering needed). `SOURCE_YEAR` records the calendar year each month's
observation actually fell in (so e.g. for AU/NZ/Chile, MONTH=6 is
SOURCE_YEAR=2025 while MONTH=5 is SOURCE_YEAR=2026; Costa Rica and Mexico
are each SOURCE_YEAR=2024/2025 respectively for every month).

The value column, and the column holding the "YYYY-MM" date, differ by
source (see `EXTRA_COUNTRY_SOURCES`): ABS Table 1's `short_term_visitors_
arriving` (short-term overseas visitor arrivals -- the closest ABS column
to "how many tourists arrived this month"), Stats NZ Table 1's
`visitor_arrivals`, Japan's e-Stat Dashboard pull's `NUM_ENTRIES`
(foreign-national border entries -- see scripts/asia/fetch_japan_tourism_
indicators.py's docstring: this counts ALL foreign-national entries, not
filtered to tourism purpose, so it runs a bit higher than a true
visitor-arrivals count would, e.g. it includes work-visa holders), Costa
Rica's `occupancy_pct` (hotel occupancy percentage, Banco Central de
Costa Rica's Cuadro 3 -- see "Costa Rica specifically" below), StatCan
table 23-10-0304-01's `VALUE` column, filtered per `CANADA_SOURCE` below,
Chile INE's `value` column, filtered per `CHILE_SOURCE` below (see "Chile
specifically"), and Mexico AFAC's `passengers` column (see "Mexico
specifically" below). All land in the output's generic `PASSENGERS`
column for schema consistency with the Eurostat rows, even though none of
them are actually air-passenger counts (except Mexico's, which literally
is one -- just domestic rather than international, see below) -- these
are different proxies for "how much inbound travel is happening," not
directly comparable in magnitude across sources, only within a single
country's own row of PEAK_RATIO values.

**Costa Rica specifically** -- its value column, `occupancy_pct`, is a
hotel occupancy PERCENTAGE (bounded 0-100), not a visitor/arrivals count
like every other source here. That makes its PEAK_RATIO curve compress
differently: a swing from 36.7% to 83.5% occupancy (Costa Rica's actual
Sep-vs-Feb 2024 range) is only about a 2.3x ratio, whereas a count-based
country can easily swing 5-10x between its quietest and busiest month.
Costa Rica's PEAK_RATIO values are correct on their own terms, just not
apples-to-apples in *magnitude of swing* against the count-based
countries -- only the shape (which month peaks) is directly comparable.
Also unlike every other source in this script, `costa_rica_monthly_hotel_
occupancy.csv` has no live fetch behind it -- it's hand-transcribed from
a PDF Banco Central de Costa Rica doesn't appear to publish through any
API (see build_costa_rica_monthly_tourism_dataset.py's docstring).

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

**Chile specifically** -- `chile_ine_tourism_monthly.csv` (see
fetch_chile_ine_tourism_accommodation.py) is a tidy long-format export of
one INE EMAT survey table, not a pre-filtered single series, so
`CHILE_SOURCE`'s two equality filters (`table_number == 1`, `level ==
"national"`) narrow it down to the national-total row of Table 1
("Número de pernoctaciones..." -- overnight stays, all accommodation
types, both residents and foreign visitors) for every available month.
Overnight stays (person-nights), not arrivals, per this project's
overnight-stays-vs-arrivals conclusion (see the Yearbook-of-Tourism-
Statistics discussion this script followed from -- overnight stays is a
better proxy for how "full" a destination is than an arrivals/trip
count). The national-total value is a **survey-weighted estimate**
("factor de expansión" in INE's own terminology), so it's a
non-integer float even though it's a count of person-nights (e.g.
1342951.2845142009 for May 2026) -- `score_latest_12_months()` already
handles this the same way it handles Costa Rica's `occupancy_pct`:
non-integer values are rounded to 2 decimals rather than truncated with
`int()`.

**Mexico specifically** -- `mexico_international_passengers_monthly.csv`
(see build_mexico_international_passengers_dataset.py) is, like Costa
Rica's source, hand-transcribed rather than fetched: AFAC's (Agencia
Federal de Aviación Civil) Monthly Bulletin of Operational Statistics
publishes this data only as charts, not downloadable tables, so the 12
monthly 2025 values were read off two charts' own data-point labels --
"Scheduled International Operations, Mexican Airlines (millions)" (page
7) and "...Foreign Airlines (millions)" (page 9) -- summed per month
into the `passengers` column (cross-checked against a direct text
extraction of the source PDF, and against the user's own screenshots;
both matched, including an independent check that December 2025 sums to
5.90M). Its `passengers` column IS a genuine air-passenger count -- the
only EXTRA_COUNTRY_SOURCES entry where that's true -- and unlike the
domestic series this replaced, it's **international** (Mexican + foreign
airlines' international operations to/from Mexico), matching the
"international signal" every other country in this table uses, though
it's still an air-passenger COUNT rather than a visitor-arrivals count
(closer in kind to Canada's Transborder-movements series or the Eurostat
rows than to ABS/Stats NZ's visitor arrivals or Chile's overnight
stays). The value is also only precise to about +/-10,000 passengers
(both source charts carry 2 decimal places in millions, and the two
sources' rounding errors compound when summed), unlike sources with an
exact reported count.

**Correction note:** an earlier version of this script used
`mexico_domestic_passengers_monthly.csv` (SCHEDULED DOMESTIC Operations,
page 3 of the same bulletin) instead -- domestic Mexican air travel, not
international, and the only EXTRA_COUNTRY_SOURCES entry that would have
been scored on a different kind of signal (domestic vs. every other
country's international one) than everything else in this table.
Corrected to the international series above; the domestic script and its
output CSV are left in place (still real, possibly useful data) but are
no longer read by this script.

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
    # series -- see module docstring's "Mexico specifically" / correction
    # note for why domestic would've been the wrong signal here.
    ("americas", "mexico_international_passengers_monthly.csv", "ref_date", "passengers", "MX", "Mexico"),
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

# Chile: like CANADA_SOURCE, the source CSV (INE's EMAT survey export) isn't
# a pre-filtered single series -- it's a tidy long-format table covering all
# 33 EMAT tables at once (or however many were fetched). These two equality
# filters isolate the national-total row of Table 1 (overnight stays, all
# accommodation types) for every month. See module docstring's "Chile
# specifically" section for why overnight stays and why the value is a
# non-integer survey-weighted estimate.
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
