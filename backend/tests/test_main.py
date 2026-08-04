"""
Integration tests against the REAL FastAPI app and this repo's real
data/ files (see conftest.py's docstring for why) -- these exercise the
full request path together: query parsing, data_loader's startup-time
loads, scoring.py's math, and pydantic response serialization, the way
an actual request does.

Assertions here deliberately avoid hardcoding exact counts/scores that
drift as the data pipeline pulls more weather/UNESCO/Michelin data (see
data_loader.py's docstrings for how often that's expected to change) --
they check shape, invariants (ranked order, weights summing to 1,
iso2-length codes), and the specific "unknown code -> null/empty, not a
404" convention this API uses throughout, not today's specific numbers.
"""

import pytest


class TestHealth:
    def test_ok(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        # Sanity floors, not exact counts -- these only grow over time as
        # the data pipeline pulls more (see data_loader.py), so an exact
        # assertion here would make this test flaky/stale by design.
        assert body["countries_loaded"] > 100
        assert body["cities_loaded"] > 1000
        assert body["countries_with_visa_requirements"] > 100


class TestTopDestinations:
    def test_requires_dates(self, client):
        res = client.get("/api/destinations/top10")
        assert res.status_code == 422

    def test_end_before_start_is_400(self, client):
        res = client.get("/api/destinations/top10", params={"start_date": "2026-07-10", "end_date": "2026-07-01"})
        assert res.status_code == 400

    def test_valid_range_returns_ranked_top_ten(self, client):
        res = client.get("/api/destinations/top10", params={"start_date": "2026-07-05", "end_date": "2026-07-15"})
        assert res.status_code == 200
        body = res.json()

        destinations = body["destinations"]
        assert 1 <= len(destinations) <= 10
        scores = [d["trip_score"] for d in destinations]
        assert scores == sorted(scores, reverse=True)  # ranked highest-first
        assert sum(body["month_weights"].values()) == pytest.approx(1.0)  # day-weighted weights sum to 1

    def test_departure_country_is_echoed_back_not_yet_used_for_scoring(self, client):
        with_dep = client.get(
            "/api/destinations/top10",
            params={"start_date": "2026-07-05", "end_date": "2026-07-15", "departure_country": "NL"},
        )
        without_dep = client.get("/api/destinations/top10", params={"start_date": "2026-07-05", "end_date": "2026-07-15"})
        assert with_dep.json()["departure_country"] == "NL"
        # See backend/README.md: departure_country doesn't affect ranking
        # yet -- reserved for a future distance/flight-time score.
        assert with_dep.json()["destinations"] == without_dep.json()["destinations"]

    def test_every_returned_destination_has_a_valid_shape(self, client):
        res = client.get("/api/destinations/top10", params={"start_date": "2026-01-01", "end_date": "2026-01-07"})
        for d in res.json()["destinations"]:
            assert len(d["country"]) == 2
            assert d["country_name"]
            assert 0 <= d["trip_score"] <= 10
            assert 1 <= d["scores_averaged"] <= 4


class TestTopCityDestinations:
    def test_no_dates_returns_static_ranking(self, client):
        res = client.get("/api/destinations/cities/top10")
        assert res.status_code == 200
        body = res.json()
        assert body["start_date"] is None
        assert body["end_date"] is None
        assert 1 <= len(body["destinations"]) <= 10

    def test_one_date_without_the_other_is_400(self, client):
        res = client.get("/api/destinations/cities/top10", params={"start_date": "2026-07-05"})
        assert res.status_code == 400
        res = client.get("/api/destinations/cities/top10", params={"end_date": "2026-07-05"})
        assert res.status_code == 400

    def test_end_before_start_is_400(self, client):
        res = client.get("/api/destinations/cities/top10", params={"start_date": "2026-07-10", "end_date": "2026-07-01"})
        assert res.status_code == 400

    def test_both_dates_returns_ranked_results(self, client):
        res = client.get("/api/destinations/cities/top10", params={"start_date": "2026-07-05", "end_date": "2026-07-15"})
        assert res.status_code == 200
        scores = [d["trip_score"] for d in res.json()["destinations"]]
        assert scores == sorted(scores, reverse=True)

    def test_diversity_guard_never_returns_a_duplicate_city(self, client):
        res = client.get("/api/destinations/cities/top10")
        city_ids = [d["city_id"] for d in res.json()["destinations"]]
        assert len(city_ids) == len(set(city_ids))

    def test_every_returned_city_has_country_code(self, client):
        res = client.get("/api/destinations/cities/top10")
        for d in res.json()["destinations"]:
            assert len(d["country_code"]) == 2


class TestCountryWeather:
    def test_end_before_start_is_400(self, client):
        res = client.get("/api/destinations/JP/weather", params={"start_date": "2026-07-10", "end_date": "2026-07-01"})
        assert res.status_code == 400

    def test_unknown_country_code_returns_200_with_null_weather(self, client):
        # "ZZ" is a valid-shaped but non-real ISO2 code -- this project's
        # "unknown, not bad" convention means this must NOT be a 404.
        res = client.get("/api/destinations/ZZ/weather", params={"start_date": "2026-07-05", "end_date": "2026-07-15"})
        assert res.status_code == 200
        body = res.json()
        assert body["weather"] is None
        assert body["capital_city"] is None

    def test_country_code_is_case_insensitive(self, client):
        params = {"start_date": "2026-07-05", "end_date": "2026-07-15"}
        upper = client.get("/api/destinations/JP/weather", params=params)
        lower = client.get("/api/destinations/jp/weather", params=params)
        assert upper.json() == lower.json()

    def test_country_with_weather_data_has_populated_fields(self, client):
        # Skip rather than hard-fail if JP happens to have no weather
        # data in this checkout -- coverage is an ongoing pull, not a
        # fixed set (see data_loader.load_country_weather_scores).
        res = client.get("/api/destinations/JP/weather", params={"start_date": "2026-07-05", "end_date": "2026-07-15"})
        body = res.json()
        if body["weather"] is None:
            pytest.skip("no weather data for JP in this checkout")
        assert isinstance(body["weather"]["avg_high_c"], float)
        assert body["weather"]["rainy_days"] >= 0
        assert body["capital_city"]


class TestVisaRequirements:
    def test_known_departure_country_returns_populated_requirements(self, client):
        res = client.get("/api/destinations/NL/visa-requirements")
        assert res.status_code == 200
        body = res.json()
        assert body["departure_country"] == "NL"
        assert body["departure_country_name"] == "Netherlands"
        assert len(body["requirements"]) > 100
        # Keyed by iso2 (2-letter codes), not visa_requirements.json's
        # own name-string labels -- see
        # data_loader.load_visa_requirements()'s docstring for why.
        assert all(len(code) == 2 and code == code.upper() for code in body["requirements"])
        assert all(isinstance(v, str) and v for v in body["requirements"].values())

    def test_unknown_departure_country_returns_200_with_empty_requirements(self, client):
        # Same "unknown, not a 404" convention as the weather endpoint.
        res = client.get("/api/destinations/ZZ/visa-requirements")
        assert res.status_code == 200
        body = res.json()
        assert body["departure_country_name"] is None
        assert body["requirements"] == {}

    def test_departure_country_is_case_insensitive(self, client):
        upper = client.get("/api/destinations/NL/visa-requirements")
        lower = client.get("/api/destinations/nl/visa-requirements")
        assert upper.json() == lower.json()

    def test_namibia_is_a_valid_destination_and_departure(self, client):
        # Regression test for the bug fixed just before this suite was
        # written: country_aliases.json parses Namibia's iso2 as the
        # float NaN (a pandas artifact -- "NA" read as a missing-value
        # marker), which 500'd this endpoint for EVERY departure country,
        # not just Namibia, since a NaN can't be a dict key in a
        # dict[str, str] response model. See
        # data_loader._load_country_name_to_iso2()'s docstring. Also
        # covered against synthetic fixtures in
        # test_data_loader.py::TestLoadVisaRequirements -- this is the
        # same fix verified end to end against the real data files.
        nl_res = client.get("/api/destinations/NL/visa-requirements")
        assert nl_res.status_code == 200
        assert "NA" in nl_res.json()["requirements"]

        na_res = client.get("/api/destinations/NA/visa-requirements")
        assert na_res.status_code == 200
        assert na_res.json()["departure_country_name"] == "Namibia"

    def test_every_loaded_departure_country_responds_without_error(self, client):
        # The actual class of bug hit in production: a single bad value
        # anywhere in visa_requirements.json / country_aliases.json can
        # 500 this endpoint for every departure country, since they all
        # come from one VISA_REQUIREMENTS dict built once at startup.
        # Hitting every real departure country end to end is the
        # strongest guard against that -- test_data_loader.py verifies
        # the loading LOGIC against synthetic fixtures, but only this
        # test verifies today's actual reference data doesn't trip it.
        from app.main import VISA_REQUIREMENTS

        assert len(VISA_REQUIREMENTS) > 100  # sanity check the fixture itself isn't empty

        for iso2 in VISA_REQUIREMENTS:
            res = client.get(f"/api/destinations/{iso2}/visa-requirements")
            assert res.status_code == 200, f"{iso2} returned {res.status_code}: {res.text}"
            requirements = res.json()["requirements"]
            assert all(isinstance(v, str) for v in requirements.values())
