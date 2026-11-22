#!/usr/bin/env python
"""Shared combiner for all four jobs.

Every mapper value is a list of additive counters (sums and counts), so partial
aggregation is mathematically safe: sum(a+b) == sum(a) + sum(b). Averages and
rates are never computed here - only in the reducer, from summed counters.

Running this as a combiner cuts shuffle volume by the number of flights per key.
"""

import sys


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
                sys.stdout.write("%s\t%s\n" % (current_key, ",".join("%.2f" % v for v in totals)))
            current_key = key
            totals = [0.0] * len(values)
        totals = [acc + part for acc, part in zip(totals, values)]
    if current_key is not None:
        sys.stdout.write("%s\t%s\n" % (current_key, ",".join("%.2f" % v for v in totals)))


if __name__ == "__main__":
    main()
