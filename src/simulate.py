"""Run 7-day EMS simulation for Lab 3, Variant 3."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from components import Battery, Grid, PVPlant
from economics import irr, npv
from ems_controller import dispatch_hour

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "energy_lab1_v3.sqlite"
OUT_TABLE_DIR = ROOT / "outputs" / "tables"
FIG_DIR = ROOT / "outputs" / "figures"
OUT_TABLE_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

PV_CAPACITY_KW = 60.0
BATTERY_CAPACITY_KWH = 50.0
BATTERY_MAX_POWER_KW = 25.0
AREA_M2 = 600.0
SIM_START = "2025-06-02 00:00:00"
SIM_END = "2025-06-08 23:00:00"


def load_week_data() -> pd.DataFrame:
    """Load hourly load and weather data for the simulation week."""
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT ms.timestamp, ms.consumption_kwh AS load_kwh,
                   w.temperature_c, w.insolation_kw_m2
            FROM measurements ms
            JOIN meters m ON m.meter_id = ms.meter_id AND m.accounting_level = 1
            JOIN weather_data w ON w.object_id = m.object_id AND w.timestamp = ms.timestamp
            WHERE ms.timestamp BETWEEN ? AND ?
            ORDER BY ms.timestamp
            """,
            conn,
            params=(SIM_START, SIM_END),
            parse_dates=["timestamp"],
        )
    if len(df) != 168:
        raise ValueError(f"Expected 168 hours, got {len(df)}")
    return df


def run_simulation() -> pd.DataFrame:
    """Run EMS simulation and return a detailed hourly dataframe."""
    data = load_week_data()
    pv = PVPlant(capacity_kw=PV_CAPACITY_KW)
    battery = Battery(capacity_kwh=BATTERY_CAPACITY_KWH, max_power_kw=BATTERY_MAX_POWER_KW, soc_initial_pct=50)
    grid = Grid(connection_limit_kw=180, export_price_uah_kwh=6.5)

    rows = []
    for row in data.itertuples(index=False):
        pv_kwh = pv.generation_kwh(row.insolation_kw_m2, row.temperature_c)
        dispatch = dispatch_hour(row.load_kwh, pv_kwh, battery, grid, row.timestamp.hour)
        dispatch["timestamp"] = row.timestamp
        dispatch["temperature_c"] = row.temperature_c
        dispatch["insolation_kw_m2"] = row.insolation_kw_m2
        rows.append(dispatch)
    result = pd.DataFrame(rows)
    result = result[["timestamp"] + [c for c in result.columns if c != "timestamp"]]
    result.to_csv(OUT_TABLE_DIR / "ems_simulation_results.csv", index=False, encoding="utf-8-sig")
    return result


