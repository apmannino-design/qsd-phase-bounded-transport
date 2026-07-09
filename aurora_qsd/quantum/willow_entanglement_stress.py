"""
Willow entanglement stress test — G factor through CX depth (May 2026 protocol).

Tests whether TriLock @ θ* + entangling CX layers suppresses basin failure
better than bare entanglement (H init) — the user's thesis:

  errors stop BECAUSE entanglement spreads the θ* lock, not despite it.

Metric (hardware-aligned):
  p_fail = P(majority of line qubits measure |1⟩)
  G(El)  = p_fail_bare(El) / p_fail_qsd(El)   (>1 ⇒ QSD wins under entanglement)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

try:
    import cirq
except ImportError:
    cirq = None  # type: ignore[assignment]

from aurora_qsd.core.constants import THETA_STAR_WILLOW_HW_DEG
from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_lines import WillowLine, get_line
from aurora_qsd.quantum.willow_run import (
    _cz_cnot,
    _require_cirq,
    _trilock_init_ops,
)


def _entangle_layer_ops(qubits: list, theta: float) -> list:
    """One entanglement layer: CX along line + basin RZ phases."""
    q0, q1, q2 = qubits
    ops: list = []
    ops.extend(_cz_cnot(q0, q1))
    ops.extend([cirq.rz(theta)(q0), cirq.rz(np.pi / 2.0 - theta)(q1)])
    ops.extend(_cz_cnot(q1, q2))
    ops.append(cirq.rz(theta)(q2))
    return ops


def build_entanglement_stress_circuit(
    line: WillowLine,
    entanglement_layers: int,
    theta: float,
    arm: str = "qsd",
) -> "cirq.Circuit":
    """
    Build El-layer entanglement stress circuit on a 3Q line.

    arm:
      qsd   — TriLock init @ θ then El CX layers
      wrong — TriLock @ θ+70°
      bare  — H init (no QSD lock) then El CX layers
    """
    _require_cirq()
    import cirq

    qubits = list(line.qubits())
    ops: list = []

    if arm == "qsd":
        ops.extend(_trilock_init_ops(qubits, theta))
    elif arm == "wrong":
        ops.extend(_trilock_init_ops(qubits, negative_control_angle(theta)))
    elif arm == "bare":
        ops.extend(cirq.H.on_each(*qubits))
    else:
        raise ValueError(f"unknown arm {arm!r}")

    for _ in range(entanglement_layers):
        ops.extend(_entangle_layer_ops(qubits, theta if arm != "wrong" else negative_control_angle(theta)))

    ops.append(cirq.measure(*qubits, key="m"))
    return cirq.Circuit(ops)


def _bitstring_from_shot(val: int, n: int) -> str:
    return "".join(str((val >> q) & 1) for q in range(n))


def p_fail_majority_one(counts: dict[str, int], n_qubits: int = 3) -> float:
    """
    Basin failure probability: majority of qubits in |1⟩.

    Matches May hardware majority-vote failure proxy.
    """
    total = sum(counts.values())
    if total == 0:
        return 1.0
    fail = 0
    for bits, c in counts.items():
        ones = bits.count("1")
        if ones > n_qubits // 2:
            fail += c
    return fail / total


def _counts_from_result(result, key: str, shots: int, n_qubits: int) -> dict[str, int]:
    series = result.data[key]
    counts: dict[str, int] = {}
    for i in range(shots):
        val = int(series.iloc[i])
        bits = _bitstring_from_shot(val, n_qubits)
        counts[bits] = counts.get(bits, 0) + 1
    return counts


@dataclass
class EntangleDepthPoint:
    el: int
    p_fail_qsd: float
    p_fail_wrong: float
    p_fail_bare: float
    g_qsd_vs_bare: float
    g_qsd_vs_wrong: float
    shots: int

    def to_dict(self) -> dict:
        return {
            "el": self.el,
            "p_fail_qsd": self.p_fail_qsd,
            "p_fail_wrong": self.p_fail_wrong,
            "p_fail_bare": self.p_fail_bare,
            "g_qsd_vs_bare": self.g_qsd_vs_bare,
            "g_qsd_vs_wrong": self.g_qsd_vs_wrong,
            "shots": self.shots,
        }


@dataclass
class EntanglementStressResult:
    processor: str = "willow_pink"
    line: list[str] = field(default_factory=list)
    theta_star_deg: float = THETA_STAR_WILLOW_HW_DEG
    shots: int = 0
    points: list[EntangleDepthPoint] = field(default_factory=list)
    g_peak: float = 0.0
    g_peak_el: int = 0
    g_at_el0: float = 0.0
    g_sustained_el_ge_1: int = 0
    n_el_tested: int = 0
    elapsed_s: float = 0.0
    verdict: str = "NULL"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "line": self.line,
            "theta_star_deg": self.theta_star_deg,
            "shots": self.shots,
            "points": [p.to_dict() for p in self.points],
            "g_peak": self.g_peak,
            "g_peak_el": self.g_peak_el,
            "g_at_el0": self.g_at_el0,
            "g_sustained_el_ge_1": self.g_sustained_el_ge_1,
            "n_el_tested": self.n_el_tested,
            "elapsed_s": self.elapsed_s,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def run_entanglement_stress(
    shots: int = 2000,
    theta_star_deg: float = THETA_STAR_WILLOW_HW_DEG,
    el_schedule: list[int] | None = None,
    line_name: str = "interior",
) -> EntanglementStressResult:
    """CX-depth sweep on willow_pink — G(El) for qsd vs bare vs wrong."""
    _require_cirq()
    from cirq_google import engine

    el_schedule = el_schedule or [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13]

    line = get_line(line_name)
    theta = float(np.radians(theta_star_deg))

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    sampler = proc.get_sampler()

    t0 = time.time()
    out = EntanglementStressResult(
        line=line.labels(),
        theta_star_deg=theta_star_deg,
        shots=shots,
    )

    for el in el_schedule:
        print(f"[entangle_stress] El={el} ({shots} shots)", flush=True)
        arm_pf: dict[str, float] = {}
        for arm in ("qsd", "wrong", "bare"):
            circuit = build_entanglement_stress_circuit(line, el, theta, arm=arm)
            result = sampler.run(circuit, repetitions=shots)
            counts = _counts_from_result(result, "m", shots, n_qubits=3)
            arm_pf[arm] = p_fail_majority_one(counts, n_qubits=3)

        p_q = max(arm_pf["qsd"], 1e-6)
        p_w = max(arm_pf["wrong"], 1e-6)
        g_bare = arm_pf["bare"] / p_q
        g_wrong = arm_pf["wrong"] / p_q

        pt = EntangleDepthPoint(
            el=el,
            p_fail_qsd=arm_pf["qsd"],
            p_fail_wrong=arm_pf["wrong"],
            p_fail_bare=arm_pf["bare"],
            g_qsd_vs_bare=float(g_bare),
            g_qsd_vs_wrong=float(g_wrong),
            shots=shots,
        )
        out.points.append(pt)
        print(
            f"  p_fail qsd={pt.p_fail_qsd:.3f} bare={pt.p_fail_bare:.3f} "
            f"G_vs_bare={pt.g_qsd_vs_bare:.3f}",
            flush=True,
        )

    gs = [p.g_qsd_vs_bare for p in out.points if p.el > 0]
    out.n_el_tested = len(out.points)
    out.g_sustained_el_ge_1 = sum(1 for g in gs if g > 1.0)
    out.g_at_el0 = next((p.g_qsd_vs_bare for p in out.points if p.el == 0), 0.0)

    if out.points:
        peak_pt = max(out.points, key=lambda p: p.g_qsd_vs_bare if p.el > 0 else 0.0)
        out.g_peak = float(peak_pt.g_qsd_vs_bare)
        out.g_peak_el = int(peak_pt.el)

    out.elapsed_s = time.time() - t0

    el1 = next((p for p in out.points if p.el == 1), None)
    el2 = next((p for p in out.points if p.el == 2), None)

    if out.g_sustained_el_ge_1 >= max(1, len(gs) * 2 // 3) and out.g_peak > 1.05:
        out.verdict = "ENTANGLEMENT_SUPPRESSES"
        out.notes = (
            f"G>1 through CX depth on Willow sim: peak G={out.g_peak:.2f} @ El={out.g_peak_el}, "
            f"{out.g_sustained_el_ge_1}/{len(gs)} entangled depths win vs bare."
        )
    elif out.g_peak > 1.0:
        out.verdict = "PARTIAL_G"
        out.notes = (
            f"Peak G={out.g_peak:.2f} @ El={out.g_peak_el} but not sustained; "
            f"{out.g_sustained_el_ge_1}/{len(gs)} depths G>1."
        )
    else:
        out.verdict = "NULL"
        out.notes = f"No G>1 vs bare on Willow sim (peak {out.g_peak:.2f})."

    if el1 and el2 and el2.g_qsd_vs_bare > el1.g_qsd_vs_bare:
        out.notes += " G rises El=1→2 (phase propagates under entanglement)."

    return out
