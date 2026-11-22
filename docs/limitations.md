# Limitations and honest caveats

## Scope

- **Historical analysis only.** The system describes 2025 flight records. It does not track
  live flights, does not predict delays, and does not estimate causal effects. Any statement
  built on the delay-cause fields is about carrier-reported attribution.
- **Descriptive statistics, not inference.** Rankings (airline, airport, route) are unadjusted
  comparisons. Airlines differ in network mix, hub exposure and seasonality; no model removes
  those confounders, and none is claimed to.

## Dataset

- **One year only (2025).** Seasonality conclusions are therefore within-year patterns, not
  long-run trends. A single severe winter month can move an annual average noticeably.
- **Reporting carriers only.** The dataset covers 14 reporting carriers. Regional operators
  that fly under a mainline brand may appear under their own reporting code, so "airline"
  performance is not always the brand a passenger booked.
- **Cause fields are partial by design.** BTS reports the five cause minutes only for flights
  with an arrival delay of at least 15 minutes, and the values are carrier-reported. A null
  means "not reported", never zero. Recorded minutes may exceed the delay itself when one
  delay is attributed to several causes.
- **No external context.** Weather severity, airport capacity, crew scheduling, aircraft type
  and passenger counts are not in scope, so no explanation of *why* a month was bad is offered.
- **One unexplained null.** 122,135 flights have no arrival delay; 122,134 are cancelled or
  diverted. One record has neither flag set and a null measurement. It is excluded from
  arrival statistics and reported in `docs/data_dictionary.md` rather than imputed.
- **Zero rows quarantined on real data.** The validation rules found no defects in the BTS 2025
  files. They are exercised by the committed fixture, which contains an invalid date, a
  negative distance and an invalid cancellation flag. "0 quarantined" is a finding, not a
  disabled check.

## Environment

- **Single node.** NameNode, DataNode and all computation run on one Windows machine. There is
  no replication benefit, no inter-node shuffle and no real data locality. Nothing in this
  repository is evidence of multi-node scalability, and no speedup is claimed.
- **LocalJobRunner instead of YARN.** YARN container localization requires
  `SeCreateSymbolicLinkPrivilege` (`CreateSymbolicLink error 1314`), which needs Administrator
  or Developer Mode on this machine. Jobs therefore execute through Hadoop's LocalJobRunner:
  the same `Job`/`Mapper`/`Reducer`/shuffle path, in a single JVM, without container isolation.
  `AIRLINE_MR_FRAMEWORK=yarn` restores cluster submission on a host with the privilege.
- **Hive with embedded Derby.** One Hive session at a time; no concurrent users, no
  HiveServer2/Beeline endpoint, no Tez. Each query pays a JVM plus session startup of roughly
  15-18 s, which inflates the per-query timings in `docs/performance.md`.
- **Windows-specific accommodations.** Direct `java -cp ... CliDriver` invocation instead of
  the `.cmd` wrappers (they returned exit 0 on failure and truncated arguments at `=`),
  unquoted Streaming commands, an empty Streaming output separator, and disabled Hive
  local-auto mode. Each is documented in `docs/architecture.md`.
- **Data volume.** 7,001,619 rows and 1.0 GB are modest by industry standards. Hadoop is used
  here to demonstrate and measure the distributed workflow end to end, not because the dataset
  requires a cluster. On a single node the pandas reference implementation is faster than both
  MapReduce and Hive; that is expected and is why the reference exists as a correctness oracle.

## Application

- **No authentication.** The API and dashboard are local academic demo components bound to
  127.0.0.1. Before any public deployment they need authentication, TLS, rate limiting and
  request logging.
- **Precomputed aggregates.** The API serves tables computed for the loaded period. Filters
  exist where the grain supports them exactly (airline, airport, route, role, year, month,
  minimum flight counts, sorting, pagination). Arbitrary date-range filtering of airline or
  airport averages is deliberately not offered, because re-deriving an average from
  pre-aggregated output would produce a number that was never computed.
- **Pagination limits.** List endpoints cap at 500 rows per request (configured) and do not
  return the raw dataset; the route table holds 6,938 rows and is served in pages.
- **Route minimum.** Route rankings are filtered by a configurable minimum flight count
  (default 100) so a route with one severe delay cannot top the table. The exported Hive table
  is unfiltered; the threshold is applied at presentation.
- **No map view.** Airport coordinates are not part of the selected dataset fields, so the
  "optional map" from the plan was not implemented rather than approximated with fake geometry.
- **Airline names** come from a static `config/airlines.csv` lookup for the 14 carriers present;
  an unknown code would display as the raw code.

## Testing

- No multi-node test, no failure-injection test against a real cluster, no concurrent-user load
  test, and no browser-level (mouse/keyboard) automation. Dashboard pages are executed through
  Streamlit's `AppTest` harness, which runs the real page code against the live API and asserts
  no exception.
- Numerical agreement is enforced at 0.01 absolute tolerance because each layer rounds to four
  decimals at different points; within that tolerance MapReduce, Hive, the reference
  implementation and the API agree row by row.
