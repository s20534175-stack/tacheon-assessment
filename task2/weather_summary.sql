-- weather_summary.sql
-- Marketing Weather Signal — BigQuery Summary Queries
-- Run these after pipeline.py has loaded data into the weather_daily table.
-- Replace `your-gcp-project-id` with your actual project ID.

-- ============================================================
-- Query 1: Weekly weather summary per city
-- A top-level view of conditions across cities for the last 7 days.
-- Useful for: understanding which markets had unfavourable conditions
-- that might explain dips in campaign performance.
-- ============================================================

SELECT
  city,
  MIN(date)                                        AS week_start,
  MAX(date)                                        AS week_end,
  ROUND(AVG(temp_mean_c), 1)                       AS avg_temp_c,
  ROUND(MAX(temp_max_c), 1)                        AS peak_temp_c,
  ROUND(SUM(total_precipitation_mm), 1)            AS total_rain_mm,
  COUNTIF(is_rainy_day)                            AS rainy_days,
  ROUND(AVG(weather_marketing_score), 2)           AS avg_marketing_score,
  -- Dominant temperature category for the week
  (
    SELECT feels_like_category
    FROM `your-gcp-project-id.marketing_signals.weather_daily` sub
    WHERE sub.city = main.city
      AND sub.date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
    GROUP BY feels_like_category
    ORDER BY COUNT(*) DESC
    LIMIT 1
  )                                                AS dominant_category
FROM `your-gcp-project-id.marketing_signals.weather_daily` main
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY city
ORDER BY avg_marketing_score DESC;


-- ============================================================
-- Query 2: Best and worst marketing weather days by city
-- Surfaces the top-3 and bottom-3 scoring days per city.
-- Useful for: correlating ad performance peaks/troughs with weather.
-- ============================================================

WITH ranked AS (
  SELECT
    city,
    date,
    temp_mean_c,
    feels_like_category,
    is_rainy_day,
    total_precipitation_mm,
    weather_marketing_score,
    ROW_NUMBER() OVER (PARTITION BY city ORDER BY weather_marketing_score DESC) AS rank_best,
    ROW_NUMBER() OVER (PARTITION BY city ORDER BY weather_marketing_score ASC)  AS rank_worst
  FROM `your-gcp-project-id.marketing_signals.weather_daily`
)
SELECT
  city,
  date,
  temp_mean_c,
  feels_like_category,
  is_rainy_day,
  weather_marketing_score,
  CASE WHEN rank_best <= 3 THEN 'Best' ELSE 'Worst' END AS day_type
FROM ranked
WHERE rank_best <= 3 OR rank_worst <= 3
ORDER BY city, day_type, weather_marketing_score DESC;


-- ============================================================
-- Query 3: Rainy day impact summary
-- Compares average marketing score on rainy vs non-rainy days.
-- Useful for: quantifying the weather drag on outdoor-brand campaigns.
-- ============================================================

SELECT
  city,
  is_rainy_day,
  COUNT(*)                                    AS day_count,
  ROUND(AVG(temp_mean_c), 1)                  AS avg_temp_c,
  ROUND(AVG(total_precipitation_mm), 1)       AS avg_rain_mm,
  ROUND(AVG(weather_marketing_score), 2)      AS avg_marketing_score
FROM `your-gcp-project-id.marketing_signals.weather_daily`
GROUP BY city, is_rainy_day
ORDER BY city, is_rainy_day;


-- ============================================================
-- Query 4: Time-based trend — marketing score over time per city
-- Shows whether conditions are improving or worsening.
-- Useful for: forward-looking budget allocation decisions.
-- ============================================================

SELECT
  city,
  date,
  temp_mean_c,
  feels_like_category,
  weather_marketing_score,
  -- 3-day rolling average score
  ROUND(
    AVG(weather_marketing_score) OVER (
      PARTITION BY city
      ORDER BY date
      ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ),
    2
  ) AS rolling_3d_avg_score
FROM `your-gcp-project-id.marketing_signals.weather_daily`
ORDER BY city, date;
