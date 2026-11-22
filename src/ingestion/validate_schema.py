"""Validate a source file against the documented schema before cleaning.

    python -m src.ingestion.validate_schema --input data/raw/bts/year=2025
    python -m src.ingestion.validate_schema --input tests/fixtures/sample_flights.csv

Exit codes:
    0  schema satisfied (optional columns may be missing, and are listed)
    1  required columns missing or file unusable
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.common.config import field_specs, load_schema_mapping
from src.ingestion.inspect_data import resolve_input
from src.preprocessing.clean_data import (
    SchemaValidationError,
    missing_optional_columns,
    read_source,
    validate_schema,
)


def report(path: Path) -> int:
    mapping = load_schema_mapping()
    try:
        frame = read_source(path, mapping)
        validate_schema(frame, mapping)
    except SchemaValidationError as error:
        print(f"FAILED: {error}")
        return 1

    optional_missing = missing_optional_columns(frame, mapping)
    availability = {}
    for spec in field_specs(mapping):
        availability.setdefault(spec["source"], spec.get("required", False))

    print(f"OK: {path.name} satisfies the required schema ({len(frame):,} rows)")
    if optional_missing:
        print("Disabled analyses from missing optional columns:")
        for column in optional_missing:
            owners = [spec["name"] for spec in field_specs(mapping) if spec["source"] == column]
            print(f"  - {column} (fields: {', '.join(owners)})")
    else:
        print("All configured optional columns are present.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a BTS file against config/schema_mapping.yaml")
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    return report(resolve_input(args.input))


if __name__ == "__main__":
    sys.exit(main())
