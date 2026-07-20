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

Default dataset here is TTR00012 -- "Air transport of passengers by
country (yearly data)" (despite the "ttr" prefix, this is NOT a tourism
dataset; it's air passenger traffic, sourced from AVIA_PAOC). Most of its
dimensions (freq, unit, tra_meas, tra_cov, schedule) are fixed at a
single value for this particular dataset -- effectively it's just
geo x time -> passengers carried.

Usage:
    python fetch_eurostat_dataset.py                        # TTR00012, year 2025
    python fetch_eurostat_dataset.py TTR00012 --time 2025
    python fetch_eurostat_dataset.py TTR00012 --time 2023 2024 2025
    python fetch_eurostat_dataset.py TTR00012                # no --time -> all years

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
DEFAULT_TIME = ["2025"]

# Eurostat's dataset ids (TTR00012, AVIA_PAOC, etc.) aren't self-explanatory
# -- this maps a dataset id to a human-readable slug used for the output
# filename instead. Add an entry here as new datasets get pulled in;
# anything not listed just falls back to the lowercased dataset id.
OUTPUT_NAME_OVERRIDES = {
    "TTR00012": "passengers_transported_by_country",
}

# ---------------------------------------------------------------------------

BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
RAW_DIR = Path(__file__).resolve().parent.parent / "raw" / "eurostat"
PROCESSED_DIR = Path(__file__).resolve().parent.parent / "processed"


def fetch_jsonstat(dataset_id: str, time: list[str] | None = None) -> dict:
    """Hit the Eurostat Statistics API for one dataset, optionally filtered to specific `time` values."""
    params = {"format": "JSON", "lang": "EN"}
    if time:
        # requests repeats a list-valued param as ?time=2024&time=2025, which
        # is exactly the multi-value filter syntax this API expects.
        params["time"] = time

    resp = requests.get(f"{BASE_URL}/{dataset_id.lower()}", params=params, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if "value" not in payload or "dimension" not in payload:
        raise ValueError(
            f"Unexpected response for {dataset_id!r} -- no 'value'/'dimension' keys. "
            f"Check the dataset id is correct (case-insensitive, e.g. 'TTR00012')."
        )
    return payload


def decode_jsonstat(payload: dict) -> pd.DataFrame:
    """
    JSON-stat -> tidy DataFrame: one row per observation, one column pair
    (`<dim>` code + `<dim>_label`) per dimension, plus `value`.
    Observations with no data (a position simply absent from `value`) are
    dropped, not filled -- Eurostat's series are frequently incomplete for
    the most recent year.
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


def save_raw_json(dataset_id: str, time: list[str] | None, payload: dict) -> Path:
    out_dir = RAW_DIR / dataset_id.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{'-'.join(time)}" if time else ""
    out_path = out_dir / f"{dataset_id.lower()}{suffix}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path


def write_csv(dataset_id: str, time: list[str] | None, df: pd.DataFrame) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    slug = OUTPUT_NAME_OVERRIDES.get(dataset_id.upper(), dataset_id.lower())
    suffix = f"_{'-'.join(time)}" if time else ""
    out_path = PROCESSED_DIR / f"eurostat_{slug}{suffix}.csv"
    df.to_csv(out_path, index=False)
    return out_path


def fetch_dataset(dataset_id: str, time: list[str] | None = None) -> Path:
    label = f"{dataset_id} (time={','.join(time)})" if time else dataset_id
    print(f"[{label}] fetching...")

    payload = fetch_jsonstat(dataset_id, time=time)
    save_raw_json(dataset_id, time, payload)

    df = decode_jsonstat(payload)
    out_path = write_csv(dataset_id, time, df)
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
        nargs="+",
        default=DEFAULT_TIME,
        help=f"One or more year filters, e.g. --time 2025 (default: {DEFAULT_TIME}). "
        "Pass --time with no values to fetch all available years.",
    )
    args = parser.parse_args()

    fetch_dataset(args.dataset_id, time=args.time or None)


if __name__ == "__main__":
    main()
