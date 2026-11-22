#!/usr/bin/env python
"""MapReduce Job 1 - mapper: airline delay summary.

Input : cleaned CSV rows (header skipped by validation)
Output: key = airline code, value = 8 additive counters
        dep_sum,dep_count,dep_delayed,arr_sum,arr_count,arr_delayed,cancelled,total

Records without a valid measurement for a metric contribute 0 minutes and
0 to that metric's count, so the reducer's denominator stays "valid
measurements only". Self-contained by design: it runs as a streaming task with
no access to the project's Python packages.
"""

import csv
import sys

DELAY_THRESHOLD_MINUTES = 15.0
IDX_AIRLINE = 4
IDX_DEP_DELAY = 16
IDX_ARR_DELAY = 20
IDX_CANCELLED = 25
MIN_COLUMNS = 34


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith("flight_date"):
            continue
        row = next(csv.reader([line]))
        if len(row) < MIN_COLUMNS:
            continue
        airline = row[IDX_AIRLINE].strip()
        if not airline:
            continue

        dep = to_float(row[IDX_DEP_DELAY])
        arr = to_float(row[IDX_ARR_DELAY])
        cancelled = 1 if to_float(row[IDX_CANCELLED]) == 1 else 0

        dep_sum = dep if dep is not None else 0.0
        dep_count = 1 if dep is not None else 0
        dep_delayed = 1 if (dep is not None and dep >= DELAY_THRESHOLD_MINUTES) else 0
        arr_sum = arr if arr is not None else 0.0
        arr_count = 1 if arr is not None else 0
        arr_delayed = 1 if (arr is not None and arr >= DELAY_THRESHOLD_MINUTES) else 0

        sys.stdout.write(
            "%s\t%.2f,%d,%d,%.2f,%d,%d,%d,1\n"
            % (airline, dep_sum, dep_count, dep_delayed, arr_sum, arr_count, arr_delayed, cancelled)
        )


if __name__ == "__main__":
    main()
