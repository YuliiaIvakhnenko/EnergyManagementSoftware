"""Generate realistic hourly test data for Variant 3."""
from __future__ import annotations

import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

from config import CONFIG, METERS, tariff_for_hour
from database import DB_PATH, connect, initialize_database


def generate_weather(timestamps: pd.DatetimeIndex, rng: np.random.Generator) -> pd.DataFrame:
    """Generate synthetic Kyiv-like hourly weather for 2025."""
    doy = timestamps.dayofyear.to_numpy()
    hour = timestamps.hour.to_numpy()

    annual = 9.0 + 13.5 * np.sin(2 * np.pi * (doy - 105) / 365.0)
    daily = 3.8 * np.sin(2 * np.pi * (hour - 8) / 24.0)
    noise = rng.normal(0, 2.2, len(timestamps))
    temperature = annual + daily + noise

    daylight = np.maximum(0, np.sin(np.pi * (hour - 6) / 12.0))
    seasonal_solar = np.clip(0.35 + 0.65 * np.sin(2 * np.pi * (doy - 80) / 365.0), 0.12, 1.0)
    cloud_factor = np.clip(rng.normal(0.82, 0.18, len(timestamps)), 0.25, 1.05)
    insolation = np.clip(daylight * seasonal_solar * cloud_factor, 0, 1.05)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "temperature_c": temperature.round(2),
            "insolation_kw_m2": insolation.round(3),
            "hdd_18": np.maximum(18 - temperature, 0).round(2),
            "cdd_22": np.maximum(temperature - 22, 0).round(2),
        }
    )


def generate_main_load(weather: pd.DataFrame, rng: np.random.Generator) -> pd.Series:
    """Generate the main meter load profile with seasonality and operating schedule."""
    ts = pd.to_datetime(weather["timestamp"])
    hour = ts.dt.hour.to_numpy()
    dow = ts.dt.dayofweek.to_numpy()
    doy = ts.dt.dayofyear.to_numpy()
    temp = weather["temperature_c"].to_numpy()

    operating = ((hour >= CONFIG.work_start_hour) & (hour < CONFIG.work_end_hour)).astype(float)
    workday = (dow < 5).astype(float)

    hour_factor = np.where(operating == 1, 1.0, 0.74)
    hour_factor += np.where(((hour >= 9) & (hour < 12)) | ((hour >= 15) & (hour < 19)), 0.12, 0.0)
    hour_factor -= np.where((hour >= 0) & (hour < 5), 0.05, 0.0)

    weekend_factor = np.where(workday == 1, 1.0, 0.88)
    seasonal_lab_factor = 1.0 + 0.06 * np.cos(2 * np.pi * (doy - 20) / 365.0)
    hvac_effect = 0.17 * np.maximum(18 - temp, 0) / 18 + 0.22 * np.maximum(temp - 22, 0) / 12
    random_factor = rng.normal(1.0, 0.055, len(weather))

    load = CONFIG.base_load_kw * hour_factor * weekend_factor * seasonal_lab_factor * (1 + hvac_effect) * random_factor

    # Planned calibration to the variant range.
    load = np.clip(load, CONFIG.min_load_kw, CONFIG.max_load_kw)

    # A few controlled anomalies for the anomaly-detection task.
    anomaly_idx = rng.choice(np.arange(len(load)), size=22, replace=False)
    load[anomaly_idx] *= rng.uniform(1.22, 1.42, size=len(anomaly_idx))
    load = np.clip(load, CONFIG.min_load_kw * 0.75, CONFIG.max_load_kw * 1.45)
    return pd.Series(load.round(3), index=weather.index, name="main_consumption_kwh")


def generate_baseline(main_load: pd.Series, weather: pd.DataFrame) -> pd.Series:
    """Create a smooth weather-normalized baseline for comparison."""
    temp = weather["temperature_c"].to_numpy()
    ts = pd.to_datetime(weather["timestamp"])
    operating = ((ts.dt.hour >= CONFIG.work_start_hour) & (ts.dt.hour < CONFIG.work_end_hour)).astype(float).to_numpy()
    baseline = CONFIG.base_load_kw * np.where(operating == 1, 1.03, 0.78)
    baseline *= 1 + 0.10 * np.maximum(18 - temp, 0) / 18 + 0.13 * np.maximum(temp - 22, 0) / 12
    baseline = pd.Series(np.clip(baseline, CONFIG.min_load_kw, CONFIG.max_load_kw).round(3), index=main_load.index)
    return baseline


