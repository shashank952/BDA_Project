# Architecture

## Components

| Layer | Location | Responsibility |
| --- | --- | --- |
| Configuration | `config/` | Single source of truth for paths, thresholds, schema mapping, Hive settings |
| Ingestion | `scripts/download_dataset.py`, `src/ingestion/inspect_data.py` | Fetch monthly BTS archives, inspect the real schema before coding |
| Preprocessing | `src/preprocessing/` | Validation, type normalization, derived columns, dedupe, quarantine, quality report |
| Storage | HDFS via `src/common/hadoop_cli.py` | Raw (immutable), processed, quarantine, analytics, reports |
| Distributed aggregation | `src/mapreduce/` | Four Hadoop Streaming jobs with a shared additive combiner |
| SQL analytics | `src/hive/` | External CSV table, Parquet table, ten analytical queries |
| API | `src/backend/` | Read-only JSON over prepared outputs, validated filters, pagination |
| Dashboard | `src/dashboard/` | Five Streamlit pages over the API, Plotly charts, CSV export |
| Verification | `tests/`, `src/common/validate.py` | Contract tests, hand-calculated expectations, cross-layer consistency |

## Data flow

1. `scripts/download_dataset.py` stores the untouched monthly archive under
   `data/raw/bts/year=YYYY/`. Archives are skipped when already present, never rewritten.
2. `src/preprocessing/clean_data.py` reads one partition at a time (zip or CSV),
   selects only the 24 mapped columns of the 110-column source, and produces:
   - `data/processed/year=YYYY/month=MM/flights.csv` (LF line endings, header included)
   - `data/quarantine/year=YYYY/month=MM/rejected.csv` (row id, reasons, key values)
   - `outputs/reports/data_quality/year=YYYY/month=MM.json` plus `summary.json`
3. `scripts/hdfs_ops.py` creates `/airline-delay/...`, uploads the raw archives (refuses to
   overwrite without `--force`) and the cleaned partitions, and verifies remote byte counts.
4. `src/mapreduce/run_jobs.py` runs four streaming jobs and writes
   `/airline-delay/analytics/<job>/mr`, then exports to `outputs/analytics/mapreduce/`.
5. `src/hive/run_queries.py` runs the DDL and ten analyses, writes
   `/airline-delay/analytics/<name>/hive`, and exports to `outputs/analytics/`.
6. `src/backend/app.py` serves those CSVs; `src/dashboard/app.py` renders them.

The raw directory is read-only for the pipeline: nothing in the cleaning, MapReduce or Hive
stages writes to `/airline-delay/raw`.

## HDFS layout (as built)

```
/airline-delay/
├── raw/source=bts/year=2025/month=01..12/<original zip>        339.0 MB, 12 files
├── staging/validated/                                          reserved
├── processed/year=2025/month=01..12/flights.csv                1.0 GB, 7,001,619 rows
├── quarantine/year=2025/month=01..12/rejected.csv              header only (0 rejects)
├── analytics/
│   ├── airline_performance/mr|hive/
│   ├── airport_performance/mr|hive/
│   ├── route_performance/mr|hive/
│   ├── monthly_trends/mr|hive/
│   ├── delay_causes/hive/
│   ├── delay_categories/hive/
│   ├── cancellation_analysis/hive/         (cancellations, cancellation_airports)
│   ├── day_of_week/hive/
│   ├── summary/hive/
│   └── ...
├── hive/warehouse/airline_analytics/       Parquet table `flights`
└── reports/data_quality/year=2025/month=01..12/quality.json
```

## Canonical cleaned schema

The cleaned CSV has exactly 34 columns in the order declared by
`config/schema_mapping.yaml -> cleaned_column_order`, mirrored one-to-one by the Hive DDL:

```
flight_date, flight_year, flight_month, day_of_week, airline_code, flight_number,
origin_airport, origin_city, origin_state, destination_airport, destination_city,
destination_state, route, scheduled_departure, actual_departure, dep_hour,
departure_delay, departure_delay_minutes, scheduled_arrival, actual_arrival,
arrival_delay, arrival_delay_minutes, is_departure_delayed, is_arrival_delayed,
delay_category, cancelled, diverted, cancellation_code, distance,
carrier_delay, weather_delay, nas_delay, security_delay, late_aircraft_delay
```

`tests/test_schema.py::test_mapping_defines_every_cleaned_column` asserts that every column
in this list has a documented definition, so the mapping cannot drift from the data.

## Hive table design

Two tables, deliberately separated:

1. `flights_raw_csv` - external, `OpenCSVSerde`, all columns `STRING`, partitioned by
   `year`/`month`, `skip.header.line.count=1`, located at `/airline-delay/processed`.
   A CSV serde is required because city names contain commas (`"New York, NY"`).
2. `flights` - internal Parquet table, partitioned by `year`/`month`, populated by one
   `INSERT OVERWRITE ... PARTITION (year, month)` that casts every column and turns empty
   strings into real `NULL` with `NULLIF(...,'')`.

Typing happens in the INSERT rather than in the external table so that an empty string can
never be silently read as zero - the subtle failure mode this dataset invites.

## Execution contracts

`src/common/validate.py` holds the output contract for every analysis: key columns, value
columns and the reference function that must reproduce them. Both the MapReduce and Hive
runners call it, so a change in one layer cannot silently diverge from the others.

## Failure handling

| Failure | Behaviour |
| --- | --- |
| Source file missing | `SchemaValidationError` naming the expected directory |
| Required column missing | Fail fast listing every missing column |
| Invalid rows | Quarantine file + per-reason counts in the quality report |
| HDFS unreachable | `HadoopUnavailableError` with the start command |
| MapReduce job fails | Non-zero exit or no part file raises; the export is never written |
| Hive statement fails | Exit code plus result-directory verification |
| Analysis output missing | API returns `503` naming the generating command |
| Dashboard/API down | Dashboard shows a retry path instead of a traceback |
| Repeated runs | Job output directories are deleted first; uploads verify byte sizes |

## Deliberate environment decisions

- **Wrapper-free Hadoop invocation.** `hdfs.cmd` and `hadoop.cmd` on this machine returned
  exit code 0 for failed commands and truncated arguments at `=`. Every call goes directly
  to `java -cp <hadoop classpath> <main class>` (`src/common/hadoop_cli.py`).
- **LocalJobRunner instead of YARN.** YARN container localization needs
  `SeCreateSymbolicLinkPrivilege`, which requires Administrator or Developer Mode on
  Windows. The four jobs therefore run through Hadoop's LocalJobRunner: real
  `Job`/`Mapper`/`Reducer`/shuffle machinery, single JVM. `AIRLINE_MR_FRAMEWORK=yarn`
  switches back on a cluster that has the privilege.
- **Streaming commands are unquoted.** Hadoop's Windows Streaming argument parser inserts an
  empty `argv` entry when the executable is quoted, which exits with code 2.
- **`mapreduce.output.textoutputformat.separator=` is set to empty.** Without it Streaming
  appends a trailing tab to every reducer line, which corrupts the last CSV field.
- **Hive local-auto mode is disabled.** `hive.exec.mode.local.auto` makes Hive spawn the
  Linux `hadoop` shell script, which cannot run on Windows; the same setting also caused a
  failed local attempt that Hive then retried successfully, so the runner treats Hive as
  successful only when the result directory exists.
