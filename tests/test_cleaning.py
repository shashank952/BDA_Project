"""Cleaning-pipeline tests against the committed fixture with known answers."""

from __future__ import annotations

import pandas as pd
import pytest

from src.common.config import cleaned_columns, load_settings
from src.common.spec import delay_category
from src.preprocessing.clean_data import clean_dataframe, read_source


def test_row_accounting(cleaned_fixture):
    assert cleaned_fixture["cleaned"].shape[0] == 11  # 15 read - 3 quarantined - 1 duplicate
    assert cleaned_fixture["quarantine"].shape[0] == 3
    assert cleaned_fixture["duplicates"] == 1


def test_quarantine_reasons_are_specific(cleaned_fixture):
    reasons = set(cleaned_fixture["rejections"])
    assert "invalid_flight_date" in reasons
    assert "implausible_distance" in reasons
    assert "invalid_cancelled_flag" in reasons
    quarantine = cleaned_fixture["quarantine"]
    assert quarantine["rejection_reasons"].notna().all()
    assert len(quarantine["source_row"].unique()) == len(quarantine)


def test_columns_match_canonical_order(cleaned_fixture):
    assert list(cleaned_fixture["cleaned"].columns) == cleaned_columns()


def test_negative_delays_are_preserved_not_zeroed(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    early = frame[frame["flight_date"].eq("2025-01-01")].iloc[0]
    assert early["departure_delay"] == -3
    assert early["arrival_delay"] == -7
    assert early["is_arrival_delayed"] == 0


def test_zero_delay_is_a_valid_measurement(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    on_time_flight = frame[frame["airline_code"].eq("B6")].iloc[0]
    assert on_time_flight["arrival_delay"] == 0
    assert not pd.isna(on_time_flight["arrival_delay"])
    assert on_time_flight["delay_category"] == "on_time"


def test_cancelled_flight_keeps_null_arrival_delay(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    cancelled = frame[frame["airline_code"].eq("UA") & frame["cancelled"].eq(1)].iloc[0]
    assert pd.isna(cancelled["arrival_delay"])
    assert pd.isna(cancelled["is_arrival_delayed"])
    assert cancelled["cancellation_code"] == "B"
    assert cancelled["delay_category"] == "unknown"


def test_diverted_flight_has_departure_but_no_arrival_measurement(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    diverted = frame[frame["diverted"].eq(1)].iloc[0]
    assert diverted["departure_delay"] == 12
    assert pd.isna(diverted["arrival_delay"])


@pytest.mark.parametrize(
    "delay,expected",
    [
        (-5, "on_time"),
        (0, "on_time"),
        (14, "on_time"),
        (15, "minor"),
        (29, "minor"),
        (30, "moderate"),
        (59, "moderate"),
        (60, "severe"),
        (240, "severe"),
        (None, "unknown"),
    ],
)
def test_delay_category_boundaries(delay, expected):
    assert delay_category(delay) == expected


def test_vectorized_categories_match_scalar_rule(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    for _, row in frame.iterrows():
        expected = delay_category(None if pd.isna(row["arrival_delay"]) else float(row["arrival_delay"]))
        assert row["delay_category"] == expected


def test_derived_date_parts(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    row = frame[frame["flight_date"].eq("2025-01-01")].iloc[0]
    assert row["flight_year"] == 2025
    assert row["flight_month"] == 1
    assert row["day_of_week"] == 3  # 2025-01-01 was a Wednesday
    assert row["dep_hour"] == 8  # CRSDepTime 0800
    assert row["route"] == "JFK-LAX"


def test_cleaning_is_deterministic(fixture_csv):
    settings = load_settings()
    raw = read_source(fixture_csv)
    first, _, _, _ = clean_dataframe(raw, settings)
    second, _, _, _ = clean_dataframe(raw, settings)
    pd.testing.assert_frame_equal(first, second)


def test_dedupe_keeps_one_row_per_natural_key(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    settings = load_settings()
    key = settings.get("cleaning.dedupe_key")
    assert not frame.duplicated(subset=key).any()


def test_delay_minutes_are_floored_at_zero(cleaned_fixture):
    frame = cleaned_fixture["cleaned"]
    early = frame[frame["flight_date"].eq("2025-01-01")].iloc[0]
    assert early["departure_delay_minutes"] == 0
    assert early["arrival_delay_minutes"] == 0
    delayed = frame[frame["airline_code"].eq("DL") & frame["arrival_delay"].eq(59)].iloc[0]
    assert delayed["arrival_delay_minutes"] == 59
