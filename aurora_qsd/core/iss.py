"""Input-to-State Stability bounds for QSD closed-loop control (Theorem 6)."""

from __future__ import annotations

import numpy as np


def contraction_rate(rho: float) -> float:
    """Γ_lock = −½ ln(ρ), the QSD basin contraction rate (per step)."""
    if not 0.0 <= rho < 1.0:
        raise ValueError("rho must satisfy 0 <= rho < 1")
    return float(-0.5 * np.log(rho))


def iss_bound(
    e0: float,
    t: int,
    rho: float,
    disturbance: float = 0.0,
) -> float:
    """
    Theorem 6 ISS bound on error:

        |e_t| ≤ ρ^(t/2) |e_0| + D / (1 − √ρ)
    """
    if not 0.0 <= rho < 1.0:
        raise ValueError("rho must satisfy 0 <= rho < 1")
    return float((rho ** (t / 2.0)) * abs(e0) + disturbance / (1.0 - np.sqrt(rho)))


def iss_trajectory(
    e0: float,
    steps: int,
    rho: float,
    disturbance: float = 0.0,
) -> np.ndarray:
    """Return the ISS bound at each timestep t = 0..steps."""
    return np.array([iss_bound(e0, t, rho, disturbance) for t in range(steps + 1)])


def return_time(rho: float, epsilon: float, e0: float) -> float:
    """Steps to return within tolerance ε under homogeneous contraction."""
    if e0 <= 0 or epsilon <= 0 or epsilon >= abs(e0):
        return 0.0
    return float(np.log(epsilon / abs(e0)) / np.log(rho))
