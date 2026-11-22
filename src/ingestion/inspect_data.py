"""Inspect a BTS source file before writing any processing code.

Reports the real header, the mapping coverage, sample rows and missing-value rates
for the configured columns. This is the tool used to verify the schema of the
2025 download (110 columns, trailing empty column name, quoted city names).

    python -m src.ingestion.inspect_data --input data/raw/bts/year=2025
    python -m src.ingestion.inspect_data --input <file.zip> --rows 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.common.config import field_specs, load_schema_mapping, required_source_columns
from src.preprocessing.clean_data import missing_optional_columns, read_source


def resolve_input(target: Path) -> Path:
    if target.is_file():
        return target
    candidates = sorted(target.glob("*.zip")) or sorted(target.glob("*.csv"))
    if not candidates:
        raise SystemExit(f"No .zip or .csv file found under {target}")
    return candidates[0]


def inspect(path: Path, sample_rows: int = 3) -> dict:
    mapping = load_schema_mapping()
    frame = read_source(path, mapping)

    declared = {spec["source"] for spec in field_specs(mapping)}
    missing_optional = missing_optional_columns(frame, mapping)
    missing_required = [name for name in required_source_columns(mapping) if name not in frame.columns]

    print(f"file        : {path.name}")
    print(f"size        : {path.stat().st_size / (1024 * 1024):.1f} MB")
    print(f"rows        : {len(frame):,}")
    print(f"columns read: {len(frame.columns)} (mapped from {len(declared)} configured)")
    print(f"required missing: {missing_required or 'none'}")
    print(f"optional missing: {missing_optional or 'none'}")
    print()

    print("sample rows (mapped columns only):")
    print(frame.head(sample_rows).to_string(max_colwidth=28))
    print()

    print("missing values per mapped column:")
    rows = []
    for column in frame.columns:
        missing = int(frame[column].isna().sum())
        rows.append((column, missing, round(100.0 * missing / max(len(frame), 1), 3)))
    for column, missing, share in sorted(rows, key=lambda item: -item[1])[:15]:
        print(f"  {column:28} {missing:>10,}  {share:6.2f}%")
    return {"rows": len(frame), "missing_required": missing_required, "missing_optional": missing_optional}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a BTS On-Time Performance file")
    parser.add_argument("--input", type=Path, required=True, help="file or directory containing the download")
    parser.add_argument("--rows", type=int, default=3)
    args = parser.parse_args(argv)

    path = resolve_input(args.input)
    result = inspect(path, args.rows)
    return 1 if result["missing_required"] else 0


if __name__ == "__main__":
    sys.exit(main())
