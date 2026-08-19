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
python scripts/multiple/fetch_unesco_world_heritage_sites.py
python scripts/multiple/fetch_unesco_world_heritage_sites.py --force-download   # re-download even if cached
```

Downloads UNESCO's World Heritage List export (~24MB — full
multi-language text and media metadata per site) and writes a much
smaller `data/processed/multiple/unesco_world_heritage_sites.json`:
English-only name/description, inscription details (date, criteria,
danger-list status, area), region/country, English-only primary
image/video credit, and coordinates flattened to top-level `lat`/`lng`
(to match `tourist_cities.json`'s naming, for an easy join later).
Drops the 5 non-English name/description variants, the long
`justification_en` inscription essay, non-English media captions, and a
few bookkeeping fields (`uuid`, `id_no`, `images_urls`, `videos_urls`).
Raw export is cached at `data/raw/unesco/whc001.json` — re-run with
`--force-download` to refresh it (UNESCO adds new inscriptions roughly
annually). See `data/README.md` for the full kept/dropped field list and
size-reduction numbers.

```
python scripts/multiple/build_unesco_sites_by_country.py
```

Regroups the site list above into `data/processed/multiple/unesco_by_country.json`
— `{ "US": [sites...], "VN": [sites...], "MX": [sites...], ... }` keyed
by the ISO alpha-2 codes already present in the source data. A
transboundary site (spans multiple countries) is listed once under EVERY
country it spans, not just one — see each site's `transboundary` field.
The one site with no country code at all (Old City of Jerusalem, whose
sovereignty is disputed) is collected separately under
`unassigned_sites` rather than dropped. Run
`fetch_unesco_world_heritage_sites.py` first — this script reads its
output rather than hitting the network itself.

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
python scripts/multiple/fetch_imls_museums.py
python scripts/multiple/fetch_imls_museums.py --list-columns   # inspect headers without processing
```

Pulls the IMLS museum directory (the Kaggle mirror of the US federal
Museum Data Files) and writes `data/processed/multiple/imls_museums.csv`
— roughly 33,000 US institutions with discipline and coordinates, of
which three disciplines matter downstream: `ZAW` (zoos, aquariums,
wildlife conservation), `BOT` (arboretums, botanical gardens, nature
centers) and `ART` (art museums). Needs Kaggle API credentials, same as
`fetch_art_museums.py`. **US-only** — pair it with the OSM pull below for
anywhere else. Public domain, citation required. Run `--list-columns`
first if the normal run errors on a missing column: the Kaggle mirror and
the raw IMLS release use different header conventions and the script
accepts either, but a third variant would need adding to
`COLUMN_CANDIDATES`.

```
python scripts/multiple/fetch_osm_zoos_and_gardens.py --limit 3   # pilot first
python scripts/multiple/fetch_osm_zoos_and_gardens.py            # full run, resumable
python scripts/multiple/fetch_osm_zoos_and_gardens.py --rebuild  # rebuild output from cache, no network
```

Pulls every zoo, aquarium, botanical garden and arboretum worldwide from
OpenStreetMap via the Overpass API (one query per country, no API key)
and writes `data/processed/multiple/osm_zoos_and_gardens.json`. This is
the worldwide half of the same categories IMLS covers for the US. Each
country's raw response is cached under `data/raw/osm_zoos_and_gardens/`,
so an interrupted run costs nothing and a rerun only fetches what's
missing; `--rebuild` regenerates the output from that cache with no
network calls. Expect occasional HTTP 504s on large, densely-mapped
countries — they're retried, and anything still failing is picked up on
the next run. ODbL licensed (share-alike), see `data/README.md`.

```
python scripts/multiple/build_city_attractions.py
```

Joins both of the above against `data/reference/tourist_cities.json` and
writes `data/processed/multiple/city_attractions.json` — for every city,
the zoos/aquariums, botanical gardens and (US-only) art museums within
100km, nearest-first with counts, deduplicated where OSM and IMLS
describe the same place. Either input missing is a warning, not an error,
so you can run this after the OSM pull alone and re-run once IMLS lands.
This file is what backs the city page's Aquariums & Zoos and Botanical
Gardens sections; without it the API simply omits those sections.

```
python scripts/multiple/fetch_traveler_trips.py
python scripts/multiple/build_synthetic_trips.py
python scripts/multiple/build_trips_enhanced.py
python scripts/multiple/build_travelers.py
```

Pulls the Kaggle traveler/trip sample dataset (139 trips) into
`data/processed/multiple/traveler_trips.csv`, cleans it into
`data/processed/multiple/trips_enhanced.json`, then groups those trips by
traveler into `data/processed/multiple/travelers.json`. Needs Kaggle API
credentials for the first script.

