"""Execute the Hive DDL + analytical queries and export their CSV results.

    python -m src.hive.run_queries --setup          # database + tables + Parquet
    python -m src.hive.run_queries --all            # setup + every query
    python -m src.hive.run_queries --query monthly_trends
    python -m src.hive.run_queries --all --validate

Each query writes to its own HDFS directory via INSERT OVERWRITE DIRECTORY, so a
re-run replaces the previous result instead of appending to it. The exported CSV
in outputs/analytics/ is what the Flask API serves.

Hive is invoked through `org.apache.hadoop.hive.cli.CliDriver` directly. The
shipped `hive.cmd` wrapper is not used because the `.cmd` wrappers on this
machine were observed to return exit code 0 for failed commands.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
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
from src.common.config import load_settings  # noqa: E402
from src.common.hadoop_cli import HadoopUnavailableError, classpath, fs, hadoop_env, java_binary  # noqa: E402
from src.common.validate import compare_file  # noqa: E402

HIVE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Query:
    name: str
    script: str
    header: str
    hdfs_dir: str
    description: str


QUERIES: dict[str, Query] = {
    "airline_performance": Query(
        name="airline_performance",
        script="03_airline_performance.hql",
        header=(
            "airline_code,total_flights,valid_departure_flights,avg_departure_delay,"
            "departure_delayed_flights,departure_delay_rate,valid_arrival_flights,"
            "avg_arrival_delay,delayed_arrivals,arrival_delay_rate,cancellations,cancellation_rate"
        ),
        hdfs_dir="analytics/airline_performance",
        description="Query A - airline performance",
    ),
    "airport_performance": Query(
        name="airport_performance",
        script="04_airport_performance.hql",
        header="role,airport_code,total_flights,valid_delay_flights,avg_delay,delayed_flights,delay_rate",
        hdfs_dir="analytics/airport_performance",
        description="Query B - airport performance (departure and arrival roles)",
    ),
    "monthly_trends": Query(
        name="monthly_trends",
        script="05_monthly_trends.hql",
        header=(
            "flight_year,flight_month,total_flights,valid_arrival_flights,"
            "avg_arrival_delay,delayed_arrivals,arrival_delay_rate,cancellations,cancellation_rate"
        ),
        hdfs_dir="analytics/monthly_trends",
        description="Query C - monthly trends",
    ),
    "route_performance": Query(
        name="route_performance",
        script="06_route_analysis.hql",
        header=(
            "route,origin_airport,destination_airport,total_flights,"
            "valid_arrival_flights,avg_arrival_delay,delayed_arrivals,arrival_delay_rate"
        ),
        hdfs_dir="analytics/route_performance",
        description="Query E - route performance",
    ),
    "delay_causes": Query(
        name="delay_causes",
        script="07_delay_causes.hql",
        header="cause,delay_minutes,flights_with_cause,share_pct",
        hdfs_dir="analytics/delay_causes",
        description="Query F - delay cause distribution",
    ),
    "cancellations": Query(
        name="cancellations",
        script="08_cancellations.hql",
        header="airline_code,flight_year,flight_month,total_flights,cancellations,cancellation_rate",
        hdfs_dir="analytics/cancellation_analysis",
        description="Query G - cancellations by airline and month",
    ),
    "cancellation_airports": Query(
        name="cancellation_airports",
        script="09_cancellation_airports.hql",
        header=(
            "origin_airport,flight_year,flight_month,total_flights,cancellations,cancellation_rate,"
            "cancelled_carrier,cancelled_weather,cancelled_nas,cancelled_security"
        ),
        hdfs_dir="analytics/cancellation_analysis",
        description="Query G - cancellations by origin airport and month",
    ),
    "delay_categories": Query(
        name="delay_categories",
        script="10_delay_categories.hql",
        header="delay_category,flights,share_pct",
        hdfs_dir="analytics/delay_categories",
        description="Query D - delay category distribution",
    ),
    "day_of_week": Query(
        name="day_of_week",
        script="11_day_of_week.hql",
        header=(
            "day_of_week,total_flights,valid_arrival_flights,avg_arrival_delay,"
            "delayed_arrivals,arrival_delay_rate"
        ),
        hdfs_dir="analytics/day_of_week",
        description="Day-of-week comparison",
    ),
    "summary": Query(
        name="summary",
        script="12_summary.hql",
        header=(
            "total_flights,valid_departure_flights,valid_arrival_flights,avg_departure_delay,"
            "avg_arrival_delay,departure_delayed_flights,arrival_delayed_flights,"
            "departure_delay_rate,arrival_delay_rate,cancelled_flights,cancellation_rate,"
            "diverted_flights,first_date,last_date"
        ),
        hdfs_dir="analytics/summary",
        description="Overall KPIs",
    ),
}

SETUP_SCRIPTS = ("01_create_database.hql", "02_create_tables.hql")


def hive_home() -> Path:
    home = Path(load_settings().get("hive.home"))
    if not (home / "lib").exists():
        raise HadoopUnavailableError(
            f"Hive not found at {home}. Download apache-hive-3.1.3-bin.tar.gz, extract it, "
            "and update config/settings.yaml -> hive.home."
        )
    return home


def hive_env() -> dict[str, str]:
    env = hadoop_env()
    settings = load_settings()
    env["HIVE_HOME"] = str(hive_home())
    env["HIVE_CONF_DIR"] = str((REPO_ROOT / str(settings.get("hive.conf_dir"))))
    return env


def hive_classpath() -> str:
    settings = load_settings()
    conf_dir = REPO_ROOT / str(settings.get("hive.conf_dir"))
    return os.pathsep.join([classpath("mapreduce"), str(hive_home() / "lib" / "*")])


def run_script(script: Path, extra_conf: dict[str, str] | None = None, timeout: int = 3600) -> tuple[int, str]:
    args = [str(java_binary()), "-Xmx2g", "-Dhive.root.logger=WARN,console", "-cp", hive_classpath(),
            "org.apache.hadoop.hive.cli.CliDriver", "-f", str(script)]
    for key, value in (extra_conf or {}).items():
        args.extend(["--hiveconf", f"{key}={value}"])
    result = subprocess.run(args, capture_output=True, text=True, env=hive_env(), timeout=timeout)
    output = (result.stdout or "") + (result.stderr or "")
    # The CLI exits 0 even for failed statements, and Hive may log a failed
    # local-mode attempt before retrying successfully as a MapReduce job. The
    # reliable success signals are therefore the exit code plus, in run_query(),
    # the existence of a non-empty result directory.
    if result.returncode != 0:
        meaningful = [line for line in output.splitlines() if line.strip()]
        tail = "\n".join(meaningful[-15:])
        raise HadoopUnavailableError(f"Hive failed on {script.name} (exit {result.returncode}):\n{tail}")
    if "FAILED: Execution Error" in output:
        print(f"[warn] Hive logged a failed attempt on {script.name}; verifying the output directory")
    return result.returncode, output


def setup() -> None:
    settings = load_settings()
    settings.path("metastore").mkdir(parents=True, exist_ok=True)
    fs("-mkdir", "-p", "/airline-delay/hive/warehouse")
    fs("-mkdir", "-p", "/tmp/hive")
    for script in SETUP_SCRIPTS:
        started = time.perf_counter()
        _, output = run_script(HIVE_DIR / script)
        elapsed = round(time.perf_counter() - started, 2)
        print(f"[setup] {script} ok in {elapsed}s")
        for line in output.splitlines():
            if "row_count" in line or line.strip().isdigit() or "\t" in line and "Time taken" not in line:
                continue


def run_query(name: str) -> dict:
    settings = load_settings()
    spec = QUERIES[name]
    outdir = f"{settings.hdfs_base}/{spec.hdfs_dir}/hive"
    fs("-rm", "-r", "-skipTrash", outdir, check=False)

    started = time.perf_counter()
    run_script(
        HIVE_DIR / spec.script,
        {"outdir": outdir, "min_route_flights": "0"},
    )
    elapsed = round(time.perf_counter() - started, 2)

    listing = fs("-ls", outdir, check=False)
    if listing.returncode != 0:
        raise HadoopUnavailableError(f"Query {name} produced no output directory {outdir}")
    part_files = [line.split()[-1] for line in listing.stdout.splitlines() if "/000000_" in line]
    if not part_files:
        raise HadoopUnavailableError(f"Query {name} produced no result files in {outdir}")

    rows: list[str] = []
    for part in part_files:
        rows.extend(line for line in fs("-cat", part).stdout.splitlines() if line.strip())

    destination = settings.path("analytics_outputs") / f"{name}.csv"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(spec.header + "\n" + "\n".join(rows) + "\n", encoding="utf-8", newline="\n")

    return {
        "query": name,
        "description": spec.description,
        "hdfs_output": outdir,
        "output_rows": len(rows),
        "seconds": elapsed,
        "exported_to": str(destination.relative_to(REPO_ROOT)),
        "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def reference_frame() -> pd.DataFrame:
    settings = load_settings()
    frames = []
    for month_dir in sorted(settings.path("data_processed").glob("year=*/month=*")):
        path = month_dir / "flights.csv"
        if path.exists():
            frames.append(metrics.load_cleaned_csv(path))
    if not frames:
        raise HadoopUnavailableError("No cleaned partitions found; run the cleaning step first")
    return pd.concat(frames, ignore_index=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Hive setup and analytical queries")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--query", choices=list(QUERIES))
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)

    settings = load_settings()
    settings.ensure_directories()

    if args.setup or args.all:
        setup()
    if not args.all and not args.query:
        return 0

    selected = list(QUERIES) if args.all else [args.query]
    results = []
    for name in selected:
        result = run_query(name)
        results.append(result)
        print(f"[ok] {name}: {result['output_rows']} rows in {result['seconds']}s -> {result['exported_to']}")

    metrics_path = settings.path("reports") / "execution_metrics" / "hive_runs.json"
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    previous = []
    if metrics_path.exists():
        try:
            previous = json.loads(metrics_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = []
    metrics_path.write_text(json.dumps(previous + results, indent=2), encoding="utf-8")

    if args.validate:
        frame = reference_frame()
        problems: list[str] = []
        for result in results:
            path = settings.path("analytics_outputs") / f"{result['query']}.csv"
            problems.extend(compare_file(result["query"], path, frame))
        if problems:
            print("\nVALIDATION FAILED")
            for problem in problems:
                print(" -", problem)
            return 1
        print("validation: Hive output matches the reference implementation")

    print(f"total Hive time: {round(sum(r['seconds'] for r in results), 2)}s; metrics -> {metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
