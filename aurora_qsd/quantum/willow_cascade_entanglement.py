"""
Willow cascade entanglement test — max qubits, max depth, least entropy.

Extends the May 2026 G(El) protocol to the full willow_pink chip:

  1. Seed every disjoint 3Q cell with TriLock @ θ* (up to ~96 qubits).
  2. Cascade entanglement layers (Cc): intra-cell CX + inter-cell bridge CX.
  3. Periodic re-lock (sunscreen reset) to minimize thermodynamic σ(θ).

Metrics per cascade depth Cc:
  G(Cc)  = p_fail_bare / p_fail_qsd   (chip-wide majority vote, >1 ⇒ QSD wins)
  σ(θ*)  = |F(θ*)|                    (phase-force entropy production proxy → 0 at θ*)
  H      = Shannon entropy of outcomes (bits; lower ⇒ more ordered lock)

Objective: maximize qubits × cascade depth while keeping G>1 and entropy low.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_WILLOW_HW_DEG
from aurora_qsd.core.phase_potential import phase_force
from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL
from aurora_qsd.quantum.willow_entanglement_stress import (
    _entangle_layer_ops,
    p_fail_majority_one,
)
from aurora_qsd.quantum.willow_lines import WillowLine, extract_disjoint_3q_lines
from aurora_qsd.quantum.willow_run import (
    _cz_cnot,
    _require_cirq,
    _sunscreen_reset_ops,
    _trilock_init_ops,
)

try:
    import cirq
except ImportError:
    cirq = None  # type: ignore[assignment]

# May 2026 hardware schedule + extended tail for max-depth cascade
DEFAULT_CC_SCHEDULE = [0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 16, 20]
QUICK_CC_SCHEDULE = [0, 1, 2, 5, 8, 13]


def _cell_for_qubit(q, cells: list[WillowLine]) -> int | None:
    for i, cell in enumerate(cells):
        if q in cell.qubits():
            return i
    return None


def find_cascade_bridges(cells: list[WillowLine], device) -> list[tuple]:
    """Adjacent qubit pairs linking different 3Q cells (cascade propagation edges)."""
    _require_cirq()
    seen: set[tuple] = set()
    bridges: list[tuple] = []
    for a, b in device.metadata.qubit_pairs:
        ca = _cell_for_qubit(a, cells)
        cb = _cell_for_qubit(b, cells)
        if ca is None or cb is None or ca == cb:
            continue
        key = (a, b) if (a.row, a.col) <= (b.row, b.col) else (b, a)
        if key not in seen:
            seen.add(key)
            bridges.append(key)
    return bridges


def sorted_chip_qubits(cells: list[WillowLine]) -> list:
    return sorted({q for cell in cells for q in cell.qubits()}, key=lambda q: (q.row, q.col))


def shannon_entropy_bits(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        p = c / total
        if p > 0:
            h -= p * math.log2(p)
    return float(h)


def build_cascade_entanglement_circuit(
    cells: list[WillowLine],
    bridge_pairs: list[tuple],
    cascade_layers: int,
    theta: float,
    arm: str = "qsd",
    relock_interval: int | None = OPTIMAL_RELOCK_INTERVAL,
) -> "cirq.Circuit":
    """
    Full-chip cascade circuit.

    arm: qsd | wrong | bare
    Each cascade layer = intra-cell entangle + inter-cell bridge CX + basin RZ.
    """
    _require_cirq()
    import cirq

    all_qubits = sorted_chip_qubits(cells)
    ops: list = []
    th = theta if arm != "wrong" else negative_control_angle(theta)

    if arm == "bare":
        ops.extend(cirq.H.on_each(*all_qubits))
    else:
        for cell in cells:
            ops.extend(_trilock_init_ops(list(cell.qubits()), th))

    done = 0
    while done < cascade_layers:
        if done > 0 and relock_interval and done % relock_interval == 0 and arm != "bare":
            for cell in cells:
                ops.extend(_sunscreen_reset_ops(list(cell.qubits()), th))

        for cell in cells:
            ops.extend(_entangle_layer_ops(list(cell.qubits()), th))

        for q0, q1 in bridge_pairs:
            ops.extend(_cz_cnot(q0, q1))
            ops.extend([cirq.rz(th)(q0), cirq.rz(np.pi / 2.0 - th)(q1)])

        done += 1

    ops.append(cirq.measure(*all_qubits, key="m"))
    return cirq.Circuit(ops)


def _bitstring_from_shot(val: int, n_qubits: int) -> str:
    return "".join(str((val >> q) & 1) for q in range(n_qubits))


def _counts_from_result(result, key: str, shots: int, n_qubits: int) -> dict[str, int]:
    series = result.data[key]
    counts: dict[str, int] = {}
    for i in range(shots):
        val = int(series.iloc[i])
        bits = _bitstring_from_shot(val, n_qubits)
        counts[bits] = counts.get(bits, 0) + 1
    return counts


@dataclass
class CascadeDepthPoint:
    cc: int
    p_fail_qsd: float
    p_fail_wrong: float
    p_fail_bare: float
    g_qsd_vs_bare: float
    g_qsd_vs_wrong: float
    entropy_qsd_bits: float
    entropy_bare_bits: float
    entropy_wrong_bits: float
    sigma_theta: float
    shots: int

    def to_dict(self) -> dict:
        return {
            "cc": self.cc,
            "p_fail_qsd": self.p_fail_qsd,
            "p_fail_wrong": self.p_fail_wrong,
            "p_fail_bare": self.p_fail_bare,
            "g_qsd_vs_bare": self.g_qsd_vs_bare,
            "g_qsd_vs_wrong": self.g_qsd_vs_wrong,
            "entropy_qsd_bits": self.entropy_qsd_bits,
            "entropy_bare_bits": self.entropy_bare_bits,
            "entropy_wrong_bits": self.entropy_wrong_bits,
            "sigma_theta": self.sigma_theta,
            "shots": self.shots,
        }


@dataclass
class CascadeEntanglementResult:
    processor: str = "willow_pink"
    theta_star_deg: float = THETA_STAR_WILLOW_HW_DEG
    n_cells: int = 0
    n_qubits: int = 0
    n_bridges: int = 0
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL
    cc_schedule: list[int] = field(default_factory=list)
    shots: int = 0
    points: list[CascadeDepthPoint] = field(default_factory=list)
    g_peak: float = 0.0
    g_peak_cc: int = 0
    g_sustained_cc_ge_1: int = 0
    entropy_min_qsd_bits: float = 0.0
    entropy_min_cc: int = 0
    entropy_at_max_cc_qsd: float = 0.0
    entropy_at_max_cc_bare: float = 0.0
    sigma_theta: float = 0.0
    elapsed_s: float = 0.0
    verdict: str = "NULL"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "theta_star_deg": self.theta_star_deg,
            "n_cells": self.n_cells,
            "n_qubits": self.n_qubits,
            "n_bridges": self.n_bridges,
            "relock_interval": self.relock_interval,
            "cc_schedule": self.cc_schedule,
            "shots": self.shots,
            "points": [p.to_dict() for p in self.points],
            "g_peak": self.g_peak,
            "g_peak_cc": self.g_peak_cc,
            "g_sustained_cc_ge_1": self.g_sustained_cc_ge_1,
            "entropy_min_qsd_bits": self.entropy_min_qsd_bits,
            "entropy_min_cc": self.entropy_min_cc,
            "entropy_at_max_cc_qsd": self.entropy_at_max_cc_qsd,
            "entropy_at_max_cc_bare": self.entropy_at_max_cc_bare,
            "sigma_theta": self.sigma_theta,
            "elapsed_s": self.elapsed_s,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def run_cascade_entanglement(
    shots: int = 2000,
    theta_star_deg: float = THETA_STAR_WILLOW_HW_DEG,
    cc_schedule: list[int] | None = None,
    max_cells: int | None = None,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
) -> CascadeEntanglementResult:
    """
    Full-chip cascade entanglement sweep on willow_pink.

    Default: all disjoint cells (~32 × 3Q = 96 qubits), Cc through 20 layers.
    """
    _require_cirq()
    from cirq_google import engine

    cc_schedule = cc_schedule or DEFAULT_CC_SCHEDULE
    theta = float(np.radians(theta_star_deg))
    sigma = abs(float(phase_force(theta)))

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    sampler = proc.get_sampler()
    device = proc.get_device()

    cells = extract_disjoint_3q_lines(device)
    if max_cells is not None:
        cells = cells[:max_cells]
    bridges = find_cascade_bridges(cells, device)
    n_qubits = len(sorted_chip_qubits(cells))

    out = CascadeEntanglementResult(
        theta_star_deg=theta_star_deg,
        n_cells=len(cells),
        n_qubits=n_qubits,
        n_bridges=len(bridges),
        relock_interval=relock_interval,
        cc_schedule=list(cc_schedule),
        shots=shots,
        sigma_theta=sigma,
    )

    print(
        f"[cascade] {n_qubits} qubits, {len(cells)} cells, {len(bridges)} bridge edges, "
        f"σ(θ*)={sigma:.2e}, relock/{relock_interval}",
        flush=True,
    )

    t0 = time.time()
    for cc in cc_schedule:
        print(f"[cascade] Cc={cc} ({shots} shots × 3 arms)", flush=True)
        arm_data: dict[str, dict] = {}
        for arm in ("qsd", "wrong", "bare"):
            circuit = build_cascade_entanglement_circuit(
                cells,
                bridges,
                cc,
                theta,
                arm=arm,
                relock_interval=relock_interval if arm != "bare" else None,
            )
            result = sampler.run(circuit, repetitions=shots)
            counts = _counts_from_result(result, "m", shots, n_qubits)
            arm_data[arm] = {
                "p_fail": p_fail_majority_one(counts, n_qubits=n_qubits),
                "entropy": shannon_entropy_bits(counts),
            }

        p_q = max(arm_data["qsd"]["p_fail"], 1e-6)
        pt = CascadeDepthPoint(
            cc=cc,
            p_fail_qsd=arm_data["qsd"]["p_fail"],
            p_fail_wrong=arm_data["wrong"]["p_fail"],
            p_fail_bare=arm_data["bare"]["p_fail"],
            g_qsd_vs_bare=arm_data["bare"]["p_fail"] / p_q,
            g_qsd_vs_wrong=arm_data["wrong"]["p_fail"] / p_q,
            entropy_qsd_bits=arm_data["qsd"]["entropy"],
            entropy_bare_bits=arm_data["bare"]["entropy"],
            entropy_wrong_bits=arm_data["wrong"]["entropy"],
            sigma_theta=sigma,
            shots=shots,
        )
        out.points.append(pt)
        print(
            f"  G={pt.g_qsd_vs_bare:.3f}  H_qsd={pt.entropy_qsd_bits:.2f}b  "
            f"H_bare={pt.entropy_bare_bits:.2f}b  p_fail qsd={pt.p_fail_qsd:.3f}",
            flush=True,
        )

    gs = [p.g_qsd_vs_bare for p in out.points if p.cc > 0]
    out.g_sustained_cc_ge_1 = sum(1 for g in gs if g > 1.0)
    if out.points:
        peak_pt = max(out.points, key=lambda p: p.g_qsd_vs_bare if p.cc > 0 else 0.0)
        out.g_peak = float(peak_pt.g_qsd_vs_bare)
        out.g_peak_cc = int(peak_pt.cc)

        ent_pts = [p for p in out.points if p.cc > 0]
        if ent_pts:
            min_ent = min(ent_pts, key=lambda p: p.entropy_qsd_bits)
            out.entropy_min_qsd_bits = min_ent.entropy_qsd_bits
            out.entropy_min_cc = min_ent.cc

        max_cc_pt = max(out.points, key=lambda p: p.cc)
        out.entropy_at_max_cc_qsd = max_cc_pt.entropy_qsd_bits
        out.entropy_at_max_cc_bare = max_cc_pt.entropy_bare_bits

    out.elapsed_s = time.time() - t0

    cc1 = next((p for p in out.points if p.cc == 1), None)
    cc2 = next((p for p in out.points if p.cc == 2), None)
    low_entropy = out.entropy_at_max_cc_qsd < out.entropy_at_max_cc_bare
    sustained = out.g_sustained_cc_ge_1 >= max(1, len(gs) * 2 // 3) and out.g_peak > 1.05

    if sustained and low_entropy:
        out.verdict = "CASCADE_STABILIZED"
        out.notes = (
            f"G>1 sustained on {n_qubits}Q cascade (peak G={out.g_peak:.2f} @ Cc={out.g_peak_cc}); "
            f"QSD entropy {out.entropy_at_max_cc_qsd:.2f}b < bare {out.entropy_at_max_cc_bare:.2f}b "
            f"at max Cc; σ(θ*)={sigma:.2e}."
        )
    elif out.g_peak > 1.0:
        out.verdict = "PARTIAL_CASCADE"
        out.notes = (
            f"Peak G={out.g_peak:.2f} @ Cc={out.g_peak_cc} on {n_qubits}Q; "
            f"{out.g_sustained_cc_ge_1}/{len(gs)} depths G>1; "
            f"H_qsd={out.entropy_at_max_cc_qsd:.2f}b vs H_bare={out.entropy_at_max_cc_bare:.2f}b."
        )
    else:
        out.verdict = "NULL"
        out.notes = f"No G>1 on {n_qubits}Q cascade (peak {out.g_peak:.2f})."

    if cc1 and cc2 and cc2.g_qsd_vs_bare > cc1.g_qsd_vs_bare:
        out.notes += " G rises Cc=1→2 (galaxy cascade propagation)."

    return out
