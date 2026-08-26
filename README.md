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
- [ ] Fix `npm warn deprecated whatwg-encoding@3.1.1` in `frontend/` — switch to `@exodus/bytes` (transitive dep, likely via jsdom).
- [ ] Warn users when their trip dates overlap hurricane/typhoon/cyclone season or wildfire season for the destination. Hurricane season has official calendar bounds for the Atlantic (Jun 1–Nov 30), Eastern Pacific (May 15–Nov 30), and Australian region (Nov 1–Apr 30) — hardcode those. Western Pacific typhoons and North Indian Ocean cyclones have no official season, so use NOAA IBTrACS historical frequency by country/month instead of a fabricated date range. Wildfire risk has no global season at all (climate-specific — California/Australia/Mediterranean summers, etc.) — use NASA FIRMS historical fire-detection frequency by country/month. Monsoon/rainy-season warnings don't need a new source — already derivable from the rainfall data `fetch_weather_normals.py` pulls from Open-Meteo.
- [ ] Namibia's ISO2 code is `NA`, and is currently misunderstood as an N/A or Null value in Pandas (`country_aliases.json` ends up with `iso2: NaN` instead of `"NA"`) — fix `build_country_aliases.py`'s CSV read (e.g. `keep_default_na=False`) and rerun everything downstream that depends on `country_aliases.json`.
- [ ] Make the Top 5 Cities cards on `/destinations` clickable, same as the country cards (`frontend/src/pages/Destinations.tsx` currently renders them as plain non-interactive `.destinations-ranked-static` divs — see that file's comment — since there's no per-city detail page yet). Needs a city detail page/route (city name alone isn't a safe URL key, e.g. two different real cities are both named "Kanpur" — use `city_id`/`simplemaps_id`, same key `GET /api/destinations/cities/top10` already returns) before this can happen.
- [ ] Once a city detail page exists: its Michelin card should link to that city's specific MICHELIN Guide region page, not the country-wide one `DestinationDetail`'s country page uses today (`getMichelinGuideUrl()` in `frontend/src/lib/michelin.ts` — `https://guide.michelin.com/en/{iso2}/restaurants`). E.g. Osaka should link to `https://guide.michelin.com/en/jp/osaka-region/restaurants`, not `https://guide.michelin.com/en/jp/restaurants`. The Guide's region slugs (`osaka-region`, etc.) don't derive predictably from a city name — needs real mapping/research, not just a lowercase-and-slugify transform.
- [ ] Brainstorm UNESCO per-city UI/UX/visuals for that same future city detail page. Unlike Michelin, UNESCO doesn't have a per-city (or even per-region) listing page to link out to the way `getUnescoStatesPartyUrl()` links to a per-country one today — need to figure out what to actually show/link for a city instead (e.g. render the nearby-sites list `tourist_cities_enhanced.json`'s `unesco_sites` already has per city, link each site to its own UNESCO World Heritage Centre page, something else entirely).
- [ ] Add a third 100% stacked bar to the traveler page for **destination continent**. **No longer blocked on data**: `data/reference/m49_regions.json` now carries `region` (Africa, Americas, Asia, Europe, Oceania) for all 248 countries, and the API already sends it on every trip as `destination_region` — so this is one function in `lib/travelerCharts.ts` (copy `subregionBreakdown`, read `destination_region`) plus one more `<StackedShareBar>`. Only the scheme question above is left.
- [ ] **Decide the continent scheme — but M49 itself resolves the objection.** The original worry was that M49's top tier merges the Americas while the brief wanted them split. M49's own footnote on the overview page defines **North America (code 003) = Northern America (021) + Caribbean (029) + Central America (013)**, so a North/South America split exists *inside* M49 and doesn't require a second, non-M49 scheme. And with the 22-value subregion bar now shipped, Northern America, Central America, Caribbean and South America already each get their own segment there — so using M49's five regions for the continent bar loses nothing. Africa's absence from the original list is moot for the same reason (the 6 African trips show as Southern/Northern Africa below). Recorded in `data/reference/m49_regions.json`'s `notes` so this doesn't need re-researching.
- [x] Add a fourth 100% stacked bar for **UN M49 subregion** — done 2026-08-17, and it turned out not to need a scraper. UNSD publishes the whole M49 table as a semicolon-delimited CSV download from https://unstats.un.org/unsd/methodology/m49/overview/, so it's committed at `data/raw/unsd_m49/UNSD_M49_2026-08-17.csv` (15KB) and `data/scripts/multiple/build_m49_regions.py` transforms it into `data/reference/m49_regions.json` — reproducible offline, no scraper to rot. **The "22" in the original note was already the derived tier, not M49's literal `subregion`**: Eastern Africa is an *intermediate* region, and M49's real sub-region list is 17 and lumps all of Latin America and the Caribbean together. `detailed_region` (intermediate where one exists, else sub-region) is the 22-value tier and is what the bar charts. Keyed by ISO-alpha3 as planned; the export carries ISO-alpha2 too, so no join through `country_aliases.json` was needed.
- [ ] **The 80% airline-loyalist threshold is currently untested by the data.** `compute_traveler_tags.py` tags 49 travelers, but every one of them is at exactly 100% and the next-highest share in the dataset is 75% — nothing lands between 80% and 100%, so any threshold from ~76% up would produce the identical result. The number is only a real choice once the synthetic data contains someone who mostly-but-not-always flies one carrier. Worth authoring a few such travelers before treating 80% as tuned.
- [ ] **Decide whether Pablo Picasso and Edward Hopper should still read as United loyalists.** Both were authored as United travelers but fly routes United doesn't serve (BCN–ORD, SFO–HKG, SFO–TPE), so `build_synthetic_trips.py` assigned those legs elsewhere and they land at 75% and 70% — below the tag. Two options, and they're genuinely different: swap those destinations for ones United flies (making the authored intent true), or leave them as the dataset's only partial loyalists (useful precisely because they sit near the threshold). Don't "fix" it by lowering the threshold.
- [ ] **Tag rule: "Repeat Destination Airport Traveler" — airport destination entropy < 0.001.** Concretises the "single-destination traveler" candidate in the "More tag rules" item below. Reads `traveler_entropy.json` (the airport unit), so it needs no new data — one function in `compute_traveler_tags.py` plus a chip. Three things to settle before writing it, all checked against the current data (86 of 210 travelers have an airport entropy at all; the other 124 are Kaggle-sourced and record no airport):
  - **The threshold selects the same 29 travelers as `== 0` would, and is untested for the same reason the 80% loyalist threshold is** (see that item above). Nobody sits between 0 and 0.001 — the smallest non-zero airport entropy in the dataset is 1.0986 (= ln 3, a uniform three-airport traveler), so any cutoff from just-above-0 to just-below-1.0986 gives an identical result. `< 0.001` is really `n_destinations == 1` written as a float comparison, which is a fine way to dodge float equality but should be labelled as that rather than read as a tuned number. It only becomes a real choice once someone flies 19-of-20 trips to one airport.
  - **It MUST also require `entropy_is_informative`** (or its own min-trips floor, the way the loyalist rule uses 5). A traveler with ONE recorded trip also has entropy 0.0, and tagging them a "repeat" traveler on the strength of a single flight would be exactly the null-vs-zero trap `compute_traveler_entropy.py` was built to avoid. Today all 29 are safe (the smallest has 8 trips) — that is a property of the current dataset, not of the rule.
  - **A null airport entropy gets no tag, not a "no" tag** — unknown is not the same as varied, same rule as everywhere else entropy appears here.
  Current population (29): Chet Baker (53 trips, all JFK), Arthur Curry (24, SRQ), Ella Fitzgerald (24, MCO), Galileo Galilei (24, MCO), Pierre-Auguste Renoir (24, SAN), then 24 more at 8-20 trips. Worth noting the chip text is long next to "Delta Loyalist" and "Multi Hub" — consider "Repeat Airport" or "Single Airport" for the label and keep the full name as the rule id.
