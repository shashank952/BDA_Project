-- 06_route_analysis.hql
-- Query E: route performance ranked by average arrival delay and delay rate.
-- min_route_flights filters out routes too small to be meaningful.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  origin_airport || '-' || destination_airport AS route,
  origin_airport,
  destination_airport,
  COUNT(1) AS total_flights,
  SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_arrival_flights,
  COALESCE(CAST(ROUND(AVG(arrival_delay), 4) AS STRING), '') AS avg_arrival_delay,
  SUM(is_arrival_delayed) AS delayed_arrivals,
  COALESCE(CAST(ROUND(100.0 * SUM(is_arrival_delayed) /
    NULLIF(SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS arrival_delay_rate
FROM flights
GROUP BY origin_airport, destination_airport
HAVING COUNT(1) >= ${hiveconf:min_route_flights}
ORDER BY arrival_delay_rate DESC, total_flights DESC;
