"""
Correct Willow run — interior line + native willow_pink noise.

Fixes the original mistakes:
  - boundary row-0 line q(0,6–8)  →  interior row-6 q(6,5–7)
  - simplified thermal noise      →  Cirq willow_pink calibrated sampler
  - ZZZ depth on FakeFez          →  echo + optional depth sunscreen on grid
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.quantum.echo_protocol import STATES, THETA_STAR_WILLOW, THETA_STAR_WILLOW_DEG
from aurora_qsd.quantum.willow_lines import WillowLine, get_line

try:
    import cirq
except ImportError:
    cirq = None  # type: ignore[assignment]


def _require_cirq() -> None:
    if cirq is None:
        raise ImportError("cirq + cirq-google required")


def _prepare_ops(qubit, state: str) -> list:
    if state == "0":
        return []
    if state == "1":
        return [cirq.X(qubit)]
    if state == "+":
        return [cirq.H(qubit)]
    if state == "-":
        return [cirq.H(qubit), cirq.Z(qubit)]
    if state == "+i":
        return [cirq.H(qubit), cirq.S(qubit)]
    if state == "-i":
        return [cirq.H(qubit), cirq.S(qubit) ** -1]
    raise ValueError(state)


def _inverse_prepare_ops(qubit, state: str) -> list:
    if state == "0":
        return []
    if state == "1":
        return [cirq.X(qubit)]
    if state == "+":
        return [cirq.H(qubit)]
    if state == "-":
        return [cirq.Z(qubit), cirq.H(qubit)]
    if state == "+i":
        return [cirq.S(qubit) ** -1, cirq.H(qubit)]
    if state == "-i":
        return [cirq.S(qubit), cirq.H(qubit)]
    raise ValueError(state)


def _trilock_init_ops(qubits: list, theta: float) -> list:
    ops = []
    for i, q in enumerate(qubits):
        angle = 2.0 * theta if i % 2 == 0 else 2.0 * (np.pi / 2.0 - theta)
        ops.append(cirq.ry(angle)(q))
    return ops


def _phase_pulse_ops(qubits: list, theta: float) -> list:
    ops = _trilock_init_ops(qubits, theta)
    for i, q in enumerate(qubits):
        ops.append(cirq.rz(theta if i % 2 == 0 else np.pi / 2.0 - theta)(q))
    return ops


def _cz_cnot(control, target) -> list:
    """CNOT via H–CZ–H (Willow native)."""
    return [cirq.H(target), cirq.CZ(control, target), cirq.H(target)]


def _sunscreen_ops(qubits: list, theta: float) -> list:
    """Full TriDelta cell on a line using native CZ (Willow-compatible)."""
    q0, q1, q2 = qubits
    ops = _trilock_init_ops(qubits, theta)
    ops.extend(_cz_cnot(q0, q1))
    ops.extend([cirq.rz(theta)(q0), cirq.rz(np.pi / 2.0 - theta)(q1)])
    ops.extend(_cz_cnot(q1, q0))
    ops.extend(_cz_cnot(q1, q2))
    ops.append(cirq.rz(theta)(q2))
    ops.extend(_cz_cnot(q1, q2))
    return ops


def _invert_ops(ops: list) -> list:
    return [cirq.inverse(op) for op in reversed(ops)]


def build_grid_echo_circuit(
    line: WillowLine,
    state: str = "+",
    mode: str = "qsd",
    tau_ns: float = 1000.0,
    theta: float = 0.0,
    phi: float = 0.0,
    pulse: str = "phase",
) -> "cirq.Circuit":
    """Phase echo on explicit Willow GridQubits."""
    _require_cirq()
    qubits = list(line.qubits())
    target = qubits[line.target_index]
    ops: list = []
    ops.extend(_prepare_ops(target, state))

    if mode == "qsd":
        forward = _sunscreen_ops(qubits, theta) if pulse == "tridelta" else _phase_pulse_ops(qubits, theta)
    elif mode == "x":
        forward = [cirq.X(q) for q in qubits]
    elif mode == "random":
        forward = [cirq.rz(phi)(q) for q in qubits]
    elif mode == "none":
        forward = []
    else:
        raise ValueError(mode)

    ops.extend(forward)
    if tau_ns > 0:
        ops.append(cirq.wait(*qubits, nanos=int(tau_ns)))
    ops.extend(_invert_ops(forward))
    ops.extend(_inverse_prepare_ops(target, state))
    ops.append(cirq.measure(target, key="m"))
    return cirq.Circuit(ops)


def build_depth_sunscreen_circuit(
    line: WillowLine,
    theta: float = THETA_STAR_WILLOW,
    layers: int = 12,
    relock_interval: int = 4,
) -> "cirq.Circuit":
    """Depth-scaling QSD sunscreen on interior line (fez-validated protocol)."""
    _require_cirq()
    qubits = list(line.qubits())
    ops: list = []
    done = 0
    while done < layers:
        if done > 0:
            ops.extend(_sunscreen_ops(qubits, theta))
        block = min(relock_interval, layers - done)
        for _ in range(block):
            ops.extend(_sunscreen_ops(qubits, theta))
        done += block
    for q in qubits:
        ops.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    return cirq.Circuit(ops)


def _survival(counts: dict, key: str = "m") -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    # key might be 'm' or first measurement key
    if key not in counts and len(counts) == 2:
        k0 = [k for k in counts if k.endswith("0") or k == "0"]
        if k0:
            return counts.get(k0[0], 0) / total
    return counts.get("0", counts.get(key, 0)) / total


def _run_survival(sampler, circuit, shots: int) -> float:
    result = sampler.run(circuit, repetitions=shots)
    key = list(result.data.keys())[0]
    return float((result.data[key] == 0).mean())


@dataclass
class WillowRunResult:
    processor: str = "willow_pink"
    line: str = "interior"
    line_coords: list[str] = field(default_factory=list)
    shots: int = 4000
    tau_ns: float = 1000.0
    theta_deg: float = 0.0
    pulse: str = "phase"
    echo: dict = field(default_factory=dict)
    depth: dict = field(default_factory=dict)
    comparison_boundary: dict = field(default_factory=dict)
    verdict: str = "NULL"
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "line": self.line,
            "line_coords": self.line_coords,
            "shots": self.shots,
            "tau_ns": self.tau_ns,
            "theta_deg": self.theta_deg,
            "pulse": self.pulse,
            "echo": self.echo,
            "depth": self.depth,
            "comparison_boundary": self.comparison_boundary,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def _pooled_echo(sampler, line: WillowLine, shots: int, tau_ns: float, theta: float, pulse: str) -> dict:
    out = {}
    for mode_name, mode in [("echo_qsd", "qsd"), ("echo_x", "x"), ("no_echo", "none")]:
        succ = tot = 0
        for state in STATES:
            c = build_grid_echo_circuit(line, state, mode, tau_ns, theta, pulse=pulse)
            f = _run_survival(sampler, c, shots)
            succ += int(round(f * shots))
            tot += shots
        out[mode_name] = {"F": succ / tot, "n": tot}
    return out


def _zzz_score(counts: dict, qubits: list) -> float:
    """⟨Z⊗Z⊗Z⟩ from measurement counts."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    acc = 0.0
    for bitstring, n in counts.items():
        parity = bitstring.count("1")
        sign = 1.0 if parity % 2 == 0 else -1.0
        acc += sign * n
    return acc / total


