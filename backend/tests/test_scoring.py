"""
Unit tests for app/scoring.py -- pure functions over plain dicts/dates,
no file I/O, so these run with no fixtures beyond hand-built inputs. See
that module's own docstring for the formulas being verified here; this
file exists to pin those formulas down with worked examples so a future
refactor can't silently change the math.
"""

import math
from datetime import date

import pytest

from app.scoring import (
    RAW_WEATHER_METRIC_KEYS,
    combine_domain_scores,
    great_circle_distance_km,
    month_weights,
    resolve_rainy_days_estimate,
    resolve_weather_metrics,
    resolve_weather_score,
    weather_score_from_monthly_metrics,
)


class TestMonthWeights:
    def test_single_day(self):
        assert month_weights(date(2026, 7, 4), date(2026, 7, 4)) == {"july": 1.0}

    def test_range_within_one_month(self):
        assert month_weights(date(2026, 7, 1), date(2026, 7, 10)) == {"july": 1.0}

    def test_spans_two_months_day_weighted(self):
        # May 28 - Jun 3 inclusive = 7 days: May 28,29,30,31 (4 days),
        # Jun 1,2,3 (3 days).
        weights = month_weights(date(2026, 5, 28), date(2026, 6, 3))
        assert weights == pytest.approx({"may": 4 / 7, "june": 3 / 7})

    def test_spans_three_months(self):
        # Jan 30,31 (2), Feb 1-28 (28, 2026 isn't a leap year), Mar 1,2 (2)
        # -> 32 total days.
        weights = month_weights(date(2026, 1, 30), date(2026, 3, 2))
        assert weights == pytest.approx({"january": 2 / 32, "february": 28 / 32, "march": 2 / 32})

    def test_weights_always_sum_to_one(self):
        weights = month_weights(date(2026, 11, 20), date(2027, 1, 15))
        assert sum(weights.values()) == pytest.approx(1.0)

    def test_end_before_start_raises(self):
        with pytest.raises(ValueError):
            month_weights(date(2026, 7, 10), date(2026, 7, 1))

    def test_year_agnostic(self):
        # Weather normals are a single representative year applied to any
        # year's dates -- same month span in a different year must
        # produce identical weights.
        assert month_weights(date(2026, 6, 1), date(2026, 6, 10)) == month_weights(date(2031, 6, 1), date(2031, 6, 10))


class TestResolveWeatherScore:
    def test_none_when_no_monthly_scores(self):
        assert resolve_weather_score(None, {"july": 1.0}) is None

    def test_single_month_passthrough(self):
        assert resolve_weather_score({"july": 8.0}, {"july": 1.0}) == 8.0

    def test_weighted_average_across_months(self):
        monthly = {"july": 10.0, "august": 8.0}
        weights = {"july": 0.3, "august": 0.7}
        assert resolve_weather_score(monthly, weights) == pytest.approx(0.3 * 10 + 0.7 * 8)


class TestResolveWeatherMetrics:
    def test_none_when_no_metrics(self):
        assert resolve_weather_metrics(None, {"july": 1.0}) is None

    def test_matches_docstring_worked_example(self):
        # avg_sunshine_hours=10 in July, 8 in August, 30%/70% split ->
        # 0.3*10 + 0.7*8 = 8.6 (this file's own docstring example).
        monthly = {
            "july": {k: (10 if k == "avg_sunshine_hours" else 1) for k in RAW_WEATHER_METRIC_KEYS},
            "august": {k: (8 if k == "avg_sunshine_hours" else 1) for k in RAW_WEATHER_METRIC_KEYS},
        }
        result = resolve_weather_metrics(monthly, {"july": 0.3, "august": 0.7})
        assert result["avg_sunshine_hours"] == pytest.approx(8.6)

    def test_returns_exactly_the_raw_metric_keys(self):
        monthly = {"july": {k: 5.0 for k in RAW_WEATHER_METRIC_KEYS}}
        result = resolve_weather_metrics(monthly, {"july": 1.0})
        assert set(result.keys()) == set(RAW_WEATHER_METRIC_KEYS)


