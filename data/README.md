# Data

## Setup

One venv for the whole project, at the repo root (not per-folder) — see
the top-level `README.md`. All commands below assume it's activated and
that you're running from `data/` (`cd data` from the repo root).

## Layout

- `scripts/` — reusable Python scripts that pull and parse raw data. Move
  code here once it's stable; use `notebooks/` for exploration.
  - `scripts/<continent>/` (`africa/`, `americas/`, `asia/`, `europe/`,
    `oceana/`) — fetch scripts scoped to that continent's geography, e.g.
    `americas/fetch_statcan_airport_movements.py` (Canada),
    `oceana/fetch_abs_visitor_arrivals.py` (Australia). `africa/` is
    currently empty (`.gitkeep`'d) — no source there yet.
  - `scripts/multiple/` — fetch scripts whose source spans many continents
    at once (World Bank, SimpleMaps, Open-Meteo, Michelin), so no single
    continent folder fits.
  - `scripts/` (root) — everything that isn't a geography-scoped fetch:
    alias-building (`build_city_aliases.py`, `build_country_aliases.py`),
    lookup helpers (`city_lookup.py`, `country_lookup.py`), scoring/compute
    scripts (`compute_monthly_scores.py`, `compute_peak_tourism_indicator.py`),
    and cross-source diffs (`diff_michelin_vs_tourist_cities.py`). These
    aren't tied to one continent, so they stay put rather than living in
    any of the geography folders.
- `raw/` — untouched downloads, one subfolder per source (gitignored, since
  it's regenerable by re-running the scripts).
- `processed/` — cleaned, tidy data derived from `raw/`, ready for scoring
  or analysis. Mirrors the `scripts/` layout above: `processed/<continent>/`
  holds output from that continent's fetch scripts (e.g.
  `processed/americas/statcan_airport_movements.csv`), `processed/multiple/`
  holds output from the cross-continent fetch scripts (World Bank,
  SimpleMaps, Open-Meteo, Michelin), and `processed/` (root) holds output
  from the root-level compute/diff scripts (`monthly_scores_<year>_by_city.json`,
  `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`,
  `michelin_cities_missing_from_tourist_cities.csv`,
  `tourist_cities_enhanced.json`) — those scripts read
  from a continent/multiple subfolder but aren't geography-scoped
  themselves, so their own output stays at root, same reasoning as why
  they stay at `scripts/` root rather than living in a geography folder.
  CSVs anywhere under `processed/` are gitignored (regenerate with the
  scripts); the tracked JSON/xlsx outputs are the exception, kept in git
  since they're the ones downstream code/notebooks actually load from.
- `reference/` — small, stable lookup files that other scripts depend on
  (country code/name mappings, API check-in caches). Tracked in git since
  they're cheap to store and useful to diff.

## Sources

### World Bank — GDP deflator (`NY.GDP.DEFL.KD.ZG`)

- **Script:** `scripts/multiple/fetch_worldbank_indicator.py`
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
  - `processed/multiple/worldbank_<code>.csv` — tidy columns `ref_area, indicator,
    time_period, obs_value, unit_measure, freq`. `ref_area` is a mix of
    ISO3 country codes and World Bank region aggregates (e.g. `ARB`,
    `AFE`) — join against `reference/worldbank_countries.json` to get
    names.
- **Run:**
  ```
  python scripts/multiple/fetch_worldbank_indicator.py NY.GDP.DEFL.KD.ZG
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

- **Script:** `scripts/multiple/fetch_worldbank_indicator.py` (same script, different code)
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
  python scripts/multiple/fetch_worldbank_indicator.py NE.EXP.GNFS.ZS
  ```

### World Bank — PPP conversion factor, GDP (`PA.NUS.PPP`)

- **Script:** `scripts/multiple/fetch_worldbank_indicator.py` (same script, different code)
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
  python scripts/multiple/fetch_worldbank_indicator.py PA.NUS.PPP
  ```

### World Bank — Price level index, GDP (`PA.NUS.GDP.PLI`)

- **Script:** `scripts/multiple/fetch_worldbank_indicator.py` (same script, different code)
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
  python scripts/multiple/fetch_worldbank_indicator.py PA.NUS.GDP.PLI
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

### `scripts/multiple/fetch_tourist_cities.py` — city list + coordinates

- **What it does:** downloads the SimpleMaps Basic zip into
  `raw/simplemaps/` (cached — reuse unless `--force-download`), loads the
  CSV with pandas, and writes `reference/tourist_cities.json`: the top N
  cities worldwide by population, plus a manually curated list of
  additional cities that matter for travel scoring but don't crack that
  population cutoff.
- **Config (top of the script, all-caps):**
  - `TOP_N_CITIES_BY_POPULATION` — how many cities to include, ranked by
    population (currently 3000).
  - `ADDITIONAL_CITIES` — force-included cities regardless of population.
    Each entry is either a plain name (`"Charlotte"`) or a `(city,
    country)` tuple (`("Merida", "Mexico")`).
    - A `(city, country)` tuple pins one specific country's city. If that
      country itself has more than one same-named city, the most
      populous is used, with a printed warning.
    - A plain name resolves to **one row per country** that has a
      matching city — the most populous such city within each country —
      so a name genuinely ambiguous across countries (e.g. `"Queenstown"`
      → New Zealand *and* South Africa *and* Australia) pulls in all of
      them, while a name that merely recurs within one country (e.g.
      several US Dublins) still only contributes a single row for that
      country. A printed note lists which countries matched, so check
      the script's output after adding a plain-name entry — use the
      tuple form instead if you only want one specific country.
  - `MANUAL_CITIES` — hand-entered rows for cities confirmed absent from
    the SimpleMaps Basic dataset entirely (not an `ADDITIONAL_CITIES`
    lookup miss — the row just isn't in the source under any spelling).
    Each entry is a full dict with `city`, `city_ascii`, `country`,
    `iso2`, `iso3`, `admin_name`, `lat`, `lng`, `population`, `capital`,
    filled in by hand from an authoritative source (e.g. the national
    statistics agency), tagged `"included_reason": "manual_override"` in
    the output. Currently just New Zealand's Queenstown (lat/lng and
    population from Stats NZ's 30 June 2025 subnational estimate for the
    Queenstown urban area) — confirmed missing by grepping the raw CSV
    directly, since only a South African and an Australian Queenstown
    exist in the Basic tier.
- **Output:** `reference/tourist_cities.json`:
  ```json
  {
    "source": "SimpleMaps World Cities Database (Basic), CC BY 4.0 -- https://simplemaps.com/data/world-cities",
    "top_n_cities_by_population": 3000,
    "additional_cities_requested": 130,
    "manual_cities_added": 1,
    "total_cities": 3062,
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
  `included_reason` is `"top_n_population"`, `"additional_cities"`, or
  `"manual_override"`, so downstream code can tell why a city is in the
  list. `simplemaps_id` is `null` for `"manual_override"` rows, since
  they have no source row. Sorted by population descending (cities with
  no population data sort last). No `timezone` field — the Basic tier's
  CSV only has 11 columns (`city, city_ascii, lat, lng, country, iso2,
  iso3, admin_name, capital, population, id`); `timezone`, `city_local`,
  `density`, `ranking`, etc. from SimpleMaps' full field list are
  Pro/Comprehensive-only.
- **Run:**
  ```
  python scripts/multiple/fetch_tourist_cities.py
  python scripts/multiple/fetch_tourist_cities.py --force-download   # bypass the raw/ cache
  ```
- **Note:** `total_cities` can be less than
  `top_n_cities_by_population + additional_cities_requested +
  manual_cities_added` when an additional or manual city already falls
  inside the top-N set, or duplicates another entry (no duplicate is
  written — check the script's printed warnings).

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

- **Script:** `scripts/multiple/latest_year_cache.py`
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
  python scripts/multiple/latest_year_cache.py NY.GDP.DEFL.KD.ZG
  python scripts/multiple/latest_year_cache.py NY.GDP.DEFL.KD.ZG --force   # bypass schedule
  ```
- Cache seeded with `NY.GDP.DEFL.KD.ZG: 2025`, `NE.EXP.GNFS.ZS: 2024`,
  `PA.NUS.PPP: 2025`, and `PA.NUS.GDP.PLI: 2025` (all confirmed live
  2026-07-19, since this sandbox can't reach the API directly — see note
  above). Different indicators can have different latest years, since
  reporting lag varies by series.

### `scripts/multiple/fetch_latest_by_country.py` — indicator value per country, latest year

- **What it does:** for each WDI indicator in `reference/worldbank_metrics.json`
  (or specific codes passed on the command line), looks up the latest
  available year via `latest_year_cache.get_latest_year()`, then fetches
  that indicator for every country/region in `reference/worldbank_countries.json`
  in one pass (`GET /data360/data?...&TIME_PERIOD=<year>`, paginated) and
  writes a single JSON keyed by country code.
- **Output:** `processed/multiple/worldbank_<code>_<year>_by_country.json`:
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
  python scripts/multiple/fetch_latest_by_country.py
  ```
  With no arguments, this runs every indicator in `reference/worldbank_metrics.json`
  in one go — this is the normal way to run it, and the reason the metrics
  registry exists: add an indicator there and it's picked up automatically,
  no script edits needed. Pass explicit codes (e.g.
  `python scripts/multiple/fetch_latest_by_country.py NY.GDP.DEFL.KD.ZG`) to run
  just a subset instead.
- **Generated:**
  - `processed/multiple/worldbank_NY.GDP.DEFL.KD.ZG_2025_by_country.json`
  - `processed/multiple/worldbank_NE.EXP.GNFS.ZS_2024_by_country.json`
  - `processed/multiple/worldbank_PA.NUS.PPP_2025_by_country.json`
  - `processed/multiple/worldbank_PA.NUS.GDP.PLI_2025_by_country.json`

  These are gitignored (see Layout above), so a fresh clone won't have
  them — run `python scripts/multiple/fetch_latest_by_country.py` to regenerate
  all four. It'll reuse `reference/latest_year_cache.json` instead of
  re-querying the API for the latest year, as long as the cached year
  isn't more than 1 year stale (see the cache section below).

### Open-Meteo — monthly weather normals (`scripts/multiple/fetch_weather_normals.py`)

- **API:** [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)
  (`GET archive-api.open-meteo.com/v1/archive`) — ERA5/ERA5-Land reanalysis
  data, free for non-commercial use, no API key. Supports multiple
  locations in one request via comma-separated `latitude`/`longitude`
  (response becomes a JSON list, one entry per coordinate, same order as
  the request).
- **What it does:** for every city in `reference/tourist_cities.json`,
  pulls one full calendar year of daily weather (max/min temperature,
  precipitation, daylight, sunshine, wind) and collapses it into a
  **monthly climate normal** — 12 months × (avg high/low temp, total
  precipitation, rainy days, avg daylight/sunshine hours, avg max wind).
  `timezone=auto` is used so days are bucketed by each city's own local
  calendar, not UTC.
- **Why it's here:** direct input to the weather/rainfall/daylight factors
  in the trip-scoring model (see the project's top-level goals) — e.g.
  "Seattle in December" vs. "Seattle in July" should score very
  differently, and this is what makes that possible per city, per month.
- **Year used:** `TARGET_YEAR = date.today().year - 1` — always the last
  *complete* calendar year, computed automatically (no manual bump needed
  each January).
- **Why one year, not a multi-year average:** a true "climate normal"
  usually averages 5-10+ years to smooth out one-off freak weather. This
  project intentionally uses a single year instead, to stay well inside
  Open-Meteo's free-tier budget (600/min, 5,000/hour, **10,000/day,
  300,000/month** — and their pricing page notes that requests spanning
  more than ~2 weeks or more than ~10 variables for a location count as
  *more than one* "call", so a multi-year pull across ~5000 cities would
  not fit in a day, possibly not even a month). If a longer baseline is
  wanted later, rerun with a different `TARGET_YEAR` each year and average
  the resulting files, or extend the script to request a multi-year range.
- **Rate limiting (confirmed empirically):** Open-Meteo's historical
  archive endpoint starts returning HTTP 429 after just 2-4 batches of 25
  cities (365 days × 7 variables each) — well short of the advertised
  600/min. `REQUEST_DELAY_SECONDS` (20s) paces successful batches; on a
  429, `fetch_batch_with_retry()` backs off and retries the *same* batch
  (60s, then 120s, 240s... up to `MAX_RATE_LIMIT_RETRIES` = 5) before
  giving up on the run. `CITIES_PER_REQUEST` (default 25) hasn't been
  tuned down in response to this — worth trying a smaller batch size if
  429s are still frequent even with the retry logic.
- **Resumable by design:** the output file is checkpointed after every
  batch, and cities already present are skipped on a re-run (`--force` to
  re-fetch anyway). This is deliberate — pulling ~5000 cities needs
  multiple sittings even with the retry logic (204 batches × 20s alone is
  over an hour before counting any 429 backoff time), and a crash or an
  unrecoverable rate limit partway through shouldn't lose progress
  already made.
- **Output:** `processed/multiple/weather_normals_<year>_by_city.json`:
  ```json
  {
    "source": "Open-Meteo Historical Weather API (ERA5/ERA5-Land reanalysis) -- https://open-meteo.com/en/docs/historical-weather-api",
    "year": 2025,
    "daily_variables": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "precipitation_hours", "daylight_duration", "sunshine_duration", "wind_speed_10m_max"],
    "generated": "2026-07-19",
    "total_cities": 5100,
    "cities": {
      "1392685764": {
        "city": "Tokyo",
        "country": "Japan",
        "admin_name": "Tōkyō",
        "lat": 35.685,
        "lng": 139.7514,
        "months": {
          "january": {
            "days_sampled": 31,
            "avg_high_c": 9.8,
            "avg_low_c": 2.1,
            "total_precipitation_mm": 45.2,
            "avg_precipitation_hours_per_day": 1.3,
            "rainy_days": 6,
            "avg_daylight_hours": 9.8,
            "avg_sunshine_hours": 6.1,
            "avg_max_wind_kmh": 14.2
          },
          ...
        }
      },
      ...
    }
  }
  ```
  Keyed by `simplemaps_id` (matches `reference/tourist_cities.json`) so
  it can be joined back to city metadata without a name-matching step.
- **Run:**
  ```
  python scripts/multiple/fetch_weather_normals.py --limit 20   # pilot a small batch first
  python scripts/multiple/fetch_weather_normals.py              # full run (resumable — safe to re-run/interrupt)
  python scripts/multiple/fetch_weather_normals.py --force       # re-fetch cities already in the output
  ```
- **Note:** this sandbox couldn't reach `open-meteo.com` at all (neither
  `curl` nor the fetch tool used for the World Bank/SimpleMaps sources got
  a response), so all real runs and rate-limit behavior were observed by
  running the script directly, not verified here. `aggregate_monthly()`
  and the batching/resume/retry/skip logic in `build_weather_normals()`
  were verified offline against synthetic fixtures, including a simulated
  429 that retries and recovers, and one that exhausts all retries and
  stops the run cleanly.
- **Note:** the output file only ever grows (cities are skipped once
  present, never removed) — if `reference/tourist_cities.json` is later
  trimmed down (e.g. by hand-editing `ADDITIONAL_CITIES`/`TOP_N_CITIES_BY_POPULATION`
  and rerunning `fetch_tourist_cities.py`), `weather_normals_<year>_by_city.json`
  can end up with *more* cities than the current tourist city list — extra
  data, not a bug. `compute_monthly_scores.py` (below) scores whatever is
  actually in this file, regardless of what's currently in
  `tourist_cities.json`.

### Monthly weather scores (`scripts/compute_monthly_scores.py`)

- **What it does:** reads `processed/multiple/weather_normals_<year>_by_city.json`
  and computes six simple, transparent, rule-based scores per city per
  calendar month — no machine learning, just plain formulas over the
  weather-normal fields, per the project's guidance to start with an
  explainable model. Each score is independent; nothing here combines them
  into one overall "goodness" number — that's a traveler-profile-specific
  weighting decision left for later, downstream code.
- **Scores computed per month:**
  - `monthly_rain_score = rainy_days / days_sampled` — fraction of days in
    the month with measurable rain.
  - `daily_rain_score = avg_precipitation_hours_per_day / 24` — fraction
    of an average day spent raining.
  - `daylight_hours_score = avg_sunshine_hours / 24` — fraction of a day
    that's actually sunny (uses `avg_sunshine_hours`, not
    `avg_daylight_hours` — sunshine is hours of unobstructed sun, daylight
    is hours the sun is above the horizon regardless of cloud cover;
    sunshine ≤ daylight always. If daylight was actually intended, swap
    the field in `compute_month_scores()`).
  - `high_temperature_score = 0 if avg_high_c >= HIGH_TEMP_THRESHOLD_C else 1`
    (default threshold 35°C).
  - `low_temperature_score = 0 if avg_low_c <= LOW_TEMP_THRESHOLD_C else 1`
    (default threshold 0°C).
  - `wind_intensity_score = min(avg_max_wind_kmh / WIND_COMFORT_CEILING_KMH, 1)`
    (default ceiling 80 km/h) — see the Beaufort scale reference just below
    for how this maps onto real-world wind conditions.
  None of these are normalized/inverted for "higher is better" consistency
  — `monthly_rain_score`/`daily_rain_score`/`wind_intensity_score` are
  literal fractions of a "worse" quantity (higher = more rain, more wind),
  while the temperature scores are binary pass/fail flags (1 = not
  extreme, 0 = extreme). Keep that in mind when combining them later.
- **Year used:** `SCORE_YEAR = date.today().year - 1` by default (matches
  `fetch_weather_normals.py`'s default, so running both with no arguments
  operates on the same year) — override with `--year` to score a
  different year's already-pulled weather file.
- **Output:** `processed/monthly_scores_<year>_by_city.json`, same
  `cities` keying (`simplemaps_id`) and city metadata as
  `weather_normals_<year>_by_city.json`, with `months` holding the six
  scores instead of raw weather stats. Includes a `scoring_rules` block
  documenting the formulas in the file itself.
- **Run:**
  ```
  python scripts/compute_monthly_scores.py
  python scripts/compute_monthly_scores.py --year 2024
  ```

#### Beaufort wind force scale (reference for `wind_intensity_score`)

The [Beaufort scale](https://en.wikipedia.org/wiki/Beaufort_scale) is the
standard way to relate a wind speed to what it actually feels/looks like
on land — used here just as an interpretability reference for
`wind_intensity_score`, not as a data source (it's a public scientific
scale, not a licensed dataset). `wind_intensity_score` is a plain linear
ramp from 0 km/h → 0 to `WIND_COMFORT_CEILING_KMH` (80 km/h) → 1, capped
at 1 beyond that — 80 km/h was chosen because it sits right at the
boundary between force 9 (Strong Gale) and force 10 (Storm), i.e.
"noticeable structural damage begins" territory.

| Force | Description | Speed (km/h) | Land observations | `wind_intensity_score` |
|---|---|---|---|---|
| 0 | Calm | <1 | Smoke rises vertically | 0.00 |
| 1 | Light Air | 1–5 | Smoke drift shows direction, wind vanes don't move | 0.01–0.06 |
| 2 | Light Breeze | 6–11 | Wind felt on face, leaves rustle | 0.08–0.14 |
| 3 | Gentle Breeze | 12–19 | Leaves/twigs in constant motion, flags extend | 0.15–0.24 |
| 4 | Moderate Breeze | 20–28 | Raises dust and loose paper, small branches move | 0.25–0.35 |
| 5 | Fresh Breeze | 29–38 | Small trees sway | 0.36–0.48 |
| 6 | Strong Breeze | 38–49 | Large branches move, umbrellas hard to use | 0.48–0.61 |
| 7 | Near Gale | 50–61 | Whole trees in motion, hard to walk against | 0.63–0.76 |
| 8 | Gale | 62–74 | Twigs break off trees, progress impeded | 0.78–0.93 |
| 9 | Strong Gale | 75–88 | Slight structural damage (chimney pots, slates) | 0.94–1.00 |
| 10 | Storm | 89–102 | Trees uprooted, considerable structural damage | 1.00 (capped) |
| 11 | Violent Storm | 103–117 | Widespread damage | 1.00 (capped) |
| 12 | Hurricane | 118+ | Devastation | 1.00 (capped) |

- Verified offline: threshold edge cases (exactly at 35°C/0°C and just to
  either side), `wind_intensity_score` at 0/40/80/100/500 km/h (confirms
  the 0→1 linear ramp and the cap beyond 80), all-extreme-values and
  no-data-for-a-month cases, then run for real against the actual
  `weather_normals_2025_by_city.json` (1770 cities) and spot-checked
  against known Tokyo seasonal patterns.

### Michelin Guide restaurants (`scripts/multiple/fetch_michelin_restaurants.py`)

- **Sources (primary + fallback, same underlying dataset):**
  - **Primary:** [Kaggle — michelin-guide-restaurants-2021](https://www.kaggle.com/datasets/ngshiheng/michelin-guide-restaurants-2021),
    via `kagglehub` (`pip install kagglehub`, requires Kaggle API
    credentials — see [kagglehub's auth docs](https://github.com/Kaggle/kagglehub#authenticate)).
  - **Fallback (no credentials needed):** the same project's CSV published
    directly on GitHub —
    [ngshiheng/michelin-my-maps](https://github.com/ngshiheng/michelin-my-maps),
    `data/michelin_my_maps.csv`. The script tries kagglehub first and
    automatically falls back to this on *any* failure (not installed, no
    credentials, network error, dataset renamed, etc.) — `--force-fallback`
    skips straight to it.
- **License/attribution:** MIT licensed (the GitHub repo, which the
  Kaggle dataset is built from). The repo's own disclaimer: the underlying
  content is scraped from the [MICHELIN Guide website](https://guide.michelin.com/en/restaurants)
  "only used for research purposes, users must abide by the relevant laws
  and regulations of their location" — worth keeping in mind since Michelin
  itself, not this project or its source, is the original rightsholder of
  the restaurant reviews/descriptions.
- **What it is:** one row per MICHELIN-guide-recognized restaurant —
  name, address, `Location` ("City, Country"), price band (€–€€€€),
  cuisine, exact lat/long, and `Award` tier (`3 Stars`, `2 Stars`,
  `1 Star`, `Bib Gourmand`, or `Selected Restaurants`), plus a `GreenStar`
  sustainability flag.
- **Why it's here:** a food/culture-quality signal for the traveler-profile
  scoring model — e.g. a "food and culture traveler" profile (see the
  project's example profiles) can weight cities with more/higher Michelin
  recognition more heavily. Not yet joined to `reference/tourist_cities.json`
  or aggregated per city — this script is just the fetch/normalize step.
- **Normalization:** `Location` ("City, Country") is split into
  `location_city`/`location_country` columns to make a future join to
  `tourist_cities.json` easier; `GreenStar` is coerced from a 0/1/blank
  column to a proper boolean. Everything else is passed through as-is
  from the source CSV.
- **Output:**
  - `raw/michelin/michelin_my_maps.csv` — untouched copy of whichever
    source succeeded (kagglehub's own cache lives outside this repo, so
    this is copied in for consistency with the other sources).
  - `processed/multiple/michelin_restaurants.csv` — same rows, plus the two
    `location_city`/`location_country` columns and the boolean `GreenStar`.
- **Run:**
  ```
  python scripts/multiple/fetch_michelin_restaurants.py
  python scripts/multiple/fetch_michelin_restaurants.py --force-fallback
  ```
- **Note:** this sandbox blocks both `kaggle.com`/kagglehub's endpoints
  and `raw.githubusercontent.com` (same allowlist issue as every other
  source in this file), so neither path was run live here. `_find_csv()`
  (locating the CSV inside a kagglehub download, whether it returns a
  file or a directory, and preferring a "michelin"-named file if there
  are several) and `normalize()` (the Location split and GreenStar
  coercion) were verified offline against a fixture built from the real
  CSV header and sample rows fetched directly from GitHub. The
  kagglehub-fails→fallback logic, `--force-fallback`, and the raw/ copy
  behavior were also verified end-to-end with both paths mocked.

### UNESCO World Heritage Sites (`scripts/multiple/fetch_unesco_world_heritage_sites.py`)

- **Source:** [UNESCO World Heritage Centre Open Data](https://data.unesco.org/pages/home/)
  — `whc001`, the full World Heritage List export
  (`GET data.unesco.org/api/explore/v2.1/catalog/datasets/whc001/exports/json`),
  one JSON record per inscribed site (1223+ sites as of this writing).
- **License — unresolved, more restrictive than every other source in this
  file, do not treat as CC BY:** the `whc001` dataset page on
  data.unesco.org links its "Terms and Conditions of Use" to
  [whc.unesco.org/en/syndication](https://whc.unesco.org/en/syndication),
  which states "any republication, online or in any other form, of any
  UNESCO/WHC data requires prior written authorization," that syndicated
  content may not be modified beyond typeface/linebreaks, that it "may
  not be sold, licensed, or otherwise assigned," and that unlisted
  sections "may not be 'scraped' or otherwise syndicated in any manner."
  This is a genuinely different posture from this project's other
  sources (SimpleMaps, Eurostat, World Bank — all explicit CC BY).
  data.unesco.org's own generic "terms-and-conditions" link resolves to
  UNESCO's org-wide Access to Information Policy, which doesn't clarify
  a specific reuse license for this dataset either. **Not a lawyer, not
  legal advice** — before using this data beyond personal/internal
  research use (e.g. before shipping it in a public product or
  redistributing the processed file), get an explicit answer from
  UNESCO/WHC (contact info on the syndication page) rather than relying
  on this note.
- **What it is:** every UNESCO World Heritage Site — name, short
  description, category (`Cultural`/`Natural`/`Mixed`), inscription year
  and criteria, in-danger-list status, area, country/countries,
  transboundary flag, and coordinates. The raw export is ~24MB because
  every record duplicates its name/description in 6 languages and
  carries a full multi-paragraph inscription "justification" essay plus
  a pile of image/video URLs and per-language captions — none of which
  this project needs.
- **Why it's here:** a culture/sightseeing-suitability signal for the
  scoring model, per the project's TODO — e.g. a "food and culture
  traveler" profile (see the project's example traveler profiles) can
  weight destinations near more/more-significant heritage sites more
  heavily, the same role Michelin restaurant data plays for food.
- **Field reduction (`KEEP_FIELDS` at the top of the script):** kept —
  `name_en`, `short_description_en`, `date_inscribed`, `secondary_dates`,
  `danger` (currently on the in-danger list), `date_end` (year removed
  from the danger list, if applicable), `danger_list` (raw danger-list
  history string), `area_hectares`, `cultural_criteria`,
  `natural_criteria`, `criteria_txt`, `category`, `category_id`,
  `states_names`, `iso_codes`, `region`, `region_code`, `transboundary`,
  `main_image_url`/`main_image_author`/`main_image_copyright`/
  `main_image_caption_en`, `main_video_url`/`main_video_author`/
  `main_video_caption_en`, `components_list`, `components_count`, plus
  `lat`/`lng` (see next point). Dropped — `name_fr/es/ru/ar/zh` and
  `short_description_fr/es/ru/ar/zh` (non-English localizations),
  `description_en` (duplicates `short_description_en` in every record
  checked), `justification_en` (the single biggest field per record — a
  multi-paragraph inscription essay, not needed for scoring),
  `main_image_caption_fr/es/ru/ar/zh` and
  `main_video_caption_fr/es/ru/ar/zh` (non-English captions),
  `images_urls`, `videos_urls`, `uuid`, `id_no`. These choices were
  confirmed with the user before building the script — the initial ask
  only named a subset of fields to drop (image captions, `images_urls`,
  `uuid`, `id_no`, and, surprisingly, `coordinates`), so two points were
  checked explicitly: whether to actually drop coordinates (project
  answer: no — every other dataset here joins on `lat`/`lng`, so
  dropping them would prevent joining a heritage site to a nearby city
  later) and whether to also trim the *un*-mentioned but much larger
  text fields (`justification_en`, the 5 non-English name/description
  variants — project answer: yes, English-only, since those are what
  actually drives the 24MB raw size).
- **Coordinates handling:** the raw `coordinates` field is a nested
  `{"lon": ..., "lat": ...}` object — flattened to top-level `lat`/`lng`
  keys (`lng`, not the source's `lon`) to match the naming used
  elsewhere in this project (`reference/tourist_cities.json`,
  `weather_normals_<year>_by_city.json`), so a future join doesn't need
  a rename step first. A handful of sites (mostly older/transboundary
  entries) have no coordinates at all — `lat`/`lng` are `null` for those
  rather than the record being dropped; `sites_missing_coordinates` in
  the output's top-level metadata reports the count.
- **Output:**
  - `raw/unesco/whc001.json` — untouched download, cached (skipped on
    rerun unless `--force-download` — UNESCO adds new inscriptions
    roughly annually, so an occasional refresh is enough).
  - `processed/multiple/unesco_world_heritage_sites.json`:
    ```json
    {
      "source": "UNESCO World Heritage Centre Open Data (whc001) -- https://data.unesco.org/pages/home/",
      "source_query_url": "https://data.unesco.org/api/explore/v2.1/catalog/datasets/whc001/exports/json/?lang=en&timezone=America%2FMexico_City",
      "generated": "2026-07-27",
      "total_sites": 1223,
      "sites_missing_coordinates": 0,
      "kept_fields": ["name_en", "short_description_en", "...", "lat", "lng"],
      "dropped_fields": ["description_en", "id_no", "images_urls", "justification_en", "main_image_caption_fr", "...", "uuid", "videos_urls"],
      "coordinates_note": "coordinates was flattened into lat/lng, not dropped -- see kept_fields",
      "sites": [
        {
          "name_en": "Old Walled City of Shibam",
          "short_description_en": "Surrounded by a fortified wall, ...",
          "date_inscribed": "1982",
          "category": "Cultural",
          "states_names": ["Yemen"],
          "iso_codes": "YE",
          "region": "Arab States",
          "lat": 15.92694,
          "lng": 48.62667,
          "...": "..."
        }
      ]
    }
    ```
- **Run:**
  ```
  python scripts/multiple/fetch_unesco_world_heritage_sites.py
  python scripts/multiple/fetch_unesco_world_heritage_sites.py --force-download
  ```
- **Verified for real:** run end-to-end against the live 24MB export
  (1273 sites, 29 missing coordinates) — 24.0 MB raw shrank to 3.0 MB
  processed (13% of original). `dropped_fields` in the real output lists
  26 keys: `description_en`, `id_no`, `images_urls`,
  `justification_en`, `main_image_caption_ar/es/fr/ru/zh`,
  `main_video_caption_ar/es/fr/ru/zh`, `name_ar/es/fr/ru/zh`,
  `short_description_ar/es/fr/ru/zh`, `uuid`, `videos_urls` — computed
  from the actual raw record keys (union across all 1273 records) rather
  than hand-maintained, so it stays accurate if UNESCO adds/removes a
  field later. Before this, field keep/drop, the `coordinates` →
  `lat`/`lng` flattening, and the missing-coordinates case were also
  checked offline against a fixture built from the exact sample record
  the user provided (Old Walled City of Shibam, Yemen) plus a synthetic
  record with `coordinates: null`.

### UNESCO World Heritage Sites by country (`scripts/multiple/build_unesco_sites_by_country.py`)

- **What it does:** regroups the flat site list from
  `unesco_world_heritage_sites.json` above into `{ iso2_code: [sites] }`
  — reads the local processed file, no network call of its own (run
  `fetch_unesco_world_heritage_sites.py` first).
- **Country codes:** uses the ISO alpha-2 codes already present in each
  site's `iso_codes` field directly — no name-matching/aliasing step
  needed, unlike sources that only give a country *name* (which is what
  `reference/country_aliases.json` exists for). A transboundary site
  (comma-separated `iso_codes`, e.g. `"FR, BE"` — ~4% of the list, 51
  sites) is listed once under **every** country it spans, not just the
  first — each site record keeps its own `transboundary` field so this
  is easy to tell apart from a single-country site downstream.
- **One unassigned site:** *Old City of Jerusalem and its Walls* has no
  `iso_codes` at all in the source (its sovereignty is disputed; UNESCO
  lists it under `states_names: ["Jerusalem (Site proposed by Jordan)"]`
  with no ISO code attached) — collected under top-level
  `unassigned_sites` rather than silently dropped or force-assigned to a
  country.
- **Per-site fields dropped in this step (on top of what
  `fetch_unesco_world_heritage_sites.py` already dropped):**
  `states_names`/`iso_codes` (redundant once grouped by country) and
  `region`/`region_code` (UNESCO's admin region, e.g. "Arab States",
  isn't specific to any one of a transboundary site's several countries
  — a reader grouping by country almost certainly wants their own
  country→region mapping instead).
- **Output:** `processed/multiple/unesco_by_country.json`:
  ```json
  {
    "source": "Derived from unesco_world_heritage_sites.json -- see that file's own `source`/`source_query_url`.",
    "generated": "2026-07-28",
    "total_countries": 173,
    "total_sites": 1273,
    "total_site_country_pairs": 1378,
    "note": "total_site_country_pairs > total_sites because transboundary sites ...",
    "unassigned_sites": [{"name_en": "Old City of Jerusalem and its Walls", "states_names": ["..."], "reason": "..."}],
    "sites_by_country": {
      "MX": [{"name_en": "Historic Centre of Mexico City and Xochimilco", "date_inscribed": "1987", "lat": 19.4326, "lng": -99.1332, "...": "..."}],
      "US": ["..."],
      "VN": ["..."]
    }
  }
  ```
  Each country's sites are sorted by inscription year (oldest first),
  then name.
- **Run:**
  ```
  python scripts/multiple/build_unesco_sites_by_country.py
  ```
- **Verified for real:** run against the live processed file — 173
  countries, 1273 sites, 1378 site-country pairs (51 transboundary
  sites accounting for the 105-pair gap over 1273), 1 unassigned. Spot
  checked: US (27 sites, oldest Mesa Verde National Park 1978), VN (9
  sites, oldest Complex of Hué Monuments 1993), MX (36 sites, oldest
  Historic Centre of Mexico City and Xochimilco 1987); confirmed a
  transboundary site (Belfries of Belgium and France) appears under both
  `BE` and `FR` with identical content.

### UNESCO score (`scripts/compute_unesco_score.py`)

- **What it does:** turns the per-country site counts in
  `unesco_by_country.json` into a simple, transparent 0–10 score per
  country. Current formula (`score_for_site_count()`):
  ```
  SITE_COUNT == 0  -> 0
  SITE_COUNT > 0   -> log(SITE_COUNT + 1) / log(MAX_SITE_COUNT + 1) * 10
  ```
  Log-scaled against the single highest country (Italy, 62 sites, as of
  this writing) — the same formula `compute_michelin_score.py` uses, for
  consistency between the project's two "density of X" scores.
- **Three-version history, worth knowing before trusting this number:**
  1. **v1 — plain linear against the max** (`SITE_COUNT / MAX_SITE_COUNT * 10`).
     Dropped because whichever country happened to have the most sites
     (Italy, 62) set the whole scale, so a genuinely heritage-rich
     country like Mexico (36 sites) landed at a middling 5.81 rather
     than reflecting that 36 UNESCO sites is, on its own terms, a lot.
  2. **v2 — fixed tiers** (50+ sites → 10, 40–49 → 9, 30–39 → 8, 20–29 →
     7, then a linear ramp landing exactly on 6.0 at 19 sites — one
     point under the flat 7 a 20-site country got). Chosen specifically
     so a country's score never depended on wherever the current record
     holder sat — a 50-site country and a hypothetical 200-site country
     both scored a flat 10.
  3. **v3 — log-scale (current)**, per project request, matching
     `compute_michelin_score.py`'s formula for consistency across the
     two "density" scores. This reintroduces the dependence on the
     current max that v2 deliberately removed (smaller than v1's, since
     log compresses, but not zero — see `compute_michelin_score.py`'s
     docstring for the fuller tradeoff, since that's where log-vs-tiered
     was originally worked out for *this* dataset's much smaller 0–62
     range before the decision was made to switch anyway). Concretely,
     versus v2: Mexico (36 sites) moved from 8.0 to **8.72**, Vietnam (9
     sites) from 2.84 to **5.56**, Namibia (2 sites) from 0.63 to
     **2.65** — log-scale gives noticeably more credit to low site
     counts than the tiered version did.
  A country with 0 sites scores 0.0 either way, under all three
  versions — see next point.
- **Full country coverage, not just countries with a site:** every
  country in `reference/country_aliases.json` (the same canonical
  241-country list `build_country_aliases.py` already maintains) gets a
  row — 242 total once the two overrides below are added — including
  the 69 with zero UNESCO sites. A destination-scoring model needs a
  real 0 for "this country has no World Heritage Sites," not a missing
  row that could be mistaken for "unscored"/"unknown."
- **Two country-code gaps, patched in this script rather than upstream:**
  `ISO2_OVERRIDES` at the top of the script hand-fixes two codes UNESCO's
  data uses that `country_aliases.json` doesn't resolve cleanly:
  - **Namibia** — its `iso2` in `country_aliases.json` is stored as an
    actual `NaN` float, not the string `"NA"`. Almost certainly
    Namibia's real ISO 3166-1 alpha-2 code (`"NA"`) got silently parsed
    as pandas' NaN sentinel somewhere in `build_country_aliases.py`'s
    SimpleMaps ingestion — a well-known footgun specific to this one
    country code (`"NA"` looks like "not available" to a lot of CSV/data
    tooling). Without the override, Namibia's 2 sites (Twyfelfontein,
    Namib Sand Sea) would silently vanish from the output rather than
    scoring ~0.32. Worth a real fix in `build_country_aliases.py`
    someday (force that column to load as string, not inferred type) —
    out of scope for this script, so patched locally instead.
  - **Palestine (`PS`)** — has 1 UNESCO site (Old City of Hebron/Al-Khalil
    and its environs) but isn't in `country_aliases.json`'s 241-country
    list at all (not present in the SimpleMaps World Cities Database
    that list was built from).
  - The script fails loud, not silent, if a *new* unresolvable code
    shows up later — an unresolved `COUNTRY` gets `COUNTRY_NAME =
    "UNKNOWN -- add to ISO2_OVERRIDES"` in the output and a printed
    warning at the end of the run, rather than being dropped.
- **Output:** `processed/UNESCO_SCORE_BY_COUNTRY.csv` — one row per
  country, `COUNTRY` (iso2), `COUNTRY_NAME`, `SITE_COUNT`,
  `UNESCO_SCORE`, sorted by score descending then name. Plain CSV (no
  JSON metadata wrapper), matching `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`'s
  format rather than `monthly_scores_<year>_by_city.json`'s, since this
  is a flat per-country table, not a per-city-per-month structure that
  benefits from JSON nesting.
- **Run:**
  ```
  python scripts/compute_unesco_score.py
  ```
- **Verified for real:** run against the live `unesco_by_country.json` —
  242 countries, 173 with at least one site, 69 at exactly 0.0, max
  Italy (62 sites) → 10.0 by construction. Mexico (36 sites) → **8.72**,
  Vietnam (9) → **5.56**, Namibia (2) → **2.65** — all matching the v2→v3
  deltas quoted above exactly. No `UNKNOWN` rows in the real output —
  both `ISO2_OVERRIDES` entries resolved as expected. `OVERARCHING_TRIP_SCORE_BY_COUNTRY.csv`
  and `peak_tourism_interactive_chart.html` were both regenerated after
  this change, since they embed `UNESCO_SCORE` — see those sections
  below for the updated numbers.

### Michelin score (`scripts/compute_michelin_score.py`)

- **What it does:** turns per-country Michelin award counts from
  `processed/multiple/michelin_restaurants.csv` into a 0–10 score, same
  rule-based-not-learned family as `compute_unesco_score.py` and
  `compute_price_level_score.py`. Uses **all** awards (Stars + Bib
  Gourmand + Selected Restaurants), not starred restaurants only — 50
  countries have at least one award under this count, vs. 48 under
  starred-only (and the interactive chart's own starred-only count is
  left as-is, unaffected by this choice).
- **Formula — log-scaled against the current max:**
  ```
  AWARD_COUNT == 0  -> 0
  AWARD_COUNT > 0   -> log(AWARD_COUNT + 1) / log(MAX_AWARD_COUNT + 1) * 10
  ```
  `compute_unesco_score.py` uses this exact same formula now too (see
  above) — this script is where log-scale was first introduced in this
  project, with the following comparison as the deciding evidence
  (France = 3,043 awards, the current max):
  | Country | Awards | Linear (`count/max*10`) | Log-scale |
  |---|---|---|---|
  | Italy | 1,977 | 6.50 | 9.46 |
  | USA | 1,776 | 5.84 | 9.33 |
  | Japan | 1,106 | 3.63 | 8.74 |
  | Belgium | 709 | 2.33 | 8.19 |
  | Thailand | 484 | 1.59 | 7.71 |
  | Canada | 297 | 0.98 | 7.10 |
  | Mexico | 225 | 0.74 | 6.76 |

  Under plain linear scaling, Italy — with nearly 2,000 awards of its
  own, a genuinely enormous food scene — would score a mediocre 6.5
  purely because France's total happens to be ~50% larger; Belgium (709
  awards, one of the best food scenes per capita in the world) would
  land at 2.33, reading as "barely anything." Log-scale fixes this
  because Michelin's spread covers **three orders of magnitude**
  (France's 3,043 vs. countries with single-digit counts) — that's the
  scale of skew log-compression is actually built for.
- **UNESCO's site counts don't have nearly the same skew (0–62, about
  one order of magnitude, not three) — log-scale was tried there and
  initially rejected** for exactly that reason (it over-rewards small
  counts on a tighter range: 2 sites would jump from a tiered scheme's
  0.63 to 2.65, more than a quarter of the maximum score for barely any
  heritage sites). `compute_unesco_score.py` ran on fixed tiers instead
  for a while, specifically to avoid that. It was switched to log-scale
  anyway, on request, for formula consistency between the two "density
  of X" scores — see that script's own docstring/README section for the
  full three-version history if the numbers there look surprising.
- **One caveat log-scale brings, now shared by both scripts:** every
  country's score still depends on whichever country currently holds the
  record. If some country's count (award or site) someday overtakes the
  current max, everyone else's score for that dimension shifts slightly
  (a smaller effect than under linear scaling, since log compresses, but
  not zero). Worth knowing if either output is ever diffed across reruns
  after its source data is refreshed.
- **Country matching:** Michelin's `location_country` is a raw scraped
  string (`"Chinese Mainland"`, `"USA"`, etc.), normalized to iso3 via
  `country_lookup.normalize_country()` (same helper `build_country_aliases.py`-
  dependent scripts already use), then to iso2 via `country_aliases.json`.
  `country_lookup.report_unmapped()` confirmed zero unmatched
  `location_country` values across all 19,399 rows before this script
  was written.
- **Full country coverage:** same 242-country list as
  `UNESCO_SCORE_BY_COUNTRY.csv` (`country_aliases.json` +
  `ISO2_OVERRIDES` for Namibia/Palestine, same two gaps, same reasoning
  — see the UNESCO section above), including the ~192 countries with a
  real `MICHELIN_SCORE = 0` for "no Michelin-recognized restaurant in
  this dataset."
- **Output:** `processed/MICHELIN_SCORE_BY_COUNTRY.csv` — `COUNTRY`
  (iso2), `COUNTRY_NAME`, `AWARD_COUNT`, `MICHELIN_SCORE`, sorted by
  score descending then name.
- **Run:**
  ```
  python scripts/compute_michelin_score.py
  ```
- **Verified for real:** run against the live `michelin_restaurants.csv`
  — 242 countries, 50 with at least one award. Max: France, 3,043
  awards, score 10.0 (by construction). Spot-checked against the
  comparison table above by hand — Mexico (225 awards) scored 6.76,
  Belgium (709) scored 8.19, matching `log(226)/log(3044)*10` and
  `log(710)/log(3044)*10` respectively.

### Price level score (`scripts/compute_price_level_score.py`)

- **What it does:** turns the World Bank's Price Level Index
  (`PA.NUS.GDP.PLI`, already pulled by `fetch_worldbank_indicator.py` —
  see `worldbank_PA.NUS.GDP.PLI_<year>_by_country.json`) into a 0–10
  **affordability** score. PLI itself runs USA=100, below 100 cheaper,
  above 100 pricier (observed range as of this writing: ~13 Nigeria to
  ~118 Iceland). Per the project's explicit decision, HIGHER
  `PRICE_SCORE` means MORE affordable — inverted from PLI's own
  direction, not a literal pass-through.
- **Formula — linear against fixed anchors, not the current
  cheapest/priciest country:**
  ```
  PLI <= 20   -> 10  (very affordable)
  PLI >= 120  -> 0   (very expensive)
  otherwise   -> 10 - (PLI - 20) / 10
  ```
  `FLOOR_PLI=20`/`CEILING_PLI=120` bracket the real observed range
  (~13–118) with a little headroom on each side, but are fixed reference
  points, not derived from whichever country happens to be
  cheapest/priciest in the current pull — same reasoning as UNESCO's
  fixed tiers, applied to a continuous metric instead of a count.
- **Why plain linear here, not log-scale or tiers:** PLI's real spread
  (~13 to ~118) isn't skewed the way UNESCO/Michelin counts are — no
  order-of-magnitude long tail, just a roughly bell-shaped range around
  a median of ~43. A plain linear scale is the right tool for a metric
  shaped like this; log-scaling or tiering would be solving a skew
  problem PLI doesn't actually have.
- **Missing data is blank, not 0:** 59 of 242 countries (mostly small
  territories, plus a handful of sanctioned/conflict states) have no PLI
  value at all — `PRICE_LEVEL_INDEX`/`PRICE_SCORE` are empty strings for
  these, not `0`. A `PRICE_SCORE` of 0 would mean "confirmed as
  extremely expensive," which is a real claim this project has no data
  to back for these countries — silently defaulting to 0 would bias any
  downstream average toward "unaffordable" for a country this script
  simply has no price signal for. See `build_overarching_trip_scores.py`
  below for how that blank is handled when averaging.
- **Country matching:** the World Bank PLI file is already keyed by
  iso3, so this joins directly against `country_aliases.json`'s
  iso3→iso2 mapping — no name-matching needed. Two gaps patched by
  hand: Namibia (PLI 40.68 → score 7.93) and Palestine (PLI 63.43 →
  score 5.66) both have real PLI values, but `country_aliases.json`'s
  iso2 gap for Namibia (see the UNESCO section above) meant their PLI
  data was being silently dropped even with `ISO2_OVERRIDES` already
  covering their *names* — `ISO3_TO_ISO2_OVERRIDES` (`NAM`→`NA`,
  `PSE`→`PS`) was needed as a second, separate patch to stop that. One
  country (Kosovo,
  World Bank iso3 `XKX`) genuinely isn't in `country_aliases.json` at
  all and has no override yet — printed as a note, not silently dropped,
  each run.
- **Output:** `processed/PRICE_LEVEL_SCORE_BY_COUNTRY.csv` — `COUNTRY`
  (iso2), `COUNTRY_NAME`, `PRICE_LEVEL_INDEX` (raw World Bank value, or
  blank), `PRICE_SCORE` (or blank), sorted by score descending (blanks
  last) then name.
- **Run:**
  ```
  python scripts/compute_price_level_score.py
  ```
- **Verified for real:** run against the live PLI file — 242 countries,
  183 with a PLI value (59 blank, all correctly flagged rather than
  zeroed). Most affordable: Burundi (PLI 18.74) → score 10.0 (below the
  `FLOOR_PLI=20` floor, correctly clamped). Least affordable: Iceland
  (PLI 117.85) → score 0.22. Spot-checked Mexico (PLI 53.69 → 6.63),
  Vietnam (PLI 28.01 → 9.2), and the fix for Namibia/Palestine (both now
  present with real scores instead of silently dropped) — Namibia: PLI
  40.68 → score 7.93.

### Overarching trip score (`scripts/build_overarching_trip_scores.py`)

- **What it does:** averages `UNESCO_SCORE`, `MICHELIN_SCORE`, and
  `PRICE_SCORE` into a single 0–10 `OVERARCHING_SCORE` per country —
  plain `mean()` of whichever of the three a country has, not weighted,
  per the request that kicked this script off. All three source CSVs
  already share the same 242-country, ISO2-keyed list (built by the
  three scripts above), so this is a straight per-`COUNTRY` join — no
  name-matching or aliasing needed here at all, unlike almost every
  other join in this project.
- **Missing data is averaged around, not treated as a 0:**
  `PRICE_SCORE` is blank for the 59 countries with no PLI value (see
  above) — a country's `OVERARCHING_SCORE` is the mean of however many
  of the three scores it actually has (tracked in `SCORES_AVERAGED`,
  1–3), never silently padded with a 0 for a domain with no data. A
  country missing all three would get a blank `OVERARCHING_SCORE`
  rather than a fabricated 0 or 5 — doesn't currently happen (UNESCO and
  Michelin both cover all 242 countries with a real 0 where applicable),
  but handled defensively in case a future domain doesn't.
- **What "0" means differs across the three inputs, worth knowing before
  reading this table:** `UNESCO_SCORE=0` and `MICHELIN_SCORE=0` are
  real, deliberate zeros — "this country genuinely has no UNESCO sites /
  no Michelin-recognized restaurant in this dataset" is itself a
  meaningful signal, and both are included in the average like any other
  value. `PRICE_SCORE`, by contrast, is *blank* rather than 0 when PLI
  data is missing — there's no such thing as a country with a "real"
  price level of exactly the worst possible score; a blank means this
  project doesn't know, not that the country scored badly.
- **Not weighted, not traveler-profile-aware:** this is the flat,
  unweighted baseline. A "food and culture traveler" profile weighting
  Michelin/UNESCO more heavily than affordability (or a budget traveler
  doing the reverse) — or folding in the weather scores, peak tourism
  indicator, or crime score — is a natural next step, but isn't what
  this script does.
- **Output:** both `processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.csv` —
  `COUNTRY` (iso2), `COUNTRY_NAME`, `UNESCO_SCORE`, `MICHELIN_SCORE`,
  `PRICE_SCORE` (any of the three may be blank), `SCORES_AVERAGED`
  (1–3), `OVERARCHING_SCORE`, sorted by score descending (blanks last)
  then name — and `processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.json`,
  the same data reshaped into this project's usual JSON convention: a
  top-level `source`/`generated`/`total_countries`/
  `full_data_countries`/`partial_data_countries`/`no_data_countries`
  metadata block (matching `unesco_by_country.json`,
  `monthly_scores_<year>_by_city.json`), plus a `countries` object keyed
  by ISO2 code, each value `{country_name, unesco_score, michelin_score,
  price_score, scores_averaged, overarching_score}`. Blank CSV cells
  (missing `PRICE_SCORE`, or a hypothetical all-missing
  `OVERARCHING_SCORE`) become JSON `null` rather than `""`. The JSON
  exists for anything downstream — the frontend, eventually — that wants
  this data without a CSV parser; both files are written from the same
  in-memory rows in the same run, so they can never drift from each
  other.
- **Run:**
  ```
  python scripts/build_overarching_trip_scores.py
  ```
  Run `compute_unesco_score.py`, `compute_michelin_score.py`, and
  `compute_price_level_score.py` first — this script only reads their
  output, no network calls of its own.
- **Verified for real:** run against all three live score files — 242
  countries, 183 with `SCORES_AVERAGED=3`, 59 with `SCORES_AVERAGED=2`
  (missing `PRICE_SCORE`), 0 with none. Numbers below reflect
  `compute_unesco_score.py`'s current log-scale version (see that
  section above) — top 5: China (8.51), Italy (8.19), France (8.03),
  Spain (8.0), Germany (7.53). Hand-verified three countries' arithmetic
  directly against the CSV: Mexico `(8.72 + 6.76 + 6.63) / 3 = 7.37`,
  Vietnam `(5.56 + 6.57 + 9.2) / 3 = 7.11`, United States
  `(8.04 + 9.33 + 2.0) / 3 = 6.46` — all matched exactly. Both Mexico and
  Vietnam moved up noticeably from the previous tiered-UNESCO run (7.13
  and 6.2 respectively), since log-scale gives more credit to their
  more modest UNESCO site counts than fixed tiers did. Cross-checked the
  JSON against the CSV directly: same 242 keys, `countries["CN"]` and
  `countries["IT"]` matched the China/Italy rows above exactly, and a
  spot-checked `SCORES_AVERAGED=2` country (Taiwan, Cuba) had
  `price_score: null` in the JSON where the CSV had a blank cell.

### Eurostat — Air transport of passengers by country (`TTR00012`/`TTR00016`, `scripts/europe/fetch_eurostat_dataset.py`)

- **Source:** [Eurostat Statistics API](https://wikis.ec.europa.eu/display/EUROSTATHELP/API+-+Getting+started)
  — `GET /eurostat/api/dissemination/statistics/1.0/data/<dataset_id>`,
  returns [JSON-stat](https://json-stat.org/): a hypercube (`value` dict
  keyed by a flat row-major index, plus a `dimension` object of
  code/label pairs per axis) rather than a flat table. The script decodes
  this back into one row per observation. Despite the "ttr" prefix,
  neither dataset is tourism data — both are air passenger traffic
  (arrivals + departures, excluding direct transit), sourced from
  Eurostat's underlying `AVIA_PAOC` collection.
- **Two granularities, same underlying source:**
  - **`TTR00012`** — yearly. Effectively `geo × time(year) → passenger
    count`; every other dimension (`freq`, `unit`, `tra_meas`, `tra_cov`,
    `schedule`) is pinned to a single value.
  - **`TTR00016`** — monthly, and the one actually used for the scoring
    model (a per-month "how busy is this country's air travel"
    signal fits the project's monthly-destination-score approach better
    than one number per year). Same shape, plus a `tra_cov` (transport
    coverage) dimension with 5 real categories — `TOTAL`, `NAT`
    (national), `INTL` (international), `INTL_IEU27_2020` (intra-EU),
    `INTL_XEU27_2020` (extra-EU) — pin it to `TOTAL` via
    `--filter tra_cov=TOTAL` to match `TTR00012`'s scope, or fetch a
    breakdown by leaving it unfiltered. **Short history**: as of this
    writing, `TTR00016` only has data from 2025-02 through 2026-05 (16
    months total) — it's a newer series than `TTR00012` (which goes back
    to 2014), and no calendar year is fully covered yet: 2025 is missing
    January, 2026 only has data through May. Fetching with no
    `--start-period`/`--end-period` at all (recommended) just returns
    whatever's currently published — all 16 months as of this writing,
    spanning parts of both 2025 and 2026 — rather than forcing a
    calendar-year window that doesn't fully exist in the source yet.
  - **Dimension order differs between them** (`TTR00012`:
    `[freq, unit, tra_meas, tra_cov, schedule, geo, time]`; `TTR00016`:
    `[freq, unit, schedule, tra_cov, tra_meas, geo, time]`) — harmless,
    since `decode_jsonstat()` always reads the order from the payload's
    own `id` list rather than assuming one, but worth knowing if you're
    ever reading the raw JSON by hand.
  - **Time filter syntax differs too**: `TTR00012`'s `time` codes are
    bare years (`"2025"`), matched via `--time`. `TTR00016`'s are
    `"YYYY-MM"` (`"2025-02"`) — `--time 2025` matches nothing on it, use
    `--start-period`/`--end-period` (SDMX range filter) instead.
- **Why it's here:** a candidate signal for destination "crowdedness" or
  travel demand/accessibility by country — high or rising passenger
  volume is a rough proxy for how busy/well-connected a country's air
  travel is. Country-level only so far, not tied to a specific
  destination city.
- **Output:**
  - `raw/eurostat/<dataset_id>/<dataset_id><suffix>.json` — untouched API
    response.
  - `processed/europe/eurostat_<slug><suffix>.csv` — tidy, one row per
    observation, with a `<dim>` code column *and* a `<dim>_label` column
    for every dimension, plus `value`. `<slug>` is a human-readable name
    (`OUTPUT_NAME_OVERRIDES` in the script maps `TTR00012` →
    `passengers_transported_by_country`, `TTR00016` →
    `passengers_transported_by_country_monthly`; unmapped dataset ids
    fall back to the lowercased id). `<suffix>` encodes whichever
    time/dimension filters were applied (`_2025` for `--time 2025`;
    `_TOTAL` for `--filter tra_cov=TOTAL` with no time filter at all).
    Filter values use `FILTER_VALUE_LABELS` for a friendlier name where
    one's registered, and drop the dimension id itself from the filename
    since it's not meaningful to anyone who hasn't read the script --
    `tra_cov=INTL_IEU27_2020` becomes `_INTRA_EU`, not `_tra_covINTL_IEU27_2020`.
    Current files:
    - `processed/europe/eurostat_passengers_transported_by_country_2025.csv`
      (29 rows — one per reporting country, `TTR00012`, 2025).
    - `processed/europe/eurostat_passengers_transported_by_country_monthly_TOTAL.csv`
      (437 rows — up to 35 reporting countries × the 16 months currently
      published, `TTR00016`, `tra_cov=TOTAL` only, no time filter). Two
      earlier pulls are superseded by this one: a `..._2025-01_2025-12_...`
      version that forced a calendar-year window (silently dropping
      January, which isn't published yet), and a `..._tra_covTOTAL.csv`
      version with the old, more verbose filename convention.
- **Run:**
  ```
  python scripts/europe/fetch_eurostat_dataset.py                       # TTR00012, 2025 (defaults)
  python scripts/europe/fetch_eurostat_dataset.py TTR00012 --time 2025
  python scripts/europe/fetch_eurostat_dataset.py TTR00012 --time 2023 2024 2025
  python scripts/europe/fetch_eurostat_dataset.py TTR00012 --time       # all years, no filter
  python scripts/europe/fetch_eurostat_dataset.py TTR00016 --filter tra_cov=TOTAL   # all published months, no period filter
  ```
  Reusable for other Eurostat datasets too — pass a different dataset id;
  add an `OUTPUT_NAME_OVERRIDES` entry for a friendlier output filename.
- **Note:** this sandbox blocks `ec.europa.eu` (same allowlist issue as
  every other live source in this file), so the script itself wasn't run
  end-to-end here. `decode_jsonstat()` (the JSON-stat → tidy-row
  conversion, including the row-major flat-index math) was verified
  offline against real API responses fetched via a separate tool, for
  both datasets:
  - `TTR00012?time=2025`: Austria's decoded 2025 value (`36151294`)
    matches the raw payload's index-287 entry from an earlier unfiltered
    fetch (`geo_index 23 × time_size 12 + time_index 11 = 287`).
  - `TTR00016?startPeriod=2025-01&endPeriod=2025-12&tra_cov=TOTAL`:
    EU27_2020's 2025-02 value (`64965062`, index 0) and Austria's 2025-11
    value (`2552040`, index `23 × 10 + 9 = 239`) both matched, including
    with `TTR00016`'s different dimension ordering.
  Both `processed/europe/eurostat_*.csv` files listed above were generated from
  those same verified responses, not a live script run.

### Eurostat — Crime statistics (`CRIM_OFF_CAT`/`CRIM_GEN_REG`, `scripts/europe/fetch_eurostat_dataset.py`)

- **Source:** same [Eurostat Statistics API](https://wikis.ec.europa.eu/display/EUROSTATHELP/API+-+Getting+started)
  and script as the air-passenger datasets above — collected jointly by
  Eurostat and UNODC from national police/justice authorities. See
  [crime statistics metadata](https://ec.europa.eu/eurostat/cache/metadata/en/crim_sims.htm).
- **Two granularities, both police-recorded offences classified by
  [ICCS](https://ec.europa.eu/eurostat/statistics-explained/index.php?title=Glossary:International_classification_of_crime_for_statistical_purposes_(ICCS))
  (International Classification of Crime for Statistical Purposes):**
  - **`CRIM_OFF_CAT`** — country-level. 41 reporting geos (EU-27, EFTA —
    Iceland/Liechtenstein/Norway/Switzerland, UK split into England &
    Wales/Scotland/Northern Ireland, plus Bosnia and Herzegovina,
    Montenegro, North Macedonia, Albania, Serbia, Türkiye, Kosovo) × 25
    ICCS categories (homicide, assault, sexual violence, robbery,
    burglary, theft, drug offences, fraud, corruption, cybercrime,
    environmental crime, and more — see the script's own decoded
    `iccs_label` column, or the raw JSON's `dimension.iccs.category.label`)
    × 2 units. Annual, 2008–2024 (per `OBS_PERIOD_OVERALL_OLDEST`/
    `_LATEST` in the raw API response as of this writing).
  - **`CRIM_GEN_REG`** — NUTS3-region breakdown of the same underlying
    collection, but only for **7** of the 25 categories: intentional
    homicide, assault, robbery, burglary, burglary of private
    residential premises, theft, and theft of a motorized land vehicle
    (confirmed by inspecting a single-country response — the ICCS
    dimension itself is smaller for this dataset, not a filtering
    artifact). Not every reporting geo in `CRIM_OFF_CAT` necessarily has
    NUTS3-level data — only checked Belgium directly; unconfirmed for
    the full geo list, since a full-history, full-geo pull is large
    enough (`OBS_COUNT` 303,546 vs. `CRIM_OFF_CAT`'s 21,040) that this
    sandbox's fetch tool couldn't render the whole response to inspect
    it directly. Worth checking the decoded CSV's `geo`/`geo_label`
    columns after a real pull to see exactly which countries/regions
    are actually populated.
  - **Two units on both datasets:** `NR` (raw count) and `P_HTHAB` (per
    hundred thousand inhabitants) — `P_HTHAB` is the population-normalized
    rate, and the more directly comparable one across places of very
    different population (a French département vs. a small NUTS3 region
    shouldn't be compared on raw counts).
- **Why it's here:** the project's "safety/crime" scoring factor (see the
  project's TODO list) — e.g. a destination's `P_HTHAB` homicide/robbery/
  burglary rate is a rougher but more transparent, rule-based-model-
  friendly input than a crowdsourced perception index (Numbeo, etc.),
  and `CRIM_GEN_REG`'s NUTS3 granularity is a closer match to an actual
  city/region-level "trip opportunity" than a national average.
- **Important caveat — cross-country comparability:** legal definitions of
  each offence, victim-reporting rates, and police recording practices
  all vary by country, so a direct "country A's homicide rate is higher
  than country B's" comparison can partly reflect definitional/reporting
  differences rather than a genuine difference in safety. Fine for
  within-country, across-region or across-time comparisons (which is
  closer to how this project would actually use it — "is this region
  safer than that region, this year vs. last"); treat cross-country
  absolute comparisons cautiously. `CRIM_OFF_CAT`'s metadata page
  (`crim_sims.htm`, linked above) documents the known caveats per
  country in more detail.
- **Output:**
  - `raw/eurostat/crim_off_cat/crim_off_cat<suffix>.json` /
    `raw/eurostat/crim_gen_reg/crim_gen_reg<suffix>.json` — untouched API
    responses.
  - `processed/europe/eurostat_crime_offences_by_country<suffix>.csv` —
    one row per (country, ICCS category, unit, year), with both raw code
    and label columns (`iccs`/`iccs_label`, `geo`/`geo_label`, etc.), per
    `decode_jsonstat()`'s standard shape.
  - `processed/europe/eurostat_crime_offences_by_nuts3_region<suffix>.csv`
    — same shape, one row per (NUTS3 region, ICCS category, unit, year).
- **Run:**
  ```
  python scripts/europe/fetch_eurostat_dataset.py CRIM_OFF_CAT --time 2023 2024
  python scripts/europe/fetch_eurostat_dataset.py CRIM_GEN_REG --time 2023 --filter unit=P_HTHAB
  ```
  `CRIM_GEN_REG` is large (~1500 NUTS3 regions) — pull one or a few
  years at a time (`--time <year(s)>`) rather than `--time` with no
  values (full 2008–2024 history), and use `--filter unit=P_HTHAB` if
  only the population-normalized rate is needed, to roughly halve the
  row count.
- **Verified live, unlike the air-passenger datasets above:** this
  sandbox's `curl` couldn't reach `ec.europa.eu` (same allowlist issue
  noted elsewhere in this file), but a separate fetch tool available in
  this session *could* reach it — so `decode_jsonstat()` was verified
  against real, live API responses for both datasets (single-country
  samples, `geo=BE`, `time=2022`, to keep the response small enough to
  inspect directly): every decoded value (e.g. `CRIM_OFF_CAT` intentional
  homicide `NR=188`/`P_HTHAB=1.62`; `CRIM_GEN_REG` theft `NR=200146`/
  `P_HTHAB=1722.78`) matched the raw JSON-stat payload exactly, including
  a case where an entire ICCS category (kidnapping, `CRIM_OFF_CAT` for
  Belgium 2022) had no observations at all — confirmed the "skip missing
  positions, don't fill" behavior correctly produced zero rows for it
  rather than a null/zero value. Full-geo, full-history pulls (the kind
  the script would actually be run with) were not attempted end-to-end in
  this sandbox, since the response size exceeds what the fetch tool here
  can render — no reason to expect this affects a normal local run
  (`requests`+`pandas`, no tool-side rendering limit).

### Peak tourism indicator (`scripts/compute_peak_tourism_indicator.py`)

- **What it does:** computes, per country per calendar month, how busy
  travel is relative to that country's own peak month — a 0.0–1.0
  seasonality ratio — by combining two source families that use two
  different methods:
  - **Europe (Eurostat), full history:** reads the monthly air-passenger
    CSV (`processed/europe/eurostat_passengers_transported_by_country_monthly_*.csv`,
    `tra_cov=TOTAL` only). Not machine-learned, just:
    ```python
    FRANCE = df[df["geo"] == "FR"]
    FR_MAX_PASSENGERS = FRANCE["value"].max()
    PEAK_RATIO = FRANCE["value"] / FR_MAX_PASSENGERS
    ```
    applied per country, with EU/euro-area aggregate `geo` codes
    (`EU27_2020`, `EA21`, `EA20`, `EA19`) dropped first since they aren't
    countries.
  - **Australia, New Zealand, Japan, Costa Rica, Canada, Chile, Mexico,
    Maldives, Indonesia, Brazil, Colombia, Paraguay, Uruguay, Argentina,
    and Vietnam (`EXTRA_COUNTRY_SOURCES` + `CANADA_SOURCE` +
    `CHILE_SOURCE` + `ARGENTINA_SOURCE`), latest 12 months only:** each
    source's own most recent 12 monthly rows,
    scored against that 12-month window's own max — not full history,
    since these sources' histories aren't comparable to each other or to
    Eurostat's (see "Data gaps are real" below and the per-country notes
    further down).
    ```python
    latest_12 = df.sort_values(date_col).tail(12)
    PEAK_RATIO = df[value_col] / latest_12[value_col].max()
    ```
- **Why it's here:** a candidate seasonality signal for the scoring
  model — e.g. a destination whose travel peaks in August is probably at
  its most crowded/expensive then, all else equal.
- **Handling the source's partial year coverage (Eurostat only):**
  `TTR00016` doesn't cover one full calendar year yet, so some months
  have two years of data and the rest have one. Where a month has two
  years available, only the MORE RECENT one is kept for that month — so
  the output is always exactly one row per (country, month), never two.
  `PEAK_RATIO` itself is still scaled against the country's true max
  across *all* fetched history (both years), not just the deduplicated
  rows, so a month whose older year got dropped can still correctly read
  as less than 1.0 relative to a genuine peak that happened to fall in
  the dropped year. `SOURCE_YEAR` in the output records which year's
  observation was kept, for transparency.
- **Data gaps are real, not a bug:** not every Eurostat country reports
  every month, so per-country row counts vary. The fifteen non-Eurostat
  countries each contribute exactly 12 rows (one per calendar month) once
  their source is filtered down, EXCEPT wherever a source itself has less
  than 12 months of history available (the script prints a warning in
  that case).
- **None of the value columns are directly comparable across sources in
  magnitude** — only the shape (which month peaks, relative to that
  country's own year) is comparable. Eurostat = air passengers (int'l +
  domestic); AU/NZ = short-term visitor arrivals / visitor arrivals;
  Japan = foreign-national border entries (not tourism-purpose filtered);
  Costa Rica = hotel occupancy % (bounded 0–100, so its swings compress
  differently than a count-based country's); Canada = Canada–US
  transborder flight movements only (not overseas international
  arrivals); Chile = overnight stays (person-nights, survey-weighted,
  hence non-integer); Mexico = international scheduled-operations air
  passengers, Mexican + foreign airlines combined; Maldives = total
  tourist arrivals; Indonesia = foreign tourist visits, every passport
  nationality combined; Brazil = share of annual visits (%, not a
  headcount); Colombia = foreign visitor entries; Paraguay = foreign
  visitor entries; Uruguay = tourism spending in USD millions (not a
  headcount); Argentina = foreign visitors arriving by international air
  travel, raw ("Serie original") monthly count, not seasonally adjusted;
  Vietnam = total international visitor arrivals, hand-transcribed
  (January 2026's own figure is still marked "(estimate)" on the source
  site). See
  `fetch_chile_ine_tourism_accommodation.py`,
  `fetch_statcan_airport_movements.py`,
  `build_mexico_international_passengers_dataset.py`, and the sections
  below for the full per-country reasoning, and the script's own
  docstring's "\<Country\> specifically" sections.
- **Mexico specifically:** `processed/americas/mexico_international_passengers_monthly.csv`
  (see `build_mexico_international_passengers_dataset.py`) is
  hand-transcribed from two charts, not fetched — AFAC's (Agencia Federal
  de Aviación Civil) Monthly Bulletin of Operational Statistics publishes
  "Monthly passengers transported in Scheduled International Operations"
  as two separate 2023/2024/2025 line charts, Mexican Airlines (page 7)
  and Foreign Airlines (page 9), no downloadable table for either. Only
  2025 (all 12 months, both charts) was transcribed and summed per month,
  cross-checked against a direct text extraction of the source PDF and
  against the user's own screenshots of both charts — both matched
  exactly, including an independent check that December 2025 sums to
  5.90M (1.80 + 4.10). Precise to roughly ±10,000 passengers (both source
  charts carry 2 decimal places in millions, and the two sources'
  rounding errors compound when summed), not an exact reported count.
  **Correction:** an earlier version of this pipeline used
  `mexico_domestic_passengers_monthly.csv` (SCHEDULED DOMESTIC Operations,
  page 3 of the same bulletin) instead — the only
  EXTRA_COUNTRY_SOURCES entry that would've been scored on a
  domestic-travel signal while every other country here uses an
  international one. `build_mexico_domestic_passengers_dataset.py` and
  its output CSV are left in place (still real data, just not used by
  `compute_peak_tourism_indicator.py` anymore) — see that section below.
- **Maldives specifically:** `processed/asia/maldives_recent_tourist_arrivals_monthly.csv`
  (see `build_maldives_recent_arrivals_dataset.py`) is hand-transcribed
  from the MMA Statistics Database's public Viya series page for "Total
  tourist arrivals" (series ID 104, no API token needed for that view) —
  the most recent 12 published months, cross-checked against Table 3.1's
  own published HTML rendering. A separate script,
  `fetch_maldives_mma_tourism_indicators.py`, pulls the full 12-series
  history via the authenticated MMA API instead, but its live-fetch path
  is unverified in this sandbox.
- **Indonesia specifically:** `processed/asia/indonesia_bps_tourist_visits_monthly.csv`
  (see `build_indonesia_monthly_tourist_visits_dataset.py`) is parsed
  programmatically (not hand-transcribed) from BPS-Statistics Indonesia's
  own downloaded CSV export, keeping only the GRAND TOTAL row across
  every passport nationality. Only 2025 is published in this export.
- **Brazil specifically:** `processed/americas/brazil_monthly_tourism_share.csv`
  (see `build_brazil_monthly_tourism_share_dataset.py`) is hand-
  transcribed from the UN Tourism Dashboard's "Brazil: Share by Month
  (%)" chart — a share-of-annual-visits percentage, not a headcount, so
  (like Costa Rica) it's excluded from the exploration notebook's
  passenger-count-based dot sizing. Sums to 100% across the 12 months.
  The dashboard doesn't specify which year the shares are computed over.
- **Colombia specifically:** `processed/americas/colombia_monthly_visitors.csv`
  (see `build_colombia_monthly_visitors_dataset.py`) — numbers were
  referenced from the official Colombian report of visitors, adjusting
  for recent waves of migration. Covers calendar year 2025. Source PDF
  URLs to be added. Supersedes an earlier version of this pipeline that
  used `colombia_recent_foreign_visitors_monthly.csv` (still on disk, not
  deleted, just unwired).
- **Paraguay specifically:** `processed/americas/paraguay_tourism_by_month.csv`
  (see `build_paraguay_tourism_by_month_dataset.py`) is parsed
  programmatically from INE Paraguay's own published spreadsheet (table
  14.3, "Turismo receptivo por continente de origen"), keeping the
  "Total" column across every continent of origin. Covers calendar year
  2024 — the most recent full year this specific table publishes. The
  sheet also breaks totals down by continent of origin (kept as extra
  columns in the CSV for future use, not currently scored). `ine.gov.py`
  isn't reachable from this sandbox, so the raw file is cached at
  `raw/paraguay_ine/14.3_CE2024.xlsx` — re-download from the URL in the
  script's docstring and overwrite that path to refresh.
- **Uruguay specifically:** `processed/americas/uruguay_monthly_tourism_spending.csv`
  (see `build_uruguay_monthly_tourism_spending_dataset.py`) is hand-
  transcribed from the Ministerio de Turismo's "Observatorio de Turismo
  Inteligente" dashboard, "Evolucion mensual del gasto" chart — an
  embedded Tableau visualization with no downloadable export. Covers
  calendar year 2024, USD millions of inbound tourism spending (foreign
  currency receipts), not a headcount. Verified: the 12 monthly figures
  sum to exactly 1,750 (USD millions), matching Uruguay's own reported
  2024 annual total. Because the raw values (tens to a few hundred) are
  three-ish orders of magnitude smaller than every headcount-based
  country's `PASSENGERS`, Uruguay is in `FIXED_SIZE_COUNTRIES` alongside
  Costa Rica, Canada, and Brazil in both the notebook and the interactive
  chart script — sqrt-scaling it against the rest would round every one
  of its months down to the same minimum dot.
- **Vietnam specifically:** `processed/asia/vietnam_monthly_visitors.csv`
  (see `build_vietnam_monthly_visitors_dataset.py`) is hand-transcribed
  from [vietnamtourism.gov.vn's monthly international-arrivals
  statistic](https://vietnamtourism.gov.vn/en/statistic/international) —
  no downloadable table, just each month's own rendered "Total" figure.
  Covers the latest 12 published months (Jul 2025 - Jun 2026). January
  2026 (2,453,724, the current peak) is itself still marked
  "(estimate)" on the source site rather than a finalized count — flagged
  via the output CSV's `is_estimate` column, not silently treated the
  same as the other, finalized months.
- **Output:** `processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`
  (`ALL_CAPS` filename by request, unlike this project's other
  `processed/` outputs) — columns `COUNTRY` (Eurostat `geo` code or ISO
  alpha-2 for the fifteen extra countries), `MONTH` (integer 1–12),
  `PEAK_RATIO`, plus `COUNTRY_NAME`, `SOURCE_YEAR`, and `PASSENGERS` (the
  raw value behind the ratio, whatever that source's unit actually is —
  see above) for traceability. One row per (`COUNTRY`, `MONTH`). Current
  run: 565 rows, 49 countries.
- **Run:**
  ```
  python scripts/compute_peak_tourism_indicator.py
  python scripts/compute_peak_tourism_indicator.py --tra-cov NAT   # score national-only traffic instead of total
  python scripts/compute_peak_tourism_indicator.py --skip-extra    # Eurostat countries only, old behavior
  ```
- **Verified for real:** run end-to-end against the actual processed
  CSVs from every source above (this sandbox can read locally-mounted
  files freely, unlike live Eurostat/StatCan/INE/AFAC-equivalent API
  calls). Cross-checked France's full `value_scaled` series against the
  script's output row-by-row — exact match. Also confirmed Mexico's 12
  rows land at `SOURCE_YEAR = 2025` for every month with `PEAK_RATIO =
  1.0` in July (5.76M passengers, the chart's own high point) and the
  July 2025 accommodation-adjacent seasonal pattern (school-vacation
  season) looks consistent with the other Northern Hemisphere countries'
  summer peaks.

### Interactive peak tourism chart (`scripts/build_peak_tourism_interactive_chart.py`)

- **What it does:** builds a hoverable Plotly version of the exploration
  notebook's matplotlib scatterplot from
  `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`, plus three live controls the
  static notebook chart doesn't have:
  - **Size by:** number of passengers/visitors (this project's per-country
    volume signal, sqrt-scaled, fixed size for Costa Rica/Canada/Brazil/
    Uruguay — same as the notebook), Michelin-STARRED restaurant count (Award
    contains "Star" — 1/2/3 Stars only, NOT Bib Gourmand or Selected
    Restaurants, a narrower cut than the notebook's all-award-tiers
    count), the peak tourism ratio itself (0–1, linearly scaled since it's
    already a bounded ratio), USD purchasing power
    (`usd_purchasing_power_by_country.csv`), or the UNESCO score (0–10,
    also linearly scaled — see `UNESCO_SCORE_BY_COUNTRY.csv`/
    `compute_unesco_score.py` above).
  - **Order countries by:** alphabetical, capital latitude, USD
    purchasing power, or UNESCO score.
  - **Direction:** ascending or descending, for whichever ordering is
    selected. "Ascending" means increasing value from the bottom of the
    chart to the top (standard graph-axis convention) — so "Latitude"
    ascending puts the southernmost capital at the bottom and the
    northernmost at the top, matching the notebook's fixed default look.
  Color always encodes `PEAK_RATIO` regardless of the size selection, and
  the hover tooltip always shows all five metrics (peak ratio, the raw
  per-country signal, Michelin-starred count, USD purchasing power,
  UNESCO score + site count) regardless of which one is currently driving
  marker size — so switching the dropdown never hides information, only
  re-emphasizes it.
- **UNESCO score join:** `UNESCO_SCORE_BY_COUNTRY.csv` is keyed by ISO2
  against `country_aliases.json`'s full 241-country list, not against
  this chart's own `COUNTRY` column (a mix of Eurostat geo codes and ISO2
  for the fifteen extra countries) — `load_unesco_scores()` joins by name
  via `country_lookup.normalize_country()` instead, the same fix the USD
  purchasing power join below already needed for the same reason (e.g.
  Eurostat's `EL` for Greece not matching standard ISO). All 49 of this
  chart's countries currently resolve with no `UNKNOWN`/unmatched
  warnings; a country that somehow failed to resolve would show `n/a` in
  its hover text and size as if it had a UNESCO score of 0, rather than
  breaking the chart.
- **How the controls work:** all five size arrays and four country
  orderings are precomputed in Python and embedded as plain JSON in the
  page; the dropdowns just call `Plotly.restyle()` / `Plotly.relayout()`
  against whichever precomputed array was picked. No recomputation happens
  in the browser, so there's no client-side dependency beyond Plotly.js
  itself.
- **Why Plotly.js from a CDN, not the `plotly` Python package:** this
  sandbox's `pip install plotly` failed (network/proxy restrictions
  blocking PyPI). Rather than add a dependency that may not always be
  installable, the script only uses pandas/numpy (already project
  dependencies) to build the trace/layout JSON by hand, then embeds it in
  a small HTML template that loads Plotly.js from
  `cdn.plot.ly`. The output file is fully self-contained — open it in any
  browser, no Python needed, no new `requirements.txt` entry either.
- **Output:** `processed/peak_tourism_interactive_chart.html`.
- **Run:**
  ```
  python scripts/build_peak_tourism_interactive_chart.py
  ```
- **Verified for real:** run end-to-end against the live processed
  files — 565 rows, 49 countries, zero UNESCO-match warnings. Spot
  checked Mexico's hover text directly from the generated file's embedded
  JSON: `UNESCO score: 8.72 (36 sites)` (updated after
  `compute_unesco_score.py`'s switch to log-scale — was 8.00 under the
  earlier tiered version), and confirmed the `unesco` country ordering
  (low to high) still puts Mexico fifth from the top, behind only
  Germany, Spain, France, and Italy, unchanged from before — the
  underlying scores shifted but the relative order among these 49
  countries didn't.

### USD purchasing power (`scripts/build_usd_purchasing_power_dataset.py`)

- **What it does:** joins the World Bank's Price Level Index
  (`PA.NUS.GDP.PLI`, see above) onto the same countries in
  `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv` (49 as of Vietnam's addition),
  matched by `COUNTRY_NAME` rather than by that file's own `COUNTRY`
  codes — a few of those are Eurostat-style codes that don't match
  standard ISO (e.g. `EL` for Greece), while matching on name via
  `country_lookup.normalize_country` resolves cleanly with no exceptions
  needed. **This means the output is only as current as its last run** —
  since it reads `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv` as an input
  rather than being wired into `compute_peak_tourism_indicator.py`
  itself, adding a new country to the peak tourism indicator (like
  Argentina) doesn't retroactively update this file; rerun this script
  afterward to pick it up.
- **Why 100 / PLI instead of PLI directly:** PLI is already "USA = 100,
  below 100 is cheaper" — re-expressing it as
  `USD_PURCHASING_POWER = 100 / PRICE_LEVEL_INDEX` turns that into a
  directly interpretable dollar figure: literally what $1's real buying
  power is worth in US-dollar-equivalent terms in that country. 1.50
  means $1 there buys what $1.50 would buy in the US; 0.80 means it buys
  what $0.80 would. No live exchange rate is needed for this — PLI is
  already normalized against the US dollar, so today's or yesterday's FX
  rate wouldn't change the number (this is a broad, once-a-year World
  Bank estimate, not a daily market rate).
- **Caveat:** PLI is a whole-economy price level (GDP-wide), not a
  tourist-specific basket — a rough affordability signal, not an exact
  "cost of your specific trip" number. Same caveat as the GDP deflator
  and PPP conversion factor above.
- **Output:** `processed/usd_purchasing_power_by_country.csv` — columns
  `COUNTRY`, `COUNTRY_NAME`, `PRICE_LEVEL_INDEX` (raw World Bank value),
  `USD_PURCHASING_POWER` (`100 / PRICE_LEVEL_INDEX`), `SOURCE_YEAR`.
  Current run: 49 rows, sorted most-purchasing-power to least. Vietnam,
  Indonesia, and Paraguay currently sit highest (~$3.49–3.57
  US-equivalent per dollar); Switzerland and Iceland lowest
  (~$0.85–0.89). Argentina and Vietnam each joined this file
  automatically once they were wired into
  `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv` — no code change needed here,
  just a rerun (see the note on stale derived files below the source
  list).
- **Run:**
  ```
  python scripts/build_usd_purchasing_power_dataset.py
  ```

### Japan tourism indicators (`scripts/asia/fetch_japan_tourism_indicators.py`)

- **Source:** the [e-Stat Statistics Dashboard WebAPI](https://dashboard.e-stat.go.jp/en/static/api)
  (`dashboard.e-stat.go.jp`) — **not** the main e-Stat API; no
  Application ID or registration required, unlike `api.e-stat.go.jp`.
  `getData` returns a flat list of `{time, value}` observations per
  indicator, much simpler than Eurostat's JSON-stat hypercube (no
  positional-index decoding needed — see `fetch_eurostat_dataset.py` for
  contrast). Data is organized as ~6,000 "indicators," each searchable
  via `getIndicatorInfo?SearchIndicatorWord=...`.
- **Two indicators, joined on month:**
  - **`NUM_ENTRIES`** — "Number of entries (Foreign nationals)"
    (indicator `0204030003000010010`, source: Statistics on Legal
    Migrants / Ministry of Justice border-crossing data). Counts ALL
    foreign-national entries/re-entries, not filtered to tourism
    purpose. This is the closest available proxy for "Visitor Arrivals
    to Japan" through this API — JNTO's own arrivals figure (the metric
    behind the uploaded `1-訪日外客者数...csv`) isn't published here
    under that name, confirmed by searching "visitor arrivals," "foreign
    visitors," and "inbound" with no match. Expect this to run somewhat
    higher than an official visitor-arrivals count, since it includes
    work-visa holders and returning long-term residents.
  - **`NUM_GUEST_NIGHTS`** — "Number of guest nights (Foreign visitors)"
    (indicator `1003010201000110000`, source: Accommodation Survey).
    Total nights foreign visitors (no address in Japan) spent at
    surveyed accommodation facilities. Also available at prefecture
    level (`RegionalRank=3`, all 47 prefectures) if destination-level
    granularity is wanted later — not used here since `NUM_ENTRIES` has
    no prefecture breakdown (it's a border-crossing stat, not tied to a
    destination) and the two indicators need a shared grain to join on.
  - Both pulled at `RegionalRank=2` (nationwide Japan) and
    `IsSeasonalAdjustment=1` (original, non-seasonally-adjusted
    figures).
- **Why it's here:** a candidate monthly seasonality/demand signal for
  Japan specifically, filling the same role the Eurostat air-passenger
  data does for Europe — a rough proxy for how busy/crowded Japan is in
  a given month. Two different signals (border entries vs. accommodation
  nights) kept side by side rather than combined, since they measure
  related but distinct things.
- **Output:** `processed/asia/japan_tourism_indicators_by_month.csv` —
  columns `COUNTRY` (`"JP"`), `COUNTRY_NAME` (`"Japan"`), `MONTH`
  (`"YYYY-MM"` string — deliberately *not* the bare 1–12 integer used in
  `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`, since this is a genuine
  multi-year time series rather than a deduplicated single-year
  seasonality profile, so a plain month number would collide across
  years), `NUM_ENTRIES`, `NUM_GUEST_NIGHTS`. One row per month. Current
  run: 16 rows, Jan 2025 through Apr 2026 (both indicators had identical
  month coverage as of this writing, so no gaps — the script still
  handles the two sources having different coverage via an outer join,
  leaving a blank cell rather than fabricating a value, in case that
  changes).
- **Run:**
  ```
  python scripts/asia/fetch_japan_tourism_indicators.py
  python scripts/asia/fetch_japan_tourism_indicators.py --since 2024-01
  ```
- **Note:** this sandbox blocks `dashboard.e-stat.go.jp` in `bash`
  (confirmed — `curl` fails to connect), same as every other live source
  in this file, but a separate fetch tool *could* reach it directly, so
  the API was researched and queried for real (not guessed at from
  docs alone): confirmed no auth needed, found both indicator codes via
  `getIndicatorInfo`, and pulled real Jan 2025–Apr 2026 data for both at
  nationwide level (and a prefecture-level sample for guest nights: Tokyo
  ~5.09M, Osaka ~2.05M, Kyoto ~1.52M guest-nights in June 2025). The
  script's `parse_monthly_values()` was verified against those real
  responses (Jan 2025 entries = `3800206`, Apr 2026 guest nights =
  `15362170`, both exact matches), and
  `processed/asia/japan_tourism_indicators_by_month.csv` was generated from
  that same verified data, not a live script run.

### Statistics Canada — airport itinerant movements (`scripts/americas/fetch_statcan_airport_movements.py`)

- **Source:** [Statistics Canada Web Data Service (WDS)](https://www.statcan.gc.ca/en/developers/wds/user-guide)
  — table [23-10-0304-01](https://open.canada.ca/data/en/dataset/0b985486-61b6-45a9-bb99-db4116c29fe1),
  "Domestic and international itinerant movements, by geography, airports
  with NAV CANADA services and other selected airports, monthly." Reached
  via `GET .../getFullTableDownloadCSV/23100304/en` (no API key), which
  returns the current bulk-download zip URL — StatCan reissues that URL on
  table updates, so the script resolves it live rather than hardcoding it.
  Not reached through open.canada.ca's own CKAN API like other datasets on
  that portal might suggest — this table's CKAN resources all have
  `datastore_active: false`; open.canada.ca only hosts the metadata page and
  a link out to StatCan's real API.
- **What it is:** monthly aircraft movement counts (domestic, transborder,
  other international) per Canadian airport — a direct proxy for how busy/
  well-connected a Canadian destination's air travel is, the same role
  Eurostat's air-passenger data and Japan's border-entry data play for
  their respective regions.
- **Airport matching:** the `Airports` column is a specific airport's full
  name + province (e.g. "Toronto/Lester B. Pearson International,
  Ontario"), not a bare city name, so `CITY_AIRPORT_PATTERNS` in the script
  matches city names in `reference/tourist_cities.json` against it via
  case-insensitive substring. Suburb cities with no airport of their own
  (Mississauga, Brampton, Markham, Vaughan → Toronto; Laval, Longueuil →
  Montreal; Gatineau → Ottawa; Surrey, Burnaby → Vancouver) are mapped to
  their metro area's airport as a **shared proxy**, tagged `match_type =
  shared_proxy` in the output (vs. `own_airport`) so downstream code can
  tell the two apart. Oshawa and St. Catharines are deliberately left
  unmapped — their local fields (Oshawa Executive, Niagara District) are
  small GA airports, unlikely to fall inside this table's NAV CANADA/
  "other selected airports" scope, and guessing would be worse than
  omitting them.
- **Output:** always `processed/americas/statcan_airport_movements.csv` (fixed name —
  rerunning with different flags overwrites it) — original table columns
  (`REF_DATE`, `GEO`, `DGUID`, `Airports`, the movements-breakdown column,
  `UOM`, `VALUE`, etc.), plus `city` and `match_type` only when `--cities-only`
  is passed. **Default run keeps everything: every airport, all available
  history, no city column** — narrow it down with the flags below if a
  smaller file is wanted.
- **Run:**
  ```
  python scripts/americas/fetch_statcan_airport_movements.py                   # everything: all airports, all time
  python scripts/americas/fetch_statcan_airport_movements.py --cities-only     # curated Canadian destination cities only
  python scripts/americas/fetch_statcan_airport_movements.py --years-back 5    # last 5 years, all airports
  python scripts/americas/fetch_statcan_airport_movements.py --start-date 2020-01 --end-date 2025-12
  python scripts/americas/fetch_statcan_airport_movements.py --cities-only --years-back 5
  python scripts/americas/fetch_statcan_airport_movements.py --force-download  # bypass the cached raw/ zip
  ```
- **Note:** this sandbox blocks `statcan.gc.ca` outright for shell/`requests`
  calls (same allowlist issue as every other live source in this file — a
  `curl` to the zip URL returned a proxy 403), but a separate fetch tool
  *could* reach the WDS API's `getFullTableDownloadCSV` endpoint directly:
  confirmed live, `{"status":"SUCCESS","object":"https://www150.statcan.gc.ca/n1/tbl/csv/23100304-eng.zip"}`,
  as of 2026-07-20 — so the product ID, endpoint, and current zip URL are
  all verified real. That tool can't fetch arbitrary binary zip contents
  though, so the actual data rows and exact `Airports` spellings are
  **not** verified against a live pull. `filter_movements()`, `match_city()`,
  `report_unmatched_patterns()`, `resolve_zip_url()`, and
  `download_and_extract()` were all verified offline: the first three
  against a synthetic fixture built to match the documented real schema
  (date-range filtering, city substring matching, Oshawa/proxy-city
  exclusion, unmatched-pattern warnings all behaved correctly), the last
  two against a mocked `requests.get`/in-memory zip (confirmed it picks the
  data CSV over the `_MetaData.csv` sidecar, and reuses the cached zip
  unless `--force-download`). **Run this for real on a machine that can
  reach statcan.gc.ca, then check the printed unmatched-pattern warning
  before trusting the output** — `CITY_AIRPORT_PATTERNS` may need a
  spelling correction once checked against real rows.

### Chile INE — monthly tourism accommodation survey, EMAT (`scripts/americas/fetch_chile_ine_tourism_accommodation.py`)

- **Source:** Chile's [Instituto Nacional de Estadísticas (INE)](https://www.ine.gob.cl/estadisticas-por-tema/comercio-y-servicios/actividad-mensual-del-turismo),
  "Encuesta Mensual de Alojamiento Turístico" (EMAT). Reached via a direct
  `.xlsx` download (no API), user-supplied for this script since this
  sandbox's network allowlist blocks `ine.gob.cl` (confirmed — a direct
  `requests.get` to the file URL returns a proxy 403, same issue as
  StatCan/Eurostat/e-Stat elsewhere in this file). Cached at
  `raw/chile_ine_tourism/`; `download_workbook()` still attempts a live
  fetch first (browser User-Agent, since a plain default UA is a common
  403 cause on government sites in this project) and only falls back to
  the cache if that fails.
- **What it is:** one workbook, one "Índice" sheet plus 34 numbered sheets.
  Sheets 1–33 are all monthly time series (July 2016–present), one metric
  each, by region and destino turístico ("tourist destination", INE's
  sub-region grouping) — overnight stays, arrivals, average stay length,
  occupancy rate, RevPAR, ADR, and estimated unit/bed counts, each split
  further by accommodation class (hotel vs. other) or origin (resident vs.
  foreign) in some of the 33. Sheet 34 isn't a time series at all — it's a
  static region → destino turístico → comuna (commune) lookup, parsed into
  its own output file. Run `--list-tables` to print all 34 titles.
- **Recommended indicator:** Table 1 (overnight stays, total) — the
  script's default. Same reasoning as the UNWTO Yearbook comparison this
  script followed from: arrivals count border crossings/trips, not people
  or duration, whereas overnight stays (person-nights) is a better proxy
  for how "full" a destination actually is in a given month.
- **Parsing notes:** the region/destino turístico hierarchy isn't indented
  or merged in the source — it's conveyed only by **bold formatting**
  (`font.bold`): "Total nacional" and each region name are bold, destino
  turístico rows nested under a region aren't. End-of-table is detected by
  column A text (blank or a footer marker like "FUENTE"/"Nota"), **not** by
  whether the first month column has a number — some destinos carry a
  literal `"-"` placeholder for months before they were added to the
  survey (e.g. "Cuenca del Lago Ranco" in Los Ríos has `"-"` for Jul–Sep
  2016, then real numbers from Oct 2016 on), which would truncate the
  table early under a numeric-based stop condition. Non-numeric month
  values are written out as empty/NaN, not dropped or coerced to 0.
- **Output:**
  - `processed/americas/chile_ine_tourism_monthly.csv` — long format:
    `table_number, table_name, level, region, destino_turistico, ref_date,
    value`. `level` is `national` / `region` / `destino`.
  - `processed/americas/chile_ine_destino_turistico_comunas.csv` — the
    region/destino turístico/comuna reference table from sheet 34.
- **Run:**
  ```
  python scripts/americas/fetch_chile_ine_tourism_accommodation.py               # Cuadro 1 only (overnight stays, total)
  python scripts/americas/fetch_chile_ine_tourism_accommodation.py --table 6     # Cuadro 6 (arrivals, total)
  python scripts/americas/fetch_chile_ine_tourism_accommodation.py --all-tables  # every Cuadro 1-33 in one long CSV
  python scripts/americas/fetch_chile_ine_tourism_accommodation.py --list-tables # print all 34 table titles, no download/parse
  python scripts/americas/fetch_chile_ine_tourism_accommodation.py --force-download
  ```

### Mexico AFAC — monthly international air passengers (`scripts/americas/build_mexico_international_passengers_dataset.py`)

- **Source:** Mexico's [Agencia Federal de Aviación Civil (AFAC)](https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404),
  Monthly Bulletin of Operational Statistics — December 2025 edition
  (`data/raw/mexico_afac/boletin-en-dic-2025-27012026.pdf`, user-supplied)
  — two charts: "Monthly passengers transported in Scheduled
  International Operations, Mexican Airlines (millions)" (page 7) and
  "...Foreign Airlines (millions)" (page 9), summed per month. AFAC
  publishes matching Spanish (`-es-`) and English (`-en-`) PDFs each
  month, e.g.
  https://www.gob.mx/cms/uploads/attachment/file/1051970/boletin-es-dic-2025-27012026.pdf
  for this same edition.
- **No live fetch, like Costa Rica:** the bulletin shows both series only
  as 2023/2024/2025 line charts, not downloadable tables, so the 12
  monthly 2025 values in `MEXICAN_AIRLINES_MILLIONS_2025` and
  `FOREIGN_AIRLINES_MILLIONS_2025` were hand-transcribed directly from
  each chart's own data-point labels — cross-checked against a direct
  `pdftotext -layout` extraction of the source PDF (the chart layout
  scrambles the labels' reading order, but every value appears verbatim
  there) and against the user's own screenshots of both charts. Both
  matched exactly, including an independent check that December 2025
  sums to 5.90M (1.80 + 4.10). There is deliberately no `fetch_*()`
  function; only 2025 was transcribed even though both charts also show
  2023/2024 lines.
- **What it is:** total passengers on SCHEDULED INTERNATIONAL flights
  to/from Mexico, Mexican airlines' international operations plus
  foreign airlines' operations into Mexico combined, in millions per
  month — a much closer match to "international travel volume" than the
  domestic series this replaced (see "Correction" below). Still an
  air-passenger COUNT rather than a visitor-arrivals count, so the same
  "different signal" caveat as Canada's StatCan Transborder-movements
  series applies (see above): comparable in kind to Canada's or
  Eurostat's rows, not to ABS/Stats NZ's visitor arrivals or Chile's
  overnight stays.
- **Precision:** both source charts only carry 2 decimal places in
  millions, so the summed value is precise to roughly ±10,000
  passengers (the two sources' rounding errors compound) — not an exact
  reported count like most other sources in this project.
- **Correction:** an earlier version of this dataset used
  `scripts/americas/build_mexico_domestic_passengers_dataset.py`
  instead — "Scheduled DOMESTIC Operations" (page 3 of the same
  bulletin), domestic Mexican air travel rather than international. That
  was the wrong chart for consistency with every other country in
  `compute_peak_tourism_indicator.py`'s `EXTRA_COUNTRY_SOURCES` (all
  international signals). The domestic script and its output CSV
  (`processed/americas/mexico_domestic_passengers_monthly.csv`) are left
  in place — still real, possibly useful data — but are no longer read
  by the peak tourism indicator.
- **Output:** `processed/americas/mexico_international_passengers_monthly.csv` —
  `ref_date` (`YYYY-MM`), `mexican_airlines_millions`,
  `foreign_airlines_millions`, `passengers_millions` (sum of the two),
  `passengers` (`passengers_millions * 1,000,000`, rounded).
- **Run:**
  ```
  python scripts/americas/build_mexico_international_passengers_dataset.py
  ```

### INDEC Argentina — international air travel, receptivo/emisivo (`scripts/americas/build_argentina_indec_air_tourism_dataset.py`)

- **Source:** Argentina's [INDEC (Instituto Nacional de Estadística y
  Censos)](https://www.indec.gob.ar/indec/web/Nivel4-Tema-3-13-55), "Turismo
  receptivo y emisivo. Series original, desestacionalizada y
  tendencia-ciclo. Vía aérea internacional", Enero 2016–Mayo 2026 edition.
  Reached via a direct `.xlsx` download —
  `https://www.indec.gob.ar/ftp/cuadros/economia/series_eti_via_aerea.xlsx`
  (`SOURCE_XLSX_URL`) — cached at `raw/argentina_indec/`.
  `download_workbook()` attempts a live fetch first (browser User-Agent,
  since a plain default UA is a common 403 cause on government sites in
  this project) and only falls back to the cache if that fails, same
  pattern as Chile INE above (`indec.gob.ar` is network-blocked in this
  sandbox, confirmed — same issue as `ine.gob.cl`/StatCan/Eurostat/e-Stat).
- **What it is:** two sheets, one row per month each, Jan 2016–May 2026 —
  "Turismo receptivo" (foreign visitors arriving in Argentina by
  international air travel — the destination-relevant series) and
  "Turismo emisivo" (Argentine residents departing by air). Each sheet
  carries three parallel series: "Serie original" (raw monthly count, in
  miles/thousands), "Serie desestacionalizada" (seasonally adjusted), and
  "Tendencia-ciclo" (trend-cycle, smoothed).
- **Recommended series:** "Serie original" (raw), not the seasonally
  adjusted or trend-cycle series — a peak-season indicator needs the
  seasonal signal itself, not one with it smoothed or removed. This is
  what's wired into `compute_peak_tourism_indicator.py`.
- **Output:** `processed/americas/argentina_indec_air_tourism_monthly.csv` —
  long format: `flow` (`receptivo`/`emisivo`), `ref_date` (`YYYY-MM`),
  `original_thousands`, `seasonally_adjusted_thousands`,
  `trend_cycle_thousands`, `passengers` (`original_thousands * 1,000`,
  rounded).
- **Peak tourism indicator:** wired in via `ARGENTINA_SOURCE` in
  `compute_peak_tourism_indicator.py`, filtered to `flow == "receptivo"`
  and scored on latest-12-months like Chile/Canada, even though this
  source (like Chile's) has a long full history — kept consistent with
  the other non-Eurostat sources rather than special-cased. January is
  Argentina's peak inbound month (Southern Hemisphere summer).
- **Run:**
  ```
  python scripts/americas/build_argentina_indec_air_tourism_dataset.py
  python scripts/americas/build_argentina_indec_air_tourism_dataset.py --force-download
  ```

### Australian Bureau of Statistics — visitor arrivals (`scripts/oceana/fetch_abs_visitor_arrivals.py`)

- **Source:** [ABS Time Series Directory API](https://www.abs.gov.au/about/data-services/application-programming-interfaces-apis/time-series-directory-api)
  — `GET https://abs.gov.au/servlet/TSSearchServlet?catno=3401.0&ttitle="table 1"`
  (no API key, plain `text/xml` response), which resolves the current
  `TableURL` for catalogue [3401.0](https://www.abs.gov.au/statistics/industry/tourism-and-transport/overseas-arrivals-and-departures-australia/latest-release),
  "Overseas Arrivals and Departures, Australia," Table 1 ("Total Movement,
  Arrivals - Category of Movement") — currently `340101.xlsx`. The script
  downloads that spreadsheet and parses its `Data1` sheet directly, rather
  than going through ABS's newer SDMX Data API.
- **Why not the SDMX Data API:** that API (`data.api.abs.gov.au`) works —
  confirmed live, e.g. a real `CPI` dataflow pull — but every response
  (XML, JSON, or CSV) comes back under a vendor SDMX MIME type that this
  project's fetch tooling can't render as text, only as opaque binary,
  making it impractical to inspect or debug in this environment. The two
  tourism-shaped SDMX dataflows found while researching this (`OAD_COUNTRY`,
  `OAD_REASON`, both under agency `ABS`) also don't carry a plain monthly
  total — they break out by country of residence or by reason for travel.
  The older Time Series Directory API's XML responses are ordinary
  `text/xml`, and its `TableURL` points at a classic ABS time series
  spreadsheet — much easier to work with end to end.
- **What it is:** monthly Australian overseas arrivals by category of
  movement (permanent, long-term, short-term), Original series, back to
  January 1976. The `short_term_visitors_arriving` column is the closest
  single number to "inbound tourist volume" in the table, and is this
  project's primary target — the same role StatCan's airport movements
  play for Canada and e-Stat's border-entry indicator plays for Japan.
  The other categories (permanent arrivals, long-term visitors/residents,
  totals) are kept alongside since they're free in the same pull.
- **Spreadsheet layout** (confirmed against a real downloaded copy of
  `340101.xlsx`): three sheets (`Index`, `Data1`, `Enquiries`). `Data1` is
  wide — one column per series, one row per month — with a 10-row header
  block (`Unit`, `Series Type`, `Data Type`, `Frequency`, `Collection Month`,
  `Series Start`, `Series End`, `No. Obs`, `Series ID` in column A, values
  across columns B+) before the actual date/value data starts.
  `find_header_rows()` locates the `Series Type`/`Series ID` rows by
  scanning column A for those labels rather than hardcoding row numbers.
- **Only "Original" series kept:** Table 1 also has Seasonally Adjusted and
  Trend variants for two categories, but ABS suspended both in 2020 (Trend
  from Feb 2020, Seasonally Adjusted from Apr 2020) "due to the impact of
  the COVID-19 pandemic on international travel," per the workbook's own
  Index sheet — both have been blank ever since. Original is the only
  variant with a complete, uninterrupted series.
- **Output:** `processed/oceana/abs_visitor_arrivals_monthly.csv` — `ref_date`
  ("YYYY-MM") plus one column per category: `permanent_arrivals`,
  `long_term_residents_returning`, `long_term_visitors_arriving`,
  `permanent_and_long_term_arrivals`, `short_term_residents_returning`,
  `short_term_visitors_arriving`, `total_arrivals`. Default run keeps full
  history (605 rows, 1976-01 through the latest available month).
- **Run:**
  ```
  python scripts/oceana/fetch_abs_visitor_arrivals.py                      # full history
  python scripts/oceana/fetch_abs_visitor_arrivals.py --years-back 10
  python scripts/oceana/fetch_abs_visitor_arrivals.py --start-date 2015-01 --end-date 2025-12
  python scripts/oceana/fetch_abs_visitor_arrivals.py --force-download     # bypass the cached raw/ xlsx
  ```
- **Note:** this sandbox blocks `abs.gov.au` outright for shell/`requests`
  calls (same allowlist issue as every other live source in this file —
  confirmed via a direct `curl` returning a proxy 403), but a separate fetch
  tool *could* reach `TSSearchServlet` directly and confirmed it returns
  plain, readable `text/xml` — captured live 2026-07-20, resolving the
  correct `TableURL` and Series IDs for every category in Table 1.
  `resolve_table_url()`'s XML parsing was verified against that exact
  captured response (mocked network call). Unlike every other source in
  this file, `parse_data1_sheet()` and `find_header_rows()` were verified
  against the **real** `340101.xlsx` (supplied directly, not a synthetic
  fixture) — confirmed 605 rows, all 7 "Original" columns, correct header
  row detection (`Series Type` row 3, `Series ID` row 10), and the
  Seasonally Adjusted/Trend COVID-suspension gap. Only `download_xlsx()`'s
  live download path is unverified end-to-end here — run this for real on
  a machine that can reach abs.gov.au to confirm that piece.

### Stats NZ — international visitor arrivals (`scripts/oceana/fetch_statsnz_visitor_arrivals.py`)

- **Source:** Stats NZ's monthly ["International travel" release](https://www.stats.govt.nz/information-releases/international-travel-may-2026/),
  Table 1 ("Monthly visitor arrivals"), reissued each month at a
  predictable URL keyed by release month
  (`build_url_for_release(year, month)` constructs it rather than
  hardcoding one release). No API — a direct `.xlsx` download.
- **What it is:** monthly international visitor arrivals to New Zealand —
  the same role ABS/e-Stat/StatCan play for Australia/Japan/Canada.
- **Spreadsheet layout** (confirmed against the real May-2026 workbook,
  user-supplied): Tables 1 and 2 share one sheet, `'Tables 1&2'`, laid out
  as a small report block rather than a plain grid — a header row, a
  fiscal-year row (5 columns, `"2021/22"`..`"2025/26"`, each meaning "year
  ended 31 May" of the second year), a Number/Percent subheader for the
  YoY change columns, then 12 month rows (`Jun`..`May`, since NZ's tourism
  year runs June–May) before a `"Source: Stats NZ"` footer.
  `find_table1_header_rows()` locates the header/fiscal-year rows by
  scanning column A for `"Month"` rather than hardcoding row numbers.
- **Fiscal-year grid to real calendar months:** each fiscal-year column
  `"YYYY/(YY+1)"` spans June `YYYY` through May `YYYY+1`, so the same
  column means a different calendar year depending on which month row
  it's read from (e.g. under `"2021/22"`, the `Jun` row is June 2021 but
  the `May` row is May 2022). `month_to_ref_date()` encodes that split to
  produce one ordered `ref_date` per cell.
- **YoY change columns** (`change_number_yoy`/`change_percent_yoy`)
  describe the change into whichever fiscal year is most recent in that
  release only — attached to that fiscal year's rows alone, `NaN`
  elsewhere, rather than duplicated across every fiscal year.
- **Output:** `processed/oceana/statsnz_visitor_arrivals_monthly.csv` —
  `ref_date` (`YYYY-MM`), `visitor_arrivals`, plus the two YoY columns.
- **Run:**
  ```
  python scripts/oceana/fetch_statsnz_visitor_arrivals.py                         # default: May 2026 release
  python scripts/oceana/fetch_statsnz_visitor_arrivals.py --release-year 2026 --release-month 5
  python scripts/oceana/fetch_statsnz_visitor_arrivals.py --url "https://.../some-other-release.xlsx"
  python scripts/oceana/fetch_statsnz_visitor_arrivals.py --force-download        # bypass the cached raw/ xlsx
  ```
- **Note:** this sandbox blocks `stats.govt.nz` outright (confirmed via a
  direct `curl`, proxy 403), so `build_url_for_release()`'s live download
  path is unverified end-to-end here. `find_table1_header_rows()` and
  `parse_table1()` WERE verified against the real May-2026 workbook the
  user supplied — not a synthetic fixture — confirming the row layout, the
  5 fiscal-year columns, the 12-month Jun–May block, and the footer row.
  Run this for real on a machine that can reach stats.govt.nz to confirm
  `download_xlsx()`.

### Hiking trails (OpenStreetMap Overpass API, `scripts/multiple/fetch_hiking_trails.py`)

- **Source:** [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
  (`overpass-api.de`, free, no key) — one Overpass QL query per country,
  counting `relation[route=hiking]` elements inside that country's
  `admin_level=2` boundary. Not a bulk export like most other sources
  here; this is a live query per country, fetch and per-country count
  done in one step.
- **What it is:** a count of OSM-tagged hiking-route relations per
  country — the same "how much of X does this country have" shape as
  `MICHELIN_SCORE_BY_COUNTRY.csv`'s `AWARD_COUNT` or
  `UNESCO_SCORE_BY_COUNTRY.csv`'s `SITE_COUNT`, just without a
  `compute_*_score.py` step turning it into a 0–10 score yet.
- **Blank vs. real zero:** each query does two counts in one round trip —
  whether the country's `admin_level=2` area resolves in OSM at all, and
  (only if it does) how many `route=hiking` relations are inside it. A
  country whose area doesn't resolve gets a BLANK `HIKING_ROUTE_COUNT`
  ("unknown"), not a fabricated 0 — same missing-data philosophy as
  `PRICE_SCORE` elsewhere in this project. A country with a real OSM
  boundary but genuinely no tagged hiking routes gets a real `0`.
- **Caveats:**
  - A relation **count is not a trail-length measure**. Long-distance
    trails are very often mapped as one "superroute" relation containing
    many regional sub-relations, each also tagged `route=hiking` — a
    finely-subdivided regional network can outscore a country with one
    genuinely longer trail that was never split up. Total trail-km
    (summing way geometry) would be more physically meaningful than a
    relation count, but needs a much heavier query — not attempted here.
  - **Coverage is a mapping-effort proxy as much as a trails-exist
    proxy** — OSM's hiking-route tagging density varies enormously by
    region (very dense in Central Europe, sparse in much of
    Africa/Central Asia even where real trails exist). A low or blank
    count doesn't necessarily mean a country has few hiking
    opportunities.
  - Disputed/contested territories (Kosovo, Taiwan, Western Sahara, etc.)
    may or may not have a consistently-tagged `admin_level=2` relation in
    OSM depending on how that region's contributors have chosen to map
    it — expect some of these to come back blank.
  - **License:** OSM data is [ODbL](https://opendatacommons.org/licenses/odbl/)
    licensed, not CC BY like most sources here — ODbL requires
    share-alike for derivative/produced databases in addition to
    attribution. This script's output (a per-country count) is arguably
    a "produced work" rather than the database itself, but that hasn't
    been legally confirmed — same unresolved-license posture this
    project already takes with UNESCO's data; confirm before this goes
    beyond personal/internal use.
- **Rate limiting:** `overpass-api.de`'s public instance allows 2
  concurrent query slots (confirmed live via `GET /api/status`); this
  script only ever runs one query at a time, with a politeness delay
  between countries and exponential backoff on HTTP 429/504. Resumable
  by default — countries already in the output CSV are skipped on a
  re-run (`--force` to override), same convention as
  `fetch_weather_normals.py`.
- **Output:** `processed/multiple/HIKING_TRAILS_BY_COUNTRY.csv` —
  `COUNTRY` (iso2), `COUNTRY_NAME`, `HIKING_ROUTE_COUNT` (blank or a real
  count — see above), sorted by count descending (blanks last) then
  name.
- **Run:**
  ```
  python scripts/multiple/fetch_hiking_trails.py
  python scripts/multiple/fetch_hiking_trails.py --limit 20   # pilot run
  python scripts/multiple/fetch_hiking_trails.py --force       # re-fetch everything
  ```
- **Note:** this sandbox blocks `overpass-api.de` for outbound `requests`
  calls in bash (same restriction as every other live source in this
  file). A separate fetch tool confirmed `overpass-api.de` is reachable
  in principle (a live `GET /api/status` call returned a real
  `Rate limit: 2` response, which is where this section's rate-limit
  numbers come from), but that same tool didn't surface a readable
  response body for `GET /api/interpreter` itself (tried both `out:json`
  and `out:csv`, both came back empty for reasons that weren't resolved —
  possibly a content-type-handling quirk in that tool, since
  `/api/status`'s plain-text response worked fine). So `build_query()`,
  `parse_response()`, and the CSV read/write/resume/retry-backoff logic
  were all verified offline: `parse_response()` against hand-built mock
  responses matching Overpass's documented `out count;` JSON shape (area
  found + real count, area found + zero routes, area not found, and a
  malformed-shape response correctly raising `ValueError`); the
  resumability/`--force`/sort-order logic against a full `fetch_all()`
  run with a mocked `fetch_country()` and a temporary output path (not
  the real `processed/` tree); and the retry-backoff logic against a
  mocked `requests.post` simulating a 429-then-recovers case, an
  always-504 case that correctly exhausts `MAX_RETRIES`, and a
  non-retryable 500 that fails fast without wasting retries. **Not**
  verified: an actual live HTTP round trip to `overpass-api.de`, or real
  hiking-route counts for any real country. Run this for real on a
  machine that can reach `overpass-api.de`, then spot-check a few known
  countries (e.g. Switzerland/Austria should be very high, a small
  Pacific island nation should be low or blank) before trusting the
  output.

### Art museums (`scripts/multiple/fetch_art_museums.py`)

- **Source:** ["Largest-art-museums" dataset on Kaggle](https://www.kaggle.com/datasets/drahulsingh/largest-art-museums)
  (uploader: drahulsingh), pulled via `kagglehub` (needs Kaggle API
  credentials — same auth requirement as `fetch_airline_routes.py`).
- **What it is:** 112 of the world's largest art museums by gallery
  space, name/city/country/gallery space (m²+ft²)/year established.
  Confirmed via a real run — this is a close match for Wikipedia's
  ["List of largest art museums"](https://en.wikipedia.org/wiki/List_of_largest_art_museums)
  (same museum count, same shape), so very likely scraped from (or
  derived from the same source as) that page.
- **Real column names:** `Name`, `City`, `Country`, `Gallery space in m2
  (sq ft)`, `Gallery space in sq ft`, `Year established`.
- **Data quirks (handled by `build_art_museums_by_country.py`):**
  - The two gallery-space columns aren't cleanly one-value-each — in
    every row, at least one (often both) actually contains the
    *combined* `"<m2>\n(<sq ft>)"` text, a leftover of scraping one
    Wikipedia cell into two output columns. A few rows (e.g. the
    Interdisciplinary Regional Museum of Messina, Kunsthaus Zürich) have
    only a bare number with no parenthetical in either column — those
    are left with `gallery_space_sqft: null` rather than guessing which
    unit the lone number is in.
  - `Year established` is a single year for most rows, but occasionally
    a slash-separated pair (e.g. `"1806/1908"`) — kept as
    `year_established_raw`, plus a parsed `year_established` (the first
    4-digit year found, or `null`).
  - Two country strings didn't resolve out of the box: `"Brasil"`
    (Portuguese/Spanish spelling, one row) and `"UAE"`. Both added to
    `EXTRA_ALIASES` in `build_country_aliases.py` rather than worked
    around in this script.
- **License:** unresolved. The Kaggle listing doesn't surface a clear
  license. Confirm on the dataset page before this data goes beyond
  personal/internal use — same unresolved-license posture already
  carried for UNESCO and OSM hiking-trail data above.
- **Coverage caveat:** 112 museums across 32 countries is a small,
  curated "largest by gallery space" list, not an exhaustive per-country
  museum count — most countries have zero rows here even though they
  genuinely have art museums; this measures "does this country have one
  of the world's biggest," not "how much art infrastructure does this
  country have."
- **Output:**
  - `processed/multiple/art_museums.csv` — the source CSV written
    through basically as-is (a `raw/kaggle_art_museums/` cache copy, no
    reshaping).
  - `processed/multiple/art_museums_by_country.json` — regrouped by
    iso2 (via `country_lookup.normalize_country()`), each museum's
    `gallery_space_m2`/`gallery_space_sqft`/`year_established` parsed
    per the quirks above, sorted by gallery space descending within each
    country. No `compute_*_score.py` step yet — same "raw count/data,
    not yet a 0–10 score" state `HIKING_ROUTE_COUNT` is in.
- **Run:**
  ```
  python scripts/multiple/fetch_art_museums.py
  python scripts/multiple/fetch_art_museums.py --list-files   # inspect the dataset's files without processing
  python scripts/multiple/build_art_museums_by_country.py
  ```
- **Note:** `fetch_art_museums.py` itself still hasn't been run inside
  this sandbox (can't reach Kaggle), but `build_art_museums_by_country.py`
  has — run for real against the actual `art_museums.csv` output (112
  rows, 32 countries, 0 unmatched), with spot-checks confirming the
  gallery-space parsing on the tricky rows: British Museum (m2-column had
  no parenthetical, sq-ft-column did — correctly pulled 92,000 m²/990,000
  sq ft), Louvre (both columns fully duplicated — 72,735 m²/782,910 sq
  ft), and the lone-number cases with no parenthetical in either column
  (Messina, Kunsthaus Zürich — correctly left `gallery_space_sqft: null`
  instead of guessing).

### US museum directory — zoos, aquariums, botanical gardens (`scripts/multiple/fetch_imls_museums.py`)

- **Source:** ["Museums, Aquariums, and Zoos" on Kaggle](https://www.kaggle.com/datasets/imls/museum-directory)
  — a mirror of the [IMLS Museum Data Files](https://www.imls.gov/research-evaluation/data-collection/museum-data-files),
  pulled via `kagglehub` (needs Kaggle API credentials — same auth
  requirement as `fetch_art_museums.py`).
- **What it is:** the US federal museum universe file — roughly 33,000
  institutions with name, discipline, city/state and geocoded
  latitude/longitude. Three of its disciplines are what this project is
  after:
  - `ZAW` — Zoos, Aquariums, & Wildlife Conservation
  - `BOT` — Arboretums, Botanical Gardens, & Nature Centers
  - `ART` — Art Museums
  The rest (`CMU`, `GMU`, `HSC`, `HST`, `NAT`, `SCI`) are carried through
  to the output but nothing consumes them yet.
- **Why it's here:** it's the only source in this project with
  per-institution coordinates for zoos, aquariums and botanical gardens,
  which is what `build_city_attractions.py` needs to answer "what's
  within 100km of this city" the same way UNESCO sites and Michelin
  restaurants already are. Its `ART` records also fill a real gap: the
  `art_museums_by_country.json` list above is only the ~112 largest art
  museums worldwide, so US cities show almost nothing from it.
- **Coverage caveat, and it's the big one:** IMLS is a US federal agency
  and this file covers the 50 states plus DC and nothing else. It is not
  a world museum directory — every non-US city gets zero rows from it,
  which is exactly why `fetch_osm_zoos_and_gardens.py` below exists
  alongside it.
- **License:** public domain, unusually cleanly for this project. The
  IMLS [data file documentation](https://www.imls.gov/sites/default/files/museum_data_file_documentation_and_users_guide.pdf)
  states: "Unless specifically noted, all information contained herein is
  in the public domain and may be used and reprinted without special
  permission. Citation of this source is required." Citation, not
  permission — contrast with UNESCO's unresolved license and OSM's
  share-alike ODbL.
- **Schema is unconfirmed first-hand** (this sandbox can't reach Kaggle).
  Two header conventions exist for this data — the raw IMLS release uses
  short uppercase codes (`COMMONNAME`, `DISCIPLINE`, `LATITUDE`,
  `LONGITUDE`, `PHCITY`), the Kaggle mirror is described with
  human-readable ones (`Museum Name`, `Museum Type`, `Latitude`,
  `Longitude`, `City (Physical Location)`) — so `COLUMN_CANDIDATES` in
  the script accepts either and prints exactly what it matched. Check
  that printout on the first real run; the IMLS release is also split
  across three CSVs by discipline group, so the script reads and
  concatenates every CSV it finds rather than guessing a filename.
- **Output:** `processed/multiple/imls_museums.csv` — one row per museum,
  normalized to `NAME`, `DISCIPLINE`, `DISCIPLINE_LABEL`, `CITY`,
  `STATE`, `LAT`, `LNG`. Rows with no name, no coordinates, or a `(0, 0)`
  failed-geocode sentinel are dropped (each count reported), as are exact
  duplicates on name+coordinates.
- **Run:**
  ```
  python scripts/multiple/fetch_imls_museums.py
  python scripts/multiple/fetch_imls_museums.py --list-columns   # inspect headers first if the run errors
  ```

### Zoos, aquariums and botanical gardens worldwide (OpenStreetMap Overpass API, `scripts/multiple/fetch_osm_zoos_and_gardens.py`)

- **Source:** OpenStreetMap via the [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API)
  (`overpass-api.de`, free, no API key) — one query per country against
  that country's `admin_level=2` boundary. Same source and same etiquette
  as the hiking-trail script above.
- **What it queries, and why exactly these tags:**
  - `tourism=zoo` — the canonical zoo tag; safari parks, petting zoos and
    wildlife parks carry it too, differing only by a `zoo=*` subtype that
    the script reads to label them.
  - `tourism=aquarium` — public aquariums.
  - `leisure=garden` + `garden:type=botanical` — botanical gardens. Bare
    `leisure=garden` is deliberately **not** queried: it covers every
    residential back garden and planted traffic island in OSM, millions
    of them, virtually none a destination.
  - `leisure=garden` + `garden:type=arboretum` — arboretums, grouped with
    botanical gardens to match IMLS's own `BOT` bundle.
- **Why it exists alongside IMLS:** IMLS is richer and public domain but
  US-only, and every city currently in this project's top 10 is outside
  the US. OSM is the only free source with worldwide coverage of these
  categories, so the two are merged in `build_city_attractions.py`.
- **Known asymmetry between the two:** IMLS's `BOT` includes nature
  centers; the OSM half doesn't, because there's no clean tag for them
  (they scatter across `tourism=attraction`, `amenity=community_centre`
  and `leisure=nature_reserve`, the last of which would sweep in
  thousands of uninhabited reserves). So a US city may list a nature
  center that a comparable European city won't. Each entry keeps its own
  `source` and `kind`, and the city page shows both, rather than blending
  them invisibly.
- **Coverage caveats:** the same mapping-effort-proxy caveat as hiking
  trails — a low count often means "not mapped much here" rather than
  "not much here." Tagging is also inconsistent at the edges (aquariums
  tagged only as `tourism=attraction`, botanical gardens with no
  `garden:type`), and those are missed; widening the query costs far more
  false positives than it gains. A large site can also appear twice (a
  zoo mapped as both a node and an enclosing way);
  `build_city_attractions.py` dedupes by name + proximity, which catches
  most of it.
- **License:** ODbL (Open Database License) — share-alike in addition to
  attribution, unlike this project's CC BY / public domain sources. Same
  unresolved posture as the hiking-trail data: flag before this goes
  beyond personal/internal use.
- **Resumability:** every country's raw response is cached under
  `raw/osm_zoos_and_gardens/<ISO2>.json` and the processed output is
  rebuilt from that cache each run, so an interrupted run loses nothing.
  `--rebuild` regenerates the output from cache with no network calls at
  all (use it after changing which tags are classified into which
  category).
- **Not run against a live response from this sandbox** — `overpass-api.de`
  and its mirrors are unreachable from where this was written, same
  situation `fetch_hiking_trails.py` was authored in. The query text and
  parsing follow Overpass's documented `out center tags;` shape and were
  verified offline against mock responses in that shape. Do a `--limit 3`
  pilot run and eyeball the output before a full run.
- **Output:** `processed/multiple/osm_zoos_and_gardens.json` — a flat
  worldwide list of `{name, category, kind, iso2, lat, lng, osm_type,
  osm_id}`, plus per-category totals and the counts dropped for having no
  name or no resolvable coordinates.
- **Run:**
  ```
  python scripts/multiple/fetch_osm_zoos_and_gardens.py --limit 3   # pilot
  python scripts/multiple/fetch_osm_zoos_and_gardens.py            # full run, resumable
  python scripts/multiple/fetch_osm_zoos_and_gardens.py --rebuild  # rebuild output from cache, no network
  ```

### Per-city attractions (`scripts/multiple/build_city_attractions.py`)

- **Inputs:** `processed/multiple/osm_zoos_and_gardens.json` and
  `processed/multiple/imls_museums.csv`. **Either one missing is a
  warning, not an error** — the script runs with whichever it has, so OSM
  can be pulled first and IMLS added later without a broken intermediate
  state. `sources_used` in the output records which were actually
  present, so a reader can tell "nothing near this city" from "the source
  that would have had it wasn't loaded."
- **What it does:** for every city in `reference/tourist_cities.json`,
  finds everything within 100km by great-circle distance (same haversine
  and same Earth radius as `distance_calculator.py`, vectorized in numpy
  for the same reason `build_tourist_cities_enhanced.py` does it), in
  three categories:
  - `zoo_aquarium` — OSM zoos/aquariums/safari parks + IMLS `ZAW`
  - `botanical_garden` — OSM botanical gardens/arboretums + IMLS `BOT`
  - `art_museum` — IMLS `ART` only, US-only by design; the frontend
    merges it with the worldwide largest-art-museums list rather than
    replacing it
- **Why a separate file from `tourist_cities_enhanced.json`:** that file
  is already 27MB and is loaded whole at API startup, and these two
  sources refresh on a completely different cadence (OSM changes daily,
  IMLS annually) from the UNESCO/Michelin/airport data it joins. Keeping
  them apart means refreshing attractions doesn't mean regenerating — or
  reviewing the diff of — a 27MB file.
- **Radius:** 100km, matching `CITY_DETAIL_RADIUS_KM` in
  `backend/app/data_loader.py` and the widest radius
  `build_tourist_cities_enhanced.py` precomputes, so every "nearby"
  number on a city page means the same thing. Wider than the 50km
  `SCORE_RADIUS_KM` that feeds scoring, on purpose: scoring asks "does
  this make the city better," this asks "could I get there on a day of my
  trip." Override with `--radius-km`.
- **Deduplication:** the two sources overlap completely for US zoos and
  gardens (the San Diego Zoo is in both). Two entries in the same
  category collapse into one when their names normalize to the same
  string **and** they're within 5km of each other — name alone would
  merge the many distinct "Botanical Garden"s across the country,
  proximity alone would merge a zoo and an aquarium sharing a campus.
  IMLS wins ties (curated, official names). Counts are post-dedupe, so
  the headline number always agrees with the list under it.
- **Output:** `processed/multiple/city_attractions.json`, keyed by
  `simplemaps_id` as a string (the same key the API and
  `tourist_cities_enhanced.json` use — city names aren't unique). Each
  category holds a true `count` within the radius plus a `places` list
  capped at 10, nearest-first. Cities with nothing in any category are
  omitted entirely rather than written as three empty objects — with OSM
  coverage what it is, that's most of the 3,069 cities, and omitting them
  keeps the file small enough to load at API startup without thinking
  about it.
- **Consumed by:** `backend/app/data_loader.py`'s
  `load_city_attractions()`, which is the one loader there that returns
  `None` instead of raising when its input is missing — this file is
  generated from sources that can't be pulled from every environment, so
  a checkout legitimately might not have it, and the city page hides its
  Aquariums/Zoos and Botanical Gardens sections rather than the API
  refusing to start.
- **Run:**
  ```
  python scripts/multiple/build_city_attractions.py
  ```

### Traveler trips (`scripts/multiple/fetch_traveler_trips.py`, `scripts/multiple/build_travelers.py`)

- **Source:** ["Traveler Trip Data" on Kaggle](https://www.kaggle.com/datasets/rkiattisak/traveler-trip-data)
  (uploader: rkiattisak), pulled via `kagglehub` (needs Kaggle API
  credentials — same auth requirement as `fetch_art_museums.py` and
  `fetch_imls_museums.py`).
- **What it is:** 139 trips (~13KB), one row per trip, with 13 columns:
  `Trip ID`, `Destination`, `Start date`, `End date`, `Duration (days)`,
  `Traveler name`, `Traveler age`, `Traveler gender`,
  `Traveler nationality`, `Accommodation type`, `Accommodation cost`,
  `Transportation type`, `Transportation cost`.
- **What it is NOT:** a real booking log or survey. This is a small
  teaching/sample dataset — enough to build and demo a recommendation UI
  against, which is what `/rec-sys` uses it for, but not a basis for any
  claim about how people actually travel. Treat it as fixture data with a
  plausible shape.
- **License:** CC BY 4.0. The [Zenodo mirror](https://zenodo.org/records/10907914)
  (DOI 10.5281/zenodo.10907914) states Creative Commons Attribution 4.0
  International — attribution required, redistribution and reuse allowed.
  Confirm the Kaggle listing's own license field on the first real run: a
  mirror's license statement and the original uploader's aren't guaranteed
  to match.
- **Data quirks (handled by `build_travelers.py`):**
  - **Costs are display strings**, not numbers — `"$1,200"`, `"1200 USD"`,
    `"1,500"`, and there's no currency column. Each cost is stored **both**
    parsed (`accommodation_cost: 1200.0`) and raw
    (`accommodation_cost_raw: "$1,200"`). The UI renders the raw string, so
    a value in an unexpected currency shows as `£900` rather than an
    unlabeled `900`; the parsed number exists for future scoring. Nothing
    is summed or converted across trips, precisely because the currency
    isn't known — a "total spend" figure would be quietly meaningless.
  - **Durations** are `"7 days"`-style strings; the first integer wins, so
    `"7 days, 6 nights"` still parses to 7. Raw string kept alongside.
  - **Dates** are parsed month-first (the documented samples are US-style
    `M/D/YYYY`). A `D/M/YYYY` source would be misread for days 1–12 — which
    is why the raw string is kept next to the ISO one, so a wrong reading
    is visible rather than invisible.
  - **Blank rows:** the source is documented as 139 rows with ~137 usable.
    Rows with no traveler name or no destination are dropped and counted.
- **There is no traveler ID in the source**, so who counts as "the same
  person" is a decision, not a lookup: **two rows are the same traveler
  when their name AND nationality both match** (case- and
  accent-insensitively). Name alone would merge two different people
  sharing a common name; adding age would split one traveler across trips
  taken in different years, since age changes per trip. The rule can still
  be wrong in both directions on this data — it's a small sample with
  repeated generic names — which is why `traveler_id` is derived from
  exactly those two fields (`john-smith-american`) and nothing else, so the
  grouping is legible from the URL rather than hidden in a hash.
- **Output:**
  - `processed/multiple/traveler_trips.csv` — the source CSV written
    through unchanged (a `raw/kaggle_traveler_trips/` cache copy, no
    reshaping), so a parsing bug is fixable without re-downloading.
  - `processed/multiple/travelers.json` — one entry per traveler with their
    trips nested, sorted most-trips-first, plus `age_range` (the spread
    across their trips), `trip_count` and `destinations`.
- **Note on the split of work:** `build_travelers.py` no longer reads the CSV
  or does any parsing. `build_trips_enhanced.py` (below) owns the cleaning —
  costs, dates, durations and the destination city/country split — and
  `build_travelers.py` reads *its* output and does two things: decide who
  counts as the same person, and infer where they live.
- **Inferred home base.** The source never says where a traveler is based, so
  `build_travelers.py` derives `base_city` / `base_country` /
  `base_country_code` from the two things it does say — nationality, and
  where they went:
  - `base_country` is the country of their nationality.
  - `base_city` is the first city in that country's `BASE_CITIES` list that
    they did **not** visit on any trip. That fall-through is the whole trick:
    an Australian who flew to Sydney three times is evidently not based in
    Sydney, so they get Melbourne; a Spanish traveler whose only domestic trip
    was Barcelona gets Madrid.
  - The lists are ordered "most plausible home first", which is usually but
    not always the capital: Australia leads with **Sydney** rather than
    Canberra, Canada with **Toronto** over Ottawa, Brazil with **São Paulo**
    over Brasília. The United States is the deliberate counter-example —
    **Washington, D.C.** leads rather than New York, because New York is one
    of this dataset's most-visited destinations and reading "based in New
    York" off a trip list that flies *to* New York is exactly the inference
    this is meant to avoid.
  - `base_inference` records which case a traveler was: `primary` (the
    country's default, 96 of 124), `avoided_visited` (they'd been to the ones
    ahead of it, 28), `visited_all_candidates`, or `unmapped` (no city list
    for that nationality — currently none).
  - It's a guess, and the site labels it "Likely base" for that reason. It is
    **not** research about the real authors whose names these travelers carry
    in `travelers_anon.json` — those biographies have nothing to do with
    these bases.
- **Consumed by:** `backend/app/data_loader.py`'s `load_travelers()` →
  `GET /api/travelers` (card grid) and `GET /api/travelers/{traveler_id}`
  (traveler + trips), which back the `/rec-sys` page. Like
  `load_city_attractions()`, this loader returns `None` rather than raising
  when its file is missing — `/api/travelers` then answers
  `dataset_available: false` and the page shows the two commands to run
  instead of an empty grid.
- **Run:**
  ```
  python scripts/multiple/fetch_traveler_trips.py
  python scripts/multiple/build_travelers.py
  ```

### Cleaned trips + destination split (`scripts/multiple/build_trips_enhanced.py`)

- **Input:** `processed/multiple/traveler_trips.csv` (the untouched Kaggle
  export — see the entry above).
- **What it is:** the canonical cleaned trip record for this project, one
  JSON object per trip. Everything downstream reads *this*, not the CSV:
  `build_travelers.py` groups these trips by traveler,
  `build_travelers_anon.py` renames those travelers, and the API serves the
  result. The pipeline is linear, each step with one job:
  ```
  fetch_traveler_trips.py   Kaggle           -> traveler_trips.csv
  build_trips_enhanced.py   clean + split    -> trips_enhanced.json
  build_travelers.py        group by person  -> travelers.json
  build_travelers_anon.py   author personas  -> travelers_anon.json
  ```
- **The destination split is the point, and it can't be done with
  `str.split(",")`.** The source has 60 distinct destination strings,
  inconsistent in five separate ways, all resolved by hand in a
  `DESTINATIONS` table:
  1. **City only, country implied** — `"Tokyo"`, `"Paris"`, `"Sydney"`.
     Resolved from the city: Tokyo → Japan. **55 of 137 trips** needed this.
  2. **Abbreviated or truncated countries** — `"Sydney, Aus"`,
     `"Sydney, AUS"`, `"Bangkok, Thai"`, `"Cape Town, SA"`, `"London, UK"`,
     `"New York, USA"`.
  3. **Country only, no city** — `"Japan"`, `"Brazil"`, `"Thailand"`.
     `destination_city` is `null`, **not** a guessed capital. 11 trips.
  4. **A sub-national region in the country slot** — `"Honolulu, Hawaii"`
     (a US state), `"Edinburgh, Scotland"` (a UK constituent country). The
     country column has to hold the sovereign state or every downstream join
     silently misses them.
  5. **Destinations that aren't cities** — `"Bali"`, `"Santorini"`,
     `"Hawaii"`, `"Phuket"` are islands, provinces or states. Kept in
     `destination_city` (they *are* the destination as this dataset means it)
     and flagged `destination_kind: "region"`, so a later join against a city
     database knows not to expect a match. 17 trips.
- **Fields per trip:** `destination_raw` (the original string, verbatim, so
  every inference stays auditable), `destination_city`,
  `destination_country`, `destination_country_code` (ISO 3166-1 alpha-2),
  `destination_kind` (`city` / `region` / `country`), plus the parsed and raw
  forms of every date, duration and cost, plus the traveler's name, age,
  gender and nationality so the file stands alone.
- **Why the ISO code:** country *names* are for display; the code is the join
  key every other dataset here is keyed by (weather, visas, UNESCO, Michelin,
  prices). That's what eventually makes "how good would this trip have been"
  answerable without a name-matching step.
- **Coverage is enforced, not best-effort.** Every non-empty destination
  string must resolve through `DESTINATIONS` or the script exits with the
  list of what didn't. There's deliberately no comma-splitting fallback: a
  fallback would let `"Bangkok, Thai"` through as country `"Thai"`, which is
  worse than failing — it looks resolved, joins to nothing, and nobody
  notices. Adding a destination means adding a line, since the whole value of
  this file is that a human decided what `"Bangkok, Thai"` means.
- **Country names are the readable ones** ("South Korea", "United States"),
  not this project's World Bank-derived `country_name` values ("Korea,
  South") — `destination_country_code` is what joins to those.
- **Output:** `processed/multiple/trips_enhanced.json` — 137 trips (2 of the
  CSV's 139 rows have no traveler name or destination and are skipped),
  across 22 countries.
- **Run:**
  ```
  python scripts/multiple/build_trips_enhanced.py
  python scripts/multiple/build_trips_enhanced.py --report   # print how every destination string resolves
  ```
  `--report` is the fastest way to check the table is saying what you meant.

### Hand-authored travelers (`scripts/multiple/build_synthetic_trips.py`)

- **Inputs:** none required. Optionally reads
  `raw/bts_t100/T_T100I_MARKET_ALL_CARRIER.csv` — a US DOT [T-100
  International Market](https://www.transtats.bts.gov/) extract (carrier,
  origin, destination, passengers) — to verify its itineraries are real
  routes.
- **Why:** the Kaggle dataset is 137 one-off trips with almost no repeat
  travelers — **113 of its 124 people have exactly one trip**. That's fine
  for filling a page and useless for the thing this project is building
  toward: recommending a destination from where someone has already been. A
  recommender needs a traveler with a *pattern*, so this script adds
  travelers who have one.
- **82 travelers, 1,887 trips, and as many shapes of pattern as possible** —
  the variety is the point, since a recommender that only ever sees one kind
  of habit learns nothing. The thirteen below came first, each built to be a
  different *kind* of traveler:

  | Traveler | Base | Pattern |
  |---|---|---|
  | **Joaquín Sorolla** | New York City (EWR) | 20 trips, 2016–2025. Two weeks in Europe every August (France/Italy/Spain/Portugal, never the same city twice) + Christmas week in Houston every December. United throughout. |
  | **Edward Hopper** | San Francisco (SFO) | 10 trips, 2016–2025. One long Asia trip each autumn, cities repeating freely (Tokyo ×3, Hong Kong ×2), carriers varying by route. A loyalist to a *region* rather than to an airline or a city. |
  | **Georgia O'Keeffe** | Houston (IAH) | 5 trips, 2021–2025. One week in Mexico every January, a different Mexican city each time. A tight, short, seasonal habit. |
  | **Pablo Picasso** | Barcelona (BCN) | 4 trips, one each August 2021–2024, a different US city each time. The only non-US base, so the "home country" side of a recommendation isn't all one place. |
  | **Jackson Pollock** | Chicago (ORD) | 12 trips, all 2025. Toronto the first week of *every* month — one route, one year. What a recommender should read as a commute, not twelve holidays. |
  | **Andy Warhol** | Houston (IAH) | 15 trips, 2020–2025. Mexico two or three times a year, working through **all twelve** routes mainline United flies from Houston into Mexico. Same base and same country as O'Keeffe, completely different rhythm — the pair a recommender should be able to tell apart. |
  | **Miles Davis** | Boston (BOS) | 24 trips, 2020–2025. Four European trips a year, twice around Delta's entire Boston transatlantic network (12 routes). |
  | **Stan Getz** | New York (JFK) | 30 trips, 2020–2025. All 24 of Delta's JFK transatlantic routes, one apiece, plus a week in Cancún every July. The widest spread here — 25 cities, 16 countries. Shares a city with Joaquín Sorolla and nothing else: Delta from JFK vs United from Newark. |
  | **Chet Baker** | Atlanta (ATL) | 53 trips, 2024–2025. New York every other week, Monday to Friday. The only pure business commuter — no holiday in any of it. |
  | **Bill Evans** | Detroit (DTW) | 10 trips, 2016–2025. Ten days in Amsterdam every April, and nowhere else. Total destination loyalty — the hardest case to recommend anything new to. |
  | **John Coltrane** | Minneapolis (MSP) | 15 trips, 2021–2025. Three Caribbean/Mexican beach trips every winter (Jan–Mar), never another season. Defined by *when*, not where: 8 countries, all warm, all in three months. |
  | **Thelonious Monk** | Los Angeles (LAX) | 14 trips, 2019–2025. Australia and New Zealand twice a year, on the southern hemisphere's seasons. Four cities, all ultra-long-haul. |
  | **Wes Montgomery** | Seattle (SEA) | 16 trips. Asia twice a year 2016–2019, **nothing in 2020–2021**, then straight back to it 2022–2025. The lapsed-and-returned traveler — the only one here whose calendar reflects that those two years happened. |

- **Plus eight domestic-only travelers**, 2018–2025 — one US city, one to
  three times a year, to see family, and nowhere else ever. United
  (painters): **Pierre-Auguste Renoir** San Francisco→San Diego ×3/yr,
  **Edgar Degas** Denver→Boston ×2/yr, **Claude Monet** Chicago→Cleveland
  ×2/yr, **Alfred d'Orsay** Dulles→Pittsburgh ×1/yr. Delta (jazz musicians):
  **Ella Fitzgerald** Cincinnati→Orlando ×3/yr, **Duke Ellington** Salt
  Lake→Portland ×2/yr, **Sarah Vaughan** LaGuardia→New Orleans ×2/yr,
  **Charlie Parker** Nashville→Detroit ×1/yr. This is the most common travel pattern there is
  and the one everything above lacked: the destination isn't chosen, so
  nothing about it can be recommended. They also **stay with family rather
  than in hotels**, so their trips carry `accommodation_type: "Family home"`
  and no accommodation cost at all — 128 of the dataset's trips have no
  place-to-sleep spend, which is a signal in its own right.

- **Plus thirty more on three other airlines**, built on one repeated
  three-way split so the file has every combination of domestic and
  international rather than only the extremes. Ten per airline: **three**
  international-only flying to the *same destination every time*, **three**
  domestic-only taking *holidays* (not visiting family — see below), and
  **four** mixed, with both in the same year.

  | Airline | International only (one destination) | Domestic only (holidays) | Mixed |
  |---|---|---|---|
  | **American** (scientists) | Albert Einstein DFW→London ×2/yr, Marie Curie MIA→Buenos Aires ×2/yr, Niels Bohr PHL→Lisbon ×1/yr | Isaac Newton ORD→Denver (Thanksgiving + Christmas), Galileo Galilei DCA→Orlando ×3/yr, Louis Pasteur PHL→Palm Beach ×2/yr | Charles Darwin (MIA: São Paulo, Lima, Boston, LA), Nikola Tesla (DFW: Cancún, London, San Antonio, Nashville), Stephen Hawking (LAX: Sydney, Tokyo, JFK, Miami), Richard Feynman (CLT: Madrid, New Orleans, Pittsburgh) |
  | **Southwest** (DC characters) | Clark Kent HOU→Cancún ×2/yr, Bruce Wayne BWI→Montego Bay ×2/yr, Diana Prince PHX→Los Cabos ×2/yr | Barry Allen MDW→Tampa ×2/yr, Hal Jordan DEN→San Diego ×2/yr, Arthur Curry BNA→Sarasota ×3/yr | Victor Stone (MCO: Nassau, San José CR, Baltimore, St. Louis), Oliver Queen (DEN: Los Cabos, Cancún, San Antonio, Seattle), Billy Batson (STL: Cancún, Orlando, Phoenix), Dick Grayson (MCI: Cancún, Las Vegas, Tampa) |
  | **Alaska** (Marvel characters) | Peter Parker SEA→Tokyo ×2/yr, Tony Stark LAX→Guadalajara ×2/yr, Steve Rogers HNL→Sydney ×1/yr | Bruce Banner SEA→Maui ×2/yr, Thor Odinson PDX→Palm Springs ×2/yr, Natasha Romanoff SFO→Orlando ×2/yr | Clint Barton (SEA: Seoul, Toronto, Anchorage, Spokane), Matt Murdock (SFO: Los Cabos, Puerto Vallarta, JFK, Orlando), Logan (LAX: Liberia CR, Belize City, Kona, Newark), Stephen Strange (SAN: Los Cabos, Puerto Vallarta, Boise, Honolulu) |

  Three things these thirty add that nothing above had:
  - **Holiday travel that isn't family travel.** Same low frequency and same
    single destination as the eight family visitors, but pinned to actual
    holidays (Thanksgiving, Christmas, Memorial Day, the 4th) and **paid
    for**. A traveler with no accommodation cost is visiting relatives; one
    with a hotel bill chose the destination. That distinction is the whole
    reason both groups exist.
  - **Short-haul international.** Southwest flies no long-haul at all in this
    data — its entire international network is Mexico, Central America and
    the Caribbean — so "flies abroad twice a year" now means something
    different at four hours than it does at ten. It also flies from the
    *secondary* airport where a city has one, which is why Chicago here means
    Midway (Barry Allen) alongside O'Hare (Jackson Pollock, Claude Monet,
    Isaac Newton), and Houston means Hobby (Clark Kent) alongside
    Intercontinental (O'Keeffe, Warhol).
  - **Domestic flights longer than most international ones.** Alaska supplies
    the only non-mainland base in the file (Steve Rogers, Honolulu — Sydney is
    a shorter flight from there than New York is) plus Seattle–Maui and
    LA–Kona, which are domestic by passport and six hours over open ocean by
    any other measure. Anything that treats "domestic" as a proxy for "short"
    gets these wrong.

- **Plus thirty-one travelers who are loyal to nothing**, spread two per city
  (three in New York) across the **fifteen most populous US cities**, named
  after Greek myth. They exist because everything above is somebody's
  loyalist, and a file of nothing but loyalists teaches a recommender that
  airline choice is a fact about a *person* rather than a fact about a
  *route*.

  | City | Travelers |
  |---|---|
  | New York (JFK / LGA / EWR) | Zeus, Hermes, Narcissus |
  | Los Angeles (LAX) | Apollo, Pandora |
  | Chicago (ORD / MDW) | Hades, Artemis |
  | Houston (IAH) | Poseidon, Circe |
  | Phoenix (PHX) | Prometheus, Persephone |
  | Philadelphia (PHL) | Athena, Odysseus |
  | San Antonio (SAT) | Ares, Medusa |
  | San Diego (SAN) | Aphrodite, Sisyphus |
  | Dallas (DFW) | Cronus, Demeter |
  | Fort Worth (DFW) | Hercules, Theseus |
  | Jacksonville (JAX) | Perseus, Chiron |
  | Austin (AUS) | Dionysus, Icarus |
  | San Jose (SJC) | Daedalus, Atlas |
  | Columbus (CMH) | Orpheus, Hera |
  | Charlotte (CLT) | Achilles, King Midas |

  - **Not one of their legs names an airline.** Every one is the
    `ANY_CARRIER` sentinel, resolved at build time from the T-100 data and
    stepped through that route's operators in volume order. Zeus's five
    New York–London trips come out on British Airways, Virgin Atlantic,
    American, Delta and JetBlue; Hera's Columbus–Orlando hops on Frontier,
    Southwest and Spirit. They average **nine or ten distinct airlines each,
    against exactly one for every loyalist above** — so "how loyal is this
    traveler" is now a number you can compute from the data rather than a
    claim this file makes.
  - **A volume floor keeps the answer to scheduled service.** Both T-100
    files include charter and business-jet operators, so an unfiltered "who
    flies this route" returns VistaJet on San Antonio–Madrid and Chartright
    on Jacksonville–Toronto. Legs need ≥1,000 international passengers or ≥5
    domestic segment records to count, and a route where nothing clears that
    is a hard failure. Four planned destinations were replaced because of it.
  - **Hobby vetoed itself.** Circe was going to be based at Houston Hobby, to
    use both of that city's airports. Every destination Hobby serves has
    exactly one operator above the floor — Southwest — so a traveler based
    there *cannot* be a non-loyalist. She flies from Intercontinental
    instead, and the attempt is left in a comment because the finding is more
    interesting than the fix.
  - **Trip shape is a property of the destination, not the traveler** (see
    the `PLACES` table): a week in Cancún, four nights in Toronto, twelve in
    Tokyo. That's what lets thirty-one itineraries be written as bare lists
    of airport codes.
  - **They don't leave on Saturdays.** Every loyalist above departs on the
    second Saturday of the month; these cycle through six days of the month,
    so day-of-week isn't a constant across the whole dataset.

- **The names are a convention, not a joke.** One category per airline, so
  which airline a traveler flies is legible from their name alone while
  reading the raw data: United → painters and architects, Delta → jazz
  musicians, American → scientists, Southwest → DC characters, Alaska →
  Marvel characters, **and no airline at all → Greek myth**. The last three
  also make the fiction unmissable, which is the point of naming these people
  at all. The pairings are deliberately **not** biographical — Marie Curie
  flies to Buenos Aires, Galileo to Orlando, Thor to Palm Springs, and
  Daedalus and Icarus live in different cities — because matching each name
  to its obvious city would imply this file knows something about real people
  (or invents something about invented ones) that it doesn't. Gender is
  lopsided but no longer nearly-uniform: the Greek group is 9 women to 22
  men, bringing the file to **15 women against 67 men**.
- **Two `id_prefix` collisions are resolved by suffixing, not renaming** —
  `PPK` for Peter Parker (Pablo Picasso holds `PP`), `BBN` for Bruce Banner
  (Billy Batson holds `BB`), `CBA` for Clint Barton (Chet Baker holds `CB`).
  `trip_id` starts with this prefix, so a duplicate would silently merge two
  people's trips.

- **Carriers come from the data, not from plausibility.** Hopper flies Cathay
  Pacific to Hong Kong and EVA Air to Taipei because those are the busiest
  operators on those routes out of SFO in the T-100 file; Picasso flies
  American to Chicago because it outflies United on BCN–ORD there (13,957
  passengers to 9,137). Everyone else flies the airline they're a loyalist
  to, on routes that airline actually operates from that hub — which is also
  what picked most of the destinations: Einstein's DFW–London and Clark
  Kent's Hobby–Cancún are the busiest international route each carrier flies
  from that airport.
- **Destination sets come from the data too.** Warhol's twelve Mexican cities
  aren't a guess at United's network — they *are* United's network from
  Houston as the T-100 file records it, in passenger order: Cancún, Mexico
  City, Los Cabos, Querétaro, Guadalajara, Puerto Vallarta, Mérida, Cozumel,
  Veracruz, Monterrey, León and San Luis Potosí. His itinerary rotates
  through that list and wraps, so fifteen trips cover all twelve and revisit
  the three busiest. Beach destinations get a week, cities a long weekend.
- **The routes are verified, not asserted — now including domestic ones.**
  Every leg must appear in T-100 data as *that carrier* flying *that origin →
  that destination*, or the script exits. Two files, because BTS splits the
  world that way:
  - `T_T100I_MARKET_ALL_CARRIER.csv` (international, ~2.6MB) carries
    passenger counts, so international legs print theirs (EWR–CDG 56,789 on
    United; SFO–HKG 103,614 on Cathay).
  - `T_T100D_SEGMENT_ALL_CARRIER.csv` (domestic, ~15MB) has **no passenger
    column** — only which carrier flew which segment in which month on which
    aircraft. That's enough for the question this check asks, which is
    whether a route is real rather than how busy it is; domestic legs print
    segment counts and months flown instead (ATL–JFK: 50 segments across 5
    months on Delta).
  Joaquín Sorolla's EWR–IAH Christmas hop and Chet Baker's entire ATL–JFK
  commute were exempted from checking until the domestic file arrived. They're
  verified now, and a domestic leg is only skipped when that file is missing
  from the checkout. Pass `--skip-route-check` to bypass both.
- **Two caveats left visible rather than smoothed away:**
  - **2020 and 2021 entries** are in most of these itineraries because the
    briefs asked for unbroken runs of years, not because those trips could
    have happened — a US traveler taking a European holiday in August 2020,
    or an Asia trip that autumn, ran into entry bans that were very much in
    force. They're the obviously fictional years in otherwise plausible
    patterns. Wes Montgomery is the deliberate exception: he doesn't fly at
    all in 2020 or 2021, which is both more realistic and a useful shape in
    its own right (a traveler who lapses and returns).
- **Everything else is fabricated:** costs (a plausible first-year baseline
  per trip type — transatlantic, transpacific, Mexico, domestic, short-haul —
  compounded ~3–5%/year and rounded to $25, so a decade of trips shows drift
  rather than identical numbers), exact dates (most departures are the second
  Saturday of the month; Christmas week is fixed 21st–28th; Pollock's are the
  1st), and ages. No randomness — rerunning produces the same file.
- **Declared home bases.** `synthetic_trips.json` carries a `declared_bases`
  map that `build_travelers.py` prefers over its own inference. Without it
  every American traveler here would be filed under Washington, D.C. (the
  American default) and Picasso under Madrid — right for someone whose home
  is unknown, wrong for someone whose home is the entire point of the
  record. All 82 come through as `base_inference: "declared"`. The site
  labels a declared base "Base" and an inferred one "Likely base".
- **They keep their names.** `build_travelers_anon.py` renames every Kaggle
  traveler after a deceased author, but passes hand-authored travelers
  through untouched with `persona_match: "authored"` — these 82 *are* the
  persona. Their `traveler_id`s are still re-slugged to that file's bare-name
  convention (`joaquin-sorolla`, not `joaquin-sorolla-american`).
- **Output:** `processed/multiple/synthetic_trips.json`, merged into
  `trips_enhanced.json` by `build_trips_enhanced.py`. Every trip in that file
  now carries `synthetic` (false for Kaggle rows), and synthetic ones also
  carry `carrier_name`, `origin_airport` and `destination_airport`.
- **Run:**
  ```
  python scripts/multiple/build_synthetic_trips.py
  python scripts/multiple/build_synthetic_trips.py --skip-route-check
  ```
  Run it **before** `build_trips_enhanced.py`.

### Author personas for travelers (`scripts/multiple/build_travelers_anon.py`)

- **Input:** `processed/multiple/travelers.json` (above).
- **What it does:** rewrites every traveler's `name` and `traveler_id`,
  replacing the source's filler names with a real, **deceased** author of
  the **same nationality and gender** — Nobel laureates and the
  best-known names first. Trips, dates, costs, ages, genders and
  nationalities are untouched; only who the trips are attributed to
  changes. `traveler_id` becomes the plain slug of the author's name
  (`jane-austen`, not `jane-austen-british`) — the nationality suffix
  existed to disambiguate sample travelers who shared a name, and real
  author names don't collide.
- **Why:** the source names are filler, and filler makes 124 cards
  unreadable — half of them are permutations of Smith/Lee/Kim, and two
  cards apart are indistinguishable at a glance. Hemingway, Woolf,
  Kawabata and Alice Munro are memorable, which is what a demo grid of
  traveler profiles needs.
- **Rules, in order:** same nationality + gender → deceased only (no
  living author is put in someone else's shoes, and it keeps the roster
  stable) → best-known first (travelers.json is sorted most-trips-first
  and assignment follows that order, so the most-travelled travelers get
  the most recognizable names) → each author used at most once.
- **Match quality is recorded in the data, not hidden.** Each traveler
  carries `persona_match`:
  - `nationality` — exact nationality and gender match. **123 of 124** on
    the current dataset.
  - `region` — an author from the same broad literary region, used where a
    nationality has too few deceased authors on record. Currently **1**:
    an Emirati traveler mapped to a Palestinian poet, since only one
    deceased Emirati woman writer is in the roster.
  - `unmapped` — nothing available; the original name is kept. Currently
    none. If this ever appears, the script prints who and why so `ROSTER`
    can be extended.
- **Nationality strings in the source are inconsistent** ("Brazil" and
  "Brazilian", "USA" and "American", "Korean"/"South Korea"/"South
  Korean"), so everything is normalized through `NATIONALITY_ALIASES`
  before lookup — which is also why the roster is keyed by demonym rather
  than by country name.
- **Judgment calls worth knowing:** author nationality is often contested
  (Kafka is filed under Czech here), and Anne Frank is deliberately
  excluded from the Dutch list — she fits the criteria on paper, but
  reassigning a murdered child's name to a fictional tourist taking beach
  holidays isn't a trade this project makes.
- **This is not anonymization.** It's a name swap in data that was
  fictional to begin with (see the traveler trips entry above). Nothing
  here protects anyone's privacy and it shouldn't be described as if it
  does. The old-name → new-name mapping is printed on each run but
  deliberately **not** written into the output file.
- **Output:** `processed/multiple/travelers_anon.json` — same shape as
  `travelers.json` plus `persona_match`. Nothing else is added: an earlier
  version also wrote a `persona_note` per author ("Nobel Prize in
  Literature, 1938") and rendered it on their page, which turned a list of
  travelers into a list of literary credentials — the ordering of `ROSTER`
  still encodes that judgment, the site just doesn't state it.
- **Consumed by:** `backend/app/data_loader.py`'s
  `resolve_travelers_path()`, which serves this file **in preference to**
  `travelers.json` whenever it exists. Deleting it is all it takes to go
  back to the raw names — that's why the choice is a file-existence check
  rather than a config flag. `/health`'s `travelers_source` reports which
  of the two is live.
- **Run:**
  ```
  python scripts/multiple/build_travelers_anon.py
  python scripts/multiple/build_travelers_anon.py --quiet   # skip the mapping printout
  ```

### Destination entropy per traveler (`scripts/multiple/compute_traveler_entropy.py`)

Reads `processed/multiple/travelers_anon.json`, writes
`processed/multiple/traveler_entropy.csv` and `.json` — one row per traveler
measuring how spread out their trips are across destinations.

    H = -sum(p_i * ln(p_i))

where `p_i` is the share of that traveler's trips going to destination `i`.
Natural log, so the units are nats.

**A destination is a destination AIRPORT.** Three cities here are served by
two airports each (New York EWR/JFK, Washington DCA/IAD, Tokyo HND/NRT), so
airport is strictly finer than city — but no single traveler currently splits
a city across two airports, so every traveler's entropy is identical either
way. Airport is the unit because the normalisation denominator counts
airports; `--by city` recomputes on cities if that ever needs checking.

**`H = 0` means two different things, and the output keeps them apart.** Chet
Baker's 0 is a finding: 53 trips, every one to JFK. A one-trip traveler's 0
is arithmetic — a single observation can only ever produce 0. `trip_count`,
`n_destinations` and `entropy_is_informative` are all in the output so the two
are never confused.

**Travelers with no airport recorded get `null`, not `0`.** Only the
hand-authored itineraries carry airports; the 124 Kaggle-sourced travelers
record a destination string and nothing else. A `0` there would assert "never
varies their destination" where the truth is "we don't know", and it would
drag down any average taken over the column.

Three normalisations are emitted. **`norm_global` is the canonical one:**

| column | formula | notes |
| --- | --- | --- |
| `norm_global` | `H / ln(K)`, K = all distinct destination airports (106, ln 4.6634) | **Canonical.** Absolute scale, comparable between any two travelers. Nobody exceeds ~0.65, so values live in the bottom two thirds. K is dataset-wide, so adding an airport rescales everyone. |
| `norm_observed` | `H / ln(k)`, k = that traveler's own destination count | The textbook version, and **undefined for 29 of the 82** — they have k = 1, so it divides by `ln(1) = 0`. Emitted as `null` rather than faked. Also saturates at 1.000 for anyone who never repeats, so a 6-destination traveler ties a 12-destination one. |
| `norm_capacity` | `H / ln(min(n_trips, K))` | Corrects for opportunity — a 4-trip traveler can't exceed `ln(4)`. 1.0 means "never repeated a destination". |

Current results: **K = 106** destination airports; 82 of 206 travelers have
airport data; **29 sit at a true zero** (single destination across 8–53
trips); the most varied is Stan Getz at **H = 3.043** over 25 destinations in
30 trips.

Verified by recomputing all 206 rows independently, and by the identity that
`H` must equal `ln(k)` exactly for a traveler with a perfectly even split —
which holds for Achilles (6 × 5 trips), Miles Davis (12 × 2) and Chet Baker
(k = 1).

Usage:

    python scripts/multiple/compute_traveler_entropy.py
    python scripts/multiple/compute_traveler_entropy.py --by city

### Traveler tags (`scripts/multiple/compute_traveler_tags.py`)

Reads `processed/multiple/travelers_anon.json`, writes
`processed/multiple/traveler_tags.csv` and `.json` — one row per traveler,
carrying a list of short labels describing a pattern that is **true of the
data as recorded**, plus the diagnostics behind each decision. Two rules so
far; everything downstream is a list of tags and doesn't know how many rules
produced them.

#### Rule 1 — airline loyalist

A traveler is tagged `"{Airline} Loyalist"` when at least **80%** of their
trips are on one airline. `--threshold` and `--min-trips` change both numbers
without editing the file.

**The denominator is trips with a recorded carrier, not all trips.** Only the
hand-authored itineraries name an airline; the 124 Kaggle-sourced travelers
record a destination string and nothing else. Counting those against the
share would drop a tag because of a gap in the source rather than because of
how someone flies. This is the same denominator the "Airlines flown" chart
states in its caption, so a 100% bar and a Loyalist chip can never disagree
on one page. **A traveler with no carrier data anywhere gets no tag and no
near-miss** — the answer is "unknown", which is not "not loyal".

**Minimum 5 carrier-recorded trips.** Two trips that happened to share an
airline are a coincidence, and 100% of 2 would otherwise outrank 85% of 40.
The floor changes nothing today (the lowest-trip qualifier has 5) but stops
the rule degenerating the moment a short itinerary is added. `below_min_trips`
marks a traveler who cleared the share and missed the floor, so "no tag" stays
separable from "not enough evidence".

Current results: **82 of 206** travelers have carrier data, **49 are tagged** —
11 Delta, 10 each Alaska / American / Southwest, 8 United.

**The share is strikingly bimodal, so the 80% is currently doing no cutting:**
49 travelers sit at exactly 100% and the next-highest is 75%. Nobody at all
lands between 80% and 100%, so any threshold from ~76% to 100% tags the same
49 people. Worth knowing before reading meaning into the exact number.

**Two intended loyalists don't get the tag, and that's the rule working.**
Pablo Picasso (3 of 4 United, 75%) and Edward Hopper (7 of 10 United, 70%)
were authored as United travelers, but BCN–ORD, SFO–HKG and SFO–TPE aren't
United routes, so `build_synthetic_trips.py` put those legs on carriers that
do fly them. The tag describes the data, not the author's intent — which is
the whole reason it's computed rather than declared.

#### Rule 2 — home hub

A traveler whose home city is a hub for exactly one airline in `AIRLINE_HUBS`
is tagged `"{Airline} Hub"`; one whose city is a hub for two or more is
tagged **`"Multi Hub"` instead of** the individual tags. The hub lists are
hand-curated (United, Delta, American and Alaska), not derived from the T-100
data — a hub is a network-design fact, not a schedule-volume ranking.

**The unit is the city, not the airport.** Every New York resident is Multi
Hub whether they fly EWR (United), JFK or LGA (Delta and American), because
the question the tag answers is "does this person have a choice of airline at
home?" — and a New Yorker does. Splitting by airport would tag three
neighbours three different ways.

**Declared bases only.** All 82 hand-authored travelers state where they live;
the other 124 have a base *inferred* from nationality by `build_travelers.py`,
and "Washington, D.C." is simply the US default — 20 travelers carry it
without the source ever saying where they live. A chip about someone's home
must not be built on a guess.

**The city table is verified, not trusted.** Every declared traveler's trips
depart from exactly one airport — that airport *is* their home airport, stated
by the data rather than by the table — so every match is checked against it
and `home_airport_is_hub` records the result. It never suppresses a tag.
Three are False today and all three are real: **Barry Allen** and **Artemis**
live in Chicago and fly Midway, **Clark Kent** lives in Houston and flies
Hobby. All three are Southwest travelers, and Southwest flies the secondary
field in both metros — they live in the hub city and use the airport the hub
airline isn't at. Anything *above* those three should be read as a table bug.

Hub results: **59 hub tags** — 20 Multi Hub (Chicago, New York, Los Angeles,
Washington D.C.), 18 American, 12 United, 5 Alaska, 4 Delta. **69 travelers
carry at least one tag of either kind.**

**The two rules are independent, and the data proves it**: travelers exist who
are loyal without living at a hub, live at a hub without being loyal, and
both. Oliver Queen lives in Denver (United's hub) and is a Southwest loyalist;
Barry Allen lives in Chicago and flies Southwest out of Midway. A hub chip
makes no claim about who someone flies.

#### Output

The API serves these on both `/api/travelers` and
`/api/travelers/{id}`; the frontend draws them as chips on the `/rec-sys`
cards and the traveler page, with **one dot per airline the tag names**, in
that airline's own brand color (`frontend/src/lib/airlineColors.ts`) — so a
Chicago Multi Hub chip (two dots) is visibly different from a New York one
(three) without spending more of a 180px card on text.

Usage:

    python scripts/multiple/compute_traveler_tags.py
    python scripts/multiple/compute_traveler_tags.py --threshold 0.9 --min-trips 10

### Country name crosswalk (`reference/country_aliases.json`)

- **Problem:** every source names countries differently — SimpleMaps says
  "United States", Michelin's scraped `location_country` says "USA" for
  some rows and "Chinese Mainland" for China, "Türkiye" instead of
  "Turkey", "Hong Kong SAR China" instead of "Hong Kong", and even leaks
  raw iso3 codes ("ARE", "THA") into the field for a handful of rows.
  Matching cities across sources by raw country string alone silently
  drops most real matches.
- **Script:** `scripts/build_country_aliases.py`. Canonical country
  names/iso2/iso3 come from the *full* SimpleMaps World Cities Database
  download (the raw ~50K-row CSV already cached at
  `raw/simplemaps/simplemaps_worldcities_basicv1.91.1.zip` by
  `fetch_tourist_cities.py` — not the trimmed `tourist_cities.json`
  subset), giving full coverage of every country SimpleMaps recognizes
  (241), not just the ones with a top-N-population city. A hand-maintained
  `EXTRA_ALIASES` dict at the top of the script adds alternate spellings
  seen in *other* sources that don't match SimpleMaps' own naming (the 9
  cases above). The script warns if `EXTRA_ALIASES` ever references an
  iso3 that isn't in the canonical list (a typo-catcher).
- **Output:** `reference/country_aliases.json`:
  ```json
  {
    "generated": "2026-07-19",
    "canonical_source": "SimpleMaps World Cities Database (Basic) -- see fetch_tourist_cities.py",
    "total_countries": 241,
    "countries": {
      "USA": {
        "canonical_name": "United States",
        "iso2": "US",
        "aliases": ["u.s.a.", "united states", "united states of america", "us", "usa"]
      },
      ...
    }
  }
  ```
  Aliases are stored casefolded/pre-normalized for direct lookup.
- **Run:**
  ```
  python scripts/build_country_aliases.py
  ```
  No network needed — reads the already-cached SimpleMaps zip. Run once
  after `fetch_tourist_cities.py` has been run at least once (to populate
  that cache), and rerun whenever `EXTRA_ALIASES` gets a new entry.
- **Verified for real** (rare for this project — no sandbox network
  restriction applies here, since it only reads a local cached file):
  ran end-to-end, produced 241 countries, and all 9 `EXTRA_ALIASES`
  entries were spot-checked against the real canonical list.

### `scripts/country_lookup.py` — shared normalization helper

- **What it does:** a small importable module (not a fetch script) built
  on top of `country_aliases.json`. `normalize_country(name)` returns the
  canonical iso3 for any country string, or `None` if unrecognized
  (handles `None`/NaN input safely). `report_unmapped(values)` takes any
  iterable of country strings and returns the distinct ones that don't
  resolve — the diagnostic tool for onboarding a new source.
- **CLI mode** — scan a CSV column for country strings that don't
  resolve yet:
  ```
  python scripts/country_lookup.py ../processed/multiple/michelin_restaurants.csv --column location_country
  ```
  Run this against any new source's country column before joining it to
  other data. If it reports unmapped strings, add them to `EXTRA_ALIASES`
  in `build_country_aliases.py` (mapped to the correct iso3) and rerun
  that script to regenerate `country_aliases.json`. Verified for real
  against `processed/multiple/michelin_restaurants.csv`: zero unmapped strings
  (547 rows have a blank `location_country` outright — Singapore, Dubai,
  Abu Dhabi, Macau, and Luxembourg all appear as a bare city with no
  ", Country" suffix in the source `Location` field, since the city
  *is* the country/territory — these are handled separately as a
  city-name → country lookup, not a country-alias problem).
- **Import usage:**
  ```python
  from country_lookup import normalize_country
  normalize_country("USA")              # -> "USA"
  normalize_country("Chinese Mainland")  # -> "CHN"
  normalize_country("nonsense")          # -> None
  ```

### City name crosswalk (`reference/city_aliases.json`)

- **Problem:** the same genuine name-variant issue as the country
  crosswalk above, but for cities — Seville vs Sevilla, Quebec vs Quebec
  City, Antwerpen vs Antwerp, etc. Unlike countries, there's no "full
  canonical list" to build this against (that would mean pulling in all
  ~50K SimpleMaps cities); this registry is entirely hand-maintained,
  built the same way `EXTRA_ALIASES` was for countries — by scanning
  `diff_michelin_vs_tourist_cities.py`'s "missing" output for a
  near-miss.
- **Script:** `scripts/build_city_aliases.py`. A hand-maintained
  `CITY_ALIASES` dict at the top of the script maps `(michelin city
  spelling, iso3) -> tourist_cities.json spelling`. Add a new entry there
  and rerun the script whenever a fresh diff run turns up another
  variant.
- **Output:** `reference/city_aliases.json`, keyed by iso3 then by the
  alias spelling (casefolded) -> canonical spelling (casefolded):
  ```json
  {
    "generated": "2026-07-20",
    "total_aliases": 19,
    "cities": {
      "ESP": {
        "seville": "sevilla",
        "alacant": "alicante",
        ...
      },
      ...
    }
  }
  ```
- **Run:**
  ```
  python scripts/build_city_aliases.py
  ```
  No network needed — entirely hand-maintained data, no source file to
  read.

### `scripts/city_lookup.py` — shared normalization helper

- **What it does:** mirrors `country_lookup.py`. `resolve_city_alias(city,
  iso3)` returns the canonical `tourist_cities.json` spelling (casefolded)
  for a `(city, iso3)` pair, or `None` if no alias is registered — used by
  `diff_michelin_vs_tourist_cities.py` instead of an inline dict, so the
  alias list can be maintained as data (`city_aliases.json`) rather than
  code.
- **Import usage:**
  ```python
  from city_lookup import resolve_city_alias
  resolve_city_alias("Seville", "ESP")      # -> "sevilla"
  resolve_city_alias("Nonexistent", "ESP")  # -> None
  ```

### `scripts/diff_michelin_vs_tourist_cities.py` — which Michelin cities aren't tracked yet

- **What it does:** compares `processed/multiple/michelin_restaurants.csv` against
  `reference/tourist_cities.json` and reports which Michelin (city,
  country) pairs have no match in the tourist cities list — a candidate
  list for expanding `ADDITIONAL_CITIES` in `fetch_tourist_cities.py`, and
  a sanity check on how much Michelin coverage the current
  `TOP_N_CITIES_BY_POPULATION` cutoff actually captures.
- **Matching logic** (see the script's docstring for the full version):
  - Country strings normalized to iso3 via `country_lookup.normalize_country()`.
  - City strings matched against **both** `tourist_cities.json`'s `city`
    and `city_ascii` fields, not just one — Michelin's own spelling is
    inconsistent about diacritics. It drops macrons for Japanese cities
    ("Kyoto", not "Kyōto" — only matches `city_ascii`) but keeps accents
    for others ("São Paulo", not "Sao Paulo" — only matches `city`). An
    earlier version of this check matched `city_ascii` only, which
    silently produced false "missing" results for São Paulo, Montréal,
    and every other accented city Michelin spells with the accent intact.
  - A trailing US two-letter state-code suffix is stripped from the city
    side if still present.
  - 5 Michelin `Location` values are a bare city name with no
    ", Country" suffix, because the city *is* the country/territory
    (Singapore, Dubai, Abu Dhabi, Macau, Luxembourg) — handled via a
    small `CITY_ONLY_COUNTRY` lookup in the script rather than
    `normalize_country()`.
  - City name aliases: a hand-maintained list of genuine name variants
    between the two sources — not diacritics, not a suffix rule, just a
    different name for the same place. Lives in `reference/city_aliases.json`
    (built from `CITY_ALIASES` in `build_city_aliases.py`, resolved at
    runtime via `city_lookup.resolve_city_alias()`) — this mirrors the
    `country_aliases.json` / `country_lookup.py` pattern used for
    countries. Found by manually scanning the top of the "missing"
    output and checking `tourist_cities.json` for a near-miss, the same
    way `EXTRA_ALIASES` was built for countries. Confirmed so far:
    Seville↔Sevilla, Québec↔Quebec City, Antwerpen↔Antwerp, Frankfurt on
    the Main↔Frankfurt, Hsinchu County/Hsinchu City↔Hsinchu,
    Alacant↔Alicante, Cebu↔Cebu City, Taguig - Metro Manila↔Taguig City,
    Dublin City↔Dublin, City of Bristol↔Bristol. There's no general rule
    that catches these (unlike the diacritic/suffix cases above) — add
    new ones to `CITY_ALIASES` in `build_city_aliases.py` and rerun it
    as they turn up when scanning future runs.
- **Output:** `processed/michelin_cities_missing_from_tourist_cities.csv`
  — `Rank`, `City`, `Country (ISO3)`, `Restaurant Count`, sorted by
  restaurant count descending.
- **Run:**
  ```
  python scripts/diff_michelin_vs_tourist_cities.py
  ```
- **Latest real run** (`tourist_cities.json` at 3062 cities, 19 city
  alias entries applied): 336 of 6,094 distinct Michelin (city, country)
  pairs match; 5,758 don't. Not a data bug — `tourist_cities.json` is a
  curated top-N-by-population list plus manual additions, while Michelin
  covers many well-known but smaller/non-top-N destinations that don't
  crack the population cutoff. The output CSV is the candidate list for
  `ADDITIONAL_CITIES` if any of the missing entries should be
  force-included regardless of population. Manually scanning the top
  ~30-50 rows of a fresh run for further name-variant aliases (like the
  `city_aliases.json` entries above) before trusting the full "missing"
  count is recommended — the automated matching only catches diacritics
  and known suffix patterns, not arbitrary rename variants.
- **Cities confirmed absent from SimpleMaps' Basic tier under any
  spelling tried** (so they can't be added to `ADDITIONAL_CITIES` at
  all, not a matching problem): Cardiff, Miguel Hidalgo (a Mexico City
  borough), Nonthaburi, Positano, Uccle (a Brussels municipality),
  Courchevel, Saint Moritz, Lech am Arlberg, Saint-Tropez, Megève, and
  the New Zealand Queenstown (only a South African and a Tasmanian
  Queenstown exist in the Basic tier). Monaco similarly has zero city
  entries in the Basic tier at all. If any of these matter for the
  scoring model, they need a different source or a manual lat/long
  entry — `MANUAL_CITIES` in `fetch_tourist_cities.py` now covers this
  case: New Zealand's Queenstown is hand-entered there (coordinates and
  population from Stats NZ's 30 June 2025 subnational estimate for the
  Queenstown urban area) since it's genuinely absent from the source,
  not just an `ADDITIONAL_CITIES` lookup miss.
- **Name-variant additions**: several `ADDITIONAL_CITIES` entries use
  SimpleMaps' shorter/different spelling rather than Michelin's exact
  string, with a matching entry in `city_aliases.json` added so the diff
  still recognizes them: `Puebla` (Michelin: "Heróica Puebla de
  Zaragoza"), `Las Palmas` (Michelin: "Las Palmas de Gran Canaria"),
  `Donostia` (Michelin: "Donostia / San Sebastián"), `Brighton`
  (Michelin: "Brighton and Hove"), `Phangnga` (Michelin: "Phang-Nga"),
  `Les Sables-d'Olonne` (Michelin: "Les Sables d'Olonne", with a curly
  apostrophe and no hyphen in the source), and `Glasgow` (Michelin:
  "Glasgow City").
