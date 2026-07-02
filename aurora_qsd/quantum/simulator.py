"""Qiskit Aer simulator helpers — hardware-faithful noise and stress tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from qiskit import transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    amplitude_damping_error,
    depolarizing_error,
    phase_damping_error,
)

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
    zzz_score,
)


def build_apocalyptic_noise_model() -> NoiseModel:
    """
    FakeFez + stacked decoherence (reference implementation noise stack).

    T1=25%, T2=35%, 1Q depol=20%, 2Q depol=40%.
    """
    try:
        from qiskit_ibm_runtime.fake_provider import FakeFez

        nm = NoiseModel.from_backend(FakeFez())
    except ImportError:
        nm = NoiseModel()

    t1 = amplitude_damping_error(0.25)
    t2 = phase_damping_error(0.35)
    dp1 = depolarizing_error(0.20, 1)
    dp2 = depolarizing_error(0.40, 2)
    sq = dp1.compose(t1).compose(t2)
    gates_1q = ["u1", "u2", "u3", "ry", "rx", "rz", "h", "x"]
    nm.add_all_qubit_quantum_error(sq, gates_1q)
    nm.add_all_qubit_quantum_error(dp2, ["cx", "ecr"])
    return nm


def build_ideal_simulator() -> AerSimulator:
    return AerSimulator()


def build_noisy_simulator() -> AerSimulator:
    return AerSimulator(noise_model=build_apocalyptic_noise_model())


def run_circuit(
    qc,
    sim: AerSimulator | None = None,
    shots: int = DEFAULT_SHOTS,
) -> dict[str, int]:
    sim = sim or build_ideal_simulator()
    compiled = transpile(qc, sim, optimization_level=0)
    return sim.run(compiled, shots=shots).result().get_counts()


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
    verdict: str = ""

    def summary(self) -> str:
        lines = [
            f"Baseline ZZZ:     {self.baseline_zzz:.4f} ± {self.baseline_std:.4f}",
            f"QSD @ θ* ({THETA_STAR_HW_DEG}°): {self.qsd_at_star_zzz:.4f}  "
            f"(gain {self.qsd_at_star_zzz - self.baseline_zzz:+.4f})",
            f"QSD re-lock /7:   {self.relock_zzz:.4f}  "
            f"(gain {self.relock_zzz - self.baseline_zzz:+.4f})",
            f"θ sweep passes:   {self.sweep_passes}/17",
            f"Best angle:       {self.best_theta_deg:.2f}° (gain {self.best_gain:+.4f})",
            f"ISS closed-loop:    θ → {self.iss_final_closed_deg:.2f}°",
            f"VERDICT:          {self.verdict}",
        ]
        return "\n".join(lines)


def run_stress_test(
    shots: int = DEFAULT_SHOTS,
    layers: int = 12,
    noisy: bool = True,
    seed: int | None = 42,
) -> StressTestResult:
    """
    Full 3-stage stress test matching code/qsd_reference_implementation.py.

    Stage 1: Baseline score
    Stage 2: θ sweep ±8° around θ*
    Stage 3: ISS closed-loop convergence
    """
    if seed is not None:
        np.random.seed(seed)

    sim = build_noisy_simulator() if noisy else build_ideal_simulator()
    result = StressTestResult(baseline_zzz=0.0, baseline_std=0.0, qsd_at_star_zzz=0.0, relock_zzz=0.0)

    # Stage 1: baseline
    b_scores = [zzz_score(run_circuit(build_baseline(layers), sim, shots)) for _ in range(3)]
    result.baseline_zzz = float(np.mean(b_scores))
    result.baseline_std = float(np.std(b_scores))

    # QSD at θ* and re-lock
    qsd_scores = [
        zzz_score(run_circuit(build_deep_qsd_circuit(THETA_STAR_HW, layers), sim, shots))
        for _ in range(3)
    ]
    result.qsd_at_star_zzz = float(np.mean(qsd_scores))

    rl_scores = [
        zzz_score(run_circuit(build_with_relock(total_layers=layers, relock_interval=7), sim, shots))
        for _ in range(3)
    ]
    result.relock_zzz = float(np.mean(rl_scores))

    # Stage 2: sweep
    for d in np.linspace(-8, 8, 17):
        theta = THETA_STAR_HW + np.radians(d)
        ss = [
            zzz_score(run_circuit(build_deep_qsd_circuit(theta, layers), sim, shots))
            for _ in range(2)
        ]
        s = float(np.mean(ss))
        g = s - result.baseline_zzz
        result.sweep.append(SweepPoint(theta_deg=float(np.degrees(theta)), zzz=s, gain=g))
        if g > 0:
            result.sweep_passes += 1
        if g > result.best_gain:
            result.best_gain = g
            result.best_theta_deg = float(np.degrees(theta))

    # Stage 3: ISS convergence
    theta_open = 45.0 * (np.pi / 180)
    theta_closed = 45.0 * (np.pi / 180)
    gains = []
    for _ in range(10):
        theta_open += np.random.normal(0, np.radians(4.5))
        theta_closed -= DEFAULT_K_GAIN * (theta_closed - THETA_STAR_HW)
        co = zzz_score(run_circuit(build_deep_qsd_circuit(theta_open, layers), sim, shots))
        cc = zzz_score(run_circuit(build_deep_qsd_circuit(theta_closed, layers), sim, shots))
        gains.append(cc - co)

    result.iss_final_closed_deg = float(np.degrees(theta_closed))
    result.iss_mean_gain = float(np.mean(gains))
    result.verdict = "COHERENCE RECOVERED" if result.sweep_passes >= 8 else "UNABLE TO RECOVER"

    return result
