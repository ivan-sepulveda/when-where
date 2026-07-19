# Data

## Setup

One venv for the whole project, at the repo root (not per-folder) — see
the top-level `README.md`. All commands below assume it's activated and
that you're running from `data/` (`cd data` from the repo root).

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

### World Bank — Exports of goods and services (`NE.EXP.GNFS.ZS`)

- **Script:** `scripts/fetch_worldbank_indicator.py` (same script, different code)
- **What it is:** exports of goods and services as % of GDP, by
  country/region and year — how export-oriented an economy is.
- **Why it's here:** a rougher, secondary proxy for economic
  openness/exposure to global trade; less directly tied to travel costs
  than the GDP deflator, kept alongside it as another candidate economic
  input.
- **Latest year available:** 2024 (not 2025 — this indicator reports with
  more lag than the GDP deflator, confirmed via `isLatestData=true`).
- **Run:**
  ```
  python scripts/fetch_worldbank_indicator.py NE.EXP.GNFS.ZS
  ```

### World Bank — PPP conversion factor, GDP (`PA.NUS.PPP`)

- **Script:** `scripts/fetch_worldbank_indicator.py` (same script, different code)
- **What it is:** local currency units per international dollar (units:
  LCU per international $), by country and year. USA = 1 by definition
  (the international $ is anchored to the US dollar).
- **Why it's here:** the core input for cost-of-living / affordability
  comparisons across countries — it's what lets you convert "how far does
  a dollar go" into a common unit. More directly useful for a travel
  affordability score than the GDP deflator or exports ratio.
- **Latest year available:** 2025.
- **Note:** unlike the other two indicators, this one has no World Bank
  region/income-group aggregates (`WLD`, `ARB`, `EAP`, etc. are absent) —
  PPP conversion factors are inherently country-specific, not something
  that aggregates across a region. 185/265 reference entries have a value;
  the rest are exactly the aggregate codes plus a handful of
  territories/sanctioned states without data.
- **Run:**
  ```
  python scripts/fetch_worldbank_indicator.py PA.NUS.PPP
  ```

### World Bank — Price level index, GDP (`PA.NUS.GDP.PLI`)

- **Script:** `scripts/fetch_worldbank_indicator.py` (same script, different code)
- **What it is:** PPP conversion factor divided by the market exchange rate,
  rebased so USA = 100. Values below 100 mean a dollar buys more there than
  in the US (cheaper); above 100 means less (pricier) — e.g. Switzerland
  ~112, India ~23.
- **Why it's here:** the cleanest single "how expensive is this country,
  relative to the US" number of the four indicators so far — more directly
  interpretable than `PA.NUS.PPP` (which needs a currency conversion step)
  for a destination affordability score.
- **Latest year available:** 2025.
- **Note:** like `PA.NUS.PPP`, this has no World Bank region/income-group
  aggregates — 184/265 reference entries have a value; the rest are the
  aggregate codes plus territories/states without data.
- **Run:**
  ```
  python scripts/fetch_worldbank_indicator.py PA.NUS.GDP.PLI
  ```

### SimpleMaps — World Cities Database (Basic)

