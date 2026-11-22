# Airline Flight Delay Analysis and Performance Monitoring Using Apache Hadoop

Historical big-data analytics over the U.S. Bureau of Transportation Statistics (BTS)
On-Time Performance dataset: 7,001,619 flight records for 2025, stored in HDFS,
aggregated by four Hadoop MapReduce jobs and by Apache Hive SQL, served through a
Flask API and explored in a 5-page Streamlit dashboard.

This is a **historical analysis system**. It does not track live flights and it does not
claim to predict delays or prove causal relationships. Delay-cause figures are the
recorded attribution reported by carriers, not causal inference.

---

## Results at a glance (2025, all 12 months)

| Metric | Value |
| --- | --- |
| Flight records analysed | 7,001,619 |
| Airlines / airports / routes | 14 / 352 / 6,938 |
| Average arrival delay | 8.50 min |
| Average departure delay | 13.56 min |
| Arrival-delay rate (>= 15 min) | 22.31 % of 6,879,484 valid measurements |
| Departure-delay rate (>= 15 min) | 21.76 % of 6,903,028 valid measurements |
| Cancelled / diverted flights | 102,876 (1.47 %) / 19,258 |
| Busiest delay month | July 2025 (avg 17.35 min, 28.89 % delay rate) |
| Calmest delay month | September 2025 (avg 2.32 min, 16.63 % delay rate) |
| Highest airline delay rate | Frontier (F9) 27.91 %, PSA (OH) 27.53 %, JetBlue (B6) 26.15 % |
| Recorded delay-minute mix | Late aircraft 39.19 %, carrier 32.45 %, NAS 21.87 %, weather 6.35 %, security 0.14 % |
| Delay categories | on time 76.34 %, minor 7.32 %, moderate 6.56 %, severe 8.03 %, unknown 1.74 % |

All figures above are produced by the pipeline in this repository and cross-checked
between MapReduce, Hive, the pandas reference implementation and the API
(`tests/test_numerical_consistency.py`).

---

## Architecture

```
BTS On-Time Performance (12 monthly zips, 339.0 MB)
        |
        v
Ingestion + validation      scripts/download_dataset.py, src/ingestion
  schema check, row counts, quality report
        |
        v
HDFS  /airline-delay/raw     preserved originals (never overwritten)
        |
        v
Cleaning + derivation       src/preprocessing  (7,001,619 rows, 1.06 GB CSV, 0 rejected)
        |
        v
HDFS  /airline-delay/processed/year=YYYY/month=MM/flights.csv
        |
        +--> Hadoop MapReduce (4 streaming jobs)      -> /airline-delay/analytics/<job>/mr
        |
        +--> Apache Hive (external CSV + Parquet, 10 analyses) -> /airline-delay/analytics/<name>/hive
        |
        v
outputs/analytics/*.csv  (Hive, authoritative)  +  outputs/analytics/mapreduce/*.csv
        |
        v
Flask API (13 endpoints, filters, pagination)  ->  Streamlit dashboard (5 pages, Plotly)
```

The dashboard and API never run Hadoop: they read the prepared result tables, so a page
interaction cannot trigger a cluster job.

---

## Technology stack (verified versions on this machine)

| Component | Version |
| --- | --- |
| Python | 3.12.10 (pandas 3.0.5, plotly 7.1.0, streamlit 1.66.1, Flask 3.1.3) |
| Hadoop / HDFS | Apache Hadoop 3.2.4 (pseudo-distributed: NameNode + DataNode) |
| Hadoop MapReduce | 3.2.4, Hadoop Streaming with Python mappers/reducers |
| Apache Hive | 3.1.3 (embedded Derby metastore, CLI driven) |
| Java | OpenJDK 8u504 (Temurin) for Hadoop/Hive |
| OS / hardware | Windows 11, AMD Ryzen 7 4800H (8C/16T), 15.4 GB RAM |
| Testing | pytest 9.1.1 |

---

## Repository layout

```
config/          settings.yaml, schema_mapping.yaml, airlines.csv, hive/hive-site.xml
data/            raw zips, cleaned partitions, quarantine (git-ignored)
scripts/         download_dataset.py, hdfs_ops.py, export_results.py, *.sh wrappers
src/common/      config, canonical spec, reference metrics, output validation, Hadoop CLI
src/ingestion/   schema inspection helpers
src/preprocessing/  cleaning, derived features, quality report
src/mapreduce/   4 mappers, 4 reducers, shared combiner, job runner
src/hive/        01..12 .hql files and the CliDriver runner
src/backend/     Flask app, routes, data-access services
src/dashboard/   Streamlit app, API client, theme, 5 page views
tests/           schema, cleaning, metrics, MapReduce, API, cross-layer consistency
docs/            architecture, data dictionary, metrics, setup, testing, performance, limitations
outputs/         exported analytics CSVs and execution metrics (git-ignored)
```

---

## Quick start (Windows, single node)

Prerequisites: JDK 8 (Hadoop 3.2.4 does not run on JDK 17+), Hadoop 3.2.4 with
`winutils.exe`, Python 3.12, and a local Hive 3.1.3 extraction. See
[`docs/setup_guide.md`](docs/setup_guide.md) for the full install and troubleshooting.

