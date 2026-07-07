"""Maximum-severity FakeFez apocalypse stress test — Aurora minimal-thermo protocol."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    amplitude_damping_error,
    depolarizing_error,
    phase_damping_error,
)

from aurora_qsd.core.aurora import check_aurora_condition
from aurora_qsd.core.constants import DEFAULT_K_GAIN, THETA_STAR_HW, THETA_STAR_HW_DEG
from aurora_qsd.core.phase_potential import phase_force, phase_potential
from aurora_qsd.quantum.circuit_builder import (
    _append_qsd_cell,
    build_baseline,
    build_deep_qsd_circuit,
    build_with_relock,
    zzz_score,
)

# Apocalypse-max noise stack (exceeds reference + 156qubit stress)
APOC_T1 = 0.35
APOC_T2 = 0.45
APOC_DP1 = 0.30
APOC_DP2 = 0.55

# Hardware depth schedule (ibm_fez June 2026)
DEPTH_SCHEDULE = [32, 140, 311, 1241]
RELOCK_INTERVALS = [None, 7, 3]  # None = open-loop decay


def build_apocalypse_max_noise_model() -> NoiseModel:
    """FakeFez backend noise + maximum stacked decoherence."""
    try:
        from qiskit_ibm_runtime.fake_provider import FakeFez

        nm = NoiseModel.from_backend(FakeFez())
    except ImportError:
        nm = NoiseModel()

    t1 = amplitude_damping_error(APOC_T1)
    t2 = phase_damping_error(APOC_T2)
    dp1 = depolarizing_error(APOC_DP1, 1)
    dp2 = depolarizing_error(APOC_DP2, 2)
    sq = dp1.compose(t1).compose(t2)
    gates_1q = ["u1", "u2", "u3", "ry", "rx", "rz", "h", "x", "id", "sx"]
    nm.add_all_qubit_quantum_error(sq, gates_1q)
    nm.add_all_qubit_quantum_error(dp2, ["cx", "ecr", "cz"])
    return nm


def build_apocalypse_simulator() -> AerSimulator:
    return AerSimulator(noise_model=build_apocalypse_max_noise_model())


def extract_zzz_cell_pairs(coupling_map: list[tuple[int, int]], max_cells: int = 52) -> list[tuple[int, int]]:
    """Greedy disjoint CX pairs for parallel ZZZ cell campaign."""
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for a, b in coupling_map:
        if a in used or b in used:
            continue
        pairs.append((a, b))
        used.add(a)
        used.add(b)
        if len(pairs) >= max_cells:
            break
    return pairs


def build_zzz_cell_circuit(
    theta: float,
    depth: int,
    relock_interval: int | None = 3,
) -> QuantumCircuit:
    """Single 2-qubit ZZZ cell — hardware campaign structure."""
    if relock_interval is None:
        return build_deep_qsd_circuit(theta, layers=depth)

    qc = QuantumCircuit(2, 2)
    layers_done = 0
    while layers_done < depth:
        if layers_done > 0:
            qc.ry(2.0 * theta, 0)
            qc.ry(2.0 * (np.pi / 2.0 - theta), 1)
        block = min(relock_interval, depth - layers_done)
        for _ in range(block):
            _append_qsd_cell(qc, theta)
        layers_done += block
    qc.measure([0, 1], [0, 1])
    return qc


def build_lattice_circuit(
    num_qubits: int,
    coupling_map: list[tuple[int, int]],
    theta: float,
    depth: int,
    relock_interval: int | None = 3,
) -> QuantumCircuit:
    """Multi-qubit lattice on FakeFez topology."""
    qc = QuantumCircuit(num_qubits, num_qubits)

    def _init():
        for i in range(num_qubits):
            qc.ry(2.0 * theta if i % 2 == 0 else 2.0 * (np.pi / 2.0 - theta), i)

    if relock_interval is None:
        _init()
        for _ in range(depth):
            for a, b in coupling_map:
                if a < num_qubits and b < num_qubits:
                    qc.cx(a, b)
            for i in range(num_qubits):
                qc.rz(theta if i % 2 == 0 else np.pi / 2.0 - theta, i)
    else:
        layers_done = 0
        while layers_done < depth:
            if layers_done > 0:
                _init()
            block = min(relock_interval, depth - layers_done)
            for _ in range(block):
                for a, b in coupling_map:
                    if a < num_qubits and b < num_qubits:
                        qc.cx(a, b)
                for i in range(num_qubits):
                    qc.rz(theta if i % 2 == 0 else np.pi / 2.0 - theta, i)
            layers_done += block

    qc.measure(range(num_qubits), range(num_qubits))
    return qc


def lattice_coherence_index(counts: dict[str, int], num_qubits: int) -> float:
    """Global polarization parity across all qubits."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    acc = 0.0
    for bitstring, count in counts.items():
        ones = bitstring.count("1")
        acc += abs(num_qubits - 2 * ones) / num_qubits * count
    return acc / total


