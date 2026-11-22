# Hive queries

All queries live in `src/hive/*.hql` and are executed through
`org.apache.hadoop.hive.cli.CliDriver` (not `hive.cmd`, see `docs/architecture.md`).
The runner is `src/hive/run_queries.py`; each analysis writes to its own HDFS directory with
`INSERT OVERWRITE DIRECTORY`, so re-running replaces the previous result instead of appending.

```powershell
python -m src.hive.run_queries --setup                    # database, tables, Parquet load
python -m src.hive.run_queries --query airline_performance
python -m src.hive.run_queries --all --validate           # every query + numeric validation
```

Single query by hand, equivalent to what the runner does:

```powershell
java -cp "<hadoop classpath>;<HIVE_HOME>/lib/*" `
  org.apache.hadoop.hive.cli.CliDriver `
  -f src/hive/05_monthly_trends.hql `
  --hiveconf outdir=/airline-delay/analytics/monthly_trends/hive
```

## Setup scripts

| File | Purpose | Notes |
| --- | --- | --- |
| `01_create_database.hql` | Create `airline_analytics` at `/airline-delay/hive/warehouse/airline_analytics` | Idempotent |
| `02_create_tables.hql` | External CSV table `flights_raw_csv` + typed Parquet table `flights` | Adds 12 monthly partitions, then one dynamic-partition `INSERT OVERWRITE` |

`flights_raw_csv` uses `OpenCSVSerde` with every column as `STRING` because city names contain
commas (`"New York, NY"`). Types are applied in the INSERT with `CAST(NULLIF(col,'') AS ...)`
so that an empty string becomes `NULL` and never a zero.

## Analytical queries

| File | Query | Output columns | Notes |
| --- | --- | --- | --- |
| `03_airline_performance.hql` | A - airline performance | `airline_code, total_flights, valid_departure_flights, avg_departure_delay, departure_delayed_flights, departure_delay_rate, valid_arrival_flights, avg_arrival_delay, delayed_arrivals, arrival_delay_rate, cancellations, cancellation_rate` | Departure and arrival metrics kept apart |
| `04_airport_performance.hql` | B - airport performance | `role, airport_code, total_flights, valid_delay_flights, avg_delay, delayed_flights, delay_rate` | `UNION ALL` of origin (departure) and destination (arrival) |
| `05_monthly_trends.hql` | C - monthly trends | `flight_year, flight_month, total_flights, valid_arrival_flights, avg_arrival_delay, delayed_arrivals, arrival_delay_rate, cancellations, cancellation_rate` | Ordered chronologically |
| `06_route_analysis.hql` | E - route performance | `route, origin_airport, destination_airport, total_flights, valid_arrival_flights, avg_arrival_delay, delayed_arrivals, arrival_delay_rate` | `--hiveconf min_route_flights=N`; exported unfiltered and ranked at presentation |
| `07_delay_causes.hql` | F - delay causes | `cause, delay_minutes, flights_with_cause, share_pct` | Counts only rows where that cause is reported; share denominator is total recorded cause minutes |
| `08_cancellations.hql` | G (1/2) - cancellations by airline and month | `airline_code, flight_year, flight_month, total_flights, cancellations, cancellation_rate` | |
| `09_cancellation_airports.hql` | G (2/2) - cancellations by airport | `origin_airport, flight_year, flight_month, total_flights, cancellations, cancellation_rate, cancelled_carrier, cancelled_weather, cancelled_nas, cancelled_security` | `HAVING SUM(cancelled) > 0` |
| `10_delay_categories.hql` | D - delay categories | `delay_category, flights, share_pct` | Includes `unknown` for flights without an arrival measurement |
| `11_day_of_week.hql` | Day-of-week comparison | `day_of_week, total_flights, valid_arrival_flights, avg_arrival_delay, delayed_arrivals, arrival_delay_rate` | ISO weekdays, 1 = Monday |
| `12_summary.hql` | Overall KPIs | 12 KPI columns + `first_date, last_date` | One row |

## SQL conventions

- Division is always guarded: `100.0 * numerator / NULLIF(denominator, 0)`, so an empty group
  yields `NULL` rather than an error or a misleading zero.
- Metrics are wrapped in `COALESCE(CAST(ROUND(x,4) AS STRING), '')` so a null is written as an
  empty field (not `\N`) and the exported CSV parses cleanly into the API.
- Null measurements are excluded from denominators via
  `SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END)`.
- Filters on the external table should use the partition columns (`year`, `month`) to prune;
  the analytical queries run over the Parquet table, which is already partitioned the same way.
- `INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'` makes every run replace its own output.

## Verifying a query

`run_queries.py --validate` compares each exported CSV against `src/common/metrics.py` with a
0.01 tolerance and fails the run on any mismatch. Outputs land in
`outputs/analytics/<name>.csv` (Hive, authoritative) and the HDFS result directory is
`/airline-delay/analytics/<name>/hive`.
