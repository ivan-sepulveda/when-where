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
  `michelin_cities_missing_from_tourist_cities.csv`) — those scripts read
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

### Peak tourism indicator (`scripts/compute_peak_tourism_indicator.py`)

- **What it does:** reads the Eurostat monthly air-passenger CSV
  (`processed/europe/eurostat_passengers_transported_by_country_monthly_*.csv`,
  `tra_cov=TOTAL` only) and computes, per country per calendar month, how
  busy air travel is relative to that country's own peak month — a
  0.0–1.0 seasonality ratio. Not machine-learned, just:
  ```python
  FRANCE = df[df["geo"] == "FR"]
  FR_MAX_PASSENGERS = FRANCE["value"].max()
  PEAK_RATIO = FRANCE["value"] / FR_MAX_PASSENGERS
  ```
  applied per country, with EU/euro-area aggregate `geo` codes
  (`EU27_2020`, `EA21`, `EA20`, `EA19`) dropped first since they aren't
  countries.
- **Why it's here:** a candidate seasonality signal for the scoring
  model — e.g. a destination whose air travel peaks in August is
  probably at its most crowded/expensive then, all else equal. Country-
  level only, same caveat as the Eurostat source itself.
- **Handling the source's partial year coverage:** `TTR00016` doesn't
  cover one full calendar year yet (see the Eurostat section above), so
  four months (Feb–May, as of this writing) have two years of data each
  and the rest have one. Where a month has two years available, only the
  MORE RECENT one is kept for that month — so the output is always
  exactly one row per (country, month), never two. `PEAK_RATIO` itself is
  still scaled against the country's true max across *all* fetched
  history (both years), not just the deduplicated rows, so a month whose
  older year got dropped can still correctly read as less than 1.0
  relative to a genuine peak that happened to fall in the dropped year.
  `SOURCE_YEAR` in the output records which year's observation was kept,
  for transparency.
- **Data gaps are real, not a bug:** not every country reports every
  month — as fetched, per-country row counts in the output range from 5
  (Türkiye) to 12 (most countries); France, Belgium, Malta, and Estonia
  currently sit at 10 (missing Dec 2025 and Jan–May 2026 entirely, not
  just a dedup artifact). Verified by checking the raw source CSV
  directly, not assumed.
- **Output:** `processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`
  (`ALL_CAPS` filename by request, unlike this project's other
  `processed/` outputs) — columns `COUNTRY` (Eurostat `geo` code),
  `MONTH` (integer 1–12), `PEAK_RATIO`, plus `COUNTRY_NAME`,
  `SOURCE_YEAR`, and `PASSENGERS` (the raw value behind the ratio) for
  traceability. One row per (`COUNTRY`, `MONTH`). Current run: 385 rows,
  34 countries.
- **Run:**
  ```
  python scripts/compute_peak_tourism_indicator.py
  python scripts/compute_peak_tourism_indicator.py --tra-cov NAT   # score national-only traffic instead of total
  ```
- **Verified for real:** run end-to-end against the actual
  `eurostat_passengers_transported_by_country_monthly_TOTAL.csv` (this
  sandbox can read locally-mounted files freely, unlike live Eurostat/etc.
  API calls). Cross-checked France's full `value_scaled` series
  (computed independently, the same way as the docstring's example)
  against the script's output row-by-row — exact match, including the
  August 2025 peak at `PEAK_RATIO = 1.0`. Also spot-checked Austria's
  Feb–May rows to confirm the "most recent year wins" dedup rule: 2026
  was correctly used for Feb/Mar/Apr (present in both years), 2025 for
  May (present in 2025 only).

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
