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
python scripts/fetch_latest_by_country.py
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
python scripts/fetch_tourist_cities.py
```

Downloads the free SimpleMaps world cities database (cached in
`data/raw/simplemaps/` after the first run) and writes
`data/reference/tourist_cities.json` — the top N cities worldwide by
population plus a manually curated list of extra cities, with lat/long.
Edit `TOP_N_CITIES_BY_POPULATION` and `ADDITIONAL_CITIES` at the top of
the script to change which cities are included.

```
python scripts/fetch_weather_normals.py --limit 20   # pilot first
python scripts/fetch_weather_normals.py              # full run, resumable
```

Pulls one year of daily weather per city from Open-Meteo and writes
`data/processed/weather_normals_<year>_by_city.json` — a monthly climate
normal (avg high/low temp, precipitation, daylight, wind) per city. Free
API budget limits mean a full ~5000-city run may need more than one
sitting; the script checkpoints and skips cities already fetched, so it's
safe to interrupt and rerun. See `data/README.md` for the reasoning
behind using one year instead of a multi-year average.

```
python scripts/fetch_michelin_restaurants.py
python scripts/fetch_michelin_restaurants.py --force-fallback   # skip kagglehub
```

Pulls the MICHELIN Guide restaurants dataset (name, location, cuisine,
price, award tier) and writes `data/processed/michelin_restaurants.csv`.
Tries Kaggle via `kagglehub` first (needs Kaggle API credentials — see
`data/README.md`), and automatically falls back to the same dataset's
CSV on GitHub if that fails for any reason, no credentials needed.

```
python scripts/fetch_eurostat_dataset.py
python scripts/fetch_eurostat_dataset.py TTR00016 --filter tra_cov=TOTAL
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

## Data attributions

- City data from the [SimpleMaps World Cities Database](https://simplemaps.com/data/world-cities), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Weather data from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5/ERA5-Land reanalysis, CC BY 4.0).
- Restaurant data from [michelin-my-maps](https://github.com/ngshiheng/michelin-my-maps) (MIT licensed), scraped from the [MICHELIN Guide](https://guide.michelin.com/en/restaurants) for research purposes.
- Economic indicators (GDP deflator, exports % of GDP, PPP conversion factor, price level index) from [The World Bank](https://data.worldbank.org), via the [Data360 API](https://data360api.worldbank.org), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Air passenger traffic data from [Eurostat](https://ec.europa.eu/eurostat) (dataset `TTR00012`, sourced from `AVIA_PAOC`), reused under the European Commission's [CC BY 4.0 reuse policy](https://ec.europa.eu/eurostat/en/help/copyright-notice).
