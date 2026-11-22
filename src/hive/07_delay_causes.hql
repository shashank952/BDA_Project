-- 07_delay_causes.hql
-- Query F: distribution of recorded delay minutes by cause.
--
-- BTS populates the cause fields only for flights whose arrival delay is at
-- least 15 minutes, so a NULL cause means "not reported", not "zero minutes".
-- This query therefore only counts rows where that specific cause is present,
-- and the share denominator is the total of all recorded cause minutes.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  cause,
  COALESCE(CAST(ROUND(SUM(minutes), 2) AS STRING), '') AS delay_minutes,
  COUNT(1) AS flights_with_cause,
  COALESCE(CAST(ROUND(100.0 * SUM(minutes) / NULLIF(t.total_minutes, 0), 4) AS STRING), '') AS share_pct
FROM (
  SELECT 'Carrier' AS cause, carrier_delay AS minutes FROM flights WHERE carrier_delay IS NOT NULL
  UNION ALL
  SELECT 'Weather' AS cause, weather_delay AS minutes FROM flights WHERE weather_delay IS NOT NULL
  UNION ALL
  SELECT 'National Aviation System' AS cause, nas_delay AS minutes FROM flights WHERE nas_delay IS NOT NULL
  UNION ALL
  SELECT 'Security' AS cause, security_delay AS minutes FROM flights WHERE security_delay IS NOT NULL
  UNION ALL
  SELECT 'Late aircraft' AS cause, late_aircraft_delay AS minutes FROM flights WHERE late_aircraft_delay IS NOT NULL
) cause_rows
CROSS JOIN (
  SELECT
    COALESCE(SUM(carrier_delay), 0) + COALESCE(SUM(weather_delay), 0) +
    COALESCE(SUM(nas_delay), 0) + COALESCE(SUM(security_delay), 0) +
    COALESCE(SUM(late_aircraft_delay), 0) AS total_minutes
  FROM flights
) t
GROUP BY cause, t.total_minutes
ORDER BY SUM(minutes) DESC;
