"""
Willow algorithm utilization benchmarks — when QSD actually helps.

QSD preserves ZZZ-locked correlation structure. It is NOT a generic
post-processing filter on arbitrary algorithm states.

Supported utilization patterns:
  1. zzz_engine   — workload IS ZZZ stabilization (depth sunscreen)
  2. idle_guard   — after Ising prep, QSD during idle delays (between blocks)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_lines import WillowLine, get_line
from aurora_qsd.quantum.willow_run import (
    _depth_head_to_head,
    _require_cirq,
    _sunscreen_body_ops,
    _sunscreen_reset_ops,
    _zzz_from_result,
    build_depth_sunscreen_circuit,
)

OPTIMAL_THETA_DEG = 22.49
OPTIMAL_SUNSCREEN_LAYERS = 14
OPTIMAL_RELOCK_INTERVAL = 5


def _ising_trotter_step(qubits: list, J: float, h: float, dt: float) -> list:
    import cirq

    q0, q1, q2 = qubits
    ops: list = []
    for q in qubits:
        ops.append(cirq.rx(2.0 * h * dt)(q))
    for a, b in ((q0, q1), (q1, q2)):
        ops.append(cirq.CZ(a, b))
        ops.append(cirq.rz(2.0 * J * dt)(a))
        ops.append(cirq.rz(2.0 * J * dt)(b))
        ops.append(cirq.CZ(a, b))
    return ops


def _append_sunscreen_block(ops: list, qubits: list, theta: float, layers: int, relock: int) -> None:
    done = 0
    while done < layers:
        if done > 0:
            ops.extend(_sunscreen_reset_ops(qubits, theta))
        block = min(relock, layers - done)
        for j in range(block):
            ops.extend(_sunscreen_body_ops(qubits, theta, with_init=(done == 0 and j == 0)))
        done += block


def build_idle_guard_circuit(
    line: WillowLine,
    trotter_steps: int = 8,
    idle_ns: float = 2000.0,
    guard_mode: str = "bare",
    theta_deg: float = OPTIMAL_THETA_DEG,
    guard_layers: int = 3,
    J: float = 1.2,
    h: float = 0.1,
    dt: float = 0.25,
) -> "cirq.Circuit":
    """
    Real utilization: run algorithm block → idle (noise) → measure.

    guard_mode:
      bare  — idle only
      qsd   — 3L sunscreen @ θ* then idle
      wrong — 3L sunscreen @ wrong θ then idle
    """
    _require_cirq()
    import cirq

    qubits = list(line.qubits())
    theta = float(np.radians(theta_deg))
    ops: list = []
    for _ in range(trotter_steps):
        ops.extend(_ising_trotter_step(qubits, J, h, dt))

    if guard_mode == "qsd":
        _append_sunscreen_block(ops, qubits, theta, guard_layers, relock=2)
    elif guard_mode == "wrong":
        _append_sunscreen_block(ops, qubits, negative_control_angle(theta), guard_layers, relock=2)

    if idle_ns > 0:
        ops.append(cirq.wait(*qubits, nanos=int(idle_ns)))

    for q in qubits:
        ops.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    return cirq.Circuit(ops)


def _ideal_zzz_after_prep(line, steps, J, h, dt) -> float:
    import cirq

    qubits = list(line.qubits())
    ops = []
    for _ in range(steps):
        ops.extend(_ising_trotter_step(qubits, J, h, dt))
    state = cirq.Simulator().simulate(cirq.Circuit(ops)).final_state_vector
    zzz = sum(
        (1.0 if format(i, "03b").count("1") % 2 == 0 else -1.0) * abs(a) ** 2
        for i, a in enumerate(state)
    )
    return float(np.real(zzz))


@dataclass
class AlgorithmBenchmarkResult:
    pattern: str = ""
    line: list[str] = field(default_factory=list)
    shots: int = 0
    ideal_zzz: float = 0.0
    bare: dict = field(default_factory=dict)
    qsd: dict = field(default_factory=dict)
    wrong: dict = field(default_factory=dict)
    verdict: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "pattern": self.pattern,
            "line": self.line,
            "shots": self.shots,
            "ideal_zzz": self.ideal_zzz,
            "bare": self.bare,
            "qsd": self.qsd,
            "wrong": self.wrong,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def run_zzz_engine_benchmark(
    shots: int = 500,
    line_name: str = "interior",
    theta_deg: float = OPTIMAL_THETA_DEG,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock: int = OPTIMAL_RELOCK_INTERVAL,
) -> AlgorithmBenchmarkResult:
    """Pattern 1: ZZZ stabilization IS the algorithm (validated use case)."""
    _require_cirq()
    from cirq_google import engine

    line = get_line(line_name)
    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()
    theta = float(np.radians(theta_deg))
    theta_neg = negative_control_angle(theta)

    out = AlgorithmBenchmarkResult(pattern="zzz_engine", line=line.labels(), shots=shots, ideal_zzz=1.0)

    row = _depth_head_to_head(sampler, line, shots, theta, theta_neg, layers, relock)
    out.qsd = {"zzz": row["qsd_theta_star"]["zzz"], "abs_gap": row["abs_gap"], "n": shots}
    out.wrong = {"zzz": row["negative_theta"]["zzz"], "n": shots}
    out.bare = {"zzz": row["negative_theta"]["zzz"], "note": "wrong-angle proxy for unstructured noise", "n": shots}

    gap = row["abs_gap"]
    if gap >= 0.05:
        out.verdict = "QSD_WINS"
        out.notes = (
            f"ZZZ engine @ θ*={theta_deg}°: |Δ|={gap:.3f} — "
            "use QSD depth when the target IS 3-qubit ZZZ correlation."
        )
    else:
        out.verdict = "NULL"
        out.notes = "ZZZ engine: no angle-specific gain."
    return out


def run_idle_guard_benchmark(
    shots: int = 500,
    line_name: str = "interior",
    trotter_steps: int = 8,
    idle_ns: float = 2000.0,
    theta_deg: float = OPTIMAL_THETA_DEG,
) -> AlgorithmBenchmarkResult:
    """Pattern 2: QSD guard during idle between algorithm blocks."""
    _require_cirq()
    from cirq_google import engine

    line = get_line(line_name)
    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()
    ideal = _ideal_zzz_after_prep(line, trotter_steps, 1.2, 0.1, 0.25)

    out = AlgorithmBenchmarkResult(
        pattern="idle_guard",
        line=line.labels(),
        shots=shots,
        ideal_zzz=ideal,
    )

    for label, mode in [("bare", "bare"), ("qsd", "qsd"), ("wrong", "wrong")]:
        c = build_idle_guard_circuit(
            line, trotter_steps, idle_ns, mode, theta_deg=theta_deg
        )
        r = sampler.run(c, repetitions=shots)
        zzz = _zzz_from_result(r, shots)
        out.__dict__[label] = {"zzz": zzz, "error_vs_ideal": abs(zzz - ideal), "n": shots}

    eb, eq, ew = out.bare["error_vs_ideal"], out.qsd["error_vs_ideal"], out.wrong["error_vs_ideal"]
    if eq < eb and eq < ew:
        out.verdict = "QSD_WINS"
        out.notes = f"Idle guard: QSD preserves Ising ZZZ best (err {eq:.3f} vs bare {eb:.3f})."
    elif out.qsd["zzz"] > out.bare["zzz"] > out.wrong["zzz"] or out.qsd["zzz"] < out.bare["zzz"] < out.wrong["zzz"]:
        # monotonic angle specificity during idle
        out.verdict = "ANGLE_SPECIFIC"
        out.notes = f"Idle guard shows angle ordering: qsd={out.qsd['zzz']:.3f} bare={out.bare['zzz']:.3f} wrong={out.wrong['zzz']:.3f}"
    else:
        out.verdict = "NULL"
        out.notes = "Idle guard: no clear QSD advantage on Ising idle hold."
    return out


def run_algorithm_benchmark(shots: int = 500, pattern: str = "all", **kwargs) -> dict:
    """Run utilization benchmark(s)."""
    results = {}
    if pattern in ("all", "zzz_engine"):
        results["zzz_engine"] = run_zzz_engine_benchmark(shots=shots, **kwargs).to_dict()
    if pattern in ("all", "idle_guard"):
        results["idle_guard"] = run_idle_guard_benchmark(shots=shots, **kwargs).to_dict()
    return results
