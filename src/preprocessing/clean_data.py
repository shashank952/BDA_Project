"""Deterministic cleaning / standardization for BTS On-Time Performance files.

Guarantees:
  * the downloaded archive is never modified (read-only access);
  * the same input always produces the same cleaned file (explicit sort order);
  * missing delay measurements stay null, they are never coerced to 0;
  * legitimate negative delays (early departures/arrivals) survive;
  * rejected rows are quarantined with a machine-readable reason list.

Run:
    python -m src.preprocessing.clean_data --year 2025 --months 1
    python -m src.preprocessing.clean_data --year 2025 --months 1-12
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from src.common.config import (
    Settings,
    cleaned_columns,
    field_specs,
    load_schema_mapping,
    load_settings,
    required_source_columns,
)
from src.preprocessing.derive_features import add_derived_columns, normalize_hhmm
from src.preprocessing.quality_report import build_quality_report, write_report

MIN_VALID_DATE = date(1987, 1, 1)
AIRLINE_PATTERN = r"^[A-Z0-9]{2,3}$"
AIRPORT_PATTERN = r"^[A-Z0-9]{3,4}$"


class SchemaValidationError(RuntimeError):
    """Raised when the input file cannot satisfy the documented schema."""


@dataclass
class PartitionResult:
    year: int
    month: int
    source_file: str
    cleaned_path: Path
    quarantine_path: Path
    report_path: Path
    rows_read: int
    rows_cleaned: int
    rows_quarantined: int
    duplicates_removed: int
    timings: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "month": self.month,
            "source_file": self.source_file,
            "cleaned_path": str(self.cleaned_path),
            "quarantine_path": str(self.quarantine_path),
            "report_path": str(self.report_path),
            "rows_read": self.rows_read,
            "rows_cleaned": self.rows_cleaned,
            "rows_quarantined": self.rows_quarantined,
            "duplicates_removed": self.duplicates_removed,
            "timings": self.timings,
        }


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def _csv_member(path: Path) -> str | None:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
    return members[0] if members else None


def read_source(path: Path, mapping: dict[str, Any] | None = None) -> pd.DataFrame:
    """Read a BTS CSV (plain or inside the downloaded zip) as strings.

    Only configured source columns are materialized; the 84 unused columns of
    the 110-column dataset never enter memory.
    """
    mapping = mapping or load_schema_mapping()
    wanted = {spec["source"] for spec in field_specs(mapping)}
    read_kwargs = dict(
        dtype=str,
        keep_default_na=False,
        na_values=[],
        encoding=mapping["source"].get("encoding", "utf-8-sig"),
        sep=mapping["source"].get("delimiter", ","),
        low_memory=False,
        usecols=lambda column: column in wanted,
    )

    if not path.exists():
        raise SchemaValidationError(
            f"Source file not found: {path}. Run scripts/download_dataset.py first."
        )

    if path.suffix.lower() == ".zip":
        member = _csv_member(path)
        if member is None:
            raise SchemaValidationError(f"No CSV member inside archive: {path.name}")
        with zipfile.ZipFile(path) as archive, archive.open(member) as handle:
            return pd.read_csv(handle, **read_kwargs)
    return pd.read_csv(path, **read_kwargs)


def validate_schema(frame: pd.DataFrame, mapping: dict[str, Any] | None = None) -> None:
    """Fail fast with an explicit field list when required columns are absent."""
    mapping = mapping or load_schema_mapping()
    present = set(frame.columns)
    missing_required = [name for name in required_source_columns(mapping) if name not in present]
    if missing_required:
        raise SchemaValidationError(
            "Required source column(s) missing: " + ", ".join(sorted(missing_required))
        )
    if frame.empty:
        raise SchemaValidationError("Source file contains no data rows")


def missing_optional_columns(frame: pd.DataFrame, mapping: dict[str, Any] | None = None) -> list[str]:
    mapping = mapping or load_schema_mapping()
    present = set(frame.columns)
    return [
        spec["source"]
        for spec in field_specs(mapping)
        if not spec.get("required") and spec["source"] not in present
    ]


# ---------------------------------------------------------------------------
# Standardization + validation
# ---------------------------------------------------------------------------


def _clean_strings(series: pd.Series, markers: set[str]) -> pd.Series:
    values = series.astype("string").str.strip()
    values = values.mask(values.isin(markers))
    return values.mask(values.str.len().fillna(0) == 0)


def _coerce(spec: dict[str, Any], series: pd.Series, markers: set[str]) -> tuple[pd.Series, pd.Series]:
    """Return (parsed_series, invalid_mask).

    invalid_mask is True only where the source held a non-empty value that
    could not be interpreted; empty markers are missing, not invalid.
    """
    raw = _clean_strings(series, markers)
    present = raw.notna()
    dtype = spec["dtype"]

    if dtype == "date":
        parsed = pd.to_datetime(raw, format="%Y-%m-%d", errors="coerce")
        invalid = present & parsed.isna()
        return parsed, invalid
    if dtype in {"double", "flag"}:
        parsed = pd.to_numeric(raw, errors="coerce")
        invalid = present & parsed.isna()
        if dtype == "flag":
            invalid = invalid | (present & ~parsed.isin([0, 1]))
        return parsed, invalid
    if dtype == "hhmm":
        parsed = normalize_hhmm(raw).astype("object")
        invalid = present & pd.isna(parsed)
        return parsed, invalid
    # default: string
    uppercased = raw.str.upper() if spec["name"].endswith(("_code", "_airport")) else raw
    return uppercased.astype("object"), pd.Series(False, index=series.index)


def standardize(frame: pd.DataFrame, mapping: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int]]:
    """Rename + type-cast source columns, quarantining invalid rows.

    Returns (valid_rows, quarantined_rows, rejection_counts).
    """
    markers = {str(marker) for marker in mapping["source"].get("null_markers", [])}
    out = pd.DataFrame(index=frame.index)
    source_row = pd.Series(frame.index + 2, index=frame.index)  # header occupies row 1

    invalid_masks: dict[str, pd.Series] = {}
    present_masks: dict[str, pd.Series] = {}
    for spec in field_specs(mapping):
        name = spec["name"]
        if spec["source"] not in frame.columns:
            out[name] = None
            present_masks[name] = pd.Series(False, index=frame.index)
            continue
        parsed, invalid = _coerce(spec, frame[spec["source"]], markers)
        out[name] = parsed
        invalid_masks[name] = invalid
        present_masks[name] = _clean_strings(frame[spec["source"]], markers).notna()

    today = pd.Timestamp.today().normalize() + pd.Timedelta(days=1)
    settings = load_settings()
    min_delay = float(settings.get("cleaning.min_plausible_delay_minutes", -300))
    max_delay = float(settings.get("cleaning.max_plausible_delay_minutes", 5000))
    max_distance = float(settings.get("cleaning.max_plausible_distance_miles", 12000))

    rules: list[tuple[str, pd.Series]] = []

    key_fields = ("flight_date", "airline_code", "origin_airport", "destination_airport")
    rules.append(("missing_key_field", out[list(key_fields)].isna().any(axis=1)))

    # NaT comparisons are False, so this is "unparseable or out of range".
    bad_date = (
        out["flight_date"].isna()
        | (out["flight_date"] < pd.Timestamp(MIN_VALID_DATE))
        | (out["flight_date"] > today)
    )
    rules.append(("invalid_flight_date", bad_date))

    rules.append(
        (
            "invalid_airline_code",
            out["airline_code"].notna() & ~out["airline_code"].astype("string").str.match(AIRLINE_PATTERN).fillna(False),
        )
    )
    for column in ("origin_airport", "destination_airport"):
        rules.append(
            (
                f"invalid_{column}",
                out[column].notna() & ~out[column].astype("string").str.match(AIRPORT_PATTERN).fillna(False),
            )
        )
    for column in ("cancelled", "diverted"):
        rules.append((f"invalid_{column}_flag", invalid_masks.get(column, pd.Series(False, index=out.index))))
    for column in (
        "departure_delay",
        "arrival_delay",
        "distance",
        "carrier_delay",
        "weather_delay",
        "nas_delay",
        "security_delay",
        "late_aircraft_delay",
    ):
        rules.append((f"non_numeric_{column}", invalid_masks.get(column, pd.Series(False, index=out.index))))

    for column in ("departure_delay", "arrival_delay"):
        values = out[column]
        rules.append(
            (
                f"implausible_{column}",
                values.notna() & ((values < min_delay) | (values > max_delay)),
            )
        )
    rules.append(
        (
            "implausible_distance",
            out["distance"].notna() & ((out["distance"] < 0) | (out["distance"] > max_distance)),
        )
    )

    rejection = pd.Series("", index=out.index, dtype="object")
    counts: dict[str, int] = {}
    for reason, mask in rules:
        mask = mask.fillna(False).astype(bool)
        counts[reason] = int(mask.sum())
        rejection = rejection.mask(mask & (rejection == ""), reason)

    rejected_mask = rejection != ""
    quarantine_columns = [
        "flight_date",
        "airline_code",
        "flight_number",
        "origin_airport",
        "destination_airport",
        "departure_delay",
        "arrival_delay",
        "cancelled",
        "diverted",
        "distance",
    ]
    quarantine = out.loc[rejected_mask, quarantine_columns].copy()
    quarantine.insert(0, "source_row", source_row[rejected_mask].astype(int))
    quarantine["rejection_reasons"] = rejection[rejected_mask]

    valid = out.loc[~rejected_mask].copy()
    return valid, quarantine, {key: value for key, value in counts.items() if value}


def clean_dataframe(
    frame: pd.DataFrame,
    settings: Settings | None = None,
    mapping: dict[str, Any] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int], int]:
    """Standardize, validate, derive and deduplicate one partition in memory."""
    settings = settings or load_settings()
    mapping = mapping or load_schema_mapping()
    validate_schema(frame, mapping)

    valid, quarantine, rejection_counts = standardize(frame, mapping)
    derived = add_derived_columns(valid, settings)

    dedupe_key = [column for column in settings.get("cleaning.dedupe_key", []) if column in derived.columns]
    derived = derived.sort_values(dedupe_key, na_position="last", kind="mergesort")
    duplicate_mask = derived.duplicated(subset=dedupe_key, keep="first") if dedupe_key else pd.Series(False, index=derived.index)
    duplicates_removed = int(duplicate_mask.sum())
    deduplicated = derived.loc[~duplicate_mask]

    ordered = deduplicated.reindex(columns=cleaned_columns(mapping))
    ordered = ordered.sort_values(dedupe_key, na_position="last", kind="mergesort").reset_index(drop=True)
    for int_column in ("flight_year", "flight_month", "day_of_week", "dep_hour", "is_departure_delayed", "is_arrival_delayed", "cancelled", "diverted"):
        if int_column in ordered:
            ordered[int_column] = pd.to_numeric(ordered[int_column], errors="coerce")
    return ordered, quarantine.reset_index(drop=True), rejection_counts, duplicates_removed


# ---------------------------------------------------------------------------
# Partition driver
# ---------------------------------------------------------------------------


def partition_paths(settings: Settings, year: int, month: int) -> tuple[Path, Path, Path]:
    processed = settings.path("data_processed") / f"year={year}" / f"month={month:02d}" / "flights.csv"
    quarantine = settings.path("data_quarantine") / f"year={year}" / f"month={month:02d}" / "rejected.csv"
    report = settings.path("reports") / "data_quality" / f"year={year}" / f"month={month:02d}.json"
    return processed, quarantine, report


def find_source_file(settings: Settings, year: int, month: int) -> Path:
    root = settings.path("data_raw") / "bts" / f"year={year}" / f"month={month:02d}"
    for pattern in ("*.csv", "*.zip"):
        candidates = sorted(root.glob(pattern))
        if candidates:
            return candidates[0]
    archive_root = settings.path("data_raw") / "bts" / f"year={year}"
    for suffix in ("zip", "csv"):
        candidates = sorted(archive_root.glob(f"*{year}_{month}.{suffix}"))
        if candidates:
            return candidates[0]
    raise SchemaValidationError(
        f"No BTS source file for {year}-{month:02d}. Expected a *.zip/*.csv under {archive_root}"
    )


def process_partition(year: int, month: int, settings: Settings | None = None) -> PartitionResult:
    settings = settings or load_settings()
    mapping = load_schema_mapping()
    source = find_source_file(settings, year, month)
    cleaned_path, quarantine_path, report_path = partition_paths(settings, year, month)

    started = time.perf_counter()
    frame = read_source(source, mapping)
    read_seconds = time.perf_counter() - started

    started = time.perf_counter()
    cleaned, quarantine, rejection_counts, duplicates_removed = clean_dataframe(frame, settings, mapping)
    clean_seconds = time.perf_counter() - started

    for path in (cleaned_path, quarantine_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    cleaned.to_csv(cleaned_path, index=False, encoding="utf-8", lineterminator="\n")
    quarantine.to_csv(quarantine_path, index=False, encoding="utf-8", lineterminator="\n")
    write_seconds = time.perf_counter() - started

    timings = {
        "read_seconds": round(read_seconds, 2),
        "clean_seconds": round(clean_seconds, 2),
        "write_seconds": round(write_seconds, 2),
        "total_seconds": round(read_seconds + clean_seconds + write_seconds, 2),
        "rows_per_second": round(len(frame) / max(read_seconds + clean_seconds, 1e-9), 1),
    }

    report = build_quality_report(
        year=year,
        month=month,
        source_file=source,
        rows_read=len(frame),
        cleaned=cleaned,
        quarantine=quarantine,
        rejection_counts=rejection_counts,
        duplicates_removed=duplicates_removed,
        missing_optional=missing_optional_columns(frame, mapping),
        timings=timings,
        mapping=mapping,
    )
    write_report(report, report_path)

    return PartitionResult(
        year=year,
        month=month,
        source_file=source.name,
        cleaned_path=cleaned_path,
        quarantine_path=quarantine_path,
        report_path=report_path,
        rows_read=len(frame),
        rows_cleaned=len(cleaned),
        rows_quarantined=len(quarantine),
        duplicates_removed=duplicates_removed,
        timings=timings,
    )


def parse_months(spec: str) -> list[int]:
    months: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            months.extend(range(int(start), int(end) + 1))
        else:
            months.append(int(part))
    return months


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Clean BTS On-Time Performance partitions.")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--months", default="1", help="e.g. 1, '1-12', '1,6,12'")
    parser.add_argument("--input-file", type=Path, help="clean a single CSV (fixture/E2E mode)")
    args = parser.parse_args(argv)

    settings = load_settings()
    settings.ensure_directories()
    results: list[dict[str, Any]] = []

    if args.input_file:
        mapping = load_schema_mapping()
        cleaned_path, quarantine_path, report_path = partition_paths(settings, args.year, 1)
        for path in (cleaned_path, quarantine_path, report_path):
            path.parent.mkdir(parents=True, exist_ok=True)
        frame = read_source(args.input_file, mapping)
        cleaned, quarantine, rejection_counts, duplicates_removed = clean_dataframe(frame, settings, mapping)
        cleaned.to_csv(cleaned_path, index=False, encoding="utf-8", lineterminator="\n")
        quarantine.to_csv(quarantine_path, index=False, encoding="utf-8", lineterminator="\n")
        report = build_quality_report(
            year=args.year,
            month=1,
            source_file=args.input_file,
            rows_read=len(frame),
            cleaned=cleaned,
            quarantine=quarantine,
            rejection_counts=rejection_counts,
            duplicates_removed=duplicates_removed,
            missing_optional=missing_optional_columns(frame, mapping),
            timings={"total_seconds": 0.0},
            mapping=mapping,
        )
        write_report(report, report_path)
        print(json.dumps({"cleaned": len(cleaned), "quarantined": len(quarantine)}, indent=2))
        return 0

    for month in parse_months(args.months):
        result = process_partition(args.year, month, settings)
        results.append(result.as_dict())
        print(
            f"[{result.year}-{result.month:02d}] read={result.rows_read} "
            f"cleaned={result.rows_cleaned} quarantined={result.rows_quarantined} "
            f"dupes={result.duplicates_removed} in {result.timings['total_seconds']}s"
        )

    summary_path = settings.path("reports") / "data_quality" / "summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "partitions": results,
                "totals": {
                    "rows_read": sum(r["rows_read"] for r in results),
                    "rows_cleaned": sum(r["rows_cleaned"] for r in results),
                    "rows_quarantined": sum(r["rows_quarantined"] for r in results),
                    "duplicates_removed": sum(r["duplicates_removed"] for r in results),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"summary -> {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
