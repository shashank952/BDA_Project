#!/usr/bin/env python
"""MapReduce Job 1 - reducer: airline delay summary.

Emits one CSV row per airline:
airline_code,total_flights,valid_departure_flights,avg_departure_delay,
departure_delayed_flights,departure_delay_rate,valid_arrival_flights,
avg_arrival_delay,delayed_arrivals,arrival_delay_rate,cancellations,
cancellation_rate

Departure and arrival metrics are kept in separate columns: no average ever
mixes the two definitions.
"""

import sys


def fmt(value, decimals=4):
    return "" if value is None else ("%%.%df" % decimals) % value


def rate(numerator, denominator):
    if not denominator:
        return None
    return 100.0 * numerator / denominator


def emit(airline, totals):
    dep_sum, dep_count, dep_delayed, arr_sum, arr_count, arr_delayed, cancelled, total = totals
    avg_dep = dep_sum / dep_count if dep_count else None
    avg_arr = arr_sum / arr_count if arr_count else None
    sys.stdout.write(
        ",".join(
            [
                airline,
                str(int(total)),
                str(int(dep_count)),
                fmt(avg_dep),
                str(int(dep_delayed)),
                fmt(rate(dep_delayed, dep_count)),
                str(int(arr_count)),
                fmt(avg_arr),
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
        totals = [acc + value_part for acc, value_part in zip(totals, values)]
    if current_key is not None:
        emit(current_key, totals)


if __name__ == "__main__":
    main()
