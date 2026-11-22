"""Export analytical result tables to outputs/analytics/.

Two modes:

  reference (default) - compute every analysis from the cleaned partitions with
      the pandas reference implementation. Useful for demos, for the API before
      Hive has run, and for regenerating outputs on a machine without Hadoop.

  hive - delegate to src.hive.run_queries, whose CSV exports overwrite the same
      files. `tests/test_numerical_consistency.py` asserts both paths agree.

    python scripts/export_results.py --method reference
    python scripts/export_results.py --method hive
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common import metrics  # noqa: E402
from src.common.config import load_settings  # noqa: E402

SUMMARY_EXTRA = ("first_date", "last_date")


def cleaned_partitions() -> list[Path]:
    settings = load_settings()
    return sorted(
        path for path in settings.path("data_processed").glob("year=*/month=*/flights.csv") if path.exists()
    )


def load_all() -> pd.DataFrame:
    paths = cleaned_partitions()
    if not paths:
        raise SystemExit(
            "No cleaned partitions found under data/processed. "
            "Run: python -m src.preprocessing.clean_data --year 2025 --months 1-12"
        )
    frames = [metrics.load_cleaned_csv(path) for path in paths]
    return pd.concat(frames, ignore_index=True)


def build_tables(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    summary = metrics.summary(frame)
    summary["first_date"] = str(frame["flight_date"].min())
    summary["last_date"] = str(frame["flight_date"].max())

    return {
        "summary": pd.DataFrame([summary]),
        "airline_performance": metrics.airline_performance(frame),
        "airport_performance": metrics.airport_performance(frame),
        "monthly_trends": metrics.monthly_trends(frame),
        "route_performance": metrics.route_performance(frame, min_flights=0),
        "delay_categories": metrics.delay_category_counts(frame),
        "delay_causes": metrics.delay_cause_summary(frame),
        "cancellations": metrics.cancellation_summary(frame),
        "cancellation_airports": metrics.cancellation_by_airport(frame),
        "day_of_week": metrics.day_of_week_performance(frame),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export analytical result tables")
    parser.add_argument("--method", choices=["reference", "hive"], default="reference")
    args = parser.parse_args(argv)

    settings = load_settings()
    settings.ensure_directories()

    if args.method == "hive":
        from src.hive import run_queries

        run_queries.setup()
        for name in run_queries.QUERIES:
            result = run_queries.run_query(name)
            print(f"[hive] {name}: {result['output_rows']} rows -> {result['exported_to']}")
        return 0

    frame = load_all()
    tables = build_tables(frame)
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "reference-pandas",
        "partitions": [str(path.relative_to(REPO_ROOT)) for path in cleaned_partitions()],
        "total_flights": int(len(frame)),
        "tables": {},
    }
    for name, table in tables.items():
        destination = settings.path("analytics_outputs") / f"{name}.csv"
        destination.parent.mkdir(parents=True, exist_ok=True)
        table.to_csv(destination, index=False, encoding="utf-8", lineterminator="\n")
        manifest["tables"][name] = {"rows": int(len(table)), "path": str(destination.relative_to(REPO_ROOT))}
        print(f"[export] {name}: {len(table)} rows")

    manifest_path = settings.path("reports") / "analytics_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest -> {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
