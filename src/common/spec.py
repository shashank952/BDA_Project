"""Canonical analytical definitions shared by Python, MapReduce and Hive.

The delay thresholds and the "delayed flight" rule live here once. MapReduce
mappers hard-code the same threshold (Hadoop Streaming jobs cannot import this
module on the cluster), so `docs/metrics.md` records the contract and
`tests/test_metrics.py` locks the numbers down.
"""

from __future__ import annotations

from typing import Final

from src.common.config import cleaned_columns, load_settings

SETTINGS = load_settings()
CLEAN_COLUMNS: Final[tuple[str, ...]] = tuple(cleaned_columns())

ON_TIME_THRESHOLD_MINUTES: Final[float] = float(
    SETTINGS.get("cleaning.on_time_threshold_minutes", 15)
)
MINOR_DELAY_UPPER_MINUTES: Final[float] = float(
    SETTINGS.get("cleaning.minor_delay_upper_minutes", 30)
)
MODERATE_DELAY_UPPER_MINUTES: Final[float] = float(
    SETTINGS.get("cleaning.moderate_delay_upper_minutes", 60)
)
MIN_ROUTE_FLIGHTS: Final[int] = int(SETTINGS.get("analytics.min_route_flights", 100))
TOP_N: Final[int] = int(SETTINGS.get("analytics.top_n", 10))

DELAY_CATEGORIES: Final[tuple[str, ...]] = ("on_time", "minor", "moderate", "severe", "unknown")

# Numeric columns that participate in averages or sums.
DELAY_MEASURES: Final[tuple[str, ...]] = (
    "departure_delay",
    "departure_delay_minutes",
    "arrival_delay",
    "arrival_delay_minutes",
)
CAUSE_FIELDS: Final[tuple[str, ...]] = (
    "carrier_delay",
    "weather_delay",
    "nas_delay",
    "security_delay",
    "late_aircraft_delay",
)

CANCELLATION_CODE_LABELS: Final[dict[str, str]] = {
    "A": "Carrier",
    "B": "Weather",
    "C": "National Aviation System",
    "D": "Security",
}

CATEGORY_LABELS: Final[dict[str, str]] = {
    "on_time": "On time (<15 min)",
    "minor": "Minor (15-29 min)",
    "moderate": "Moderate (30-59 min)",
    "severe": "Severe (>=60 min)",
    "unknown": "Unknown (no arrival measurement)",
}

DELAY_CAUSE_LABELS: Final[dict[str, str]] = {
    "carrier_delay": "Carrier",
    "weather_delay": "Weather",
    "nas_delay": "National Aviation System",
    "security_delay": "Security",
    "late_aircraft_delay": "Late aircraft",
}


def delay_category(arrival_delay: float | None) -> str:
    """Project-defined arrival-delay bucket.

    Scalar counterpart of the vectorized rule used during cleaning; both must
    agree (see tests/test_cleaning.py::test_delay_category_boundaries).
    """
    if arrival_delay is None or arrival_delay != arrival_delay:  # NaN check
        return "unknown"
    if arrival_delay < ON_TIME_THRESHOLD_MINUTES:
        return "on_time"
    if arrival_delay < MINOR_DELAY_UPPER_MINUTES:
        return "minor"
    if arrival_delay < MODERATE_DELAY_UPPER_MINUTES:
        return "moderate"
    return "severe"


def is_delayed(delay_minutes: float | None) -> int | None:
    """1 when a delay measurement reaches the 15 minute threshold, else 0."""
    if delay_minutes is None or delay_minutes != delay_minutes:
        return None
    return 1 if delay_minutes >= ON_TIME_THRESHOLD_MINUTES else 0


def safe_rate(numerator: float, denominator: float) -> float | None:
    """Percentage rate with an explicit empty denominator guard."""
    if not denominator:
        return None
    return round(100.0 * numerator / denominator, 4)


def average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None
