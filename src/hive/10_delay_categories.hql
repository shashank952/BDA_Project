-- 10_delay_categories.hql
-- Query D: flight counts in the four project-defined delay categories.
-- "unknown" covers cancelled / diverted flights without an arrival measurement.
USE airline_analytics;

INSERT OVERWRITE DIRECTORY '${hiveconf:outdir}'
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
SELECT
  delay_category,
  COUNT(1) AS flights,
  COALESCE(CAST(ROUND(100.0 * COUNT(1) / NULLIF(t.total, 0), 4) AS STRING), '') AS share_pct
FROM flights
CROSS JOIN (SELECT COUNT(1) AS total FROM flights) t
GROUP BY delay_category, t.total
ORDER BY flights DESC;