def run_willow_correct(
    shots: int = 4000,
    tau_ns: float = 1000.0,
    theta_deg: float = 0.0,
    pulse: str = "phase",
    line_name: str = "interior",
    depth_layers: int = 12,
    relock_interval: int = 4,
    compare_boundary: bool = True,
) -> WillowRunResult:
    """
    Correct Willow campaign:
      1. Interior line q(6,5)–q(6,6)–q(6,7)
      2. Native willow_pink noisy sampler
      3. Phase echo at θ=0° (best sim Δ≈0) + depth sunscreen
    """
    _require_cirq()
    from cirq_google import engine

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()
    line = get_line(line_name)
    theta = float(np.radians(theta_deg))

    out = WillowRunResult(
        line=line_name,
        line_coords=line.labels(),
        shots=shots,
        tau_ns=tau_ns,
        theta_deg=theta_deg,
        pulse=pulse,
    )

    out.echo = _pooled_echo(sampler, line, shots, tau_ns, theta, pulse)

    # Depth sunscreen: θ* vs negative control
    for label, th in [("qsd_theta_star", THETA_STAR_WILLOW), ("negative_theta", THETA_STAR_WILLOW + np.radians(70))]:
        c = build_depth_sunscreen_circuit(line, theta=th, layers=depth_layers, relock_interval=relock_interval)
        result = sampler.run(c, repetitions=shots)
        keys = sorted(result.data.keys())
        zzz = []
        for i in range(shots):
            pop = sum(int(result.data[k][i]) for k in keys)
            zzz.append(1.0 if pop % 2 == 0 else -1.0)
        out.depth[label] = {"zzz": float(np.mean(zzz)), "n": shots}

    if compare_boundary:
        boundary = get_line("boundary")
        out.comparison_boundary = _pooled_echo(sampler, boundary, shots, tau_ns, theta, pulse)

    fq = out.echo["echo_qsd"]["F"]
    fx = out.echo["echo_x"]["F"]
    fn = out.echo["no_echo"]["F"]
    zsd = out.depth.get("qsd_theta_star", {}).get("zzz", 0.0)
    zneg = out.depth.get("negative_theta", {}).get("zzz", 0.0)

    if fq > fx and fq > fn and zsd > zneg + 0.05:
        out.verdict = "QSD_WIN"
        out.notes = "Interior line: echo QSD beats controls and depth ZZZ beats negative θ."
    elif fq > fx and fq > fn:
        out.verdict = "ECHO_WIN"
        out.notes = "Echo QSD beats X and no-echo on interior line."
    elif zsd > zneg + 0.05:
        out.verdict = "DEPTH_WIN"
        out.notes = "Depth sunscreen ZZZ angle-specific on interior line."
    else:
        out.verdict = "NULL"
        out.notes = "No clear QSD advantage on interior line with native willow_pink noise."

    return out
