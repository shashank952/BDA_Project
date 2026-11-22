#!/usr/bin/env python
"""MapReduce Job 4 - mapper: route-level delay analysis.

Composite key origin-destination; arrival delay is the ranking metric because
that is the passenger-visible outcome of a route.
"""

import csv
import sys

DELAY_THRESHOLD_MINUTES = 15.0
IDX_ORIGIN = 6
IDX_DEST = 9
IDX_ARR_DELAY = 20
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
        origin = row[IDX_ORIGIN].strip()
        dest = row[IDX_DEST].strip()
        if not origin or not dest:
            continue

        arr = to_float(row[IDX_ARR_DELAY])
        arr_sum = arr if arr is not None else 0.0
        arr_count = 1 if arr is not None else 0
        arr_delayed = 1 if (arr is not None and arr >= DELAY_THRESHOLD_MINUTES) else 0

        sys.stdout.write("%s-%s\t%.2f,%d,%d,1\n" % (origin, dest, arr_sum, arr_count, arr_delayed))


if __name__ == "__main__":
    main()
