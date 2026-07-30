# when-where
Recommends destinations based on your dates or dates based on your destination. Datasets include Michelin restaurants, Price Level Indices, and more.

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

With the venv active, run the scoring scripts from `data/` to turn pulled
data into weather scores, the peak-tourism seasonality indicator, USD
purchasing power, and the interactive chart. See
[`data/SCORING.md`](data/SCORING.md) for the full list of scripts, what
each one computes/writes, and per-source notes.

## App

`frontend/` (React + Vite, deployed to `travel.iesepulveda.com`) and
`backend/` (FastAPI) are the first pieces that turn this data into
something a user can query — `GET /api/destinations/top10` ranks
countries for a given date range using the scoring output above, plus a
weather score resolved against those specific dates. See
[`frontend/README.md`](frontend/README.md) and
[`backend/README.md`](backend/README.md).

## TODO

- [ ] Find a public data source for visa requirements by passport (e.g. Mexico passport: 90-day visa-free to Germany, visa required for Gambia). Needed to score trip opportunities by whether a traveler's passport can actually make the trip, not just whether the destination looks good.
- [ ] Get Maldives tourism statistics via the Maldives Monetary Authority API: https://database.mma.gov.mv/api/docs
- [x] Begin research on Safety or Crime Statistics by Country (specifically, where to pull data) — EU covered via Eurostat `CRIM_OFF_CAT`/`CRIM_GEN_REG`; still need a non-EU source (e.g. UNODC) for global coverage.
- [ ] Still missing many countries: United States, China, United Kingdom, United Arab Emirates, South Korea, Georgia, Philippines and more.
- [ ] Consider how to handle territories (US: Puerto Rico, Guam, etc, France: French Polynesia, French Guiana, etc. UK: Falkland Islands)
- [ ] Figure out - UK - Split up into it's 4 Countries + Overseas territories?
- [ ] User IP Address recognition (country-only, not persisted; use country.is)
- [x] Pull UNESCO World Heritage Sites data — done (`scripts/multiple/fetch_unesco_world_heritage_sites.py`). License terms are unclear/restrictive (see `data/README.md`) — confirm redistribution rights with UNESCO/WHC before this goes beyond personal/internal use.
- [ ] Fix `npm warn deprecated whatwg-encoding@3.1.1` in `frontend/` — switch to `@exodus/bytes` (transitive dep, likely via jsdom).

## Data attributions

- City data from the [SimpleMaps World Cities Database](https://simplemaps.com/data/world-cities), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Weather data from the [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api) (ERA5/ERA5-Land reanalysis, CC BY 4.0).
- Restaurant data from [michelin-my-maps](https://github.com/ngshiheng/michelin-my-maps) (MIT licensed), scraped from the [MICHELIN Guide](https://guide.michelin.com/en/restaurants) for research purposes.
- Economic indicators (GDP deflator, exports % of GDP, PPP conversion factor, price level index) from [The World Bank](https://data.worldbank.org), via the [Data360 API](https://data360api.worldbank.org), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Air passenger traffic data from [Eurostat](https://ec.europa.eu/eurostat) (dataset `TTR00012`, sourced from `AVIA_PAOC`), reused under the European Commission's [CC BY 4.0 reuse policy](https://ec.europa.eu/eurostat/en/help/copyright-notice).
- Crime statistics from [Eurostat](https://ec.europa.eu/eurostat) (datasets `CRIM_OFF_CAT` and `CRIM_GEN_REG`, collected jointly with UNODC from national police/justice authorities), reused under the European Commission's [CC BY 4.0 reuse policy](https://ec.europa.eu/eurostat/en/help/copyright-notice).
- World Heritage Site data from the [UNESCO World Heritage Centre](https://whc.unesco.org) (`whc001` export via [UNESCO Open Data](https://data.unesco.org)). **License unresolved** — UNESCO/WHC's [syndication terms](https://whc.unesco.org/en/syndication) require prior written authorization for republication; not CC BY like this project's other sources. See `data/README.md` for details — confirm reuse rights with UNESCO/WHC before redistributing this data.
- Tourism accommodation data (EMAT) from Chile's [Instituto Nacional de Estadísticas (INE)](https://www.ine.gob.cl/estadisticas-por-tema/comercio-y-servicios/actividad-mensual-del-turismo).
- Domestic air passenger data from Mexico's [Agencia Federal de Aviación Civil (AFAC)](https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404), Monthly Bulletin of Operational Statistics.