- [ ] More tag rules beyond airline loyalty and home hub — the tag pipeline (`compute_traveler_tags.py` → `traveler_tags.json` → `tags[]` on both traveler routes → `components/TravelerTags.tsx`) is generic in the number of rules, so a second one is a function plus a chip. Candidates the current data can already support: domestic-only / international-only traveler, single-destination traveler (`traveler_entropy.json` already computes it), holiday traveler (their trips pin to real holiday dates — see `build_synthetic_trips.py`), family-stay traveler (`accommodation_type: "Family home"`).
- [ ] The repo spells Oceania as **`oceana`** in `data/processed/oceana/` and `data/scripts/oceana/`. Harmless as a folder name, and the M49 work did **not** leak it — region and subregion labels come verbatim from UNSD's CSV, so the charts say "Oceania" — but the folders are still worth renaming.
- [ ] Add a **UTC time to every flight** (departure and/or arrival), computed from the local `depart`/`arrive` time plus the airport's timezone. Backend/dataset only for now — don't surface it on the frontend yet. Needs a timezone per airport, which `data/reference/airports.json` doesn't carry today (would need adding, e.g. via `timezonefinder` on each airport's lat/lon, or a timezone-by-IATA-code source). Legs that only have a date and no local time (most of the hand-logged Gomez trips and all the Kaggle-sourced ones — see [[gomez_flight_log]]) have nothing to convert, so their UTC field stays null too, same "nothing invented" rule as the rest of that dataset.
- [ ] Add **Rick Steves** as a fourth travel-show-host traveler, same pattern as Bourdain/Ramsay/Conan (`chef_trips.py`/`chef_traveler.py`, see [[chef_travelers]]) — two new scripts (`build_ricksteves_trips.py`, `build_ricksteves_traveler.py`) plus a path in `build_trips_enhanced.py`'s `SYNTHETIC_SOURCES`. Source for his trips: [Rick Steves' Europe (Wikipedia)](https://en.wikipedia.org/wiki/Rick_Steves%27_Europe)'s episode list — still needs the same per-episode research the other three hosts got before it's buildable (home airport(s), the capital rule for country-only episodes, the nonstop-exists filter, dropped-episode reasons), not just the scaffolding.

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
- Hiking trail counts from [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, via the [Overpass API](https://wiki.openstreetmap.org/wiki/Overpass_API), licensed under [ODbL](https://opendatacommons.org/licenses/odbl/). **License nuance** — unlike this project's CC BY sources, ODbL requires share-alike for derivative/produced databases in addition to attribution; see `data/README.md` for details before this goes beyond personal/internal use.
- Visa requirement data (`data/reference/visa_requirements.json`) from [Passport Index](https://www.passportindex.org).