def insert_static_data(conn: sqlite3.Connection) -> int:
    """Insert object, meters and tariff schedule. Return object_id."""
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO energy_objects
            (name, object_type, city, area_m2, installed_power_kw, work_start_hour, work_end_hour)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            CONFIG.object_name,
            CONFIG.object_type,
            CONFIG.city,
            CONFIG.area_m2,
            CONFIG.installed_power_kw,
            CONFIG.work_start_hour,
            CONFIG.work_end_hour,
        ),
    )
    object_id = int(cur.lastrowid)

    for meter in METERS:
        cur.execute(
            """
            INSERT INTO meters
                (object_id, code, name, meter_type, location, accounting_level, share_of_main_load)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                object_id,
                meter["code"],
                meter["name"],
                meter["meter_type"],
                meter["location"],
                meter["level"],
                meter["share"],
            ),
        )

    for hour in range(24):
        zone, price = tariff_for_hour(hour)
        cur.execute(
            """
            INSERT INTO tariff_schedule
                (tariff_type, hour, zone_name, import_price_uah_kwh, export_price_uah_kwh)
            VALUES (?, ?, ?, ?, ?)
            """,
            (CONFIG.tariff_type, hour, zone, price, CONFIG.export_price_uah_kwh),
        )

    conn.commit()
    return object_id


def insert_time_series(
    conn: sqlite3.Connection,
    object_id: int,
    weather: pd.DataFrame,
    main_load: pd.Series,
    baseline: pd.Series,
    rng: np.random.Generator,
) -> None:
    """Insert weather, baseline and measurements."""
    weather_rows = [
        (
            object_id,
            row.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            float(row.temperature_c),
            float(row.insolation_kw_m2),
            float(row.hdd_18),
            float(row.cdd_22),
        )
        for row in weather.itertuples(index=False)
    ]
    conn.executemany(
        """
        INSERT INTO weather_data
            (object_id, timestamp, temperature_c, insolation_kw_m2, hdd_18, cdd_22)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        weather_rows,
    )

    baseline_rows = [
        (object_id, ts.strftime("%Y-%m-%d %H:%M:%S"), float(value))
        for ts, value in zip(weather["timestamp"], baseline)
    ]
    conn.executemany(
        "INSERT INTO baselines (object_id, timestamp, baseline_kwh) VALUES (?, ?, ?)",
        baseline_rows,
    )

    meter_map = {row[1]: row[0] for row in conn.execute("SELECT meter_id, code FROM meters")}
    measurement_rows = []
    for meter in METERS:
        meter_id = meter_map[meter["code"]]
        if meter["level"] == 1:
            values = main_load.to_numpy()
        else:
            local_noise = rng.normal(1.0, 0.045, len(main_load))
            values = np.maximum(main_load.to_numpy() * meter["share"] * local_noise, 0)
        for ts, value in zip(weather["timestamp"], values):
            quality = "ANOMALY" if value > CONFIG.max_load_kw * (1.18 if meter["level"] == 1 else meter["share"] * 1.18) else "OK"
            measurement_rows.append((meter_id, ts.strftime("%Y-%m-%d %H:%M:%S"), round(float(value), 3), quality))

    conn.executemany(
        """
        INSERT INTO measurements (meter_id, timestamp, consumption_kwh, quality_flag)
        VALUES (?, ?, ?, ?)
        """,
        measurement_rows,
    )
    conn.commit()


