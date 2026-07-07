"""
⟨ZZZ⟩ preservation line — QSD depth sunscreen vs matched-depth XY4 control.

Control construction: matched layers, matched 1q count, documented 2q asymmetry.

Scoring requires noiseless reference per arm:
  retention R = ⟨ZZZ⟩_noisy / ⟨ZZZ⟩_ideal

Arm-vs-arm gaps alone are insufficient — a coherent rotation (different unitary,
zero protection) can pass |θ*−XY4| thresholds via sign flips while |magnitude|
stays a dead heat.

Decisive artifact: R(θ) = noisy/ideal across θ sweep.
  Flat R(θ)  → coherent artifact (unitarity, not protection)
  R peaked at θ* → angle-specific retention

NOT preregistered: the ≥0.05 |θ*−XY4| bar was added post-hoc and is reported
for transparency only — it does not gate endorsement.
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

# Interior |ΔZZZ| bar from hardware handoff (preregistered elsewhere)
INTERIOR_GAP_THRESHOLD = 0.5

# Post-hoc exploratory — NOT preregistered before XY4 run
POST_HOC_ARM_GAP_THRESHOLD = 0.05

# Retention endorsement: R(θ*) must exceed R(XY4) by this margin (exploratory)
RETENTION_MARGIN = 0.15

# Flat R(θ) if peak - median < this (exploratory)
RETENTION_PEAK_FLATNESS = 0.10


def _count_gates(ops: list) -> dict[str, int]:
    import cirq

    c = cirq.Circuit(ops)
    n1 = sum(1 for o in c.all_operations() if len(o.qubits) == 1)
    n2 = sum(1 for o in c.all_operations() if len(o.qubits) == 2)
    return {"one_qubit": n1, "two_qubit": n2, "moments": len(c)}


def _xy4_body_ops(qubits: list) -> list:
    """One matched body layer: 11 single-qubit pulses (same 1q budget as QSD body)."""
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
    measure: bool = True,
) -> "cirq.Circuit":
    """Matched-depth XY4 DD control (same schedule as QSD sunscreen)."""
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
    """QSD depth sunscreen with optional measurement stripping for ideal sim."""
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
    """Noiseless ⟨Z⊗Z⊗Z⟩ via statevector simulation (qsim-class, seconds)."""
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


def compute_retention(measured: float, ideal: float) -> dict:
    """
    Retention R = measured / ideal.

    Interpretation:
      ideal ≈ −1, measured ≈ −0.30 → R ≈ 0.30 (30% of target correlator retained)
      ideal ≈ −0.30, measured ≈ −0.30 → R ≈ 1.0 (noiseless matched; no protection)
    """
    eps = 1e-9
    out = {
        "ideal_zzz": ideal,
        "measured_zzz": measured,
        "retention_signed": None,
        "retention_magnitude": None,
        "noise_delta": float(measured - ideal),
        "magnitude_ratio": float(abs(measured) / abs(ideal)) if abs(ideal) > eps else None,
    }
    if abs(ideal) > eps:
        out["retention_signed"] = float(measured / ideal)
        out["retention_magnitude"] = float(abs(measured) / abs(ideal))
    return out


def _gate_budget_metadata(line: WillowLine, theta: float, layers: int, relock: int) -> dict:
    qubits = list(line.qubits())
    import cirq

    qsd_ops = [
        op
        for op in build_qsd_circuit(line, theta, layers, relock, measure=False).all_operations()
    ]
    xy4_ops = [
        op
        for op in build_xy4_matched_circuit(line, theta, layers, relock, measure=False).all_operations()
    ]
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


def _run_arm(
    sampler,
    line: WillowLine,
    arm: str,
    theta: float,
    shots: int,
    layers: int,
    relock: int,
) -> dict:
    """Run one arm: noisy measurement + noiseless ideal + retention."""
    if arm == "xy4":
        c_noisy = build_xy4_matched_circuit(line, theta, layers, relock, measure=True)
        c_ideal = build_xy4_matched_circuit(line, theta, layers, relock, measure=False)
    elif arm == "qsd":
        c_noisy = build_qsd_circuit(line, theta, layers, relock, measure=True)
        c_ideal = build_qsd_circuit(line, theta, layers, relock, measure=False)
    else:
        raise ValueError(arm)

    measured = _zzz_from_result(sampler.run(c_noisy, repetitions=shots), shots)
    ideal = ideal_zzz_from_circuit(c_ideal)
    ret = compute_retention(measured, ideal)
    return {
        "arm": arm,
        "theta_deg": float(np.degrees(theta)),
        "shots": shots,
        **ret,
    }


@dataclass
class RetentionSweepPoint:
    theta_deg: float
    ideal_zzz: float
    measured_zzz: float
    retention_signed: float | None
    retention_magnitude: float | None


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


def run_retention_theta_sweep(
    sampler,
    line: WillowLine,
    shots: int,
    layers: int,
    relock: int,
    theta_center_deg: float = OPTIMAL_THETA_DEG,
    span_deg: float = 40.0,
    n_points: int = 17,
) -> list[dict]:
    """R(θ) = noisy/ideal for QSD depth sunscreen across partition angle."""
    thetas_deg = np.linspace(theta_center_deg - span_deg, theta_center_deg + span_deg, n_points)
    points: list[dict] = []
    for td in thetas_deg:
        theta = float(np.radians(td))
        row = _run_arm(sampler, line, "qsd", theta, shots, layers, relock)
        points.append(row)
    return points


def _analyze_retention_curve(
    sweep: list[dict],
    theta_star_deg: float,
    xy4_retention_signed: float | None,
) -> dict:
    """Detect flat R(θ) vs peak at θ*."""
    if not sweep:
        return {"status": "no_sweep"}

    rs = [p["retention_signed"] for p in sweep if p.get("retention_signed") is not None]
    thetas = [p["theta_deg"] for p in sweep if p.get("retention_signed") is not None]
    if not rs:
        return {"status": "undefined_retention"}

    arr = np.array(rs)
    peak_idx = int(np.argmax(arr))
    peak_theta = thetas[peak_idx]
    peak_r = float(arr[peak_idx])
    median_r = float(np.median(arr))
    star_idx = int(np.argmin([abs(t - theta_star_deg) for t in thetas]))
    r_at_star = float(rs[star_idx])
    theta_at_star = thetas[star_idx]

    flat = (peak_r - median_r) < RETENTION_PEAK_FLATNESS
    peak_near_star = abs(peak_theta - theta_star_deg) <= (
        thetas[1] - thetas[0] if len(thetas) > 1 else 5.0
    )

    beats_xy4 = (
        xy4_retention_signed is not None
        and r_at_star > xy4_retention_signed + RETENTION_MARGIN
    )

    return {
        "status": "computed",
        "r_at_theta_star": r_at_star,
        "theta_nearest_star_deg": theta_at_star,
        "r_peak": peak_r,
        "theta_peak_deg": peak_theta,
        "r_median": median_r,
        "r_xy4": xy4_retention_signed,
        "flat_curve": flat,
        "peak_near_theta_star": peak_near_star,
        "retention_beats_xy4": beats_xy4,
        "curve": [{"theta_deg": t, "R": r} for t, r in zip(thetas, rs)],
    }


def _assign_verdict(
    arm_gaps: dict,
    retention: dict,
    analysis: dict,
) -> tuple[str, bool, str]:
    """
    Endorsement requires retention dominance, not arm-vs-arm sign flips.

    Never returns ENDORSABLE without R(θ*) ≫ R(XY4) and peaked R(θ).
    """
    r_star = analysis.get("r_at_theta_star")
    r_xy4 = analysis.get("r_xy4")
    mag_qsd = arm_gaps.get("magnitude_qsd_vs_xy4_delta")
    mag_note = ""
    if mag_qsd is not None:
        mag_note = f" |magnitude dead-heat check: |θ*|-|XY4|={mag_qsd:.3f}."

    if r_star is None or r_xy4 is None:
        return (
            "PENDING_RETENTION",
            False,
            "Retention R(θ) not computed; arm-vs-arm gaps alone are insufficient." + mag_note,
        )

    ideal_star = analysis.get("ideal_at_star")
    if ideal_star is not None and abs(ideal_star) < 0.35:
        return (
            "WEAK_TARGET",
            False,
            f"|ideal(θ*)|={abs(ideal_star):.3f} — unitary targets weak ⟨ZZZ⟩, not −1; "
            f"R(θ*)={r_star:.3f} vs R(XY4)={r_xy4:.3f} does not establish protection.{mag_note}",
        )

    if analysis.get("flat_curve"):
        return (
            "COHERENT_ARTIFACT",
            False,
            f"R(θ) flat (peak−median={analysis.get('r_peak', 0) - analysis.get('r_median', 0):.3f}); "
            f"likely unitary rotation, not noise protection.{mag_note}",
        )

    if r_star is not None and abs(r_star - 1.0) < 0.05 and abs(analysis.get("ideal_at_star", 0)) < 0.5:
        return (
            "COHERENT_ARTIFACT",
            False,
            f"Noisy ≈ noiseless at θ* (R≈{r_star:.3f}); circuit computes a function, does not protect.{mag_note}",
        )

    if analysis.get("retention_beats_xy4") and analysis.get("peak_near_theta_star"):
        return (
            "RETENTION_WIN",
            True,
            f"R(θ*)={r_star:.3f} ≫ R(XY4)={r_xy4:.3f}; peak near θ*={analysis.get('theta_peak_deg'):.1f}°.{mag_note}",
        )

    if abs(arm_gaps.get("angle_specific_abs", 0)) >= INTERIOR_GAP_THRESHOLD:
        return (
            "ARM_GAP_ONLY",
            False,
            f"Arm-vs-arm |ΔZZZ|={arm_gaps['angle_specific_abs']:.3f} passes interior bar, but "
            f"retention R(θ*)={r_star:.3f} vs R(XY4)={r_xy4:.3f} does not endorse "
            f"(need R(θ*) > R(XY4)+{RETENTION_MARGIN}).{mag_note}",
        )

    return (
        "NULL",
        False,
        f"No retention win: R(θ*)={r_star:.3f}, R(XY4)={r_xy4:.3f}.{mag_note}",
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
    sweep_span_deg: float = 40.0,
    sweep_n_points: int = 17,
) -> ZZZPreservationResult:
    """
    Matched-depth XY4 control + retention scoring vs noiseless ideal.

    Protocol order:
      1. Noiseless ideal ⟨ZZZ⟩ per arm (statevector)
      2. XY4 matched-depth noisy
      3. QSD @ θ* and wrong θ noisy
      4. R(θ) sweep (QSD, noisy+ideal at each θ)
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
        preregistration={
            "interior_abs_gap_0_5": "preregistered (hardware handoff)",
            "arm_gap_0_05": "NOT preregistered — post-hoc exploratory only",
            "retention_margin": f"exploratory +{RETENTION_MARGIN} over R(XY4)",
            "do_not_stamp_until": "R(θ) sweep complete and peaked at θ*",
        },
    )

    # Arms: XY4 first, then QSD θ*, QSD wrong
    xy4 = _run_arm(sampler, line, "xy4", theta_star, shots, layers, relock_interval)
    qsd_star = _run_arm(sampler, line, "qsd", theta_star, shots, layers, relock_interval)
    qsd_wrong = _run_arm(sampler, line, "qsd", theta_wrong, shots, layers, relock_interval)

    out.arms = {
        "xy4_matched": xy4,
        "qsd_theta_star": qsd_star,
        "qsd_wrong_theta": qsd_wrong,
    }

    z_star = qsd_star["measured_zzz"]
    z_wrong = qsd_wrong["measured_zzz"]
    z_xy4 = xy4["measured_zzz"]

    out.arm_gaps = {
        "angle_specific_signed": float(z_star - z_wrong),
        "angle_specific_abs": abs(z_star - z_wrong),
        "qsd_vs_xy4_signed": float(z_star - z_xy4),
        "qsd_vs_xy4_abs": abs(z_star - z_xy4),
        "magnitude_qsd": abs(z_star),
        "magnitude_xy4": abs(z_xy4),
        "magnitude_qsd_vs_xy4_delta": abs(abs(z_star) - abs(z_xy4)),
        "post_hoc_arm_gap_passes_0_05": abs(z_star - z_xy4) >= POST_HOC_ARM_GAP_THRESHOLD,
        "post_hoc_note": "≥0.05 |θ*−XY4| was NOT preregistered; reported for transparency only",
    }

    if run_theta_sweep:
        out.retention_theta_sweep = run_retention_theta_sweep(
            sampler,
            line,
            sweep_shots,
            layers,
            relock_interval,
            theta_center_deg=theta_star_deg,
            span_deg=sweep_span_deg,
            n_points=sweep_n_points,
        )

    analysis = _analyze_retention_curve(
        out.retention_theta_sweep,
        theta_star_deg,
        xy4.get("retention_signed"),
    )
    analysis["ideal_at_star"] = qsd_star.get("ideal_zzz")
    analysis["ideal_xy4"] = xy4.get("ideal_zzz")
    analysis["ideal_wrong"] = qsd_wrong.get("ideal_zzz")
    out.retention_analysis = analysis

    verdict, endorsable, notes = _assign_verdict(out.arm_gaps, out.arms, analysis)
    out.verdict = verdict
    out.endorsable = endorsable
    out.notes = notes

    return out


def run_zzz_preservation_campaign(
    shots: int = 4000,
    sweep_shots: int = 512,
    **kwargs,
) -> dict:
    """Full ⟨ZZZ⟩ preservation campaign with retention scoring."""
    result = run_zzz_preservation_benchmark(
        shots=shots, sweep_shots=sweep_shots, line_name="interior", **kwargs,
    )
    return {
        "candidate": "zzz_preservation_interior",
        "protocol": (
            "XY4 matched-depth control; noiseless ideal per arm; "
            "retention R=noisy/ideal; R(θ) sweep for peak test"
        ),
        "result": result.to_dict(),
        "stamp_status": "HOLD — do not update README/meta/Zalcman until R(θ) adjudicated",
        "hardware_ready": False,
        "endorsable": result.endorsable,
    }