- **Source:** [SimpleMaps World Cities Database](https://simplemaps.com/data/world-cities) — Basic tier
  (free, ~50.2K prominent cities/towns worldwide, downloadable CSV/Excel).
  Fields include `city`, `lat`, `lng`, `country`, `iso2`/`iso3`,
  `admin_name`, `population`, `timezone`, `capital`, and more.
- **License:** [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
  — free to use, but **attribution is required**. Attribution for this
  project:

  > City data from the [SimpleMaps World Cities Database](https://simplemaps.com/data/world-cities), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

  (The Pro/Comprehensive tiers drop the attribution requirement, but Basic
  covers every city we need here — no reason to pay for it.)
- **What it's for:** latitude/longitude (and population) lookup for
  popular tourist destination cities. This is a one-time bulk download
  (not a per-city API), so there are no rate limits and the lookup runs
  fully offline once downloaded.

### `scripts/fetch_tourist_cities.py` — city list + coordinates

- **What it does:** downloads the SimpleMaps Basic zip into
  `raw/simplemaps/` (cached — reuse unless `--force-download`), loads the
  CSV with pandas, and writes `reference/tourist_cities.json`: the top N
  cities worldwide by population, plus a manually curated list of
  additional cities that matter for travel scoring but don't crack that
  population cutoff.
- **Config (top of the script, all-caps):**
  - `TOP_N_CITIES_BY_POPULATION` — how many cities to include, ranked by
    population (default 5000).
  - `ADDITIONAL_CITIES` — force-included cities regardless of population.
    Each entry is either a plain name (`"Charlotte"`) or a `(city,
    country)` tuple (`("Merida", "Mexico")`) to disambiguate names that
    exist in multiple countries (Mérida exists in Mexico, Spain, and
    Venezuela). Plain names fall back to the most populous match with a
    printed warning if ambiguous, so check the script's output after
    adding one.
- **Output:** `reference/tourist_cities.json`:
  ```json
  {
    "source": "SimpleMaps World Cities Database (Basic), CC BY 4.0 -- https://simplemaps.com/data/world-cities",
    "top_n_cities_by_population": 5000,
    "additional_cities_requested": 2,
    "total_cities": 5000,
    "cities": [
      {
        "city": "Tokyo",
        "city_ascii": "Tokyo",
        "country": "Japan",
        "iso2": "JP",
        "iso3": "JPN",
        "admin_name": "Tōkyō",
        "lat": 35.6897,
        "lng": 139.7742,
        "population": 39105000,
        "capital": "primary",
        "simplemaps_id": 1392685764,
        "included_reason": "top_n_population"
      },
      ...
    ]
  }
  ```
  `included_reason` is `"top_n_population"` or `"additional_cities"`, so
  downstream code can tell why a city is in the list. Sorted by
  population descending (cities with no population data sort last). No
  `timezone` field — the Basic tier's CSV only has 11 columns (`city,
  city_ascii, lat, lng, country, iso2, iso3, admin_name, capital,
  population, id`); `timezone`, `city_local`, `density`, `ranking`, etc.
  from SimpleMaps' full field list are Pro/Comprehensive-only.
- **Run:**
  ```
  python scripts/fetch_tourist_cities.py
  python scripts/fetch_tourist_cities.py --force-download   # bypass the raw/ cache
  ```
- **Note:** this sandbox blocks `simplemaps.com` (same allowlist issue as
  the World Bank API — see note above), so the script was run and
  verified on your machine, not here. `total_cities` can be less than
  `top_n_cities_by_population + additional_cities_requested` when an
  additional city already falls inside the top-N set (no duplicate is
  written).

### `reference/worldbank_metrics.json` — indicator registry

The single place that lists which World Bank indicators this project
tracks. Each entry: `code` (WDI dotted code), `name`, `unit`, `notes`.
`fetch_latest_by_country.py` reads this file to know what to fetch when
run with no arguments — to add a new indicator to the pipeline, add an
entry here rather than editing any script.

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
- Cache seeded with `NY.GDP.DEFL.KD.ZG: 2025`, `NE.EXP.GNFS.ZS: 2024`,
  `PA.NUS.PPP: 2025`, and `PA.NUS.GDP.PLI: 2025` (all confirmed live
  2026-07-19, since this sandbox can't reach the API directly — see note
  above). Different indicators can have different latest years, since
  reporting lag varies by series.

### `scripts/fetch_latest_by_country.py` — indicator value per country, latest year

- **What it does:** for each WDI indicator in `reference/worldbank_metrics.json`
  (or specific codes passed on the command line), looks up the latest
  available year via `latest_year_cache.get_latest_year()`, then fetches
  that indicator for every country/region in `reference/worldbank_countries.json`
  in one pass (`GET /data360/data?...&TIME_PERIOD=<year>`, paginated) and
  writes a single JSON keyed by country code.
- **Output:** `processed/worldbank_<code>_<year>_by_country.json`:
  ```json
  {
    "indicator": "NY.GDP.DEFL.KD.ZG",
    "indicator_id": "WB_WDI_NY_GDP_DEFL_KD_ZG",
    "name": "GDP deflator (annual %)",
    "unit": "annual % change",
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
  `name`/`unit` come from the matching entry in `worldbank_metrics.json`;
  if a code isn't registered there, they fall back to the raw code and a
  placeholder string rather than failing.
  Countries/regions without a value for that year (smaller territories,
  sanctioned/conflict states, reporting lag) are listed in `missing_codes`
  rather than silently dropped or backfilled with an old year.
- **Run:**
  ```
  python scripts/fetch_latest_by_country.py
  ```
  With no arguments, this runs every indicator in `reference/worldbank_metrics.json`
  in one go — this is the normal way to run it, and the reason the metrics
  registry exists: add an indicator there and it's picked up automatically,
  no script edits needed. Pass explicit codes (e.g.
  `python scripts/fetch_latest_by_country.py NY.GDP.DEFL.KD.ZG`) to run
  just a subset instead.
- **Generated:**
  - `processed/worldbank_NY.GDP.DEFL.KD.ZG_2025_by_country.json`
  - `processed/worldbank_NE.EXP.GNFS.ZS_2024_by_country.json`
  - `processed/worldbank_PA.NUS.PPP_2025_by_country.json`
  - `processed/worldbank_PA.NUS.GDP.PLI_2025_by_country.json`

  These are gitignored (see Layout above), so a fresh clone won't have
  them — run `python scripts/fetch_latest_by_country.py` to regenerate
  all four. It'll reuse `reference/latest_year_cache.json` instead of
  re-querying the API for the latest year, as long as the cached year
  isn't more than 1 year stale (see the cache section below).
