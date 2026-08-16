"""
Unit tests for app/data_loader.py's loader functions, run against small
synthetic fixture files (built per-test with tmp_path + monkeypatch), NOT
this repo's real data/ files -- see conftest.py's docstring for why that
split exists. These tests are about the LOADING/NORMALIZATION LOGIC:
skip-on-bad-record behavior, name-to-iso2 normalization, and the
clustering algorithm -- not about what's currently true of the real
reference data (test_main.py covers that, against the real files).
"""

import json
from pathlib import Path

import pytest

from app import data_loader


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestLoadStaticCountryScores:
    def test_reads_expected_shape(self, tmp_path, monkeypatch):
        path = tmp_path / "overarching.json"
        write_json(
            path,
            {
                "countries": {
                    "JP": {
                        "country_name": "Japan",
                        "unesco_score": 9.0,
                        "michelin_score": 8.0,
                        "price_score": 5.0,
                        "overarching_score": 7.3,
                    },
                }
            },
        )
        monkeypatch.setattr(data_loader, "OVERARCHING_PATH", path)

        result = data_loader.load_static_country_scores()

        assert result == {
            "JP": {"country_name": "Japan", "unesco_score": 9.0, "michelin_score": 8.0, "price_score": 5.0},
        }
        # The file's own precomputed 3-domain overarching_score is
        # intentionally NOT carried through -- this API recomputes its
        # own 4-domain average per request instead (see main.py).
        assert "overarching_score" not in result["JP"]

    def test_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(data_loader, "OVERARCHING_PATH", tmp_path / "does-not-exist.json")
        with pytest.raises(FileNotFoundError):
            data_loader.load_static_country_scores()


class TestLoadStaticCityScores:
    def _write_cities(self, tmp_path, monkeypatch, cities):
        path = tmp_path / "enhanced.json"
        write_json(path, {"cities": cities})
        monkeypatch.setattr(data_loader, "TOURIST_CITIES_ENHANCED_PATH", path)

    def _base_city(self, **overrides):
        city = {
            "simplemaps_id": 1,
            "city": "Ōsaka",
            "city_ascii": "Osaka",
            "country": "Japan",
            "iso2": "JP",
            "unesco_score": 5.0,
            "michelin_score": 5.0,
            "price_score": 5.0,
        }
        city.update(overrides)
        return city

    def test_reads_expected_shape_and_keys_by_string_id(self, tmp_path, monkeypatch):
        self._write_cities(tmp_path, monkeypatch, [self._base_city()])
        result = data_loader.load_static_city_scores()
        assert set(result.keys()) == {"1"}
        assert result["1"]["city"] == "Ōsaka"
        assert result["1"]["city_ascii"] == "Osaka"
        assert result["1"]["country_code"] == "JP"

    def test_skips_record_with_non_string_iso2(self, tmp_path, monkeypatch):
        # Windhoek/Namibia-shaped bad record: iso2 is a float (NaN, in
        # the real data), not a string.
        self._write_cities(
            tmp_path,
            monkeypatch,
            [
                self._base_city(simplemaps_id=1, city="Windhoek", iso2=float("nan")),
                self._base_city(simplemaps_id=2, city="Tokyo"),
            ],
        )
        result = data_loader.load_static_city_scores()
        assert set(result.keys()) == {"2"}

    def test_skips_record_with_null_simplemaps_id(self, tmp_path, monkeypatch):
        # Queenstown/NZ-shaped bad record: a manually-added city with no
        # simplemaps_id at all.
        self._write_cities(
            tmp_path,
            monkeypatch,
            [
                self._base_city(simplemaps_id=None, city="Queenstown"),
                self._base_city(simplemaps_id=2, city="Tokyo"),
            ],
        )
        result = data_loader.load_static_city_scores()
        assert set(result.keys()) == {"2"}

    def test_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(data_loader, "TOURIST_CITIES_ENHANCED_PATH", tmp_path / "nope.json")
        with pytest.raises(FileNotFoundError):
            data_loader.load_static_city_scores()


