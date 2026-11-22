-- 11_day_of_week.hql
-- Day-of-week comparison used by the time-analysis dashboard page.
-- day_of_week is ISO: 1 = Monday ... 7 = Sunday.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  day_of_week,
  COUNT(1) AS total_flights,
  SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END) AS valid_arrival_flights,
  COALESCE(CAST(ROUND(AVG(arrival_delay), 4) AS STRING), '') AS avg_arrival_delay,
  SUM(is_arrival_delayed) AS delayed_arrivals,
  COALESCE(CAST(ROUND(100.0 * SUM(is_arrival_delayed) /
    NULLIF(SUM(CASE WHEN arrival_delay IS NOT NULL THEN 1 ELSE 0 END), 0), 4) AS STRING), '') AS arrival_delay_rate
FROM flights
GROUP BY day_of_week
ORDER BY day_of_week;
