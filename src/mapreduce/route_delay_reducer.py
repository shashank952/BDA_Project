#!/usr/bin/env python
"""MapReduce Job 4 - reducer: route-level delay analysis.

Emits: route,origin_airport,destination_airport,total_flights,
valid_arrival_flights,avg_arrival_delay,delayed_arrivals,arrival_delay_rate

All routes are emitted; the minimum-flight-count filter for rankings is applied
at export time (config: analytics.min_route_flights) so the raw aggregate stays
complete and reusable.
"""

import sys


def fmt(value, decimals=4):
    return "" if value is None else ("%%.%df" % decimals) % value


def rate(numerator, denominator):
    if not denominator:
        return None
    return 100.0 * numerator / denominator


def emit(key, totals):
    origin, _, dest = key.partition("-")
    arr_sum, arr_count, arr_delayed, total = totals
    avg = arr_sum / arr_count if arr_count else None
    sys.stdout.write(
        ",".join(
            [
                key,
                origin,
                dest,
                str(int(total)),
                str(int(arr_count)),
                fmt(avg),
                str(int(arr_delayed)),
                fmt(rate(arr_delayed, arr_count)),
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