class TestLoadCityClusterRepresentatives:
    def _write_tourist_cities(self, tmp_path, monkeypatch, cities):
        path = tmp_path / "tourist_cities.json"
        write_json(path, {"cities": cities})
        monkeypatch.setattr(data_loader, "TOURIST_CITIES_PATH", path)

    def test_nearby_smaller_city_absorbed_into_larger_representative(self, tmp_path, monkeypatch):
        # Two Osaka-area points ~5km apart (well under the 50km radius),
        # a Tokyo point ~400km away (well outside it).
        self._write_tourist_cities(
            tmp_path,
            monkeypatch,
            [
                {"simplemaps_id": 1, "population": 2_000_000, "lat": 34.6937, "lng": 135.5023},  # bigger
                {"simplemaps_id": 2, "population": 100_000, "lat": 34.7300, "lng": 135.5000},  # nearby, smaller
                {"simplemaps_id": 3, "population": 1_000_000, "lat": 35.6762, "lng": 139.6503},  # far away
            ],
        )
        result = data_loader.load_city_cluster_representatives()

        assert result["1"] == "1"  # most populous -- represents itself
        assert result["2"] == "1"  # absorbed into the nearby, more populous city
        assert result["3"] == "3"  # far enough away to be its own representative

    def test_skips_entries_with_no_simplemaps_id(self, tmp_path, monkeypatch):
        self._write_tourist_cities(
            tmp_path,
            monkeypatch,
            [
                {"simplemaps_id": 1, "population": 100, "lat": 0.0, "lng": 0.0},
                {"simplemaps_id": None, "population": 999_999, "lat": 0.0, "lng": 0.0},  # Queenstown-shaped
            ],
        )
        result = data_loader.load_city_cluster_representatives()
        assert set(result.keys()) == {"1"}

    def test_missing_population_treated_as_zero_not_error(self, tmp_path, monkeypatch):
        self._write_tourist_cities(
            tmp_path, monkeypatch, [{"simplemaps_id": 1, "population": None, "lat": 0.0, "lng": 0.0}]
        )
        assert data_loader.load_city_cluster_representatives() == {"1": "1"}


class TestPrimaryCapitals:
    def _write_tourist_cities(self, tmp_path, monkeypatch, cities):
        path = tmp_path / "tourist_cities.json"
        write_json(path, {"cities": cities})
        monkeypatch.setattr(data_loader, "TOURIST_CITIES_PATH", path)

    def test_picks_most_populous_primary_capital(self, tmp_path, monkeypatch):
        self._write_tourist_cities(
            tmp_path,
            monkeypatch,
            [
                {"iso2": "US", "capital": "primary", "population": 700_000, "city": "Washington", "simplemaps_id": 1},
                # A second "primary"-tagged US entry with lower
                # population shouldn't happen in real data, but the
                # loader should still pick the bigger one deterministically.
                {"iso2": "US", "capital": "primary", "population": 100, "city": "SmallTown", "simplemaps_id": 2},
                {"iso2": "US", "capital": "admin", "population": 8_000_000, "city": "New York", "simplemaps_id": 3},
            ],
        )
        assert data_loader.load_country_capital_names() == {"US": "Washington"}

    def test_ignores_non_primary_capitals(self, tmp_path, monkeypatch):
        self._write_tourist_cities(
            tmp_path,
            monkeypatch,
            [
                {"iso2": "US", "capital": "admin", "population": 8_000_000, "city": "New York", "simplemaps_id": 1},
                {"iso2": "US", "capital": None, "population": 500_000, "city": "Boston", "simplemaps_id": 2},
            ],
        )
        assert data_loader.load_country_capital_names() == {}


class TestLoadCountryWeatherScores:
    def test_resolves_via_capital_join(self, tmp_path, monkeypatch):
        tourist_cities_path = tmp_path / "tourist_cities.json"
        write_json(
            tourist_cities_path,
            {"cities": [{"iso2": "JP", "capital": "primary", "population": 9_000_000, "city": "Tokyo", "simplemaps_id": 42}]},
        )
        monkeypatch.setattr(data_loader, "TOURIST_CITIES_PATH", tourist_cities_path)

        perfect_month = {
            "monthly_rain_score": 0.0,
            "daily_rain_score": 0.0,
            "daylight_hours_score": 1.0,
            "high_temperature_score": 1.0,
            "low_temperature_score": 1.0,
            "wind_intensity_score": 0.0,
        }
        monthly_scores_path = tmp_path / "monthly_scores.json"
        write_json(monthly_scores_path, {"cities": {"42": {"months": {month: perfect_month for month in data_loader.MONTHS}}}})
        monkeypatch.setattr(data_loader, "MONTHLY_SCORES_PATH", monthly_scores_path)

        result = data_loader.load_country_weather_scores()
        assert result["JP"]["july"] == 10.0

    def test_country_with_unpulled_capital_is_simply_absent(self, tmp_path, monkeypatch):
        # Not an error -- fetch_weather_normals.py is a slow, ongoing
        # pull, so most countries not having weather data yet is the
        # normal case (see this loader's docstring).
        tourist_cities_path = tmp_path / "tourist_cities.json"
        write_json(
            tourist_cities_path,
            {"cities": [{"iso2": "AU", "capital": "primary", "population": 400_000, "city": "Canberra", "simplemaps_id": 99}]},
        )
        monkeypatch.setattr(data_loader, "TOURIST_CITIES_PATH", tourist_cities_path)

        monthly_scores_path = tmp_path / "monthly_scores.json"
        write_json(monthly_scores_path, {"cities": {}})  # Canberra not pulled yet
        monkeypatch.setattr(data_loader, "MONTHLY_SCORES_PATH", monthly_scores_path)

        assert "AU" not in data_loader.load_country_weather_scores()


