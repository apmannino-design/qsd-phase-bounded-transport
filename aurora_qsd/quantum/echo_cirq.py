"""Willow line echo protocol — Cirq / qsim implementation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.quantum.echo_protocol import (
    STATES,
    THETA_STAR_WILLOW,
    THETA_STAR_WILLOW_DEG,
)
from aurora_qsd.quantum.willow_noise import cirq_idle_noise_ops

try:
    import cirq
except ImportError:
    cirq = None  # type: ignore[assignment]


def _require_cirq() -> None:
    if cirq is None:
        raise ImportError("cirq required. Install with: pip install cirq")


def _line_qubits() -> list:
    _require_cirq()
    return [cirq.LineQubit(i) for i in range(3)]


def _prepare_ops(qubit, state: str) -> list:
    _require_cirq()
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
    _require_cirq()
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


def _qsd_phase_ops(qubits: list, theta: float) -> list:
    ops = _trilock_init_ops(qubits, theta)
    for i, q in enumerate(qubits):
        ops.append(cirq.rz(theta if i % 2 == 0 else np.pi / 2.0 - theta)(q))
    return ops


def _qsd_sunscreen_ops(qubits: list, theta: float) -> list:
    q0, q1, q2 = qubits
    ops = _trilock_init_ops(qubits, theta)
    ops.extend(
        [
            cirq.CNOT(q0, q1),
            cirq.rz(theta)(q0),
            cirq.rz(np.pi / 2.0 - theta)(q1),
            cirq.CNOT(q1, q0),
            cirq.CNOT(q1, q2),
            cirq.rz(theta)(q2),
            cirq.CNOT(q1, q2),
        ]
    )
    return ops


def _qsd_pulse_ops(qubits: list, theta: float, variant: str = "phase") -> list:
    if variant == "phase":
        return _qsd_phase_ops(qubits, theta)
    if variant == "sunscreen":
        return _qsd_sunscreen_ops(qubits, theta)
    if variant == "hybrid":
        return [cirq.X(q) for q in qubits] + _qsd_phase_ops(qubits, theta)
    if variant == "relock":
        return _qsd_phase_ops(qubits, theta)
    raise ValueError(f"unknown pulse variant: {variant}")


def _invert_ops(ops: list) -> list:
    return [cirq.inverse(op) for op in reversed(ops)]


def _echo_forward_ops(qubits: list, mode: str, theta: float, phi: float, pulse_variant: str) -> list:
    if mode == "qsd":
        return _qsd_pulse_ops(qubits, theta, pulse_variant)
    if mode == "x":
        return [cirq.X(q) for q in qubits]
    if mode == "random":
        return [cirq.rz(phi)(q) for q in qubits]
    if mode == "none":
        return []
    raise ValueError(mode)


def _idle_noise_ops(qubits: list, tau_ns: float, t2_ns: float) -> list:
    """Thermal relaxation during idle τ (same channel as Qiskit Aer)."""
    if tau_ns <= 0:
        return []
    return cirq_idle_noise_ops(qubits, tau_ns, t2_ns)


def build_echo_circuit(
    state: str,
    mode: str,
    tau_ns: float = 1000.0,
    theta: float = THETA_STAR_WILLOW,
    phi: float = 0.0,
    pulse_variant: str = "phase",
    t2_ns: float = 2000.0,
) -> "cirq.Circuit":
    """Build Cirq echo circuit with idle dephasing during τ."""
    _require_cirq()
    qubits = _line_qubits()
    target = qubits[1]
    ops: list = []
    ops.extend(_prepare_ops(target, state))

    forward = _echo_forward_ops(qubits, mode, theta, phi, pulse_variant)
    ops.extend(forward)

    if tau_ns > 0:
        if pulse_variant == "relock" and mode == "qsd":
            half = int(tau_ns / 2)
            ops.append(cirq.wait(*qubits, nanos=half))
            ops.extend(_idle_noise_ops(qubits, half, t2_ns))
            ops.extend(_qsd_phase_ops(qubits, theta))
            rem = int(tau_ns) - half
            ops.append(cirq.wait(*qubits, nanos=rem))
            ops.extend(_idle_noise_ops(qubits, rem, t2_ns))
        else:
            ops.append(cirq.wait(*qubits, nanos=int(tau_ns)))
            ops.extend(_idle_noise_ops(qubits, tau_ns, t2_ns))

    ops.extend(_invert_ops(forward))
    ops.extend(_inverse_prepare_ops(target, state))
    ops.append(cirq.measure(target, key="m"))
    return cirq.Circuit(ops)


def _count_survival(result: "cirq.Result", shots: int) -> int:
    return int(np.sum(result.data["m"] == 0))


def _pooled_stats(mode_data: dict) -> dict:
    succ = sum(v["succ"] for v in mode_data.values())
    tot = sum(v["tot"] for v in mode_data.values())
    f = succ / tot if tot else 0.0
    se = math.sqrt(f * (1 - f) / tot) if tot else 0.0
    return {"F": f, "se": se, "n": tot}


@dataclass
class WillowEchoCirqResult:
    processor: str = "willow_pink_cirq"
    cirq_version: str = ""
    simulator: str = "DensityMatrixSimulator"
    theta_star_rad: float = THETA_STAR_WILLOW
    theta_star_deg: float = THETA_STAR_WILLOW_DEG
    line: list[str] = field(default_factory=lambda: ["q(0,6)", "q(0,7)", "q(0,8)"])
    shots_per_circuit: int = 4000
    tau_ns: float = 1000.0
    t2_ns: float = 2000.0
    random_phis_rad: list[float] = field(default_factory=list)
    per_state: dict = field(default_factory=dict)
    pooled: dict = field(default_factory=dict)
    z_qsd_minus_x: float = 0.0
    z_qsd_minus_random: float = 0.0
    verdict: str = "NULL"

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "cirq_version": self.cirq_version,
            "simulator": self.simulator,
            "theta_star_rad": self.theta_star_rad,
            "theta_star_deg": self.theta_star_deg,
            "line": self.line,
            "shots_per_circuit": self.shots_per_circuit,
            "tau_ns": self.tau_ns,
            "t2_ns": self.t2_ns,
            "random_phis_rad": self.random_phis_rad,
            "per_state": self.per_state,
            "pooled": self.pooled,
            "z_qsd_minus_x": self.z_qsd_minus_x,
            "z_qsd_minus_random": self.z_qsd_minus_random,
            "verdict": self.verdict,
        }


def run_willow_echo_benchmark(
    shots: int = 4000,
    tau_ns: float = 1000.0,
    n_random: int = 10,
    seed: int = 42,
    t2_ns: float = 2000.0,
    theta: float = THETA_STAR_WILLOW,
    pulse_variant: str = "phase",
    use_density_matrix: bool = True,
) -> WillowEchoCirqResult:
    """Run Willow echo benchmark on Cirq density-matrix simulator."""
    _require_cirq()
    rng = np.random.default_rng(seed)
    phis = [float(x) for x in rng.uniform(0, 2 * np.pi, n_random)]

    sim: cirq.Simulator = (
        cirq.DensityMatrixSimulator() if use_density_matrix else cirq.Simulator()
    )
    out = WillowEchoCirqResult(
        shots_per_circuit=shots,
        tau_ns=tau_ns,
        t2_ns=t2_ns,
        random_phis_rad=phis,
        cirq_version=cirq.__version__,
        simulator=type(sim).__name__,
    )

    for mode_name, mode in [("echo_qsd", "qsd"), ("echo_x", "x"), ("no_echo", "none")]:
        out.per_state[mode_name] = {}
        for state in STATES:
            circuit = build_echo_circuit(
                state=state,
                mode=mode,
                tau_ns=tau_ns,
                theta=theta,
                pulse_variant=pulse_variant if mode == "qsd" else "phase",
                t2_ns=t2_ns,
            )
            result = sim.run(circuit, repetitions=shots)
            out.per_state[mode_name][state] = {
                "succ": _count_survival(result, shots),
                "tot": shots,
            }

    out.per_state["echo_random"] = {s: {"succ": 0, "tot": 0} for s in STATES}
    for phi in phis:
        for state in STATES:
            circuit = build_echo_circuit(
                state=state,
                mode="random",
                tau_ns=tau_ns,
                theta=theta,
                phi=phi,
                t2_ns=t2_ns,
            )
            result = sim.run(circuit, repetitions=shots)
            out.per_state["echo_random"][state]["succ"] += _count_survival(result, shots)
            out.per_state["echo_random"][state]["tot"] += shots

    for mode_name in ("echo_qsd", "echo_x", "echo_random", "no_echo"):
        out.pooled[mode_name] = _pooled_stats(out.per_state[mode_name])

    fq, fx, fr = out.pooled["echo_qsd"]["F"], out.pooled["echo_x"]["F"], out.pooled["echo_random"]["F"]
    sq, sx, sr = out.pooled["echo_qsd"]["se"], out.pooled["echo_x"]["se"], out.pooled["echo_random"]["se"]
    out.z_qsd_minus_x = (fq - fx) / math.sqrt(sq**2 + sx**2) if sq and sx else 0.0
    out.z_qsd_minus_random = (fq - fr) / math.sqrt(sq**2 + sr**2) if sq and sr else 0.0

    if out.z_qsd_minus_x > 1.96 and out.z_qsd_minus_random > 1.96:
        out.verdict = "QSD_ECHO_WIN"
    elif fq > fx and fq > out.pooled["no_echo"]["F"]:
        out.verdict = "MARGINAL"
    else:
        out.verdict = "NULL"

    return out
