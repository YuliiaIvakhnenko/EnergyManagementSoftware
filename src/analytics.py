"""Run analytical SQL queries for Lab 1."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from config import CONFIG
from database import DB_PATH, connect

ROOT_DIR = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT_DIR / "outputs" / "analytics_results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

QUERIES: dict[str, str] = {
    "daily_consumption": """
        SELECT DATE(timestamp) AS day, ROUND(SUM(consumption_kwh), 2) AS consumption_kwh
        FROM v_level1_hourly
        GROUP BY DATE(timestamp)
        ORDER BY day;
    """,
    "weekly_consumption": """
        SELECT STRFTIME('%Y-W%W', timestamp) AS week, ROUND(SUM(consumption_kwh), 2) AS consumption_kwh
        FROM v_level1_hourly
        GROUP BY STRFTIME('%Y-W%W', timestamp)
        ORDER BY week;
    """,
    "monthly_consumption": """
        SELECT STRFTIME('%Y-%m', timestamp) AS month, ROUND(SUM(consumption_kwh), 2) AS consumption_kwh
        FROM v_level1_hourly
        GROUP BY STRFTIME('%Y-%m', timestamp)
        ORDER BY month;
    """,
    "consumption_by_tariff_zone": """
        SELECT ts.zone_name,
               ROUND(SUM(ms.consumption_kwh), 2) AS consumption_kwh,
               ROUND(SUM(ms.consumption_kwh * ts.import_price_uah_kwh), 2) AS cost_uah
        FROM measurements ms
        JOIN meters m ON m.meter_id = ms.meter_id AND m.accounting_level = 1
        JOIN tariff_schedule ts ON ts.hour = CAST(STRFTIME('%H', ms.timestamp) AS INTEGER)
        GROUP BY ts.zone_name
        ORDER BY cost_uah DESC;
    """,
    "specific_indicators": """
        SELECT period_start, period_end, consumption_kwh, specific_kwh_m2, baseline_kwh, deviation_pct
        FROM energy_efficiency_kpis
        ORDER BY period_start;
    """,
    "baseline_comparison_monthly": """
        SELECT period_start,
               ROUND(consumption_kwh - baseline_kwh, 2) AS delta_kwh,
               deviation_pct
        FROM energy_efficiency_kpis
        ORDER BY period_start;
    """,
    "anomalies_gt_20_pct": """
        WITH hourly_avg AS (
            SELECT STRFTIME('%w', timestamp) AS weekday,
                   STRFTIME('%H', timestamp) AS hour,
                   AVG(consumption_kwh) AS avg_kwh
            FROM v_level1_hourly
            GROUP BY weekday, hour
        )
        SELECT l.timestamp,
               ROUND(l.consumption_kwh, 2) AS consumption_kwh,
               ROUND(a.avg_kwh, 2) AS expected_kwh,
               ROUND((l.consumption_kwh - a.avg_kwh) / a.avg_kwh * 100, 1) AS deviation_pct
        FROM v_level1_hourly l
        JOIN hourly_avg a
          ON a.weekday = STRFTIME('%w', l.timestamp)
         AND a.hour = STRFTIME('%H', l.timestamp)
        WHERE ABS(l.consumption_kwh - a.avg_kwh) / a.avg_kwh > 0.20
        ORDER BY ABS(l.consumption_kwh - a.avg_kwh) / a.avg_kwh DESC
        LIMIT 50;
    """,
}


def run_queries(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:
    """Execute all analytical queries and return their dataframes."""
    result = {}
    for name, sql in QUERIES.items():
        df = pd.read_sql_query(sql, conn)
        df.to_csv(OUT_DIR / f"{name}.csv", index=False, encoding="utf-8-sig")
        result[name] = df
    return result


def write_summary(result: dict[str, pd.DataFrame]) -> None:
    """Write a compact text summary for the report."""
    monthly = result["monthly_consumption"]
    tariffs = result["consumption_by_tariff_zone"]
    anomalies = result["anomalies_gt_20_pct"]
    annual_kwh = monthly["consumption_kwh"].sum()
    annual_cost = tariffs["cost_uah"].sum()
    specific = annual_kwh / CONFIG.area_m2
    summary = [
        "ЛР1. Варіант 3 — Лабораторія",
        f"Річне споживання головного лічильника: {annual_kwh:,.2f} кВт·год".replace(',', ' '),
        f"Орієнтовна річна вартість за 3-зонним тарифом: {annual_cost:,.2f} грн".replace(',', ' '),
        f"Питомий показник: {specific:.2f} кВт·год/м²·рік",
        f"Кількість аномальних годин у топ-вибірці (>20%): {len(anomalies)}",
        "Найбільша тарифна складова за вартістю: " + str(tariffs.iloc[0]["zone_name"]),
    ]
    (OUT_DIR / "summary.txt").write_text("\n".join(summary), encoding="utf-8")


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}. Run generate_data.py first.")
    with connect(DB_PATH) as conn:
        result = run_queries(conn)
    write_summary(result)
    print(f"Analytics written to {OUT_DIR}")


if __name__ == "__main__":
    main()
