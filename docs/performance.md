# Performance evaluation

All numbers below were measured on this machine, not estimated. Nothing here implies cluster
scalability: the deployment is one node.

## Environment

| Item | Value |
| --- | --- |
| CPU | AMD Ryzen 7 4800H, 8 cores / 16 threads |
| RAM | 15.4 GB |
| OS | Windows 11 (10.0.26200) |
| Hadoop | 3.2.4, pseudo-distributed NameNode + DataNode on `localhost:9000` |
| MapReduce | LocalJobRunner (see `docs/limitations.md` for why YARN containers are disabled) |
| Hive | 3.1.3, embedded Derby, MapReduce engine |
| Python | 3.12.10 |

## Dataset sizes

| Stage | Files | Size | Records |
| --- | --- | --- | --- |
| Raw archives (zip) | 12 | 339.0 MB | - |
| Cleaned CSV | 12 | 1,063.7 MB | 7,001,619 |
| HDFS `/airline-delay/processed` | 12 | 1.0 GB (replication 1) | 7,001,619 |
| Hive Parquet `flights` | 12 partitions | - | 7,001,619 |

Cleaning expands the data ~3.1x because the raw archive is compressed and only 24 of 110
columns are kept; the cleaned file is wider per row than the compressed input per row.

## Stage timings

### Cleaning (pandas, one partition at a time)

| Month | Rows | Seconds |
| --- | --- | --- |
| 2025-01 | 539,747 | 25.38 |
| 2025-02 | 504,884 | 23.81 |
| 2025-03 | 600,872 | 28.25 |
| 2025-04 | 583,950 | 27.33 |
| 2025-05 | 605,648 | 28.65 |
| 2025-06 | 611,575 | 29.37 |
| 2025-07 | 631,428 | 30.19 |
| 2025-08 | 602,378 | 28.66 |
| 2025-09 | 562,439 | 26.51 |
| 2025-10 | 605,844 | 28.32 |
| 2025-11 | 570,550 | 27.17 |
| 2025-12 | 582,304 | 27.43 |
| **Total** | **7,001,619** | **331.07 s** |

Throughput: ~21,100 rows/second end-to-end (read zip, validate, derive, dedupe, write CSV and
quality report). The January run alone was 24.7 s, so per-partition cost is essentially linear
with a fixed JVM-free overhead of ~2 s.

### HDFS upload

| Item | Bytes | Seconds | Throughput |
| --- | --- | --- | --- |
| One cleaned month (2025-12) | 93,658,273 | 14.2 | ~6.6 MB/s |

Extrapolated full upload: ~161 s for 1.0 GB (not separately measured; labelled as an
extrapolation). Every upload is byte-verified against the local file.

### MapReduce (4 streaming jobs, 12 partitions, 1.0 GB input)

| Job | Output rows | Seconds |
| --- | --- | --- |
| airline_performance | 14 | 71.96 |
| airport_performance | 704 | 86.93 |
| monthly_trends | 12 | 63.82 |
| route_performance | 6,938 | 65.85 |
| **Total** | 7,668 | **288.56 s** |

Same jobs on one month (2025-01, 85.4 MB): 8.43 + 10.43 + 8.38 + 8.46 = **35.7 s**.
So 12x the data took 8.1x the MapReduce wall time: fixed JVM/job setup dominates for small
inputs, and the combiner keeps shuffle volume flat. This is a single-node observation and is
not evidence of distributed scaling.

### Hive

| Stage | Seconds |
| --- | --- |
| `01_create_database.hql` | 20.02 |
| `02_create_tables.hql` (external table + Parquet load of 7,001,619 rows) | 159.66 |
| airline_performance | 22.63 |
| airport_performance | 25.66 |
| monthly_trends | 20.61 |
| route_performance | 22.60 |
| delay_causes | 50.42 |
| cancellations | 20.22 |
| cancellation_airports | 21.47 |
| delay_categories | 40.43 |
| day_of_week | 20.38 |
| summary | 19.88 |
| **All ten queries** | **264.30 s** |

Each number includes a fresh JVM plus Hive session (~15-18 s of it), which is the honest cost
of driving Hive through the CLI per query: it makes per-query attribution possible at the price
of repeated startup. The two slower queries (`delay_causes` 50.4 s, `delay_categories` 40.4 s)
use `UNION ALL` / `CROSS JOIN` and first log a failed local-mode attempt before retrying as a
MapReduce job.

### End-to-end

| Phase | Seconds |
| --- | --- |
| Cleaning | 331.1 |
| HDFS upload (extrapolated) | ~161 |
| MapReduce | 288.6 |
| Hive (setup + queries) | 424.0 |
| **Total pipeline** | **~1,205 s (~20 min)** |

API and dashboard startup are excluded: the API serves the exported CSVs and has no Hadoop
dependency, so a page interaction costs milliseconds rather than a cluster job.

## Scale experiments

| Experiment | Dataset | Performed | Outcome |
| --- | --- | --- | --- |
| 1 - correctness | 15-row fixture + 1 month | yes | 73 tests pass; all layers agree |
| 2 - functional | 2025-01 (539,747 rows) | yes | MapReduce 35.7 s, Hive queries 208 s |
| 3 - mid-scale | 2025-01..06 (3.4M rows) | not run separately | available via `--months 1-6` |
| 4 - full year | 2025-01..12 (7,001,619 rows) | yes | MapReduce 288.6 s, Hive 264.3 s |

Experiment 3 was skipped rather than estimated: the pipeline is linear between the measured
one-month and twelve-month points, and reporting an interpolated number as a measurement would
be exactly the kind of fabricated benchmark this project avoids.

## What the numbers do and do not show

- They show the pipeline processes 7M records on one machine in about 20 minutes with full
  validation, and that MapReduce/Hive outputs agree with an independent implementation.
- They do **not** show speedup from parallelism. On a single node with LocalJobRunner there is
  no inter-node shuffle, no container scheduling and no replication overhead to measure.
- Peak memory was not instrumented. The observed footprint is dominated by one cleaning process
  holding a single month (~600k rows) and a 1 GB JVM heap for Hive; the machine had 3.3 GB free
  of 15.4 GB while idle after a full run.
