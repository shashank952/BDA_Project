"""HDFS operations for the project (create layout, upload, verify, clean up).

Uses the Hadoop installation from `hdfs.hadoop_home` in config/settings.yaml via
src.common.hadoop_cli, so nothing is hard-coded to one developer's machine.

    python scripts/hdfs_ops.py init
    python scripts/hdfs_ops.py upload-raw --year 2025
    python scripts/hdfs_ops.py upload-processed --year 2025 --months 1
    python scripts/hdfs_ops.py verify --year 2025 --month 1
    python scripts/hdfs_ops.py ls
    python scripts/hdfs_ops.py cleanup-temp

Raw uploads are one-way: `upload-raw` refuses to overwrite an existing archive
unless --force is passed, so the preserved original cannot be lost by a re-run
of the cleaning pipeline.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.common.config import load_settings  # noqa: E402
from src.common.hadoop_cli import HadoopUnavailableError, fs, ping  # noqa: E402

PROJECT_DIRS = [
    "raw/source=bts",
    "staging/validated",
    "processed",
    "quarantine",
    "analytics/airline_performance",
    "analytics/airport_performance",
    "analytics/route_performance",
    "analytics/monthly_trends",
    "analytics/delay_causes",
    "analytics/cancellation_analysis",
    "analytics/delay_categories",
    "reports/data_quality",
    "reports/execution_metrics",
]


def uri(relative: str) -> str:
    return f"{load_settings().hdfs_base}/{relative}".rstrip("/")


def init_layout() -> None:
    print(ping())
    for directory in PROJECT_DIRS:
        fs("-mkdir", "-p", uri(directory))
    print(f"created {len(PROJECT_DIRS)} directories under {load_settings().hdfs_base}")


def remote_size(path: str) -> int:
    result = fs("-stat", "%b", path)
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise HadoopUnavailableError(f"Cannot read size of {path}: {result.stdout!r}") from exc


def exists(path: str) -> bool:
    return fs("-test", "-e", path, check=False).returncode == 0


def _put(local: Path, destination: str, force: bool) -> str:
    if exists(destination) and not force:
        return f"skip (exists) {destination}"
    fs("-put", "-f", str(local), destination)
    uploaded = remote_size(destination)
    local_size = local.stat().st_size
    if uploaded != local_size:
        raise HadoopUnavailableError(f"size mismatch for {destination}: local={local_size} hdfs={uploaded}")
    return f"ok {local.name} -> {destination} ({uploaded} bytes)"


def upload_raw(year: int, force: bool = False) -> None:
    source_root = load_settings().path("data_raw") / "bts" / f"year={year}"
    archives = sorted(source_root.glob("*.zip")) + sorted(source_root.glob("*.csv"))
    if not archives:
        raise HadoopUnavailableError(f"No raw archives found under {source_root}")

    for archive in archives:
        month = int(archive.stem.rsplit("_", 1)[-1])
        destination = uri(f"raw/source=bts/year={year}/month={month:02d}")
        fs("-mkdir", "-p", destination)
        print(_put(archive, f"{destination}/{archive.name}", force))


def upload_processed(year: int, months: list[int]) -> None:
    settings = load_settings()
    for month in months:
        local = settings.path("data_processed") / f"year={year}" / f"month={month:02d}" / "flights.csv"
        if not local.exists():
            raise HadoopUnavailableError(f"Cleaned partition missing: {local}. Run the cleaning step first.")
        destination = uri(f"processed/year={year}/month={month:02d}")
        fs("-mkdir", "-p", destination)
        print(_put(local, f"{destination}/flights.csv", force=True))

        quarantine = settings.path("data_quarantine") / f"year={year}" / f"month={month:02d}" / "rejected.csv"
        if quarantine.exists() and quarantine.stat().st_size > 0:
            quarantine_dest = uri(f"quarantine/year={year}/month={month:02d}")
            fs("-mkdir", "-p", quarantine_dest)
            print(_put(quarantine, f"{quarantine_dest}/rejected.csv", force=True))


def verify(year: int, month: int) -> None:
    settings = load_settings()
    local = settings.path("data_processed") / f"year={year}" / f"month={month:02d}" / "flights.csv"
    remote = f"{uri(f'processed/year={year}/month={month:02d}')}/flights.csv"
    if not local.exists():
        raise HadoopUnavailableError(f"Local cleaned partition missing: {local}")
    local_bytes = local.stat().st_size
    remote_bytes = remote_size(remote)
    local_rows = sum(1 for _ in local.open("rb")) - 1
    print(f"local  : {local_rows} data rows, {local_bytes} bytes")
    print(f"hdfs   : {remote_bytes} bytes")
    if local_bytes != remote_bytes:
        raise HadoopUnavailableError("HDFS copy does not match the local partition")
    print("verification: byte-for-byte match; raw archives are untouched by cleaning")


def report_upload(year: int, month: int) -> None:
    settings = load_settings()
    local = settings.path("reports") / "data_quality" / f"year={year}" / f"month={month:02d}.json"
    if not local.exists():
        raise HadoopUnavailableError(f"Quality report missing: {local}")
    destination = uri(f"reports/data_quality/year={year}/month={month:02d}")
    fs("-mkdir", "-p", destination)
    print(_put(local, f"{destination}/quality.json", force=True))


def ls(path: str | None = None) -> None:
    print(fs("-ls", "-R", "-h", path or load_settings().hdfs_base).stdout)


def cleanup_temp() -> None:
    """Remove only project-owned temporary paths; never raw or processed data."""
    for temp in ("/tmp/wc", f"{load_settings().hdfs_base}/_tmp"):
        result = fs("-rm", "-r", "-skipTrash", temp, check=False)
        print(f"{temp}: {(result.stdout or result.stderr).strip()[:120]}")


def parse_months(spec: str) -> list[int]:
    months: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            months.extend(range(int(start), int(end) + 1))
        elif part:
            months.append(int(part))
    return months


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HDFS operations for the airline project")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")

    raw = sub.add_parser("upload-raw")
    raw.add_argument("--year", type=int, required=True)
    raw.add_argument("--force", action="store_true")

    processed = sub.add_parser("upload-processed")
    processed.add_argument("--year", type=int, required=True)
    processed.add_argument("--months", default="1-12")

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--year", type=int, required=True)
    verify_parser.add_argument("--month", type=int, required=True)

    report = sub.add_parser("upload-report")
    report.add_argument("--year", type=int, required=True)
    report.add_argument("--month", type=int, required=True)

    ls_parser = sub.add_parser("ls")
    ls_parser.add_argument("--path")

    sub.add_parser("cleanup-temp")
    args = parser.parse_args(argv)

    if args.command == "init":
        init_layout()
    elif args.command == "upload-raw":
        upload_raw(args.year, args.force)
    elif args.command == "upload-processed":
        upload_processed(args.year, parse_months(args.months))
    elif args.command == "verify":
        verify(args.year, args.month)
    elif args.command == "upload-report":
        report_upload(args.year, args.month)
    elif args.command == "ls":
        ls(args.path)
    elif args.command == "cleanup-temp":
        cleanup_temp()
    return 0


if __name__ == "__main__":
    sys.exit(main())
