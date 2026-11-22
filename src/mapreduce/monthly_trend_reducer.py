#!/usr/bin/env python
"""MapReduce Job 3 - reducer: monthly delay trend.

Emits: flight_year,flight_month,total_flights,valid_arrival_flights,
avg_arrival_delay,delayed_arrivals,arrival_delay_rate,cancellations,
cancellation_rate
"""

import sys


def fmt(value, decimals=4):
    return "" if value is None else ("%%.%df" % decimals) % value


def rate(numerator, denominator):
    if not denominator:
        return None
    return 100.0 * numerator / denominator


def emit(key, totals):
    arr_sum, arr_count, arr_delayed, total, cancelled = totals
    year, _, month = key.partition("-")
    avg = arr_sum / arr_count if arr_count else None
    sys.stdout.write(
        ",".join(
            [
                year,
                str(int(month)),
                str(int(total)),
                str(int(arr_count)),
                fmt(avg),
                str(int(arr_delayed)),
                fmt(rate(arr_delayed, arr_count)),
                str(int(cancelled)),
                fmt(rate(cancelled, total)),
            ]
        )
        + "\n"
    )


def main():
    current_key = None
    totals = None
    for line in sys.stdin:
        if not line.strip():
            continue
        key, _, value = line.rstrip("\n").partition("\t")
        values = [float(part) for part in value.split(",")]
        if key != current_key:
            if current_key is not None:
                emit(current_key, totals)
            current_key = key
            totals = [0.0] * len(values)
        totals = [acc + part for acc, part in zip(totals, values)]
    if current_key is not None:
        emit(current_key, totals)


if __name__ == "__main__":
    main()
