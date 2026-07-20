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
  python scripts/fetch_tourist_cities.py
  python scripts/fetch_tourist_cities.py --force-download   # bypass the raw/ cache
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

### Open-Meteo — monthly weather normals (`scripts/fetch_weather_normals.py`)

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
- **Output:** `processed/weather_normals_<year>_by_city.json`:
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
  python scripts/fetch_weather_normals.py --limit 20   # pilot a small batch first
  python scripts/fetch_weather_normals.py              # full run (resumable — safe to re-run/interrupt)
  python scripts/fetch_weather_normals.py --force       # re-fetch cities already in the output
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

- **What it does:** reads `processed/weather_normals_<year>_by_city.json`
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

### Michelin Guide restaurants (`scripts/fetch_michelin_restaurants.py`)

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
  - `processed/michelin_restaurants.csv` — same rows, plus the two
    `location_city`/`location_country` columns and the boolean `GreenStar`.
- **Run:**
  ```
  python scripts/fetch_michelin_restaurants.py
  python scripts/fetch_michelin_restaurants.py --force-fallback
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
  python scripts/country_lookup.py ../processed/michelin_restaurants.csv --column location_country
  ```
  Run this against any new source's country column before joining it to
  other data. If it reports unmapped strings, add them to `EXTRA_ALIASES`
  in `build_country_aliases.py` (mapped to the correct iso3) and rerun
  that script to regenerate `country_aliases.json`. Verified for real
  against `processed/michelin_restaurants.csv`: zero unmapped strings
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

- **What it does:** compares `processed/michelin_restaurants.csv` against
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
