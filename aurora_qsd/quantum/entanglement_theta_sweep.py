"""
Entanglement θ sweep — G(El) across corridor 22.5° → 90°.

Preregistered angles (May/July 2026 corridor):
  θ* = 22.5°        design setpoint (π/8)
  22.49°            Willow platform optimum
  27.61°            SO(2) merger partition
  67.5° = 3θ*       basin near edge
  90°               far basin edge / bridge reference

At fixed entanglement depth El (default 2 = galaxy-propagation probe),
sweeps θ and reports G(θ) = p_fail_bare / p_fail_qsd.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.constants import (
    BASIN_BOUNDARY_DEG,
    MERGER_PARTITION_THETA_DEG,
    THETA_STAR_DEG,
    THETA_STAR_WILLOW_HW_DEG,
)
from aurora_qsd.quantum.fez_cells import (
    _append_3q_qsd_layer,
    _trilock_init,
    negative_control_angle,
    zzz_correlator,
)
from aurora_qsd.quantum.noise_models import build_simulator
from aurora_qsd.quantum.runner import run_circuit
from aurora_qsd.quantum.willow_entanglement_stress import (
    build_entanglement_stress_circuit,
    p_fail_majority_one,
    run_entanglement_stress,
)
from aurora_qsd.quantum.willow_lines import get_line

try:
    from qiskit import QuantumCircuit
except ImportError:
    QuantumCircuit = None  # type: ignore[misc, assignment]

# Corridor sweep (22.5° → 90°) with structural anchors
DEFAULT_THETA_SWEEP_DEG = [
    22.5,
    22.49,
    27.61,
    35.0,
    45.0,
    55.0,
    BASIN_BOUNDARY_DEG,
    75.0,
    82.5,
    90.0,
]

LOGICAL_QUBITS = (0, 1, 2)


def generate_theta_sweep_deg(
    start_deg: float = THETA_STAR_DEG,
    end_deg: float = 90.0,
    n_steps: int = 10,
) -> list[float]:
    return [float(x) for x in np.linspace(start_deg, end_deg, n_steps)]


@dataclass
class EntangleThetaPoint:
    theta_deg: float
    el: int
    p_fail_qsd: float
    p_fail_wrong: float
    p_fail_bare: float
    g_qsd_vs_bare: float
    g_qsd_vs_wrong: float
    zzz_qsd: float | None = None
    shots: int = 0

    def to_dict(self) -> dict:
        return {
            "theta_deg": self.theta_deg,
            "el": self.el,
            "p_fail_qsd": self.p_fail_qsd,
            "p_fail_wrong": self.p_fail_wrong,
            "p_fail_bare": self.p_fail_bare,
            "g_qsd_vs_bare": self.g_qsd_vs_bare,
            "g_qsd_vs_wrong": self.g_qsd_vs_wrong,
            "zzz_qsd": self.zzz_qsd,
            "shots": self.shots,
        }


@dataclass
class EntangleThetaSweepResult:
    backend: str = "willow_pink"
    el: int = 2
    theta_sweep_deg: list[float] = field(default_factory=list)
    shots: int = 0
    points: list[EntangleThetaPoint] = field(default_factory=list)
    g_peak: float = 0.0
    theta_peak_deg: float = 0.0
    theta_star_deg: float = THETA_STAR_DEG
    interior_peak: bool = False
    elapsed_s: float = 0.0
    verdict: str = "NULL"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "backend": self.backend,
            "el": self.el,
            "theta_sweep_deg": self.theta_sweep_deg,
            "shots": self.shots,
            "points": [p.to_dict() for p in self.points],
            "g_peak": self.g_peak,
            "theta_peak_deg": self.theta_peak_deg,
            "theta_star_deg": self.theta_star_deg,
            "interior_peak": self.interior_peak,
            "elapsed_s": self.elapsed_s,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def _build_ibm_3q_entangle_circuit(theta_deg: float, el: int, arm: str = "qsd") -> "QuantumCircuit":
    if QuantumCircuit is None:
        raise ImportError("qiskit required")
    theta = float(np.radians(theta_deg))
    th_wrong = float(negative_control_angle(theta))
    logical = LOGICAL_QUBITS
    qc = QuantumCircuit(3, 3)

    if arm == "qsd":
        _trilock_init(qc, logical, theta)
        body_th = theta
    elif arm == "wrong":
        _trilock_init(qc, logical, th_wrong)
        body_th = th_wrong
    elif arm == "bare":
        for q in logical:
            qc.h(q)
        body_th = theta
    else:
        raise ValueError(arm)

    for layer in range(el):
        _append_3q_qsd_layer(qc, logical, body_th, with_init=False)

    qc.measure(list(logical), [0, 1, 2])
    return qc


def run_willow_entanglement_theta_sweep(
    shots: int = 2000,
    el: int = 2,
    thetas_deg: list[float] | None = None,
    line_name: str = "interior",
) -> EntangleThetaSweepResult:
    """θ sweep on Willow @ fixed El (G(θ) corridor 22.5°–90°)."""
    try:
        import cirq
        from cirq_google import engine
    except ImportError as exc:
        raise ImportError("cirq + cirq_google required for Willow sweep") from exc

    thetas = thetas_deg or DEFAULT_THETA_SWEEP_DEG
    line = get_line(line_name)
    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    sampler = proc.get_sampler()

    out = EntangleThetaSweepResult(
        backend="willow_pink",
        el=el,
        theta_sweep_deg=list(thetas),
        shots=shots,
    )
    t0 = time.time()

    for td in thetas:
        print(f"[entangle_θ] Willow θ={td:.2f}° El={el} ({shots} shots)", flush=True)
        theta = float(np.radians(td))
        arm_pf: dict[str, float] = {}
        for arm in ("qsd", "wrong", "bare"):
            circuit = build_entanglement_stress_circuit(line, el, theta, arm=arm)
            result = sampler.run(circuit, repetitions=shots)
            counts = {}
            series = result.data["m"]
            for i in range(shots):
                val = int(series.iloc[i])
                bits = "".join(str((val >> q) & 1) for q in range(3))
                counts[bits] = counts.get(bits, 0) + 1
            arm_pf[arm] = p_fail_majority_one(counts, n_qubits=3)

        p_q = max(arm_pf["qsd"], 1e-6)
        pt = EntangleThetaPoint(
            theta_deg=td,
            el=el,
            p_fail_qsd=arm_pf["qsd"],
            p_fail_wrong=arm_pf["wrong"],
            p_fail_bare=arm_pf["bare"],
            g_qsd_vs_bare=arm_pf["bare"] / p_q,
            g_qsd_vs_wrong=arm_pf["wrong"] / p_q,
            shots=shots,
        )
        out.points.append(pt)
        print(f"  G={pt.g_qsd_vs_bare:.3f}  p_fail qsd={pt.p_fail_qsd:.3f}", flush=True)

    _finalize_theta_sweep(out, t0)
    return out


def run_ibm_entanglement_theta_sweep(
    shots: int = 2048,
    el: int = 2,
    thetas_deg: list[float] | None = None,
    backend_name: str = "aer_fez",
    noise: str = "native",
    physical_qubits: tuple[int, int, int] = (0, 1, 2),
    use_hardware: bool = False,
) -> EntangleThetaSweepResult:
    """θ sweep on IBM 3Q line @ fixed El (FakeFez/Aer or real ibm_fez)."""
    thetas = thetas_deg or DEFAULT_THETA_SWEEP_DEG
    out = EntangleThetaSweepResult(
        backend=backend_name,
        el=el,
        theta_sweep_deg=list(thetas),
        shots=shots,
    )
    t0 = time.time()

    if use_hardware:
        from aurora_qsd.quantum.ibm_retention_audit import run_circuit_zzz, _transpile_for_run, _resolve_backend

        backend, mode = _resolve_backend(backend_name)
        for td in thetas:
            print(f"[entangle_θ] IBM {backend_name} θ={td:.2f}° El={el}", flush=True)
            arm_pf: dict[str, float] = {}
            zzz_qsd = None
            for arm in ("qsd", "wrong", "bare"):
                c = _build_ibm_3q_entangle_circuit(td, el, arm=arm)
                hw = run_circuit_zzz(c, backend_name, shots, physical_qubits=physical_qubits, backend=backend, mode=mode)
                counts = hw["counts"]
                arm_pf[arm] = p_fail_majority_one(counts, n_qubits=3)
                if arm == "qsd":
                    zzz_qsd = zzz_correlator(counts, n_qubits=3)
            p_q = max(arm_pf["qsd"], 1e-6)
            out.points.append(
                EntangleThetaPoint(
                    theta_deg=td,
                    el=el,
                    p_fail_qsd=arm_pf["qsd"],
                    p_fail_wrong=arm_pf["wrong"],
                    p_fail_bare=arm_pf["bare"],
                    g_qsd_vs_bare=arm_pf["bare"] / p_q,
                    g_qsd_vs_wrong=arm_pf["wrong"] / p_q,
                    zzz_qsd=zzz_qsd,
                    shots=shots,
                )
            )
    else:
        sim = build_simulator(noise)
        for td in thetas:
            print(f"[entangle_θ] Aer {noise} θ={td:.2f}° El={el}", flush=True)
            arm_pf: dict[str, float] = {}
            zzz_qsd = None
            for arm in ("qsd", "wrong", "bare"):
                c = _build_ibm_3q_entangle_circuit(td, el, arm=arm)
                counts = run_circuit(c, sim, shots)
                arm_pf[arm] = p_fail_majority_one(counts, n_qubits=3)
                if arm == "qsd":
                    zzz_qsd = zzz_correlator(counts, n_qubits=3)
            p_q = max(arm_pf["qsd"], 1e-6)
            out.points.append(
                EntangleThetaPoint(
                    theta_deg=td,
                    el=el,
                    p_fail_qsd=arm_pf["qsd"],
                    p_fail_wrong=arm_pf["wrong"],
                    p_fail_bare=arm_pf["bare"],
                    g_qsd_vs_bare=arm_pf["bare"] / p_q,
                    g_qsd_vs_wrong=arm_pf["wrong"] / p_q,
                    zzz_qsd=zzz_qsd,
                    shots=shots,
                )
            )
            pt = out.points[-1]
            print(f"  G={pt.g_qsd_vs_bare:.3f}  ZZZ={zzz_qsd:+.3f}", flush=True)

    _finalize_theta_sweep(out, t0)
    return out


def _finalize_theta_sweep(out: EntangleThetaSweepResult, t0: float) -> None:
    if not out.points:
        out.verdict = "NULL"
        out.notes = "No sweep points."
        out.elapsed_s = time.time() - t0
        return

    peak = max(out.points, key=lambda p: p.g_qsd_vs_bare)
    out.g_peak = float(peak.g_qsd_vs_bare)
    out.theta_peak_deg = float(peak.theta_deg)
    sweep = out.theta_sweep_deg
    out.interior_peak = bool(sweep[0] < peak.theta_deg < sweep[-1])

    near_star = any(abs(p.theta_deg - THETA_STAR_DEG) < 1.0 for p in out.points)
    g_at_star = next(
        (p.g_qsd_vs_bare for p in out.points if abs(p.theta_deg - THETA_STAR_DEG) < 1.0),
        None,
    )

    if out.g_peak > 1.05 and out.interior_peak:
        out.verdict = "ENTANGLEMENT_ANGLE_WIN"
        out.notes = (
            f"G peak {out.g_peak:.2f} @ θ={out.theta_peak_deg:.2f}° (interior); "
            f"corridor {sweep[0]:.1f}°–{sweep[-1]:.1f}° @ El={out.el}."
        )
    elif out.g_peak > 1.0:
        out.verdict = "PARTIAL_ANGLE"
        out.notes = f"Peak G={out.g_peak:.2f} @ θ={out.theta_peak_deg:.2f}° but weak basin."
    else:
        out.verdict = "NULL"
        out.notes = f"No G>1 across θ sweep (peak {out.g_peak:.2f})."

    if g_at_star and g_at_star > 1.0:
        out.notes += f" G(θ*≈22.5°)={g_at_star:.2f}."
    if abs(out.theta_peak_deg - THETA_STAR_WILLOW_HW_DEG) < 2.0:
        out.notes += " Peak near Willow/platform θ."
    if abs(out.theta_peak_deg - MERGER_PARTITION_THETA_DEG) < 3.0:
        out.notes += " Peak near merger partition 27.61°."

    out.elapsed_s = time.time() - t0
