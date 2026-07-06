"""
Full-chip QSD stability controller — closed-loop Ae / σ monitoring + adaptive re-lock.

Target: Ae → 0, Δσ → ∅ (dispersion collapsed) at θ* across all disjoint 3Q lines.

Operational loop per cell:
  1. Measure ZZZ + TriDelta proxy from counts
  2. Compute alignment error Ae and entropy production σ(θ)
  3. Adapt re-lock interval (tighter if out-of-band, looser if locked)
  4. Run depth sunscreen at θ* with adapted schedule
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.aurora import check_aurora_condition, optimal_relock_interval
from aurora_qsd.core.constants import THETA_STAR, THETA_STAR_DEG
from aurora_qsd.core.phase_potential import entropy_production_rate, is_zero_dissipation, phase_force
from aurora_qsd.core.tridelta import decompose_covariance
from aurora_qsd.quantum.analyzer import QuantumQSDAnalyzer
from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_THETA_DEG
from aurora_qsd.quantum.willow_lines import WillowLine, extract_disjoint_3q_lines
from aurora_qsd.quantum.willow_run import (
    _depth_head_to_head,
    _require_cirq,
    _zzz_from_result,
    build_depth_sunscreen_circuit,
)


def _counts_3q(result, shots: int) -> dict[str, int]:
    keys = sorted(result.data.keys(), key=lambda k: str(k))
    counts: dict[str, int] = {}
    for i in range(shots):
        bits = "".join(str(int(result.data[k][i])) for k in keys)
        counts[bits] = counts.get(bits, 0) + 1
    return counts


def _covariance_from_3q_counts(counts: dict[str, int]) -> np.ndarray:
    """Map 3-qubit counts → 3×3 covariance proxy for TriDelta."""
    total = sum(counts.values())
    if total == 0:
        return np.eye(3) * 0.01

    z = [0.0, 0.0, 0.0]
    zz_pairs = [(0, 1), (1, 2), (0, 2)]
    zz_vals = []
    for i in range(3):
        acc = 0.0
        for bitstring, n in counts.items():
            if len(bitstring) < 3:
                continue
            zi = 1.0 - 2.0 * int(bitstring[i])
            acc += zi * n
        z[i] = acc / total
    for i, j in zz_pairs:
        acc = 0.0
        for bitstring, n in counts.items():
            if len(bitstring) < 3:
                continue
            sign = 1.0 if int(bitstring[i]) == int(bitstring[j]) else -1.0
            acc += sign * n
        zz_vals.append(acc / total)

    obs = np.array([z[0], z[1], zz_vals[0]])
    return np.outer(obs, obs) + 0.005 * np.eye(3)


@dataclass
class CellStabilityState:
    cell_id: int
    line: list[str]
    zzz: float = 0.0
    theta_deg: float = 0.0
    ae_deg: float = 0.0
    sigma: float = 0.0
    heron: float = 0.0
    in_band: bool = False
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL
    depth_layers: int = 14
    abs_gap: float = 0.0
    shots: int = 0

    def to_dict(self) -> dict:
        return {
            "cell_id": self.cell_id,
            "line": self.line,
            "zzz": self.zzz,
            "theta_deg": self.theta_deg,
            "ae_deg": self.ae_deg,
            "sigma": self.sigma,
            "heron": self.heron,
            "in_band": bool(self.in_band),
            "relock_interval": self.relock_interval,
            "depth_layers": self.depth_layers,
            "abs_gap": self.abs_gap,
            "shots": self.shots,
        }


@dataclass
class ChipStabilityResult:
    processor: str = "willow_pink"
    theta_star_deg: float = OPTIMAL_THETA_DEG
    n_cells: int = 0
    n_qubits: int = 0
    shots: int = 0
    cells: list[CellStabilityState] = field(default_factory=list)
    aggregate: dict = field(default_factory=dict)
    elapsed_s: float = 0.0
    verdict: str = "NULL"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "theta_star_deg": self.theta_star_deg,
            "n_cells": self.n_cells,
            "n_qubits": self.n_qubits,
            "shots": self.shots,
            "cells": [c.to_dict() for c in self.cells],
            "aggregate": self.aggregate,
            "elapsed_s": self.elapsed_s,
            "verdict": self.verdict,
            "notes": self.notes,
        }


class ChipStabilityController:
    """
    Closed-loop full-chip stability controller.

    Ae → 0:  |θ_cell − θ*| < ae_tol
    Δσ → ∅:  σ(θ_cell) < sigma_tol  and  in QSD corridor
  """

    def __init__(
        self,
        theta_star_deg: float = OPTIMAL_THETA_DEG,
        base_depth: int = 14,
        base_relock: int = OPTIMAL_RELOCK_INTERVAL,
        ae_tol_deg: float = 3.0,
        sigma_tol: float = 0.05,
        min_relock: int = 2,
        max_relock: int = 8,
        rho: float = 0.85,
        t2_us: float = 100.0,
    ):
        self.theta_star = float(np.radians(theta_star_deg))
        self.theta_star_deg = theta_star_deg
        self.base_depth = base_depth
        self.base_relock = base_relock
        self.ae_tol_deg = ae_tol_deg
        self.sigma_tol = sigma_tol
        self.min_relock = min_relock
        self.max_relock = max_relock
        self.rho = rho
        self.t2_us = t2_us
        self.analyzer = QuantumQSDAnalyzer(theta_target=self.theta_star, rho=rho, t2_us=t2_us)
        self._intervals: dict[int, int] = {}

    def _adapt_relock(self, cell_id: int, in_band: bool) -> int:
        cur = self._intervals.get(cell_id, self.base_relock)
        if in_band:
            cur = min(self.max_relock, cur + 1)
        else:
            cur = max(self.min_relock, cur - 1)
        self._intervals[cell_id] = cur
        return cur

    def _monitor_cell(self, counts: dict[str, int], zzz: float) -> tuple[float, float, float, float, bool]:
        sigma_mat = _covariance_from_3q_counts(counts)
        td = decompose_covariance(sigma_mat, theta_target=self.theta_star)
        ae_deg = float(np.degrees(td.alignment_error))
        theta_rad = float(td.theta)
        sigma = abs(float(phase_force(theta_rad)))
        in_band = (
            abs(ae_deg) <= self.ae_tol_deg
            and sigma <= self.sigma_tol
            and td.in_qsd_corridor
            and td.heron < 1e-6
        )
        return ae_deg, sigma, float(np.degrees(theta_rad)), td.heron, in_band

    def run_cell(
        self,
        sampler,
        line: WillowLine,
        cell_id: int,
        shots: int,
        theta_neg: float | None = None,
    ) -> CellStabilityState:
        _require_cirq()

        theta_neg = theta_neg or negative_control_angle(self.theta_star)
        relock = self._intervals.get(cell_id, self.base_relock)

        c_star = build_depth_sunscreen_circuit(
            line,
            theta=self.theta_star,
            layers=self.base_depth,
            relock_interval=relock,
        )
        r_star = sampler.run(c_star, repetitions=shots)
        counts = _counts_3q(r_star, shots)
        zzz = _zzz_from_result(r_star, shots)
        ae_deg, sigma, theta_deg, heron, in_band = self._monitor_cell(counts, zzz)
        new_relock = self._adapt_relock(cell_id, in_band)

        c_neg = build_depth_sunscreen_circuit(
            line,
            theta=theta_neg,
            layers=self.base_depth,
            relock_interval=relock,
        )
        r_neg = sampler.run(c_neg, repetitions=shots)
        zzz_neg = _zzz_from_result(r_neg, shots)
        abs_gap = abs(zzz - zzz_neg)

        return CellStabilityState(
            cell_id=cell_id,
            line=line.labels(),
            zzz=zzz,
            theta_deg=theta_deg,
            ae_deg=ae_deg,
            sigma=sigma,
            heron=heron,
            in_band=in_band,
            relock_interval=new_relock,
            depth_layers=self.base_depth,
            abs_gap=abs_gap,
            shots=shots,
        )

    def run_chip(
        self,
        shots: int = 400,
        max_cells: int | None = None,
        progress: bool = True,
    ) -> ChipStabilityResult:
        _require_cirq()
        from cirq_google import engine

        t0 = time.time()
        proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
        sampler = proc.get_sampler()
        device = proc.get_device()
        lines = extract_disjoint_3q_lines(device)
        if max_cells is not None:
            lines = lines[:max_cells]

        out = ChipStabilityResult(
            theta_star_deg=self.theta_star_deg,
            n_cells=len(lines),
            n_qubits=len(lines) * 3,
            shots=shots,
        )

        for i, line in enumerate(lines):
            if progress:
                print(f"[chip] cell {i + 1}/{len(lines)} {line.labels()}", flush=True)
            out.cells.append(self.run_cell(sampler, line, i, shots))

        ae_vals = [abs(c.ae_deg) for c in out.cells]
        sig_vals = [c.sigma for c in out.cells]
        gaps = [c.abs_gap for c in out.cells]
        in_band = sum(1 for c in out.cells if c.in_band)
        ae_near_zero = sum(1 for a in ae_vals if a <= self.ae_tol_deg)
        sigma_near_zero = sum(1 for s in sig_vals if s <= self.sigma_tol)

        aurora = check_aurora_condition(rho=self.rho, t2_us=self.t2_us)
        out.aggregate = {
            "ae_median_deg": float(np.median(ae_vals)),
            "ae_mean_deg": float(np.mean(ae_vals)),
            "sigma_median": float(np.median(sig_vals)),
            "sigma_mean": float(np.mean(sig_vals)),
            "abs_gap_median": float(np.median(gaps)),
            "cells_in_band": in_band,
            "cells_ae_near_zero": ae_near_zero,
            "cells_sigma_near_zero": sigma_near_zero,
            "cells_winning": int(sum(1 for g in gaps if g >= 0.05)),
            "aurora_satisfied": bool(aurora.satisfied),
            "zero_dissipation_at_theta_star": bool(is_zero_dissipation(self.theta_star)),
            "optimal_relock_hint": optimal_relock_interval(rho=0.85, t2_us=100.0),
        }
        out.elapsed_s = time.time() - t0

        agg = out.aggregate
        if (
            in_band >= max(1, len(lines) // 2)
            and agg["cells_winning"] >= max(1, len(lines) // 2)
            and agg["sigma_median"] <= 0.15
        ):
            out.verdict = "CHIP_STABLE"
            out.notes = (
                f"Full-chip lock: {in_band}/{len(lines)} cells in band, "
                f"median |Ae|={agg['ae_median_deg']:.2f}°, "
                f"median σ={agg['sigma_median']:.4f}, "
                f"median |ΔZZZ|={agg['abs_gap_median']:.3f}."
            )
        elif agg["cells_winning"] >= max(1, len(lines) // 2):
            out.verdict = "PARTIAL_STABLE"
            out.notes = (
                f"Angle-specific wins on {agg['cells_winning']}/{len(lines)} cells; "
                f"dispersion collapse partial (in-band {in_band}/{len(lines)})."
            )
        else:
            out.verdict = "NULL"
            out.notes = "Chip-wide stability not achieved at current settings."

        return out


def run_chip_stability(
    shots: int = 400,
    max_cells: int | None = None,
    theta_star_deg: float = OPTIMAL_THETA_DEG,
    **kwargs,
) -> ChipStabilityResult:
    """Run full-chip closed-loop stability campaign."""
    ctrl = ChipStabilityController(theta_star_deg=theta_star_deg, **kwargs)
    return ctrl.run_chip(shots=shots, max_cells=max_cells)
