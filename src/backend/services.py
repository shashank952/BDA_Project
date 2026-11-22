"""Data-access layer for the Flask API.

Reads the analytical outputs produced by Hive (authoritative) or MapReduce and
never triggers a Hadoop job. Missing outputs raise OutputUnavailable, which the
routes translate into a 503 with an actionable message instead of a stack trace.

Directory overrides for testing:
    AIRLINE_ANALYTICS_DIR   directory holding <analysis>.csv
    AIRLINE_REPORTS_DIR     directory holding data_quality/summary.json etc.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.common.config import load_airlines, load_settings

INT_COLUMNS = {
    "total_flights",
    "valid_departure_flights",
    "valid_arrival_flights",
    "departure_delayed_flights",
    "arrival_delayed_flights",
    "delayed_arrivals",
    "delayed_flights",
    "valid_delay_flights",
    "cancellations",
    "cancelled_flights",
    "diverted_flights",
    "flights",
    "flights_with_cause",
    "day_of_week",
    "flight_year",
    "flight_month",
    "cancelled_carrier",
    "cancelled_weather",
    "cancelled_nas",
    "cancelled_security",
}

NUMERIC_COLUMNS = INT_COLUMNS | {
    "avg_departure_delay",
    "avg_arrival_delay",
    "avg_delay",
    "departure_delay_rate",
    "arrival_delay_rate",
    "cancellation_rate",
    "delay_rate",
    "delay_minutes",
    "share_pct",
    "distance",
}


class InvalidParameter(ValueError):
    """A request parameter is syntactically valid HTTP but not an allowed value."""


class OutputUnavailable(RuntimeError):
    """An analytical result has not been generated yet."""


@dataclass(frozen=True)
class Paths:
    analytics: Path
    reports: Path


def load_settings_value(dotted_key: str, default=None):
    return load_settings().get(dotted_key, default)


def paths() -> Paths:
    settings = load_settings()
    analytics = Path(os.environ.get("AIRLINE_ANALYTICS_DIR") or settings.path("analytics_outputs"))
    reports = Path(os.environ.get("AIRLINE_REPORTS_DIR") or settings.path("reports"))
    return Paths(analytics=analytics, reports=reports)


def _coerce(frame: pd.DataFrame) -> pd.DataFrame:
    for column in frame.columns:
        if column in NUMERIC_COLUMNS:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


@lru_cache(maxsize=32)
def _read_cached(path: str, modified: float) -> pd.DataFrame:
    return _coerce(pd.read_csv(path))


def load_output(name: str) -> pd.DataFrame:
    path = paths().analytics / f"{name}.csv"
    if not path.exists():
        raise OutputUnavailable(
            f"Analytical output '{name}' is not available yet. Generate it with "
            f"`python -m src.hive.run_queries --all` or `python -m src.mapreduce.run_jobs`."
        )
    frame = _read_cached(str(path), path.stat().st_mtime)
    return frame.copy()


def load_json_report(relative: str) -> dict:
    path = paths().reports / relative
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def airline_names() -> dict[str, str]:
    return load_airlines()


def with_airline_names(frame: pd.DataFrame) -> pd.DataFrame:
    if "airline_code" not in frame:
        return frame
    names = airline_names()
    frame["airline_name"] = frame["airline_code"].map(names).fillna(frame["airline_code"])
    return frame


def paginate(frame: pd.DataFrame, limit: int, offset: int) -> dict:
    window = frame.iloc[offset : offset + limit]
    return {
        "total": int(len(frame)),
        "limit": limit,
        "offset": offset,
        "returned": int(len(window)),
    }


def sort_frame(frame: pd.DataFrame, column: str | None, order: str, allowed: set[str]) -> pd.DataFrame:
    if not column:
        return frame
    if column not in allowed:
        raise InvalidParameter("Requested sort column is not allowed. Allowed: " + ", ".join(sorted(allowed)))
    ascending = order != "desc"
    return frame.sort_values(column, ascending=ascending, na_position="last")


def _python_scalar(value):
    import numpy as np

    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def records(frame: pd.DataFrame) -> list[dict]:
    clean = frame.astype(object).where(pd.notna(frame), None)
    return [
        {key: _python_scalar(value) for key, value in row.items()}
        for row in clean.to_dict(orient="records")
    ]


def summary() -> dict:
    frame = load_output("summary")
    if frame.empty:
        raise OutputUnavailable("summary.csv is empty")
    row = frame.iloc[0].to_dict()
    return {
        "period": {"from": row.pop("first_date", None), "to": row.pop("last_date", None)},
        "totals": {
            "total_flights": int(row.get("total_flights") or 0),
            "valid_departure_flights": int(row.get("valid_departure_flights") or 0),
            "valid_arrival_flights": int(row.get("valid_arrival_flights") or 0),
            "departure_delayed_flights": int(row.get("departure_delayed_flights") or 0),
            "arrival_delayed_flights": int(row.get("arrival_delayed_flights") or 0),
            "cancelled_flights": int(row.get("cancelled_flights") or 0),
            "diverted_flights": int(row.get("diverted_flights") or 0),
        },
        "averages": {
            "departure_delay_minutes": row.get("avg_departure_delay"),
            "arrival_delay_minutes": row.get("avg_arrival_delay"),
        },
        "rates": {
            "departure_delay_rate": row.get("departure_delay_rate"),
            "arrival_delay_rate": row.get("arrival_delay_rate"),
            "cancellation_rate": row.get("cancellation_rate"),
        },
        "definitions": {
            "delay_threshold_minutes": 15,
            "arrival_delay_rate": "arrival delays >= 15 min / flights with a valid arrival measurement",
            "cancellation_rate": "cancelled flights / all flight records",
        },
    }


def airlines(airline: list[str] | None, limit: int, offset: int, sort_by: str | None, order: str) -> tuple[pd.DataFrame, dict]:
    frame = with_airline_names(load_output("airline_performance"))
    if airline:
        wanted = {code.upper() for code in airline}
        frame = frame[frame["airline_code"].str.upper().isin(wanted)]
    frame = sort_frame(
        frame,
        sort_by or "arrival_delay_rate",
        order,
        {"airline_code", "airline_name", "total_flights", "avg_arrival_delay", "arrival_delay_rate", "cancellations", "cancellation_rate"},
    )
    return frame.iloc[offset : offset + limit], paginate(frame, limit, offset)


def airports(
    role: str | None,
    airport: list[str] | None,
    min_flights: int,
    limit: int,
    offset: int,
    sort_by: str | None,
    order: str,
) -> tuple[pd.DataFrame, dict]:
    frame = load_output("airport_performance")
    if role:
        frame = frame[frame["role"] == role]
    if airport:
        wanted = {code.upper() for code in airport}
        frame = frame[frame["airport_code"].str.upper().isin(wanted)]
    frame = frame[frame["total_flights"] >= min_flights]
    frame = sort_frame(
        frame,
        sort_by or "delay_rate",
        order,
        {"airport_code", "role", "total_flights", "valid_delay_flights", "avg_delay", "delayed_flights", "delay_rate"},
    )
    return frame.iloc[offset : offset + limit], paginate(frame, limit, offset)


def routes(
    origin: str | None,
    destination: str | None,
    min_flights: int,
    limit: int,
    offset: int,
    sort_by: str | None,
    order: str,
) -> tuple[pd.DataFrame, dict]:
    frame = load_output("route_performance")
    if origin:
        frame = frame[frame["origin_airport"].str.upper() == origin.upper()]
    if destination:
        frame = frame[frame["destination_airport"].str.upper() == destination.upper()]
    frame = frame[frame["total_flights"] >= min_flights]
    frame = sort_frame(
        frame,
        sort_by or "arrival_delay_rate",
        order,
        {"route", "total_flights", "valid_arrival_flights", "avg_arrival_delay", "delayed_arrivals", "arrival_delay_rate"},
    )
    return frame.iloc[offset : offset + limit], paginate(frame, limit, offset)


def monthly(year_from: int | None, year_to: int | None, limit: int, offset: int) -> tuple[pd.DataFrame, dict]:
    frame = load_output("monthly_trends").sort_values(["flight_year", "flight_month"])
    if year_from is not None:
        frame = frame[frame["flight_year"] >= year_from]
    if year_to is not None:
        frame = frame[frame["flight_year"] <= year_to]
    return frame.iloc[offset : offset + limit], paginate(frame, limit, offset)


def day_of_week() -> pd.DataFrame:
    frame = load_output("day_of_week").sort_values("day_of_week")
    labels = {1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday", 7: "Sunday"}
    frame["day_name"] = frame["day_of_week"].map(labels)
    return frame


def delay_causes() -> pd.DataFrame:
    frame = load_output("delay_causes")
    return frame.sort_values("delay_minutes", ascending=False)


def delay_categories() -> pd.DataFrame:
    from src.common.spec import CATEGORY_LABELS

    frame = load_output("delay_categories")
    frame["category_label"] = frame["delay_category"].map(CATEGORY_LABELS).fillna(frame["delay_category"])
    order = ["on_time", "minor", "moderate", "severe", "unknown"]
    frame["_order"] = frame["delay_category"].map({name: i for i, name in enumerate(order)}).fillna(len(order))
    return frame.sort_values("_order").drop(columns="_order")


def cancellations(
    airline: list[str] | None,
    year: int | None,
    month: int | None,
    limit: int,
    offset: int,
) -> tuple[pd.DataFrame, dict]:
    frame = load_output("cancellations")
    if airline:
        wanted = {code.upper() for code in airline}
        frame = frame[frame["airline_code"].str.upper().isin(wanted)]
    if year is not None:
        frame = frame[frame["flight_year"] == year]
    if month is not None:
        frame = frame[frame["flight_month"] == month]
    frame = frame.sort_values(["flight_year", "flight_month", "cancellations"], ascending=[True, True, False])
    frame = with_airline_names(frame)
    return frame.iloc[offset : offset + limit], paginate(frame, limit, offset)


def cancellation_airports(year: int | None, month: int | None, limit: int, offset: int) -> tuple[pd.DataFrame, dict]:
    frame = load_output("cancellation_airports")
    if year is not None:
        frame = frame[frame["flight_year"] == year]
    if month is not None:
        frame = frame[frame["flight_month"] == month]
    frame = frame.sort_values(["cancellations"], ascending=False)
    return frame.iloc[offset : offset + limit], paginate(frame, limit, offset)


def metadata() -> dict:
    quality = load_json_report("data_quality/summary.json")
    partitions = quality.get("partitions", [])
    totals = quality.get("totals", {})
    runs = load_json_report("execution_metrics/mapreduce_runs.json") or []
    hive_runs = load_json_report("execution_metrics/hive_runs.json") or []

    dates = []
    for partition in partitions:
        report = partition.get("report_path")
        if not report:
            continue
        name = Path(report).name
        year = partition.get("year")
        path = paths().reports / "data_quality" / f"year={year}" / name
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                period = payload.get("period", {})
                if period.get("from"):
                    dates.append(period["from"])
                if period.get("to"):
                    dates.append(period["to"])
            except json.JSONDecodeError:
                continue

    available = sorted(
        path.stem for path in paths().analytics.glob("*.csv") if path.is_file()
    )
    return {
        "dataset": {
            "provider": "BTS On-Time Performance",
            "period_from": min(dates) if dates else None,
            "period_to": max(dates) if dates else None,
            "records_read": totals.get("rows_read"),
            "records_cleaned": totals.get("rows_cleaned"),
            "records_quarantined": totals.get("rows_quarantined"),
            "duplicates_removed": totals.get("duplicates_removed"),
            "partitions": len(partitions),
        },
        "analyses": available,
        "processing": {
            "mapreduce_jobs": [
                {"job": run.get("job"), "rows": run.get("output_rows"), "seconds": run.get("seconds"), "completed_at": run.get("completed_at")}
                for run in runs[-8:]
            ],
            "hive_queries": [
                {"query": run.get("query"), "rows": run.get("output_rows"), "seconds": run.get("seconds"), "completed_at": run.get("completed_at")}
                for run in hive_runs[-12:]
            ],
            "last_updated": max(
                [run.get("completed_at", "") for run in runs + hive_runs if run.get("completed_at")] or [""]
            )
            or None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
