
```
python scripts/multiple/build_bourdain_trips.py
python scripts/multiple/build_bourdain_trips.py --include-excluded   # excluded episodes in the CSV too
```

Turns the 143 episodes of *Anthony Bourdain: No Reservations* (IMDb
tt0475900, seasons 1-9, transcribed by hand from the episode list) into
70 flight trips: a 5-day round trip departing on each episode's air date,
nonstop out of New York, preferring JFK then LGA then EWR. Writes
`data/processed/multiple/bourdain_trips.csv` and `.json`. Reads
`airline_routes_enhanced.csv` to decide whether a nonstop exists at all —
an episode with no New York nonstop is excluded, as are the clip shows,
the home-turf episodes and the regional travelogues with no single
gateway. All 73 exclusions keep their reason in the JSON's
`excluded_episodes`. The trips are FABRICATED: shooting predated each air
date by months, and the 5-day length is a modeling assumption.

```
python scripts/multiple/build_bourdain_traveler.py
python scripts/multiple/build_bourdain_traveler.py --report   # route, airlines available, pick
```

Reshapes those trips into one traveler and writes
`data/processed/multiple/bourdain_traveler.json`, which
`build_trips_enhanced.py` merges alongside `synthetic_trips.json` (both
are in its `SYNTHETIC_SOURCES`). Picks the airline per trip from the
operators of that exact route in `airline_routes_enhanced.csv` — Delta,
then United, then American, then a seeded random draw from whoever else
flies it — and names them with the T-100 spellings the rest of the
rec-sys data uses. Re-run `build_trips_enhanced.py`, `build_travelers.py`
and `build_travelers_anon.py` after this to see him on `/rec-sys`.