def create_kpis(conn: sqlite3.Connection, object_id: int) -> None:
    """Create monthly energy-efficiency KPIs for the main meter."""
    df = pd.read_sql_query(
        """
        SELECT ms.timestamp, ms.consumption_kwh, b.baseline_kwh
        FROM measurements ms
        JOIN meters m ON m.meter_id = ms.meter_id AND m.accounting_level = 1
        JOIN baselines b ON b.object_id = m.object_id AND b.timestamp = ms.timestamp
        WHERE m.object_id = ?
        ORDER BY ms.timestamp
        """,
        conn,
        params=(object_id,),
        parse_dates=["timestamp"],
    )
    monthly = df.set_index("timestamp").resample("MS").agg({"consumption_kwh": "sum", "baseline_kwh": "sum"})
    rows = []
    for start, row in monthly.iterrows():
        end = start + pd.offsets.MonthEnd(1)
        deviation = (row.consumption_kwh - row.baseline_kwh) / row.baseline_kwh * 100
        rows.append(
            (
                object_id,
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d"),
                round(float(row.consumption_kwh), 2),
                round(float(row.consumption_kwh / CONFIG.area_m2), 3),
                round(float(row.baseline_kwh), 2),
                round(float(deviation), 2),
            )
        )
    conn.executemany(
        """
        INSERT INTO energy_efficiency_kpis
            (object_id, period_start, period_end, consumption_kwh, specific_kwh_m2, baseline_kwh, deviation_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()


def write_schema_diagram() -> None:
    """Write Mermaid and PNG ER diagram artifacts."""
    root = Path(__file__).resolve().parents[1]
    diagram_dir = root / "outputs" / "diagrams"
    diagram_dir.mkdir(parents=True, exist_ok=True)
    (diagram_dir / "schema.mmd").write_text(
        """erDiagram
    ENERGY_OBJECTS ||--o{ METERS : has
    ENERGY_OBJECTS ||--o{ WEATHER_DATA : has
    ENERGY_OBJECTS ||--o{ BASELINES : has
    ENERGY_OBJECTS ||--o{ ENERGY_EFFICIENCY_KPIS : has
    METERS ||--o{ MEASUREMENTS : records
    TARIFF_SCHEDULE ||--o{ MEASUREMENTS : applies_by_hour

    ENERGY_OBJECTS {
        int object_id PK
        text name
        text object_type
        real area_m2
        real installed_power_kw
    }
    METERS {
        int meter_id PK
        int object_id FK
        text code
        int accounting_level
        real share_of_main_load
    }
    MEASUREMENTS {
        int measurement_id PK
        int meter_id FK
        text timestamp
        real consumption_kwh
        text quality_flag
    }
    WEATHER_DATA {
        int weather_id PK
        text timestamp
        real temperature_c
        real insolation_kw_m2
        real hdd_18
        real cdd_22
    }
    TARIFF_SCHEDULE {
        int tariff_id PK
        int hour
        text zone_name
        real import_price_uah_kwh
    }
    BASELINES {
        int baseline_id PK
        text timestamp
        real baseline_kwh
    }
""",
        encoding="utf-8",
    )

    # Lightweight PNG diagram without external Graphviz dependency.
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    fig, ax = plt.subplots(figsize=(11, 7))
    ax.axis("off")
    boxes = {
        "energy_objects": (0.08, 0.62, "energy_objects\nobject_id, name, area, power"),
        "meters": (0.40, 0.62, "meters\nmeter_id, object_id, level"),
        "measurements": (0.72, 0.62, "measurements\nmeter_id, timestamp, kWh"),
        "weather": (0.08, 0.25, "weather_data\ntemperature, insolation, HDD/CDD"),
        "baseline": (0.40, 0.25, "baselines / KPIs\nbaseline, kWh/m², deviation"),
        "tariff": (0.72, 0.25, "tariff_schedule\nhour, zone, price"),
    }
    for x, y, text in boxes.values():
        rect = FancyBboxPatch((x, y), 0.21, 0.18, boxstyle="round,pad=0.02", linewidth=1.3, facecolor="white")
        ax.add_patch(rect)
        ax.text(x + 0.105, y + 0.09, text, ha="center", va="center", fontsize=10)
    arrows = [
        ("energy_objects", "meters"),
        ("meters", "measurements"),
        ("energy_objects", "weather"),
        ("energy_objects", "baseline"),
        ("tariff", "measurements"),
    ]
    for a, b in arrows:
        x1, y1, _ = boxes[a]
        x2, y2, _ = boxes[b]
        ax.annotate("", xy=(x2, y2 + 0.09), xytext=(x1 + 0.21, y1 + 0.09), arrowprops=dict(arrowstyle="->", lw=1.2))
    ax.set_title("Логічна структура даних енергомоніторингу", fontsize=14, pad=15)
    fig.tight_layout()
    fig.savefig(diagram_dir / "schema_diagram.png", dpi=180)
    plt.close(fig)


def main() -> None:
    rng = np.random.default_rng(CONFIG.random_seed)
    if DB_PATH.exists():
        DB_PATH.unlink()
    with connect(DB_PATH) as conn:
        initialize_database(conn)
        object_id = insert_static_data(conn)
        timestamps = pd.date_range(f"{CONFIG.year}-01-01 00:00:00", f"{CONFIG.year}-12-31 23:00:00", freq="h")
        weather = generate_weather(timestamps, rng)
        main_load = generate_main_load(weather, rng)
        baseline = generate_baseline(main_load, weather)
        insert_time_series(conn, object_id, weather, main_load, baseline, rng)
        create_kpis(conn, object_id)
    write_schema_diagram()
    print(f"Generated database: {DB_PATH}")
    print(f"Hourly records: {8760 * CONFIG.meter_count}")


if __name__ == "__main__":
    main()
