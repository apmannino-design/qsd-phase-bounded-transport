"""Third-harmonic phase potential V(Θ) = -cos Θ - (1/3) sin(3Θ)."""

from __future__ import annotations

import numpy as np

from aurora_qsd.core.constants import THETA_STAR, BASIN_BOUNDARY_DEG


def phase_potential(theta: float | np.ndarray) -> float | np.ndarray:
    """QSD basin potential; deepest well at θ*."""
    return -np.cos(theta) - (1.0 / 3.0) * np.sin(3.0 * theta)


def phase_force(theta: float | np.ndarray) -> float | np.ndarray:
    """Thermodynamic force F(Θ) = -∂V/∂Θ = cos(3Θ) - sin(Θ)."""
    return np.cos(3.0 * theta) - np.sin(theta)


def entropy_production_rate(theta: float, theta_dot: float, temperature: float = 1.0) -> float:
    """Instantaneous entropy production σ(Θ) = F(Θ)·Θ̇ / T ≥ 0."""
    return float(phase_force(theta) * theta_dot / temperature)


def is_zero_dissipation(theta: float, tol: float = 1e-6) -> bool:
    """True at fixed points where F(Θ) = 0 (zero instantaneous entropy production)."""
    return abs(float(phase_force(theta))) < tol


def basin_boundary(theta_star: float = THETA_STAR) -> float:
    """Basin edge at ±3θ* (hardware escape threshold)."""
    return 3.0 * theta_star


def basin_boundary_deg() -> float:
    return BASIN_BOUNDARY_DEG
