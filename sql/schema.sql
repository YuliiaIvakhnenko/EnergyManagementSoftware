PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_level1_hourly;
DROP VIEW IF EXISTS v_level2_hourly;
DROP VIEW IF EXISTS v_level3_hourly;
DROP TABLE IF EXISTS energy_efficiency_kpis;
DROP TABLE IF EXISTS baselines;
DROP TABLE IF EXISTS measurements;
DROP TABLE IF EXISTS weather_data;
DROP TABLE IF EXISTS tariff_schedule;
DROP TABLE IF EXISTS meters;
DROP TABLE IF EXISTS energy_objects;

CREATE TABLE energy_objects (
    object_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    object_type TEXT NOT NULL,
    city TEXT NOT NULL,
    area_m2 REAL NOT NULL CHECK (area_m2 > 0),
    installed_power_kw REAL NOT NULL CHECK (installed_power_kw > 0),
    work_start_hour INTEGER NOT NULL CHECK (work_start_hour BETWEEN 0 AND 23),
    work_end_hour INTEGER NOT NULL CHECK (work_end_hour BETWEEN 0 AND 24),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE meters (
    meter_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    meter_type TEXT NOT NULL,
    location TEXT NOT NULL,
    accounting_level INTEGER NOT NULL CHECK (accounting_level IN (1, 2, 3)),
    share_of_main_load REAL NOT NULL CHECK (share_of_main_load > 0 AND share_of_main_load <= 1),
    accuracy_class TEXT NOT NULL DEFAULT '1.0',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    FOREIGN KEY (object_id) REFERENCES energy_objects(object_id) ON DELETE CASCADE
);

CREATE TABLE tariff_schedule (
    tariff_id INTEGER PRIMARY KEY AUTOINCREMENT,
    tariff_type TEXT NOT NULL,
    hour INTEGER NOT NULL CHECK (hour BETWEEN 0 AND 23),
    zone_name TEXT NOT NULL,
    import_price_uah_kwh REAL NOT NULL CHECK (import_price_uah_kwh >= 0),
    export_price_uah_kwh REAL NOT NULL CHECK (export_price_uah_kwh >= 0),
    UNIQUE (tariff_type, hour)
);

CREATE TABLE weather_data (
    weather_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    temperature_c REAL NOT NULL,
    insolation_kw_m2 REAL NOT NULL CHECK (insolation_kw_m2 >= 0),
    hdd_18 REAL NOT NULL CHECK (hdd_18 >= 0),
    cdd_22 REAL NOT NULL CHECK (cdd_22 >= 0),
    FOREIGN KEY (object_id) REFERENCES energy_objects(object_id) ON DELETE CASCADE,
    UNIQUE (object_id, timestamp)
);

CREATE TABLE measurements (
    measurement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    meter_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    consumption_kwh REAL NOT NULL CHECK (consumption_kwh >= 0),
    quality_flag TEXT NOT NULL DEFAULT 'OK' CHECK (quality_flag IN ('OK', 'ESTIMATED', 'MISSING', 'ANOMALY')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (meter_id) REFERENCES meters(meter_id) ON DELETE CASCADE,
    UNIQUE (meter_id, timestamp)
);

CREATE TABLE baselines (
    baseline_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    baseline_kwh REAL NOT NULL CHECK (baseline_kwh >= 0),
    method TEXT NOT NULL DEFAULT 'synthetic weather-normalized baseline',
    FOREIGN KEY (object_id) REFERENCES energy_objects(object_id) ON DELETE CASCADE,
    UNIQUE (object_id, timestamp)
);

CREATE TABLE energy_efficiency_kpis (
    kpi_id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id INTEGER NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    consumption_kwh REAL NOT NULL,
    specific_kwh_m2 REAL NOT NULL,
    baseline_kwh REAL NOT NULL,
    deviation_pct REAL NOT NULL,
    FOREIGN KEY (object_id) REFERENCES energy_objects(object_id) ON DELETE CASCADE
);

CREATE INDEX idx_measurements_meter_time ON measurements (meter_id, timestamp);
CREATE INDEX idx_measurements_time ON measurements (timestamp);
CREATE INDEX idx_weather_object_time ON weather_data (object_id, timestamp);
CREATE INDEX idx_baselines_object_time ON baselines (object_id, timestamp);
CREATE INDEX idx_meters_object_level ON meters (object_id, accounting_level);
CREATE INDEX idx_tariff_hour ON tariff_schedule (tariff_type, hour);

CREATE VIEW v_level1_hourly AS
SELECT
    eo.object_id,
    eo.name AS object_name,
    m.code AS meter_code,
    m.name AS meter_name,
    ms.timestamp,
    ms.consumption_kwh,
    ms.quality_flag
FROM measurements ms
JOIN meters m ON m.meter_id = ms.meter_id
JOIN energy_objects eo ON eo.object_id = m.object_id
WHERE m.accounting_level = 1;

CREATE VIEW v_level2_hourly AS
SELECT
    eo.object_id,
    eo.name AS object_name,
    m.code AS meter_code,
    m.name AS meter_name,
    ms.timestamp,
    ms.consumption_kwh,
    ms.quality_flag
FROM measurements ms
JOIN meters m ON m.meter_id = ms.meter_id
JOIN energy_objects eo ON eo.object_id = m.object_id
WHERE m.accounting_level = 2;

CREATE VIEW v_level3_hourly AS
SELECT
    eo.object_id,
    eo.name AS object_name,
    m.code AS meter_code,
    m.name AS meter_name,
    ms.timestamp,
    ms.consumption_kwh,
    ms.quality_flag
FROM measurements ms
JOIN meters m ON m.meter_id = ms.meter_id
JOIN energy_objects eo ON eo.object_id = m.object_id
WHERE m.accounting_level = 3;
