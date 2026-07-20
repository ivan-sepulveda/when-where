"""
Fetch a Eurostat dataset via the Eurostat Statistics API and flatten it
into a tidy CSV.

Eurostat's REST API returns JSON-stat: a flat `value` dict keyed by a
stringified integer index, plus a `dimension` object describing each
dimension's category codes/labels and a `size` array giving each
dimension's cardinality. The index encodes a position in every dimension
at once (row-major / C order: the *last* dimension listed in `id` varies
fastest) -- e.g. for TTR00012 (dims `[..., geo, time]`, sizes
`[..., 42, 12]`), the value for (AT, 2025) sits at
`23 * 12 + 11 = 287` (AT is geo position 23, 2025 is time position 11).
This script decodes that back into one row per (dimension combo, value)
with both the raw category code and its human-readable label for every
dimension.

Two time-filter styles, because Eurostat's `time` category codes differ
by frequency:
  - Annual datasets (e.g. TTR00012) use plain-year codes ("2025") --
    filter these with `--time`, an exact-match list against those codes.
  - Monthly/quarterly datasets (e.g. TTR00016, "YYYY-MM" codes like
    "2025-02") don't have one code per bare year, so `--time 2025` won't
    match anything -- use `--start-period`/`--end-period` instead (the
    SDMX range filter), e.g. `--start-period 2025-01 --end-period 2025-12`.
`--filter DIM=VALUE` (repeatable) pins down any other dimension, e.g.
TTR00016 has a `tra_cov` (transport coverage) axis that TTR00012 doesn't
-- `--filter tra_cov=TOTAL` collapses it to "Total transport" so the
output matches TTR00012's scope instead of also breaking out national
vs. international.

Default dataset here is TTR00012 -- "Air transport of passengers by
country (yearly data)" (despite the "ttr" prefix, this is NOT a tourism
dataset; it's air passenger traffic, sourced from AVIA_PAOC). TTR00016 is
its monthly sibling, "Air transport of passengers by country and type of
transport (monthly data)" -- same underlying AVIA_PAOC source, finer time
grain, plus the extra `tra_cov` dimension noted above. As of this
writing TTR00016 only has data from 2025-02 through 2026-05 (it's a
newer series with a shorter history than TTR00012).

Usage:
    python fetch_eurostat_dataset.py                                    # TTR00012, year 2025 (defaults)
    python fetch_eurostat_dataset.py TTR00012 --time 2025
    python fetch_eurostat_dataset.py TTR00012 --time 2023 2024 2025
    python fetch_eurostat_dataset.py TTR00012 --time                    # no values -> all years
    python fetch_eurostat_dataset.py TTR00016 --start-period 2025-01 --end-period 2025-12 --filter tra_cov=TOTAL

API docs: https://wikis.ec.europa.eu/display/EUROSTATHELP/API+-+Getting+started
"""

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

DEFAULT_DATASET_ID = "TTR00012"
DEFAULT_TIME = ["2025"]  # only applied when dataset_id == DEFAULT_DATASET_ID and no time/period flag is given at all

# Eurostat's dataset ids (TTR00012, AVIA_PAOC, etc.) aren't self-explanatory
# -- this maps a dataset id to a human-readable slug used for the output
# filename instead. Add an entry here as new datasets get pulled in;
# anything not listed just falls back to the lowercased dataset id.
OUTPUT_NAME_OVERRIDES = {
    "TTR00012": "passengers_transported_by_country",
    "TTR00016": "passengers_transported_by_country_monthly",
}

# Friendly filename labels for --filter values that are cryptic Eurostat
# codes -- used ONLY in the output filename (the API query itself still
# uses the raw code from --filter as typed). Keyed by (dim, raw value).
# Anything not listed here just uses the raw value as-is in the filename.
FILTER_VALUE_LABELS = {
    ("tra_cov", "INTL_IEU27_2020"): "INTRA_EU",
    ("tra_cov", "INTL_XEU27_2020"): "EXTRA_EU",
}

# ---------------------------------------------------------------------------

BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
RAW_DIR = Path(__file__).resolve().parent.parent / "raw" / "eurostat"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"


def fetch_jsonstat(
    dataset_id: str,
    time: list[str] | None = None,
    start_period: str | None = None,
    end_period: str | None = None,
    filters: dict[str, str] | None = None,
) -> dict:
    """
    Hit the Eurostat Statistics API for one dataset.

    `time` is an exact-match filter against the `time` dimension's raw
    category codes -- fine for annual datasets ("2025"), but won't match
    anything on a monthly/quarterly dataset ("2025-02", "2025-Q1", ...).
    Use `start_period`/`end_period` (SDMX range filter) for those instead.
    `filters` passes through arbitrary dimension=value constraints, e.g.
    `{"tra_cov": "TOTAL"}`.
    """
    params = {"format": "JSON", "lang": "EN"}
    if time:
        # requests repeats a list-valued param as ?time=2024&time=2025, which
        # is exactly the multi-value filter syntax this API expects.
        params["time"] = time
    if start_period:
        params["startPeriod"] = start_period
    if end_period:
        params["endPeriod"] = end_period
    if filters:
        params.update(filters)

    resp = requests.get(f"{BASE_URL}/{dataset_id.lower()}", params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "value" not in payload or "dimension" not in payload:
        raise ValueError(
            f"Unexpected response for {dataset_id!r} -- no 'value'/'dimension' keys. "
            f"Check the dataset id is correct (case-insensitive, e.g. 'TTR00012')."
        )
    if not payload["value"]:
        raise ValueError(
            f"{dataset_id!r} returned zero observations for this filter combination. "
            f"If this is a monthly/quarterly dataset, check you used --start-period/"
            f"--end-period rather than --time (whose exact-match codes are frequency-specific)."
        )
    return payload


def decode_jsonstat(payload: dict) -> pd.DataFrame:
    """
    JSON-stat -> tidy DataFrame: one row per observation, one column pair
    (`<dim>` code + `<dim>_label`) per dimension, plus `value`.
    Observations with no data (a position simply absent from `value`) are
    dropped, not filled -- Eurostat's series are frequently incomplete for
    the most recent period.
    """
    dim_ids = payload["id"]
    dims = payload["dimension"]

    # Ordered (code, label) pairs per dimension, ordered by the position
    # JSON-stat assigned them -- this order is what the flat index is
    # computed against, so it must match exactly.
    dim_categories = []
    for dim_id in dim_ids:
        cat = dims[dim_id]["category"]
        index_map = cat["index"]  # code -> position
        labels = cat.get("label", {})
        ordered_codes = [code for code, _ in sorted(index_map.items(), key=lambda kv: kv[1])]
        dim_categories.append([(code, labels.get(code, code)) for code in ordered_codes])

    rows = []
    # itertools.product with dims in `id` order makes the LAST dimension
    # vary fastest, matching JSON-stat's row-major flat-index convention.
    for flat_idx, combo in enumerate(itertools.product(*dim_categories)):
        raw_value = payload["value"].get(str(flat_idx))
        if raw_value is None:
            continue  # no observation at this position -- skip, don't fill
        row = {}
        for dim_id, (code, label) in zip(dim_ids, combo):
            row[dim_id] = code
            row[f"{dim_id}_label"] = label
        row["value"] = raw_value
        rows.append(row)

    if not rows:
        raise ValueError("Decoded zero observations -- check the API response wasn't empty/filtered to nothing.")

    df = pd.DataFrame(rows)
    # Column order: code/label pairs in dimension order, value last.
    ordered_cols = [c for dim_id in dim_ids for c in (dim_id, f"{dim_id}_label")] + ["value"]
    return df[ordered_cols]


def _output_suffix(
    time: list[str] | None,
    start_period: str | None,
    end_period: str | None,
    filters: dict[str, str] | None,
) -> str:
    """
    Build the filename suffix encoding whatever time/dimension filters were
    applied. Filter values use FILTER_VALUE_LABELS for a friendlier name
    where one's registered (e.g. tra_cov=INTL_IEU27_2020 -> "INTRA_EU")
    and drop the dimension name entirely -- just the value(s), since the
    raw dimension id (e.g. "tra_cov") isn't meaningful to anyone who
    hasn't read the script.
    """
    bits = []
    if time:
        bits.append("-".join(time))
    elif start_period or end_period:
        bits.append(f"{start_period or 'start'}_{end_period or 'end'}")
    if filters:
        labels = [FILTER_VALUE_LABELS.get((k, v), v) for k, v in sorted(filters.items())]
        bits.append("-".join(labels))
    return f"_{'_'.join(bits)}" if bits else ""


def save_raw_json(dataset_id: str, suffix: str, payload: dict) -> Path:
    out_dir = RAW_DIR / dataset_id.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{dataset_id.lower()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path


def write_csv(dataset_id: str, suffix: str, df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    slug = OUTPUT_NAME_OVERRIDES.get(dataset_id.upper(), dataset_id.lower())
    out_path = PROCESSED_DIR / f"eurostat_{slug}{suffix}.csv"
    df.to_csv(out_path, index=False)
    return out_path


def fetch_dataset(
    dataset_id: str,
    time: list[str] | None = None,
    start_period: str | None = None,
    end_period: str | None = None,
    filters: dict[str, str] | None = None,
) -> Path:
    bits = []
    if time:
        bits.append(f"time={','.join(time)}")
    if start_period or end_period:
        bits.append(f"period={start_period or '*'}..{end_period or '*'}")
    if filters:
        bits.append(",".join(f"{k}={v}" for k, v in filters.items()))
    label = f"{dataset_id} ({'; '.join(bits)})" if bits else dataset_id
    print(f"[{label}] fetching...")

    payload = fetch_jsonstat(dataset_id, time=time, start_period=start_period, end_period=end_period, filters=filters)
    suffix = _output_suffix(time, start_period, end_period, filters)
    save_raw_json(dataset_id, suffix, payload)

    df = decode_jsonstat(payload)
    out_path = write_csv(dataset_id, suffix, df)
    print(f"[{label}] wrote {len(df)} rows -> {out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "dataset_id",
        nargs="?",
        default=DEFAULT_DATASET_ID,
        help=f"Eurostat dataset id, e.g. TTR00012 (default: {DEFAULT_DATASET_ID})",
    )
    parser.add_argument(
        "--time",
        nargs="*",
        default=None,
        help="Exact-match year filter(s) against the time dimension's raw codes, e.g. "
        "--time 2025 -- only valid for annual datasets (frequency codes like '2025', "
        "not '2025-02'). Pass --time with no values to fetch all available periods. "
        f"If omitted entirely and dataset_id is {DEFAULT_DATASET_ID}, defaults to "
        f"--time {' '.join(DEFAULT_TIME)}.",
    )
    parser.add_argument(
        "--start-period",
        default=None,
        help="SDMX range filter start, for monthly/quarterly datasets -- e.g. 2025-01.",
    )
    parser.add_argument(
        "--end-period",
        default=None,
        help="SDMX range filter end, for monthly/quarterly datasets -- e.g. 2025-12.",
    )
    parser.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        metavar="DIM=VALUE",
        help="Extra dimension filter, repeatable -- e.g. --filter tra_cov=TOTAL. "
        "Check the dataset's `dimension` object (in the raw JSON, or via the API) "
        "for available dimension ids/codes.",
    )
    args = parser.parse_args()

    if args.time is not None:
        time = args.time or None  # --time with no values -> explicitly no filter
    elif args.start_period is None and args.end_period is None and args.dataset_id.upper() == DEFAULT_DATASET_ID:
        time = DEFAULT_TIME
    else:
        time = None

    filters = {}
    for raw in args.filters:
        if "=" not in raw:
            parser.error(f"--filter must be DIM=VALUE, got {raw!r}")
        k, v = raw.split("=", 1)
        filters[k] = v

    fetch_dataset(
        args.dataset_id,
        time=time,
        start_period=args.start_period,
        end_period=args.end_period,
        filters=filters or None,
    )


if __name__ == "__main__":
    main()
