"""
Derives data/processed/multiple/unesco_by_country.json from the already-reduced
data/processed/multiple/unesco_world_heritage_sites.json (built by
fetch_unesco_world_heritage_sites.py -- run that first).

Regroups the flat site list into { iso2_code: [sites] }, using the
2-letter codes already present in each site's `iso_codes` field (comma-
separated for transboundary sites, e.g. "FR, BE") rather than re-deriving
country codes from `states_names` text -- the source already provides
ISO alpha-2 directly, so there's no name-matching/aliasing step needed
here (unlike, say, `country_aliases.json`, which exists for sources that
*don't* give a clean code).

A transboundary site (spans multiple countries -- ~4% of the list, e.g.
the Primeval Beech Forests site spanning 18 countries) appears once
under EACH of its countries, not just the first -- see `transboundary`
on each site record to tell these apart from single-country ones. A
handful of sites have no iso_codes at all in the source (e.g. Old City
of Jerusalem, whose sovereignty is disputed and which UNESCO lists
without a country code) -- these are collected separately under
`unassigned_sites` in the output rather than silently dropped or forced
into a country they weren't actually assigned to.

Usage:
    python build_unesco_sites_by_country.py
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config -- the only section you should need to edit.
# ---------------------------------------------------------------------------

PROCESSED_DIR = Path(__file__).resolve().parent.parent.parent / "processed" / "multiple"
INPUT_PATH = PROCESSED_DIR / "unesco_world_heritage_sites.json"
OUTPUT_PATH = PROCESSED_DIR / "unesco_by_country.json"

# ---------------------------------------------------------------------------


def load_sites(input_path: Path) -> list[dict]:
    if not input_path.exists():
        raise FileNotFoundError(
            f"{input_path} not found -- run fetch_unesco_world_heritage_sites.py first."
        )
    with open(input_path, "r", encoding="utf-8") as f:
        return json.load(f)["sites"]


def site_summary(site: dict) -> dict:
    """The per-site record kept under each country -- everything from the
    input site except `states_names`/`iso_codes` themselves (redundant
    once grouped by country) and `region`/`region_code` (dropped here
    too -- a UNESCO admin region, e.g. "Arab States", isn't specific to
    any one of a transboundary site's several countries, and readers
    grouping by country almost certainly want their own country->region
    mapping rather than UNESCO's)."""
    return {k: v for k, v in site.items() if k not in ("states_names", "iso_codes", "region", "region_code")}


def group_by_country(sites: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    by_country: dict[str, list[dict]] = {}
    unassigned: list[dict] = []

    for site in sites:
        raw_codes = site.get("iso_codes")
        if not raw_codes:
            unassigned.append(
                {
                    "name_en": site.get("name_en"),
                    "states_names": site.get("states_names"),
                    "reason": "no iso_codes present for this site in the source data",
                }
            )
            continue
        codes = [c.strip() for c in str(raw_codes).split(",") if c.strip()]
        summary = site_summary(site)
        for code in codes:
            by_country.setdefault(code, []).append(summary)

    # Sort each country's sites by inscription year (oldest first; None sorts last), then name.
    for code, country_sites in by_country.items():
        country_sites.sort(key=lambda s: (s.get("date_inscribed") or "9999", s.get("name_en") or ""))

    return by_country, unassigned


def build_dataset(sites: list[dict]) -> dict:
    by_country, unassigned = group_by_country(sites)
    site_country_pairs = sum(len(v) for v in by_country.values())

    return {
        "source": "Derived from unesco_world_heritage_sites.json -- see that file's own `source`/`source_query_url`.",
        "generated": datetime.now(timezone.utc).date().isoformat(),
        "total_countries": len(by_country),
        "total_sites": len(sites),
        "total_site_country_pairs": site_country_pairs,
        "note": (
            "total_site_country_pairs > total_sites because transboundary sites "
            "(see the `transboundary` field on each site) are listed once under "
            "EVERY country they span, not just one."
        ),
        "unassigned_sites": unassigned,
        "sites_by_country": dict(sorted(by_country.items())),
    }


def write_output(dataset: dict) -> Path:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)
    return OUTPUT_PATH


def main():
    sites = load_sites(INPUT_PATH)
    dataset = build_dataset(sites)
    out_path = write_output(dataset)
    print(
        f"[unesco_by_country] {dataset['total_countries']} countries, "
        f"{dataset['total_sites']} sites ({dataset['total_site_country_pairs']} site-country pairs, "
        f"{len(dataset['unassigned_sites'])} unassigned) -> {out_path}"
    )


if __name__ == "__main__":
    main()