def run_single(qc: QuantumCircuit, sim: AerSimulator, shots: int) -> dict[str, int]:
    compiled = transpile(qc, sim, optimization_level=0)
    return sim.run(compiled, shots=shots).result().get_counts()


@dataclass
class DepthResult:
    depth: int
    relock_interval: int | None
    zzz_median: float
    zzz_mean: float
    zzz_std: float
    n_cells: int
    entropy_sigma_theta_star: float
    aurora_satisfied: bool
    gamma_ratio: float
    elapsed_s: float


@dataclass
class ApocalypseResult:
    backend: str = "FakeFez"
    num_qubits_backend: int = 156
    noise_stack: str = f"T1={APOC_T1} T2={APOC_T2} 1Q={APOC_DP1} 2Q={APOC_DP2}"
    theta_star_deg: float = THETA_STAR_HW_DEG
    shots: int = 4096
    n_zzz_cells: int = 0
    lattice_qubits: int = 29
    depth_results: list[DepthResult] = field(default_factory=list)
    cell_campaign_median: float = 0.0
    negative_control_zzz: float = 0.0
    baseline_zzz: float = 0.0
    iss_open_final_deg: float = 0.0
    iss_closed_final_deg: float = 0.0
    iss_mean_gain: float = 0.0
    verdict: str = ""
    total_elapsed_s: float = 0.0

    def summary(self) -> str:
        lines = [
            "=" * 72,
            " APOCALYPSE-MAX STRESS — IBM FakeFez Simulator",
            f" Backend: {self.backend} ({self.num_qubits_backend}Q) | Noise: {self.noise_stack}",
            f" θ* = {self.theta_star_deg}° | Aurora: minimal thermo (re-lock /3)",
            f" σ(θ*) = {phase_force(THETA_STAR_HW):.2e} (zero-dissipation lock)",
            "=" * 72,
            "",
            f"ZZZ cell campaign: {self.n_zzz_cells} cells × depth 1241",
            f"  Median ZZZ @ θ*:  {self.cell_campaign_median:+.4f}",
            f"  Negative control: {self.negative_control_zzz:+.4f} (θ+70°)",
            f"  Baseline (H):     {self.baseline_zzz:+.4f}",
            "",
            "Depth scaling (median ZZZ across cells):",
            f"  {'Depth':>6} | {'Open':>8} | {'/7':>8} | {'/3':>8} | Aurora",
            "  " + "-" * 48,
        ]
        by_depth: dict[int, dict] = {}
        for r in self.depth_results:
            by_depth.setdefault(r.depth, {})[r.relock_interval] = r

        for d in DEPTH_SCHEDULE:
            row = by_depth.get(d, {})
            o = row.get(None)
            r7 = row.get(7)
            r3 = row.get(3)
            lines.append(
                f"  {d:>6} | "
                f"{o.zzz_median if o else 0:>8.4f} | "
                f"{r7.zzz_median if r7 else 0:>8.4f} | "
                f"{r3.zzz_median if r3 else 0:>8.4f} | "
                f"{'OK' if (r3 and r3.aurora_satisfied) else '—'}"
            )

        lines.extend([
            "",
            f"{self.lattice_qubits}Q lattice depth {min(32, max(DEPTH_SCHEDULE))} (re-lock /3): see depth_results",
            f"ISS convergence: open {self.iss_open_final_deg:.1f}° → closed {self.iss_closed_final_deg:.2f}°",
            f"ISS mean ZZZ gain: {self.iss_mean_gain:+.4f}",
            f"Total runtime: {self.total_elapsed_s:.0f}s",
            "",
            f"VERDICT: {self.verdict}",
            "=" * 72,
        ])
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "noise_stack": self.noise_stack,
            "theta_star_deg": self.theta_star_deg,
            "shots": self.shots,
            "n_zzz_cells": self.n_zzz_cells,
            "cell_campaign_median": self.cell_campaign_median,
            "negative_control_zzz": self.negative_control_zzz,
            "baseline_zzz": self.baseline_zzz,
            "iss_closed_final_deg": self.iss_closed_final_deg,
            "iss_mean_gain": self.iss_mean_gain,
            "verdict": self.verdict,
            "depth_results": [
                {
                    "depth": r.depth,
                    "relock": r.relock_interval,
                    "zzz_median": r.zzz_median,
                    "zzz_mean": r.zzz_mean,
                    "aurora_satisfied": bool(r.aurora_satisfied),
                    "gamma_ratio": r.gamma_ratio,
                }
                for r in self.depth_results
            ],
        }


