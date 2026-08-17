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

import math
import re
from collections import Counter

import pytest


@pytest.fixture(scope="module")
def a_city_id(client) -> str:
    """A city_id that's guaranteed to exist right now, taken from
    cities/top10 rather than hardcoded -- simplemaps_ids are stable, but
    which cities rank is not, and this suite deliberately doesn't pin
    today's specific data (see this module's docstring). Module-scoped
    and defined here rather than inside TestCityDetail/TestCityWeather so
    both classes share one lookup."""
    return client.get("/api/destinations/cities/top10").json()["destinations"][0]["city_id"]


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


class TestCityDetail:
    def test_returns_detail_for_a_ranked_city(self, client, a_city_id):
        res = client.get(f"/api/destinations/cities/{a_city_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["city_id"] == a_city_id
        assert body["city_ascii"]
        assert len(body["country_code"]) == 2
        assert -90 <= body["lat"] <= 90
        assert -180 <= body["lng"] <= 180
        assert body["radius_km"] == 100

    def test_unknown_city_id_is_404(self, client):
        # Unlike the weather/visa routes' "unknown code -> null/empty, not
        # a 404" convention (which is about missing DATA for a real
        # place), an unrecognized city_id is a place this project has
        # never heard of -- there's no partial answer to give.
        res = client.get("/api/destinations/cities/0")
        assert res.status_code == 404

    def test_top10_still_wins_the_route_over_city_id(self, client):
        # /api/destinations/cities/{city_id} would swallow "top10" if it
        # were declared first -- FastAPI matches in declaration order.
        res = client.get("/api/destinations/cities/top10")
        assert res.status_code == 200
        assert "destinations" in res.json()

    def test_nearby_lists_are_within_the_radius_and_nearest_first(self, client, a_city_id):
        body = client.get(f"/api/destinations/cities/{a_city_id}").json()
        radius = body["radius_km"]
        for key in ("unesco_sites", "michelin_restaurants"):
            distances = [entry["distance_km"] for entry in body[key]]
            assert all(d <= radius for d in distances)
            assert distances == sorted(distances)

    def test_counts_are_full_totals_not_the_truncated_list_length(self, client, a_city_id):
        # michelin_restaurants is capped at CITY_DETAIL_MICHELIN_LIMIT
        # while michelin_count is the real total within the radius, so the
        # count may exceed the list -- but never the other way around.
        body = client.get(f"/api/destinations/cities/{a_city_id}").json()
        assert body["michelin_count"] >= len(body["michelin_restaurants"])
        assert body["unesco_site_count"] >= len(body["unesco_sites"])

    def test_every_top10_city_has_a_detail_page(self, client):
        # Same reasoning as TestVisaRequirements' every-departure-country
        # test: one bad record in tourist_cities_enhanced.json shouldn't
        # be discoverable only by a user clicking the row that happens to
        # hit it. Every city the ranking can link to must resolve.
        for destination in client.get("/api/destinations/cities/top10").json()["destinations"]:
            res = client.get(f"/api/destinations/cities/{destination['city_id']}")
            assert res.status_code == 200, f"{destination['city_id']} returned {res.status_code}: {res.text}"


class TestCityAttractions:
    """The Aquariums/Zoos, Botanical Gardens and (US-only) local art museum
    fields on the city detail response.

    These assert the null-vs-empty contract rather than any particular
    city having a zoo, because city_attractions.json is generated from
    sources that can't be pulled everywhere (Kaggle credentials, Overpass
    reachability) -- so this checkout may or may not have the file, and both
    states are legitimate. See data_loader.load_city_attractions()."""

    ATTRACTION_FIELDS = ("zoos_and_aquariums", "botanical_gardens", "local_art_museums")

    def test_fields_are_present_on_the_response(self, client, a_city_id):
        body = client.get(f"/api/destinations/cities/{a_city_id}").json()
        for field in self.ATTRACTION_FIELDS:
            assert field in body, f"{field} missing from the city detail response"

    def test_all_categories_agree_on_whether_the_dataset_exists(self, client, a_city_id):
        # Either the dataset is loaded (every category is an object) or it
        # isn't (every category is null). A mix would mean the frontend could
        # show one section and hide another for the same city, which is a bug
        # in city_attractions() rather than a data condition.
        body = client.get(f"/api/destinations/cities/{a_city_id}").json()
        nulls = [body[field] is None for field in self.ATTRACTION_FIELDS]
        assert all(nulls) or not any(nulls)
        # The radius field follows the same all-or-nothing rule.
        assert (body["attractions_radius_km"] is None) == all(nulls)

    def test_loaded_categories_have_a_valid_shape(self, client, a_city_id):
        body = client.get(f"/api/destinations/cities/{a_city_id}").json()
        if body["zoos_and_aquariums"] is None:
            pytest.skip("city_attractions.json not generated in this checkout")

        assert body["attractions_radius_km"] > 0
        for field in self.ATTRACTION_FIELDS:
            payload = body[field]
            assert payload["count"] >= len(payload["places"])  # count is the true total, list is capped
            distances = [p["distance_km"] for p in payload["places"]]
            assert distances == sorted(distances)  # nearest-first
            assert all(d <= body["attractions_radius_km"] for d in distances)
            assert all(p["name"] and p["kind"] for p in payload["places"])
            assert all(p["source"] in ("IMLS", "OpenStreetMap") for p in payload["places"])

    def test_health_reports_attractions_coverage(self, client):
        body = client.get("/health").json()
        assert "cities_with_attractions" in body
        count = body["cities_with_attractions"]
        assert count is None or count >= 0


class TestCityWeather:
    def test_requires_dates(self, client, a_city_id):
        res = client.get(f"/api/destinations/cities/{a_city_id}/weather")
        assert res.status_code == 422

    def test_end_before_start_is_400(self, client, a_city_id):
        res = client.get(
            f"/api/destinations/cities/{a_city_id}/weather",
            params={"start_date": "2026-07-10", "end_date": "2026-07-01"},
        )
        assert res.status_code == 400

    def test_unknown_city_id_is_404(self, client):
        res = client.get(
            "/api/destinations/cities/0/weather", params={"start_date": "2026-07-05", "end_date": "2026-07-15"}
        )
        assert res.status_code == 404

    def test_known_city_returns_weather_or_an_explicit_null(self, client, a_city_id):
        res = client.get(
            f"/api/destinations/cities/{a_city_id}/weather",
            params={"start_date": "2026-07-05", "end_date": "2026-07-15"},
        )
        assert res.status_code == 200
        body = res.json()
        assert sum(body["month_weights"].values()) == pytest.approx(1.0)
        # weather may legitimately be null -- only ~1,770 of 3,069 cities
        # have normals pulled so far (see load_city_weather_metrics).
        if body["weather"] is None:
            pytest.skip(f"no weather normals for city {a_city_id} in this checkout")
        assert isinstance(body["weather"]["avg_high_c"], float)
        assert body["weather"]["rainy_days"] >= 0

    def test_rainy_days_never_exceeds_trip_length(self, client, a_city_id):
        # Regression guard for the bug resolve_rainy_days_estimate()
        # exists to prevent (a 7-day trip reporting 11 rainy days) -- same
        # scaling the country route already gets, now on the city path.
        res = client.get(
            f"/api/destinations/cities/{a_city_id}/weather",
            params={"start_date": "2026-07-05", "end_date": "2026-07-11"},
        )
        weather = res.json()["weather"]
        if weather is None:
            pytest.skip(f"no weather normals for city {a_city_id} in this checkout")
        assert weather["rainy_days"] <= 7


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


class TestTravelers:
    """The /rec-sys data routes. Like TestCityAttractions above, these assert
    the contract rather than any particular traveler existing -- travelers.json
    comes from a Kaggle dataset that can't be pulled from every environment,
    so this checkout may or may not have it and both states are legitimate."""

    def test_list_route_always_answers(self, client):
        res = client.get("/api/travelers")
        assert res.status_code == 200
        body = res.json()
        assert isinstance(body["dataset_available"], bool)
        assert isinstance(body["travelers"], list)
        # A missing dataset is an explicit flag, never an error and never an
        # empty list masquerading as "no travelers exist" -- /rec-sys uses
        # the flag to decide between an empty state and a "run these scripts"
        # message.
        if not body["dataset_available"]:
            assert body["travelers"] == []

    def test_summaries_omit_trips_and_carry_an_id(self, client):
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        for traveler in body["travelers"]:
            assert traveler["traveler_id"]
            assert traveler["name"]
            assert traveler["trip_count"] >= 1
            # The card grid doesn't need trips, and shipping them would make
            # this response scale with total trips rather than travelers.
            assert "trips" not in traveler

    def test_every_traveler_has_an_inferred_base(self, client):
        # The base is a guess (nationality + which cities they flew to), but
        # it should exist for every traveler in this dataset -- an "unmapped"
        # one means a nationality BASE_CITIES doesn't cover yet, which the
        # build script also reports.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        for traveler in body["travelers"]:
            assert traveler["base_inference"] in (
                "declared",  # a hand-authored traveler who states their own home
                "primary",
                "avoided_visited",
                "visited_all_candidates",
                "unmapped",
            )
            if traveler["base_inference"] != "unmapped":
                assert traveler["base_city"]
                assert traveler["base_country"]
                assert len(traveler["base_country_code"]) == 2

    def test_base_city_is_never_somewhere_they_visited(self, client):
        # The entire point of the inference: three trips to Sydney means the
        # traveler is not based in Sydney. The one allowed exception is a
        # country whose whole candidate list they've visited (Singapore has
        # exactly one city), which is flagged rather than silently kept.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        for summary in body["travelers"]:
            # "declared" is exempt for the same reason it wins over inference:
            # it's a stated home, not a guess, so nothing about their trip
            # list constrains it.
            if summary["base_inference"] in ("declared", "unmapped", "visited_all_candidates"):
                continue
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            visited = {t["destination_city"] for t in detail["trips"] if t["destination_city"]}
            assert summary["base_city"] not in visited, summary

    def test_hand_authored_travelers_keep_their_own_name(self, client):
        # build_travelers_anon.py renames every Kaggle traveler after a
        # deceased author, but a hand-authored traveler already IS the persona
        # -- renaming Frank Lloyd Wright would undo the point of authoring
        # him. Their id is still re-slugged to this file's bare-name
        # convention, so it must not carry a nationality suffix.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        authored = [t for t in body["travelers"] if t.get("synthetic")]
        if not authored:
            pytest.skip("no hand-authored travelers in this checkout")

        for traveler in authored:
            assert traveler["persona_match"] == "authored"
            assert traveler["base_inference"] == "declared"
            detail = client.get(f"/api/travelers/{traveler['traveler_id']}").json()
            # Their trips carry the airline and route their itinerary was
            # built from; Kaggle trips have none of that.
            assert all(t["synthetic"] for t in detail["trips"])
            assert all(t["carrier_name"] for t in detail["trips"])
            assert all(len(t["origin_airport"]) == 3 for t in detail["trips"])
            assert all(len(t["destination_airport"]) == 3 for t in detail["trips"])

    def test_destination_entropy_is_consistent_with_the_traveler_it_describes(self, client):
        # The entropy block is computed by a separate script from a separate
        # file (compute_traveler_entropy.py -> traveler_entropy.json), joined
        # back on traveler_id at request time -- so the two CAN drift apart.
        # This recomputes the entropy from the trips in the same response and
        # checks they agree, which is what would catch a stale entropy file
        # served alongside freshly rebuilt travelers.
        import math
        from collections import Counter

        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        checked = 0
        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            entropy = detail.get("destination_entropy")
            if entropy is None:
                continue  # compute_traveler_entropy.py not run here
            checked += 1

            counts = Counter(
                t["destination_airport"] for t in detail["trips"] if t.get("destination_airport")
            )
            assert entropy["trips_with_destination"] == sum(counts.values()), summary["traveler_id"]
            assert entropy["n_destinations"] == len(counts), summary["traveler_id"]

            if not counts:
                # No airport on any trip -- must be null, NOT 0. A 0 here
                # would claim the traveler never varies their destination
                # when the source simply doesn't record where they flew.
                assert entropy["entropy"] is None, summary["traveler_id"]
                assert entropy["normalized"] is None, summary["traveler_id"]
                continue

            total = sum(counts.values())
            expected = -sum((c / total) * math.log(c / total) for c in counts.values())
            assert entropy["entropy"] == pytest.approx(expected, abs=1e-3), summary["traveler_id"]

        if checked == 0:
            pytest.skip("traveler_entropy.json not generated in this checkout")

    def test_entropy_zero_is_distinguishable_from_entropy_unknown(self, client):
        # The distinction the whole DestinationEntropy model exists to
        # preserve. A traveler who flew 53 times to one airport and a
        # traveler whose trips record no airport at all are both "not spread
        # out" in some loose sense, but only the first is a fact about the
        # person -- and only the first should ever render as 0.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        saw_real_zero = False
        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            entropy = detail.get("destination_entropy")
            if entropy is None:
                continue

            if entropy["entropy"] == 0:
                # A real zero needs a destination to point at and at least
                # one trip that went there.
                assert entropy["n_destinations"] == 1, summary["traveler_id"]
                assert entropy["top_destination"], summary["traveler_id"]
                assert entropy["trips_with_destination"] >= 1, summary["traveler_id"]
                # And it's only meaningful with 2+ observations -- one trip
                # can only ever produce 0.
                assert entropy["is_informative"] == (entropy["trips_with_destination"] >= 2)
                if entropy["is_informative"]:
                    saw_real_zero = True
            elif entropy["entropy"] is None:
                assert entropy["top_destination"] is None, summary["traveler_id"]
                assert entropy["is_informative"] is False, summary["traveler_id"]

        if not saw_real_zero:
            pytest.skip("no single-destination traveler in this checkout")

    def test_normalized_entropy_states_its_own_denominator(self, client):
        # `normalized` is a fraction of a dataset-wide count that moves
        # whenever the trip data does, so the API has to send that count
        # rather than let the page hardcode it -- and the fraction has to
        # actually equal entropy / ln(count).
        import math

        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            entropy = detail.get("destination_entropy")
            if entropy is None or entropy["entropy"] is None:
                continue

            k = entropy["global_distinct_destinations"]
            assert k and k > 1, summary["traveler_id"]
            assert entropy["destination_unit"] in ("airport", "city")
            expected = entropy["entropy"] / math.log(k)
            assert entropy["normalized"] == pytest.approx(expected, abs=1e-3), summary["traveler_id"]
            # Normalised entropy is a proportion; outside 0-1 means the
            # denominator is wrong, not the traveler.
            assert 0.0 <= entropy["normalized"] <= 1.0, summary["traveler_id"]

    def test_loyalist_tags_agree_with_the_carriers_in_the_same_response(self, client):
        # Tags come from a separate script and a separate file
        # (compute_traveler_tags.py -> traveler_tags.json), joined back on
        # traveler_id at request time, so they CAN drift from the trips they
        # describe. This recomputes the rule from the trips in the same
        # response -- which is what would catch a stale tags file served
        # alongside freshly rebuilt travelers.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        checked = 0
        for summary in body["travelers"]:
            tags = summary.get("tags") or []
            loyalist = [t for t in tags if t["kind"] == "airline_loyalist"]
            if not loyalist:
                continue

            # One airline can be a majority, so one loyalist tag at most.
            assert len(loyalist) == 1, summary["traveler_id"]
            tag = loyalist[0]

            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            counts = Counter(
                trip["carrier_name"] for trip in detail["trips"] if trip["carrier_name"]
            )
            # THE DENOMINATOR IS TRIPS WITH A CARRIER, not trip_count -- the
            # rule's one non-obvious choice, and the one a future refactor is
            # most likely to get wrong.
            assert tag["denominator"] == sum(counts.values()), summary["traveler_id"]
            assert tag["trips"] == counts[tag["carrier_name"]], summary["traveler_id"]
            assert tag["carrier_name"] == counts.most_common(1)[0][0], summary["traveler_id"]
            assert tag["share"] == pytest.approx(
                tag["trips"] / tag["denominator"], abs=1e-3
            ), summary["traveler_id"]
            checked += 1

        if checked == 0:
            pytest.skip("traveler_tags.json not generated in this checkout")

    def test_an_untagged_traveler_genuinely_fails_the_rule(self, client):
        # The other direction: every traveler WITHOUT the tag must actually
        # miss it, on share or on trip count. A rule that silently stopped
        # firing would still pass the test above, which only inspects the
        # tags that exist.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")
        if not any(t.get("tags") for t in body["travelers"]):
            pytest.skip("traveler_tags.json not generated in this checkout")

        for summary in body["travelers"]:
            if any(t["kind"] == "airline_loyalist" for t in summary.get("tags") or []):
                continue

            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            counts = Counter(
                trip["carrier_name"] for trip in detail["trips"] if trip["carrier_name"]
            )
            n = sum(counts.values())
            if n == 0:
                continue  # no carrier recorded at all -- unknown, not disloyal

            share = counts.most_common(1)[0][1] / n
            # 0.8 and 5 are compute_traveler_tags.py's defaults; both are
            # --flags there, so a checkout built with stricter ones still
            # satisfies this.
            assert share < 0.8 or n < 5, summary["traveler_id"]

    def test_tags_are_a_list_on_both_routes_and_identical_between_them(self, client):
        # Tags are attached to the SUMMARY as well as the detail so the
        # /rec-sys grid can show chips without fetching every traveler's
        # trips -- which only works if the two agree.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        for summary in body["travelers"]:
            # Never null: "no rule matched" and "the file isn't there" are
            # both an empty list, and the frontend maps over it unguarded.
            assert isinstance(summary["tags"], list), summary["traveler_id"]

        for summary in body["travelers"][:20]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            assert detail["tags"] == summary["tags"], summary["traveler_id"]

    def test_tag_shape_is_stable_enough_to_render(self, client):
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        tags = [tag for t in body["travelers"] for tag in t.get("tags") or []]
        if not tags:
            pytest.skip("traveler_tags.json not generated in this checkout")

        for tag in tags:
            # The three fields every tag has, whatever rule made it.
            assert tag["tag_id"] and tag["kind"] and tag["label"]
            assert re.fullmatch(r"[a-z0-9:-]+", tag["tag_id"]), tag
            if tag["kind"] != "airline_loyalist":
                continue
            # The label is the SHORT airline name -- a chip has to fit a
            # 180px card, and "Delta Air Lines Inc. Loyalist" does not.
            assert tag["label"].endswith(" Loyalist"), tag
            assert tag["label"] != f"{tag['carrier_name']} Loyalist", tag
            assert tag["tag_id"].startswith("airline-loyalist:"), tag
            assert tag["share"] >= 0.8, tag
            assert tag["denominator"] >= 5, tag

    def test_a_traveler_with_no_recorded_airline_gets_no_loyalist_tag(self, client):
        # The 124 Kaggle-sourced travelers record no carrier anywhere. "We
        # don't know who they fly with" must not come out as a tag, and
        # equally must not come out as a "no airline" tag -- it comes out as
        # nothing at all.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        checked = 0
        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            if any(trip["carrier_name"] for trip in detail["trips"]):
                continue
            assert not [t for t in detail["tags"] if t["kind"] == "airline_loyalist"], summary
            checked += 1
            if checked >= 15:
                break

    def test_hub_tags_only_go_to_travelers_who_declare_where_they_live(self, client):
        # The rule's sharpest edge. 124 travelers have a base INFERRED from
        # their nationality -- "Washington, D.C." is just the US default --
        # and a chip saying where someone lives must not be built on a guess.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        hub_kinds = {"airline_hub", "multi_hub"}
        tagged = [
            t for t in body["travelers"]
            if any(tag["kind"] in hub_kinds for tag in t.get("tags") or [])
        ]
        if not tagged:
            pytest.skip("traveler_tags.json not generated in this checkout")

        for traveler in tagged:
            assert traveler["base_inference"] == "declared", traveler["traveler_id"]
            assert traveler["base_country_code"] == "US", traveler["traveler_id"]

    def test_a_multi_hub_tag_replaces_the_individual_hub_tags(self, client):
        # Chicago gets one chip, not three. If both kinds ever appear on one
        # traveler the card grid is wrong and so is the rule.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        seen = 0
        for traveler in body["travelers"]:
            kinds = [tag["kind"] for tag in traveler.get("tags") or []]
            if "multi_hub" not in kinds:
                continue
            assert "airline_hub" not in kinds, traveler["traveler_id"]
            assert kinds.count("multi_hub") == 1, traveler["traveler_id"]
            seen += 1

        if seen == 0:
            pytest.skip("no multi-hub travelers in this checkout")

    def test_hub_tags_carry_the_city_and_airlines_they_claim(self, client):
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        hubs = [
            tag for t in body["travelers"] for tag in t.get("tags") or []
            if tag["kind"] in ("airline_hub", "multi_hub")
        ]
        if not hubs:
            pytest.skip("traveler_tags.json not generated in this checkout")

        for tag in hubs:
            # The city is the whole basis of the tag -- the tooltip is built
            # from it, and without one the chip can't say anything.
            assert tag["hub_city"], tag
            assert tag["hub_airports"], tag
            assert all(len(code) == 3 for code in tag["hub_airports"]), tag
            # One dot per airline, and the short names line up with them.
            assert len(tag["carrier_names"]) == len(tag["airlines"]), tag

            if tag["kind"] == "multi_hub":
                # More than one airline is what the tag MEANS.
                assert len(tag["airlines"]) >= 2, tag
                # Null rather than the first of them, so nothing downstream
                # can treat this as a single-airline tag.
                assert tag["carrier_name"] is None, tag
            else:
                assert len(tag["airlines"]) == 1, tag
                assert tag["carrier_name"] == tag["carrier_names"][0], tag
                assert tag["label"] == f"{tag['airlines'][0]} Hub", tag

    def test_a_hub_tag_makes_no_claim_about_who_the_traveler_flies(self, client):
        # Living at a hub and being loyal to that airline are independent --
        # the dataset has travelers who are both, either, and neither, and
        # the two rules must not have been quietly wired together. Barry
        # Allen (Chicago, Southwest, flies Midway) is the case that matters.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        hub_only = loyalist_only = both = 0
        for traveler in body["travelers"]:
            kinds = {tag["kind"] for tag in traveler.get("tags") or []}
            has_hub = bool(kinds & {"airline_hub", "multi_hub"})
            has_loyalty = "airline_loyalist" in kinds
            hub_only += has_hub and not has_loyalty
            loyalist_only += has_loyalty and not has_hub
            both += has_hub and has_loyalty

        if hub_only + loyalist_only + both == 0:
            pytest.skip("traveler_tags.json not generated in this checkout")
        # All three populations exist, which is what proves the rules are
        # independent rather than one implying the other.
        assert hub_only > 0 and loyalist_only > 0 and both > 0

    def test_a_hub_traveler_actually_flies_out_of_that_metro(self, client):
        # Independent check on the hand-written city table in
        # compute_traveler_tags.py: every declared traveler departs from
        # exactly one airport, so a tag claiming they live in Denver had
        # better not belong to someone who only ever flies out of Boston.
        #
        # The hub airports themselves are NOT asserted -- three travelers
        # live in a hub city and use its secondary field (Midway, Hobby),
        # which is real. What's checked is the metro, via the destination
        # cities their own trips reach.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        # Airports that are in one of the table's metros but aren't the hub.
        SECONDARY = {"MDW": "Chicago", "HOU": "Houston"}
        checked = 0
        for summary in body["travelers"]:
            hub = next(
                (t for t in summary.get("tags") or [] if t["kind"] in ("airline_hub", "multi_hub")),
                None,
            )
            if hub is None:
                continue

            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            origins = {t["origin_airport"] for t in detail["trips"] if t["origin_airport"]}
            assert len(origins) == 1, summary["traveler_id"]
            origin = origins.pop()
            assert (
                origin in hub["hub_airports"] or SECONDARY.get(origin) == hub["hub_city"]
            ), f"{summary['traveler_id']} flies {origin}, tagged for {hub['hub_city']}"
            checked += 1

        if checked == 0:
            pytest.skip("traveler_tags.json not generated in this checkout")

    def test_every_destination_country_resolves_to_an_m49_region(self, client):
        # Coverage, asserted rather than assumed. M49 covers 248 countries and
        # areas but NOT Taiwan, which this dataset visits -- build_m49_regions.py
        # supplies that one as a documented addition. If a new destination
        # country appears in the trip data and isn't in M49 either, its trips
        # would silently drop out of the region chart's denominator; this is
        # what makes that loud instead.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        unresolved, checked = set(), 0
        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            for trip in detail["trips"]:
                if trip["destination_subregion"] is None:
                    unresolved.add((trip["destination_country_code"], trip["destination_country"]))
                else:
                    checked += 1

        if checked == 0:
            pytest.skip("m49_regions.json not built in this checkout")
        assert not unresolved, f"destination countries with no M49 region: {sorted(unresolved)}"

    def test_region_and_subregion_agree_with_each_other(self, client):
        # M49's own rule is that each country appears in exactly one region,
        # so the two fields can never disagree -- a subregion always implies
        # its parent region. Catches an index built from a half-parsed file.
        PARENT = {
            "Northern Africa": "Africa", "Eastern Africa": "Africa",
            "Middle Africa": "Africa", "Southern Africa": "Africa",
            "Western Africa": "Africa",
            "Caribbean": "Americas", "Central America": "Americas",
            "South America": "Americas", "Northern America": "Americas",
            "Central Asia": "Asia", "Eastern Asia": "Asia",
            "South-eastern Asia": "Asia", "Southern Asia": "Asia",
            "Western Asia": "Asia",
            "Eastern Europe": "Europe", "Northern Europe": "Europe",
            "Southern Europe": "Europe", "Western Europe": "Europe",
            "Australia and New Zealand": "Oceania", "Melanesia": "Oceania",
            "Micronesia": "Oceania", "Polynesia": "Oceania",
        }
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        seen, checked = {}, 0
        for summary in body["travelers"][:40]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            for trip in detail["trips"]:
                subregion = trip["destination_subregion"]
                if subregion is None:
                    continue
                # One of the 22, never M49's coarser "Latin America and the
                # Caribbean" or "Sub-Saharan Africa" -- those are the parents
                # the detailed tier exists to replace.
                assert subregion in PARENT, subregion
                assert trip["destination_region"] == PARENT[subregion], trip
                # And the join is 1:1: one country code, one region, always.
                code = trip["destination_country_code"]
                assert seen.setdefault(code, subregion) == subregion, code
                checked += 1

        if checked == 0:
            pytest.skip("m49_regions.json not built in this checkout")

    def test_mexico_is_central_america_not_lumped_with_south_america(self, client):
        # The whole reason the charted tier is the intermediate region rather
        # than M49's literal sub-region. On the literal tier Mexico, Jamaica,
        # Costa Rica and Argentina all read as one "Latin America and the
        # Caribbean" segment -- and with 341 Mexico trips that segment would
        # be most of the non-domestic bar.
        EXPECTED = {
            "MX": ("Americas", "Central America"),
            "JM": ("Americas", "Caribbean"),
            "AR": ("Americas", "South America"),
            "US": ("Americas", "Northern America"),
            "JP": ("Asia", "Eastern Asia"),
            "GB": ("Europe", "Northern Europe"),
        }
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        found = {}
        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            for trip in detail["trips"]:
                code = trip["destination_country_code"]
                if code in EXPECTED and trip["destination_subregion"]:
                    found[code] = (trip["destination_region"], trip["destination_subregion"])
            if len(found) == len(EXPECTED):
                break

        if not found:
            pytest.skip("m49_regions.json not built in this checkout")
        for code, expected in EXPECTED.items():
            if code in found:
                assert found[code] == expected, code

    def test_region_entropy_covers_every_traveler_unlike_the_airport_one(self, client):
        # The reason the region unit exists. Only hand-authored itineraries
        # record an airport, so airport entropy is null for most travelers;
        # every trip records a destination country and every country resolves
        # to an M49 region, so the region one is defined for all of them.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        with_airport = with_region = 0
        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            region = detail.get("region_entropy")
            airport = detail.get("destination_entropy")
            if region is None:
                pytest.skip("traveler_entropy_region.json not generated in this checkout")
            if airport and airport["entropy"] is not None:
                with_airport += 1
            if region["entropy"] is not None:
                with_region += 1
                assert region["destination_unit"] == "region", summary["traveler_id"]
                # Fixed denominator: every M49 detailed region there is, not
                # the subset this dataset visits -- so a score doesn't
                # rescale when a trip to a new region is added.
                assert region["global_distinct_destinations"] == 22, summary["traveler_id"]

        assert with_region == len(body["travelers"])
        assert with_airport < with_region  # the whole point

    def test_the_two_entropies_are_separate_and_consistent(self, client):
        # They measure the same trips at different grains, so region can
        # never be the finer one: you cannot visit more regions than
        # airports. A traveler with high airport entropy and zero region
        # entropy is the interesting case and must be representable.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        checked = 0
        for summary in body["travelers"]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            airport, region = detail.get("destination_entropy"), detail.get("region_entropy")
            if not airport or not region:
                continue
            if airport["entropy"] is None or region["entropy"] is None:
                continue

            assert airport["destination_unit"] == "airport", summary["traveler_id"]
            # Coarser unit, so never more categories and never more spread.
            assert region["n_destinations"] <= airport["n_destinations"], summary["traveler_id"]
            assert region["entropy"] <= airport["entropy"] + 1e-9, summary["traveler_id"]
            # Same trips counted either way for these travelers -- both units
            # are derivable from every hand-authored trip.
            assert region["trips_with_destination"] == airport["trips_with_destination"]
            checked += 1

        if checked == 0:
            pytest.skip("entropy files not generated in this checkout")

    def test_normalized_region_entropy_uses_the_fixed_22(self, client):
        # Guards the choice itself: dividing by the 14 regions this dataset
        # happens to visit would make every score jump the moment a 15th
        # appeared. ln(22) = 3.0910.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        checked = 0
        for summary in body["travelers"][:40]:
            detail = client.get(f"/api/travelers/{summary['traveler_id']}").json()
            region = detail.get("region_entropy")
            if not region or region["entropy"] is None or region["normalized"] is None:
                continue
            expected = region["entropy"] / math.log(22)
            assert region["normalized"] == pytest.approx(expected, abs=1e-3), summary["traveler_id"]
            assert 0.0 <= region["normalized"] <= 1.0, summary["traveler_id"]
            checked += 1

        if checked == 0:
            pytest.skip("traveler_entropy_region.json not generated in this checkout")

    def test_traveler_ids_are_unique_and_url_safe(self, client):
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        ids = [t["traveler_id"] for t in body["travelers"]]
        assert len(ids) == len(set(ids))  # a collision would make one traveler unreachable
        assert all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids)

    def test_detail_returns_every_trip_for_that_traveler(self, client):
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        summary = body["travelers"][0]
        res = client.get(f"/api/travelers/{summary['traveler_id']}")
        assert res.status_code == 200
        detail = res.json()
        assert detail["name"] == summary["name"]
        assert len(detail["trips"]) == summary["trip_count"]
        assert all(trip["destination_raw"] for trip in detail["trips"])

    def test_every_trip_has_a_resolved_destination_country(self, client):
        # build_trips_enhanced.py resolves every destination string through a
        # hand-written table and refuses to write an unmapped one, so a trip
        # reaching the API without a country means that guarantee broke
        # somewhere between the table and here.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        for summary in body["travelers"]:
            for trip in client.get(f"/api/travelers/{summary['traveler_id']}").json()["trips"]:
                assert trip["destination_country"], trip
                assert len(trip["destination_country_code"]) == 2
                assert trip["destination_kind"] in ("city", "region", "country")
                # A city is absent only when the source named no city at all;
                # any other combination means the split lost information.
                assert (trip["destination_city"] is None) == (trip["destination_kind"] == "country")

    def test_every_listed_traveler_has_a_reachable_detail_page(self, client):
        # Same reasoning as the equivalent city and visa tests: a card the
        # grid can link to must resolve, and finding that out shouldn't
        # depend on which card someone happens to click.
        body = client.get("/api/travelers").json()
        if not body["dataset_available"]:
            pytest.skip("travelers.json not generated in this checkout")

        for traveler in body["travelers"]:
            res = client.get(f"/api/travelers/{traveler['traveler_id']}")
            assert res.status_code == 200, f"{traveler['traveler_id']} returned {res.status_code}"

    def test_unknown_traveler_id_is_404(self, client):
        res = client.get("/api/travelers/not-a-real-traveler")
        assert res.status_code == 404

    def test_health_reports_traveler_coverage(self, client):
        body = client.get("/health").json()
        assert "travelers_loaded" in body
        count = body["travelers_loaded"]
        assert count is None or count >= 0
