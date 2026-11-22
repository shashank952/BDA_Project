-- 08_cancellations.hql
-- Query G (part 1): cancellations by airline and month.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  airline_code,
  flight_year,
  flight_month,
  COUNT(1) AS total_flights,
  SUM(cancelled) AS cancellations,
  COALESCE(CAST(ROUND(100.0 * SUM(cancelled) / NULLIF(COUNT(1), 0), 4) AS STRING), '') AS cancellation_rate
FROM flights
GROUP BY airline_code, flight_year, flight_month
ORDER BY flight_year, flight_month, cancellations DESC;