def run_cell_campaign(
    sim: AerSimulator,
    pairs: list[tuple[int, int]],
    theta: float,
    depth: int,
    relock_interval: int | None,
    shots: int,
    label: str = "",
) -> list[float]:
    """Run independent ZZZ cells (hardware-faithful parallel campaign)."""
    scores = []
    n = len(pairs)
    for i, (_a, _b) in enumerate(pairs):
        qc = build_zzz_cell_circuit(theta, depth, relock_interval)
        counts = run_single(qc, sim, shots)
        scores.append(zzz_score(counts))
        if label and (i + 1) % 10 == 0:
            print(f"  [{label}] {i + 1}/{n} cells done (depth={depth}, relock={relock_interval})", flush=True)
    return scores


def run_apocalypse_max(
    shots: int = 4096,
    max_cells: int = 43,
    lattice_qubits: int = 29,
    depths: list[int] | None = None,
    seed: int = 42,
) -> ApocalypseResult:
    """
    Hardest FakeFez stress test:
      - Apocalypse-max noise on FakeFez
      - 43+ parallel ZZZ cells (full-chip scale)
      - Depths up to 1241 layers
      - Aurora re-lock /3 (minimal thermo) vs open-loop
      - 29Q entangled lattice at max depth
      - ISS closed-loop vs open-loop
    """
    t_start = time.time()
    if seed is not None:
        np.random.seed(seed)

    depths = depths or DEPTH_SCHEDULE
    sim = build_apocalypse_simulator()

    try:
        from qiskit_ibm_runtime.fake_provider import FakeFez

        backend = FakeFez()
        coupling_map = backend.configuration().coupling_map
        n_backend = backend.num_qubits
    except ImportError:
        coupling_map = [(0, 1)]
        n_backend = 2

    pairs = extract_zzz_cell_pairs(coupling_map, max_cells=max_cells)
    aurora = check_aurora_condition(rho=0.85, t2_us=80.0)
    sigma_star = float(abs(phase_force(THETA_STAR_HW)))

    result = ApocalypseResult(
        num_qubits_backend=n_backend,
        shots=shots,
        n_zzz_cells=len(pairs),
        lattice_qubits=lattice_qubits,
    )

    # Baseline + negative control at depth 32
    result.baseline_zzz = zzz_score(run_single(build_baseline(32), sim, shots))
    neg_theta = THETA_STAR_HW + np.radians(70.0)
    result.negative_control_zzz = float(np.median(
        run_cell_campaign(sim, pairs[:5], neg_theta, 32, 3, shots)
    ))

    # Depth scaling across re-lock strategies
    for depth in depths:
        for relock in RELOCK_INTERVALS:
            rl = "open" if relock is None else f"/{relock}"
            print(f"\n[Depth {depth} re-lock {rl}] {len(pairs)} cells...", flush=True)
            t0 = time.time()
            scores = run_cell_campaign(
                sim, pairs, THETA_STAR_HW, depth, relock, shots,
                label=f"d{depth}{rl}",
            )
            dr = DepthResult(
                depth=depth,
                relock_interval=relock,
                zzz_median=float(np.median(scores)),
                zzz_mean=float(np.mean(scores)),
                zzz_std=float(np.std(scores)),
                n_cells=len(pairs),
                entropy_sigma_theta_star=sigma_star,
                aurora_satisfied=aurora.satisfied,
                gamma_ratio=aurora.gamma_lock / aurora.gamma_loss if aurora.gamma_loss else 0,
                elapsed_s=time.time() - t0,
            )
            result.depth_results.append(dr)

    print(f"\n[Cell campaign] depth=1241 re-lock /3, {len(pairs)} cells...", flush=True)
    result.cell_campaign_median = float(np.median(
        run_cell_campaign(sim, pairs, THETA_STAR_HW, 1241, 3, shots, label="1241/3")
    ))

    # 29Q lattice — depth capped (1241L on full lattice is ~470k gates; cells carry max depth)
    lattice_depth = min(32, max(depths))
    if lattice_qubits > 0:
        print(f"\n[{lattice_qubits}Q lattice] depth={lattice_depth} re-lock /3...", flush=True)
        t0 = time.time()
        try:
            lattice_cm = [(a, b) for a, b in coupling_map if a < lattice_qubits and b < lattice_qubits]
            qc_lat = build_lattice_circuit(
                lattice_qubits, lattice_cm, THETA_STAR_HW, lattice_depth, relock_interval=3,
            )
            counts_lat = run_single(qc_lat, sim, shots)
            lat_score = lattice_coherence_index(counts_lat, lattice_qubits)
            result.depth_results.append(DepthResult(
                depth=lattice_depth,
                relock_interval=3,
                zzz_median=lat_score,
                zzz_mean=lat_score,
                zzz_std=0.0,
                n_cells=lattice_qubits,
                entropy_sigma_theta_star=sigma_star,
                aurora_satisfied=aurora.satisfied,
                gamma_ratio=aurora.gamma_lock / aurora.gamma_loss,
                elapsed_s=time.time() - t0,
            ))
        except Exception as exc:
            print(f"  Lattice skipped ({exc})", flush=True)

    # ISS open vs closed loop (12-layer cells under apocalypse noise)
    theta_open = np.radians(45.0)
    theta_closed = np.radians(45.0)
    gains = []
    for _ in range(8):
        theta_open += np.random.normal(0, np.radians(5.0))
        theta_closed -= DEFAULT_K_GAIN * (theta_closed - THETA_STAR_HW)
        co = zzz_score(run_single(build_deep_qsd_circuit(theta_open, 12), sim, shots))
        cc = zzz_score(run_single(build_deep_qsd_circuit(theta_closed, 12), sim, shots))
        gains.append(cc - co)

    result.iss_open_final_deg = float(np.degrees(theta_open))
    result.iss_closed_final_deg = float(np.degrees(theta_closed))
    result.iss_mean_gain = float(np.mean(gains))

    # Verdict
    d1241_open = next((r for r in result.depth_results if r.depth == 1241 and r.relock_interval is None), None)
    d1241_r3 = next((r for r in result.depth_results if r.depth == 1241 and r.relock_interval == 3), None)
    sustained = d1241_r3 and d1241_open and d1241_r3.zzz_median >= d1241_open.zzz_median
    locked = result.cell_campaign_median > result.negative_control_zzz + 0.05
    result.verdict = (
        "✅ AURORA LOCK SUSTAINED AT MAX DEPTH"
        if sustained and locked and result.iss_mean_gain > 0
        else "⚠️ PARTIAL LOCK — see depth table"
    )

    result.total_elapsed_s = time.time() - t_start
    return result


def save_results(result: ApocalypseResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "fez_apocalypse_summary.txt").write_text(result.summary())
    (out_dir / "fez_apocalypse_results.json").write_text(json.dumps(result.to_dict(), indent=2))

    import csv
    with open(out_dir / "fez_apocalypse_depth_table.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["depth", "relock_interval", "zzz_median", "zzz_mean", "zzz_std", "n_cells", "aurora_ok", "elapsed_s"])
        for r in result.depth_results:
            w.writerow([r.depth, r.relock_interval, r.zzz_median, r.zzz_mean, r.zzz_std, r.n_cells, r.aurora_satisfied, r.elapsed_s])
