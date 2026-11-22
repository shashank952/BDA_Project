#!/usr/bin/env python
"""MapReduce Job 3 - mapper: monthly delay trend.

Key is the zero-padded year-month ("2025-01") so that lexicographic key order
equals chronological order, which lets a single reducer emit months in order.
"""

import csv
import sys

DELAY_THRESHOLD_MINUTES = 15.0
IDX_FLIGHT_DATE = 0
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
        flight_date = row[IDX_FLIGHT_DATE].strip()
        if len(flight_date) < 7:
            continue
        month_key = flight_date[:7]

        arr = to_float(row[IDX_ARR_DELAY])
        cancelled = 1 if to_float(row[IDX_CANCELLED]) == 1 else 0
        arr_sum = arr if arr is not None else 0.0
        arr_count = 1 if arr is not None else 0
        arr_delayed = 1 if (arr is not None and arr >= DELAY_THRESHOLD_MINUTES) else 0

        sys.stdout.write("%s\t%.2f,%d,%d,1,%d\n" % (month_key, arr_sum, arr_count, arr_delayed, cancelled))


if __name__ == "__main__":
    main()
