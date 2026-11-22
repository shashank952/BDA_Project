USE airline_analytics;
SELECT COUNT(1) AS rows_in_hive FROM flights;
SELECT COUNT(DISTINCT airline_code) AS airlines FROM flights;
