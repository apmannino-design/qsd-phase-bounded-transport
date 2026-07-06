"""Analyze quantum measurement outcomes through the QSD/Aurora lens."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG
from aurora_qsd.core.tridelta import TriDelta, decompose_covariance
from aurora_qsd.core.aurora import check_aurora_condition
from aurora_qsd.core.iss import iss_bound
from aurora_qsd.core.phase_potential import phase_potential, is_zero_dissipation
from aurora_qsd.quantum.circuit_builder import zzz_score


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

    def from_counts(self, counts: dict[str, int], n_qubits: int | None = None) -> AnalysisReport:
        """Build covariance from bitstring counts and run QSD analysis."""
        if n_qubits is None:
            n_qubits = len(next(iter(counts)))
        sigma = covariance_from_counts(counts, n_qubits=n_qubits)
        return self.from_covariance(sigma, parity=zzz_score(counts, n_qubits=n_qubits))

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
        """Map measurement counts to a covariance proxy (2- or 3-qubit)."""
        n_qubits = len(next(iter(counts)))
        return covariance_from_counts(counts, n_qubits=n_qubits)

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


def _z_expectation(counts: dict[str, int], i: int) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    acc = 0.0
    for bitstring, n in counts.items():
        if len(bitstring) <= i:
            continue
        acc += (1.0 - 2.0 * int(bitstring[i])) * n
    return acc / total


def _zz_expectation(counts: dict[str, int], i: int, j: int) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    acc = 0.0
    for bitstring, n in counts.items():
        if len(bitstring) <= max(i, j):
            continue
        sign = 1.0 if int(bitstring[i]) == int(bitstring[j]) else -1.0
        acc += sign * n
    return acc / total


def covariance_from_counts(counts: dict[str, int], n_qubits: int = 3) -> np.ndarray:
    """
    Map Z-basis counts → n×n Pauli-Z covariance matrix.

    For 3 qubits: Cov(Zᵢ, Zⱼ) = ⟨ZᵢZⱼ⟩ − ⟨Zᵢ⟩⟨Zⱼ⟩, Var(Zᵢ) = 1 − ⟨Zᵢ⟩².
  """
    if not counts:
        return np.eye(n_qubits) * 0.01

    if n_qubits == 2:
        total = sum(counts.values())
        probs = {k: v / total for k, v in counts.items()}
        p00 = probs.get("00", 0.0)
        p01 = probs.get("01", 0.0)
        p10 = probs.get("10", 0.0)
        p11 = probs.get("11", 0.0)
        z0 = p00 + p01 - p10 - p11
        z1 = p00 - p01 + p10 - p11
        zz = p00 - p01 - p10 + p11
        obs = np.array([z0, z1, zz])
        return np.outer(obs, obs) + 0.01 * np.eye(3)

    z = [_z_expectation(counts, i) for i in range(n_qubits)]
    cov = np.zeros((n_qubits, n_qubits), dtype=float)
    for i in range(n_qubits):
        for j in range(n_qubits):
            if i == j:
                cov[i, j] = max(1.0 - z[i] ** 2, 1e-4)
            else:
                cov[i, j] = _zz_expectation(counts, i, j) - z[i] * z[j]
    # Regularize to keep PSD for TriDelta
    cov += 1e-3 * np.eye(n_qubits)
    return cov
