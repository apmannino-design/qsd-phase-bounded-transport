"""Willow / 3Q apocalypse-max hold test — 1241L + stacked max noise."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_WILLOW_HW_DEG
from aurora_qsd.quantum.extreme_stress import build_apocalypse_simulator
from aurora_qsd.quantum.fez_cells import build_zzz_cell_circuit, negative_control_angle, zzz_correlator
from aurora_qsd.quantum.willow_gain_sweep import OPTIMAL_THETA_DEG, OPTIMAL_RELOCK_INTERVAL
from aurora_qsd.quantum.willow_run import (
    _depth_head_to_head,
    _require_cirq,
    build_depth_sunscreen_circuit,
    run_willow_max,
)
from aurora_qsd.quantum.willow_lines import get_line


def _run_qiskit_zzz(
    theta: float,
    depth: int,
    relock: int,
    shots: int,
) -> float:
    from qiskit import transpile

    sim = build_apocalypse_simulator()
    qc = build_zzz_cell_circuit(theta=theta, depth=depth, relock_interval=relock)
    qc = transpile(qc, sim)
    counts = sim.run(qc, shots=shots).result().get_counts()
    return zzz_correlator(counts, 3)


@dataclass
class ApocalypseHoldResult:
    processor: str = "apocalypse_qiskit_3q"
    theta_star_deg: float = OPTIMAL_THETA_DEG
    depth_layers: int = 1241
    relock_interval: int = 3
    shots: int = 0
    qsd: dict = field(default_factory=dict)
    wrong: dict = field(default_factory=dict)
    abs_gap: float = 0.0
    holds: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "theta_star_deg": self.theta_star_deg,
            "depth_layers": self.depth_layers,
            "relock_interval": self.relock_interval,
            "shots": self.shots,
            "qsd": self.qsd,
            "wrong": self.wrong,
            "abs_gap": self.abs_gap,
            "holds": self.holds,
            "notes": self.notes,
        }


def run_apocalypse_hold(
    shots: int = 2048,
    depth_layers: int = 1241,
    theta_deg: float = OPTIMAL_THETA_DEG,
    relock_interval: int = 3,
) -> ApocalypseHoldResult:
    """Max noise (apocalypse stack) + max depth 1241L on 3Q ZZZ sunscreen."""
    theta = float(np.radians(theta_deg))
    theta_neg = negative_control_angle(theta)

    z_star = _run_qiskit_zzz(theta, depth_layers, relock_interval, shots)
    z_wrong = _run_qiskit_zzz(theta_neg, depth_layers, relock_interval, shots)
    gap = abs(z_star - z_wrong)

    out = ApocalypseHoldResult(
        shots=shots,
        depth_layers=depth_layers,
        theta_star_deg=theta_deg,
        relock_interval=relock_interval,
        qsd={"zzz": z_star, "n": shots},
        wrong={"zzz": z_wrong, "n": shots},
        abs_gap=gap,
    )
    out.holds = gap >= 0.05
    out.notes = (
        f"Apocalypse 1241L @ θ*={theta_deg}°: ZZZ {z_star:+.3f} vs wrong {z_wrong:+.3f} "
        f"(|Δ|={gap:.3f}) — {'HOLD' if out.holds else 'weak'}."
    )
    return out


def run_willow_pink_max_hold(
    shots: int = 500,
    depth_layers: int = 1241,
    theta_deg: float = OPTIMAL_THETA_DEG,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
) -> dict:
    """Willow willow_pink native noise + max depth."""
    _require_cirq()
    from cirq_google import engine

    line = get_line("interior")
    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()
    theta = float(np.radians(theta_deg))
    theta_neg = negative_control_angle(theta)
    row = _depth_head_to_head(
        sampler, line, shots, theta, theta_neg, depth_layers, relock_interval
    )
    return {
        "processor": "willow_pink",
        "depth_layers": depth_layers,
        "theta_star_deg": theta_deg,
        "relock_interval": relock_interval,
        "shots": shots,
        **row,
        "holds": row["abs_gap"] >= 0.05,
    }


def run_max_max_campaign(
    shots_apocalypse: int = 2048,
    shots_willow: int = 500,
) -> dict:
    """Full max-noise + max-depth hold campaign."""
    print("[max_max] apocalypse 1241L relock/3 ...", flush=True)
    apoc = run_apocalypse_hold(shots=shots_apocalypse, depth_layers=1241, relock_interval=3)
    print(apoc.notes, flush=True)

    print("[max_max] willow_pink 1241L optimum settings ...", flush=True)
    willow = run_willow_pink_max_hold(
        shots=shots_willow,
        depth_layers=1241,
        theta_deg=OPTIMAL_THETA_DEG,
        relock_interval=OPTIMAL_RELOCK_INTERVAL,
    )
    print(
        f"Willow: |Δ|={willow['abs_gap']:.3f} holds={willow['holds']}",
        flush=True,
    )

    verdict = "HOLD" if apoc.holds and willow["holds"] else "PARTIAL" if (apoc.holds or willow["holds"]) else "FAIL"
    return {
        "verdict": verdict,
        "apocalypse_1241": apoc.to_dict(),
        "willow_pink_1241": willow,
        "notes": (
            "Max depth 1241L with apocalypse stacked noise and Willow native noise. "
            f"Apocalypse |Δ|={apoc.abs_gap:.3f}, Willow |Δ|={willow['abs_gap']:.3f}."
        ),
    }
