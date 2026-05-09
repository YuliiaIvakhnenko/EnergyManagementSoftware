"""Configuration for Variant 3 of the energy-management labs."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VariantConfig:
    object_name: str = "Лабораторія"
    object_type: str = "laboratory"
    city: str = "Київ"
    year: int = 2025
    area_m2: float = 600.0
    installed_power_kw: float = 180.0
    meter_count: int = 7
    work_start_hour: int = 6
    work_end_hour: int = 22
    base_load_kw: float = 40.0
    min_load_kw: float = 30.0
    max_load_kw: float = 65.0
    pv_capacity_kw: float = 60.0
    battery_capacity_kwh: float = 50.0
    tariff_type: str = "3-zone"
    export_price_uah_kwh: float = 6.5
    random_seed: int = 303


CONFIG = VariantConfig()

# Seven meters are modeled. M-01 is the main object-level meter. Other meters
# describe level-2 and level-3 submetering. Shares are used only for synthetic
# disaggregation and are not summed with the main meter in object-level reports.
METERS = [
    {"code": "M-01", "name": "Головний ввід лабораторії", "level": 1, "share": 1.00, "location": "ГРЩ", "meter_type": "main"},
    {"code": "M-02", "name": "Вентиляція та HVAC", "level": 2, "share": 0.34, "location": "Щит HVAC", "meter_type": "subsystem"},
    {"code": "M-03", "name": "Лабораторне обладнання", "level": 2, "share": 0.28, "location": "Лабораторний блок", "meter_type": "subsystem"},
    {"code": "M-04", "name": "Освітлення", "level": 2, "share": 0.16, "location": "Щит освітлення", "meter_type": "subsystem"},
    {"code": "M-05", "name": "Серверна та ІТ", "level": 3, "share": 0.09, "location": "Серверна", "meter_type": "equipment"},
    {"code": "M-06", "name": "Холодильні установки", "level": 3, "share": 0.08, "location": "Зона зберігання", "meter_type": "equipment"},
    {"code": "M-07", "name": "Допоміжні розетки", "level": 3, "share": 0.05, "location": "Робочі місця", "meter_type": "equipment"},
]

# Simplified 3-zone business tariff for Kyiv, UAH/kWh without VAT and network fees.
# Peak: 08-11 and 17-22, half-peak: 07-08, 11-17, 22-23, night: 23-07.
def tariff_for_hour(hour: int) -> tuple[str, float]:
    if 23 <= hour or hour < 7:
        return "night", 5.6
    if 8 <= hour < 11 or 17 <= hour < 22:
        return "peak", 9.0
    return "half_peak", 6.9
