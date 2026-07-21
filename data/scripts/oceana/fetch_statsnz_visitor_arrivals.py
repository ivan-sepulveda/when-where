"""
Fetch Stats NZ's monthly "International travel" release and extract
Table 1 ("Monthly visitor arrivals") into a tidy monthly CSV -- the same
role the ABS/e-Stat/StatCan scripts elsewhere in data/scripts/ play for
Australia, Japan, and Canada: a national-level monthly "how much inbound
travel is happening" volume signal, this time for New Zealand.

**Source file**, reissued monthly at a predictable URL keyed by release
month, e.g. for the May 2026 issue:

    https://www.stats.govt.nz/assets/Uploads/International-travel/
    International-travel-<Month>-<YYYY>/Download-data/
    international-visitor-arrivals-to-new-zealand-<month>-<yyyy>.xlsx

`build_url_for_release()` constructs this from a (year, month) pair so the
script can be pointed at any past release without hardcoding one URL, but
the default is the URL for the May 2026 release (the one this script was
built and verified against).

**The spreadsheet's layout** (confirmed against a real copy of
international-visitor-arrivals-to-new-zealand-may-2026.xlsx, supplied
directly by the user -- not fetched by this tool, since this sandbox's
network allowlist blocks stats.govt.nz for outbound requests, same
restriction noted in fetch_abs_visitor_arrivals.py; confirmed via direct
curl, proxy 403 "blocked-by-allowlist"). The workbook has one sheet per
table plus cover/notes sheets. Tables 1 and 2 share a single sheet,
`'Tables 1&2'`, laid out as a small "report" block rather than a plain
data grid:

    row w/ col A == "Table 1"        (title)
    next row: "Monthly visitor arrivals"
    next row ("header row"): col A = "Month", one col holds
        "Change 2024/25" (first half of a merged "Change 2024/25 to
        2025/26" header -- the two fiscal years in this label always
        being the two most recent in the table, i.e. it updates every
        release)
    next row ("fiscal-year row"): col A blank, cols B.. = five fiscal-year
        labels "2021/22".."2025/26" (format YYYY/YY, meaning "year ended
        31 May YYYY+1"), then "to 2025/26" (second half of the merged
        header above)
    next row ("subheader row"): col A blank, the change column pair
        labelled "Number" / "Percent"
    next row: blank spacer row
    next 12 rows: one per month, col A = 3-letter month abbreviation
        starting at "Jun" and ending at "May" (NZ's tourism year runs
        Jun-May), cols B-F = visitor arrival counts for that month in
        each of the five fiscal years, cols G-H = YoY change (number,
        percent) versus the prior fiscal year, for that month only
    next row: "Source: Stats NZ" (footer -- parsing stops here)
    (Table 2 continues below in the same sheet)

`find_table1_header_rows()` locates the header/fiscal-year/subheader rows
by scanning column A for "Month" rather than hardcoding row numbers, since
Stats NZ has added/removed rows across releases before.

**Turning the fiscal-year x month grid into real calendar months.** Each
fiscal-year column "YYYY/(YY+1)" spans Jun YYYY - May (YYYY+1). So a cell
in the "Jun" row under column "2021/22" is June 2021, while a cell in the
"May" row under the same column is May 2022. `month_to_ref_date()` encodes
that split (Jun-Dec -> the column's first calendar year, Jan-May -> the
column's second calendar year) to produce a proper "YYYY-MM" ref_date per
cell, so the output is a real, ordered monthly time series (Jun 2021 ->
May 2026 in the May-2026 release) rather than a month-name/fiscal-year
cross-tab.

**YoY change columns** (cols G-H) describe the change into whichever
fiscal year is most recent in that release (2024/25 -> 2025/26 as of
May 2026) -- not a per-fiscal-year figure. They're attached only to the
rows for that most-recent fiscal year (`change_number_yoy` /
`change_percent_yoy`, NaN elsewhere) rather than duplicated across every
fiscal year, since they're only ever computed for the newest one.

Usage:
    python fetch_statsnz_visitor_arrivals.py                         # default: May 2026 release
    python fetch_statsnz_visitor_arrivals.py --release-year 2026 --release-month 5
    python fetch_statsnz_visitor_arrivals.py --url "https://.../some-other-release.xlsx"
    python fetch_statsnz_visitor_arrivals.py --force-download        # bypass the cached raw/ xlsx

Source: https://www.stats.govt.nz/information-releases/international-travel-may-2026/

Note on verification: `build_url_for_release()` is unverified end-to-end
in this sandbox (stats.govt.nz is proxy-blocked here, confirmed via direct
curl -> 403 "blocked-by-allowlist", the same restriction documented in
fetch_abs_visitor_arrivals.py). `find_table1_header_rows()` and
`parse_table1()` WERE verified for real against the actual May-2026
workbook the user supplied -- not a synthetic fixture -- confirming the
row layout, the 5 fiscal-year columns, the 12-month Jun-May block, and the
"Source: Stats NZ" footer row. Run this on a machine that can reach
stats.govt.nz to confirm `download_xlsx()` end-to-end.
"""

