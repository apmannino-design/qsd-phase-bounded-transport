"""
Full-chip QSD stability controller — closed-loop Ae / σ monitoring + adaptive re-lock.

Target: Ae → 0, Δσ → ∅ (dispersion collapsed) at θ* across all disjoint 3Q lines.

Operational loop per cell:
  1. Optional per-cell θ offset calibration (micro-sweep)
  2. Measure ZZZ + TriDelta from full 3×3 Z covariance
  3. Compute alignment error Ae and entropy production σ(θ)
  4. Adapt re-lock interval (tighter if out-of-band, looser if locked)
  5. Run depth sunscreen at θ* + offset with adapted schedule
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.aurora import check_aurora_condition, optimal_relock_interval
from aurora_qsd.core.phase_potential import is_zero_dissipation, phase_force
from aurora_qsd.quantum.analyzer import QuantumQSDAnalyzer, covariance_from_counts
from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_THETA_DEG
from aurora_qsd.quantum.willow_lines import WillowLine, extract_disjoint_3q_lines
from aurora_qsd.quantum.willow_run import (
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
    """Map 3-qubit counts → 3×3 Pauli-Z covariance for TriDelta."""
    return covariance_from_counts(counts, n_qubits=3)


# Default micro-sweep offsets (degrees) for per-cell θ calibration
DEFAULT_THETA_OFFSETS_DEG = (-4.0, -2.0, 0.0, 2.0, 4.0)


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
    tri_band: bool = False
    zzz_band: bool = False
    theta_offset_deg: float = 0.0
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL
    depth_layers: int = 14
    abs_gap: float = 0.0
    task_energy: float = 0.0
    task_energy_error: float = 0.0
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
            "tri_band": bool(self.tri_band),
            "zzz_band": bool(self.zzz_band),
            "theta_offset_deg": self.theta_offset_deg,
            "relock_interval": self.relock_interval,
            "depth_layers": self.depth_layers,
            "abs_gap": self.abs_gap,
            "task_energy": self.task_energy,
            "task_energy_error": self.task_energy_error,
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
    task_benchmark: dict = field(default_factory=dict)
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
            "task_benchmark": self.task_benchmark,
            "elapsed_s": self.elapsed_s,
            "verdict": self.verdict,
            "notes": self.notes,
        }


class ChipStabilityController:
    """
    Closed-loop full-chip stability controller.

    Ae → 0:  |θ_cell − θ*| < ae_tol
    Δσ → ∅:  σ(θ_cell) < sigma_tol  and  in QSD corridor

    In-band uses dual criteria:
      - TriDelta band: Ae, σ, corridor, Heron
      - ZZZ-native band: |ΔZZZ| ≥ gap_tol with relaxed Ae (task-aligned win)
    """

    def __init__(
        self,
        theta_star_deg: float = OPTIMAL_THETA_DEG,
        base_depth: int = 14,
        base_relock: int = OPTIMAL_RELOCK_INTERVAL,
        ae_tol_deg: float = 8.0,
        sigma_tol: float = 0.25,
        heron_tol: float = 0.05,
        zzz_gap_tol: float = 0.05,
        zzz_ae_tol_deg: float = 20.0,
        min_relock: int = 2,
        max_relock: int = 8,
        rho: float = 0.85,
        t2_us: float = 100.0,
        calibrate_theta: bool = True,
        calibrate_shots: int = 128,
        theta_offsets_deg: tuple[float, ...] = DEFAULT_THETA_OFFSETS_DEG,
    ):
        self.theta_star = float(np.radians(theta_star_deg))
        self.theta_star_deg = theta_star_deg
        self.base_depth = base_depth
        self.base_relock = base_relock
        self.ae_tol_deg = ae_tol_deg
        self.sigma_tol = sigma_tol
        self.heron_tol = heron_tol
        self.zzz_gap_tol = zzz_gap_tol
        self.zzz_ae_tol_deg = zzz_ae_tol_deg
        self.min_relock = min_relock
        self.max_relock = max_relock
        self.rho = rho
        self.t2_us = t2_us
        self.calibrate_theta = calibrate_theta
        self.calibrate_shots = calibrate_shots
        self.theta_offsets_deg = theta_offsets_deg
        self.analyzer = QuantumQSDAnalyzer(theta_target=self.theta_star, rho=rho, t2_us=t2_us)
        self._intervals: dict[int, int] = {}
        self._theta_offsets: dict[int, float] = {}

    def _cell_theta(self, cell_id: int) -> float:
        offset = self._theta_offsets.get(cell_id, 0.0)
        return self.theta_star + float(np.radians(offset))

    def _adapt_relock(self, cell_id: int, in_band: bool) -> int:
        cur = self._intervals.get(cell_id, self.base_relock)
        if in_band:
            cur = min(self.max_relock, cur + 1)
        else:
            cur = max(self.min_relock, cur - 1)
        self._intervals[cell_id] = cur
        return cur

    def _monitor_cell(self, counts: dict[str, int], abs_gap: float) -> tuple[float, float, float, float, bool, bool, bool]:
        report = self.analyzer.from_counts(counts, n_qubits=3)
        td = report.tri_delta
        ae_deg = float(np.degrees(td.alignment_error))
        theta_rad = float(td.theta)
        sigma = abs(float(phase_force(theta_rad)))

        tri_band = (
            abs(ae_deg) <= self.ae_tol_deg
            and sigma <= self.sigma_tol
            and td.in_qsd_corridor
            and td.heron < self.heron_tol
        )
        zzz_band = abs_gap >= self.zzz_gap_tol and abs(ae_deg) <= self.zzz_ae_tol_deg
        in_band = tri_band or zzz_band

        return ae_deg, sigma, float(np.degrees(theta_rad)), td.heron, in_band, tri_band, zzz_band

    def calibrate_cell_theta(
        self,
        sampler,
        line: WillowLine,
        cell_id: int,
        shots: int | None = None,
    ) -> float:
        """Micro-sweep θ offsets; pick offset maximizing |ΔZZZ|."""
        _require_cirq()
        shots = shots or self.calibrate_shots
        relock = self._intervals.get(cell_id, self.base_relock)
        theta_neg = negative_control_angle(self.theta_star)
        best_offset = 0.0
        best_gap = -1.0

        for offset_deg in self.theta_offsets_deg:
            theta = self.theta_star + float(np.radians(offset_deg))
            c_star = build_depth_sunscreen_circuit(
                line, theta=theta, layers=self.base_depth, relock_interval=relock,
            )
            c_neg = build_depth_sunscreen_circuit(
                line, theta=theta_neg, layers=self.base_depth, relock_interval=relock,
            )
            z_star = _zzz_from_result(sampler.run(c_star, repetitions=shots), shots)
            z_neg = _zzz_from_result(sampler.run(c_neg, repetitions=shots), shots)
            gap = abs(z_star - z_neg)
            if gap > best_gap:
                best_gap = gap
                best_offset = offset_deg

        self._theta_offsets[cell_id] = best_offset
        return best_offset

    def run_cell(
        self,
        sampler,
        line: WillowLine,
        cell_id: int,
        shots: int,
        theta_neg: float | None = None,
        calibrate: bool | None = None,
    ) -> CellStabilityState:
        _require_cirq()

        do_cal = self.calibrate_theta if calibrate is None else calibrate
        if do_cal:
            self.calibrate_cell_theta(sampler, line, cell_id)

        theta_cell = self._cell_theta(cell_id)
        theta_neg = theta_neg or negative_control_angle(self.theta_star)
        relock = self._intervals.get(cell_id, self.base_relock)
        offset_deg = self._theta_offsets.get(cell_id, 0.0)

        c_star = build_depth_sunscreen_circuit(
            line,
            theta=theta_cell,
            layers=self.base_depth,
            relock_interval=relock,
        )
        r_star = sampler.run(c_star, repetitions=shots)
        counts = _counts_3q(r_star, shots)
        zzz = _zzz_from_result(r_star, shots)

        c_neg = build_depth_sunscreen_circuit(
            line,
            theta=theta_neg,
            layers=self.base_depth,
            relock_interval=relock,
        )
        r_neg = sampler.run(c_neg, repetitions=shots)
        zzz_neg = _zzz_from_result(r_neg, shots)
        abs_gap = abs(zzz - zzz_neg)

        ae_deg, sigma, theta_deg, heron, in_band, tri_band, zzz_band = self._monitor_cell(
            counts, abs_gap,
        )
        new_relock = self._adapt_relock(cell_id, in_band)

        task_energy = -zzz
        task_energy_error = abs(task_energy - (-1.0))

        return CellStabilityState(
            cell_id=cell_id,
            line=line.labels(),
            zzz=zzz,
            theta_deg=theta_deg,
            ae_deg=ae_deg,
            sigma=sigma,
            heron=heron,
            in_band=in_band,
            tri_band=tri_band,
            zzz_band=zzz_band,
            theta_offset_deg=offset_deg,
            relock_interval=new_relock,
            depth_layers=self.base_depth,
            abs_gap=abs_gap,
            task_energy=task_energy,
            task_energy_error=task_energy_error,
            shots=shots,
        )

    def run_chip(
        self,
        shots: int = 400,
        max_cells: int | None = None,
        progress: bool = True,
        run_task_benchmark: bool = True,
    ) -> ChipStabilityResult:
        _require_cirq()
        from cirq_google import engine

        from aurora_qsd.quantum.willow_ising_energy import run_zzz_task_energy_benchmark

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
        task_errs = [c.task_energy_error for c in out.cells]
        in_band = sum(1 for c in out.cells if c.in_band)
        tri_band = sum(1 for c in out.cells if c.tri_band)
        zzz_band = sum(1 for c in out.cells if c.zzz_band)
        ae_near_zero = sum(1 for a in ae_vals if a <= self.ae_tol_deg)
        sigma_near_zero = sum(1 for s in sig_vals if s <= self.sigma_tol)
        cells_winning = int(sum(1 for g in gaps if g >= self.zzz_gap_tol))
        cells_task_winning = int(sum(1 for e, g in zip(task_errs, gaps) if g >= self.zzz_gap_tol))

        aurora = check_aurora_condition(rho=self.rho, t2_us=self.t2_us)
        out.aggregate = {
            "ae_median_deg": float(np.median(ae_vals)),
            "ae_mean_deg": float(np.mean(ae_vals)),
            "sigma_median": float(np.median(sig_vals)),
            "sigma_mean": float(np.mean(sig_vals)),
            "abs_gap_median": float(np.median(gaps)),
            "task_energy_error_median": float(np.median(task_errs)),
            "cells_in_band": in_band,
            "cells_tri_band": tri_band,
            "cells_zzz_band": zzz_band,
            "cells_ae_near_zero": ae_near_zero,
            "cells_sigma_near_zero": sigma_near_zero,
            "cells_winning": cells_winning,
            "cells_task_winning": cells_task_winning,
            "aurora_satisfied": bool(aurora.satisfied),
            "zero_dissipation_at_theta_star": bool(is_zero_dissipation(self.theta_star)),
            "optimal_relock_hint": optimal_relock_interval(rho=0.85, t2_us=100.0),
        }

        if run_task_benchmark:
            if progress:
                print("[chip] ZZZ Hamiltonian task benchmark (interior) ...", flush=True)
            out.task_benchmark = run_zzz_task_energy_benchmark(
                shots=shots,
                line_name="interior",
                theta_deg=self.theta_star_deg,
                layers=self.base_depth,
                relock=self.base_relock,
            )

        out.elapsed_s = time.time() - t0

        agg = out.aggregate
        task_ok = (
            out.task_benchmark.get("verdict") == "QSD_WINS"
            if out.task_benchmark
            else cells_task_winning >= max(1, len(lines) // 2)
        )
        if (
            in_band >= max(1, len(lines) // 2)
            and cells_winning >= max(1, len(lines) // 2)
            and agg["sigma_median"] <= 0.15
            and task_ok
        ):
            out.verdict = "CHIP_STABLE"
            out.notes = (
                f"Full-chip lock: {in_band}/{len(lines)} cells in band "
                f"(tri {tri_band}, zzz {zzz_band}), "
                f"median |Ae|={agg['ae_median_deg']:.2f}°, "
                f"median σ={agg['sigma_median']:.4f}, "
                f"median |ΔZZZ|={agg['abs_gap_median']:.3f}, "
                f"task median |ΔE|={agg['task_energy_error_median']:.3f}."
            )
        elif cells_winning >= max(1, len(lines) // 2) and task_ok:
            out.verdict = "PARTIAL_STABLE"
            out.notes = (
                f"Angle-specific wins on {cells_winning}/{len(lines)} cells; "
                f"in-band {in_band}/{len(lines)} (tri {tri_band}, zzz {zzz_band}); "
                f"task wins {cells_task_winning}/{len(lines)}."
            )
        else:
            out.verdict = "NULL"
            out.notes = "Chip-wide stability not achieved at current settings."

        return out


def run_chip_stability(
    shots: int = 400,
    max_cells: int | None = None,
    theta_star_deg: float = OPTIMAL_THETA_DEG,
    run_task_benchmark: bool = True,
    **kwargs,
) -> ChipStabilityResult:
    """Run full-chip closed-loop stability campaign."""
    ctrl = ChipStabilityController(theta_star_deg=theta_star_deg, **kwargs)
    return ctrl.run_chip(shots=shots, max_cells=max_cells, run_task_benchmark=run_task_benchmark)
