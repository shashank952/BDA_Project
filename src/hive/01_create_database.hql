-- 01_create_database.hql
-- Creates the analytical database. Safe to re-run.
CREATE DATABASE IF NOT EXISTS airline_analytics
  COMMENT 'Airline flight delay analysis (BTS On-Time Performance, 2025)'
  LOCATION '/airline-delay/hive/warehouse/airline_analytics';

USE airline_analytics;

SHOW DATABASES;
