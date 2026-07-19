# Data

## Layout

- `scripts/` — reusable Python scripts that pull and parse raw data. Move
  code here once it's stable; use `notebooks/` for exploration.
- `raw/` — untouched downloads, one subfolder per source (gitignored, since
  it's regenerable by re-running the scripts).
- `processed/` — cleaned, tidy CSVs derived from `raw/`, ready for scoring
  or analysis (gitignored — regenerate with the scripts).

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
    `AFE`); it isn't joined to country names yet — that mapping is a
    separate future step.
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
