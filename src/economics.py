"""Economic helper functions for EMS analysis."""
from __future__ import annotations

import numpy as np


def npv(rate: float, cashflows: list[float]) -> float:
    """Calculate net present value for a sequence of yearly cashflows."""
    return sum(cf / ((1 + rate) ** i) for i, cf in enumerate(cashflows))


def irr(cashflows: list[float], low: float = -0.95, high: float = 1.5, tol: float = 1e-6) -> float | None:
    """Calculate IRR with bisection; return None if no sign change."""
    f_low = npv(low, cashflows)
    f_high = npv(high, cashflows)
    if f_low * f_high > 0:
        return None
    for _ in range(160):
        mid = (low + high) / 2
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2
