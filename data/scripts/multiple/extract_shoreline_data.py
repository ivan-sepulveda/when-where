"""Pull shoreline coordinates from every source into one flat CSV.

Sources, both under data/globalshorelines/:
  * Shoreline_data_2D_2000_2013.nc -- a coastal-change study's transect grid
    (HDF5/netCDF4, needs h5py). Global-ish, but with hard gaps: nothing above
    60N, nothing below 54S, and nothing in Hawaii.
  * Shoreline_Public_Access.csv -- Oahu public shoreline access points.
  * ../processed/multiple/geonames_beaches.csv -- 12,984 GeoNames beaches
    (BCH/BCHS), built by extract_geonames_beaches.py. This is the source that
    reaches past 60N and onto islands the other two miss.

Output is two columns, lat/lon, deduplicated. Provenance lives here rather
than in a source column so the CSV stays trivially joinable.
"""

import csv
from pathlib import Path

import h5py
import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE_NC = DATA_DIR / "globalshorelines" / "Shoreline_data_2D_2000_2013.nc"
SOURCE_OAHU = DATA_DIR / "globalshorelines" / "Shoreline_Public_Access.csv"
SOURCE_BEACHES = DATA_DIR / "processed" / "multiple" / "geonames_beaches.csv"
OUT_CSV = DATA_DIR / "processed" / "multiple" / "shorelines.csv"


def from_netcdf():
    """The 100x100 transect grid. `lat` and `lon` are named correctly --
    checked against grid point [2,0] = (46.58, -124.02), the Washington
    coast; read the other way round it would be an impossible latitude.
    Cells with no transect are NaN in both arrays."""
    with h5py.File(SOURCE_NC, "r") as f:
        lat, lon = f["lat"][:], f["lon"][:]
    valid = np.isfinite(lat) & np.isfinite(lon)
    return np.column_stack([lat[valid], lon[valid]])


def from_oahu():
    """Oahu shoreline public access points. Every row is kept, including the
    single one whose shore_type is "River": it sits within a couple of km of
    the coast like the rest, and dropping rows on a descriptive field would
    be a judgement this file doesn't need to make."""
    if not SOURCE_OAHU.exists():
        return np.empty((0, 2))
    points = []
    # utf-8-sig: the file ships with a BOM, which otherwise lands in the
    # first column name and hides the X header.
    with open(SOURCE_OAHU, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (TypeError, ValueError):
                continue
            points.append([lat, lon])
    return np.array(points) if points else np.empty((0, 2))


def from_beaches():
    """GeoNames beaches. Optional: if extract_geonames_beaches.py hasn't been
    run in this checkout the file simply isn't there, and the other sources
    still produce a usable file."""
    if not SOURCE_BEACHES.exists():
        return np.empty((0, 2))
    points = []
    with open(SOURCE_BEACHES, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                points.append([float(row["lat"]), float(row["lon"])])
            except (TypeError, ValueError):
                continue
    return np.array(points) if points else np.empty((0, 2))


def extract():
    parts = {"netcdf transects": from_netcdf(),
             "oahu access points": from_oahu(),
             "geonames beaches": from_beaches()}
    combined = np.vstack([p for p in parts.values() if len(p)])

    if not (np.abs(combined[:, 0]) <= 90).all():
        raise SystemExit("latitude out of range -- lat/lon may be swapped")
    if not (np.abs(combined[:, 1]) <= 180).all():
        raise SystemExit("longitude out of range -- lat/lon may be swapped")

    rounded = np.round(combined, 6)
    _, first = np.unique(rounded, axis=0, return_index=True)
    deduped = rounded[np.sort(first)]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["lat", "lon"])
        for lat, lon in deduped:
            writer.writerow([f"{lat:.6f}", f"{lon:.6f}"])

    return parts, combined, deduped


def main():
    parts, combined, deduped = extract()
    print(f"Wrote {len(deduped)} points -> {OUT_CSV}")
    for name, pts in parts.items():
        print(f"  {name:22} {len(pts):>6}")
    print(f"  {'duplicates dropped':22} {len(combined) - len(deduped):>6}")
    print(f"  lat  {deduped[:, 0].min():.4f} .. {deduped[:, 0].max():.4f}")
    print(f"  lon  {deduped[:, 1].min():.4f} .. {deduped[:, 1].max():.4f}")


if __name__ == "__main__":
    main()
