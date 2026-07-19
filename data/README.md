# Data

## Layout

- `scripts/` — reusable Python scripts that pull and parse raw data. Move
  code here once it's stable; use `notebooks/` for exploration.
- `raw/` — untouched downloads, one subfolder per source (gitignored, since
  it's regenerable by re-running the scripts).
- `processed/` — cleaned, tidy CSVs derived from `raw/`, ready for scoring
  or analysis (gitignored — regenerate with the scripts).
- `reference/` — small, stable lookup files that other scripts depend on
  (country code/name mappings, API check-in caches). Tracked in git since
  they're cheap to store and useful to diff.

## Sources

### World Bank — GDP deflator (`NY.GDP.DEFL.KD.ZG`)

- **Script:** `scripts/fetch_worldbank_indicator.py`
- **API:** World Bank [Data360](https://data360api.worldbank.org) —
  `GET /data360/data?DATABASE_ID=WB_WDI&INDICATOR=WB_WDI_NY_GDP_DEFL_KD_ZG`
  (JSON, paginated 1000 rows/call via `skip`). WDI dotted codes map to
  Data360 indicator IDs as `WB_WDI_<code with . replaced by _>`.
- **What it is:** annual % change in the GDP deflator, by country/region and
  year. It's a broad measure of domestic price inflation (not
  tourist-specific prices), sourced from World Bank national accounts data.
- **Why it's here:** a candidate input for an "affordability" factor —
  countries/years with high inflation may signal rising costs for
  travelers. This is a rough proxy, not a direct measure of travel prices.
- **Output:**
  - `raw/worldbank/<code>/<code>.json` — full raw API response records.
  - `processed/worldbank_<code>.csv` — tidy columns `ref_area, indicator,
    time_period, obs_value, unit_measure, freq`. `ref_area` is a mix of
    ISO3 country codes and World Bank region aggregates (e.g. `ARB`,
    `AFE`) — join against `reference/worldbank_countries.json` to get
    names.
- **Run:**
  ```
  pip install -r requirements.txt
  python scripts/fetch_worldbank_indicator.py NY.GDP.DEFL.KD.ZG
  ```
- The script accepts any WDI indicator code, so it can be reused for future
  indicators (e.g. exchange rates, tourism arrivals) by passing a different
  code.
- **Note:** this sandbox's network allowlist blocks `data360api.worldbank.org`,
  so the script can't be run to completion in this environment — it was
  verified with a live sample of the API response (via a separate fetch
  tool) and an offline unit check of the pagination/CSV logic. It should
  run normally on your own machine or in CI.

### `reference/worldbank_countries.json`

Country/region code → name lookup (265 entries: ISO3 countries plus World
Bank aggregates like `WLD`, `ARB`, income-level groups, etc.), extracted
from a World Bank bulk-download XML (`Country or Area` fields). One-time
extraction, not something to be regenerated per run.

### `reference/latest_year_cache.json` — "is there new data yet?" cache

- **Script:** `scripts/latest_year_cache.py`
- **What it does:** checks the latest year available for a WDI indicator
  via `GET /data360/data?...&REF_AREA=USA&isLatestData=true` (USA used as
  a reliable proxy country), and caches the result so we don't hit the API
  needlessly — annual indicators only update once a year, often with a lag.
- **Check schedule** (`get_latest_year()` in the script):
  - If the cached year is 0–1 years behind the current year (the normal
    state — e.g. cached year 2025 anytime in 2026), skip the check
    entirely.
  - Once the cached year is 2+ years behind (e.g. cached year 2025 once
    it's 2027), re-check, but at most every 30 days.
  - Example: cached `latest_year=2025` — no checks at all through 2026;
    first re-check on 2027-01-01, next on 2027-01-31, etc. until a newer
    year shows up.
- **Run:**
  ```
  python scripts/latest_year_cache.py NY.GDP.DEFL.KD.ZG
  python scripts/latest_year_cache.py NY.GDP.DEFL.KD.ZG --force   # bypass schedule
  ```
- Cache seeded with `NY.GDP.DEFL.KD.ZG: 2025` (confirmed live 2026-07-19,
  since this sandbox can't reach the API directly — see note above).

### `scripts/fetch_latest_by_country.py` — indicator value per country, latest year

- **What it does:** for a WDI indicator, looks up the latest available year
  via `latest_year_cache.get_latest_year()`, then fetches that indicator for
  every country/region in `reference/worldbank_countries.json` in one
  pass (`GET /data360/data?...&TIME_PERIOD=<year>`, paginated) and writes a
  single JSON keyed by country code.
- **Output:** `processed/worldbank_<code>_<year>_by_country.json`:
  ```json
  {
    "indicator": "NY.GDP.DEFL.KD.ZG",
    "year": 2025,
    "generated": "2026-07-19",
    "countries_total": 265,
    "countries_with_data": 232,
    "countries_missing_data": 33,
    "missing_codes": ["ABW", "AFG", ...],
    "data": {
      "ARG": {"country_name": "Argentina", "value": 39.088894},
      "USA": {"country_name": "United States", "value": 2.801236},
      ...
    }
  }
  ```
  Countries/regions without a value for that year (smaller territories,
  sanctioned/conflict states, reporting lag) are listed in `missing_codes`
  rather than silently dropped or backfilled with an old year.
- **Run:**
  ```
  python scripts/fetch_latest_by_country.py NY.GDP.DEFL.KD.ZG
  ```
- **Already generated:** `processed/worldbank_NY.GDP.DEFL.KD.ZG_2025_by_country.json`
  (232/265 countries, built 2026-07-19 from a live pull of the API — same
  sandbox network caveat as above, so it was assembled via a separate fetch
  tool rather than running the script directly here, then verified by
  passing the real records through the script's own merge/lookup functions).
