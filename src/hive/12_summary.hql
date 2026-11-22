-- 12_summary.hql
-- Overall KPIs for the overview dashboard page.
-- Every rate states its denominator through the *_flights columns.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  COUNT(1) AS total_flights,
  SUM(CASE WHEN departure_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_departure_flights,
  SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_arrival_flights,
  COALESCE(CAST(ROUND(AVG(departure_delay), 4) AS STRING), '') AS avg_departure_delay,
  COALESCE(CAST(ROUND(AVG(arrival_delay), 4) AS STRING), '') AS avg_arrival_delay,
  SUM(is_departure_delayed) AS departure_delayed_flights,
  SUM(is_arrival_delayed) AS arrival_delayed_flights,
  COALESCE(CAST(ROUND(100.0 * SUM(is_departure_delayed) /
    NULLIF(SUM(CASE WHEN departure_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS departure_delay_rate,
  COALESCE(CAST(ROUND(100.0 * SUM(is_arrival_delayed) /
    NULLIF(SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS arrival_delay_rate,
  SUM(cancelled) AS cancelled_flights,
  COALESCE(CAST(ROUND(100.0 * SUM(cancelled) / NULLIF(COUNT(1), 0), 4) AS STRING), '') AS cancellation_rate,
  SUM(diverted) AS diverted_flights,
  MIN(flight_date) AS first_date,
  MAX(flight_date) AS last_date
FROM flights;
