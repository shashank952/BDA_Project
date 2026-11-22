"""Numerical-correctness tests for the metric definitions.

Expected values are hand-calculated from tests/fixtures/sample_flights.csv:

  valid departure measurements : 10 flights, delays sum 227  -> avg 22.70
  valid arrival measurements   :  9 flights, delays sum 219  -> avg 24.3333
  arrival delays >= 15 min     :  6 of 9  -> 66.6667 %
  departure delays >= 15 min   :  6 of 10 -> 60.0 %
  cancellations                :  1 of 11 -> 9.0909 %
"""

from __future__ import annotations

import pytest

from src.common.metrics import (
    airline_performance,
    airport_performance,
    cancellation_codes,
    cancellation_summary,
    delay_cause_summary,
    delay_category_counts,
    monthly_trends,
    route_performance,
    summary,
)
from src.common.spec import safe_rate


@pytest.fixture()
def frame(cleaned_fixture):
    return cleaned_fixture["cleaned"]


def test_summary_kpis(frame):
    result = summary(frame)
    assert result["total_flights"] == 11
    assert result["valid_departure_flights"] == 10
    assert result["valid_arrival_flights"] == 9
    assert result["avg_departure_delay"] == pytest.approx(22.7, abs=1e-4)
    assert result["avg_arrival_delay"] == pytest.approx(24.3333, abs=1e-3)
    assert result["departure_delayed_flights"] == 6
    assert result["arrival_delayed_flights"] == 6
    assert result["departure_delay_rate"] == pytest.approx(60.0, abs=1e-3)
    assert result["arrival_delay_rate"] == pytest.approx(66.6667, abs=1e-3)
    assert result["cancelled_flights"] == 1
    assert result["cancellation_rate"] == pytest.approx(9.0909, abs=1e-3)
    assert result["diverted_flights"] == 1


def test_airline_performance_matches_hand_calculation(frame):
    result = airline_performance(frame).set_index("airline_code")

    aa = result.loc["AA"]
    assert aa["total_flights"] == 3
    assert aa["valid_arrival_flights"] == 2
    assert aa["avg_arrival_delay"] == pytest.approx(9.0, abs=1e-4)
    assert aa["delayed_arrivals"] == 1
    assert aa["arrival_delay_rate"] == pytest.approx(50.0, abs=1e-3)

    ua = result.loc["UA"]
    assert ua["total_flights"] == 2
    assert ua["valid_arrival_flights"] == 1
    assert ua["cancellations"] == 1
    assert ua["cancellation_rate"] == pytest.approx(50.0, abs=1e-3)

    assert result.loc["B6", "arrival_delay_rate"] == pytest.approx(0.0)
    assert result["valid_arrival_flights"].sum() == 9


def test_airport_roles_are_reported_separately(frame):
    result = airport_performance(frame)
    assert set(result["role"]) == {"departure", "arrival"}

    jfk_departure = result[(result["airport_code"] == "JFK") & (result["role"] == "departure")].iloc[0]
    assert jfk_departure["total_flights"] == 3
    assert jfk_departure["valid_delay_flights"] == 3
    assert jfk_departure["avg_delay"] == pytest.approx(9.6667, abs=1e-3)
    assert jfk_departure["delay_rate"] == pytest.approx(33.3333, abs=1e-3)

    lax_arrival = result[(result["airport_code"] == "LAX") & (result["role"] == "arrival")].iloc[0]
    assert lax_arrival["valid_delay_flights"] == 2
    assert lax_arrival["avg_delay"] == pytest.approx(9.0, abs=1e-4)
    assert lax_arrival["delay_rate"] == pytest.approx(50.0, abs=1e-3)

    sfo_arrival = result[(result["airport_code"] == "SFO") & (result["role"] == "arrival")].iloc[0]
    assert sfo_arrival["total_flights"] == 2
    assert sfo_arrival["valid_delay_flights"] == 1


def test_monthly_trends_cover_multiple_months(frame):
    result = monthly_trends(frame).set_index(["flight_year", "flight_month"])

    january = result.loc[(2025, 1)]
    assert january["total_flights"] == 10
    assert january["valid_arrival_flights"] == 8
    assert january["avg_arrival_delay"] == pytest.approx(26.375, abs=1e-3)
    assert january["arrival_delay_rate"] == pytest.approx(75.0, abs=1e-3)
    assert january["cancellation_rate"] == pytest.approx(10.0, abs=1e-3)

    december = result.loc[(2024, 12)]
    assert december["total_flights"] == 1
    assert december["avg_arrival_delay"] == pytest.approx(8.0)
    assert december["arrival_delay_rate"] == pytest.approx(0.0)


def test_delay_category_distribution(frame):
    result = delay_category_counts(frame).set_index("delay_category")
    assert result.loc["on_time", "flights"] == 3
    assert result.loc["minor", "flights"] == 3
    assert result.loc["moderate", "flights"] == 2
    assert result.loc["severe", "flights"] == 1
    assert result.loc["unknown", "flights"] == 2
    assert result["flights"].sum() == 11
    assert result.loc["severe", "share_pct"] == pytest.approx(9.0909, abs=1e-3)


def test_delay_causes_use_reported_minutes_only(frame):
    result = delay_cause_summary(frame).set_index("cause")
    assert result.loc["Carrier", "delay_minutes"] == pytest.approx(40.0)
    assert result.loc["Weather", "delay_minutes"] == pytest.approx(10.0)
    assert result.loc["National Aviation System", "delay_minutes"] == pytest.approx(5.0)
    assert result.loc["Security", "delay_minutes"] == pytest.approx(0.0)
    assert result.loc["Late aircraft", "delay_minutes"] == pytest.approx(5.0)
    assert result["delay_minutes"].sum() == pytest.approx(60.0)
    assert result.loc["Carrier", "share_pct"] == pytest.approx(66.6667, abs=1e-3)
    assert result.loc["Carrier", "flights_with_cause"] == 1


def test_route_performance_respects_minimum_flights(frame):
    all_routes = route_performance(frame, min_flights=1).set_index("route")
    assert all_routes.loc["JFK-LAX", "total_flights"] == 3
    assert all_routes.loc["JFK-LAX", "valid_arrival_flights"] == 2
    assert all_routes.loc["JFK-LAX", "avg_arrival_delay"] == pytest.approx(9.0)
    assert all_routes.loc["JFK-LAX", "arrival_delay_rate"] == pytest.approx(50.0)

    filtered = route_performance(frame, min_flights=3)
    assert list(filtered["route"]) == ["JFK-LAX"]


def test_cancellation_summary_and_codes(frame):
    result = cancellation_summary(frame).set_index(["airline_code", "flight_year", "flight_month"])
    ua = result.loc[("UA", 2025, 1)]
    assert ua["cancellations"] == 1
    assert ua["total_flights"] == 2
    assert ua["cancellation_rate"] == pytest.approx(50.0)

    codes = cancellation_codes(frame).set_index("cancellation_code")
    assert codes.loc["B", "flights"] == 1


def test_safe_rate_guards_zero_denominator():
    assert safe_rate(0, 0) is None
    assert safe_rate(1, 0) is None
    assert safe_rate(1, 4) == pytest.approx(25.0)