import argparse
import re
from pathlib import Path

import openpyxl
import pandas as pd
import requests

RAW_DIR = Path(__file__).resolve().parent.parent.parent / "raw" / "statsnz_visitor_arrivals"
PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "oceana"
OUTPUT_FILENAME = "statsnz_visitor_arrivals_monthly.csv"

SHEET_NAME = "Tables 1&2"
TABLE_TITLE = "Table 1"
FOOTER_TEXT = "Source: Stats NZ"

# Month abbreviation (as it appears in col A) -> (calendar month number,
# which half of the "YYYY/YY" fiscal-year label it belongs to).
# NZ's tourism year runs Jun -> May: Jun-Dec fall in the fiscal label's
# first calendar year, Jan-May fall in its second.
MONTH_ORDER = [
    ("Jun", 6, "first"), ("Jul", 7, "first"), ("Aug", 8, "first"),
    ("Sep", 9, "first"), ("Oct", 10, "first"), ("Nov", 11, "first"),
    ("Dec", 12, "first"),
    ("Jan", 1, "second"), ("Feb", 2, "second"), ("Mar", 3, "second"),
    ("Apr", 4, "second"), ("May", 5, "second"),
]
MONTH_TO_INFO = {name: (num, half) for name, num, half in MONTH_ORDER}

FISCAL_YEAR_RE = re.compile(r"^(\d{4})/(\d{2})$")

DEFAULT_RELEASE_YEAR = 2026
DEFAULT_RELEASE_MONTH = 5  # May


def build_url_for_release(year: int, month: int) -> str:
    """Construct the Stats NZ download URL for a given release (year, month).
    Verified by pattern-matching against the real May-2026 URL the user
    supplied; not yet confirmed for other months/years since stats.govt.nz
    is unreachable from this sandbox (see module docstring)."""
    month_name = pd.Timestamp(year=year, month=month, day=1).strftime("%B")
    month_slug = month_name.lower()
    return (
        "https://www.stats.govt.nz/assets/Uploads/International-travel/"
        f"International-travel-{month_name}-{year}/Download-data/"
        f"international-visitor-arrivals-to-new-zealand-{month_slug}-{year}.xlsx"
    )


def download_xlsx(url: str, force: bool = False) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1]
    xlsx_path = RAW_DIR / filename

    if force or not xlsx_path.exists():
        print(f"[stats.govt.nz] downloading {url} ...")
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        xlsx_path.write_bytes(resp.content)
    else:
        print(f"[stats.govt.nz] using cached {xlsx_path} (--force-download to bypass)")

    return xlsx_path


def find_table1_header_rows(ws, max_scan: int = 40) -> dict[str, int]:
    """Scan column A for 'Table 1' then, below it, 'Month' -- the header
    row that anchors the fiscal-year row and subheader row beneath it.
    Row numbers aren't hardcoded since Stats NZ has reshuffled rows
    (notes, blank spacers) across past releases."""
    table1_row = None
    for r in range(1, max_scan + 1):
        val = ws.cell(row=r, column=1).value
        if isinstance(val, str) and val.strip() == TABLE_TITLE:
            table1_row = r
            break
    if table1_row is None:
        raise ValueError(f"Could not find '{TABLE_TITLE}' in column A of sheet '{SHEET_NAME}'.")

    month_header_row = None
    for r in range(table1_row + 1, table1_row + 10):
        val = ws.cell(row=r, column=1).value
        if isinstance(val, str) and val.strip() == "Month":
            month_header_row = r
            break
    if month_header_row is None:
        raise ValueError(f"Could not find 'Month' header row below row {table1_row}.")

    fiscal_year_row = month_header_row + 1
    subheader_row = month_header_row + 2

    # Data doesn't necessarily start immediately after the subheader row --
    # the real file has a blank spacer row in between -- so scan forward
    # for the first row whose column A is a recognized month abbreviation
    # rather than assuming a fixed offset.
    data_start_row = None
    for r in range(subheader_row + 1, subheader_row + 6):
        val = ws.cell(row=r, column=1).value
        if isinstance(val, str) and val.strip() in MONTH_TO_INFO:
            data_start_row = r
            break
    if data_start_row is None:
        raise ValueError(f"Could not find first month data row below row {subheader_row}.")

    return {
        "table1_row": table1_row,
        "month_header_row": month_header_row,
        "fiscal_year_row": fiscal_year_row,
        "subheader_row": subheader_row,
        "data_start_row": data_start_row,
    }


