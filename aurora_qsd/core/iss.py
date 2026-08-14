"""Input-to-State Stability bounds for QSD closed-loop control (Theorem 6)."""

from __future__ import annotations

import numpy as np


def discrete_iss_gain(rho: float) -> float:
    """Per-sample type-1 step k = 1 − √ρ matching the homogeneous map e ← √ρ e."""
    if not 0.0 <= rho < 1.0:
        raise ValueError("rho must satisfy 0 <= rho < 1")
    return float(1.0 - np.sqrt(rho))


def matched_integrator_ki(dt: float, rho: float) -> float:
    """PI I-gain such that ki·dt = 1 − √ρ (matched bandwidth vs ISS)."""
    if dt <= 0:
        raise ValueError("dt must be positive")
    return discrete_iss_gain(rho) / dt


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


def one_step_iss_coverage(
    error: np.ndarray,
    rho: float,
    d_step: float,
) -> float:
    """
    Fraction of samples satisfying the Theorem 6 induction step:

        |e_{t+1}| ≤ √ρ |e_t| + D

    This is the non-unfolded certificate. The closed-form envelope
    |e_t| ≤ ρ^{t/2}|e_0| + D/(1−√ρ) uses the same D at every step and is
    often vacuous; this one-step test is the bound that can actually fail.
    """
    if not 0.0 <= rho < 1.0:
        raise ValueError("rho must satisfy 0 <= rho < 1")
    e = np.abs(np.asarray(error, dtype=float).reshape(-1))
    if e.size < 2:
        return 1.0
    pred = np.sqrt(rho) * e[:-1] + abs(d_step)
    return float(np.mean(e[1:] <= pred + 1e-15))
