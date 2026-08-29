"""Pull beaches out of the GeoNames gazetteer into a flat CSV.

Source: data/globalshorelines/geonames.csv -- the GeoNames worldwide dump
(11,061,987 rows, ~1.5GB, 19 comma-separated columns WITH a header row).

Feature codes BCH ("beach") and BCHS ("beaches"). Both, deliberately: BCHS
is only 39 rows worldwide, but taking BCH alone silently drops them.

WHY THIS PARSES RATHER THAN GREPS. `grep -cE ',(BCH|BCHS),'` returns 13,257
against this file; the real count is 12,984. The extra 273 are rows where
that string appears in a name or alternatename field, not in column 7. A
full csv.reader pass over all 11M rows costs about 7 seconds, so there is no
reason to accept the looser answer.

OCEAN ONLY. GeoNames BCH does not mean "sea beach" -- it covers lake and
river beaches too. Unfiltered, this file put Chicago 20.7km from a "shore"
(Lake Michigan), Salt Lake City 17.7km (Great Salt Lake), Atlanta 56km and
Nashville 6.9km, none of which are near an ocean. So every beach is tested
against a 1km land/ocean mask (global_land_mask, GLOBE elevation derived)
and kept only if there is real ocean within OCEAN_SEARCH_KM. That mask
treats the Great Lakes, the Great Salt Lake and the Caspian as land, which
is exactly the distinction needed here.
"""

import csv
import math
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent.parent
SOURCE = DATA_DIR / "globalshorelines" / "geonames.csv"
OUT_CSV = DATA_DIR / "processed" / "multiple" / "geonames_beaches.csv"

BEACH_CODES = ("BCH", "BCHS")
OUT_COLUMNS = ["name", "lat", "lon", "country_code", "feature_code"]

# A beach point sits ON the shore, so the mask cell under it is usually land.
# Ocean is looked for on a ring around it instead. 5km is generous against a
# ~0.93km mask: it tolerates a coordinate placed slightly inland without
# reaching across anything. It cannot produce a false positive on a lake --
# inland water is land to this mask, so there is no ocean to find.
OCEAN_SEARCH_KM = 5.0
OCEAN_RING_POINTS = 12


def ocean_nearby(lats, lons):
    """Bool per input point: is there ocean within OCEAN_SEARCH_KM?"""
    from global_land_mask import globe

    found = globe.is_ocean(lats, lons)
    for bearing in np.linspace(0, 2 * math.pi, OCEAN_RING_POINTS, endpoint=False):
        # Flat-earth offset is fine at 5km; the error is metres.
        dlat = (OCEAN_SEARCH_KM / 111.32) * math.cos(bearing)
        dlon = (OCEAN_SEARCH_KM / 111.32) * math.sin(bearing) / np.maximum(
            np.cos(np.radians(lats)), 1e-6)
        probe_lat = np.clip(lats + dlat, -90, 90)
        probe_lon = ((lons + dlon + 180) % 360) - 180
        found = found | globe.is_ocean(probe_lat, probe_lon)
    return found


def extract():
    # Some alternatename fields are enormous; the default limit rejects them.
    csv.field_size_limit(10**9)

    rows, skipped = [], 0
    with open(SOURCE, encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        idx = {name: header.index(name) for name in
               ("name", "latitude", "longitude", "feature code", "country code")}

        for row in reader:
            if len(row) <= idx["feature code"] or row[idx["feature code"]] not in BEACH_CODES:
                continue
            try:
                lat = float(row[idx["latitude"]])
                lon = float(row[idx["longitude"]])
            except (TypeError, ValueError):
                skipped += 1
                continue
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                skipped += 1
                continue
            rows.append([row[idx["name"]], lat, lon,
                         row[idx["country code"]], row[idx["feature code"]]])

    lats = np.array([r[1] for r in rows])
    lons = np.array([r[2] for r in rows])
    keep = ocean_nearby(lats, lons)
    inland = len(rows) - int(keep.sum())
    rows = [[r[0], f"{r[1]:.6f}", f"{r[2]:.6f}", r[3], r[4]]
            for r, k in zip(rows, keep) if k]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(OUT_COLUMNS)
        writer.writerows(rows)
    return rows, skipped, inland


def main():
    rows, skipped, inland = extract()
    print(f"Wrote {len(rows)} ocean beaches -> {OUT_CSV}")
    print(f"  dropped {inland} lake/river beaches with no ocean within {OCEAN_SEARCH_KM}km")
    if skipped:
        print(f"  skipped {skipped} row(s) with unparseable or out-of-range coordinates")
    import collections
    codes = collections.Counter(r[4] for r in rows)
    print(f"  by feature code: {dict(codes)}")
    countries = collections.Counter(r[3] for r in rows)
    print(f"  countries covered: {len(countries)}")
    print(f"  top: {', '.join(f'{c}={n}' for c, n in countries.most_common(8))}")
    lats = [float(r[1]) for r in rows]
    print(f"  lat {min(lats):.4f} .. {max(lats):.4f}")


if __name__ == "__main__":
    main()