class TestLoadCountryNameToIso2:
    def _write_aliases(self, tmp_path, monkeypatch, countries):
        path = tmp_path / "country_aliases.json"
        write_json(path, {"countries": countries})
        monkeypatch.setattr(data_loader, "COUNTRY_ALIASES_PATH", path)

    def test_maps_canonical_name_and_aliases(self, tmp_path, monkeypatch):
        self._write_aliases(tmp_path, monkeypatch, {"JPN": {"canonical_name": "Japan", "iso2": "JP", "aliases": ["nippon"]}})
        mapping = data_loader._load_country_name_to_iso2()
        assert mapping["japan"] == "JP"
        assert mapping["nippon"] == "JP"

    def test_skips_non_string_iso2_regression_for_namibia_nan_bug(self, tmp_path, monkeypatch):
        # Reproduces the real bug this test suite was written right
        # after fixing: country_aliases.json's Namibia entry has
        # iso2 == NaN (a float -- an upstream pandas parsing quirk where
        # the string "NA" got read as a missing-value marker). If this
        # loader trusted that value verbatim, a NaN would end up as a
        # dict KEY in load_visa_requirements()'s output, which pydantic
        # 500'd on for EVERY departure country (not just Namibia), since
        # VisaRequirementsResponse.requirements is dict[str, str] and NaN
        # isn't a valid string key.
        self._write_aliases(tmp_path, monkeypatch, {"NAM": {"canonical_name": "Namibia", "iso2": float("nan"), "aliases": ["namibia"]}})
        mapping = data_loader._load_country_name_to_iso2()
        # Not silently dropped either -- VISA_NAME_ISO2_OVERRIDES
        # restores the real code "NA" for exactly this case.
        assert mapping["namibia"] == "NA"

    def test_overrides_are_the_final_word(self, tmp_path, monkeypatch):
        self._write_aliases(tmp_path, monkeypatch, {"RUS": {"canonical_name": "Russia", "iso2": "RU", "aliases": ["russia"]}})
        mapping = data_loader._load_country_name_to_iso2()
        # "russian federation" isn't in country_aliases.json at all here
        # -- this only resolves via VISA_NAME_ISO2_OVERRIDES.
        assert mapping["russian federation"] == "RU"

    def test_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(data_loader, "COUNTRY_ALIASES_PATH", tmp_path / "nope.json")
        with pytest.raises(FileNotFoundError):
            data_loader._load_country_name_to_iso2()


