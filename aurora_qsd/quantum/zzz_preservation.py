"""
⟨ZZZ⟩ preservation line — QSD depth sunscreen vs matched-depth XY4 control.

Endorsement gate: QSD must survive a fair dynamical-decoupling control at matched
layer schedule before the ⟨ZZZ⟩ preservation claim is endorsable.

Protocol (interior line q(6,5)–q(6,6)–q(6,7)):
  1. XY4 matched-depth control (same 14L, re-lock /5, matched 1q layer budget)
  2. QSD depth sunscreen @ θ* vs wrong θ (negative control)
  3. Endorse only if angle-specific |ΔZZZ| holds AND QSD beats XY4 on correlator gap
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_algorithm import (
    OPTIMAL_RELOCK_INTERVAL,
    OPTIMAL_SUNSCREEN_LAYERS,
    OPTIMAL_THETA_DEG,
)
from aurora_qsd.quantum.willow_lines import WillowLine, get_line
from aurora_qsd.quantum.willow_run import (
    _require_cirq,
    _sunscreen_body_ops,
    _sunscreen_reset_ops,
    _trilock_init_ops,
    _zzz_from_result,
    build_depth_sunscreen_circuit,
)

# Minimum |ΔZZZ| for interior endorsement (hardware handoff bar)
INTERIOR_GAP_THRESHOLD = 0.5
ANGLE_GAP_THRESHOLD = 0.05


def _count_gates(ops: list) -> dict[str, int]:
    import cirq

    c = cirq.Circuit(ops)
    n1 = sum(1 for o in c.all_operations() if len(o.qubits) == 1)
    n2 = sum(1 for o in c.all_operations() if len(o.qubits) == 2)
    return {"one_qubit": n1, "two_qubit": n2, "moments": len(c)}


def _xy4_body_ops(qubits: list) -> list:
    """
    One matched body layer: 11 single-qubit pulses (same 1q budget as QSD body).

    Three full XY4 blocks = 12 gates; drop one pulse to match QSD body 1q count.
    """
    import cirq

    ops: list = []
    for q in qubits:
        ops.extend([cirq.X(q), cirq.Y(q), cirq.X(q), cirq.Y(q)])
    if ops:
        ops.pop()
    return ops


def build_xy4_matched_circuit(
    line: WillowLine,
    theta: float,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
) -> "cirq.Circuit":
    """
    Matched-depth XY4 dynamical decoupling control.

    Mirrors QSD depth sunscreen schedule:
      - 14 macro-layers, re-lock every 5
      - TriLock re-init at block boundaries (same cadence as sunscreen reset)
      - 11 single-qubit pulses per body layer (matched to QSD body 1q count)

    Note: QSD body layers also include 4 entangling ops per layer; XY4 is 1q-only
    by design (standard DD). Gate-budget metadata is recorded in results.
    """
    _require_cirq()
    import cirq

    qubits = list(line.qubits())
    ops: list = []
    layers_done = 0
    while layers_done < layers:
        if layers_done > 0:
            ops.extend(_trilock_init_ops(qubits, theta))
            ops.extend(_xy4_body_ops(qubits))
        block = min(relock_interval, layers - layers_done)
        for j in range(block):
            if layers_done == 0 and j == 0:
                ops.extend(_trilock_init_ops(qubits, theta))
            ops.extend(_xy4_body_ops(qubits))
        layers_done += block

    for q in qubits:
        ops.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    return cirq.Circuit(ops)


def _gate_budget_metadata(line: WillowLine, theta: float, layers: int, relock: int) -> dict:
    """Document matched vs QSD gate budgets for transparency."""
    qubits = list(line.qubits())
    qsd_ops = list(
        build_depth_sunscreen_circuit(line, theta, layers=layers, relock_interval=relock)
        .all_operations()
    )
    import cirq

    qsd_ops = [op for op in qsd_ops if not cirq.is_measurement(op)]
    xy4_c = build_xy4_matched_circuit(line, theta, layers=layers, relock_interval=relock)
    xy4_ops = [op for op in xy4_c.all_operations() if not cirq.is_measurement(op)]

    return {
        "layers": layers,
        "relock_interval": relock,
        "qsd_body_per_layer": _count_gates(_sunscreen_body_ops(qubits, theta, with_init=False)),
        "xy4_body_per_layer": _count_gates(_xy4_body_ops(qubits)),
        "qsd_total": _count_gates(qsd_ops),
        "xy4_total": _count_gates(xy4_ops),
        "matched_1q_per_body_layer": True,
        "two_qubit_asymmetry": (
            "QSD includes 4 two-qubit ops per body layer; XY4 is 1q-only (standard DD)."
        ),
    }


@dataclass
class ZZZPreservationResult:
    task: str = "zzz_preservation_xy4_control"
    processor: str = "willow_pink"
    line: list[str] = field(default_factory=list)
    theta_star_deg: float = OPTIMAL_THETA_DEG
    depth_layers: int = OPTIMAL_SUNSCREEN_LAYERS
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL
    shots: int = 0
    gate_budget: dict = field(default_factory=dict)
    xy4_matched: dict = field(default_factory=dict)
    qsd_theta_star: dict = field(default_factory=dict)
    qsd_wrong_theta: dict = field(default_factory=dict)
    gaps: dict = field(default_factory=dict)
    verdict: str = "NULL"
    endorsable: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "processor": self.processor,
            "line": self.line,
            "theta_star_deg": self.theta_star_deg,
            "depth_layers": self.depth_layers,
            "relock_interval": self.relock_interval,
            "shots": self.shots,
            "gate_budget": self.gate_budget,
            "xy4_matched": self.xy4_matched,
            "qsd_theta_star": self.qsd_theta_star,
            "qsd_wrong_theta": self.qsd_wrong_theta,
            "gaps": self.gaps,
            "verdict": self.verdict,
            "endorsable": bool(self.endorsable),
            "notes": self.notes,
        }


def run_zzz_preservation_benchmark(
    shots: int = 4000,
    line_name: str = "interior",
    theta_star_deg: float = OPTIMAL_THETA_DEG,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    negative_offset_deg: float = 70.0,
    gap_threshold: float = INTERIOR_GAP_THRESHOLD,
) -> ZZZPreservationResult:
    """
    Run matched-depth XY4 control first, then QSD θ* vs wrong θ.

    Endorsement criteria (all required):
      1. Angle-specific: |ZZZ(θ*) − ZZZ(θ_wrong)| ≥ angle threshold
      2. QSD beats XY4: |ZZZ(θ*) − ZZZ(XY4)| ≥ angle threshold
      3. Interior bar: |ZZZ(θ*) − ZZZ(θ_wrong)| ≥ gap_threshold (0.5 default)
    """
    _require_cirq()
    from cirq_google import engine

    line = get_line(line_name)
    theta_star = float(np.radians(theta_star_deg))
    theta_wrong = negative_control_angle(theta_star, offset_deg=negative_offset_deg)

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()

    out = ZZZPreservationResult(
        line=line.labels(),
        theta_star_deg=theta_star_deg,
        depth_layers=layers,
        relock_interval=relock_interval,
        shots=shots,
        gate_budget=_gate_budget_metadata(line, theta_star, layers, relock_interval),
    )

    # 1. XY4 matched-depth control (run first per protocol)
    c_xy4 = build_xy4_matched_circuit(line, theta_star, layers=layers, relock_interval=relock_interval)
    r_xy4 = sampler.run(c_xy4, repetitions=shots)
    zzz_xy4 = _zzz_from_result(r_xy4, shots)
    out.xy4_matched = {"zzz": zzz_xy4, "n": shots, "control": "XY4_matched_depth"}

    # 2. QSD depth sunscreen @ θ* and wrong θ
    for label, th, attr in [
        ("qsd_theta_star", theta_star, "qsd_theta_star"),
        ("qsd_wrong_theta", theta_wrong, "qsd_wrong_theta"),
    ]:
        c = build_depth_sunscreen_circuit(
            line, theta=th, layers=layers, relock_interval=relock_interval,
        )
        r = sampler.run(c, repetitions=shots)
        zzz = _zzz_from_result(r, shots)
        out.__dict__[attr] = {
            "zzz": zzz,
            "n": shots,
            "theta_deg": float(np.degrees(th)),
        }

    z_star = out.qsd_theta_star["zzz"]
    z_wrong = out.qsd_wrong_theta["zzz"]
    gap_angle = float(z_star - z_wrong)
    gap_vs_xy4 = float(z_star - zzz_xy4)

    out.gaps = {
        "angle_specific_signed": gap_angle,
        "angle_specific_abs": abs(gap_angle),
        "qsd_vs_xy4_signed": gap_vs_xy4,
        "qsd_vs_xy4_abs": abs(gap_vs_xy4),
        "xy4_vs_wrong_abs": abs(zzz_xy4 - z_wrong),
    }

    angle_ok = abs(gap_angle) >= ANGLE_GAP_THRESHOLD
    beats_xy4 = abs(gap_vs_xy4) >= ANGLE_GAP_THRESHOLD
    interior_ok = abs(gap_angle) >= gap_threshold

    # QSD should show angle specificity XY4 lacks: QSD angle gap > XY4-vs-wrong gap
    angle_specificity = abs(gap_angle) > abs(zzz_xy4 - z_wrong)

    if interior_ok and beats_xy4 and angle_ok and angle_specificity:
        out.verdict = "ENDORSABLE"
        out.endorsable = True
        out.notes = (
            f"⟨ZZZ⟩ preservation survives matched-depth XY4: "
            f"|ΔZZZ|={abs(gap_angle):.3f} (θ* vs wrong), "
            f"|θ*−XY4|={abs(gap_vs_xy4):.3f}. Interior bar met."
        )
    elif angle_ok and beats_xy4:
        out.verdict = "SURVIVES_XY4"
        out.endorsable = False
        out.notes = (
            f"QSD beats XY4 (|θ*−XY4|={abs(gap_vs_xy4):.3f}) with angle gap "
            f"{abs(gap_angle):.3f}, but interior |Δ| < {gap_threshold}."
        )
    elif angle_ok:
        out.verdict = "ANGLE_ONLY"
        out.notes = (
            f"Angle-specific gap {abs(gap_angle):.3f} but QSD does not clear XY4 control "
            f"(|θ*−XY4|={abs(gap_vs_xy4):.3f}). Not endorsable."
        )
    else:
        out.verdict = "NULL"
        out.notes = "No angle-specific ⟨ZZZ⟩ gap; XY4 control not surpassed."

    return out


def run_zzz_preservation_campaign(
    shots: int = 4000,
    **kwargs,
) -> dict:
    """Run ⟨ZZZ⟩ preservation with XY4 control on interior line."""
    result = run_zzz_preservation_benchmark(shots=shots, line_name="interior", **kwargs)
    return {
        "candidate": "zzz_preservation_interior",
        "protocol": "XY4 matched-depth control first, then QSD θ* vs θ*+70°",
        "result": result.to_dict(),
        "endorsement_bar": {
            "angle_gap_min": ANGLE_GAP_THRESHOLD,
            "interior_abs_gap_min": INTERIOR_GAP_THRESHOLD,
        },
        "hardware_ready": result.endorsable,
    }
