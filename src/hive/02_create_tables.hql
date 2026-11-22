-- 02_create_tables.hql
-- External CSV table over the cleaned HDFS partitions + a typed Parquet table.
--
-- The CSV table keeps every column as STRING (OpenCSVSerde) because the cleaned
-- files contain quoted city names such as "New York, NY"; typing happens in the
-- INSERT below with explicit NULLIF(...,'') so that empty strings become real
-- NULLs instead of zeroes.

USE airline_analytics;

SET hive.exec.dynamic.partition = true;
SET hive.exec.dynamic.partition.mode = nonstrict;
SET hive.exec.max.dynamic.partitions = 5000;
SET mapreduce.framework.name = local;

CREATE EXTERNAL TABLE IF NOT EXISTS flights_raw_csv (
  flight_date            STRING,
  flight_year            STRING,
  flight_month           STRING,
  day_of_week            STRING,
  airline_code           STRING,
  flight_number          STRING,
  origin_airport         STRING,
  origin_city            STRING,
  origin_state           STRING,
  destination_airport    STRING,
  destination_city       STRING,
  destination_state      STRING,
  route                  STRING,
  scheduled_departure    STRING,
  actual_departure       STRING,
  dep_hour               STRING,
  departure_delay        STRING,
  departure_delay_minutes STRING,
  scheduled_arrival      STRING,
  actual_arrival         STRING,
  arrival_delay          STRING,
  arrival_delay_minutes  STRING,
  is_departure_delayed   STRING,
  is_arrival_delayed     STRING,
  delay_category         STRING,
  cancelled              STRING,
  diverted               STRING,
  cancellation_code      STRING,
  distance               STRING,
  carrier_delay          STRING,
  weather_delay          STRING,
  nas_delay              STRING,
  security_delay         STRING,
  late_aircraft_delay    STRING
)
PARTITIONED BY (year STRING, month STRING)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
WITH SERDEPROPERTIES (
  "separatorChar" = ",",
  "quoteChar"     = "\"",
  "escapeChar"    = "\\"
)
STORED AS TEXTFILE
LOCATION '/airline-delay/processed'
TBLPROPERTIES ("skip.header.line.count" = "1");

ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='01') LOCATION '/airline-delay/processed/year=2025/month=01';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='02') LOCATION '/airline-delay/processed/year=2025/month=02';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='03') LOCATION '/airline-delay/processed/year=2025/month=03';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='04') LOCATION '/airline-delay/processed/year=2025/month=04';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='05') LOCATION '/airline-delay/processed/year=2025/month=05';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='06') LOCATION '/airline-delay/processed/year=2025/month=06';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='07') LOCATION '/airline-delay/processed/year=2025/month=07';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='08') LOCATION '/airline-delay/processed/year=2025/month=08';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='09') LOCATION '/airline-delay/processed/year=2025/month=09';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='10') LOCATION '/airline-delay/processed/year=2025/month=10';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='11') LOCATION '/airline-delay/processed/year=2025/month=11';
ALTER TABLE flights_raw_csv ADD IF NOT EXISTS PARTITION (year='2025', month='12') LOCATION '/airline-delay/processed/year=2025/month=12';

CREATE TABLE IF NOT EXISTS flights (
  flight_date             DATE,
  flight_year             INT,
  flight_month            INT,
  day_of_week             INT,
  airline_code            STRING,
  flight_number           STRING,
  origin_airport          STRING,
  origin_city             STRING,
  origin_state            STRING,
  destination_airport     STRING,
  destination_city        STRING,
  destination_state       STRING,
  route                   STRING,
  scheduled_departure     STRING,
  actual_departure        STRING,
  dep_hour                INT,
  departure_delay         DOUBLE,
  departure_delay_minutes DOUBLE,
  scheduled_arrival       STRING,
  actual_arrival          STRING,
  arrival_delay           DOUBLE,
  arrival_delay_minutes   DOUBLE,
  is_departure_delayed    INT,
  is_arrival_delayed      INT,
  delay_category          STRING,
  cancelled               INT,
  diverted                INT,
  cancellation_code       STRING,
  distance                DOUBLE,
  carrier_delay           DOUBLE,
  weather_delay           DOUBLE,
  nas_delay               DOUBLE,
  security_delay          DOUBLE,
  late_aircraft_delay     DOUBLE
)
PARTITIONED BY (year STRING, month STRING)
STORED AS PARQUET
TBLPROPERTIES ("parquet.compression" = "UNCOMPRESSED");

INSERT OVERWRITE TABLE flights PARTITION (year, month)
SELECT
  CAST(NULLIF(flight_date, '') AS DATE),
  CAST(NULLIF(flight_year, '') AS INT),
  CAST(NULLIF(flight_month, '') AS INT),
  CAST(NULLIF(day_of_week, '') AS INT),
  NULLIF(airline_code, ''),
  NULLIF(flight_number, ''),
  NULLIF(origin_airport, ''),
  NULLIF(origin_city, ''),
  NULLIF(origin_state, ''),
  NULLIF(destination_airport, ''),
  NULLIF(destination_city, ''),
  NULLIF(destination_state, ''),
  NULLIF(route, ''),
  NULLIF(scheduled_departure, ''),
  NULLIF(actual_departure, ''),
  CAST(NULLIF(dep_hour, '') AS INT),
  CAST(NULLIF(departure_delay, '') AS DOUBLE),
  CAST(NULLIF(departure_delay_minutes, '') AS DOUBLE),
  NULLIF(scheduled_arrival, ''),
  NULLIF(actual_arrival, ''),
  CAST(NULLIF(arrival_delay, '') AS DOUBLE),
  CAST(NULLIF(arrival_delay_minutes, '') AS DOUBLE),
  CAST(NULLIF(is_departure_delayed, '') AS INT),
  CAST(NULLIF(is_arrival_delayed, '') AS INT),
  NULLIF(delay_category, ''),
  CAST(NULLIF(cancelled, '') AS INT),
  CAST(NULLIF(diverted, '') AS INT),
  NULLIF(cancellation_code, ''),
  CAST(NULLIF(distance, '') AS DOUBLE),
  CAST(NULLIF(carrier_delay, '') AS DOUBLE),
  CAST(NULLIF(weather_delay, '') AS DOUBLE),
  CAST(NULLIF(nas_delay, '') AS DOUBLE),
  CAST(NULLIF(security_delay, '') AS DOUBLE),
  CAST(NULLIF(late_aircraft_delay, '') AS DOUBLE),
  year,
  month
FROM flights_raw_csv;

SELECT COUNT(1) AS row_count,
       COUNT(DISTINCT airline_code) AS airlines,
       MIN(flight_date) AS first_date,
       MAX(flight_date) AS last_date
FROM flights;