class TestLoadVisaRequirements:
    def _setup(self, tmp_path, monkeypatch, aliases, visa_payload):
        aliases_path = tmp_path / "country_aliases.json"
        write_json(aliases_path, {"countries": aliases})
        monkeypatch.setattr(data_loader, "COUNTRY_ALIASES_PATH", aliases_path)

        visa_path = tmp_path / "visa_requirements.json"
        write_json(visa_path, visa_payload)
        monkeypatch.setattr(data_loader, "VISA_REQUIREMENTS_PATH", visa_path)

    def test_keys_departure_and_destination_by_iso2(self, tmp_path, monkeypatch):
        self._setup(
            tmp_path,
            monkeypatch,
            aliases={
                "MEX": {"canonical_name": "Mexico", "iso2": "MX", "aliases": []},
                "JPN": {"canonical_name": "Japan", "iso2": "JP", "aliases": []},
            },
            visa_payload={"Mexico": {"Japan": "VISA-FREE 90"}},
        )
        result = data_loader.load_visa_requirements()
        assert result == {"MX": {"country_name": "Mexico", "requirements": {"JP": "VISA-FREE 90"}}}

    def test_skips_departure_with_unresolvable_name(self, tmp_path, monkeypatch, capsys):
        self._setup(
            tmp_path,
            monkeypatch,
            aliases={"JPN": {"canonical_name": "Japan", "iso2": "JP", "aliases": []}},
            visa_payload={"Nowhereland": {"Japan": "VISA-FREE 90"}},
        )
        result = data_loader.load_visa_requirements()
        assert result == {}
        assert "Nowhereland" in capsys.readouterr().out

    def test_drops_only_the_unresolvable_destination_not_the_whole_departure(self, tmp_path, monkeypatch, capsys):
        self._setup(
            tmp_path,
            monkeypatch,
            aliases={
                "MEX": {"canonical_name": "Mexico", "iso2": "MX", "aliases": []},
                "JPN": {"canonical_name": "Japan", "iso2": "JP", "aliases": []},
            },
            visa_payload={"Mexico": {"Japan": "VISA-FREE 90", "Nowhereland": "VISA REQUIRED"}},
        )
        result = data_loader.load_visa_requirements()
        assert result["MX"]["requirements"] == {"JP": "VISA-FREE 90"}
        assert "Nowhereland" in capsys.readouterr().out

    def test_namibia_departure_and_destination_resolve_end_to_end(self, tmp_path, monkeypatch):
        # End-to-end regression test for the NaN-iso2 bug (see
        # TestLoadCountryNameToIso2.test_skips_non_string_iso2_regression_for_namibia_nan_bug)
        # through the actual function main.py calls at startup.
        self._setup(
            tmp_path,
            monkeypatch,
            aliases={
                "NAM": {"canonical_name": "Namibia", "iso2": float("nan"), "aliases": ["namibia"]},
                "NLD": {"canonical_name": "Netherlands", "iso2": "NL", "aliases": []},
            },
            visa_payload={
                "Netherlands": {"Namibia": "EVISA · VISA ON ARRIVAL 90"},
                "Namibia": {"Netherlands": "VISA-FREE 90"},
            },
        )
        result = data_loader.load_visa_requirements()
        assert result["NL"]["requirements"]["NA"] == "EVISA · VISA ON ARRIVAL 90"
        assert result["NA"]["country_name"] == "Namibia"
        assert result["NA"]["requirements"]["NL"] == "VISA-FREE 90"

    def test_missing_file_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(data_loader, "VISA_REQUIREMENTS_PATH", tmp_path / "nope.json")
        with pytest.raises(FileNotFoundError):
            data_loader.load_visa_requirements()


class TestLoadCityAttractions:
    """The one loader in this module that returns None instead of raising on
    a missing file -- see load_city_attractions()'s docstring for why that
    asymmetry is deliberate."""

    def _write(self, tmp_path, monkeypatch, payload):
        path = tmp_path / "city_attractions.json"
        write_json(path, payload)
        monkeypatch.setattr(data_loader, "CITY_ATTRACTIONS_PATH", path)

    def test_missing_file_returns_none_rather_than_raising(self, tmp_path, monkeypatch):
        # Every other loader here raises FileNotFoundError instead. This file
        # is generated from sources that can't be pulled everywhere (Kaggle
        # credentials, Overpass reachability), so a checkout without it is
        # legitimate and must not stop the API from starting.
        monkeypatch.setattr(data_loader, "CITY_ATTRACTIONS_PATH", tmp_path / "nope.json")
        assert data_loader.load_city_attractions() is None

    def test_reads_expected_shape(self, tmp_path, monkeypatch):
        self._write(
            tmp_path,
            monkeypatch,
            {
                "radius_km": 100,
                "sources_used": {"openstreetmap": True, "imls": False},
                "cities": {
                    "1": {
                        "zoo_aquarium": {
                            "count": 1,
                            "places": [
                                {
                                    "name": "Antwerp Zoo",
                                    "kind": "Zoo",
                                    "source": "OpenStreetMap",
                                    "distance_km": 43.2,
                                }
                            ],
                        }
                    }
                },
            },
        )

        result = data_loader.load_city_attractions()

        assert result["radius_km"] == 100
        assert result["sources_used"] == {"openstreetmap": True, "imls": False}
        assert result["cities"]["1"]["zoo_aquarium"]["places"][0]["name"] == "Antwerp Zoo"

    def test_radius_falls_back_to_the_page_radius_when_absent(self, tmp_path, monkeypatch):
        # An older/hand-edited file without the field shouldn't make the
        # frontend label its headings "within nullkm".
        self._write(tmp_path, monkeypatch, {"cities": {}})
        assert data_loader.load_city_attractions()["radius_km"] == data_loader.CITY_DETAIL_RADIUS_KM

    def test_empty_cities_map_is_not_the_same_as_a_missing_file(self, tmp_path, monkeypatch):
        # "Generated, but no city has anything nearby" -> a real (empty)
        # dataset, not None. main.py turns the two into different responses:
        # empty sections vs hidden sections.
        self._write(tmp_path, monkeypatch, {"radius_km": 50, "cities": {}})
        result = data_loader.load_city_attractions()
        assert result is not None
        assert result["cities"] == {}


