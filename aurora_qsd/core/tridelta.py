"""TriDelta covariance decomposition and Heron closure invariant."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.core.constants import THETA_STAR, TAN_THETA_STAR


@dataclass(frozen=True)
class TriDelta:
    """TriDelta coordinates and derived partition angle."""

    delta_j: float
    delta_l: float
    delta_x: float
    delta_e: float
    theta: float
    alignment_error: float
    heron: float
    in_qsd_corridor: bool
    in_phi_corridor: bool

    @property
    def residual_radius(self) -> float:
        return float(np.sqrt(self.delta_l**2 + self.delta_x**2))


def _projector_j(n: int) -> np.ndarray:
    """J-channel projector: uniform off-diagonal coupling."""
    p = np.ones((n, n), dtype=float) / n
    return p


def _projector_r(n: int) -> np.ndarray:
    """R-channel projector: complement of J."""
    return np.eye(n, dtype=float) - _projector_j(n)


def decompose_covariance(
    sigma: np.ndarray,
    m: float = 1.0,
    theta_target: float = THETA_STAR,
) -> TriDelta:
    """
    Decompose a positive-semidefinite covariance matrix into TriDelta coordinates.

    Pipeline: Σ → (∆J, ∆L, ∆X) → θ = arctan(∆J/R), ∆E = √(Tr Σ / M).
    """
    sigma = np.asarray(sigma, dtype=float)
    if sigma.ndim != 2 or sigma.shape[0] != sigma.shape[1]:
        raise ValueError("sigma must be a square matrix")

    n = sigma.shape[0]
    pj = _projector_j(n)
    pr = _projector_r(n)

    delta_j = float(np.trace(pj @ sigma))
    delta_l = float(np.trace(pr @ sigma @ pr) / 2.0)
    delta_x = float(np.sqrt(max(0.0, np.trace(sigma) - delta_j - 2.0 * delta_l)))

    r = float(np.sqrt(delta_l**2 + delta_x**2))
    theta = float(np.arctan(delta_j / r)) if r > 0 else (np.pi / 2 if delta_j > 0 else 0.0)
    delta_e = float(np.sqrt(np.trace(sigma) / m))
    heron = heron_penalty(delta_j, delta_l, delta_x)

  # QSD corridor: |∆J| ≤ (√2-1)·R
    in_qsd = abs(delta_j) <= TAN_THETA_STAR * r if r > 0 else True
    # Golden corridor: |∆J| ≤ R/φ
    in_phi = abs(delta_j) <= (1.0 / ((1.0 + np.sqrt(5.0)) / 2.0)) * r if r > 0 else True

    return TriDelta(
        delta_j=delta_j,
        delta_l=delta_l,
        delta_x=delta_x,
        delta_e=delta_e,
        theta=theta,
        alignment_error=float(theta - theta_target),
        heron=heron,
        in_qsd_corridor=in_qsd,
        in_phi_corridor=in_phi,
    )


def heron_penalty(delta_j: float, delta_l: float, delta_x: float) -> float:
    """
    Differentiable Heron non-closure penalty.

    H = Σ_cyc [max(0, c - a - b)]²; zero iff triangle inequalities hold.
    """
    sides = (abs(delta_j), abs(delta_l), abs(delta_x))
    penalty = 0.0
    for i in range(3):
        a, b, c = sides[i], sides[(i + 1) % 3], sides[(i + 2) % 3]
        penalty += max(0.0, c - a - b) ** 2
    return float(penalty)
