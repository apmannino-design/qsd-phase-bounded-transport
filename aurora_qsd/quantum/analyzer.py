"""Analyze quantum measurement outcomes through the QSD/Aurora lens."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG
from aurora_qsd.core.tridelta import TriDelta, decompose_covariance
from aurora_qsd.core.aurora import check_aurora_condition
from aurora_qsd.core.iss import iss_bound
from aurora_qsd.core.phase_potential import phase_potential, is_zero_dissipation
from aurora_qsd.quantum.circuit_builder import parity_score


@dataclass
class AnalysisReport:
    """QSD analysis of a quantum experiment or simulation."""

    tri_delta: TriDelta
    parity: float | None
    theta_deg: float
    alignment_error_deg: float
    at_lock_point: bool
    in_basin: bool
    aurora_satisfied: bool
    iss_error_bound: float
    recommendations: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=== QSD/Aurora Quantum Analysis ===",
            f"θ = {self.theta_deg:.4f}° (target θ* = {THETA_STAR_DEG:.4f}°)",
            f"Alignment error: {self.alignment_error_deg:+.4f}°",
            f"∆E = {self.tri_delta.delta_e:.4f}, Heron = {self.tri_delta.heron:.6f}",
            f"QSD corridor: {'YES' if self.tri_delta.in_qsd_corridor else 'NO'}",
            f"At lock point: {'YES' if self.at_lock_point else 'NO'}",
            f"In basin: {'YES' if self.in_basin else 'NO'}",
            f"Aurora condition: {'SATISFIED' if self.aurora_satisfied else 'NOT SATISFIED'}",
        ]
        if self.parity is not None:
            lines.append(f"Parity score: {self.parity:.4f}")
        lines.append(f"ISS error bound (t=10): {self.iss_error_bound:.6f}")
        if self.recommendations:
            lines.append("Recommendations:")
            for r in self.recommendations:
                lines.append(f"  • {r}")
        return "\n".join(lines)


class QuantumQSDAnalyzer:
    """Analyze quantum states and measurement statistics via TriDelta decomposition."""

    def __init__(
        self,
        theta_target: float = THETA_STAR,
        rho: float = 0.85,
        t2_us: float = 100.0,
        alignment_tol_deg: float = 1.0,
    ):
        self.theta_target = theta_target
        self.rho = rho
        self.t2_us = t2_us
        self.alignment_tol_deg = alignment_tol_deg

    def from_counts(self, counts: dict[str, int]) -> AnalysisReport:
        """Build covariance from bitstring counts and run QSD analysis."""
        sigma = self._counts_to_covariance(counts)
        return self.from_covariance(sigma, parity=parity_score(counts))

    def from_covariance(self, sigma: np.ndarray, parity: float | None = None) -> AnalysisReport:
        """Analyze a covariance matrix directly."""
        td = decompose_covariance(sigma, theta_target=self.theta_target)
        aurora = check_aurora_condition(rho=self.rho, t2_us=self.t2_us)

        ae_deg = float(np.degrees(td.alignment_error))
        at_lock = abs(ae_deg) < self.alignment_tol_deg
        in_basin = abs(ae_deg) < 3.0 * THETA_STAR_DEG

        iss_err = iss_bound(
            e0=abs(td.alignment_error),
            t=10,
            rho=self.rho,
        )

        recs = self._generate_recommendations(td, aurora.satisfied, at_lock, parity)
        return AnalysisReport(
            tri_delta=td,
            parity=parity,
            theta_deg=float(np.degrees(td.theta)),
            alignment_error_deg=ae_deg,
            at_lock_point=at_lock,
            in_basin=in_basin,
            aurora_satisfied=aurora.satisfied,
            iss_error_bound=iss_err,
            recommendations=recs,
        )

    def _counts_to_covariance(self, counts: dict[str, int]) -> np.ndarray:
        """Map measurement counts to a 3×3 covariance proxy."""
        total = sum(counts.values())
        n_qubits = len(next(iter(counts)))
        probs = {k: v / total for k, v in counts.items()}

        # Observable expectations for 2-qubit case
        p00 = probs.get("00", 0.0)
        p01 = probs.get("01", 0.0)
        p10 = probs.get("10", 0.0)
        p11 = probs.get("11", 0.0)

        # Pauli-Z expectations
        z0 = p00 + p01 - p10 - p11
        z1 = p00 - p01 + p10 - p11
        zz = p00 - p01 - p10 + p11

        obs = np.array([z0, z1, zz])
        return np.outer(obs, obs) + 0.01 * np.eye(3)

    def _generate_recommendations(
        self,
        td: TriDelta,
        aurora_ok: bool,
        at_lock: bool,
        parity: float | None,
    ) -> list[str]:
        recs: list[str] = []
        ae_deg = float(np.degrees(td.alignment_error))

        if not at_lock:
            direction = "decrease" if ae_deg > 0 else "increase"
            recs.append(
                f"Adjust partition angle: {direction} θ by {abs(ae_deg):.2f}° toward θ* = {THETA_STAR_DEG:.2f}°"
            )

        if not aurora_ok:
            recs.append("Enable periodic re-preparation (re-lock every 7 layers) to satisfy Aurora condition")

        if td.heron > 0:
            recs.append("Heron closure violated — check projector decomposition consistency")

        if parity is not None and parity < 0.5:
            recs.append("Low parity score — apply QSD cell initialization at θ* before entangling layers")

        if at_lock and aurora_ok and (parity is None or parity >= 0.6):
            recs.append("System near optimal QSD lock — maintain current re-preparation cadence")

        if is_zero_dissipation(self.theta_target):
            v_at_star = float(phase_potential(self.theta_target))
            recs.append(f"Zero-dissipation point confirmed (V(θ*) = {v_at_star:.4f})")

        return recs
