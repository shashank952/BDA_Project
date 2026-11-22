-- 09_cancellation_airports.hql
-- Query G (part 2): cancellation counts and rates by origin airport and month.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  origin_airport,
  flight_year,
  flight_month,
  COUNT(1) AS total_flights,
  SUM(cancelled) AS cancellations,
  COALESCE(CAST(ROUND(100.0 * SUM(cancelled) / NULLIF(COUNT(1), 0), 4) AS STRING), '') AS cancellation_rate,
  SUM(CASE WHEN cancellation_code = 'A' THEN 1 ELSE 0 END) AS cancelled_carrier,
  SUM(CASE WHEN cancellation_code = 'B' THEN 1 ELSE 0 END) AS cancelled_weather,
  SUM(CASE WHEN cancellation_code = 'C' THEN 1 ELSE 0 END) AS cancelled_nas,
  SUM(CASE WHEN cancellation_code = 'D' THEN 1 ELSE 0 END) AS cancelled_security
FROM flights
GROUP BY origin_airport, flight_year, flight_month
HAVING SUM(cancelled) > 0
ORDER BY cancellations DESC;