class TestResolveRainyDaysEstimate:
    def test_none_when_no_metrics(self):
        assert resolve_rainy_days_estimate(None, {"july": 1.0}, 7) is None

    def test_worked_example(self):
        # 7-day trip, 30% July (5 rainy days / 31 sampled), 70% August
        # (10 rainy days / 31 sampled) -> weighted daily-rain fraction
        # scaled by trip length.
        monthly = {
            "july": {"rainy_days": 5, "days_sampled": 31},
            "august": {"rainy_days": 10, "days_sampled": 31},
        }
        result = resolve_rainy_days_estimate(monthly, {"july": 0.3, "august": 0.7}, trip_days=7)
        expected = (0.3 * (5 / 31) + 0.7 * (10 / 31)) * 7
        assert result == pytest.approx(round(expected, 2))

    def test_scales_linearly_with_trip_length(self):
        # A trip covering the whole sampled month should land back on
        # that month's raw rainy_days count.
        monthly = {"july": {"rainy_days": 10, "days_sampled": 31}}
        weights = {"july": 1.0}
        full_month_trip = resolve_rainy_days_estimate(monthly, weights, trip_days=31)
        assert full_month_trip == pytest.approx(10.0)

        # A 7-day trip should land on roughly 7/31 of that, within the
        # function's own 2-decimal rounding (comparing against the
        # unrounded fraction directly, rather than against the ALREADY
        # -rounded 7-day figure re-scaled by 31/7 -- that derived
        # comparison compounds two roundings and fails a tight tolerance
        # despite both individual numbers being correct).
        short_trip = resolve_rainy_days_estimate(monthly, weights, trip_days=7)
        assert short_trip == pytest.approx((10 / 31) * 7, abs=0.01)

    def test_uses_days_sampled_not_a_hardcoded_thirty(self):
        # A month sampled over only 28 days should differ from one
        # sampled over 31, even with the same rainy_days count -- proves
        # days_sampled (not a hardcoded ~30) drives the fraction.
        monthly_28 = {"february": {"rainy_days": 7, "days_sampled": 28}}
        monthly_31 = {"february": {"rainy_days": 7, "days_sampled": 31}}
        weights = {"february": 1.0}
        assert resolve_rainy_days_estimate(monthly_28, weights, 28) != resolve_rainy_days_estimate(
            monthly_31, weights, 28
        )


class TestCombineDomainScores:
    def test_all_four_present_averages_all_four(self):
        score, count = combine_domain_scores(8.0, 6.0, 4.0, 10.0)
        assert score == pytest.approx((8 + 6 + 4 + 10) / 4)
        assert count == 4

    def test_missing_weather_averages_the_other_three(self):
        score, count = combine_domain_scores(8.0, 6.0, 4.0, None)
        assert score == pytest.approx((8 + 6 + 4) / 3)
        assert count == 3

    def test_all_none_returns_none_and_zero(self):
        assert combine_domain_scores(None, None, None, None) == (None, 0)

    def test_only_one_domain_present(self):
        assert combine_domain_scores(None, None, None, 7.5) == (7.5, 1)

    def test_zero_is_a_real_score_not_treated_as_missing(self):
        # 0.0 (e.g. a country with no UNESCO sites) must be averaged in,
        # not dropped the way None is -- `if v is not None`, not `if v`.
        score, count = combine_domain_scores(0.0, 0.0, 0.0, 0.0)
        assert score == 0.0
        assert count == 4


class TestGreatCircleDistanceKm:
    def test_same_point_is_zero(self):
        assert great_circle_distance_km(35.0, 139.0, 35.0, 139.0) == pytest.approx(0.0, abs=1e-6)

    def test_symmetric(self):
        a = great_circle_distance_km(51.5074, -0.1278, 48.8566, 2.3522)  # London -> Paris
        b = great_circle_distance_km(48.8566, 2.3522, 51.5074, -0.1278)  # Paris -> London
        assert a == pytest.approx(b)

    def test_known_distance_london_to_paris(self):
        # Well-known reference value (~344km great-circle).
        distance = great_circle_distance_km(51.5074, -0.1278, 48.8566, 2.3522)
        assert distance == pytest.approx(344, rel=0.02)

    def test_antipodal_points_are_half_earth_circumference(self):
        distance = great_circle_distance_km(0, 0, 0, 180)
        assert distance == pytest.approx(math.pi * 6371.0088, rel=1e-6)


class TestWeatherScoreFromMonthlyMetrics:
    def test_perfect_weather_scores_ten(self):
        metrics = {
            "monthly_rain_score": 0.0,
            "daily_rain_score": 0.0,
            "daylight_hours_score": 1.0,
            "high_temperature_score": 1.0,
            "low_temperature_score": 1.0,
            "wind_intensity_score": 0.0,
        }
        assert weather_score_from_monthly_metrics(metrics) == 10.0

    def test_worst_weather_scores_zero(self):
        metrics = {
            "monthly_rain_score": 1.0,
            "daily_rain_score": 1.0,
            "daylight_hours_score": 0.0,
            "high_temperature_score": 0.0,
            "low_temperature_score": 0.0,
            "wind_intensity_score": 1.0,
        }
        assert weather_score_from_monthly_metrics(metrics) == 0.0

    def test_matches_hand_computed_value(self):
        metrics = {
            "monthly_rain_score": 0.2,
            "daily_rain_score": 0.4,
            "daylight_hours_score": 0.8,
            "high_temperature_score": 1.0,
            "low_temperature_score": 0.6,
            "wind_intensity_score": 0.3,
        }
        dryness = 1 - (0.2 + 0.4) / 2
        daylight = 0.8
        temperature = (1.0 + 0.6) / 2
        calm = 1 - 0.3
        expected = round((dryness + daylight + temperature + calm) / 4 * 10, 2)
        assert weather_score_from_monthly_metrics(metrics) == expected
