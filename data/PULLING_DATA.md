# Pulling data

With the venv active (see the top-level `README.md` for setup):

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
python scripts/europe/fetch_eurostat_dataset.py CRIM_OFF_CAT --time 2023 2024
python scripts/europe/fetch_eurostat_dataset.py CRIM_GEN_REG --time 2023 --filter unit=P_HTHAB
```

Same script, two crime datasets. `CRIM_OFF_CAT` is police-recorded
offences by offence category, country-level (41 countries, 25 ICCS
categories) — small enough to pull several years at once. `CRIM_GEN_REG`
is the NUTS3-region breakdown, but only for 7 offence categories
(intentional homicide, assault, robbery, burglary, burglary of private
residential premises, theft, theft of a motorized land vehicle) — a
useful subset for a personal-safety signal. It's much bigger (~1500
regions), so pull one or a few years at a time rather than the full
2008–2024 history, and consider `--filter unit=P_HTHAB` to get only the
per-100k-inhabitants rate (population-normalized, more comparable across
regions of different sizes than raw counts). Writes
`data/processed/europe/eurostat_crime_offences_by_country<suffix>.csv`
and `data/processed/europe/eurostat_crime_offences_by_nuts3_region<suffix>.csv`.
See `data/README.md` for the full ICCS category list, unit meanings, and
cross-country comparability caveats.

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
