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

With the venv active, run the fetch/build scripts from `data/` to populate
`data/reference/` and `data/processed/`. See
[`data/PULLING_DATA.md`](data/PULLING_DATA.md) for the full list of scripts,
what each one pulls/writes, and per-source notes.

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
thirteen more countries scored on their own latest-12-months only —
Australia, New Zealand, Japan, Costa Rica, Canada, Chile, Mexico,
Maldives, Indonesia, Brazil, Colombia, Paraguay, and Uruguay — into
`data/processed/PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`: one row per
(country, month) with `PEAK_RATIO`, how busy that month is relative to
the country's own peak month (0–1). A candidate seasonality signal by
country — currently 47 countries, 541 rows. The non-Eurostat countries
each use a different underlying signal (visitor arrivals, hotel
occupancy %, domestic air passengers, etc.), so `PEAK_RATIO` is only
comparable *within* a country's own row, not in magnitude across
countries — see `data/README.md` for the full per-country breakdown and
how Eurostat's partial-year coverage is handled.

```
python scripts/build_usd_purchasing_power_dataset.py
```

Joins the World Bank's Price Level Index (`PA.NUS.GDP.PLI`, already
pulled by `fetch_worldbank_indicator.py`) onto the same 47 countries,
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
`data/processed/peak_tourism_interactive_chart.html`. Unlike the static
matplotlib version in `notebooks/peak_tourism_months_exploration.ipynb`,
the viewer can change how it's drawn live in the browser: size by number
of passengers/visitors, Michelin-starred restaurant count, the peak ratio
itself, or USD purchasing power; order countries alphabetically, by
capital latitude, or by USD purchasing power; ascending or descending.
Color always encodes `PEAK_RATIO` and the hover tooltip always shows all
four metrics no matter which one is driving marker size. Renders via
Plotly.js from a CDN rather than the `plotly` Python package, so opening
the file needs nothing but a browser and generating it needs no new
dependency — see `data/README.md` for the full breakdown of each control.

## TODO

- [ ] Find a public data source for visa requirements by passport (e.g. Mexico passport: 90-day visa-free to Germany, visa required for Gambia). Needed to score trip opportunities by whether a traveler's passport can actually make the trip, not just whether the destination looks good.
- [ ] Get Maldives tourism statistics via the Maldives Monetary Authority API: https://database.mma.gov.mv/api/docs
- [ ] Begin research on Safety or Crime Statistics by Country (specifically, where to pull data)
- [ ] Still missing many countries: United States, China, United Kingdom, United Arab Emirates, South Korea, Georgia, Philippines and more.
- [ ] Consider how to handle territories (US: Puerto Rico, Guam, etc, France: French Polynesia, French Guiana, etc. UK: Falkland Islands)
- [ ] Figure out - UK - Split up into it's 4 Countries + Overseas territories?

## Data attributions

- City data from the [SimpleMaps World Cities Database](https://simplemaps.com/data/world-cities), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Weather data from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5/ERA5-Land reanalysis, CC BY 4.0).
- Restaurant data from [michelin-my-maps](https://github.com/ngshiheng/michelin-my-maps) (MIT licensed), scraped from the [MICHELIN Guide](https://guide.michelin.com/en/restaurants) for research purposes.
- Economic indicators (GDP deflator, exports % of GDP, PPP conversion factor, price level index) from [The World Bank](https://data.worldbank.org), via the [Data360 API](https://data360api.worldbank.org), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Air passenger traffic data from [Eurostat](https://ec.europa.eu/eurostat) (dataset `TTR00012`, sourced from `AVIA_PAOC`), reused under the European Commission's [CC BY 4.0 reuse policy](https://ec.europa.eu/eurostat/en/help/copyright-notice).
- Tourism accommodation data (EMAT) from Chile's [Instituto Nacional de Estadísticas (INE)](https://www.ine.gob.cl/estadisticas-por-tema/comercio-y-servicios/actividad-mensual-del-turismo).
- Domestic air passenger data from Mexico's [Agencia Federal de Aviación Civil (AFAC)](https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404), Monthly Bulletin of Operational Statistics.
