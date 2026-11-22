"""MapReduce correctness tests without a cluster.

The mapper and reducer scripts are executed as real subprocesses over the
cleaned fixture, with an explicit key sort between the stages to emulate the
shuffle, and the result is compared with the pandas reference implementation.
The combiner is exercised too, since a combiner that is not mathematically safe
would silently change the totals.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.common import metrics
from src.mapreduce.run_jobs import JOBS, MAPREDUCE_DIR


def _sort_like_shuffle(lines: list[str]) -> list[str]:
    return sorted(lines, key=lambda line: line.split("\t", 1)[0])


def _run(script: str, lines: list[str]) -> list[str]:
    result = subprocess.run(
        [sys.executable, str(MAPREDUCE_DIR / script)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"{script} failed: {result.stderr}"
    return [line for line in result.stdout.splitlines() if line.strip()]


def _execute_job(name: str, csv_text: str, use_combiner: bool) -> pd.DataFrame:
    spec = JOBS[name]
    source_lines = csv_text.splitlines()
    mapped = _run(spec.mapper, source_lines)

    if use_combiner:
        combined = _run("numeric_sum_combiner.py", _sort_like_shuffle(mapped))
        shuffled = _sort_like_shuffle(combined)
    else:
        shuffled = _sort_like_shuffle(mapped)

    reduced = _run(spec.reducer, shuffled)
    return pd.read_csv(pd.io.common.StringIO("\n".join([spec.header, *reduced])))


@pytest.fixture(scope="module")
def fixture_frame(cleaned_fixture):
    return cleaned_fixture["cleaned"]


@pytest.fixture(scope="module")
def fixture_text(cleaned_fixture):
    return cleaned_fixture["cleaned"].to_csv(index=False, lineterminator="\n")


@pytest.mark.parametrize("use_combiner", [False, True])
def test_airline_job_matches_reference(fixture_frame, fixture_text, use_combiner):
    produced = _execute_job("airline_performance", fixture_text, use_combiner).set_index("airline_code")
    expected = metrics.airline_performance(fixture_frame).set_index("airline_code")
    assert produced.loc["AA", "total_flights"] == expected.loc["AA", "total_flights"]
    assert produced.loc["AA", "avg_arrival_delay"] == pytest.approx(expected.loc["AA", "avg_arrival_delay"], abs=0.01)
    assert produced.loc["UA", "cancellations"] == expected.loc["UA", "cancellations"]
    assert produced["valid_arrival_flights"].sum() == expected["valid_arrival_flights"].sum()


@pytest.mark.parametrize("use_combiner", [False, True])
def test_airport_job_keeps_roles_separate(fixture_frame, fixture_text, use_combiner):
    produced = _execute_job("airport_performance", fixture_text, use_combiner)
    expected = metrics.airport_performance(fixture_frame)
    assert set(produced["role"]) == {"departure", "arrival"}

    key = ["role", "airport_code"]
    merged = produced.merge(expected, on=key, suffixes=("_mr", "_ref"))
    assert len(merged) == len(expected)
    for column in ("total_flights", "valid_delay_flights", "delayed_flights"):
        assert (merged[f"{column}_mr"] == merged[f"{column}_ref"]).all(), column
    for column in ("avg_delay", "delay_rate"):
        delta = (merged[f"{column}_mr"] - merged[f"{column}_ref"]).abs()
        assert delta.max() < 0.01, column


@pytest.mark.parametrize("use_combiner", [False, True])
def test_monthly_job_is_chronological(fixture_frame, fixture_text, use_combiner):
    produced = _execute_job("monthly_trends", fixture_text, use_combiner)
    expected = metrics.monthly_trends(fixture_frame)
    assert list(zip(produced["flight_year"], produced["flight_month"])) == list(
        zip(expected["flight_year"], expected["flight_month"])
    )
    assert produced["total_flights"].sum() == expected["total_flights"].sum()


@pytest.mark.parametrize("use_combiner", [False, True])
def test_route_job_matches_reference(fixture_frame, fixture_text, use_combiner):
    produced = _execute_job("route_performance", fixture_text, use_combiner)
    expected = metrics.route_performance(fixture_frame, min_flights=0)
    merged = produced.merge(expected, on="route", suffixes=("_mr", "_ref"))
    assert len(merged) == len(expected)
    assert (merged["total_flights_mr"] == merged["total_flights_ref"]).all()
    assert (merged["arrival_delay_rate_mr"] - merged["arrival_delay_rate_ref"]).abs().max() < 0.01


def test_mapper_skips_header_and_short_rows(fixture_text):
    lines = ["flight_date,flight_year", "malformed,row"] + fixture_text.splitlines()
    output = _run("airline_delay_mapper.py", lines)
    assert output, "mapper produced no records"
    assert all(not line.startswith("flight_date") for line in output)
    assert all(line.count("\t") == 1 for line in output)


def test_combiner_is_associative(fixture_text):
    """Combined-then-reduced must equal plain reduce for additive counters."""
    for name in JOBS:
        plain = _execute_job(name, fixture_text, use_combiner=False)
        combined = _execute_job(name, fixture_text, use_combiner=True)
        pd.testing.assert_frame_equal(
            plain.sort_index(axis=1).reset_index(drop=True),
            combined.sort_index(axis=1).reset_index(drop=True),
            check_dtype=False,
        )
