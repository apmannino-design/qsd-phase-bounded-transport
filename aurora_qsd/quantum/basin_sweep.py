"""Basin sweep — find empirical θ optimum before lock (ibm_fez protocol)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_HW, THETA_STAR_HW_DEG
from aurora_qsd.quantum.fez_cells import (
    build_zzz_baseline_circuit,
    build_zzz_cell_circuit,
    negative_control_angle,
    zzz_correlator,
)
from aurora_qsd.quantum.noise_models import build_simulator
from aurora_qsd.quantum.runner import run_circuit


@dataclass
class BasinSweepResult:
    """Result of basin angle sweep."""

    theta_star_deg: float
    optimal_theta_deg: float
    optimal_zzz: float
    baseline_zzz: float
    negative_control_zzz: float
    gain_vs_baseline: float
    gain_vs_neg_control: float
    sweep_points: list[tuple[float, float]]
    in_basin: bool

    def summary(self) -> str:
        return (
            f"Basin sweep: optimal θ = {self.optimal_theta_deg:.2f}° "
            f"(ZZZ = {self.optimal_zzz:+.4f}, gain vs baseline {self.gain_vs_baseline:+.4f}, "
            f"vs neg control {self.gain_vs_neg_control:+.4f})"
        )


def run_basin_sweep(
    shots: int = 4096,
    depth: int = 12,
    sweep_deg: tuple[float, float] = (-20.0, 20.0),
    n_points: int = 21,
    noise: str = "native",
    seed: int | None = 42,
) -> BasinSweepResult:
    """
    Sweep partition angle around θ* and select basin peak (ibm_fez basin sweep).

    Hardware used 20 points per cell; default ±20° matches full-chip optimization.
    """
    if seed is not None:
        np.random.seed(seed)

    sim = build_simulator(noise)
    baseline_zzz = zzz_correlator(
        run_circuit(build_zzz_baseline_circuit(depth), sim, shots), n_qubits=3,
    )
    neg_zzz = zzz_correlator(
        run_circuit(
            build_zzz_cell_circuit(theta=negative_control_angle(), depth=depth),
            sim,
            shots,
        ),
        n_qubits=3,
    )

    points: list[tuple[float, float]] = []
    best_theta = THETA_STAR_HW
    best_zzz = -1.0

    for d in np.linspace(sweep_deg[0], sweep_deg[1], n_points):
        theta = THETA_STAR_HW + np.radians(d)
        counts = run_circuit(build_zzz_cell_circuit(theta=theta, depth=depth), sim, shots)
        zzz = zzz_correlator(counts, n_qubits=3)
        deg = float(np.degrees(theta))
        points.append((deg, zzz))
        if zzz > best_zzz:
            best_zzz = zzz
            best_theta = theta

    opt_deg = float(np.degrees(best_theta))
    return BasinSweepResult(
        theta_star_deg=THETA_STAR_HW_DEG,
        optimal_theta_deg=opt_deg,
        optimal_zzz=float(best_zzz),
        baseline_zzz=float(baseline_zzz),
        negative_control_zzz=float(neg_zzz),
        gain_vs_baseline=float(best_zzz - baseline_zzz),
        gain_vs_neg_control=float(best_zzz - neg_zzz),
        sweep_points=points,
        in_basin=abs(opt_deg - THETA_STAR_HW_DEG) <= 20.0,
    )