def parse_table1(xlsx_path: Path) -> pd.DataFrame:
    """Read Table 1 (Monthly visitor arrivals) out of the 'Tables 1&2'
    sheet and return a tidy monthly DataFrame: one row per real calendar
    month, columns ref_date / fiscal_year / month / visitor_arrivals /
    change_number_yoy / change_percent_yoy."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        raise ValueError(f"Expected a '{SHEET_NAME}' sheet, found {wb.sheetnames!r}")
    ws = wb[SHEET_NAME]

    rows_meta = find_table1_header_rows(ws)
    fy_row = rows_meta["fiscal_year_row"]
    subheader_row = rows_meta["subheader_row"]
    data_start_row = rows_meta["data_start_row"]

    # Locate the fiscal-year columns (e.g. "2021/22" .. "2025/26"), in
    # left-to-right / chronological order.
    fy_cols: dict[int, str] = {}
    for c in range(2, ws.max_column + 1):
        val = ws.cell(row=fy_row, column=c).value
        if isinstance(val, str) and FISCAL_YEAR_RE.match(val.strip()):
            fy_cols[c] = val.strip()
    if not fy_cols:
        raise ValueError(f"No fiscal-year columns (e.g. '2021/22') found in row {fy_row}.")

    most_recent_fy = fy_cols[max(fy_cols)]  # rightmost column = most recent

    # Locate the YoY change columns via the subheader row's "Number"/"Percent" labels.
    change_number_col = change_percent_col = None
    for c in range(max(fy_cols) + 1, ws.max_column + 1):
        val = ws.cell(row=subheader_row, column=c).value
        if val == "Number":
            change_number_col = c
        elif val == "Percent":
            change_percent_col = c
    if change_number_col is None or change_percent_col is None:
        raise ValueError(f"Could not find 'Number'/'Percent' change columns in row {subheader_row}.")

    records = []
    r = data_start_row
    while True:
        month_name = ws.cell(row=r, column=1).value
        if not isinstance(month_name, str) or month_name.strip() not in MONTH_TO_INFO:
            break  # hit the "Source: Stats NZ" footer (or ran out of expected months)
        month_name = month_name.strip()
        month_num, half = MONTH_TO_INFO[month_name]

        change_number = ws.cell(row=r, column=change_number_col).value
        change_percent = ws.cell(row=r, column=change_percent_col).value

        for c, fy_label in fy_cols.items():
            year_start, year_end_suffix = FISCAL_YEAR_RE.match(fy_label).groups()
            calendar_year = int(year_start) if half == "first" else int(year_start[:2] + year_end_suffix)
            ref_date = f"{calendar_year}-{month_num:02d}"

            is_most_recent_fy = fy_label == most_recent_fy
            records.append({
                "ref_date": ref_date,
                "fiscal_year": fy_label,
                "month": month_name,
                "visitor_arrivals": ws.cell(row=r, column=c).value,
                "change_number_yoy": change_number if is_most_recent_fy else None,
                "change_percent_yoy": change_percent if is_most_recent_fy else None,
            })
        r += 1

    if not records:
        raise ValueError("Parsed zero data rows -- check data_start_row / month labels in column A.")

    df = pd.DataFrame(records).sort_values("ref_date").reset_index(drop=True)
    return df


def filter_dates(df: pd.DataFrame, start_date: str | None, end_date: str | None) -> pd.DataFrame:
    out = df
    if start_date:
        out = out[out["ref_date"] >= start_date]
    if end_date:
        out = out[out["ref_date"] <= end_date]
    return out


def write_output(df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / OUTPUT_FILENAME
    df.to_csv(out_path, index=False)
    return out_path


def fetch_dataset(
    url: str | None = None,
    release_year: int = DEFAULT_RELEASE_YEAR,
    release_month: int = DEFAULT_RELEASE_MONTH,
    start_date: str | None = None,
    end_date: str | None = None,
    force_download: bool = False,
) -> Path:
    resolved_url = url or build_url_for_release(release_year, release_month)
    xlsx_path = download_xlsx(resolved_url, force=force_download)

    print(f"[stats.govt.nz] reading {xlsx_path} ...")
    df = parse_table1(xlsx_path)
    df = filter_dates(df, start_date, end_date)

    out_path = write_output(df)
    print(f"[stats.govt.nz] wrote {len(df)} rows -> {out_path}")
    print("[stats.govt.nz] primary column: 'visitor_arrivals' (Table 1, Monthly visitor arrivals)")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=None, help="Exact xlsx URL to fetch. Overrides --release-year/--release-month.")
    parser.add_argument("--release-year", type=int, default=DEFAULT_RELEASE_YEAR, help=f"Release year, default {DEFAULT_RELEASE_YEAR}.")
    parser.add_argument("--release-month", type=int, default=DEFAULT_RELEASE_MONTH, help=f"Release month (1-12), default {DEFAULT_RELEASE_MONTH} (May).")
    parser.add_argument("--start-date", default=None, help="ref_date lower bound, 'YYYY-MM'.")
    parser.add_argument("--end-date", default=None, help="ref_date upper bound, 'YYYY-MM'.")
    parser.add_argument("--force-download", action="store_true", help="Bypass the cached raw/ xlsx.")
    args = parser.parse_args()

    fetch_dataset(
        url=args.url,
        release_year=args.release_year,
        release_month=args.release_month,
        start_date=args.start_date,
        end_date=args.end_date,
        force_download=args.force_download,
    )


if __name__ == "__main__":
    main()
