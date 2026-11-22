#!/usr/bin/env python
"""MapReduce Job 2 - reducer: airport delay analysis.

Emits: role,airport_code,total_flights,valid_delay_flights,avg_delay,
delayed_flights,delay_rate
"""

import sys


def fmt(value, decimals=4):
    return "" if value is None else ("%%.%df" % decimals) % value


def rate(numerator, denominator):
    if not denominator:
        return None
    return 100.0 * numerator / denominator


def emit(key, totals):
    role_code, _, airport = key.partition(":")
    role = "departure" if role_code == "D" else "arrival"
    delay_sum, valid_count, delayed, total = totals
    avg = delay_sum / valid_count if valid_count else None
    sys.stdout.write(
        ",".join(
            [
                role,
                airport,
                str(int(total)),
                str(int(valid_count)),
                fmt(avg),
                str(int(delayed)),
                fmt(rate(delayed, valid_count)),
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
