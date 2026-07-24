# when-where
A travel discovery app that recommends the best destinations for your dates based on weather, seasonality, crowds, exchange rates, and interests like hiking, beaches, food, nightlife, and culture.

## Setup

One Python virtual environment for the whole project, at the repo root:

```
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Activate it (`source venv/bin/activate`) before running anything in
`data/` or `notebooks/`.

## Pulling data

With the venv active:

```
cd data
python scripts/multiple/fetch_latest_by_country.py
```

This pulls the latest available value of every World Bank indicator
registered in `data/reference/worldbank_metrics.json` (GDP deflator,
exports % of GDP, PPP conversion factor, price level index), for every
country, into `data/processed/worldbank_<code>_<year>_by_country.json`.
These output files are gitignored, so run this after a fresh clone before
anything downstream expects them.

To add a new World Bank indicator to the pipeline, add an entry to
`data/reference/worldbank_metrics.json` — no script changes needed. See
`data/README.md` for the full pipeline, caching behavior, and per-source
details.

```
python scripts/multiple/fetch_tourist_cities.py
```

Downloads the free SimpleMaps world cities database (cached in
`data/raw/simplemaps/` after the first run) and writes
`data/reference/tourist_cities.json` — the top N cities worldwide by
population plus a manually curated list of extra cities, with lat/long.
Edit `TOP_N_CITIES_BY_POPULATION` and `ADDITIONAL_CITIES` at the top of
the script to change which cities are included.

```
python scripts/multiple/fetch_weather_normals.py --limit 20   # pilot first
python scripts/multiple/fetch_weather_normals.py              # full run, resumable
```

Pulls one year of daily weather per city from Open-Meteo and writes
`data/processed/weather_normals_<year>_by_city.json` — a monthly climate
normal (avg high/low temp, precipitation, daylight, wind) per city. Free
API budget limits mean a full ~5000-city run may need more than one
sitting; the script checkpoints and skips cities already fetched, so it's
safe to interrupt and rerun. See `data/README.md` for the reasoning
behind using one year instead of a multi-year average.

```
python scripts/multiple/fetch_michelin_restaurants.py
python scripts/multiple/fetch_michelin_restaurants.py --force-fallback   # skip kagglehub
```

Pulls the MICHELIN Guide restaurants dataset (name, location, cuisine,
price, award tier) and writes `data/processed/michelin_restaurants.csv`.
Tries Kaggle via `kagglehub` first (needs Kaggle API credentials — see
`data/README.md`), and automatically falls back to the same dataset's
CSV on GitHub if that fails for any reason, no credentials needed.

```
python scripts/europe/fetch_eurostat_dataset.py
python scripts/europe/fetch_eurostat_dataset.py TTR00016 --filter tra_cov=TOTAL
```

Pulls a Eurostat dataset via their Statistics API (decoding its JSON-stat
hypercube format into a tidy CSV) and writes
`data/processed/eurostat_<slug><suffix>.csv`. Defaults to `TTR00012` —
yearly air passenger traffic by country — for 2025; its monthly sibling
`TTR00016` is the one actually used for scoring (a per-month signal fits
the monthly-destination-score approach better than one number a year).
Leave `--start-period`/`--end-period` off entirely to just get whatever
Eurostat has currently published (`TTR00016` doesn't cover any full
calendar year yet, so forcing a Jan–Dec window silently drops months).
See `data/README.md` for the full JSON-stat decoding details and the
differences between the two datasets.

```
python scripts/asia/fetch_japan_tourism_indicators.py
python scripts/asia/fetch_japan_tourism_indicators.py --since 2024-01
```

Pulls two Japan e-Stat Statistics Dashboard indicators (no API key
needed) — monthly foreign-national border entries and monthly
foreign-visitor accommodation guest-nights, both nationwide — and joins
them into `data/processed/japan_tourism_indicators_by_month.csv`
(`COUNTRY, COUNTRY_NAME, MONTH, NUM_ENTRIES, NUM_GUEST_NIGHTS`). Defaults
to January 2025 onward. See `data/README.md` for why entries is a proxy
rather than an exact "visitor arrivals" match, and for the prefecture-
level guest-nights option if destination-level granularity is wanted
later.

```
python scripts/americas/fetch_chile_ine_tourism_accommodation.py               # Cuadro 1 -- overnight stays, total
python scripts/americas/fetch_chile_ine_tourism_accommodation.py --all-tables  # every Cuadro 1-33
python scripts/americas/fetch_chile_ine_tourism_accommodation.py --list-tables # print all 34 table titles
```

Pulls Chile's INE (Instituto Nacional de Estadísticas) monthly tourism
accommodation survey (EMAT) and writes
`data/processed/americas/chile_ine_tourism_monthly.csv` (long format:
`table_number, table_name, level, region, destino_turistico, ref_date,
value`) plus a region/destino-turístico/comuna reference table at
`data/processed/americas/chile_ine_destino_turistico_comunas.csv`.
Covers July 2016 to present, region and destino-turístico level. Defaults
to Table 1 (overnight stays, total) — see `data/README.md` for why
overnight stays is the recommended indicator over arrivals for this
project's scoring purposes.
Source: https://www.ine.gob.cl/estadisticas-por-tema/comercio-y-servicios/actividad-mensual-del-turismo

```
python scripts/americas/build_mexico_international_passengers_dataset.py
```

Writes `data/processed/americas/mexico_international_passengers_monthly.csv`
(`ref_date`, `mexican_airlines_millions`, `foreign_airlines_millions`,
`passengers_millions`, `passengers`) — 12 months of 2025 international
scheduled-operations air passenger totals for Mexico (Mexican + foreign
airlines combined). Unlike every other script above, there's no live
fetch here: AFAC (Mexico's civil aviation authority) publishes this as
two separate charts in its Monthly Bulletin of Operational Statistics,
not a downloadable table, so the values are hand-transcribed from each
chart's own data-point labels and summed per month (cross-checked
against a text extraction of the source PDF — see `data/README.md`).
An earlier version of this dataset used the bulletin's DOMESTIC
passengers chart instead (`build_mexico_domestic_passengers_dataset.py`,
still present but no longer used for scoring) — corrected to this
international series for consistency with the rest of the peak tourism
indicator below.
Source: https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404

```
python scripts/build_country_aliases.py
```

Builds `data/reference/country_aliases.json` — a canonical iso3-keyed
country registry with alternate spellings (USA vs United States, Chinese
Mainland vs China, Türkiye vs Turkey, etc.), so different sources' country
strings can be normalized before joining. Import `normalize_country()`
from `data/scripts/country_lookup.py` to use it in new scripts; run that
module's CLI mode against a new source's country column to check for
unmapped strings first. See `data/README.md` for the full list of known
aliases and how to extend it.

```
python scripts/build_city_aliases.py
```

Builds `data/reference/city_aliases.json` — the same idea as
`country_aliases.json`, but for genuine city-name variants between
sources (Seville vs Sevilla, Quebec vs Quebec City, Antwerpen vs
Antwerp). Import `resolve_city_alias()` from `data/scripts/city_lookup.py`
to use it. Entirely hand-maintained, since there's no canonical "every
city name variant" list to build from — add a new entry as one turns up.

```
python scripts/diff_michelin_vs_tourist_cities.py
```

Diagnostic script: compares `data/processed/michelin_restaurants.csv`
against `data/reference/tourist_cities.json` and reports which Michelin
(city, country) pairs have no match — a candidate list for expanding
`ADDITIONAL_CITIES` in `fetch_tourist_cities.py`, and a way to check how
much Michelin coverage the current population cutoff actually captures.
Writes `data/processed/michelin_cities_missing_from_tourist_cities.csv`.

## Scoring

```
python scripts/compute_monthly_scores.py
```

Turns `data/processed/weather_normals_<year>_by_city.json` into
`data/processed/monthly_scores_<year>_by_city.json` — six simple,
transparent per-month scores per city (rain frequency, rain hours,
sunshine hours, pass/fail high/low temperature flags, and a wind
intensity score referenced against the Beaufort scale), each a plain
formula documented in `data/README.md`. Rule-based by design, per the
project's approach — not combined into one overall number here, since
that weighting should depend on the traveler profile.

```
python scripts/compute_peak_tourism_indicator.py
```

Combines the Eurostat monthly air-passenger CSV (full history) with
twelve more countries scored on their own latest-12-months only —
Australia, New Zealand, Japan, Costa Rica, Canada, Chile, Mexico,
Maldives, Indonesia, Brazil, Colombia, and Paraguay — into
`data/processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`: one row per
(country, month) with `PEAK_RATIO`, how busy that month is relative to
the country's own peak month (0–1). A candidate seasonality signal by
country — currently 46 countries, 529 rows. The non-Eurostat countries
each use a different underlying signal (visitor arrivals, hotel
occupancy %, domestic air passengers, etc.), so `PEAK_RATIO` is only
comparable *within* a country's own row, not in magnitude across
countries — see `data/README.md` for the full per-country breakdown and
how Eurostat's partial-year coverage is handled.

```
python scripts/build_usd_purchasing_power_dataset.py
```

Joins the World Bank's Price Level Index (`PA.NUS.GDP.PLI`, already
pulled by `fetch_worldbank_indicator.py`) onto the same 46 countries,
matched by name rather than by the Eurostat-style codes in
`PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv` (a couple of those, like `EL` for
Greece, don't match standard ISO). Writes
`data/processed/usd_purchasing_power_by_country.csv`:
`USD_PURCHASING_POWER = 100 / PRICE_LEVEL_INDEX`, literally what $1's
real buying power is worth in US-dollar-equivalent terms in that country
— 1.50 means $1 there buys what $1.50 would buy in the US, 0.80 means it
buys what $0.80 would. No exchange rate needed, since PLI is already
normalized against the US dollar.

```
python scripts/build_peak_tourism_interactive_chart.py
```

Turns `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv` into an interactive,
hoverable version of the peak-tourism scatterplot —
`data/processed/peak_tourism_interactive_chart.html`. Same encoding as
the static matplotlib version in
`notebooks/peak_tourism_months_exploration.ipynb` (country sorted
north-to-south by capital latitude, color = `PEAK_RATIO`, size = each
row's underlying volume signal, peak months outlined), plus hover
tooltips with the country, month, peak ratio, and raw value. Renders via
Plotly.js from a CDN rather than the `plotly` Python package, so opening
the file needs nothing but a browser and generating it needs no new
dependency.

## TODO

- [ ] Find a public data source for visa requirements by passport (e.g. Mexico passport: 90-day visa-free to Germany, visa required for Gambia). Needed to score trip opportunities by whether a traveler's passport can actually make the trip, not just whether the destination looks good.
- [ ] Get Maldives tourism statistics via the Maldives Monetary Authority API: https://database.mma.gov.mv/api/docs

## Data attributions

- City data from the [SimpleMaps World Cities Database](https://simplemaps.com/data/world-cities), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Weather data from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5/ERA5-Land reanalysis, CC BY 4.0).
- Restaurant data from [michelin-my-maps](https://github.com/ngshiheng/michelin-my-maps) (MIT licensed), scraped from the [MICHELIN Guide](https://guide.michelin.com/en/restaurants) for research purposes.
- Economic indicators (GDP deflator, exports % of GDP, PPP conversion factor, price level index) from [The World Bank](https://data.worldbank.org), via the [Data360 API](https://data360api.worldbank.org), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Air passenger traffic data from [Eurostat](https://ec.europa.eu/eurostat) (dataset `TTR00012`, sourced from `AVIA_PAOC`), reused under the European Commission's [CC BY 4.0 reuse policy](https://ec.europa.eu/eurostat/en/help/copyright-notice).
- Tourism accommodation data (EMAT) from Chile's [Instituto Nacional de Estadísticas (INE)](https://www.ine.gob.cl/estadisticas-por-tema/comercio-y-servicios/actividad-mensual-del-turismo).
- Domestic air passenger data from Mexico's [Agencia Federal de Aviación Civil (AFAC)](https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404), Monthly Bulletin of Operational Statistics.
