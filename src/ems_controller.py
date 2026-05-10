"""Rule-based EMS controller for Lab 3."""
from __future__ import annotations

from components import Battery, Grid


def dispatch_hour(load_kwh: float, pv_kwh: float, battery: Battery, grid: Grid, hour: int) -> dict[str, float | str]:
    """Dispatch one hourly step and return detailed energy flows."""
    zone, import_price = grid.tariff(hour)
    battery.apply_self_discharge()

    pv_to_load = min(load_kwh, pv_kwh)
    remaining_load = load_kwh - pv_to_load
    surplus_pv = pv_kwh - pv_to_load

    pv_to_battery = 0.0
    export_kwh = 0.0
    battery_to_load = 0.0
    grid_to_load = 0.0
    grid_to_battery = 0.0

    if surplus_pv > 0:
        pv_to_battery = battery.charge(surplus_pv)
        export_kwh = max(surplus_pv - pv_to_battery, 0.0)

    if remaining_load > 0:
        if zone == "peak" or battery.soc_pct > 60:
            battery_to_load = battery.discharge(remaining_load)
            remaining_load -= battery_to_load
        elif zone == "half_peak" and battery.soc_pct > 75:
            battery_to_load = battery.discharge(remaining_load * 0.55)
            remaining_load -= battery_to_load
        grid_to_load = min(remaining_load, grid.connection_limit_kw)

    # Cheap night charging for preparation before daytime/peak demand.
    if zone == "night" and battery.soc_pct < 78:
        grid_to_battery = battery.charge(min(grid.connection_limit_kw - grid_to_load, battery.max_power_kw))

    import_kwh = grid_to_load + grid_to_battery
    import_cost = import_kwh * import_price
    export_revenue = export_kwh * grid.export_price_uah_kwh

    return {
        "zone_name": zone,
        "import_price_uah_kwh": import_price,
        "load_kwh": load_kwh,
        "pv_generation_kwh": pv_kwh,
        "pv_to_load_kwh": pv_to_load,
        "pv_to_battery_kwh": pv_to_battery,
        "battery_to_load_kwh": battery_to_load,
        "grid_to_load_kwh": grid_to_load,
        "grid_to_battery_kwh": grid_to_battery,
        "grid_import_kwh": import_kwh,
        "grid_export_kwh": export_kwh,
        "soc_pct": battery.soc_pct,
        "import_cost_uah": import_cost,
        "export_revenue_uah": export_revenue,
        "net_cost_uah": import_cost - export_revenue,
    }
