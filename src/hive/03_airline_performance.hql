-- 03_airline_performance.hql
-- Query A: airline performance.
-- Delay denominators are valid measurements only; cancellations use all flights.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  airline_code,
  COUNT(1) AS total_flights,
  SUM(CASE WHEN departure_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_departure_flights,
  COALESCE(CAST(ROUND(AVG(departure_delay), 4) AS STRING), '') AS avg_departure_delay,
  SUM(is_departure_delayed) AS departure_delayed_flights,
  COALESCE(CAST(ROUND(100.0 * SUM(is_departure_delayed) /
    NULLIF(SUM(CASE WHEN departure_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS departure_delay_rate,
  SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_arrival_flights,
  COALESCE(CAST(ROUND(AVG(arrival_delay), 4) AS STRING), '') AS avg_arrival_delay,
  SUM(is_arrival_delayed) AS delayed_arrivals,
  COALESCE(CAST(ROUND(100.0 * SUM(is_arrival_delayed) /
    NULLIF(SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS arrival_delay_rate,
  SUM(cancelled) AS cancellations,
  COALESCE(CAST(ROUND(100.0 * SUM(cancelled) / NULLIF(COUNT(1), 0), 4) AS STRING), '') AS cancellation_rate
FROM flights
GROUP BY airline_code
ORDER BY airline_code;
