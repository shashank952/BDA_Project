#!/usr/bin/env python
"""MapReduce Job 2 - mapper: airport delay analysis.

Each flight emits two records so that the departure role (origin airport) and
the arrival role (destination airport) are never conflated:

    D:<airport>  -> dep_sum,dep_count,dep_delayed,total
    A:<airport>  -> arr_sum,arr_count,arr_delayed,total
"""

import csv
import sys

DELAY_THRESHOLD_MINUTES = 15.0
IDX_ORIGIN = 6
IDX_DEST = 9
IDX_DEP_DELAY = 16
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
        dep = to_float(row[IDX_DEP_DELAY])
        arr = to_float(row[IDX_ARR_DELAY])

        if origin:
            dep_sum = dep if dep is not None else 0.0
            dep_count = 1 if dep is not None else 0
            dep_delayed = 1 if (dep is not None and dep >= DELAY_THRESHOLD_MINUTES) else 0
            sys.stdout.write("D:%s\t%.2f,%d,%d,1\n" % (origin, dep_sum, dep_count, dep_delayed))

        if dest:
            arr_sum = arr if arr is not None else 0.0
            arr_count = 1 if arr is not None else 0
            arr_delayed = 1 if (arr is not None and arr >= DELAY_THRESHOLD_MINUTES) else 0
            sys.stdout.write("A:%s\t%.2f,%d,%d,1\n" % (dest, arr_sum, arr_count, arr_delayed))


if __name__ == "__main__":
    main()
