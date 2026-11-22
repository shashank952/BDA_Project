# Testing

```
python -m pytest tests -q
73 passed in 42.37s
```

The suite is layered so that a failure points at one stage: contracts first, numbers second,
execution third, cross-layer agreement last.

## Inventory

| File | Tests | What it proves |
| --- | --- | --- |
| `tests/test_schema.py` | 6 | Every cleaned column has a documented definition; required columns are enforced; a missing required column fails fast with its name; absent optional cause columns degrade gracefully instead of crashing; an empty file is rejected; every dedupe key column exists |
| `tests/test_cleaning.py` | 13 | Row accounting on a fixture with known defects; quarantine reasons; canonical column order; negative delays preserved; zero delay recognised as a valid measurement; cancelled flights keep a null arrival delay; diverted flights keep departure but no arrival; all six category boundaries; vectorized and scalar categorisation agree; derived date parts; determinism (same input, identical output); dedupe uniqueness; delay minutes floored at zero |
| `tests/test_metrics.py` | 10 | Every aggregate against hand-calculated values from the fixture, including denominators, cancellation rate, cause minutes and shares |
| `tests/test_mapreduce.py` | 9 | Mappers/reducers run as real subprocesses; shuffle emulated by key sort; header and malformed rows skipped; combiner is associative for all four jobs |
| `tests/test_api.py` | 18 | 13 endpoints; filters, sorting, pagination envelopes; parameter validation (400); unknown endpoint (404); missing outputs (503); error payloads never echo input or paths |
| `tests/test_numerical_consistency.py` | 5 | MapReduce vs Hive per key; Hive vs reference; API vs Hive; API summary vs Hive summary; delay-cause shares sum to 100 % |

## Hand-calculated expectations

`tests/fixtures/sample_flights.csv` contains 15 rows: 11 valid flights, 1 exact duplicate,
1 invalid date, 1 negative distance, 1 invalid cancellation flag. The numbers below are what
the tests assert, and they were computed by hand before the code was written.

| Quantity | Calculation | Expected |
| --- | --- | --- |
| Records read / cleaned / quarantined / duplicates | 15 / 11 / 3 / 1 | 15 / 11 / 3 / 1 |
| Valid departure measurements | 10 flights, delays sum 227 | avg 22.70 min |
| Valid arrival measurements | 9 flights, delays sum 219 | avg 24.3333 min |
| Arrival delays >= 15 min | 6 of 9 | 66.6667 % |
| Departure delays >= 15 min | 6 of 10 | 60.0 % |
| Cancellations | 1 of 11 | 9.0909 % |
| January arrival average | 211 / 8 valid | 26.375 min |
| Category counts | on_time 3, minor 3, moderate 2, severe 1, unknown 2 | total 11 |
| Recorded cause minutes | carrier 40, weather 10, NAS 5, security 0, late 5 | total 60 |

## Category boundary cases

`tests/test_cleaning.py::test_delay_category_boundaries` locks 14 -> `on_time`, 15 -> `minor`,
29 -> `minor`, 30 -> `moderate`, 59 -> `moderate`, 60 -> `severe`, plus `None` -> `unknown`.
A single-line change to the thresholds breaks exactly these assertions.

## Cross-layer consistency

`tests/test_numerical_consistency.py` compares real artefacts, not synthetic frames:

1. MapReduce exports (`outputs/analytics/mapreduce/*.csv`) against Hive exports
   (`outputs/analytics/*.csv`) on the analysis key, tolerance 0.01.
2. Hive exports against the pandas reference implementation (`src/common/metrics.py`).
3. The Flask API (in-process test client) against the Hive exports.
4. The API summary against the Hive summary row.
5. Delay-cause shares summing to 100 %.

These tests skip when the artefacts are absent, so a fresh checkout still runs; after a full
pipeline run they execute and pass.

## Validation performed during the build

| Check | Command | Result |
| --- | --- | --- |
| Cleaning determinism | run `clean_data` twice for 2025-01 | identical output |
| Cleaning scale | `--months 1-12` | 7,001,619 rows, 0 quarantined, 0 duplicates |
| HDFS upload integrity | `scripts/hdfs_ops.py verify --year 2025 --month 1` | local 85,396,092 bytes = HDFS 85,396,092 bytes |
| MapReduce correctness | `run_jobs --validate` | output matches reference for all four jobs |
| Hive correctness | `run_queries --all --validate` | output matches reference for all ten analyses |
| Dashboard rendering | `streamlit.testing.v1.AppTest` over all five pages | 0 exceptions, 0 error elements, KPI values populated |
| API liveness | `GET /api/health` | `status=ok`, 10 analysis tables available |

## Not covered

- No multi-node cluster test: the environment is a single node (see `docs/limitations.md`).
- No browser automation of the dashboard: page rendering is verified through Streamlit's
  `AppTest` harness, which executes each page's real code against the live API, but it does not
  simulate mouse-level interaction.
- No long-running soak test or concurrent-user load test.
