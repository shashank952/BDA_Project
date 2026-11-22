"""Download monthly BTS On-Time Performance archives.

The public BTS download page is a POST form. The stable, scriptable endpoint is
the PREZIP archive bucket, which serves one zip per month:

    https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{YYYY}_{M}.zip

Usage:
    python scripts/download_dataset.py --year 2025 --months 1 2 3
    python scripts/download_dataset.py --year 2025 --months 1-12
    python scripts/download_dataset.py --list-available 2025

Files land in data/raw/bts/year=YYYY/ and are never modified afterwards.
Downloads are resumable-safe: an existing non-empty file is skipped unless
--force is passed.
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)
REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = REPO_ROOT / "data" / "raw" / "bts"


def archive_url(year: int, month: int) -> str:
    return BASE_URL.format(year=year, month=month)


def target_path(year: int, month: int) -> Path:
    return RAW_ROOT / f"year={year}" / f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"


def month_range(spec: str) -> list[int]:
    """Accept '3' or '1-12' or a comma separated list."""
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
    invalid = [m for m in months if not 1 <= m <= 12]
    if invalid:
        raise SystemExit(f"Invalid month(s): {invalid}")
    return months


def download(year: int, month: int, force: bool = False) -> Path:
    dest = target_path(year, month)
    if dest.exists() and dest.stat().st_size > 0 and not force:
        print(f"[skip] {dest.name} already present ({dest.stat().st_size} bytes)")
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    url = archive_url(year, month)
    tmp = dest.with_suffix(".zip.part")
    print(f"[get ] {url}")
    request = Request(url, headers={"User-Agent": "airline-delay-course-project/1.0"})
    try:
        with urlopen(request, timeout=120) as response, open(tmp, "wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            read = 0
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                handle.write(chunk)
                read += len(chunk)
            size_mb = read / (1024 * 1024)
            expected_mb = total / (1024 * 1024)
            print(f"[ok  ] {dest.name}: {size_mb:.1f} MB (expected {expected_mb:.1f} MB)")
    except (HTTPError, URLError) as exc:
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"[fail] {year}-{month:02d}: {exc}") from exc

    if not zipfile.is_zipfile(tmp):
        tmp.unlink(missing_ok=True)
        raise SystemExit(f"[fail] {dest.name}: download is not a valid zip archive")
    tmp.replace(dest)
    return dest


def list_available(year: int) -> None:
    for month in range(1, 13):
        try:
            request = Request(archive_url(year, month), method="HEAD")
            with urlopen(request, timeout=30) as response:
                size = int(response.headers.get("Content-Length") or 0)
            print(f"{year}-{month:02d}: available ({size / (1024 * 1024):.1f} MB)")
        except (HTTPError, URLError) as exc:
            print(f"{year}-{month:02d}: unavailable ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--months", default="1", help="e.g. '1', '1-12', '1,6,12'")
    parser.add_argument("--force", action="store_true", help="re-download existing archives")
    parser.add_argument("--list-available", action="store_true")
    args = parser.parse_args()

    if args.list_available:
        list_available(args.year)
        return

    for month in month_range(args.months):
        download(args.year, month, force=args.force)


if __name__ == "__main__":
    main()
