# Metric definitions

Every number in the dashboard, the API, the MapReduce jobs and the Hive queries comes from
the definitions below. The same definitions are implemented once in `src/common/spec.py`
and `src/common/metrics.py`, mirrored by the reducers and the `.hql` files, and enforced by
`tests/test_metrics.py` (hand-calculated fixture) and `tests/test_numerical_consistency.py`
(MapReduce vs Hive vs API vs reference).

Rounding: averages and rates are rounded to 4 decimal places in every layer. Rates are
percentages (a value of `22.31` means 22.31 %). Comparisons between layers allow 0.01
absolute tolerance.

## Core metrics

| Metric | Definition | Numerator | Denominator | Empty denominator |
| --- | --- | --- | --- | --- |
| Total flights | Records after the deduplication rule | - | - | - |
| Flights with valid departure measurement | `COUNT(departure_delay)` | - | - | - |
| Flights with valid arrival measurement | `COUNT(arrival_delay)` | - | - | - |
| Average departure delay | Mean of departure delays in minutes | `SUM(departure_delay)` | valid departure measurements | null |
| Average arrival delay | Mean of arrival delays in minutes | `SUM(arrival_delay)` | valid arrival measurements | null |
| Departure-delay rate | Share of flights departing 15+ min late | `SUM(is_departure_delayed)` | valid departure measurements | null |
| Arrival-delay rate | Share of flights arriving 15+ min late | `SUM(is_arrival_delayed)` | valid arrival measurements | null |
| Cancellation rate | Share of cancelled flights | `SUM(cancelled)` | all flight records | null |
| Delay minutes | Delay floored at zero | `SUM(MAX(delay,0))` | - | - |

Deliberate choices:

- **Departure and arrival metrics are never combined.** An average is always of one metric.
- **Cancelled and diverted flights do not enter delay denominators.** They have no arrival
  measurement; treating a missing arrival delay as zero would understate delays by roughly
  the cancellation rate.
- **Negative delays are kept.** Early departures and arrivals are real measurements, not
  errors; they are excluded only from "delay minutes" sums, which are floored at zero.
- **Rates always state their denominator.** The API returns the denominator counts next to
  every rate, and the dashboard labels rates as "of flights with a valid measurement".

## Dimensions

| Analysis | Grain | Key | Output file |
| --- | --- | --- | --- |
| Airline performance | airline | `airline_code` | `airline_performance.csv` |
| Airport performance | airport x role | `role`, `airport_code` | `airport_performance.csv` |
| Route performance | origin-destination | `route` | `route_performance.csv` |
| Monthly trends | year-month | `flight_year`, `flight_month` | `monthly_trends.csv` |
| Day of week | ISO weekday | `day_of_week` | `day_of_week.csv` |
| Delay categories | category | `delay_category` | `delay_categories.csv` |
| Delay causes | cause | `cause` | `delay_causes.csv` |
| Cancellations | airline x month | `airline_code`, `flight_year`, `flight_month` | `cancellations.csv` |
| Cancellations by airport | airport x month | `origin_airport`, `flight_year`, `flight_month` | `cancellation_airports.csv` |
| Summary | whole period | - | `summary.csv` |

Output columns are declared in exactly one place - `src/common/validate.py` (`OUTPUTS`) -
which both runners use to export headers and to compare against the reference.

## Delay categories

| Category | Arrival delay | Note |
| --- | --- | --- |
| `on_time` | < 15 min (including negative) | early arrivals count as on time |
| `minor` | 15-29 min | |
| `moderate` | 30-59 min | |
| `severe` | >= 60 min | |
| `unknown` | no arrival measurement | cancelled and most diverted flights |

These bands are **project-defined** for analysis; they are not an official aviation
standard. Boundary behaviour (14, 15, 29, 30, 59, 60) is locked by
`tests/test_cleaning.py::test_delay_category_boundaries`.

## Delay-cause attribution

| Rule | Detail |
| --- | --- |
| Source | `CarrierDelay`, `WeatherDelay`, `NASDelay`, `SecurityDelay`, `LateAircraftDelay` |
| Availability | BTS populates them only for flights with arrival delay >= 15 min |
| Missing means | "not reported", never zero minutes |
| Numerator | `SUM(cause_field)` over rows where that field is present |
| Share denominator | total of all five recorded cause fields |
| Interpretation | the carrier-reported attribution mix, **not** causal inference |

Recorded minutes can exceed the flight delay when a carrier attributes one delay to several
causes; the five shares answer "what does the operator blame", not "what caused the delay".

## Deduplication rule

Natural key: `flight_date`, `airline_code`, `flight_number`, `origin_airport`,
`destination_airport`. Rows are sorted by that key and the first occurrence is kept; the
remainder are counted in `duplicates_removed` and reported in the quality report. On the
2025 data this removed **0** rows, which is reported as-is rather than presented as a
cleaned improvement.

## Where each metric is computed

| Layer | Role |
| --- | --- |
| `src/common/metrics.py` | Reference implementation; used by tests and by `scripts/export_results.py` |
| `src/mapreduce/*_reducer.py` | Distributed implementation for airline, airport, monthly, route |
| `src/hive/0*.hql` | SQL implementation for all ten analyses (authoritative exports) |
| `src/backend/services.py` | Presentation only: filters, sorts, paginates, joins airline names |

No business rule is duplicated in the API or dashboard; they read prepared tables.
