# Task 2: Pipeline Building — Marketing Weather Signal

## What I Built and Why

I built a data pipeline that pulls daily weather data from [Open-Meteo](https://open-meteo.com) for a configurable set of cities, transforms it into an analytics-ready format, and loads it into BigQuery.

### Why weather data for a marketing pipeline?

Weather is a genuine marketing signal. Retail, food delivery, outdoor, and FMCG brands routinely see conversion rates and footfall correlate with local weather conditions. A team running campaigns across multiple Indian cities (Chennai, Mumbai, Delhi, Bangalore, Hyderabad) would benefit from a clean, queryable daily weather table that can be joined against ad spend and conversion data.

This choice also connects Task 1 and Task 2 under a single narrative: the Marketing Signal Dashboard (Task 1) could surface weather context alongside channel performance — explaining *why* a campaign underperformed, not just *that* it did.

### Why Open-Meteo?

- Free, no API key, no billing setup
- Returns rich hourly JSON (good for demonstrating transformation skills)
- Reliable and well-documented
- Returns genuine data for Indian cities with good accuracy

---

## Pipeline Architecture

```
[Scheduler: cron / Cloud Scheduler]
              │
              ▼
      [pipeline.py runs]
              │
    ┌─────────┴──────────┐
    │  Fetch Layer        │  — requests with retry + timeout
    │  Open-Meteo API     │  — one API call per city
    └─────────┬──────────┘
              │ raw JSON (hourly resolution)
    ┌─────────┴──────────┐
    │  Transform Layer    │  — aggregate hourly → daily
    │                     │  — handle nulls and type mismatches
    │                     │  — compute 3 derived fields
    └─────────┬──────────┘
              │ list of WeatherRecord dataclasses
    ┌─────────┴──────────┐
    │  Load Layer         │  — google-cloud-bigquery SDK
    │  BigQuery           │  — append to weather_daily table
    └─────────────────────┘
```

---

## How to Run It

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set up BigQuery Sandbox

Go to [console.cloud.google.com/bigquery](https://console.cloud.google.com/bigquery). A default project is created automatically with a Google account — no credit card needed.

Open `pipeline.py` and replace the `BIGQUERY_PROJECT` constant at the top with your actual project ID (shown in the BigQuery console header).

### 3. Authenticate

```bash
gcloud auth application-default login
```

This stores credentials locally that the BigQuery SDK picks up automatically.

### 4. Run the pipeline

```bash
# Default: all 5 cities, last 7 days
python pipeline.py

# Dry run (no BigQuery write — useful for testing)
python pipeline.py --dry-run

# Custom cities
python pipeline.py --cities "Chennai,Mumbai"

# Extend lookback
python pipeline.py --days 14
```

### 5. Query the data

Open BigQuery console, select your project, and run the queries in `weather_summary.sql`.

---

## What the Pipeline Does at Each Step

### Step 1: Fetch
Calls the Open-Meteo hourly forecast endpoint for each city. Handles:
- Timeouts (15s limit, 3 retries with exponential backoff)
- HTTP 4xx errors (logged and skipped — retrying will not fix a bad request)
- Connection failures (retried with backoff)
- Malformed JSON (logged and skipped)

### Step 2: Transform
Groups hourly readings into daily records. Per day, per city:
- `temp_max_c`, `temp_min_c`, `temp_mean_c` — from temperature_2m hourly values
- `total_precipitation_mm` — summed over the day
- `max_windspeed_kmh` — peak reading of the day
- `mean_humidity_pct` — daily average

Three derived fields are computed:
- `feels_like_category` — "Cold" / "Mild" / "Warm" / "Hot" based on mean temp
- `is_rainy_day` — `True` if total precipitation exceeds 2mm
- `weather_marketing_score` — a 0–10 heuristic score for outdoor/retail conditions (see docstring in pipeline.py for full methodology)

Null handling: any hourly slot where the API returns `None` is filtered before aggregation. Days where the core temperature data is entirely missing are skipped with a warning.

### Step 3: Load
Appends records to `marketing_signals.weather_daily` in BigQuery. The schema is defined in code (`get_bigquery_schema()`) so it is version-controlled.

---

## BigQuery Schema

| Field | Type | Notes |
|---|---|---|
| city | STRING | City name |
| date | DATE | Day of record |
| lat / lon | FLOAT64 | Coordinates |
| temp_max_c | FLOAT64 | Daily high |
| temp_min_c | FLOAT64 | Daily low |
| temp_mean_c | FLOAT64 | Daily average |
| total_precipitation_mm | FLOAT64 | Rain/total precip |
| max_windspeed_kmh | FLOAT64 | Peak wind |
| mean_humidity_pct | FLOAT64 | Avg relative humidity |
| feels_like_category | STRING | Derived — Cold/Mild/Warm/Hot |
| is_rainy_day | BOOL | Derived — precip > 2mm |
| weather_marketing_score | FLOAT64 | Derived — 0–10 outdoor score |
| pipeline_run_date | DATE | When this run executed |

---

## Sample SQL Query Output

From `weather_summary.sql` Query 1 — weekly summary by city:

| city | avg_temp_c | total_rain_mm | rainy_days | avg_marketing_score | dominant_category |
|---|---|---|---|---|---|
| Bangalore | 24.1 | 12.4 | 3 | 6.8 | Warm |
| Chennai | 31.8 | 28.6 | 5 | 3.9 | Hot |
| Mumbai | 28.9 | 44.2 | 6 | 2.1 | Warm |
| Delhi | 38.2 | 0.0 | 0 | 4.7 | Hot |
| Hyderabad | 33.1 | 8.1 | 2 | 4.3 | Hot |

*(Sample output — actual values depend on when the pipeline is run)*

---

## Step 5: How I Would Run This in Production

### Scheduling
I would use **Google Cloud Scheduler** to trigger this pipeline daily at 2:00 AM IST (before the analyst's working day starts). The Cloud Scheduler job would call a **Cloud Run** container that runs `pipeline.py`. This avoids the need for a persistent VM and costs essentially nothing at this data volume.

```
Cloud Scheduler (cron: 0 2 * * * Asia/Kolkata)
    → triggers Cloud Run job
        → runs pipeline.py
            → writes to BigQuery
```

Alternatively, if the team already uses Airflow or Prefect, a single DAG task wrapping this script would work fine. I chose Cloud Run here because it requires zero infrastructure to maintain.

### How I Would Know If It Failed
- Cloud Run captures stdout/stderr — pipeline logs go to **Cloud Logging** automatically
- I would set a **log-based alert** in Cloud Monitoring: if the log string `"Pipeline completed successfully"` does not appear within 30 minutes of the scheduled run time, fire a **PagerDuty / Slack alert**
- BigQuery has a `pipeline_run_date` field on every row — a simple **scheduled query** that checks `MAX(pipeline_run_date) < CURRENT_DATE()` and alerts if true is a cheap, additional safety net
- For a stricter SLA I would add `--dry-run` as a health check in a separate job that runs 10 minutes before the real pipeline, to confirm API connectivity before committing to the full run

### What I Would Change at 10× Data Volume
At current scale (5 cities × 7 days = 35 rows/run), BigQuery is overkill — but that is intentional: it scales to millions of rows without changes to the pipeline.

If we added 50+ cities or pulled hourly data instead of daily:
- Switch the BigQuery table to **date partitioning** on `date` (already structured for this)  
- Change `WRITE_APPEND` to **upsert via MERGE** to make the pipeline idempotent (re-running the same date range should not create duplicates)
- Add **city-level parallelism** using `concurrent.futures.ThreadPoolExecutor` — API calls per city are independent and can be parallelised safely
- Consider batching BigQuery writes rather than one `load_table_from_json` call

---

## Files in This Folder

- `pipeline.py` — Main pipeline script (fetch → transform → load)
- `weather_summary.sql` — 4 SQL queries against the BigQuery table
- `requirements.txt` — Python dependencies
- `README.md` — This file
