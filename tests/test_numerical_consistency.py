"""Cross-layer numerical consistency.

Asserts that the same metric has the same value in:
  * the MapReduce exports (outputs/analytics/mapreduce/*.csv)
  * the Hive exports      (outputs/analytics/*.csv)
  * the Flask API         (/api/airlines, /api/airports, /api/summary, ...)

These tests are skipped when the corresponding artifacts have not been
generated yet, so a fresh checkout can still run the rest of the suite.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.backend.app import create_app
from src.common import metrics
from src.common.config import load_settings

TOLERANCE = 0.01
MR_DIR = "mapreduce"


def _analytics_dir() -> Path:
    return load_settings().path("analytics_outputs")


def _require(path: Path):
    if not path.exists():
        pytest.skip(f"missing artifact: {path.name}")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def reference_frame() -> pd.DataFrame:
    settings = load_settings()
    paths = sorted(settings.path("data_processed").glob("year=*/month=*/flights.csv"))
    if not paths:
        pytest.skip("no cleaned partitions available")
    return pd.concat([metrics.load_cleaned_csv(path) for path in paths], ignore_index=True)


@pytest.mark.parametrize(
    "name,keys,values",
    [
        ("airline_performance", ["airline_code"], ["total_flights", "avg_arrival_delay", "arrival_delay_rate"]),
        ("airport_performance", ["role", "airport_code"], ["total_flights", "avg_delay", "delay_rate"]),
        ("monthly_trends", ["flight_year", "flight_month"], ["total_flights", "avg_arrival_delay", "arrival_delay_rate"]),
        ("route_performance", ["route"], ["total_flights", "avg_arrival_delay", "arrival_delay_rate"]),
    ],
)
def test_mapreduce_and_hive_agree(name, keys, values):
    mapreduce = _require(_analytics_dir() / MR_DIR / f"{name}.csv")
    hive = _require(_analytics_dir() / f"{name}.csv")

    merged = mapreduce.merge(hive, on=keys, suffixes=("_mr", "_hive"))
    assert len(merged) == len(hive), "row sets differ between MapReduce and Hive"
    for column in values:
        delta = (pd.to_numeric(merged[f"{column}_mr"]) - pd.to_numeric(merged[f"{column}_hive"])).abs()
        assert delta.max() < TOLERANCE, f"{name}.{column} differs: worst {delta.max()}"


def test_hive_outputs_match_reference(reference_frame):
    from src.common.validate import compare_file

    problems = []
    for name in ("airline_performance", "airport_performance", "monthly_trends", "route_performance", "summary"):
        path = _analytics_dir() / f"{name}.csv"
        problems.extend(compare_file(name, path, reference_frame))
    assert not problems, problems


def test_api_matches_hive_outputs():
    hive = _require(_analytics_dir() / "airline_performance.csv")
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        payload = client.get("/api/airlines?limit=500").get_json()
    assert payload["pagination"]["total"] == len(hive)

    api = pd.DataFrame(payload["data"])
    merged = hive.merge(api, on="airline_code", suffixes=("_hive", "_api"))
    for column in ("total_flights", "valid_arrival_flights", "delayed_arrivals"):
        assert (merged[f"{column}_hive"] == merged[f"{column}_api"]).all(), column
    for column in ("avg_arrival_delay", "arrival_delay_rate", "cancellation_rate"):
        delta = (merged[f"{column}_hive"] - merged[f"{column}_api"]).abs()
        assert delta.max() < TOLERANCE, column


def test_api_summary_matches_hive_summary():
    hive = _require(_analytics_dir() / "summary.csv").iloc[0]
    app = create_app({"TESTING": True})
    with app.test_client() as client:
        payload = client.get("/api/summary").get_json()

    assert payload["totals"]["total_flights"] == int(hive["total_flights"])
    assert payload["rates"]["arrival_delay_rate"] == pytest.approx(float(hive["arrival_delay_rate"]), abs=TOLERANCE)
    assert payload["rates"]["cancellation_rate"] == pytest.approx(float(hive["cancellation_rate"]), abs=TOLERANCE)
    assert payload["averages"]["arrival_delay_minutes"] == pytest.approx(float(hive["avg_arrival_delay"]), abs=TOLERANCE)


def test_delay_cause_totals_are_internally_consistent():
    causes = _require(_analytics_dir() / "delay_causes.csv")
    shares = causes["share_pct"].sum()
    assert shares == pytest.approx(100.0, abs=0.05)
    assert (causes["delay_minutes"] >= 0).all()
