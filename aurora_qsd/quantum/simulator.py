"""Qiskit Aer simulator helpers — hardware-faithful noise and stress tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from qiskit_aer import AerSimulator

from aurora_qsd.core.constants import (
    DEFAULT_K_GAIN,
    DEFAULT_SHOTS,
    THETA_STAR_HW,
    THETA_STAR_HW_DEG,
)
from aurora_qsd.quantum.circuit_builder import (
    build_baseline,
    build_deep_qsd_circuit,
    build_with_relock,
)
from aurora_qsd.quantum.fez_cells import (
    build_zzz_baseline_circuit,
    build_zzz_cell_circuit,
    zzz_correlator,
)
from aurora_qsd.quantum.noise_models import build_simulator
from aurora_qsd.quantum.runner import run_circuit
from aurora_qsd.quantum.sunscreen import build_sunscreen_circuit


# Backward-compatible aliases
def build_ideal_simulator() -> AerSimulator:
    return build_simulator("ideal")


def build_noisy_simulator() -> AerSimulator:
    return build_simulator("native")


def build_apocalyptic_noise_model():
    from aurora_qsd.quantum.noise_models import build_apocalypse_noise_model

    return build_apocalypse_noise_model()


@dataclass
class SweepPoint:
    theta_deg: float
    zzz: float
    gain: float


@dataclass
class StressTestResult:
    baseline_zzz: float
    baseline_std: float
    qsd_at_star_zzz: float
    relock_zzz: float
    sweep: list[SweepPoint] = field(default_factory=list)
    sweep_passes: int = 0
    best_theta_deg: float = 0.0
    best_gain: float = 0.0
    iss_final_closed_deg: float = 0.0
    iss_mean_gain: float = 0.0
    basin: object | None = None
    verdict: str = ""

    def summary(self) -> str:
        lines = [
            f"Baseline ZZZ:     {self.baseline_zzz:.4f} ± {self.baseline_std:.4f}",
            f"QSD @ θ* ({THETA_STAR_HW_DEG}°): {self.qsd_at_star_zzz:.4f}  "
            f"(gain {self.qsd_at_star_zzz - self.baseline_zzz:+.4f})",
            f"QSD sunscreen /8: {self.relock_zzz:.4f}  "
            f"(gain {self.relock_zzz - self.baseline_zzz:+.4f})",
            f"θ sweep passes:   {self.sweep_passes}/17",
            f"Best angle:       {self.best_theta_deg:.2f}° (gain {self.best_gain:+.4f})",
            f"ISS closed-loop:    θ → {self.iss_final_closed_deg:.2f}°",
        ]
        if self.basin:
            lines.append(f"Basin optimum:    {self.basin.optimal_theta_deg:.2f}° (ZZZ {self.basin.optimal_zzz:+.4f})")
        lines.append(f"VERDICT:          {self.verdict}")
        return "\n".join(lines)


def run_stress_test(
    shots: int = DEFAULT_SHOTS,
    layers: int = 12,
    noise: str = "native",
    seed: int | None = 42,
    use_3q: bool = True,
) -> StressTestResult:
    """Hardware-faithful 3-stage stress test with optional 3-qubit ZZZ cells."""
    if seed is not None:
        np.random.seed(seed)

    sim = build_simulator(noise)
    result = StressTestResult(baseline_zzz=0.0, baseline_std=0.0, qsd_at_star_zzz=0.0, relock_zzz=0.0)

    if use_3q:
        b_circ = lambda d: build_zzz_baseline_circuit(d)
        q_circ = lambda t, d: build_zzz_cell_circuit(theta=t, depth=d)
        s_circ = lambda t, d: build_sunscreen_circuit(theta=t, total_layers=d, reset_interval=8)
        zzz_fn = lambda c: zzz_correlator(c, n_qubits=3)
    else:
        b_circ = build_baseline
        q_circ = lambda t, d: build_deep_qsd_circuit(t, d)
        s_circ = lambda t, d: build_with_relock(theta=t, total_layers=d, relock_interval=7)
        from aurora_qsd.quantum.circuit_builder import zzz_score as zzz_fn

    b_scores = [zzz_fn(run_circuit(b_circ(layers), sim, shots)) for _ in range(3)]
    result.baseline_zzz = float(np.mean(b_scores))
    result.baseline_std = float(np.std(b_scores))

    qsd_scores = [zzz_fn(run_circuit(q_circ(THETA_STAR_HW, layers), sim, shots)) for _ in range(3)]
    result.qsd_at_star_zzz = float(np.mean(qsd_scores))

    rl_scores = [zzz_fn(run_circuit(s_circ(THETA_STAR_HW, layers), sim, shots)) for _ in range(3)]
    result.relock_zzz = float(np.mean(rl_scores))

    for d in np.linspace(-8, 8, 17):
        theta = THETA_STAR_HW + np.radians(d)
        ss = [zzz_fn(run_circuit(q_circ(theta, layers), sim, shots)) for _ in range(2)]
        s = float(np.mean(ss))
        g = s - result.baseline_zzz
        result.sweep.append(SweepPoint(theta_deg=float(np.degrees(theta)), zzz=s, gain=g))
        if g > 0:
            result.sweep_passes += 1
        if g > result.best_gain:
            result.best_gain = g
            result.best_theta_deg = float(np.degrees(theta))

    theta_open = np.radians(45.0)
    theta_closed = np.radians(45.0)
    gains = []
    for _ in range(10):
        theta_open += np.random.normal(0, np.radians(4.5))
        theta_closed -= DEFAULT_K_GAIN * (theta_closed - THETA_STAR_HW)
        co = zzz_fn(run_circuit(q_circ(theta_open, layers), sim, shots))
        cc = zzz_fn(run_circuit(q_circ(theta_closed, layers), sim, shots))
        gains.append(cc - co)

    result.iss_final_closed_deg = float(np.degrees(theta_closed))
    result.iss_mean_gain = float(np.mean(gains))
    result.basin = __import__(
        "aurora_qsd.quantum.basin_sweep", fromlist=["run_basin_sweep"]
    ).run_basin_sweep(shots=shots, depth=layers, noise=noise, seed=seed)
    result.verdict = "COHERENCE RECOVERED" if result.sweep_passes >= 8 else "UNABLE TO RECOVER"
    return result