```powershell
# 1. dependencies
python -m pip install -r requirements.txt

# 2. start HDFS (first time only: hdfs namenode -format)
& "$env:HADOOP_HOME\sbin\start-dfs.cmd"

# 3. download the dataset (12 months of 2025, ~339 MB)
python scripts/download_dataset.py --year 2025 --months 1-12

# 4. clean + derive (writes data/processed, data/quarantine, quality reports)
python -m src.preprocessing.clean_data --year 2025 --months 1-12

# 5. HDFS layout, raw archives, cleaned partitions
python scripts/hdfs_ops.py init
python scripts/hdfs_ops.py upload-raw --year 2025
python scripts/hdfs_ops.py upload-processed --year 2025 --months 1-12

# 6. Hadoop MapReduce jobs (+ numeric validation against the reference implementation)
python -m src.mapreduce.run_jobs --year 2025 --months 1-12 --validate

# 7. Hive: database, tables, Parquet load, all analyses (+ validation)
python -m src.hive.run_queries --all --validate

# 8. API and dashboard
python -m src.backend.app                 # http://127.0.0.1:5050
streamlit run src/dashboard/app.py        # http://localhost:8501
```

Without Hadoop, a demo-only path is available:
`python scripts/export_results.py --method reference` computes the same tables in pandas.

---

## API endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /api/health` | Liveness plus the list of available analysis tables |
| `GET /api/summary` | Overall KPIs, averages, rates, dataset period |
| `GET /api/airlines` | Airline performance (`airline`, `sort`, `order`, `limit`, `offset`) |
| `GET /api/airports` | Airport performance (`role=departure|arrival`, `airport`, `min_flights`) |
| `GET /api/routes` | Route performance (`origin`, `destination`, `min_flights`) |
| `GET /api/trends/monthly` | Monthly trend (`year_from`, `year_to`) |
| `GET /api/trends/day-of-week` | Day-of-week comparison |
| `GET /api/delay-causes` | Recorded delay-minute attribution |
| `GET /api/delay-categories` | On-time / minor / moderate / severe / unknown counts |
| `GET /api/cancellations` | Cancellations by airline and month |
| `GET /api/cancellations/airports` | Cancellations by origin airport with reason codes |
| `GET /api/metadata` | Dataset period, record counts, processing status |

Every list response returns `data`, `pagination`, `filters` and `generated_at`. Invalid
parameters return `400` with a message; a missing analysis returns `503` with the command
that generates it. Stack traces and filesystem paths are never returned.

## Dashboard pages

1. **Overview** - five KPI cards, monthly delay and delay-rate chart, top delayed airlines.
2. **Airline performance** - airline filter, sort control, delay bar chart, volume/rate
   scatter, ranking table with CSV export.
3. **Airport and routes** - departure/arrival role switch, top-N airport chart, route
   table with minimum-flight filter and CSV export.
4. **Time analysis** - monthly trend with cancellation overlay, day-of-week chart,
   delay-category breakdown.
5. **Delay causes and cancellations** - attribution chart with stated limitations,
   cancellation tables by airline and airport, CSV exports.

Every page states the denominator behind a rate, shows an empty state when a filter
matches nothing, and shows a retry path when the API is unreachable.

### Screenshots of the running system

Captured with `python scripts/capture_screenshots.py` against the live API and Streamlit
instance (1680x1050, real 2025 results):

| Page | Screenshot |
| --- | --- |
| Overview | [`docs/screenshots/01_overview.png`](docs/screenshots/01_overview.png) |
| Airline performance | [`docs/screenshots/02_airline_performance.png`](docs/screenshots/02_airline_performance.png) |
| Airport and routes | [`docs/screenshots/03_airport_and_routes.png`](docs/screenshots/03_airport_and_routes.png) |
| Time analysis | [`docs/screenshots/04_time_analysis.png`](docs/screenshots/04_time_analysis.png) |
| Delay causes and cancellations | [`docs/screenshots/05_delay_causes_and_cancellations.png`](docs/screenshots/05_delay_causes_and_cancellations.png) |

---

## Testing

```
python -m pytest tests -q
73 passed
```

Coverage by layer: schema contract (6), cleaning and derivation (13), metrics against
hand-calculated fixtures (10), MapReduce mappers/reducers/combiners as real subprocesses
(9, including a combiner associativity check), API behaviour and validation (18),
cross-layer consistency MapReduce vs Hive vs API vs reference (5). Details and the exact
expected values are in [`docs/testing.md`](docs/testing.md).

---

## Performance (measured, single node)

| Stage | Data | Time |
| --- | --- | --- |
| Cleaning (12 partitions) | 7,001,619 rows / 1,063.7 MB | 331 s (~21,000 rows/s) |
| HDFS upload | 93.7 MB (one month) | 14.2 s (~6.6 MB/s) |
| MapReduce, 4 jobs | 1.0 GB in HDFS | 288.6 s total |
| Hive Parquet load | 7,001,619 rows | 159.7 s |
| Hive, 10 analytical queries | Parquet table | 264.3 s total |

These are single-node numbers. No multi-node speedup is claimed; see
[`docs/performance.md`](docs/performance.md) and [`docs/limitations.md`](docs/limitations.md).

---

## Documentation

- [`docs/architecture.md`](docs/architecture.md) - components, data flow, HDFS layout, contracts
- [`docs/data_dictionary.md`](docs/data_dictionary.md) - every field, source column, validity rule
- [`docs/metrics.md`](docs/metrics.md) - numerator/denominator of every metric
- [`docs/setup_guide.md`](docs/setup_guide.md) - install, configure, run, troubleshoot
- [`docs/hive_queries.md`](docs/hive_queries.md) - how to run each Hive analysis
- [`docs/testing.md`](docs/testing.md) - test inventory, expected values, results
- [`docs/performance.md`](docs/performance.md) - measurements and scale experiments
- [`docs/limitations.md`](docs/limitations.md) - environment limits and honest caveats
