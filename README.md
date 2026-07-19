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
