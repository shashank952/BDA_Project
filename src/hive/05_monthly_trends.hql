-- 05_monthly_trends.hql
-- Query C: monthly trends (average arrival delay, delayed rate, cancellations).
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  flight_year,
  flight_month,
  COUNT(1) AS total_flights,
  SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_arrival_flights,
  COALESCE(CAST(ROUND(AVG(arrival_delay), 4) AS STRING), '') AS avg_arrival_delay,
  SUM(is_arrival_delayed) AS delayed_arrivals,
  COALESCE(CAST(ROUND(100.0 * SUM(is_arrival_delayed) /
    NULLIF(SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS arrival_delay_rate,
  SUM(cancelled) AS cancellations,
  COALESCE(CAST(ROUND(100.0 * SUM(cancelled) / NULLIF(COUNT(1), 0), 4) AS STRING), '') AS cancellation_rate
FROM flights
GROUP BY flight_year, flight_month
ORDER BY flight_year, flight_month;
