"""Component models for the hybrid energy system."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PVPlant:
    """Simple PV generation model."""

    capacity_kw: float
    efficiency: float = 0.94
    degradation: float = 0.005
    temp_coeff_per_c: float = -0.004

    def generation_kwh(self, insolation_kw_m2: float, temperature_c: float) -> float:
        """Return hourly PV generation in kWh."""
        temp_derate = max(0.80, 1 + self.temp_coeff_per_c * max(temperature_c - 25, 0))
        return max(self.capacity_kw * insolation_kw_m2 * self.efficiency * (1 - self.degradation) * temp_derate, 0.0)


@dataclass
class Battery:
    """Battery model with SOC limits and charge/discharge efficiency."""

    capacity_kwh: float
    max_power_kw: float
    soc_initial_pct: float = 50.0
    soc_min_pct: float = 20.0
    soc_max_pct: float = 90.0
    charge_efficiency: float = 0.92
    discharge_efficiency: float = 0.92
    self_discharge_per_hour: float = 0.00004

    def __post_init__(self) -> None:
        self.energy_kwh = self.capacity_kwh * self.soc_initial_pct / 100

    @property
    def soc_pct(self) -> float:
        """Current state of charge in %."""
        return self.energy_kwh / self.capacity_kwh * 100

    def apply_self_discharge(self) -> None:
        """Apply small hourly self-discharge."""
        self.energy_kwh = max(self.capacity_kwh * self.soc_min_pct / 100, self.energy_kwh * (1 - self.self_discharge_per_hour))

    def available_charge_capacity(self) -> float:
        """Maximum energy that can be stored before reaching SOC max, kWh."""
        return max(self.capacity_kwh * self.soc_max_pct / 100 - self.energy_kwh, 0.0)

    def available_discharge_energy(self) -> float:
        """Maximum delivered energy before reaching SOC min, kWh."""
        stored_above_min = max(self.energy_kwh - self.capacity_kwh * self.soc_min_pct / 100, 0.0)
        return stored_above_min * self.discharge_efficiency

    def charge(self, energy_available_kwh: float) -> float:
        """Charge battery and return energy taken from source before efficiency losses."""
        source_energy = min(energy_available_kwh, self.max_power_kw, self.available_charge_capacity() / self.charge_efficiency)
        self.energy_kwh += source_energy * self.charge_efficiency
        return max(source_energy, 0.0)

    def discharge(self, demand_kwh: float) -> float:
        """Discharge battery and return energy delivered to load."""
        delivered = min(demand_kwh, self.max_power_kw, self.available_discharge_energy())
        self.energy_kwh -= delivered / self.discharge_efficiency
        return max(delivered, 0.0)


@dataclass(frozen=True)
class Grid:
    """Grid model with import/export prices and connection limit."""

    connection_limit_kw: float = 180.0
    export_price_uah_kwh: float = 6.5

    def tariff(self, hour: int) -> tuple[str, float]:
        """Return tariff zone and import price for hour."""
        if 23 <= hour or hour < 7:
            return "night", 5.6
        if 8 <= hour < 11 or 17 <= hour < 22:
            return "peak", 9.0
        return "half_peak", 6.9
