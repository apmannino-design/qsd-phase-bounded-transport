"""
IBM hardware ⟨ZZZ⟩ retention audit — July 7, 2026 protocol on Qiskit.

Ports the Willow retention benchmark (zzz_preservation.py) to IBM backends:
  - Exact 3Q QSD body from fez_cells (_append_3q_qsd_layer + sunscreen re-lock)
  - Repaired matched-depth XY4 control (12 single-qubit pulses / body layer)
  - Ideal ⟨ZZZ⟩ via Aer statevector + density-matrix cross-check
  - Retention R = noisy / ideal with preregistered verdict ladder
  - θ-sweep for R(θ) curve
  - Diagnostic mode: multiple champion 3Q lines from device coupling map

Simulation never endorses (endorsable=False always until hardware confirmation).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_DEG
from aurora_qsd.quantum.fez_cells import (
    _append_3q_qsd_layer,
    append_sunscreen_reset,
    extract_zzz_triplets,
    zzz_correlator,
)
from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_SUNSCREEN_LAYERS
from aurora_qsd.quantum.zzz_preservation import (
    MIN_TARGET_SIGNAL,
    RETENTION_ADVANTAGE_MARGIN,
    VALID_R_MAX,
    _analyze_retention_curve,
    _audit_theta_points,
    assign_retention_verdict,
    compute_retention,
)

try:
    from qiskit import ClassicalRegister, QuantumCircuit, transpile
    from qiskit.quantum_info import DensityMatrix, Statevector, SparsePauliOp
    from qiskit_aer import AerSimulator
except ImportError:
    QuantumCircuit = None  # type: ignore[misc, assignment]

try:
    from qiskit_ibm_runtime import Batch, QiskitRuntimeService, SamplerV2
except ImportError:
    QiskitRuntimeService = None  # type: ignore[misc, assignment]


def _require_qiskit() -> None:
    if QuantumCircuit is None:
        raise ImportError("qiskit and qiskit-aer required")


LOGICAL_QUBITS: tuple[int, int, int] = (0, 1, 2)


def _xy4_single_qubit(qc: "QuantumCircuit", q: int) -> None:
    qc.x(q)
    qc.y(q)
    qc.x(q)
    qc.y(q)


def _xy4_body_layer(qc: "QuantumCircuit", qubits: tuple[int, int, int]) -> None:
    """One body layer: three complete XY4 blocks (12 single-qubit pulses)."""
    for q in qubits:
        _xy4_single_qubit(qc, q)


def _normalize_physical_qubits(qubits: tuple[int, int, int]) -> tuple[int, int, int]:
    """Physical hardware indices for transpile layout (may be sparse, e.g. 20,21,36)."""
    if len(qubits) != 3:
        raise ValueError("exactly 3 qubits required")
    return tuple(int(q) for q in qubits)


def build_qsd_sunscreen_circuit(
    qubits: tuple[int, int, int] = LOGICAL_QUBITS,
    theta_deg: float = 22.5,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    measure: bool = True,
) -> "QuantumCircuit":
    """QSD depth-sunscreen on logical qubits 0,1,2 (fez_cells exact). Map to hardware at transpile."""
    _require_qiskit()
    logical = LOGICAL_QUBITS
    theta = float(np.radians(theta_deg))
    cr = ClassicalRegister(3, "c")
    qc = QuantumCircuit(3)
    qc.add_register(cr)

    layers_done = 0
    while layers_done < layers:
        if layers_done > 0:
            append_sunscreen_reset(qc, logical, theta)
        block = min(relock_interval, layers - layers_done)
        for j in range(block):
            _append_3q_qsd_layer(
                qc,
                logical,
                theta,
                with_init=(layers_done == 0 and j == 0),
            )
        layers_done += block

    if measure:
        qc.measure(list(logical), cr)
    return qc


def build_xy4_matched_circuit(
    qubits: tuple[int, int, int] = LOGICAL_QUBITS,
    theta_deg: float = 22.5,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    measure: bool = True,
) -> "QuantumCircuit":
    """Matched-schedule XY4 DD control on logical qubits 0,1,2."""
    _require_qiskit()
    from aurora_qsd.quantum.fez_cells import _trilock_init

    logical = LOGICAL_QUBITS
    theta = float(np.radians(theta_deg))
    cr = ClassicalRegister(3, "c")
    qc = QuantumCircuit(3)
    qc.add_register(cr)

    layers_done = 0
    while layers_done < layers:
        if layers_done > 0:
            _trilock_init(qc, logical, theta)
            _xy4_body_layer(qc, logical)
        block = min(relock_interval, layers - layers_done)
        for j in range(block):
            if layers_done == 0 and j == 0:
                _trilock_init(qc, logical, theta)
            _xy4_body_layer(qc, logical)
        layers_done += block

    if measure:
        qc.measure(list(logical), cr)
    return qc


def verify_xy4_layer_qiskit(qubits: tuple[int, int, int] = LOGICAL_QUBITS) -> dict:
    """Verify repaired XY4 body is not degenerate I⊗I⊗Y (always 3-qubit logical space)."""
    _require_qiskit()
    from qiskit.quantum_info import Operator

    logical = LOGICAL_QUBITS
    qc = QuantumCircuit(3)
    _xy4_body_layer(qc, logical)
    u = Operator(qc).data
    y3 = np.kron(np.eye(2), np.kron(np.eye(2), np.array([[0, -1j], [1j, 0]], dtype=complex)))
    overlap_y = float(np.abs(np.trace(u.conj().T @ y3)) / u.size)
    return {
        "pulses_per_layer": 12,
        "overlap_with_IIIY": overlap_y,
        "degenerate_IIIY": overlap_y > 0.99,
        "passes": overlap_y < 0.99,
        "checked_on_logical_qubits": list(logical),
        "requested_physical_qubits": list(qubits),
    }


def _zzz_pauli_string(n_qubits: int, qubits: tuple[int, ...]) -> str:
    label = ["I"] * n_qubits
    for q in qubits:
        label[q] = "Z"
    return "".join(reversed(label))


def ideal_zzz_qiskit(circuit: "QuantumCircuit", qubits: tuple[int, int, int] | None = None) -> dict[str, float]:
    """Noiseless ⟨ZZZ⟩ via statevector parity + density-matrix ZZZ operator."""
    _require_qiskit()
    logical = LOGICAL_QUBITS
    qc = circuit.remove_final_measurements(inplace=False)
    n = qc.num_qubits
    zzz_op = SparsePauliOp.from_list([(_zzz_pauli_string(n, logical), 1.0)])

    sv = Statevector.from_instruction(qc)
    ideal_sv = float(np.real(sv.expectation_value(zzz_op)))

    dm = DensityMatrix.from_instruction(qc)
    ideal_dm = float(np.real(dm.expectation_value(zzz_op)))

    return {
        "ideal_zzz_sv": ideal_sv,
        "ideal_zzz_dm": ideal_dm,
        "ideal_zzz": ideal_sv,
        "ideal_paths_agree": abs(ideal_sv - ideal_dm) < 1e-5,
    }


def gate_budget_metadata(
    theta_deg: float,
    layers: int,
    relock: int,
) -> dict:
    _require_qiskit()
    logical = LOGICAL_QUBITS

    def _count(qc: "QuantumCircuit") -> dict[str, int]:
        ops = qc.count_ops()
        twoq = sum(v for k, v in ops.items() if k in ("cx", "cz", "ecr"))
        oneq = sum(v for k, v in ops.items() if k not in ("cx", "cz", "ecr", "measure", "barrier"))
        return {"one_qubit": oneq, "two_qubit": twoq}

    theta = float(np.radians(theta_deg))
    qsd = build_qsd_sunscreen_circuit(logical, theta_deg, layers, relock, measure=False)
    xy4 = build_xy4_matched_circuit(logical, theta_deg, layers, relock, measure=False)

    qsd_body = QuantumCircuit(3)
    _append_3q_qsd_layer(qsd_body, logical, theta, with_init=False)
    xy4_body = QuantumCircuit(3)
    _xy4_body_layer(xy4_body, logical)

    return {
        "layers": layers,
        "relock_interval": relock,
        "qsd_body_per_layer": _count(qsd_body),
        "xy4_body_per_layer": _count(xy4_body),
        "qsd_total": _count(qsd),
        "xy4_total": _count(xy4),
        "xy4_layer_check": verify_xy4_layer_qiskit(logical),
        "note": "QSD: 4 two-qubit ops/body layer; XY4: 12 single-qubit pulses/body layer (repaired).",
    }


def _transpile_for_run(
    circuit: "QuantumCircuit",
    backend,
    mode: str,
    physical_qubits: tuple[int, int, int],
) -> "QuantumCircuit":
    """Transpile logical 3Q circuit; map to sparse physical indices on hardware."""
    if mode == "aer" and getattr(backend, "coupling_map", None) is None:
        return circuit
    layout = list(physical_qubits)
    return transpile(circuit, backend, initial_layout=layout, optimization_level=1)


def _resolve_backend(backend_name: str):
    name = backend_name.lower()
    if name in ("aer_sim", "aer", "aer_ideal"):
        return AerSimulator(), "aer"
    if name in ("aer_fez", "aer_fez_noisy"):
        try:
            if QiskitRuntimeService is None:
                raise ImportError("no runtime")
            svc = QiskitRuntimeService()
            return AerSimulator.from_backend(svc.backend("ibm_fez")), "aer"
        except Exception:
            return AerSimulator(), "aer"
    if QiskitRuntimeService is None:
        raise ImportError("qiskit-ibm-runtime required for IBM hardware")
    svc = QiskitRuntimeService()
    return svc.backend(backend_name), "hw"


def _counts_from_sampler_result(pub_result) -> dict[str, int]:
    if hasattr(pub_result.data, "c"):
        return pub_result.data.c.get_counts()
    if hasattr(pub_result.data, "meas"):
        return pub_result.data.meas.get_counts()
    raise AttributeError("Cannot extract counts from sampler pub result")


def run_circuit_zzz(
    circuit: "QuantumCircuit",
    backend_name: str,
    shots: int,
    physical_qubits: tuple[int, int, int] = LOGICAL_QUBITS,
    backend=None,
    mode: str | None = None,
) -> dict[str, Any]:
    """Run circuit on Aer or IBM hardware; return counts + metadata."""
    _require_qiskit()
    physical_qubits = _normalize_physical_qubits(physical_qubits)
    if backend is None or mode is None:
        backend, mode = _resolve_backend(backend_name)

    if mode == "aer":
        from qiskit_aer.primitives import SamplerV2 as AerSamplerV2

        sampler = AerSamplerV2()
        isa = _transpile_for_run(circuit, backend, mode, physical_qubits)
        job = sampler.run([isa], shots=shots)
        pub = job.result()[0]
        counts = _counts_from_sampler_result(pub)
        return {"counts": counts, "shots": shots, "backend": backend_name, "job_id": None}

    sampler = SamplerV2(mode=Batch(backend=backend))
    isa = _transpile_for_run(circuit, backend, mode, physical_qubits)
    job = sampler.run([isa], shots=shots)
    pub = job.result()[0]
    jid = job.job_id() if callable(getattr(job, "job_id", None)) else getattr(job, "job_id", None)
    return {
        "counts": _counts_from_sampler_result(pub),
        "shots": shots,
        "backend": backend_name,
        "job_id": jid,
    }


def _run_arm(
    physical_qubits: tuple[int, int, int],
    arm: str,
    theta_deg: float,
    layers: int,
    relock: int,
    backend_name: str,
    shots: int,
    ideals_only: bool,
    backend=None,
    mode: str | None = None,
) -> dict:
    logical = LOGICAL_QUBITS
    if arm == "xy4":
        c_noisy = build_xy4_matched_circuit(logical, theta_deg, layers, relock, measure=True)
        c_ideal = build_xy4_matched_circuit(logical, theta_deg, layers, relock, measure=False)
    elif arm == "qsd":
        c_noisy = build_qsd_sunscreen_circuit(logical, theta_deg, layers, relock, measure=True)
        c_ideal = build_qsd_sunscreen_circuit(logical, theta_deg, layers, relock, measure=False)
    else:
        raise ValueError(arm)

    ideal = ideal_zzz_qiskit(c_ideal)
    measured = None
    job_id = None
    if not ideals_only:
        hw = run_circuit_zzz(
            c_noisy, backend_name, shots, physical_qubits=physical_qubits, backend=backend, mode=mode
        )
        measured = zzz_correlator(hw["counts"], n_qubits=3)
        job_id = hw.get("job_id")

    ret = compute_retention(measured, ideal["ideal_zzz"])
    ret.update({
        "arm": arm,
        "theta_deg": theta_deg,
        "shots": shots if not ideals_only else 0,
        **ideal,
        "measured_zzz": measured,
        "job_id": job_id,
    })
    return ret


@dataclass
class IBMRetentionResult:
    task: str = "qsd_ibm_retention_audit"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    backend: str = ""
    qubits: list[int] = field(default_factory=list)
    theta_star_deg: float = THETA_STAR_DEG
    layers: int = OPTIMAL_SUNSCREEN_LAYERS
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL
    shots: int = 0
    gate_budget: dict = field(default_factory=dict)
    preregistration: dict = field(default_factory=dict)
    arms: dict = field(default_factory=dict)
    arm_gaps: dict = field(default_factory=dict)
    retention_theta_sweep: list = field(default_factory=list)
    retention_analysis: dict = field(default_factory=dict)
    job_ids: dict = field(default_factory=dict)
    verdict: str = "PENDING"
    endorsable: bool = False
    notes: str = ""
    elapsed_s: float = 0.0
    diagnostic_lines: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def run_ibm_retention_benchmark(
    backend_name: str = "aer_sim",
    qubits: tuple[int, int, int] = (0, 1, 2),
    theta_star_deg: float = THETA_STAR_DEG,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock_interval: int = OPTIMAL_RELOCK_INTERVAL,
    shots: int = 4096,
    sweep_shots: int = 1024,
    run_sweep: bool = True,
    ideals_only: bool = False,
    negative_offset_deg: float = 70.0,
) -> IBMRetentionResult:
    t0 = time.time()
    theta_wrong_deg = float(theta_star_deg + negative_offset_deg)
    physical_qubits = _normalize_physical_qubits(qubits)

    backend, mode = _resolve_backend(backend_name)

    out = IBMRetentionResult(
        backend=backend_name,
        qubits=list(physical_qubits),
        theta_star_deg=theta_star_deg,
        layers=layers,
        relock_interval=relock_interval,
        shots=shots,
        gate_budget=gate_budget_metadata(theta_star_deg, layers, relock_interval),
        preregistration={
            "min_target_signal": MIN_TARGET_SIGNAL,
            "retention_advantage_margin": RETENTION_ADVANTAGE_MARGIN,
            "valid_r_range": f"(0, {VALID_R_MAX}]",
            "simulation_endorses": False,
        },
    )

    xy4 = _run_arm(physical_qubits, "xy4", theta_star_deg, layers, relock_interval, backend_name, shots, ideals_only, backend, mode)
    qsd_star = _run_arm(physical_qubits, "qsd", theta_star_deg, layers, relock_interval, backend_name, shots, ideals_only, backend, mode)
    qsd_wrong = _run_arm(physical_qubits, "qsd", theta_wrong_deg, layers, relock_interval, backend_name, shots, ideals_only, backend, mode)

    out.arms = {"xy4_matched": xy4, "qsd_theta_star": qsd_star, "qsd_wrong_theta": qsd_wrong}
    out.job_ids = {
        "qsd_theta_star": qsd_star.get("job_id"),
        "qsd_wrong_theta": qsd_wrong.get("job_id"),
        "xy4_matched": xy4.get("job_id"),
    }

    if not ideals_only:
        z_star = qsd_star["measured_zzz"]
        z_wrong = qsd_wrong["measured_zzz"]
        z_xy4 = xy4["measured_zzz"]
        out.arm_gaps = {
            "angle_specific_signed": float(z_star - z_wrong),
            "angle_specific_abs": abs(z_star - z_wrong),
            "qsd_vs_xy4_signed": float(z_star - z_xy4),
            "qsd_vs_xy4_abs": abs(z_star - z_xy4),
            "ideal_angle_gap": abs(qsd_star["ideal_zzz"] - qsd_wrong["ideal_zzz"]),
            "noisy_angle_gap": abs(z_star - z_wrong),
        }

    if run_sweep:
        sweep: list[dict] = []
        for td in _audit_theta_points(theta_star_deg):
            row = _run_arm(
                physical_qubits, "qsd", td, layers, relock_interval,
                backend_name, sweep_shots, ideals_only, backend, mode,
            )
            sweep.append(row)
        out.retention_theta_sweep = sweep

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
    out.elapsed_s = time.time() - t0
    return out


def _rank_champion_cells(backend, n: int = 3) -> list[tuple[int, int, int]]:
    cm = backend.coupling_map.get_edges() if hasattr(backend.coupling_map, "get_edges") else backend.coupling_map
    cells = extract_zzz_triplets(list(cm), max_cells=64)
    tgt = backend.target
    twoq = next((g for g in ("cz", "ecr", "cx") if g in tgt.operation_names), "cx")

    def e2(a: int, b: int) -> float:
        try:
            p = tgt[twoq].get((a, b)) or tgt[twoq].get((b, a))
            return p.error if p and p.error is not None else 0.02
        except Exception:
            return 0.02

    def eread(q: int) -> float:
        try:
            p = tgt["measure"][(q,)]
            return p.error if p and p.error is not None else 0.02
        except Exception:
            return 0.02

    scored = []
    for cell in cells:
        a, b, c = cell.qubits
        score = e2(a, b) + e2(b, c) + eread(a) + eread(b) + eread(c)
        scored.append((score, cell.qubits))
    scored.sort()
    return [t for _, t in scored[:n]]


def run_diagnostic_retention(
    backend_name: str,
    n_lines: int = 3,
    shots: int = 2048,
    sweep_shots: int = 512,
    run_sweep: bool = False,
    **kwargs,
) -> dict:
    """Multi-line chip-health probe on champion 3Q cells."""
    backend, mode = _resolve_backend(backend_name)
    if mode != "hw":
        lines = [(0, 1, 2), (3, 4, 5), (6, 7, 8)][:n_lines]
    else:
        lines = _rank_champion_cells(backend, n_lines)

    results = []
    for qubits in lines:
        print(f"[diagnostic] qubits={qubits}", flush=True)
        res = run_ibm_retention_benchmark(
            backend_name=backend_name,
            qubits=qubits,
            shots=shots,
            sweep_shots=sweep_shots,
            run_sweep=run_sweep,
            **kwargs,
        )
        results.append(res.to_dict())

    verdicts = [r["verdict"] for r in results]
    summary_verdict = "PROTECTION_CANDIDATE" if all(v == "PROTECTION_CANDIDATE" for v in verdicts) else verdicts[0]

    return {
        "task": "qsd_ibm_retention_diagnostic",
        "backend": backend_name,
        "n_lines": len(lines),
        "lines": [list(q) for q in lines],
        "results": results,
        "summary_verdict": summary_verdict,
        "endorsable": False,
        "stamp_status": "HOLD — hardware confirmation required",
    }


def write_results_markdown(result: IBMRetentionResult | dict, path: Path) -> None:
    """Immutable RESULTS-style Markdown log."""
    d = result if isinstance(result, dict) else result.to_dict()
    arms = d.get("arms", {})
    lines = [
        f"# IBM QSD Retention Audit — {d.get('timestamp', '')}",
        "",
        f"**Backend:** {d.get('backend')}  ",
        f"**Qubits:** {d.get('qubits')}  ",
        f"**θ*:** {d.get('theta_star_deg')}°  ",
        f"**Layers:** {d.get('layers')}  re-lock /{d.get('relock_interval')}  ",
        f"**Shots:** {d.get('shots')}  ",
        f"**Verdict:** {d.get('verdict')}  ",
        f"**Endorsable:** {d.get('endorsable')}  ",
        "",
        "## Arms",
        "",
        "| Arm | ideal ⟨ZZZ⟩ | noisy ⟨ZZZ⟩ | R |",
        "|-----|-------------|-------------|---|",
    ]
    for name, arm in arms.items():
        lines.append(
            f"| {name} | {arm.get('ideal_zzz', 'n/a'):+.4f} | "
            f"{arm.get('measured_zzz', 'n/a')} | {arm.get('retention_signed', 'n/a')} |"
        )
    lines.extend(["", f"**Notes:** {d.get('notes', '')}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def save_retention_result(result: IBMRetentionResult | dict, json_path: Path, md_path: Path | None = None) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = result if isinstance(result, dict) else result.to_dict()
    json_path.write_text(json.dumps(payload, indent=2) + "\n")
    if md_path:
        write_results_markdown(payload, md_path)
