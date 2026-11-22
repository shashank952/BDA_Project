-- 04_airport_performance.hql
-- Query B: airport performance, departure and arrival roles kept separate.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  'departure' AS role,
  origin_airport AS airport_code,
  COUNT(1) AS total_flights,
  SUM(CASE WHEN departure_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_delay_flights,
  COALESCE(CAST(ROUND(AVG(departure_delay), 4) AS STRING), '') AS avg_delay,
  SUM(is_departure_delayed) AS delayed_flights,
  COALESCE(CAST(ROUND(100.0 * SUM(is_departure_delayed) /
    NULLIF(SUM(CASE WHEN departure_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS delay_rate
FROM flights
GROUP BY origin_airport

UNION ALL

SELECT
  'arrival' AS role,
  destination_airport AS airport_code,
  COUNT(1) AS total_flights,
  SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_delay_flights,
  COALESCE(CAST(ROUND(AVG(arrival_delay), 4) AS STRING), '') AS avg_delay,
  SUM(is_arrival_delayed) AS delayed_flights,
  COALESCE(CAST(ROUND(100.0 * SUM(is_arrival_delayed) /
    NULLIF(SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS delay_rate
FROM flights
GROUP BY destination_airport;
