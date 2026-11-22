"""Schema-contract tests: mapping integrity and fail-fast behaviour."""

from __future__ import annotations

import pandas as pd
import pytest

from src.common.config import (
    cleaned_columns,
    field_specs,
    load_schema_mapping,
    load_settings,
    required_source_columns,
)
from src.preprocessing.clean_data import SchemaValidationError, clean_dataframe, read_source, validate_schema


def test_mapping_defines_every_cleaned_column():
    mapping = load_schema_mapping()
    declared = {spec["name"] for spec in mapping["fields"]} | {
        spec["name"] for spec in mapping["derived_fields"]
    }
    for column in cleaned_columns(mapping):
        assert column in declared, f"cleaned column {column} has no definition in schema_mapping.yaml"


def test_every_field_has_documented_attributes():
    for spec in field_specs():
        for key in ("name", "source", "dtype", "required", "description", "missing_handling"):
            assert key in spec, f"{spec.get('name')} missing attribute {key}"
        assert spec["dtype"] in {"date", "string", "double", "flag", "hhmm"}


def test_required_columns_are_a_subset_of_fixture(fixture_csv):
    frame = read_source(fixture_csv)
    present = set(frame.columns)
    for column in required_source_columns():
        assert column in present
    validate_schema(frame)


def test_missing_required_column_fails_fast(fixture_csv):
    frame = read_source(fixture_csv).drop(columns=["FlightDate"])
    with pytest.raises(SchemaValidationError) as excinfo:
        validate_schema(frame)
    assert "FlightDate" in str(excinfo.value)


def test_missing_optional_causes_disable_cause_analysis(fixture_csv):
    """Absent optional columns must degrade gracefully, not crash."""
    mapping = load_schema_mapping()
    optional_causes = ["CarrierDelay", "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay"]
    frame = read_source(fixture_csv).drop(columns=optional_causes)
    cleaned, _, _, _ = clean_dataframe(frame, load_settings(), mapping)
    assert len(cleaned) > 0
    assert cleaned["carrier_delay"].isna().all()


def test_empty_dataset_is_rejected(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("FlightDate,Reporting_Airline\n", encoding="utf-8")
    frame = read_source(path)
    with pytest.raises(SchemaValidationError):
        validate_schema(frame)


def test_dedupe_key_columns_exist_in_cleaned_schema():
    settings = load_settings()
    columns = set(cleaned_columns())
    for key in settings.get("cleaning.dedupe_key"):
        assert key in columns
