-- 1. Daily consumption for the main meter
SELECT DATE(timestamp) AS day, ROUND(SUM(consumption_kwh), 2) AS consumption_kwh
FROM v_level1_hourly
GROUP BY DATE(timestamp)
ORDER BY day;

-- 2. Weekly consumption for the main meter
SELECT STRFTIME('%Y-W%W', timestamp) AS week, ROUND(SUM(consumption_kwh), 2) AS consumption_kwh
FROM v_level1_hourly
GROUP BY STRFTIME('%Y-W%W', timestamp)
ORDER BY week;

-- 3. Monthly consumption for the main meter
SELECT STRFTIME('%Y-%m', timestamp) AS month, ROUND(SUM(consumption_kwh), 2) AS consumption_kwh
FROM v_level1_hourly
GROUP BY STRFTIME('%Y-%m', timestamp)
ORDER BY month;

-- 4. Consumption by tariff zone
SELECT ts.zone_name, ROUND(SUM(ms.consumption_kwh), 2) AS consumption_kwh,
       ROUND(SUM(ms.consumption_kwh * ts.import_price_uah_kwh), 2) AS cost_uah
FROM measurements ms
JOIN meters m ON m.meter_id = ms.meter_id AND m.accounting_level = 1
JOIN tariff_schedule ts ON ts.hour = CAST(STRFTIME('%H', ms.timestamp) AS INTEGER)
GROUP BY ts.zone_name
ORDER BY cost_uah DESC;

-- 5. Specific indicators by month
SELECT period_start, consumption_kwh, specific_kwh_m2, baseline_kwh, deviation_pct
FROM energy_efficiency_kpis
ORDER BY period_start;

-- 6. Anomalies: deviations greater than 20% from average for same hour of week
WITH hourly_avg AS (
    SELECT STRFTIME('%w', timestamp) AS weekday, STRFTIME('%H', timestamp) AS hour,
           AVG(consumption_kwh) AS avg_kwh
    FROM v_level1_hourly
    GROUP BY weekday, hour
)
SELECT l.timestamp, ROUND(l.consumption_kwh, 2) AS consumption_kwh,
       ROUND(a.avg_kwh, 2) AS expected_kwh,
       ROUND((l.consumption_kwh - a.avg_kwh) / a.avg_kwh * 100, 1) AS deviation_pct
FROM v_level1_hourly l
JOIN hourly_avg a ON a.weekday = STRFTIME('%w', l.timestamp) AND a.hour = STRFTIME('%H', l.timestamp)
WHERE ABS(l.consumption_kwh - a.avg_kwh) / a.avg_kwh > 0.20
ORDER BY ABS(l.consumption_kwh - a.avg_kwh) / a.avg_kwh DESC
LIMIT 50;
