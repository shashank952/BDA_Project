# Downloading the dataset

Source: U.S. Bureau of Transportation Statistics, *Airline On-Time Performance*.

- Landing page: <https://www.transtats.bts.gov/>
- Field selection page: <https://transtats.bts.gov/DL_SelectFields.aspx?gnoyr_VQ=FGJ>

## Option 1 - scripted (used by this project)

BTS publishes one zip per month in a stable URL pattern, which the downloader uses:

```
https://transtats.bts.gov/PREZIP/On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{YYYY}_{M}.zip
```

```powershell
python scripts/download_dataset.py --year 2025 --months 1-12
python scripts/download_dataset.py --year 2025 --list-available   # probe which months exist
```

Behaviour:

- files are stored at `data/raw/bts/year=YYYY/` and are never rewritten;
- an existing non-empty archive is skipped unless `--force` is passed;
- each download is checked to be a valid zip before the `.part` file is promoted;
- the reported size is compared with the server's `Content-Length`.

Verified availability at the time of the build: 2024-01 through 2026-06. This project uses the
full 2025 year (12 files, 339.0 MB, 7,001,619 records).

## Option 2 - manual, through the BTS web form

1. Open the field selection page.
2. Choose **Prezip, Download, All Fields** or a subset. If you select a subset, the pipeline's
   required columns are:

   `FlightDate`, `Reporting_Airline`, `Flight_Number_Reporting_Airline`, `Origin`,
   `Dest`, `Cancelled`, `Diverted`
   plus the strongly recommended ones:
   `DepDelay`, `ArrDelay`, `CRSDepTime`, `DepTime`, `CRSArrTime`, `ArrTime`,
   `Distance`, `CancellationCode`, `CarrierDelay`, `WeatherDelay`, `NASDelay`,
   `SecurityDelay`, `LateAircraftDelay`, `OriginCityName`, `OriginState`,
   `DestCityName`, `DestState`.

   Missing optional columns do not break the pipeline: the affected analysis is disabled and
   the fact is written to the quality report. Missing required columns abort validation with
   the list of names.
3. Select **January 2025** and **December 2025** as the range, or one month at a time.
4. Download the zip(s) and place them in `data/raw/bts/year=2025/`.

The pipeline accepts either the zip or an already extracted CSV; `--input-file` cleans a single
file directly.

## Licensing and redistribution

BTS data is U.S. federal government data distributed by the Bureau of Transportation
Statistics. Before redistributing the raw archives, check the current terms on the BTS site.
This repository therefore:

- does **not** commit the downloaded archives (`data/raw/` is git-ignored);
- commits only a 15-row synthetic fixture with hand-chosen values for tests;
- records the source, period and row counts so results can be reproduced.

## Verifying a download

```powershell
python -c "import pandas as pd; d=pd.read_csv('data/processed/year=2025/month=01/flights.csv', nrows=5); print(d[['flight_date','airline_code','origin_airport','destination_airport','arrival_delay']])"
```

Expected for 2025-01: 539,747 data rows, dates 2025-01-01..2025-01-31, 14 carriers,
329 origin airports.
