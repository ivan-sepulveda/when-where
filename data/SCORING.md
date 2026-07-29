# Scoring

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
python scripts/compute_unesco_score.py
```

Turns `data/processed/multiple/unesco_by_country.json` into
`data/processed/UNESCO_SCORE_BY_COUNTRY.csv`: a **log-scaled** 0–10
score against the single highest country (Italy, 62 sites, as of this
writing) — `score = log(SITE_COUNT+1) / log(MAX_SITE_COUNT+1) * 10`,
matching `compute_michelin_score.py`'s formula below for consistency
between the project's two "density of X" scores. This is the third
version of this script's scoring rule: v1 was plain linear against the
max (dropped — Mexico's 36 sites landed at a middling 5.81 just because
Italy happened to have 62); v2 was fixed tiers (50+→10, 40–49→9,
30–39→8, 20–29→7, linear ramp below that — chosen specifically to
decouple every score from the current record holder). v3 (current)
moved back to log-scale, on request, for consistency with the Michelin
score's formula — this does reintroduce a small dependence on the
current max that the tiered version didn't have, and gives noticeably
more credit to low site counts than tiers did (Mexico 36→8.72, Vietnam
9→5.56, Namibia 2→2.65, vs. 8.0/2.84/0.63 under tiers). See
`data/README.md` for the full three-version history and
`compute_michelin_score.py`'s docstring for the original log-vs-tiered
tradeoff discussion. Every country in `reference/country_aliases.json`
gets a row (242 total), including the 69 with zero UNESCO sites — a 0 is
a real data point here, not a country silently dropped. Not combined
with anything else — like the weather scores, this is one candidate
input for a traveler-profile-specific weighted score (a "food and
culture traveler" profile would presumably weight this heavily). See
`data/README.md` for two country-code gaps patched by hand (Namibia,
Palestine) and why.

```
python scripts/compute_michelin_score.py
```

Turns `data/processed/multiple/michelin_restaurants.csv` into
`data/processed/MICHELIN_SCORE_BY_COUNTRY.csv`: a **log-scaled** 0–10
score against the single highest country (France, 3,043 total Michelin
awards — Stars + Bib Gourmand + Selected Restaurants combined, not
starred-only) — `score = log(count+1) / log(max+1) * 10`. Michelin
awards are far more top-heavy than UNESCO sites (France's 3,043 vs.
Italy's 62 — a ~50x wider spread): under a plain linear scale, that
spread crushes almost every other country toward 0 (Italy, with ~2,000
awards, would land at 6.5); log-scale compresses it so hundreds of
awards reads as "very good" (7–9 range). Same 242-country coverage as
`UNESCO_SCORE_BY_COUNTRY.csv`, 0 for the ~192 countries with no
Michelin-recognized restaurant in this dataset. See `data/README.md` for
the log-vs-linear comparison table and the one real caveat log-scale
brings (score still shifts slightly if some country ever overtakes
France) — now shared by `compute_unesco_score.py` above too, since both
scripts use the same formula.

```
python scripts/compute_price_level_score.py
```

Turns the already-pulled World Bank Price Level Index
(`worldbank_PA.NUS.GDP.PLI_<year>_by_country.json`) into
`data/processed/PRICE_LEVEL_SCORE_BY_COUNTRY.csv`: a 0–10
**affordability** score — HIGHER means CHEAPER, inverted from PLI's own
"USA=100, higher=pricier" direction, per the project's decision. Linear
against fixed anchors (PLI ≤ 20 → 10, PLI ≥ 120 → 0, not the current
min/max country), chosen because PLI's real range (~13 to ~118) isn't
skewed the way UNESCO/Michelin counts are — a plain linear scale is the
right tool here, tiering or log-scaling would solve a problem this
metric doesn't have. Countries with no PLI value (59 of 242 — small
territories, sanctioned/conflict states) get a **blank**, not a 0 —
missing data isn't the same as "extremely expensive." See
`build_overarching_trip_scores.py` below for how that blank is handled.

```
python scripts/build_overarching_trip_scores.py
```

Averages `UNESCO_SCORE`, `MICHELIN_SCORE`, and `PRICE_SCORE` into
`OVERARCHING_SCORE` — plain `mean()`, not weighted, per the request that
kicked this script off. All three inputs share the same 242-country,
ISO2-keyed list, so this is a straight join, no name-matching needed.
Missing `PRICE_SCORE` (59 countries) is averaged *around*, not treated
as 0 — a country's score is the mean of however many of the three it
actually has, tracked in `SCORES_AVERAGED` (1–3) so a score built from
only 1–2 domains is never mistaken for a full 3-domain one. Not
traveler-profile-aware — a natural next step is weighting these (and
the weather/peak-tourism/crime scores above) differently per profile,
but this script is the flat, unweighted baseline underneath that.

Written as both `data/processed/OVERARCHING_TRIP_SCORE_BY_COUNTRY.csv`
(one row per country) and `...json` (an object keyed by ISO2 code, plus
`source`/`generated`/count metadata matching this project's other JSON
outputs, e.g. `unesco_by_country.json`) — same data either way, with a
missing `PRICE_SCORE` as a blank CSV cell / JSON `null` respectively. The
JSON exists for anything downstream (the frontend, eventually) that wants
this data without a CSV parser.

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
itself, USD purchasing power, or `UNESCO_SCORE_BY_COUNTRY.csv`'s 0–10
UNESCO score; order countries alphabetically, by capital latitude, by
USD purchasing power, or by UNESCO score; ascending or descending.
Color always encodes `PEAK_RATIO` and the hover tooltip always shows all
five metrics no matter which one is driving marker size. UNESCO scores
are joined onto the chart's 49 countries by name (via
`country_lookup.normalize_country()`), same fix as USD purchasing power
already needed, since `UNESCO_SCORE_BY_COUNTRY.csv`'s ISO2 codes don't
line up with `PEAK_TOURISM_INDICATOR_BY_COUNTRY.csv`'s Eurostat-style
ones. Renders via Plotly.js from a CDN rather than the `plotly` Python
package, so opening the file needs nothing but a browser and generating
it needs no new dependency — see `data/README.md` for the full breakdown
of each control.
