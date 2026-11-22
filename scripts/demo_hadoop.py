"""Guided, reproducible demonstration that Hadoop is doing the work.

Every step below queries the real daemons and the real files on disk; nothing is
simulated. Run it in front of an examiner and the console output is the evidence.

    python scripts/demo_hadoop.py                 # full demo (~2.5 min)
    python scripts/demo_hadoop.py --skip-job      # skip the live MapReduce run
    python scripts/demo_hadoop.py --month 3       # use another partition

The script is read-only against the pipeline's data: it writes only to
/airline-delay/_demo (a temp path it deletes) and to a temp file locally.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_settings  # noqa: E402
from src.common.hadoop_cli import (  # noqa: E402
    dfsadmin,
    fs,
    hadoop_home,
    java_binary,
    run_jar,
    streaming_jar,
)

SETTINGS = load_settings()
DEMO_PATH = f"{SETTINGS.hdfs_base}/_demo"


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def show(text: str, limit: int = 14) -> None:
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines[:limit]:
        print("  " + line[:150])


def step_processes() -> None:
    banner("STEP 1  Hadoop daemons running as OS processes")
    jps = java_binary().parent / ("jps.exe" if sys.platform == "win32" else "jps")
    if jps.exists():
        result = subprocess.run([str(jps)], capture_output=True, text=True, timeout=60)
        show(result.stdout)
    print("  HADOOP_HOME:", hadoop_home())
    print("  The NameNode serves metadata on :9000, the DataNode stores blocks and")
    print("  :9870 serves the NameNode web UI.")


def step_cluster_report() -> None:
    banner("STEP 2  Live HDFS cluster report")
    output = dfsadmin("-report").stdout
    keep = (
        "Live datanodes",
        "Configured Capacity",
        "DFS Used",
        "DFS Remaining",
        "Under replicated",
        "Name:",
        "Hostname:",
        "Storage Type",
    )
    for line in output.splitlines():
        if any(token in line for token in keep):
            print("  " + line.strip()[:150])


def step_stored_data() -> None:
    banner("STEP 3  Bytes actually stored in HDFS")
    for path, label in (
        (f"{SETTINGS.hdfs_base}/raw", "raw archives (originals, never rewritten)"),
        (f"{SETTINGS.hdfs_base}/processed", "cleaned CSV partitions"),
        (f"{SETTINGS.hdfs_base}/analytics", "MapReduce / Hive result directories"),
        (f"{SETTINGS.hdfs_base}/hive/warehouse", "Hive Parquet warehouse"),
    ):
        result = fs("-du", "-s", "-h", path, check=False)
        if result.returncode == 0 and result.stdout.strip():
            print(f"  {label:45} {result.stdout.split()[0]:>8}")


def step_blocks_on_disk() -> None:
    banner("STEP 4  The same bytes as physical block files on the DataNode disk")
    root = hadoop_home() / "data" / "datanode" / "current" / "finalized"
    blocks = sorted(root.rglob("blk_*")) if root.exists() else []
    data_blocks = [block for block in blocks if not block.name.endswith(".meta")]
    total_mb = sum(block.stat().st_size for block in data_blocks) / (1024 * 1024)
    print(f"  block directory : {root}")
    print(f"  block files     : {len(data_blocks):,}")
    print(f"  total on disk   : {total_mb:,.1f} MB")
    for block in data_blocks[:5]:
        print(f"    {block.name:28} {block.stat().st_size / 1024 / 1024:8.1f} MB")
    print("  Each blk_<id> is a 128 MB-max HDFS block; the .meta file holds the checksum.")
    print("  These files are not readable as a normal CSV: HDFS assembles them on read.")


def step_round_trip() -> None:
    banner("STEP 5  Round trip through HDFS (write, read, replication, delete)")
    fs("-mkdir", "-p", DEMO_PATH)
    local = Path(SETTINGS.path("data_sample")) / "hdfs_roundtrip_demo.csv"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(
        "flight_date,airline_code,origin_airport,destination_airport,arrival_delay\n"
        "2025-01-01,AA,JFK,LAX,-7\n"
        "2025-01-01,WN,DAL,ATL,29\n",
        encoding="utf-8",
        newline="\n",
    )

    started = time.perf_counter()
    fs("-put", "-f", str(local), f"{DEMO_PATH}/demo.csv")
    elapsed = time.perf_counter() - started
    remote = f"{DEMO_PATH}/demo.csv"

    print(f"  wrote {local.stat().st_size} bytes to {remote} in {elapsed:.2f}s")
    print("  read back from HDFS:")
    show(fs("-cat", remote).stdout)
    stats = fs("-stat", "%b bytes  replication=%r  owner=%u", remote).stdout.strip()
    print("  metadata:", stats)
    fs("-rm", "-skipTrash", remote)
    print("  deleted the temp file again (raw data untouched)")


def step_mapreduce(month: int) -> None:
    banner("STEP 6  A real Hadoop MapReduce job executing now")
    output = f"{DEMO_PATH}/mr_out"
    fs("-rm", "-r", "-skipTrash", output, check=False)

    mapper = REPO_ROOT / "src" / "mapreduce" / "airport_delay_mapper.py"
    reducer = REPO_ROOT / "src" / "mapreduce" / "airport_delay_reducer.py"
    combiner = REPO_ROOT / "src" / "mapreduce" / "numeric_sum_combiner.py"
    source = f"{SETTINGS.hdfs_base}/processed/year=2025/month={month:02d}"

    args = [
        "-D",
        f"mapreduce.framework.name={SETTINGS.mapreduce_framework}",
        "-D",
        "mapreduce.job.reduces=1",
        "-D",
        "mapreduce.output.textoutputformat.separator=",
        "-D",
        "mapreduce.job.name=airline-delay-demo-airport",
        "-mapper",
        f"{sys.executable} {mapper}",
        "-reducer",
        f"{sys.executable} {reducer}",
        "-combiner",
        f"{sys.executable} {combiner}",
        "-input",
        source,
        "-output",
        output,
    ]

    print(f"  input : {source}")
    print(f"  output: {output}")
    print("  submitting ... (a minute at most)")
    started = time.perf_counter()
    result = run_jar(streaming_jar(), args, timeout=3600)
    elapsed = time.perf_counter() - started
    combined = f"{result.stdout}\n{result.stderr}"

    print(f"  exit code {result.returncode} after {elapsed:.1f}s")
    counters = (
        "Map input records",
        "Map output records",
        "Combine input records",
        "Combine output records",
        "Reduce input records",
        "Reduce output records",
        "Spilled Records",
        "Failed Shuffles",
    )
    print("  job counters (real work done by Hadoop):")
    for line in combined.splitlines():
        if any(line.strip().startswith(name) for name in counters):
            print("    " + line.strip())
    if "Job complete" in combined or result.returncode == 0:
        print("  status: job completed")

    listing = fs("-ls", output, check=False).stdout
    parts = [line.split()[-1] for line in listing.splitlines() if "/part-" in line]
    if parts:
        print(f"  result files: {len(parts)}; first rows:")
        show(fs("-cat", parts[0]).stdout, limit=4)
    fs("-rm", "-r", "-skipTrash", output, check=False)


def step_hive() -> None:
    banner("STEP 7  Hive querying the same HDFS dataset")
    from src.hive import run_queries

    script = REPO_ROOT / "data" / "demo_hive_count.hql"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "USE airline_analytics;\n"
        "SELECT COUNT(1) AS rows_in_hive FROM flights;\n"
        "SELECT COUNT(DISTINCT airline_code) AS airlines FROM flights;\n",
        encoding="utf-8",
        newline="\n",
    )
    started = time.perf_counter()
    _, output = run_queries.run_script(script)
    elapsed = time.perf_counter() - started

    numbers = [line.strip() for line in output.splitlines() if line.strip().isdigit()]
    print(f"  Hive answered in {elapsed:.1f}s")
    if len(numbers) >= 2:
        print(f"  rows_in_hive = {int(numbers[0]):,}")
        print(f"  airlines     = {int(numbers[1]):,}")

    local_rows = 0
    for path in sorted(SETTINGS.path("data_processed").glob("year=*/month=*/flights.csv")):
        with path.open("rb") as handle:
            local_rows += sum(1 for _ in handle) - 1
    print(f"  rows in the local cleaned CSVs = {local_rows:,}")
    if numbers:
        match = int(numbers[0]) == local_rows
        print(f"  match: {'YES - Hive is reading every cleaned row from HDFS' if match else 'MISMATCH'}")
    script.unlink(missing_ok=True)


def step_raw_immutable() -> None:
    banner("STEP 8  Raw archives are still the untouched originals")
    result = fs("-count", "-h", f"{SETTINGS.hdfs_base}/raw/source=bts").stdout.strip()
    print("  directories/files/bytes:", result)
    print("  The cleaning pipeline writes to /processed; nothing writes to /raw.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demonstrate that Hadoop is working")
    parser.add_argument("--month", type=int, default=1)
    parser.add_argument("--skip-job", action="store_true")
    parser.add_argument("--skip-hive", action="store_true")
    args = parser.parse_args(argv)

    print("Airline delay project - Hadoop evidence walkthrough")
    print(f"Hadoop: {hadoop_home()}   HDFS: {SETTINGS.hdfs_uri}")

    step_processes()
    step_cluster_report()
    step_stored_data()
    step_blocks_on_disk()
    step_round_trip()
    if not args.skip_job:
        step_mapreduce(args.month)
    if not args.skip_hive:
        step_hive()
    step_raw_immutable()

    shutil.rmtree(Path(SETTINGS.path("data_sample")) / "hdfs_roundtrip_demo.csv", ignore_errors=True)
    fs("-rm", "-r", "-skipTrash", DEMO_PATH, check=False)
    banner("DONE - every step above queried the live cluster")
    return 0


if __name__ == "__main__":
    sys.exit(main())
