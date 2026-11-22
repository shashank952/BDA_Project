"""Reference implementation of every analytical metric.

This module is the single source of truth used by:
  * pytest, to assert that MapReduce and Hive outputs match an independent
    calculation performed on the cleaned dataset;
  * the export step, to produce the ``outputs/analytics`` mirror that the
    Flask API serves.

Output column names here are the API contract; Hive queries and MapReduce
reducers emit exactly these names (see docs/metrics.md).
"""

from __future__ import annotations

import pandas as pd

from src.common.spec import (
    CAUSE_FIELDS,
    DELAY_CAUSE_LABELS,
    MIN_ROUTE_FLIGHTS,
    ON_TIME_THRESHOLD_MINUTES,
    average,
    safe_rate,
)

AVG_DECIMALS = 4
RATE_DECIMALS = 4


def _round(series: pd.Series, decimals: int = AVG_DECIMALS) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").round(decimals)


def load_cleaned_csv(path) -> pd.DataFrame:
    """Read a cleaned partition, preserving null delay measurements."""
    frame = pd.read_csv(path, dtype={"flight_date": str, "airline_code": str, "flight_number": str})
    for column in ("arrival_delay", "departure_delay", "arrival_delay_minutes", "departure_delay_minutes", "distance"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in ("is_arrival_delayed", "is_departure_delayed", "cancelled", "diverted"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def summary(frame: pd.DataFrame) -> dict:
    """Overall KPIs. Every rate states its denominator implicitly via *_flights."""
    total = int(len(frame))
    valid_dep = int(frame["departure_delay"].notna().sum())
    valid_arr = int(frame["arrival_delay"].notna().sum())
    cancelled = int(pd.to_numeric(frame["cancelled"], errors="coerce").fillna(0).sum())
    diverted = int(pd.to_numeric(frame["diverted"], errors="coerce").fillna(0).sum())
    dep_delayed = int(pd.to_numeric(frame["is_departure_delayed"], errors="coerce").fillna(0).sum())
    arr_delayed = int(pd.to_numeric(frame["is_arrival_delayed"], errors="coerce").fillna(0).sum())
    return {
        "total_flights": total,
        "valid_departure_flights": valid_dep,
        "valid_arrival_flights": valid_arr,
        "avg_departure_delay": average(frame["departure_delay"].dropna().round(AVG_DECIMALS).tolist()),
        "avg_arrival_delay": average(frame["arrival_delay"].dropna().round(AVG_DECIMALS).tolist()),
        "departure_delayed_flights": dep_delayed,
        "arrival_delayed_flights": arr_delayed,
        "departure_delay_rate": safe_rate(dep_delayed, valid_dep),
        "arrival_delay_rate": safe_rate(arr_delayed, valid_arr),
        "cancelled_flights": cancelled,
        "cancellation_rate": safe_rate(cancelled, total),
        "diverted_flights": diverted,
        "delay_threshold_minutes": ON_TIME_THRESHOLD_MINUTES,
    }


def airline_performance(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby("airline_code", dropna=True).agg(
        total_flights=("flight_date", "size"),
        valid_arrival_flights=("arrival_delay", "count"),
        avg_arrival_delay=("arrival_delay", "mean"),
        delayed_arrivals=("is_arrival_delayed", "sum"),
        cancellations=("cancelled", "sum"),
    ).reset_index()
    grouped["avg_arrival_delay"] = _round(grouped["avg_arrival_delay"])
    grouped["arrival_delay_rate"] = [
        safe_rate(delayed, valid)
        for delayed, valid in zip(grouped["delayed_arrivals"], grouped["valid_arrival_flights"])
    ]
    grouped["cancellation_rate"] = [
        safe_rate(cancelled, total)
        for cancelled, total in zip(grouped["cancellations"], grouped["total_flights"])
    ]
    grouped["delayed_arrivals"] = grouped["delayed_arrivals"].astype(int)
    grouped["cancellations"] = grouped["cancellations"].astype(int)
    return grouped.sort_values("airline_code").reset_index(drop=True)


def airport_performance(frame: pd.DataFrame) -> pd.DataFrame:
    """Departure and arrival roles are reported separately, never merged."""
    departures = frame.groupby("origin_airport").agg(
        total_flights=("flight_date", "size"),
        valid_delay_flights=("departure_delay", "count"),
        avg_delay=("departure_delay", "mean"),
        delayed_flights=("is_departure_delayed", "sum"),
    ).reset_index()
    departures["role"] = "departure"
    departures = departures.rename(columns={"origin_airport": "airport_code"})

    arrivals = frame.groupby("destination_airport").agg(
        total_flights=("flight_date", "size"),
        valid_delay_flights=("arrival_delay", "count"),
        avg_delay=("arrival_delay", "mean"),
        delayed_flights=("is_arrival_delayed", "sum"),
    ).reset_index()
    arrivals["role"] = "arrival"
    arrivals = arrivals.rename(columns={"destination_airport": "airport_code"})

    combined = pd.concat([departures, arrivals], ignore_index=True)
    combined["avg_delay"] = _round(combined["avg_delay"])
    combined["delay_rate"] = [
        safe_rate(delayed, valid)
        for delayed, valid in zip(combined["delayed_flights"], combined["valid_delay_flights"])
    ]
    combined["delayed_flights"] = combined["delayed_flights"].astype(int)
    return combined.sort_values(["airport_code", "role"]).reset_index(drop=True)


def monthly_trends(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby(["flight_year", "flight_month"], dropna=True).agg(
        total_flights=("flight_date", "size"),
        valid_arrival_flights=("arrival_delay", "count"),
        avg_arrival_delay=("arrival_delay", "mean"),
        delayed_arrivals=("is_arrival_delayed", "sum"),
        cancellations=("cancelled", "sum"),
    ).reset_index()
    grouped["avg_arrival_delay"] = _round(grouped["avg_arrival_delay"])
    grouped["arrival_delay_rate"] = [
        safe_rate(delayed, valid)
        for delayed, valid in zip(grouped["delayed_arrivals"], grouped["valid_arrival_flights"])
    ]
    grouped["cancellation_rate"] = [
        safe_rate(cancelled, total)
        for cancelled, total in zip(grouped["cancellations"], grouped["total_flights"])
    ]
    grouped["delayed_arrivals"] = grouped["delayed_arrivals"].astype(int)
    grouped["cancellations"] = grouped["cancellations"].astype(int)
    return grouped.sort_values(["flight_year", "flight_month"]).reset_index(drop=True)


def day_of_week_performance(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby("day_of_week", dropna=True).agg(
        total_flights=("flight_date", "size"),
        valid_arrival_flights=("arrival_delay", "count"),
        avg_arrival_delay=("arrival_delay", "mean"),
        delayed_arrivals=("is_arrival_delayed", "sum"),
    ).reset_index()
    grouped["avg_arrival_delay"] = _round(grouped["avg_arrival_delay"])
    grouped["arrival_delay_rate"] = [
        safe_rate(delayed, valid)
        for delayed, valid in zip(grouped["delayed_arrivals"], grouped["valid_arrival_flights"])
    ]
    grouped["delayed_arrivals"] = grouped["delayed_arrivals"].astype(int)
    return grouped.sort_values("day_of_week").reset_index(drop=True)


def route_performance(frame: pd.DataFrame, min_flights: int = MIN_ROUTE_FLIGHTS) -> pd.DataFrame:
    grouped = frame.groupby(["origin_airport", "destination_airport"], dropna=True).agg(
        total_flights=("flight_date", "size"),
        valid_arrival_flights=("arrival_delay", "count"),
        avg_arrival_delay=("arrival_delay", "mean"),
        delayed_arrivals=("is_arrival_delayed", "sum"),
    ).reset_index()
    grouped = grouped[grouped["total_flights"] >= min_flights].copy()
    grouped["route"] = grouped["origin_airport"] + "-" + grouped["destination_airport"]
    grouped["avg_arrival_delay"] = _round(grouped["avg_arrival_delay"])
    grouped["arrival_delay_rate"] = [
        safe_rate(delayed, valid)
        for delayed, valid in zip(grouped["delayed_arrivals"], grouped["valid_arrival_flights"])
    ]
    grouped["delayed_arrivals"] = grouped["delayed_arrivals"].astype(int)
    columns = [
        "route",
        "origin_airport",
        "destination_airport",
        "total_flights",
        "valid_arrival_flights",
        "avg_arrival_delay",
        "delayed_arrivals",
        "arrival_delay_rate",
    ]
    return grouped.sort_values(["arrival_delay_rate", "total_flights"], ascending=False)[columns].reset_index(drop=True)


def delay_category_counts(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby("delay_category", dropna=False).size().reset_index(name="flights")
    total = int(grouped["flights"].sum())
    grouped["share_pct"] = (100.0 * grouped["flights"] / total).round(RATE_DECIMALS) if total else None
    return grouped.sort_values("flights", ascending=False).reset_index(drop=True)


def delay_cause_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Aggregate recorded cause minutes.

    Only rows with at least one reported cause contribute; BTS populates these
    columns for delayed flights only, so `flights_with_cause` is the honest
    denominator for the share calculation.
    """
    if not all(field in frame.columns for field in CAUSE_FIELDS):
        return pd.DataFrame(columns=["cause", "delay_minutes", "flights_with_cause", "share_pct"])

    cause_values = frame[list(CAUSE_FIELDS)]
    has_cause = cause_values.notna().any(axis=1)
    subset = cause_values.loc[has_cause]
    total_minutes = float(subset.sum().sum()) if not subset.empty else 0.0
    rows = []
    for field in CAUSE_FIELDS:
        minutes = float(subset[field].fillna(0).sum()) if not subset.empty else 0.0
        rows.append(
            {
                "cause": DELAY_CAUSE_LABELS[field],
                "cause_field": field,
                "delay_minutes": round(minutes, 2),
                "flights_with_cause": int(subset[field].notna().sum()) if not subset.empty else 0,
                "share_pct": round(100.0 * minutes / total_minutes, RATE_DECIMALS) if total_minutes else None,
            }
        )
    return pd.DataFrame(rows).sort_values("delay_minutes", ascending=False).reset_index(drop=True)


def cancellation_summary(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby(["airline_code", "flight_year", "flight_month"], dropna=True).agg(
        total_flights=("flight_date", "size"),
        cancellations=("cancelled", "sum"),
    ).reset_index()
    grouped["cancellation_rate"] = [
        safe_rate(cancelled, total)
        for cancelled, total in zip(grouped["cancellations"], grouped["total_flights"])
    ]
    grouped["cancellations"] = grouped["cancellations"].astype(int)
    return grouped.sort_values(["flight_year", "flight_month", "cancellations"], ascending=[True, True, False]).reset_index(drop=True)


def cancellation_codes(frame: pd.DataFrame) -> pd.DataFrame:
    cancelled = frame[pd.to_numeric(frame["cancelled"], errors="coerce").eq(1)]
    grouped = cancelled.groupby("cancellation_code", dropna=False).size().reset_index(name="flights")
    return grouped.sort_values("flights", ascending=False).reset_index(drop=True)


def cancellation_by_airport(frame: pd.DataFrame) -> pd.DataFrame:
    """Cancellations by origin airport and month, including code breakdown.

    Only airports with at least one cancellation are returned, matching the
    `HAVING SUM(cancelled) > 0` clause of the Hive query.
    """
    grouped = frame.groupby(["origin_airport", "flight_year", "flight_month"], dropna=True).agg(
        total_flights=("flight_date", "size"),
        cancellations=("cancelled", "sum"),
        cancelled_carrier=("cancellation_code", lambda s: int((s == "A").sum())),
        cancelled_weather=("cancellation_code", lambda s: int((s == "B").sum())),
        cancelled_nas=("cancellation_code", lambda s: int((s == "C").sum())),
        cancelled_security=("cancellation_code", lambda s: int((s == "D").sum())),
    ).reset_index()
    grouped = grouped[grouped["cancellations"] > 0].copy()
    grouped["cancellations"] = grouped["cancellations"].astype(int)
    grouped["cancellation_rate"] = [
        safe_rate(cancelled, total)
        for cancelled, total in zip(grouped["cancellations"], grouped["total_flights"])
    ]
    return grouped.sort_values(
        ["flight_year", "flight_month", "cancellations"], ascending=[True, True, False]
    ).reset_index(drop=True)
