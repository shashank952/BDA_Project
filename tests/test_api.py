"""API tests against a small analytics fixture built from the cleaned dataset.

The fixture is written to a temporary directory and pointed at with
AIRLINE_ANALYTICS_DIR / AIRLINE_REPORTS_DIR, so the tests never depend on
whatever happens to be in outputs/ on this machine.
"""

from __future__ import annotations

import json

import pytest

from src.backend.app import create_app
from src.backend import services
from src.common import metrics


def _write(path, frame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


@pytest.fixture()
def client(tmp_path, monkeypatch, cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    analytics = tmp_path / "analytics"
    reports = tmp_path / "reports"
    analytics.mkdir(parents=True)
    reports.mkdir(parents=True)

    _write(analytics / "airline_performance.csv", metrics.airline_performance(frame))
    _write(analytics / "airport_performance.csv", metrics.airport_performance(frame))
    _write(analytics / "monthly_trends.csv", metrics.monthly_trends(frame))
    _write(analytics / "route_performance.csv", metrics.route_performance(frame, min_flights=0))
    _write(analytics / "delay_categories.csv", metrics.delay_category_counts(frame))
    _write(analytics / "delay_causes.csv", metrics.delay_cause_summary(frame))
    _write(analytics / "cancellations.csv", metrics.cancellation_summary(frame))
    _write(analytics / "cancellation_airports.csv", metrics.cancellation_by_airport(frame))
    _write(analytics / "day_of_week.csv", metrics.day_of_week_performance(frame))
    _write(analytics / "summary.csv", _summary_frame(frame))

    monkeypatch.setenv("AIRLINE_ANALYTICS_DIR", str(analytics))
    monkeypatch.setenv("AIRLINE_REPORTS_DIR", str(reports))
    services._read_cached.cache_clear()

    app = create_app({"TESTING": True})
    with app.test_client() as test_client:
        yield test_client


def _summary_frame(frame):
    import pandas as pd

    result = metrics.summary(frame)
    result["first_date"] = "2024-12-31"
    result["last_date"] = "2025-01-12"
    return pd.DataFrame([result])


def test_health_reports_available_outputs(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert "summary" in payload["analytics_available"]


def test_summary_kpis(client):
    response = client.get("/api/summary")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["totals"]["total_flights"] == 11
    assert payload["totals"]["cancelled_flights"] == 1
    assert payload["rates"]["arrival_delay_rate"] == pytest.approx(66.6667, abs=1e-3)
    assert payload["period"] == {"from": "2024-12-31", "to": "2025-01-12"}


def test_airlines_default_sorted_by_delay_rate(client):
    response = client.get("/api/airlines")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["pagination"]["total"] == 6
    rates = [row["arrival_delay_rate"] for row in payload["data"]]
    assert rates == sorted(rates, reverse=True)
    assert payload["data"][0]["airline_name"]


def test_airline_filter_is_case_insensitive(client):
    response = client.get("/api/airlines?airline=aa")
    payload = response.get_json()
    assert payload["pagination"]["total"] == 1
    row = payload["data"][0]
    assert row["airline_code"] == "AA"
    assert row["airline_name"] == "American Airlines"
    assert row["valid_arrival_flights"] == 2


def test_pagination_envelope(client):
    response = client.get("/api/airlines?limit=2&offset=1")
    payload = response.get_json()
    assert payload["pagination"] == {"total": 6, "limit": 2, "offset": 1, "returned": 2}
    assert len(payload["data"]) == 2


def test_limit_validation(client):
    assert client.get("/api/airlines?limit=0").status_code == 400
    assert client.get("/api/airlines?limit=abc").status_code == 400
    response = client.get("/api/airlines?limit=99999")
    assert response.status_code == 400
    assert "limit" in response.get_json()["error"]["message"]


def test_airport_role_filter_and_validation(client):
    arrival = client.get("/api/airports?role=arrival").get_json()
    assert {row["role"] for row in arrival["data"]} == {"arrival"}

    bad = client.get("/api/airports?role=sideways")
    assert bad.status_code == 400
    assert "role" in bad.get_json()["error"]["message"]


def test_airports_min_flights_filter(client):
    payload = client.get("/api/airports?role=arrival&min_flights=2").get_json()
    assert all(row["total_flights"] >= 2 for row in payload["data"])


def test_routes_respect_minimum_flight_count(client):
    payload = client.get("/api/routes?min_flights=3").get_json()
    assert payload["pagination"]["total"] == 1
    assert payload["data"][0]["route"] == "JFK-LAX"


def test_monthly_trends_are_chronological(client):
    payload = client.get("/api/trends/monthly").get_json()
    keys = [(row["flight_year"], row["flight_month"]) for row in payload["data"]]
    assert keys == sorted(keys)
    assert payload["pagination"]["total"] == 2


def test_monthly_year_filter(client):
    payload = client.get("/api/trends/monthly?year_from=2025").get_json()
    assert payload["data"][0]["flight_year"] == 2025
    assert client.get("/api/trends/monthly?year_from=2026&year_to=2020").status_code == 400


def test_delay_causes_and_categories(client):
    causes = client.get("/api/delay-causes").get_json()
    assert len(causes["data"]) == 5
    assert causes["data"][0]["cause"] == "Carrier"
    assert causes["data"][0]["delay_minutes"] == pytest.approx(40.0)

    categories = client.get("/api/delay-categories").get_json()
    assert [row["delay_category"] for row in categories["data"]][0] == "on_time"


def test_cancellations_filter_by_month(client):
    payload = client.get("/api/cancellations?year=2025&month=1").get_json()
    assert payload["pagination"]["total"] > 0
    ua = [row for row in payload["data"] if row["airline_code"] == "UA"][0]
    assert ua["cancellations"] == 1
    assert ua["cancellation_rate"] == pytest.approx(50.0)


def test_metadata_shape(client):
    payload = client.get("/api/metadata").get_json()
    assert "dataset" in payload and "processing" in payload
    assert "summary" in payload["analyses"]


def test_unknown_endpoint_returns_json_404(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.get_json()["error"]["type"] == "not_found"


def test_missing_outputs_return_503(tmp_path, monkeypatch):
    monkeypatch.setenv("AIRLINE_ANALYTICS_DIR", str(tmp_path / "empty"))
    services._read_cached.cache_clear()
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        response = client.get("/api/summary")
    assert response.status_code == 503
    assert response.get_json()["error"]["type"] == "analysis_unavailable"


def test_error_payloads_do_not_leak_paths(client, tmp_path):
    response = client.get("/api/routes?sort=../../etc/passwd")
    assert response.status_code == 400
    body = json.dumps(response.get_json())
    assert "passwd" not in body
