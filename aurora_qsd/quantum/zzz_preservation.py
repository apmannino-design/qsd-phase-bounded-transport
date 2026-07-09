"""
⟨ZZZ⟩ preservation line — QSD depth sunscreen vs matched-depth XY4 control.

Control construction:
  - Matched layer schedule (14L, re-lock /5)
  - XY4: three complete XY4 blocks per body layer (12 single-qubit pulses)
  - QSD: 11 single-qubit + 4 two-qubit per body layer (asymmetry documented)

Scoring requires noiseless ideal per arm:
  retention R = ⟨ZZZ⟩_noisy / ⟨ZZZ⟩_ideal

Verdict ladder (July 7 audit — simulation never endorses):
  NO_TARGET_SIGNAL  → |ideal(θ*)| < 0.5
  COHERENT_ARTIFACT   → ideal angle gap ≥ noisy angle gap
  NO_PROTECTION_ADVANTAGE → retention fail or R outside (0, 1.05]
  PROTECTION_CANDIDATE → passes all (hardware confirmation still required)
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
    _trilock_init_ops,
    _zzz_from_result,
    build_depth_sunscreen_circuit,
)

# Audit thresholds (July 7, 2026 retention audit)
MIN_TARGET_SIGNAL = 0.5
RETENTION_ADVANTAGE_MARGIN = 0.10
VALID_R_MAX = 1.05
INTERIOR_GAP_THRESHOLD = 0.5  # preregistered hardware handoff bar (informational)
POST_HOC_ARM_GAP_THRESHOLD = 0.05  # NOT preregistered


def _count_gates(ops: list) -> dict[str, int]:
    import cirq

    c = cirq.Circuit(ops)
    n1 = sum(1 for o in c.all_operations() if len(o.qubits) == 1)
    n2 = sum(1 for o in c.all_operations() if len(o.qubits) == 2)
    return {"one_qubit": n1, "two_qubit": n2, "moments": len(c)}


def _xy4_single_qubit(q) -> list:
    import cirq

    return [cirq.X(q), cirq.Y(q), cirq.X(q), cirq.Y(q)]


def _xy4_body_ops(qubits: list) -> list:
    """
    One body layer: three complete XY4 blocks (12 single-qubit pulses).

    Prior bug: dropping the 12th pulse made the layer ≈ I⊗I⊗Y (not DD).
    +1 single-qubit pulse per layer vs QSD body (11) is documented in gate budget.
    """
    ops: list = []
    for q in qubits:
        ops.extend(_xy4_single_qubit(q))
    return ops


def verify_xy4_layer(qubits: list | None = None) -> dict:
    """Verify repaired XY4 body is genuine DD, not degenerate I⊗I⊗Y."""
    import cirq

    if qubits is None:
        qubits = list(cirq.LineQubit.range(3))

    ops = _xy4_body_ops(qubits)
    n1 = len(ops)
    u_layer = cirq.unitary(cirq.Circuit(ops))

    # Degenerate old control: proportional to I⊗I⊗Y (only q2 rotates)
    y3 = np.kron(np.eye(2), np.kron(np.eye(2), cirq.unitary(cirq.Y)))
    overlap_y = float(np.abs(np.trace(u_layer.conj().T @ y3)) / u_layer.size)

    # Full XY4 on all qubits should differ strongly from single-qubit Y on q2
    return {
        "pulses_per_layer": n1,
        "expected_pulses": 12,
        "is_twelve_pulse_xy4": n1 == 12,
        "overlap_with_IIIY": overlap_y,
        "degenerate_IIIY": overlap_y > 0.99,
        "passes": n1 == 12 and overlap_y < 0.99,
    }


def build_xy4_matched_circuit(
    line: WillowLine,
    theta: float,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    measure: bool = True,
) -> "cirq.Circuit":
    """Matched-schedule XY4 dynamical decoupling control."""
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

    if measure:
        for q in qubits:
            ops.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    return cirq.Circuit(ops)


def build_qsd_circuit(
    line: WillowLine,
    theta: float,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    measure: bool = True,
) -> "cirq.Circuit":
    c = build_depth_sunscreen_circuit(
        line, theta=theta, layers=layers, relock_interval=relock_interval,
    )
    if not measure:
        import cirq

        return cirq.Circuit(
            [op for op in c.all_operations() if not cirq.is_measurement(op)]
        )
    return c


def ideal_zzz_from_circuit(circuit) -> float:
    """Noiseless ⟨Z⊗Z⊗Z⟩ via statevector simulation."""
    _require_cirq()
    import cirq

    c = cirq.Circuit(
        [op for op in circuit.all_operations() if not cirq.is_measurement(op)]
    )
    sv = cirq.Simulator().simulate(c).final_state_vector
    acc = 0.0
    for i, amp in enumerate(sv):
        sign = 1.0 if bin(i).count("1") % 2 == 0 else -1.0
        acc += sign * (abs(amp) ** 2)
    return float(np.real(acc))


def ideal_zzz_density_matrix(circuit) -> float:
    """Independent ideal check via density-matrix simulation."""
    _require_cirq()
    import cirq

    c = cirq.Circuit(
        [op for op in circuit.all_operations() if not cirq.is_measurement(op)]
    )
    rho = cirq.DensityMatrixSimulator().simulate(c).final_density_matrix
    zzz = np.array([[1, 0], [0, -1]], dtype=complex)
    op = np.kron(zzz, np.kron(zzz, zzz))
    return float(np.real(np.trace(rho @ op)))


def compute_retention(measured: float | None, ideal: float) -> dict:
    """Retention R = measured / ideal."""
    eps = 1e-9
    out: dict = {
        "ideal_zzz": ideal,
        "measured_zzz": measured,
        "retention_signed": None,
        "retention_magnitude": None,
        "noise_delta": None,
        "magnitude_ratio": None,
    }
    if measured is not None:
        out["noise_delta"] = float(measured - ideal)
        if abs(ideal) > eps:
            out["retention_signed"] = float(measured / ideal)
            out["retention_magnitude"] = float(abs(measured) / abs(ideal))
            out["magnitude_ratio"] = out["retention_magnitude"]
    return out


def _gate_budget_metadata(line: WillowLine, theta: float, layers: int, relock: int) -> dict:
    qubits = list(line.qubits())
    qsd_ops = list(build_qsd_circuit(line, theta, layers, relock, measure=False).all_operations())
    xy4_ops = list(
        build_xy4_matched_circuit(line, theta, layers, relock, measure=False).all_operations()
    )
    qsd_body = _count_gates(_sunscreen_body_ops(qubits, theta, with_init=False))
    xy4_body = _count_gates(_xy4_body_ops(qubits))
    return {
        "layers": layers,
        "relock_interval": relock,
        "qsd_body_per_layer": qsd_body,
        "xy4_body_per_layer": xy4_body,
        "qsd_total": _count_gates(qsd_ops),
        "xy4_total": _count_gates(xy4_ops),
        "matched_1q_per_body_layer": False,
        "one_qubit_asymmetry": (
            f"XY4 has {xy4_body['one_qubit']} 1q/layer vs QSD {qsd_body['one_qubit']} "
            f"(repaired full XY4; prior 11-pulse layer was degenerate I⊗I⊗Y)."
        ),
        "two_qubit_asymmetry": (
            f"QSD has {qsd_body['two_qubit']} 2q/layer; XY4 has 0 (standard DD)."
        ),
        "xy4_layer_check": verify_xy4_layer(qubits),
    }


def _run_arm(
    sampler,
    line: WillowLine,
    arm: str,
    theta: float,
    shots: int,
    layers: int,
    relock: int,
    ideals_only: bool = False,
) -> dict:
    if arm == "xy4":
        c_noisy = build_xy4_matched_circuit(line, theta, layers, relock, measure=True)
        c_ideal = build_xy4_matched_circuit(line, theta, layers, relock, measure=False)
    elif arm == "qsd":
        c_noisy = build_qsd_circuit(line, theta, layers, relock, measure=True)
        c_ideal = build_qsd_circuit(line, theta, layers, relock, measure=False)
    else:
        raise ValueError(arm)

    ideal_sv = ideal_zzz_from_circuit(c_ideal)
    ideal_dm = ideal_zzz_density_matrix(c_ideal)
    measured = None
    if not ideals_only:
        measured = _zzz_from_result(sampler.run(c_noisy, repetitions=shots), shots)

    ret = compute_retention(measured, ideal_sv)
    ret.update({
        "arm": arm,
        "theta_deg": float(np.degrees(theta)),
        "shots": shots if not ideals_only else 0,
        "ideal_zzz_dm": ideal_dm,
        "ideal_paths_agree": abs(ideal_sv - ideal_dm) < 1e-5,
    })
    return ret


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
    preregistration: dict = field(default_factory=dict)
    arms: dict = field(default_factory=dict)
    arm_gaps: dict = field(default_factory=dict)
    retention_theta_sweep: list = field(default_factory=list)
    retention_analysis: dict = field(default_factory=dict)
    verdict: str = "PENDING_RETENTION"
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
            "preregistration": self.preregistration,
            "arms": self.arms,
            "arm_gaps": self.arm_gaps,
            "retention_theta_sweep": self.retention_theta_sweep,
            "retention_analysis": self.retention_analysis,
            "verdict": self.verdict,
            "endorsable": bool(self.endorsable),
            "notes": self.notes,
        }


def _audit_theta_points(theta_star_deg: float) -> list[float]:
    """θ points matching July 7 audit table (2°–92.49°)."""
    pts = [2.0, 8.0, 14.0, 20.0, theta_star_deg, 26.0, 32.0, 38.0, 44.0, 50.0, 56.0, 62.0, 68.0, 74.0, 80.0, 86.0]
    wrong = theta_star_deg + 70.0
    if wrong not in pts:
        pts.append(wrong)
    return sorted(pts)


def run_retention_theta_sweep(
    sampler,
    line: WillowLine,
    shots: int,
    layers: int,
    relock: int,
    theta_star_deg: float = OPTIMAL_THETA_DEG,
    theta_points_deg: list[float] | None = None,
    ideals_only: bool = False,
) -> list[dict]:
    """R(θ): noisy/ideal for QSD at each θ."""
    points_deg = theta_points_deg or _audit_theta_points(theta_star_deg)
    out: list[dict] = []
    for td in points_deg:
        theta = float(np.radians(td))
        row = _run_arm(sampler, line, "qsd", theta, shots, layers, relock, ideals_only=ideals_only)
        out.append(row)
    return out


def _analyze_retention_curve(
    sweep: list[dict],
    theta_star_deg: float,
    xy4_retention_signed: float | None,
) -> dict:
    if not sweep:
        return {"status": "no_sweep"}

    rs = [p["retention_signed"] for p in sweep if p.get("retention_signed") is not None]
    thetas = [p["theta_deg"] for p in sweep if p.get("retention_signed") is not None]
    if not rs:
        ideals = [p["ideal_zzz"] for p in sweep]
        noisies = [p.get("measured_zzz") for p in sweep]
        return {
            "status": "ideals_only",
            "ideal_curve": [{"theta_deg": t, "ideal": i} for t, i in zip(thetas or [p["theta_deg"] for p in sweep], ideals)],
            "noisy_curve": [{"theta_deg": p["theta_deg"], "noisy": p.get("measured_zzz")} for p in sweep],
        }

    arr = np.array(rs)
    peak_idx = int(np.argmax(arr))
    star_idx = int(np.argmin([abs(t - theta_star_deg) for t in thetas]))

    return {
        "status": "computed",
        "r_at_theta_star": float(rs[star_idx]),
        "theta_nearest_star_deg": thetas[star_idx],
        "r_peak": float(arr[peak_idx]),
        "theta_peak_deg": thetas[peak_idx],
        "r_median": float(np.median(arr)),
        "r_xy4": xy4_retention_signed,
        "peak_near_theta_star": abs(thetas[peak_idx] - theta_star_deg) <= 5.0,
        "curve": [{"theta_deg": t, "R": r, "ideal": p["ideal_zzz"], "noisy": p.get("measured_zzz")}
                  for t, r, p in zip(thetas, rs, sweep[: len(thetas)])],
    }


def assign_retention_verdict(arms: dict, arm_gaps: dict, analysis: dict) -> tuple[str, bool, str]:
    """
    July 7 audit verdict ladder. endorsable is always False on simulation alone.
    """
    qsd = arms["qsd_theta_star"]
    wrong = arms["qsd_wrong_theta"]
    xy4 = arms["xy4_matched"]

    ideal_star = qsd["ideal_zzz"]
    ideal_wrong = wrong["ideal_zzz"]
    z_star = qsd.get("measured_zzz")
    z_wrong = wrong.get("measured_zzz")
    r_star = qsd.get("retention_signed")
    r_xy4 = xy4.get("retention_signed")

    mag_note = ""
    if arm_gaps.get("magnitude_qsd_vs_xy4_delta") is not None:
        mag_note = f" |magnitude Δ={arm_gaps['magnitude_qsd_vs_xy4_delta']:.3f}."

    if abs(ideal_star) < MIN_TARGET_SIGNAL:
        return (
            "NO_TARGET_SIGNAL",
            False,
            f"|ideal(θ*)|={abs(ideal_star):.3f} < {MIN_TARGET_SIGNAL}; nothing to preserve.{mag_note}",
        )

    if z_star is not None and z_wrong is not None:
        ideal_gap = abs(ideal_star - ideal_wrong)
        noisy_gap = abs(z_star - z_wrong)
        if ideal_gap >= noisy_gap - 1e-9:
            return (
                "COHERENT_ARTIFACT",
                False,
                f"Ideal angle gap {ideal_gap:.3f} ≥ noisy gap {noisy_gap:.3f}; "
                f"signature is unitary, not protective.{mag_note}",
            )

    if r_star is None or r_xy4 is None:
        return (
            "PENDING_RETENTION",
            False,
            "Noisy retention not computed." + mag_note,
        )

    valid_r = 0.0 < r_star <= VALID_R_MAX
    beats_xy4 = r_star >= r_xy4 + RETENTION_ADVANTAGE_MARGIN
    peak_ok = analysis.get("peak_near_theta_star", False)

    if not valid_r or not beats_xy4:
        return (
            "NO_PROTECTION_ADVANTAGE",
            False,
            f"R(θ*)={r_star:.3f}, R(XY4)={r_xy4:.3f}; need R∈(0,{VALID_R_MAX}] and "
            f"R(θ*)≥R(XY4)+{RETENTION_ADVANTAGE_MARGIN}.{mag_note}",
        )

    if peak_ok:
        return (
            "PROTECTION_CANDIDATE",
            False,
            f"Simulation candidate: R(θ*)={r_star:.3f}, peak near θ*; hardware confirmation required.{mag_note}",
        )

    return (
        "NO_PROTECTION_ADVANTAGE",
        False,
        f"R(θ*)={r_star:.3f} but retention peak at θ={analysis.get('theta_peak_deg', '?')}°, "
        f"not θ*={analysis.get('theta_nearest_star_deg', '?')}°.{mag_note}",
    )


def run_zzz_preservation_benchmark(
    shots: int = 4000,
    sweep_shots: int = 512,
    line_name: str = "interior",
    theta_star_deg: float = OPTIMAL_THETA_DEG,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    negative_offset_deg: float = 70.0,
    run_theta_sweep: bool = True,
    ideals_only: bool = False,
) -> ZZZPreservationResult:
    _require_cirq()
    from cirq_google import engine

    line = get_line(line_name)
    theta_star = float(np.radians(theta_star_deg))
    theta_wrong = negative_control_angle(theta_star, offset_deg=negative_offset_deg)

    sampler = None
    if not ideals_only:
        proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
            "willow_pink"
        )
        sampler = proc.get_sampler()

    out = ZZZPreservationResult(
        line=line.labels(),
        theta_star_deg=theta_star_deg,
        depth_layers=layers,
        relock_interval=relock_interval,
        shots=shots,
        gate_budget=_gate_budget_metadata(line, theta_star, layers, relock_interval),
        preregistration={
            "min_target_signal": MIN_TARGET_SIGNAL,
            "retention_advantage_margin": RETENTION_ADVANTAGE_MARGIN,
            "valid_r_range": f"(0, {VALID_R_MAX}]",
            "arm_gap_0_05": "NOT preregistered — post-hoc exploratory only",
            "simulation_endorses": False,
        },
    )

    xy4 = _run_arm(sampler, line, "xy4", theta_star, shots, layers, relock_interval, ideals_only)
    qsd_star = _run_arm(sampler, line, "qsd", theta_star, shots, layers, relock_interval, ideals_only)
    qsd_wrong = _run_arm(sampler, line, "qsd", theta_wrong, shots, layers, relock_interval, ideals_only)

    out.arms = {"xy4_matched": xy4, "qsd_theta_star": qsd_star, "qsd_wrong_theta": qsd_wrong}

    if not ideals_only:
        z_star, z_wrong, z_xy4 = qsd_star["measured_zzz"], qsd_wrong["measured_zzz"], xy4["measured_zzz"]
        out.arm_gaps = {
            "angle_specific_signed": float(z_star - z_wrong),
            "angle_specific_abs": abs(z_star - z_wrong),
            "qsd_vs_xy4_signed": float(z_star - z_xy4),
            "qsd_vs_xy4_abs": abs(z_star - z_xy4),
            "ideal_angle_gap": abs(qsd_star["ideal_zzz"] - qsd_wrong["ideal_zzz"]),
            "noisy_angle_gap": abs(z_star - z_wrong),
            "magnitude_qsd": abs(z_star),
            "magnitude_xy4": abs(z_xy4),
            "magnitude_qsd_vs_xy4_delta": abs(abs(z_star) - abs(z_xy4)),
            "post_hoc_arm_gap_passes_0_05": abs(z_star - z_xy4) >= POST_HOC_ARM_GAP_THRESHOLD,
            "post_hoc_note": "≥0.05 |θ*−XY4| was NOT preregistered",
        }

    if run_theta_sweep:
        out.retention_theta_sweep = run_retention_theta_sweep(
            sampler,
            line,
            sweep_shots,
            layers,
            relock_interval,
            theta_star_deg=theta_star_deg,
            ideals_only=ideals_only,
        )

    analysis = _analyze_retention_curve(
        out.retention_theta_sweep,
        theta_star_deg,
        xy4.get("retention_signed"),
    )
    analysis["ideal_at_star"] = qsd_star["ideal_zzz"]
    analysis["ideal_xy4"] = xy4["ideal_zzz"]
    analysis["ideal_wrong"] = qsd_wrong["ideal_zzz"]
    out.retention_analysis = analysis

    verdict, endorsable, notes = assign_retention_verdict(out.arms, out.arm_gaps, analysis)
    out.verdict = verdict
    out.endorsable = endorsable
    out.notes = notes
    return out


def run_retention_audit_benchmark(
    shots: int = 4000,
    sweep_shots: int = 1000,
    theta_star_deg: float = OPTIMAL_THETA_DEG,
    ideals_only: bool = False,
) -> dict:
    """July 7 audit protocol wrapper."""
    result = run_zzz_preservation_benchmark(
        shots=shots,
        sweep_shots=sweep_shots,
        theta_star_deg=theta_star_deg,
        run_theta_sweep=True,
        ideals_only=ideals_only,
    )
    return {
        "audit": "RESULTS_JULY07_2026_RETENTION_AUDIT",
        "xy4_repaired": True,
        "result": result.to_dict(),
        "stamp_status": "HOLD — simulation does not endorse",
        "endorsable": False,
        "hardware_ready": False,
    }


def run_zzz_preservation_campaign(**kwargs) -> dict:
    """Alias for benchmark campaign JSON output."""
    result = run_zzz_preservation_benchmark(line_name="interior", **kwargs)
    return {
        "candidate": "zzz_preservation_interior",
        "protocol": "repaired XY4 + retention R=noisy/ideal + audit θ-sweep",
        "result": result.to_dict(),
        "stamp_status": "HOLD",
        "endorsable": False,
        "hardware_ready": False,
    }