class TestLoadTravelers:
    def _write(self, tmp_path, monkeypatch, payload):
        path = tmp_path / "travelers.json"
        write_json(path, payload)
        monkeypatch.setattr(data_loader, "TRAVELERS_PATH", path)
        # Both paths have to be redirected, not just the one under test:
        # load_travelers() resolves between them (see resolve_travelers_path),
        # so leaving TRAVELERS_ANON_PATH pointing at the real repo file would
        # make these tests read that instead of the fixture.
        monkeypatch.setattr(data_loader, "TRAVELERS_ANON_PATH", tmp_path / "no-anon.json")

    def test_missing_file_returns_none_rather_than_raising(self, tmp_path, monkeypatch):
        # Same reasoning as TestLoadCityAttractions' equivalent test -- this
        # file comes from a Kaggle dataset that can't be pulled everywhere.
        monkeypatch.setattr(data_loader, "TRAVELERS_PATH", tmp_path / "nope.json")
        monkeypatch.setattr(data_loader, "TRAVELERS_ANON_PATH", tmp_path / "nope-anon.json")
        assert data_loader.load_travelers() is None

    def test_keys_by_traveler_id_and_preserves_file_order(self, tmp_path, monkeypatch):
        # Order matters: build_travelers.py sorts most-trips-first and
        # /api/travelers doesn't re-sort, so the page's ordering comes from
        # the file through this dict unchanged.
        self._write(
            tmp_path,
            monkeypatch,
            {
                "travelers": [
                    {"traveler_id": "john-smith-american", "name": "John Smith", "trip_count": 3, "trips": []},
                    {"traveler_id": "jane-doe-canadian", "name": "Jane Doe", "trip_count": 1, "trips": []},
                ]
            },
        )

        result = data_loader.load_travelers()

        assert list(result) == ["john-smith-american", "jane-doe-canadian"]
        assert result["john-smith-american"]["name"] == "John Smith"

    def test_empty_traveler_list_is_not_the_same_as_a_missing_file(self, tmp_path, monkeypatch):
        self._write(tmp_path, monkeypatch, {"travelers": []})
        assert data_loader.load_travelers() == {}


class TestResolveTravelersPath:
    """Which of the two traveler files gets served. The anonymized one wins
    when present -- see resolve_travelers_path()'s docstring for why that's a
    file-existence check rather than a config flag."""

    def _paths(self, tmp_path, monkeypatch):
        raw = tmp_path / "travelers.json"
        anon = tmp_path / "travelers_anon.json"
        monkeypatch.setattr(data_loader, "TRAVELERS_PATH", raw)
        monkeypatch.setattr(data_loader, "TRAVELERS_ANON_PATH", anon)
        return raw, anon

    def test_neither_file_resolves_to_none(self, tmp_path, monkeypatch):
        self._paths(tmp_path, monkeypatch)
        assert data_loader.resolve_travelers_path() is None

    def test_raw_only_resolves_to_raw(self, tmp_path, monkeypatch):
        raw, _ = self._paths(tmp_path, monkeypatch)
        write_json(raw, {"travelers": []})
        assert data_loader.resolve_travelers_path() == raw

    def test_anon_wins_when_both_exist(self, tmp_path, monkeypatch):
        raw, anon = self._paths(tmp_path, monkeypatch)
        write_json(raw, {"travelers": [{"traveler_id": "john-smith-american", "name": "John Smith"}]})
        write_json(anon, {"travelers": [{"traveler_id": "ernest-hemingway", "name": "Ernest Hemingway"}]})

        assert data_loader.resolve_travelers_path() == anon
        # And the loader actually reads the one this resolves to, rather than
        # resolving correctly and then loading the other.
        assert list(data_loader.load_travelers()) == ["ernest-hemingway"]

    def test_anon_only_resolves_to_anon(self, tmp_path, monkeypatch):
        _, anon = self._paths(tmp_path, monkeypatch)
        write_json(anon, {"travelers": []})
        assert data_loader.resolve_travelers_path() == anon
