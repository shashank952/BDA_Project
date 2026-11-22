"""Derived-column construction for cleaned flight records."""

from __future__ import annotations

import pandas as pd

from src.common.config import Settings
from src.common.spec import (
    MINOR_DELAY_UPPER_MINUTES,
    MODERATE_DELAY_UPPER_MINUTES,
    ON_TIME_THRESHOLD_MINUTES,
)


def normalize_hhmm(series: pd.Series) -> pd.Series:
    """Normalize an hhmm time column to zero-padded 4 characters.

    BTS stores times as integers-ish strings ("659", "0659", "2400"). Values
    outside 0000-2359 after folding 2400 -> 0000 become null rather than being
    silently reinterpreted.
    """
    digits = series.astype("string").str.replace(r"[^0-9]", "", regex=True)
    digits = digits.where(digits.str.len().between(1, 4))
    numeric = pd.to_numeric(digits, errors="coerce")
    numeric = numeric.where(numeric >= 0)
    numeric = numeric.mask(numeric == 2400, 0)
    numeric = numeric.where(numeric <= 2359)
    return numeric.map(lambda value: None if pd.isna(value) else f"{int(value):04d}")


def dep_hour(scheduled_departure: pd.Series) -> pd.Series:
    hours = scheduled_departure.astype("string").str[:2]
    numeric = pd.to_numeric(hours, errors="coerce")
    return numeric.where((numeric >= 0) & (numeric <= 23))


def _categorize(arrival_delay: pd.Series) -> pd.Series:
    """Vectorized delay_category that matches src.common.spec.delay_category."""
    categories = pd.Series("unknown", index=arrival_delay.index, dtype="object")
    measured = arrival_delay.notna()
    categories[measured] = "severe"
    categories[measured & (arrival_delay < MODERATE_DELAY_UPPER_MINUTES)] = "moderate"
    categories[measured & (arrival_delay < MINOR_DELAY_UPPER_MINUTES)] = "minor"
    categories[measured & (arrival_delay < ON_TIME_THRESHOLD_MINUTES)] = "on_time"
    return categories


def add_derived_columns(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """Attach every derived column declared in schema_mapping.yaml.

    Expects parsed (typed) columns: flight_date as datetime, departure_delay /
    arrival_delay as float, scheduled_departure as string.
    """
    out = df.copy()

    out["scheduled_departure"] = normalize_hhmm(out["scheduled_departure"]) if "scheduled_departure" in out else None
    out["actual_departure"] = normalize_hhmm(out["actual_departure"]) if "actual_departure" in out else None
    out["scheduled_arrival"] = normalize_hhmm(out["scheduled_arrival"]) if "scheduled_arrival" in out else None
    out["actual_arrival"] = normalize_hhmm(out["actual_arrival"]) if "actual_arrival" in out else None

    out["dep_hour"] = dep_hour(out["scheduled_departure"])

    flight_date = pd.to_datetime(out["flight_date"], errors="coerce")
    out["flight_date"] = flight_date.dt.strftime("%Y-%m-%d")
    out["flight_year"] = flight_date.dt.year
    out["flight_month"] = flight_date.dt.month
    out["day_of_week"] = flight_date.dt.dayofweek + 1  # ISO: 1=Monday

    departure_delay = pd.to_numeric(out["departure_delay"], errors="coerce")
    arrival_delay = pd.to_numeric(out["arrival_delay"], errors="coerce")
    out["departure_delay"] = departure_delay
    out["arrival_delay"] = arrival_delay

    # BTS semantics: the "minutes" columns are the delay floored at zero.
    out["departure_delay_minutes"] = departure_delay.clip(lower=0)
    out["arrival_delay_minutes"] = arrival_delay.clip(lower=0)

    out["is_departure_delayed"] = (departure_delay >= ON_TIME_THRESHOLD_MINUTES).astype("Int64")
    out["is_departure_delayed"] = out["is_departure_delayed"].mask(departure_delay.isna())
    out["is_arrival_delayed"] = (arrival_delay >= ON_TIME_THRESHOLD_MINUTES).astype("Int64")
    out["is_arrival_delayed"] = out["is_arrival_delayed"].mask(arrival_delay.isna())

    out["delay_category"] = _categorize(arrival_delay)

    out["route"] = (
        out["origin_airport"].astype("string").fillna("?")
        + "-"
        + out["destination_airport"].astype("string").fillna("?")
    )
    return out
