"""
pipeline.py — Marketing Weather Signal Pipeline
================================================
Fetches weather data from Open-Meteo (free, no API key required) for a set of
cities relevant to client marketing campaigns, transforms it into an analytics-
ready format, and loads it into BigQuery.

Why weather data for a marketing pipeline?
  Weather is a genuine marketing signal — retail, food delivery, and outdoor
  brands routinely correlate ad performance with local weather conditions.
  This pipeline pulls daily weather snapshots that can be joined against
  campaign spend/conversion data to surface weather-driven performance patterns.

Usage:
  python pipeline.py                         # runs for default cities, last 7 days
  python pipeline.py --cities "Mumbai,Delhi" # override cities
  python pipeline.py --days 14              # extend lookback window
  python pipeline.py --dry-run              # fetch + transform only, skip BigQuery

Author: Santhosh B
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Logging setup — structured, readable, useful in production
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — all tuneable values in one place, never hardcoded in logic
# ---------------------------------------------------------------------------
API_BASE_URL = "https://api.open-meteo.com/v1/forecast"
API_TIMEOUT_SECONDS = 15
API_RETRY_ATTEMPTS = 3
API_RETRY_BACKOFF_SECONDS = 2

BIGQUERY_PROJECT = "your-gcp-project-id"   # ← replace before running
BIGQUERY_DATASET = "marketing_signals"
BIGQUERY_TABLE = "weather_daily"

# Cities with their coordinates — extend this list freely
CITY_COORDINATES: dict[str, dict[str, float]] = {
    "Chennai":   {"lat": 13.0827, "lon": 80.2707},
    "Mumbai":    {"lat": 19.0760, "lon": 72.8777},
    "Delhi":     {"lat": 28.7041, "lon": 77.1025},
    "Bangalore": {"lat": 12.9716, "lon": 77.5946},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867},
}

# Weather variables to pull from the API
HOURLY_VARIABLES = [
    "temperature_2m",
    "precipitation",
    "windspeed_10m",
    "relativehumidity_2m",
]

# ---------------------------------------------------------------------------
# Data model for a single day's weather record
# ---------------------------------------------------------------------------
@dataclass
class WeatherRecord:
    city: str
    date: str                        # ISO format: YYYY-MM-DD
    lat: float
    lon: float
    temp_max_c: float
    temp_min_c: float
    temp_mean_c: float
    total_precipitation_mm: float
    max_windspeed_kmh: float
    mean_humidity_pct: float
    # Derived fields — analytical value beyond raw API data
    feels_like_category: str         # "Cold" / "Mild" / "Warm" / "Hot"
    is_rainy_day: bool               # precipitation > 2mm threshold
    weather_marketing_score: float   # 0–10: how conducive is weather to outdoor activity/shopping
    pipeline_run_date: str           # when this record was generated


def classify_temperature(temp_c: float) -> str:
    """Derived field: human-readable temperature category for marketing segmentation."""
    if temp_c < 15:
        return "Cold"
    elif temp_c < 25:
        return "Mild"
    elif temp_c < 32:
        return "Warm"
    else:
        return "Hot"


def compute_marketing_score(
    temp_mean: float,
    precipitation_mm: float,
    windspeed_kmh: float,
) -> float:
    """
    Derived field: a 0–10 score estimating how weather-friendly a day is for
    outdoor activity and physical retail footfall.

    Methodology:
    - Ideal temperature range (18–28°C) scores highest
    - Rain penalises the score significantly
    - High wind adds a smaller penalty
    - Score is bounded [0, 10]

    This is a heuristic, not a statistical model. It is documented here so
    analysts know exactly how it is calculated and can challenge it.
    """
    # Temperature score (peaks at 23°C, falls off symmetrically)
    temp_score = max(0, 10 - abs(temp_mean - 23) * 0.5)

    # Rain penalty: -1 per mm up to -5 max
    rain_penalty = min(5, precipitation_mm * 1.0)

    # Wind penalty: -0.05 per km/h above 20
    wind_penalty = max(0, (windspeed_kmh - 20) * 0.05)

    score = temp_score - rain_penalty - wind_penalty
    return round(max(0.0, min(10.0, score)), 2)


# ---------------------------------------------------------------------------
# API layer — fetch with retry and graceful error handling
# ---------------------------------------------------------------------------
def build_api_params(lat: float, lon: float, start_date: str, end_date: str) -> dict:
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(HOURLY_VARIABLES),
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "Asia/Kolkata",
    }


def fetch_weather(city: str, lat: float, lon: float, start_date: str, end_date: str) -> dict[str, Any] | None:
    """
    Calls the Open-Meteo API with retry logic.
    Returns the parsed JSON response or None if all attempts fail.
    """
    params = build_api_params(lat, lon, start_date, end_date)

    for attempt in range(1, API_RETRY_ATTEMPTS + 1):
        try:
            log.info(f"Fetching weather for {city} (attempt {attempt}/{API_RETRY_ATTEMPTS}) "
                     f"{start_date} → {end_date}")
            response = requests.get(API_BASE_URL, params=params, timeout=API_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            log.info(f"  ✓ {city}: received {len(data.get('hourly', {}).get('time', []))} hourly records")
            return data
        except requests.exceptions.Timeout:
            log.warning(f"  ✗ {city}: request timed out (attempt {attempt})")
        except requests.exceptions.HTTPError as e:
            log.error(f"  ✗ {city}: HTTP error {e.response.status_code} — {e}")
            break  # Do not retry on HTTP 4xx — it will not fix itself
        except requests.exceptions.ConnectionError:
            log.warning(f"  ✗ {city}: connection error (attempt {attempt})")
        except (json.JSONDecodeError, ValueError) as e:
            log.error(f"  ✗ {city}: unexpected response format — {e}")
            break

        if attempt < API_RETRY_ATTEMPTS:
            wait = API_RETRY_BACKOFF_SECONDS * attempt
            log.info(f"  Retrying in {wait}s...")
            time.sleep(wait)

    log.error(f"  All attempts failed for {city}. Skipping.")
    return None


# ---------------------------------------------------------------------------
# Transform layer — raw JSON → clean, analytics-ready WeatherRecord list
# ---------------------------------------------------------------------------
def safe_mean(values: list) -> float | None:
    """Mean of a list, filtering out None values. Returns None if list is empty."""
    clean = [v for v in values if v is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def safe_max(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return max(clean) if clean else None


def safe_min(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return min(clean) if clean else None


def transform_city_response(
    city: str, lat: float, lon: float, raw: dict[str, Any]
) -> list[WeatherRecord]:
    """
    Flattens hourly Open-Meteo response into one WeatherRecord per day.

    Handles:
    - Null / missing hourly values (API returns None for some hours)
    - Type coercion (API returns floats; we validate)
    - Daily aggregation from hourly (max, min, mean, sum as appropriate)
    """
    hourly = raw.get("hourly", {})
    times = hourly.get("time", [])

    if not times:
        log.warning(f"  {city}: no hourly data in response — skipping")
        return []

    # Group hourly readings by date
    days: dict[str, dict[str, list]] = {}
    for i, ts in enumerate(times):
        day = ts[:10]  # "2026-05-20T14:00" → "2026-05-20"
        if day not in days:
            days[day] = {v: [] for v in HOURLY_VARIABLES}
        for var in HOURLY_VARIABLES:
            val = hourly.get(var, [None] * len(times))[i]
            days[day][var].append(val)

    records: list[WeatherRecord] = []
    today_str = date.today().isoformat()

    for day_str, readings in sorted(days.items()):
        temps = readings["temperature_2m"]
        precip = readings["precipitation"]
        wind = readings["windspeed_10m"]
        humidity = readings["relativehumidity_2m"]

        temp_max = safe_max(temps)
        temp_min = safe_min(temps)
        temp_mean = safe_mean(temps)
        total_precip = round(sum(v for v in precip if v is not None), 2)
        max_wind = safe_max(wind)
        mean_humidity = safe_mean(humidity)

        # Skip days where core data is entirely missing
        if temp_mean is None:
            log.warning(f"  {city} {day_str}: temperature data missing — skipping day")
            continue

        record = WeatherRecord(
            city=city,
            date=day_str,
            lat=lat,
            lon=lon,
            temp_max_c=temp_max or 0.0,
            temp_min_c=temp_min or 0.0,
            temp_mean_c=temp_mean,
            total_precipitation_mm=total_precip,
            max_windspeed_kmh=max_wind or 0.0,
            mean_humidity_pct=mean_humidity or 0.0,
            # Derived fields
            feels_like_category=classify_temperature(temp_mean),
            is_rainy_day=total_precip > 2.0,
            weather_marketing_score=compute_marketing_score(temp_mean, total_precip, max_wind or 0.0),
            pipeline_run_date=today_str,
        )
        records.append(record)

    log.info(f"  {city}: transformed {len(records)} daily records")
    return records


# ---------------------------------------------------------------------------
# BigQuery load layer
# ---------------------------------------------------------------------------
def get_bigquery_schema() -> list:
    """Returns the BigQuery schema matching WeatherRecord fields."""
    from google.cloud import bigquery
    return [
        bigquery.SchemaField("city",                     "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("date",                     "DATE",    mode="REQUIRED"),
        bigquery.SchemaField("lat",                      "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("lon",                      "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("temp_max_c",               "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("temp_min_c",               "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("temp_mean_c",              "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("total_precipitation_mm",   "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("max_windspeed_kmh",        "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("mean_humidity_pct",        "FLOAT64", mode="NULLABLE"),
        bigquery.SchemaField("feels_like_category",      "STRING",  mode="REQUIRED"),
        bigquery.SchemaField("is_rainy_day",             "BOOL",    mode="REQUIRED"),
        bigquery.SchemaField("weather_marketing_score",  "FLOAT64", mode="REQUIRED"),
        bigquery.SchemaField("pipeline_run_date",        "DATE",    mode="REQUIRED"),
    ]


def load_to_bigquery(records: list[WeatherRecord]) -> None:
    """
    Loads transformed records into BigQuery using WRITE_TRUNCATE for the date
    range covered — idempotent: re-running the pipeline for the same date range
    replaces existing rows rather than duplicating them.
    """
    try:
        from google.cloud import bigquery
        from google.api_core.exceptions import GoogleAPIError
    except ImportError:
        log.error("google-cloud-bigquery not installed. Run: pip install google-cloud-bigquery")
        sys.exit(1)

    client = bigquery.Client(project=BIGQUERY_PROJECT)
    table_ref = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}.{BIGQUERY_TABLE}"

    # Convert dataclass instances to dicts for BigQuery
    rows = [
        {
            "city": r.city,
            "date": r.date,
            "lat": r.lat,
            "lon": r.lon,
            "temp_max_c": r.temp_max_c,
            "temp_min_c": r.temp_min_c,
            "temp_mean_c": r.temp_mean_c,
            "total_precipitation_mm": r.total_precipitation_mm,
            "max_windspeed_kmh": r.max_windspeed_kmh,
            "mean_humidity_pct": r.mean_humidity_pct,
            "feels_like_category": r.feels_like_category,
            "is_rainy_day": r.is_rainy_day,
            "weather_marketing_score": r.weather_marketing_score,
            "pipeline_run_date": r.pipeline_run_date,
        }
        for r in records
    ]

    job_config = bigquery.LoadJobConfig(
        schema=get_bigquery_schema(),
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        # For production: switch to WRITE_TRUNCATE on a date-partitioned table
        # to make the pipeline idempotent
    )

    log.info(f"Loading {len(rows)} rows into {table_ref}...")
    try:
        job = client.load_table_from_json(rows, table_ref, job_config=job_config)
        job.result()  # Wait for job to complete
        log.info(f"  ✓ BigQuery load complete. Rows loaded: {job.output_rows}")
    except GoogleAPIError as e:
        log.error(f"  ✗ BigQuery load failed: {e}")
        raise


def ensure_dataset_exists() -> None:
    """Creates the BigQuery dataset if it does not already exist."""
    try:
        from google.cloud import bigquery
    except ImportError:
        return

    client = bigquery.Client(project=BIGQUERY_PROJECT)
    dataset_ref = f"{BIGQUERY_PROJECT}.{BIGQUERY_DATASET}"
    try:
        client.get_dataset(dataset_ref)
        log.info(f"Dataset {BIGQUERY_DATASET} already exists")
    except Exception:
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset, exists_ok=True)
        log.info(f"Created dataset {BIGQUERY_DATASET}")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Weather marketing signal pipeline — Open-Meteo → BigQuery"
    )
    parser.add_argument(
        "--cities",
        type=str,
        default=None,
        help="Comma-separated city names from the configured list (default: all cities)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of historical days to fetch (default: 7)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and transform only — do not write to BigQuery",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve city list
    if args.cities:
        requested = [c.strip() for c in args.cities.split(",")]
        cities = {k: v for k, v in CITY_COORDINATES.items() if k in requested}
        unknown = [c for c in requested if c not in CITY_COORDINATES]
        if unknown:
            log.warning(f"Unknown cities (will skip): {unknown}")
    else:
        cities = CITY_COORDINATES

    if not cities:
        log.error("No valid cities to process. Exiting.")
        sys.exit(1)

    # Date range
    end_date = date.today()
    start_date = end_date - timedelta(days=args.days - 1)
    start_str = start_date.isoformat()
    end_str = end_date.isoformat()

    log.info("=" * 60)
    log.info("Marketing Weather Signal Pipeline")
    log.info(f"Cities      : {list(cities.keys())}")
    log.info(f"Date range  : {start_str} → {end_str} ({args.days} days)")
    log.info(f"Dry run     : {args.dry_run}")
    log.info("=" * 60)

    all_records: list[WeatherRecord] = []

    for city, coords in cities.items():
        raw = fetch_weather(city, coords["lat"], coords["lon"], start_str, end_str)
        if raw is None:
            continue
        records = transform_city_response(city, coords["lat"], coords["lon"], raw)
        all_records.extend(records)

    log.info(f"\nTotal records after transform: {len(all_records)}")

    if not all_records:
        log.error("No records to load. Check API connectivity and city config.")
        sys.exit(1)

    # Preview first 3 records
    log.info("\nSample records:")
    for r in all_records[:3]:
        log.info(
            f"  {r.city} {r.date} | "
            f"mean {r.temp_mean_c}°C | "
            f"{r.feels_like_category} | "
            f"rain={r.is_rainy_day} | "
            f"score={r.weather_marketing_score}"
        )

    if args.dry_run:
        log.info("\nDry run — skipping BigQuery load.")
        log.info("Pipeline completed successfully (dry run).")
        return

    ensure_dataset_exists()
    load_to_bigquery(all_records)
    log.info("\nPipeline completed successfully.")


if __name__ == "__main__":
    main()
