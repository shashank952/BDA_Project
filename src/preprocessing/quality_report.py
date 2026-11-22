"""Data-quality report construction (JSON).

The report is the audit trail for every downstream claim: row counts, missing
rates per field, rejection reasons and which optional analyses are available.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.common.spec import CAUSE_FIELDS, DELAY_MEASURES


def _numeric_profile(series: pd.Series) -> dict[str, Any]:
    numeric = pd.to_numeric(series, errors="coerce")
    present = numeric.dropna()
    return {
        "missing": int(numeric.isna().sum()),
        "missing_pct": round(100.0 * numeric.isna().mean(), 3),
        "min": None if present.empty else round(float(present.min()), 2),
        "max": None if present.empty else round(float(present.max()), 2),
        "mean": None if present.empty else round(float(present.mean()), 2),
    }


def _categorical_profile(series: pd.Series) -> dict[str, Any]:
    return {
        "missing": int(series.isna().sum()),
        "missing_pct": round(100.0 * series.isna().mean(), 3),
        "distinct": int(series.nunique(dropna=True)),
    }


def build_quality_report(
    *,
    year: int,
    month: int,
    source_file: Path,
    rows_read: int,
    cleaned: pd.DataFrame,
    quarantine: pd.DataFrame,
    rejection_counts: dict[str, int],
    duplicates_removed: int,
    missing_optional: list[str],
    timings: dict[str, float],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    columns: dict[str, Any] = {}
    for name in cleaned.columns:
        series = cleaned[name]
        if name in {*DELAY_MEASURES, *CAUSE_FIELDS, "distance"}:
            columns[name] = _numeric_profile(series)
        else:
            columns[name] = _categorical_profile(series)

    cause_available = all(field in cleaned.columns and cleaned[field].notna().any() for field in CAUSE_FIELDS)
    period = {
        "from": None if cleaned.empty else str(cleaned["flight_date"].min()),
        "to": None if cleaned.empty else str(cleaned["flight_date"].max()),
    }

    return {
        "schema_version": mapping.get("source", {}).get("dataset", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "partition": {"year": year, "month": month},
        "source_file": source_file.name,
        "source_size_mb": round(source_file.stat().st_size / (1024 * 1024), 2) if source_file.exists() else None,
        "period": period,
        "rows": {
            "read": int(rows_read),
            "cleaned": int(len(cleaned)),
            "quarantined": int(len(quarantine)),
            "duplicates_removed": int(duplicates_removed),
            "cancelled": int(pd.to_numeric(cleaned.get("cancelled"), errors="coerce").fillna(0).sum()),
            "diverted": int(pd.to_numeric(cleaned.get("diverted"), errors="coerce").fillna(0).sum()),
            "clean_pct": round(100.0 * len(cleaned) / rows_read, 3) if rows_read else 0.0,
        },
        "rejections": rejection_counts,
        "field_availability": {
            "delay_causes": cause_available,
            "missing_optional_source_columns": missing_optional,
        },
        "columns": columns,
        "timings": timings,
        "definitions": {
            "missing": "Count of null values after standardized missing-marker handling.",
            "delay_causes": "BTS reports cause minutes only for flights delayed >= 15 minutes.",
        },
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
