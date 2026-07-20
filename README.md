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
