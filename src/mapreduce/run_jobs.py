"""Hadoop Streaming job registry, runner and result exporter.

    python -m src.mapreduce.run_jobs --year 2025 --months 1
    python -m src.mapreduce.run_jobs --year 2025 --months 1 --validate

Each run:
  1. deletes the previous HDFS output directory (no silent result accumulation);
  2. submits the streaming job with one reducer (single ordered part file);
  3. fails loudly on a non-zero exit code or a missing output directory;
  4. copies the result to outputs/analytics/<job>.csv with the documented header;
  5. records execution metrics under outputs/reports/execution_metrics/.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common import metrics  # noqa: E402
from src.common.validate import compare_file  # noqa: E402
from src.common.config import load_settings  # noqa: E402
from src.common.hadoop_cli import HadoopUnavailableError, fs, run_jar, streaming_jar  # noqa: E402

MAPREDUCE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class JobSpec:
    name: str
    mapper: str
    reducer: str
    header: str
    hdfs_dir: str
    description: str


JOBS: dict[str, JobSpec] = {
    "airline_performance": JobSpec(
        name="airline_performance",
        mapper="airline_delay_mapper.py",
        reducer="airline_delay_reducer.py",
        header=(
            "airline_code,total_flights,valid_departure_flights,avg_departure_delay,"
            "departure_delayed_flights,departure_delay_rate,valid_arrival_flights,"
            "avg_arrival_delay,delayed_arrivals,arrival_delay_rate,cancellations,cancellation_rate"
        ),
        hdfs_dir="analytics/airline_performance",
        description="Airline delay summary (departure + arrival metrics per carrier)",
    ),
    "airport_performance": JobSpec(
        name="airport_performance",
        mapper="airport_delay_mapper.py",
        reducer="airport_delay_reducer.py",
        header="role,airport_code,total_flights,valid_delay_flights,avg_delay,delayed_flights,delay_rate",
        hdfs_dir="analytics/airport_performance",
        description="Airport delay statistics split by departure / arrival role",
    ),
    "monthly_trends": JobSpec(
        name="monthly_trends",
        mapper="monthly_trend_mapper.py",
        reducer="monthly_trend_reducer.py",
        header=(
            "flight_year,flight_month,total_flights,valid_arrival_flights,"
            "avg_arrival_delay,delayed_arrivals,arrival_delay_rate,cancellations,cancellation_rate"
        ),
        hdfs_dir="analytics/monthly_trends",
        description="Monthly arrival-delay trend across all processed partitions",
    ),
    "route_performance": JobSpec(
        name="route_performance",
        mapper="route_delay_mapper.py",
        reducer="route_delay_reducer.py",
        header=(
            "route,origin_airport,destination_airport,total_flights,"
            "valid_arrival_flights,avg_arrival_delay,delayed_arrivals,arrival_delay_rate"
        ),
        hdfs_dir="analytics/route_performance",
        description="Route-level arrival delay analysis (composite origin-destination key)",
    ),
}


def _streaming_command(script: str, framework: str) -> str:
    """Streaming command line.

    LocalJobRunner needs absolute paths; cluster mode relies on -files
    localization. The command is intentionally unquoted: Hadoop's Streaming
    argument parser on Windows inserts an empty argv entry when the executable
    is quoted, which makes the interpreter exit with code 2.
    """
    path = MAPREDUCE_DIR / script
    if framework == "local":
        return f"{sys.executable} {path}"
    return f"python {script}"


def _localized_files(scripts: tuple[str, ...], framework: str) -> list[str]:
    """`-files` values.

    LocalJobRunner runs the command on this machine, so absolute paths in the
    mapper/reducer command are enough and no localization is needed (Hadoop
    would try to parse the Windows paths as URIs and reject the drive letter).
    For cluster mode the scripts must be shipped, as file:// URIs.
    """
    if framework == "local":
        return []
    return ["-files", ",".join((MAPREDUCE_DIR / script).as_uri() for script in scripts)]


def run_job(name: str, year: int, months: list[int]) -> dict:
    settings = load_settings()
    spec = JOBS[name]
    framework = settings.mapreduce_framework

    inputs: list[str] = []
    for month in months:
        inputs.extend(["-input", f"{settings.hdfs_base}/processed/year={year}/month={month:02d}"])

    output = f"{settings.hdfs_base}/{spec.hdfs_dir}/mr"
    fs("-rm", "-r", "-skipTrash", output, check=False)

    args = [
        "-D",
        f"mapreduce.framework.name={framework}",
        "-D",
        "mapreduce.job.reduces=1",
        "-D",
        "mapreduce.output.textoutputformat.separator=",
        "-D",
        f"mapreduce.job.name=airline-delay-{spec.name}",
        *_localized_files((spec.mapper, spec.reducer, "numeric_sum_combiner.py"), framework),
        "-mapper",
        _streaming_command(spec.mapper, framework),
        "-reducer",
        _streaming_command(spec.reducer, framework),
        "-combiner",
        _streaming_command("numeric_sum_combiner.py", framework),
        *inputs,
        "-output",
        output,
    ]

    started = time.perf_counter()
    result = run_jar(streaming_jar(), args, timeout=3600)
    elapsed = round(time.perf_counter() - started, 2)
    combined = f"{result.stdout}\n{result.stderr}"

    if result.returncode != 0 or "Job not successful" in combined:
        tail = "\n".join(combined.strip().splitlines()[-15:])
        raise HadoopUnavailableError(
            f"MapReduce job '{name}' failed (exit {result.returncode}) after {elapsed}s:\n{tail}"
        )

    listing = fs("-ls", output)
    part_files = [
        line.split()[-1] for line in listing.stdout.splitlines() if "/part-" in line
    ]
    if not part_files:
        raise HadoopUnavailableError(f"Job '{name}' produced no part files in {output}")

    rows: list[str] = []
    for part in part_files:
        content = fs("-cat", part).stdout
        rows.extend(line.rstrip("\t\r") for line in content.splitlines() if line.strip())

    destination = settings.path("analytics_outputs") / "mapreduce" / f"{spec.name}.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(spec.header + "\n" + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")

    return {
        "job": name,
        "description": spec.description,
        "framework": framework,
        "inputs": [value for value in inputs if value.startswith(settings.hdfs_base)],
        "hdfs_output": output,
        "part_files": len(part_files),
        "output_rows": len(rows),
        "seconds": elapsed,
        "exit_code": result.returncode,
        "exported_to": str(destination.relative_to(REPO_ROOT)),
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _reference_frames(year: int, months: list[int]) -> pd.DataFrame:
    settings = load_settings()
    frames = []
    for month in months:
        path = settings.path("data_processed") / f"year={year}" / f"month={month:02d}" / "flights.csv"
        if not path.exists():
            raise HadoopUnavailableError(f"Cleaned partition missing for validation: {path}")
        frames.append(metrics.load_cleaned_csv(path))
    return pd.concat(frames, ignore_index=True)


def validate(name: str, year: int, months: list[int], tolerance: float = 0.01) -> list[str]:
    """Compare exported MapReduce output with the pandas reference implementation."""
    settings = load_settings()
    path = settings.path("analytics_outputs") / "mapreduce" / f"{name}.csv"
    return compare_file(name, path, _reference_frames(year, months), tolerance=tolerance)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Hadoop Streaming MapReduce jobs")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--months", default="1-12")
    parser.add_argument("--job", default="all", choices=[*JOBS.keys(), "all"])
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--validate-only", action="store_true", help="validate existing exports without re-running jobs")
    args = parser.parse_args(argv)

    settings = load_settings()
    settings.ensure_directories()
    months = []
    for part in args.months.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            months.extend(range(int(start), int(end) + 1))
        elif part:
            months.append(int(part))

    if args.validate_only:
        problems: list[str] = []
        for name in (list(JOBS) if args.job == "all" else [args.job]):
            problems.extend(validate(name, args.year, months))
        if problems:
            print("VALIDATION FAILED")
            for problem in problems:
                print(" -", problem)
            return 1
        print("validation: existing MapReduce exports match the reference implementation")
        return 0

    selected = list(JOBS) if args.job == "all" else [args.job]
    results = []
    for name in selected:
        print(f"[run] {name} ...", flush=True)
        result = run_job(name, args.year, months)
        results.append(result)
        print(f"[ok ] {name}: {result['output_rows']} rows in {result['seconds']}s -> {result['exported_to']}")

    metrics_path = settings.path("reports") / "execution_metrics" / "mapreduce_runs.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    previous = []
    if metrics_path.exists():
        try:
            previous = json.loads(metrics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = []
    metrics_path.write_text(json.dumps(previous + results, indent=2), encoding="utf-8")

    problems = []
    if args.validate:
        for result in results:
            problems.extend(validate(result["job"], args.year, months))
        if problems:
            print("\nVALIDATION FAILED")
            for problem in problems:
                print(" -", problem)
            return 1
        print("validation: MapReduce output matches the reference implementation")

    total = round(sum(result["seconds"] for result in results), 2)
    print(f"total MapReduce time: {total}s; metrics -> {metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