def calculate_summary(df: pd.DataFrame) -> dict[str, float | str | None]:
    """Calculate energy and financial KPIs for EMS."""
    baseline_cost = float((df["load_kwh"] * df["import_price_uah_kwh"]).sum())
    actual_cost = float(df["net_cost_uah"].sum())
    weekly_savings = baseline_cost - actual_cost
    annual_savings = weekly_savings * 52

    pv_total = float(df["pv_generation_kwh"].sum())
    load_total = float(df["load_kwh"].sum())
    pv_self_consumed = float(df["pv_to_load_kwh"].sum() + df["pv_to_battery_kwh"].sum())
    battery_discharge = float(df["battery_to_load_kwh"].sum())
    cycles = battery_discharge / BATTERY_CAPACITY_KWH

    capex_pv = PV_CAPACITY_KW * 28_000
    capex_battery = BATTERY_CAPACITY_KWH * 12_000
    capex_total = capex_pv + capex_battery
    annual_om = capex_total * 0.01
    net_annual_cashflow = annual_savings - annual_om
    cashflows = [-capex_total] + [net_annual_cashflow] * 10
    discount_rate = 0.12
    npv_value = npv(discount_rate, cashflows)
    irr_value = irr(cashflows)

    summary = {
        "simulation_period": f"{SIM_START} — {SIM_END}",
        "total_load_kwh": round(load_total, 2),
        "total_pv_generation_kwh": round(pv_total, 2),
        "pv_coverage_pct_direct": round(float(df["pv_to_load_kwh"].sum()) / load_total * 100, 2),
        "pv_self_consumption_pct": round(pv_self_consumed / max(pv_total, 1e-6) * 100, 2),
        "battery_cycles_week": round(cycles, 2),
        "grid_import_kwh": round(float(df["grid_import_kwh"].sum()), 2),
        "grid_export_kwh": round(float(df["grid_export_kwh"].sum()), 2),
        "baseline_cost_uah": round(baseline_cost, 2),
        "actual_net_cost_uah": round(actual_cost, 2),
        "weekly_savings_uah": round(weekly_savings, 2),
        "annual_savings_forecast_uah": round(annual_savings, 2),
        "capex_total_uah": round(capex_total, 2),
        "simple_payback_years": round(capex_total / max(annual_savings, 1e-6), 2),
        "npv_10y_12pct_uah": round(float(npv_value), 2),
        "irr_pct": None if irr_value is None else round(float(irr_value * 100), 2),
    }
    (OUT_TABLE_DIR / "ems_summary_metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def save_plot(path: Path) -> None:
    plt.tight_layout()
    plt.savefig(path, dpi=170)
    plt.close()


def create_figures(df: pd.DataFrame) -> None:
    """Create visualization set for EMS results."""
    ts = pd.to_datetime(df["timestamp"])

    plt.figure(figsize=(12, 5))
    plt.plot(ts, df["load_kwh"], label="Навантаження")
    plt.plot(ts, df["pv_generation_kwh"], label="Генерація СЕС")
    plt.plot(ts, df["grid_import_kwh"], label="Імпорт з мережі")
    plt.title("Енергобаланс за тиждень")
    plt.xlabel("Час")
    plt.ylabel("кВт·год")
    plt.legend()
    save_plot(FIG_DIR / "01_energy_balance.png")

    plt.figure(figsize=(12, 4))
    plt.plot(ts, df["soc_pct"], marker="o", markersize=2)
    plt.axhline(20, linestyle="--", label="SOC min")
    plt.axhline(90, linestyle="--", label="SOC max")
    plt.title("Рівень заряду батареї, SOC")
    plt.xlabel("Час")
    plt.ylabel("SOC, %")
    plt.legend()
    save_plot(FIG_DIR / "02_battery_soc.png")

    plt.figure(figsize=(12, 4))
    plt.bar(ts, df["grid_import_kwh"], label="Імпорт")
    plt.bar(ts, -df["grid_export_kwh"], label="Експорт")
    plt.title("Імпорт та експорт з мережі")
    plt.xlabel("Час")
    plt.ylabel("кВт·год")
    plt.legend()
    save_plot(FIG_DIR / "03_grid_import_export.png")

    by_zone = df.groupby("zone_name").agg(
        baseline_cost=("load_kwh", lambda x: 0.0),
        actual_cost=("net_cost_uah", "sum"),
        load=("load_kwh", "sum"),
        price=("import_price_uah_kwh", "mean"),
    )
    by_zone["baseline_cost"] = by_zone["load"] * by_zone["price"]
    by_zone["savings"] = by_zone["baseline_cost"] - by_zone["actual_cost"]
    by_zone.to_csv(OUT_TABLE_DIR / "savings_by_tariff_zone.csv", encoding="utf-8-sig")
    plt.figure(figsize=(8, 4))
    plt.bar(by_zone.index, by_zone["savings"])
    plt.title("Економія за тарифними зонами")
    plt.xlabel("Тарифна зона")
    plt.ylabel("грн/тиждень")
    save_plot(FIG_DIR / "04_savings_by_tariff_zone.png")

    sources = pd.Series({
        "СЕС → споживання": df["pv_to_load_kwh"].sum(),
        "Батарея → споживання": df["battery_to_load_kwh"].sum(),
        "Мережа → споживання": df["grid_to_load_kwh"].sum(),
    })
    plt.figure(figsize=(7, 7))
    plt.pie(sources.values, labels=sources.index, autopct="%1.1f%%")
    plt.title("Розподіл джерел покриття навантаження")
    save_plot(FIG_DIR / "05_source_distribution.png")

    baseline_hourly_cost = df["load_kwh"] * df["import_price_uah_kwh"]
    actual_hourly_cost = df["net_cost_uah"]
    cumulative_savings = (baseline_hourly_cost - actual_hourly_cost).cumsum()
    plt.figure(figsize=(12, 4))
    plt.plot(ts, cumulative_savings)
    plt.title("Накопичена економія протягом тижня")
    plt.xlabel("Час")
    plt.ylabel("грн")
    save_plot(FIG_DIR / "06_cumulative_savings.png")


def main() -> None:
    df = run_simulation()
    summary = calculate_summary(df)
    create_figures(df)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
