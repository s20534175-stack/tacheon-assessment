Task 2: Pipeline Building — Marketing Weather Signal
What I Built and Why
I built a data pipeline that pulls daily weather data from Open-Meteo for a configurable set of cities, transforms it into an analytics-ready format, and loads it into BigQuery.
Why weather data for a marketing pipeline?
Weather is a genuine marketing signal. Retail, food delivery, outdoor, and FMCG brands routinely see conversion rates and footfall correlate with local weather conditions. A team running campaigns across multiple Indian cities (Chennai, Mumbai, Delhi, Bangalore, Hyderabad) would benefit from a clean, queryable daily weather table that can be joined against ad spend and conversion data.
This choice also connects Task 1 and Task 2 under a single narrative: the Marketing Signal Dashboard (Task 1) could surface weather context alongside channel performance — explaining why a campaign underperformed, not just that it did.
Why Open-Meteo?

Free, no API key, no billing setup
Returns rich hourly JSON (good for demonstrating transformation skills)
Reliable and well-documented
Returns genuine data for Indian cities with good accuracy
- `weather_summary.sql` — 4 SQL queries against the BigQuery table
- `requirements.txt` — Python dependencies
- `README.md` — This file

Pipeline Architecture
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


    How to Run It
1. Install dependencies
pip install -r requirements.txt
2. Set up BigQuery Sandbox
Go to console.cloud.google.com/bigquery. A default project is created automatically with a Google account — no credit card needed.
3. Authenticate
gcloud auth application-default login
4. Run the pipeline
# Default: all 5 cities, last 7 days
python pipeline.py

# Dry run (no BigQuery write — useful for testing)
python pipeline.py --dry-run

# Custom cities
python pipeline.py --cities "Chennai,Mumbai"

# Extend lookback
python pipeline.py --days 14

BigQuery Schema
FieldTypeNotescitySTRINGCity namedateDATEDay of recordtemp_mean_cFLOAT64Daily average temperaturetotal_precipitation_mmFLOAT64Rain/total precipmax_windspeed_kmhFLOAT64Peak windfeels_likeSTRINGDerived — Cold/Mild/Warm/Hotis_rainy_dayBOOLDerived — precip > 2mmweather_marketing_scoreFLOAT64Derived — 0–10 outdoor score

Sample SQL Query Output
From weather_summary.sql — weekly summary by city (actual output from BigQuery, run 30 May 2026, project: tacheon-assessment-497917):
citydaysavg_temp_crainy_daysavg_scoreBangalore725.245.72Hyderabad731.624.45Mumbai731.624.44Chennai733.314.18Delhi734.413.25

Bangalore scores highest (5.72) due to cooler temperatures (25.2°C). Delhi scores lowest (3.25) as the hottest city at 34.4°C — useful signal for outdoor and retail campaign planning.

Step 5: How I Would Run This in Production
Scheduling
I would use Google Cloud Scheduler to trigger this pipeline daily at 2:00 AM IST. The Cloud Scheduler job would call a Cloud Run container that runs pipeline.py. This avoids the need for a persistent VM and costs essentially nothing at this data volume.
How I Would Know If It Failed

Cloud Run captures stdout/stderr — pipeline logs go to Cloud Logging automatically
A log-based alert in Cloud Monitoring fires if "Pipeline completed successfully" does not appear within 30 minutes of scheduled run time
BigQuery has a pipeline_run_date field — a scheduled query that checks MAX(pipeline_run_date) < CURRENT_DATE() alerts if stale

What I Would Change at 10× Data Volume

Switch the BigQuery table to date partitioning on date
Change WRITE_APPEND to upsert via MERGE to make the pipeline idempotent
Add city-level parallelism using concurrent.futures.ThreadPoolExecutor
Consider batching BigQuery writes


Files in This Folder

pipeline.py — Main pipeline script (fetch → transform → load)
weather_summary.sql — SQL queries against the BigQuery table
requirements.txt — Python dependencies
README.md — This file
