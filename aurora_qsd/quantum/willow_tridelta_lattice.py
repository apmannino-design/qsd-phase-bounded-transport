"""
Willow Tridelta lattice submission protocol (April 2026 proposal).

Implements Appendix A: Trotterized H(θ) = Σ Jzz(θ) ZZ + Jxx(θ) XX on a 9-qubit
patch, θ sweep, nearest-neighbor correlator, and model-independent ΔE(t).

Runs on willow_pink QVM (noisy simulation) via Cirq.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Iterator, Sequence

import numpy as np

try:
    import cirq
except ImportError:
    cirq = None  # type: ignore[assignment]

# Logical 3×3 Tridelta patch edges (submission Listing 1).
TRIDELTA_LOGICAL_EDGES: list[tuple[int, int]] = [
    (0, 1), (1, 2),
    (3, 4), (4, 5),
    (6, 7), (7, 8),
    (0, 3), (3, 6),
    (1, 4), (4, 7),
    (2, 5), (5, 8),
    (0, 4), (4, 8),
    (2, 4), (4, 6),
]

# Interior 3×3 block on Willow grid (rows 5–7, cols 5–7).
WILLOW_PATCH_COORDS: tuple[tuple[int, int], ...] = (
    (5, 5), (5, 6), (5, 7),
    (6, 5), (6, 6), (6, 7),
    (7, 5), (7, 6), (7, 7),
)


@dataclass(frozen=True)
class TrideltaLatticeConfig:
    trotter_steps: int = 8
    dt: float = 0.08
    h_field: float = 0.0
    shots: int = 500
    measure_key: str = "m"


@dataclass
class ThetaPointResult:
    theta_deg: float
    trotter_steps: int
    x_mean: float
    x_std: float
    delta_e_shot: float
    n_edges: int
    shots: int

    def to_dict(self) -> dict:
        return {
            "theta_deg": self.theta_deg,
            "trotter_steps": self.trotter_steps,
            "x_mean": self.x_mean,
            "x_std": self.x_std,
            "delta_e_shot": self.delta_e_shot,
            "n_edges": self.n_edges,
            "shots": self.shots,
        }


@dataclass
class PhaseDiagramResult:
    processor: str = "willow_pink"
    patch: list[str] = field(default_factory=list)
    n_qubits: int = 9
    n_edges: int = 0
    config: dict = field(default_factory=dict)
    points: list[dict] = field(default_factory=list)
    theta_summary: list[dict] = field(default_factory=list)
    elapsed_s: float = 0.0
    verdict: str = "NULL"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "patch": self.patch,
            "n_qubits": self.n_qubits,
            "n_edges": self.n_edges,
            "config": self.config,
            "points": self.points,
            "theta_summary": self.theta_summary,
            "elapsed_s": self.elapsed_s,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def _require_cirq() -> None:
    if cirq is None:
        raise ImportError("cirq + cirq-google required")


def couplings(theta_deg: float) -> tuple[float, float]:
    theta = math.radians(theta_deg)
    return math.cos(theta), math.sin(theta)


def greedy_edge_layers(edges: Sequence[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    layers: list[list[tuple[int, int]]] = []
    for edge in edges:
        a, b = edge
        placed = False
        for layer in layers:
            used = {q for e in layer for q in e}
            if a not in used and b not in used:
                layer.append(edge)
                placed = True
                break
        if not placed:
            layers.append([edge])
    return layers


def _zz_native(q0, q1, jzz: float, dt: float) -> Iterator:
    """exp(-i dt jzz Z⊗Z) via native Willow CZ + RZ (no fractional CZ)."""
    angle = 2.0 * jzz * dt
    yield cirq.CZ(q0, q1)
    yield cirq.rz(angle)(q0)
    yield cirq.rz(angle)(q1)
    yield cirq.CZ(q0, q1)


def _xx_native(q0, q1, jxx: float, dt: float) -> Iterator:
    yield cirq.H(q0)
    yield cirq.H(q1)
    yield from _zz_native(q0, q1, jxx, dt)
    yield cirq.H(q0)
    yield cirq.H(q1)


def _local_field(q, h_field: float, dt: float):
    return cirq.rz(2.0 * h_field * dt)(q)


def filter_edges_on_device(
    hw_qubits: Sequence,
    logical_edges: Sequence[tuple[int, int]],
    device,
) -> list[tuple[int, int]]:
    """Keep only edges with native coupling on the processor grid."""
    pairs = set()
    for a, b in device.metadata.qubit_pairs:
        pairs.add((min(a, b, key=lambda q: (q.row, q.col)), max(a, b, key=lambda q: (q.row, q.col))))

    out: list[tuple[int, int]] = []
    for i, j in logical_edges:
        qa, qb = hw_qubits[i], hw_qubits[j]
        lo, hi = (qa, qb) if (qa.row, qa.col) <= (qb.row, qb.col) else (qb, qa)
        if (lo, hi) in pairs or qa.is_adjacent(qb):
            out.append((i, j))
    return out


def choose_willow_patch(device) -> list:
    """9-qubit interior 3×3 patch validated on willow_pink."""
    _require_cirq()
    qset = device.metadata.qubit_set
    patch = [cirq.GridQubit(r, c) for r, c in WILLOW_PATCH_COORDS]
    missing = [q for q in patch if q not in qset]
    if missing:
        raise ValueError(f"patch qubits missing on device: {missing}")
    return patch


def build_tridelta_circuit(
    hw_qubits: Sequence,
    logical_edges: Sequence[tuple[int, int]],
    theta_deg: float,
    config: TrideltaLatticeConfig,
) -> "cirq.Circuit":
    """Trotterized Tridelta lattice — native willow_pink gates (CZ, RZ, H)."""
    _require_cirq()
    jzz, jxx = couplings(theta_deg)
    edge_layers = greedy_edge_layers(logical_edges)
    circuit = cirq.Circuit()
    circuit.append(cirq.H.on_each(*hw_qubits))
    for _ in range(config.trotter_steps):
        for layer in edge_layers:
            for i, j in layer:
                circuit.append(
                    list(_zz_native(hw_qubits[i], hw_qubits[j], jzz, config.dt))
                )
        for layer in edge_layers:
            for i, j in layer:
                circuit.append(
                    list(_xx_native(hw_qubits[i], hw_qubits[j], jxx, config.dt))
                )
        if abs(config.h_field) > 0:
            circuit.append(
                [_local_field(q, config.h_field, config.dt) for q in hw_qubits]
            )
    circuit.append(cirq.measure(*hw_qubits, key=config.measure_key))
    return circuit


def nearest_neighbor_correlator_per_shot(
    measurement_array: np.ndarray,
    logical_edges: Sequence[tuple[int, int]],
) -> np.ndarray:
    """Spatially averaged ⟨Z_i Z_j⟩ per shot (submission observable x(t))."""
    x_t = []
    for shot_bits in measurement_array:
        z = [1 - 2 * int(b) for b in shot_bits]
        corr_vals = [z[i] * z[j] for i, j in logical_edges]
        x_t.append(sum(corr_vals) / len(corr_vals))
    return np.asarray(x_t, dtype=float)


def delta_e_from_series(x: np.ndarray, eps: float = 1e-6, window: int = 5) -> float:
    """
    Model-independent fluctuation observable ΔE(t) from submission §V.

    y(t) = log(|x(t)| + ε), Δy = diff(y), σ = rolling std(|Δy|), ΔE = σ / M.
    """
    x = np.asarray(x, dtype=float)
    if len(x) < 3:
        return 0.0
    y = np.log(np.abs(x) + eps)
    dy = np.abs(np.diff(y))
    if len(dy) < window:
        sigma = float(np.std(dy)) if len(dy) else 0.0
    else:
        sigmas = [float(np.std(dy[i : i + window])) for i in range(len(dy) - window + 1)]
        sigma = float(np.mean(sigmas))
    m = float(np.median(np.abs(x))) or 1.0
    return sigma / m


def delta_e_from_shots(x_shots: np.ndarray, eps: float = 1e-6) -> float:
    """Shot-resolved ΔE proxy at fixed (θ, t): fluctuation across repetitions."""
    x = np.asarray(x_shots, dtype=float)
    if len(x) < 4:
        return 0.0
    y = np.log(np.abs(x) + eps)
    dy = np.abs(np.diff(np.sort(y)))
    med = float(np.median(dy))
    mad = float(np.median(np.abs(dy - med)))
    scale = 1.4826 * mad if mad > 0 else float(np.std(dy) or 1.0)
    z = np.clip((dy - med) / scale, 0.0, None)
    return float(np.mean(z))


def _measurement_bit_array(result, key: str, n_qubits: int, shots: int) -> np.ndarray:
    """Decode packed integer measurements from willow_pink sampler."""
    series = result.data[key]
    rows = []
    for i in range(shots):
        val = int(series.iloc[i])
        rows.append([(val >> q) & 1 for q in range(n_qubits)])
    return np.asarray(rows, dtype=int)


def run_single_point(
    sampler,
    hw_qubits: Sequence,
    logical_edges: Sequence[tuple[int, int]],
    theta_deg: float,
    config: TrideltaLatticeConfig,
) -> ThetaPointResult:
    circuit = build_tridelta_circuit(hw_qubits, logical_edges, theta_deg, config)
    result = sampler.run(circuit, repetitions=config.shots)
    arr = _measurement_bit_array(result, config.measure_key, len(hw_qubits), config.shots)
    x_shots = nearest_neighbor_correlator_per_shot(arr, logical_edges)
    return ThetaPointResult(
        theta_deg=theta_deg,
        trotter_steps=config.trotter_steps,
        x_mean=float(np.mean(x_shots)),
        x_std=float(np.std(x_shots)),
        delta_e_shot=delta_e_from_shots(x_shots),
        n_edges=len(logical_edges),
        shots=config.shots,
    )


def default_theta_sweep(fine_center: float = 22.49) -> list[float]:
    """Coarse sweep + fine resolution near θ* (submission §VI)."""
    coarse = list(np.linspace(2.0, 88.0, 15))
    fine = [fine_center + d for d in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0)]
    thetas = sorted(set(round(t, 2) for t in coarse + fine))
    return thetas


def run_phase_diagram_on_willow(
    thetas_deg: Sequence[float] | None = None,
    trotter_range: Sequence[int] | None = None,
    shots: int = 500,
    dt: float = 0.08,
    h_field: float = 0.0,
) -> PhaseDiagramResult:
    """
    Full submission test on willow_pink QVM:
      - 9-qubit interior Tridelta patch
      - θ sweep × Trotter depth sweep
      - correlator + ΔE diagnostics
    """
    _require_cirq()
    from cirq_google import engine

    thetas_deg = list(thetas_deg or default_theta_sweep())
    trotter_range = list(trotter_range or range(4, 13))  # submission: 8–12; include 4–12

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    sampler = proc.get_sampler()
    device = proc.get_device()
    hw_qubits = choose_willow_patch(device)
    logical_edges = filter_edges_on_device(hw_qubits, TRIDELTA_LOGICAL_EDGES, device)

    out = PhaseDiagramResult(
        patch=[f"q({q.row},{q.col})" for q in hw_qubits],
        n_edges=len(logical_edges),
        config={
            "dt": dt,
            "h_field": h_field,
            "shots": shots,
            "trotter_range": list(trotter_range),
            "n_thetas": len(thetas_deg),
        },
    )

    t0 = time.time()
    total = len(thetas_deg) * len(trotter_range)
    k = 0

    for theta_deg in thetas_deg:
        time_series: list[float] = []
        for steps in trotter_range:
            k += 1
            print(
                f"[tridelta] {k}/{total} θ={theta_deg:.2f}° steps={steps}",
                flush=True,
            )
            cfg = TrideltaLatticeConfig(
                trotter_steps=steps, dt=dt, h_field=h_field, shots=shots
            )
            pt = run_single_point(sampler, hw_qubits, logical_edges, theta_deg, cfg)
            out.points.append(pt.to_dict())
            time_series.append(pt.x_mean)

        delta_e_t = delta_e_from_series(np.array(time_series))
        out.theta_summary.append(
            {
                "theta_deg": theta_deg,
                "x_mean_over_steps": float(np.mean(time_series)),
                "x_std_over_steps": float(np.std(time_series)),
                "delta_e_time": delta_e_t,
                "near_theta_star": abs(theta_deg - 22.49) <= 2.0,
            }
        )

    out.elapsed_s = time.time() - t0

    # Compare dynamics near θ* vs far from θ*
    near = [r for r in out.theta_summary if r["near_theta_star"]]
    far = [r for r in out.theta_summary if not r["near_theta_star"]]
    de_near = float(np.mean([r["delta_e_time"] for r in near])) if near else 0.0
    de_far = float(np.mean([r["delta_e_time"] for r in far])) if far else 0.0
    x_spread_near = float(np.std([r["x_mean_over_steps"] for r in near])) if near else 0.0
    x_spread_far = float(np.std([r["x_mean_over_steps"] for r in far])) if far else 0.0

    if abs(de_near - de_far) > 0.05 or abs(x_spread_near - x_spread_far) > 0.05:
        out.verdict = "REGIME_STRUCTURE"
        out.notes = (
            f"9Q Tridelta on willow_pink: ΔE_time near θ*={de_near:.3f} vs far={de_far:.3f}; "
            f"x-spread near={x_spread_near:.3f} far={x_spread_far:.3f}; "
            f"{len(logical_edges)} native edges."
        )
    else:
        out.verdict = "NULL"
        out.notes = (
            f"No clear θ-dependent regime separation on 9Q patch "
            f"(ΔE near={de_near:.3f}, far={de_far:.3f})."
        )

    return out
