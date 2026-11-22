"""Cross-layer output validation.

Every analytical result - MapReduce, Hive, or the API - is compared against the
independent pandas implementation in src.common.metrics. This is how the project
proves that "the same metric has the same value in every layer", rather than
trusting a visual check of the dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from src.common import metrics

TOLERANCE = 0.01


@dataclass(frozen=True)
class OutputSpec:
    keys: tuple[str, ...]
    values: tuple[str, ...]
    reference: Callable[[pd.DataFrame], pd.DataFrame]


OUTPUTS: dict[str, OutputSpec] = {
    "airline_performance": OutputSpec(
        keys=("airline_code",),
        values=(
            "total_flights",
            "valid_arrival_flights",
            "avg_arrival_delay",
            "delayed_arrivals",
            "arrival_delay_rate",
            "cancellations",
            "cancellation_rate",
        ),
        reference=metrics.airline_performance,
    ),
    "airport_performance": OutputSpec(
        keys=("role", "airport_code"),
        values=("total_flights", "valid_delay_flights", "avg_delay", "delayed_flights", "delay_rate"),
        reference=metrics.airport_performance,
    ),
    "monthly_trends": OutputSpec(
        keys=("flight_year", "flight_month"),
        values=(
            "total_flights",
            "valid_arrival_flights",
            "avg_arrival_delay",
            "delayed_arrivals",
            "arrival_delay_rate",
            "cancellations",
            "cancellation_rate",
        ),
        reference=metrics.monthly_trends,
    ),
    "route_performance": OutputSpec(
        keys=("route",),
        values=(
            "total_flights",
            "valid_arrival_flights",
            "avg_arrival_delay",
            "delayed_arrivals",
            "arrival_delay_rate",
        ),
        reference=lambda frame: metrics.route_performance(frame, min_flights=0),
    ),
    "delay_categories": OutputSpec(
        keys=("delay_category",),
        values=("flights", "share_pct"),
        reference=metrics.delay_category_counts,
    ),
    "delay_causes": OutputSpec(
        keys=("cause",),
        values=("delay_minutes", "flights_with_cause", "share_pct"),
        reference=metrics.delay_cause_summary,
    ),
    "cancellations": OutputSpec(
        keys=("airline_code", "flight_year", "flight_month"),
        values=("total_flights", "cancellations", "cancellation_rate"),
        reference=metrics.cancellation_summary,
    ),
    "cancellation_airports": OutputSpec(
        keys=("origin_airport", "flight_year", "flight_month"),
        values=(
            "total_flights",
            "cancellations",
            "cancellation_rate",
            "cancelled_carrier",
            "cancelled_weather",
            "cancelled_nas",
            "cancelled_security",
        ),
        reference=metrics.cancellation_by_airport,
    ),
    "day_of_week": OutputSpec(
        keys=("day_of_week",),
        values=(
            "total_flights",
            "valid_arrival_flights",
            "avg_arrival_delay",
            "delayed_arrivals",
            "arrival_delay_rate",
        ),
        reference=metrics.day_of_week_performance,
    ),
    "summary": OutputSpec(
        keys=(),
        values=(
            "total_flights",
            "valid_departure_flights",
            "valid_arrival_flights",
            "avg_departure_delay",
            "avg_arrival_delay",
            "departure_delayed_flights",
            "arrival_delayed_flights",
            "departure_delay_rate",
            "arrival_delay_rate",
            "cancelled_flights",
            "cancellation_rate",
            "diverted_flights",
        ),
        reference=lambda frame: pd.DataFrame([metrics.summary(frame)]),
    ),
}


def _key_column(frame: pd.DataFrame, keys: tuple[str, ...]) -> pd.Series:
    if not keys:
        return pd.Series(["all"] * len(frame), index=frame.index)
    return frame[list(keys)].astype(str).agg("|".join, axis=1)


def compare(
    name: str,
    produced: pd.DataFrame,
    frame: pd.DataFrame,
    tolerance: float = TOLERANCE,
) -> list[str]:
    """Return a list of human-readable mismatches (empty list == all good)."""
    spec = OUTPUTS[name]
    expected = spec.reference(frame)
    problems: list[str] = []

    if name == "summary":
        produced = produced.head(1).copy()
        expected = expected.head(1).copy()

    produced = produced.copy()
    expected = expected.copy()
    produced["_key"] = _key_column(produced, spec.keys)
    expected["_key"] = _key_column(expected, spec.keys)

    missing = set(expected["_key"]) - set(produced["_key"])
    extra = set(produced["_key"]) - set(expected["_key"])
    if missing:
        problems.append(f"{name}: {len(missing)} key(s) missing, e.g. {sorted(missing)[:5]}")
    if extra:
        problems.append(f"{name}: {len(extra)} unexpected key(s), e.g. {sorted(extra)[:5]}")

    merged = produced.merge(expected, on="_key", suffixes=("_out", "_ref"))
    for column in spec.values:
        left_name, right_name = f"{column}_out", f"{column}_ref"
        if left_name not in merged or right_name not in merged:
            problems.append(f"{name}.{column}: column missing from one of the outputs")
            continue
        left = pd.to_numeric(merged[left_name], errors="coerce")
        right = pd.to_numeric(merged[right_name], errors="coerce")
        bad = (left - right).abs()
        offenders = bad[bad > tolerance]
        if not offenders.empty:
            worst = merged.loc[offenders.index[0]]
            problems.append(
                f"{name}.{column}: {len(offenders)} row(s) differ by more than {tolerance}; "
                f"e.g. key={worst['_key']} output={worst[left_name]} reference={worst[right_name]}"
            )
    return problems


def compare_file(name: str, path, frame: pd.DataFrame, tolerance: float = TOLERANCE) -> list[str]:
    produced = pd.read_csv(path)
    return compare(name, produced, frame, tolerance=tolerance)
