"""
SO(2) projector sweep at peak merger — TriDelta L/X channel rotation.

Rotates the L–X split inside the R-channel and searches for the merger lock
where ΔL/ΔX → MERGER_STRUCTURAL_RATIO_LX and partition θ emerges.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from aurora_qsd.core.constants import (
    MERGER_PARTITION_THETA_DEG,
    MERGER_PROJECTOR_ALPHA_DEG,
    MERGER_STRUCTURAL_RATIO_LX,
    THETA_STAR,
)
from aurora_qsd.core.tridelta import TriDelta, decompose_covariance, heron_penalty


@dataclass(frozen=True)
class MergerSweepPoint:
    alpha_deg: float
    delta_l: float
    delta_x: float
    ratio_lx: float
    theta_deg: float
    score: float

    def to_dict(self) -> dict:
        return {
            "alpha_deg": self.alpha_deg,
            "delta_l": self.delta_l,
            "delta_x": self.delta_x,
            "ratio_lx": self.ratio_lx,
            "theta_deg": self.theta_deg,
            "score": self.score,
        }


@dataclass(frozen=True)
class MergerSweepResult:
    optimal_alpha_deg: float
    optimal_ratio_lx: float
    optimal_theta_deg: float
    target_ratio_lx: float
    target_theta_deg: float
    target_alpha_deg: float
    ratio_error: float
    theta_error_deg: float
    alpha_error_deg: float
    points: tuple[MergerSweepPoint, ...]
    verdict: str
    notes: str

    def to_dict(self) -> dict:
        return {
            "optimal_alpha_deg": self.optimal_alpha_deg,
            "optimal_ratio_lx": self.optimal_ratio_lx,
            "optimal_theta_deg": self.optimal_theta_deg,
            "target_ratio_lx": self.target_ratio_lx,
            "target_theta_deg": self.target_theta_deg,
            "target_alpha_deg": self.target_alpha_deg,
            "ratio_error": self.ratio_error,
            "theta_error_deg": self.theta_error_deg,
            "alpha_error_deg": self.alpha_error_deg,
            "points": [p.to_dict() for p in self.points],
            "verdict": self.verdict,
            "notes": self.notes,
        }


def _rotate_lx(delta_l0: float, delta_x0: float, alpha_rad: float) -> tuple[float, float]:
    c, s = math.cos(alpha_rad), math.sin(alpha_rad)
    return delta_l0 * c - delta_x0 * s, delta_l0 * s + delta_x0 * c


def tri_delta_from_lx(
    delta_j: float,
    delta_l: float,
    delta_x: float,
    trace_sigma: float = 1.0,
    m: float = 1.0,
    theta_target: float = THETA_STAR,
) -> TriDelta:
    r = float(math.hypot(delta_l, delta_x))
    theta = float(math.atan(delta_j / r)) if r > 0 else (math.pi / 2 if delta_j > 0 else 0.0)
    delta_e = float(math.sqrt(trace_sigma / m))
    heron = heron_penalty(delta_j, delta_l, delta_x)

    from aurora_qsd.core.constants import TAN_THETA_STAR, PHI

    in_qsd = abs(delta_j) <= TAN_THETA_STAR * r if r > 0 else True
    in_phi = abs(delta_j) <= (1.0 / PHI) * r if r > 0 else True

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


def decompose_with_projector_rotation(
    sigma: np.ndarray,
    alpha_rad: float,
    m: float = 1.0,
    theta_target: float = THETA_STAR,
) -> TriDelta:
    """SO(2) rotation of L/X invariants extracted from Σ."""
    td0 = decompose_covariance(sigma, m=m, theta_target=theta_target)
    delta_l, delta_x = _rotate_lx(td0.delta_l, td0.delta_x, alpha_rad)
    return tri_delta_from_lx(
        td0.delta_j,
        delta_l,
        delta_x,
        trace_sigma=float(np.trace(sigma)),
        m=m,
        theta_target=theta_target,
    )


def merger_score(
    ratio_lx: float,
    theta_deg: float,
    target_ratio: float = MERGER_STRUCTURAL_RATIO_LX,
    target_theta_deg: float = MERGER_PARTITION_THETA_DEG,
    w_ratio: float = 1.0,
    w_theta: float = 0.25,
) -> float:
    """Lower is better — distance to preregistered peak-merger targets."""
    if ratio_lx <= 0 or not math.isfinite(ratio_lx):
        return float("inf")
    r_err = (ratio_lx - target_ratio) / target_ratio
    t_err = (theta_deg - target_theta_deg) / max(target_theta_deg, 1e-6)
    return float(w_ratio * r_err**2 + w_theta * t_err**2)


def run_so2_sweep_from_invariants(
    delta_j: float,
    delta_l0: float,
    delta_x0: float,
    alpha_deg_range: tuple[float, float] = (0.0, 90.0),
    n_points: int = 901,
    store_curve: bool = False,
) -> MergerSweepResult:
    """Core SO(2) sweep on TriDelta L/X components (α = 0 reference frame)."""
    alphas = np.linspace(alpha_deg_range[0], alpha_deg_range[1], n_points)
    best: MergerSweepPoint | None = None
    curve: list[MergerSweepPoint] = []

    for alpha_deg in alphas:
        alpha = math.radians(float(alpha_deg))
        delta_l, delta_x = _rotate_lx(delta_l0, delta_x0, alpha)
        td = tri_delta_from_lx(delta_j, delta_l, delta_x)
        ratio = abs(delta_l / delta_x) if abs(delta_x) > 1e-12 else float("inf")
        theta_deg = float(np.degrees(td.theta))
        score = merger_score(ratio, theta_deg)
        pt = MergerSweepPoint(
            alpha_deg=float(alpha_deg),
            delta_l=delta_l,
            delta_x=delta_x,
            ratio_lx=float(ratio),
            theta_deg=theta_deg,
            score=score,
        )
        if store_curve:
            curve.append(pt)
        if best is None or score < best.score:
            best = pt

    assert best is not None
    return _finalize_merger_result(best, curve if store_curve else [])


def run_so2_projector_sweep(
    sigma: np.ndarray,
    alpha_deg_range: tuple[float, float] = (0.0, 90.0),
    n_points: int = 901,
    store_curve: bool = False,
) -> MergerSweepResult:
    """Sweep projector rotation α on a measured covariance Σ."""
    td0 = decompose_covariance(sigma)
    return run_so2_sweep_from_invariants(
        td0.delta_j,
        td0.delta_l,
        td0.delta_x,
        alpha_deg_range=alpha_deg_range,
        n_points=n_points,
        store_curve=store_curve,
    )


def _finalize_merger_result(best: MergerSweepPoint, curve: list[MergerSweepPoint]) -> MergerSweepResult:
    ratio_err = abs(best.ratio_lx - MERGER_STRUCTURAL_RATIO_LX)
    theta_err = abs(best.theta_deg - MERGER_PARTITION_THETA_DEG)
    alpha_err = abs(best.alpha_deg - MERGER_PROJECTOR_ALPHA_DEG)

    if ratio_err < 0.02 and theta_err < 1.0 and alpha_err < 1.0:
        verdict = "MERGER_LOCK"
        notes = (
            f"Peak merger: α={best.alpha_deg:.2f}° ΔL/ΔX={best.ratio_lx:.4f} θ={best.theta_deg:.2f}°"
        )
    elif ratio_err < 0.05:
        verdict = "RATIO_LOCK"
        notes = f"Structural ratio locked (ΔL/ΔX={best.ratio_lx:.4f}); θ offset {theta_err:.2f}°."
    else:
        verdict = "NO_LOCK"
        notes = f"No merger lock (best ratio err {ratio_err:.4f})."

    return MergerSweepResult(
        optimal_alpha_deg=best.alpha_deg,
        optimal_ratio_lx=best.ratio_lx,
        optimal_theta_deg=best.theta_deg,
        target_ratio_lx=MERGER_STRUCTURAL_RATIO_LX,
        target_theta_deg=MERGER_PARTITION_THETA_DEG,
        target_alpha_deg=MERGER_PROJECTOR_ALPHA_DEG,
        ratio_error=ratio_err,
        theta_error_deg=theta_err,
        alpha_error_deg=alpha_err,
        points=tuple(curve),
        verdict=verdict,
        notes=notes,
    )


def merger_reference_invariants(scale: float = 1.0) -> tuple[float, float, float]:
    """
    Reference (ΔJ, ΔL₀, ΔX₀) whose SO(2) sweep peak matches preregistered merger targets.

    At α = MERGER_PROJECTOR_ALPHA_DEG the rotated frame hits ratio 2.1974 and θ = 27.61°.
    """
    ratio = MERGER_STRUCTURAL_RATIO_LX
    theta = math.radians(MERGER_PARTITION_THETA_DEG)
    alpha = math.radians(MERGER_PROJECTOR_ALPHA_DEG)

    delta_x_m = scale
    delta_l_m = ratio * delta_x_m
    r = math.hypot(delta_l_m, delta_x_m)
    delta_j = r * math.tan(theta)

    c, s = math.cos(alpha), math.sin(alpha)
    delta_l0 = delta_l_m * c + delta_x_m * s
    delta_x0 = -delta_l_m * s + delta_x_m * c
    return float(delta_j), float(delta_l0), float(delta_x0)


def synthesis_sigma_for_merger_targets(n: int = 3, scale: float = 1.0) -> np.ndarray:
    """PSD proxy Σ for pipeline tests (invariants approximate at α = 0)."""
    delta_j, delta_l0, delta_x0 = merger_reference_invariants(scale=scale)
    pj = np.ones((n, n), dtype=float) / n
    pr = np.eye(n, dtype=float) - pj
    trace_target = max(delta_j + 2.0 * delta_l0 + delta_x0**2, 1e-6)
    sigma = abs(delta_j) * pj + abs(delta_l0) * pr / max(float(np.trace(pr)), 1e-9)
    cur = float(np.trace(sigma))
    if cur < trace_target:
        sigma = sigma + (trace_target - cur) * np.eye(n) / n
    return sigma
