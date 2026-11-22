# Data dictionary

Source: U.S. Bureau of Transportation Statistics, *Airline On-Time Performance*
(`On_Time_Reporting_Carrier_On_Time_Performance_1987_present`), monthly archives.
Download page: <https://transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FGJ>

The archive used here contains **110 columns**. Only the 24 mapped below are read; the
others (taxi times, gate return details, diversion legs 1-5) are out of scope and never
enter memory. The mapping is declared in `config/schema_mapping.yaml`, which is the
authoritative version of this table.

`Required` refers to the cleaning contract: a missing required column aborts the run; a
missing optional column disables only the analyses that depend on it and is recorded in
`field_availability.missing_optional_source_columns` of the quality report.

## Source fields

| Standardized field | Source column | Type | Unit | Required | Validity rule | Missing handling | Used by |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `flight_date` | `FlightDate` | date | calendar date | yes | `YYYY-MM-DD`, 1987-01-01..today+1 | Row quarantined | all analyses |
| `airline_code` | `Reporting_Airline` | string | IATA carrier code | yes | 2-3 alphanumeric, uppercased | Row quarantined | airline, monthly, cancellations, causes |
| `flight_number` | `Flight_Number_Reporting_Airline` | string | flight number | no | digits | Null allowed | dedupe key only |
| `origin_airport` | `Origin` | string | IATA code | yes | 3-4 alphanumeric | Row quarantined | airport departure, routes, cancellations |
| `origin_city` | `OriginCityName` | string | text | no | free text (may contain a comma) | Null allowed | dashboard labels |
| `origin_state` | `OriginState` | string | 2-letter state | no | two letters | Null allowed | dashboard labels |
| `destination_airport` | `Dest` | string | IATA code | yes | 3-4 alphanumeric | Row quarantined | airport arrival, routes |
| `destination_city` | `DestCityName` | string | text | no | free text | Null allowed | dashboard labels |
| `destination_state` | `DestState` | string | 2-letter state | no | two letters | Null allowed | dashboard labels |
| `scheduled_departure` | `CRSDepTime` | hhmm | local hhmm | no | 0000-2359 (`2400` folded to 0000) | Null allowed | hour-of-day |
| `actual_departure` | `DepTime` | hhmm | local hhmm | no | 0000-2359 | Expected null when cancelled | traceability |
| `departure_delay` | `DepDelay` | double | minutes | no | -300..5000 | Excluded from statistics, **never** coerced to 0 | airport departure, monthly |
| `arrival_delay` | `ArrDelay` | double | minutes | no | -300..5000 | Excluded from numerators and denominators | airline, airport arrival, routes, monthly |
| `scheduled_arrival` | `CRSArrTime` | hhmm | local hhmm | no | 0000-2359 | Null allowed | traceability |
| `actual_arrival` | `ArrTime` | hhmm | local hhmm | no | 0000-2359 | Expected null when cancelled | traceability |
| `cancelled` | `Cancelled` | flag | 0/1 | yes | exactly 0 or 1 | Row quarantined | cancellations, summary |
| `diverted` | `Diverted` | flag | 0/1 | yes | exactly 0 or 1 | Row quarantined | summary |
| `distance` | `Distance` | double | miles | no | 0..12000 | Null allowed | labels, sanity checks |
| `cancellation_code` | `CancellationCode` | string | A/B/C/D | no | one of A,B,C,D or null | Null is normal when not cancelled | cancellation reasons |
| `carrier_delay` | `CarrierDelay` | double | minutes | no | 0..5000 | Null means *not reported* | delay causes |
| `weather_delay` | `WeatherDelay` | double | minutes | no | 0..5000 | Null means *not reported* | delay causes |
| `nas_delay` | `NASDelay` | double | minutes | no | 0..5000 | Null means *not reported* | delay causes |
| `security_delay` | `SecurityDelay` | double | minutes | no | 0..5000 | Null means *not reported* | delay causes |
| `late_aircraft_delay` | `LateAircraftDelay` | double | minutes | no | 0..5000 | Null means *not reported* | delay causes |

## Derived fields

| Field | Definition | Type |
| --- | --- | --- |
| `flight_year` | Year of `flight_date` | int |
| `flight_month` | Month of `flight_date`, 1-12 | int |
| `day_of_week` | ISO day of week, 1 = Monday, 7 = Sunday | int |
| `dep_hour` | Hour of `scheduled_departure`, 0-23, null when unknown | int |
| `departure_delay_minutes` | `max(departure_delay, 0)`, null when the delay is null | double |
| `arrival_delay_minutes` | `max(arrival_delay, 0)`, null when the delay is null | double |
| `is_departure_delayed` | 1 when `departure_delay >= 15`, else 0, null when unknown | int |
| `is_arrival_delayed` | 1 when `arrival_delay >= 15`, else 0, null when unknown | int |
| `delay_category` | `on_time` <15, `minor` 15-29, `moderate` 30-59, `severe` >=60, `unknown` when no arrival measurement | string |
| `route` | `origin_airport` + `-` + `destination_airport` | string |

## Rejection reasons (quarantine)

`source_row` and a `rejection_reasons` list are written to
`data/quarantine/year=YYYY/month=MM/rejected.csv`. Reasons, in evaluation order:

| Reason | Trigger |
| --- | --- |
| `missing_key_field` | any of `flight_date`, `airline_code`, `origin_airport`, `destination_airport` empty |
| `invalid_flight_date` | unparseable or outside 1987-01-01..today+1 |
| `invalid_airline_code` | not 2-3 alphanumeric characters |
| `invalid_origin_airport` / `invalid_destination_airport` | not 3-4 alphanumeric characters |
| `invalid_cancelled_flag` / `invalid_diverted_flag` | not exactly 0 or 1 |
| `non_numeric_<field>` | a non-empty value that cannot be parsed as a number |
| `implausible_departure_delay` / `implausible_arrival_delay` | outside -300..5000 minutes |
| `implausible_distance` | negative or above 12,000 miles |

On the real 2025 data **no rows were quarantined** (0 of 7,001,619). That is a property of
the BTS dataset, not a disabled check: the rules are exercised by
`tests/fixtures/sample_flights.csv`, which contains one invalid date, one negative
distance and one invalid cancellation flag.

## Observed data quality (2025)

| Field | Missing | Share |
| --- | --- | --- |
| `arrival_delay` | 122,135 | 1.74 % - 122,134 are the cancelled and diverted flights, plus one record with neither flag set |
| `departure_delay` | 98,591 | 1.41 % |
| `carrier_delay` .. `late_aircraft_delay` | 5,466,981 | 78.08 % - BTS reports causes only for delays >= 15 min |
| `cancellation_code` | 6,898,743 | 98.53 % - null for every non-cancelled flight, as expected |
| `distance` | 0 | 0.00 % |

The arrival-delay null count is explained by cancellations and diversions to within a single
record (102,876 cancelled + 19,258 diverted = 122,134). That one residual row keeps a null
arrival measurement with neither flag set; it is retained, excluded from arrival-delay
statistics, and reported here rather than patched, because inventing a delay for it would be
worse than leaving it out.