`build_trips_enhanced.py` is where all the cleaning lives: display-string
costs (`"800 USD"`, `"1200"`), `"7 days"` durations, mixed date formats —
each kept as both a parsed value and the original string, since there's
no currency column to trust — and the split of the source's single
`Destination` column into `destination_city` + `destination_country`
(plus an ISO country code). That split is a hand-written table, not a
comma split: the source abbreviates (`"Sydney, Aus"`), omits the country
(`"Tokyo"`), names a US state instead (`"Honolulu, Hawaii"`) and
sometimes gives only a country. Run it with `--report` to see how every
destination string resolves. An unmapped destination is a hard failure,
not a null.

`build_synthetic_trips.py` adds hand-authored travelers the Kaggle data
can't supply — people with an actual travel *pattern*, since 113 of its
124 travelers have exactly one trip. 82 of them now, 1,887 trips, each
one a different shape, and named to a convention that makes the airline
legible from the name alone: United loyalists are painters and architects,
Delta loyalists are jazz musicians, American loyalists are scientists,
Southwest loyalists are DC characters, Alaska loyalists are Marvel
characters, and the 31 travelers loyal to **no** airline are named after
Greek myth. Those 31 live two per city across the fifteen most populous US
cities and name no carrier at all: each leg is resolved from the T-100 data
at build time to whoever actually flies that route, so they average nine or
ten airlines each against exactly one for every loyalist. Their patterns range from one city for a decade (Bill Evans)
to a biweekly Monday-Friday commute (Chet Baker) to a traveler who stops
for two years and resumes (Wes Montgomery). Eight fly domestically only,
once to three times a year to see family in a single US city, and stay
with relatives, so those trips carry no accommodation cost at all. The
thirty on American, Southwest and Alaska follow one repeated three-way
split — three international-only to the same destination every time, three
domestic-only taking (paid-for) holidays, four mixed. Routes are checked
against both T-100 extracts in `data/raw/bts_t100/`: the international one
for legs that cross a border, the domestic segment one for those that
don't. An unflown route is a hard failure.
`build_trips_enhanced.py` merges its output.

`build_travelers.py` then does two things: group trips by name +
nationality (the source has no traveler ID), and infer a home base for
everyone who doesn't declare one. These files back the
`/rec-sys` page; without them it shows the commands above instead of a
traveler grid. Sample data, not a real booking log — see
`data/README.md`.

```
python scripts/multiple/build_travelers_anon.py
```

Rewrites `travelers.json` into
`data/processed/multiple/travelers_anon.json`, replacing each traveler's
filler name with a real deceased author of the same nationality and
gender (Nobel laureates first), and dropping the `-nationality` suffix
from `traveler_id` (`jane-austen`, not `jane-austen-british`). Trips,
dates, costs and nationalities are unchanged. The API serves this file in
preference to `travelers.json` whenever it exists — delete it to go back
to the raw names. Prints the old → new mapping on each run; that mapping
is not written into the output. Not anonymization: the source data is
fictional to begin with. See `data/README.md`.

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

```
python scripts/multiple/build_bourdain_trips.py
python scripts/multiple/build_bourdain_trips.py --include-excluded   # excluded episodes in the CSV too
```

Turns both of Anthony Bourdain's travel series into flight trips: the
143 episodes of *No Reservations* (IMDb tt0475900, seasons 1-9) and the
103 of *Parts Unknown* (CNN, seasons 1-12, from Wikipedia's episode
table), both transcribed by hand. 246 episodes in, **130 trips out** — a
5-day round trip departing on each episode's air date, nonstop out of New
York, preferring JFK then LGA then EWR. Writes
`data/processed/multiple/bourdain_trips.csv` and `.json`, with a `show`
column on every row. Reads `airline_routes_enhanced.csv` to decide
whether a nonstop exists at all — an episode with no New York nonstop is
excluded, as are the clip shows, the home-turf episodes and the regional
travelogues with no single gateway. All 116 exclusions keep their reason
in the JSON's `excluded_episodes`. The trips are FABRICATED: shooting
predated each air date by months, and the 5-day length is a modeling
assumption.

```
python scripts/multiple/build_bourdain_traveler.py
python scripts/multiple/build_bourdain_traveler.py --report   # route, airlines available, pick
```

Reshapes those trips into one traveler and writes
`data/processed/multiple/bourdain_traveler.json`, which
`build_trips_enhanced.py` merges alongside `synthetic_trips.json` (both
are in its `SYNTHETIC_SOURCES`). Picks the airline per trip from the
operators of that exact route in `airline_routes_enhanced.csv` — DL, then
UA, then AA by IATA code, then a seeded random draw from whoever else
flies it — and names them with the T-100 spellings the rest of the
rec-sys data uses. Re-run `build_trips_enhanced.py`, `build_travelers.py`
and `build_travelers_anon.py` after this to see him on `/rec-sys`.
