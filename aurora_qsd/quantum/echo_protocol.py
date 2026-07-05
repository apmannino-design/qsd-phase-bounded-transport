"""
Willow / line echo protocol — correct QSD validation experiment.

NOT the IBM fez ZZZ depth test. This is:
  prepare |ψ⟩ → P → idle τ → P† → measure survival

echo_qsd:   P = full TriDelta TriLock sunscreen (3Q QSD cell) at θ* = π/8
echo_x:     P = X on line
echo_random:P = Rz(φ) on line
no_echo:    τ only
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_WILLOW_HW, THETA_STAR_WILLOW_HW_DEG
from aurora_qsd.quantum.fez_cells import _trilock_init, append_sunscreen_reset
from aurora_qsd.quantum.willow_noise import qiskit_idle_noise_model

try:
    from qiskit import QuantumCircuit
except ImportError:
    QuantumCircuit = None  # type: ignore[misc, assignment]

THETA_STAR_WILLOW = THETA_STAR_WILLOW_HW
THETA_STAR_WILLOW_DEG = THETA_STAR_WILLOW_HW_DEG
STATES = ("0", "1", "+", "-", "+i", "-i")
PULSE_VARIANTS = ("tridelta", "phase", "sunscreen", "hybrid", "relock")
DEFAULT_PULSE_VARIANT = "tridelta"


def _require_qiskit() -> None:
    if QuantumCircuit is None:
        raise ImportError("qiskit required")


def _qsd_echo_layer(theta: float = THETA_STAR_WILLOW) -> "QuantumCircuit":
    """
    QSD echo pulse P at θ*: TriLock RY init + alternating RZ phase kick.

    Phase echo on a line — no entangling CX (unlike fez ZZZ depth sunscreen).
    """
    _require_qiskit()
    qc = QuantumCircuit(3, name="qsd_echo")
    _trilock_init(qc, (0, 1, 2), theta)
    for i, q in enumerate((0, 1, 2)):
        qc.rz(theta if i % 2 == 0 else np.pi / 2.0 - theta, q)
    return qc


def _prepare_state(qc: "QuantumCircuit", q: int, state: str) -> None:
    if state == "0":
        return
    if state == "1":
        qc.x(q)
    elif state == "+":
        qc.h(q)
    elif state == "-":
        qc.h(q)
        qc.z(q)
    elif state == "+i":
        qc.h(q)
        qc.s(q)
    elif state == "-i":
        qc.h(q)
        qc.sdg(q)
    else:
        raise ValueError(state)


def _inverse_prepare_state(qc: "QuantumCircuit", q: int, state: str) -> None:
    """Undo preparation so Z-measurement on q tests survival in the prep basis."""
    if state == "0":
        return
    if state == "1":
        qc.x(q)
    elif state == "+":
        qc.h(q)
    elif state == "-":
        qc.z(q)
        qc.h(q)
    elif state == "+i":
        qc.sdg(q)
        qc.h(q)
    elif state == "-i":
        qc.s(q)
        qc.h(q)
    else:
        raise ValueError(state)


def _qsd_sunscreen_layer(theta: float = THETA_STAR_WILLOW) -> "QuantumCircuit":
    """Entangling TriLock sunscreen layer (fez-style, heavier pulse)."""
    _require_qiskit()
    qc = QuantumCircuit(3, name="qsd_sunscreen")
    append_sunscreen_reset(qc, (0, 1, 2), theta)
    return qc


def _qsd_tridelta_layer(theta: float = THETA_STAR_WILLOW) -> "QuantumCircuit":
    """Full TriDelta TriLock sunscreen: init + 2Q QSD + line bridge (fez-validated)."""
    return _qsd_sunscreen_layer(theta)


def _qsd_pulse_layer(theta: float, variant: str = DEFAULT_PULSE_VARIANT) -> "QuantumCircuit":
    if variant in ("tridelta", "sunscreen"):
        return _qsd_tridelta_layer(theta)
    if variant == "phase":
        return _qsd_echo_layer(theta)
    if variant == "hybrid":
        _require_qiskit()
        qc = QuantumCircuit(3, name="qsd_hybrid")
        for q in (0, 1, 2):
            qc.x(q)
        qc.compose(_qsd_echo_layer(theta), qubits=[0, 1, 2], inplace=True)
        return qc
    if variant == "relock":
        return _qsd_tridelta_layer(theta)
    raise ValueError(f"unknown pulse variant: {variant}")


def _append_echo_forward(
    qc: "QuantumCircuit",
    line: tuple[int, int, int],
    mode: str,
    theta: float,
    phi: float,
    pulse_variant: str = DEFAULT_PULSE_VARIANT,
) -> None:
    q0, q1, q2 = line
    if mode == "qsd":
        qc.compose(_qsd_pulse_layer(theta, pulse_variant), qubits=[q0, q1, q2], inplace=True)
    elif mode == "x":
        qc.x(q0)
        qc.x(q1)
        qc.x(q2)
    elif mode == "random":
        qc.rz(phi, q0)
        qc.rz(phi, q1)
        qc.rz(phi, q2)
    elif mode == "none":
        pass
    else:
        raise ValueError(mode)


def _append_echo_inverse(
    qc: "QuantumCircuit",
    line: tuple[int, int, int],
    mode: str,
    theta: float,
    phi: float,
    pulse_variant: str = DEFAULT_PULSE_VARIANT,
) -> None:
    q0, q1, q2 = line
    if mode == "qsd":
        qc.compose(_qsd_pulse_layer(theta, pulse_variant).inverse(), qubits=[q0, q1, q2], inplace=True)
    elif mode == "x":
        qc.x(q0)
        qc.x(q1)
        qc.x(q2)
    elif mode == "random":
        qc.rz(-phi, q0)
        qc.rz(-phi, q1)
        qc.rz(-phi, q2)
    elif mode == "none":
        pass


def build_echo_circuit(
    state: str,
    mode: str,
    tau_ns: float = 1000.0,
    theta: float = THETA_STAR_WILLOW,
    phi: float = 0.0,
    line: tuple[int, int, int] = (0, 1, 2),
    target: int = 1,
    pulse_variant: str = DEFAULT_PULSE_VARIANT,
) -> "QuantumCircuit":
    """Echo circuit: |0⟩ on line, |ψ⟩ on middle qubit, survival via inverse-prep + Z."""
    _require_qiskit()
    qc = QuantumCircuit(3, 1)
    _prepare_state(qc, target, state)

    if mode != "none":
        _append_echo_forward(qc, line, mode, theta, phi, pulse_variant)

    if tau_ns > 0:
        if pulse_variant == "relock" and mode == "qsd":
            half = int(tau_ns / 2)
            qc.delay(half, list(line), unit="ns")
            qc.compose(_qsd_tridelta_layer(theta), qubits=list(line), inplace=True)
            qc.delay(int(tau_ns) - half, list(line), unit="ns")
        else:
            qc.delay(int(tau_ns), list(line), unit="ns")

    if mode != "none":
        _append_echo_inverse(qc, line, mode, theta, phi, pulse_variant)

    _inverse_prepare_state(qc, target, state)
    qc.measure(target, 0)
    return qc


def _survival_probability(qc: "QuantumCircuit", state: str, target: int = 1) -> float:
    """Noiseless survival P(target=0) after inverse-prep measurement."""
    from qiskit.quantum_info import Statevector

    qc_u = qc.remove_final_measurements(inplace=False)
    psi_out = Statevector.from_label("000").evolve(qc_u)
    return float(psi_out.probabilities([target])[0])


def _willow_idle_noise_model(tau_ns: float = 1000.0, t2_ns: float = 2000.0) -> "NoiseModel":
    """Idle thermal noise during echo delay τ (Willow/qsim-like)."""
    return qiskit_idle_noise_model(tau_ns=tau_ns, t2_ns=t2_ns)


def _count_survival(counts: dict[str, int]) -> int:
    """Success = middle-qubit survival bit (classical bit 0) reads 0."""
    return int(counts.get("0", 0))


def _pooled_stats(mode_data: dict) -> dict:
    succ = sum(v["succ"] for v in mode_data.values())
    tot = sum(v["tot"] for v in mode_data.values())
    f = succ / tot if tot else 0.0
    se = math.sqrt(f * (1 - f) / tot) if tot else 0.0
    return {"F": f, "se": se, "n": tot}


@dataclass
class WillowEchoResult:
    processor: str = "willow_pink_sim"
    theta_star_rad: float = THETA_STAR_WILLOW
    theta_star_deg: float = THETA_STAR_WILLOW_DEG
    line: list[str] = field(default_factory=lambda: ["q(0,6)", "q(0,7)", "q(0,8)"])
    shots_per_circuit: int = 4000
    tau_ns: float = 1000.0
    random_phis_rad: list[float] = field(default_factory=list)
    per_state: dict = field(default_factory=dict)
    pooled: dict = field(default_factory=dict)
    z_qsd_minus_x: float = 0.0
    z_qsd_minus_random: float = 0.0
    verdict: str = "NULL"

    def to_dict(self) -> dict:
        return {
            "processor": self.processor,
            "theta_star_rad": self.theta_star_rad,
            "theta_star_deg": self.theta_star_deg,
            "line": self.line,
            "shots_per_circuit": self.shots_per_circuit,
            "tau_ns": self.tau_ns,
            "random_phis_rad": self.random_phis_rad,
            "per_state": self.per_state,
            "pooled": self.pooled,
            "z_qsd_minus_x": self.z_qsd_minus_x,
            "z_qsd_minus_random": self.z_qsd_minus_random,
            "verdict": self.verdict,
        }


def _run_echo_shots(
    sim,
    state: str,
    mode: str,
    shots: int,
    tau_ns: float,
    theta: float,
    phi: float,
    pulse_variant: str = DEFAULT_PULSE_VARIANT,
) -> dict[str, int]:
    from qiskit import transpile

    qc = build_echo_circuit(
        state=state,
        mode=mode,
        tau_ns=tau_ns,
        theta=theta,
        phi=phi,
        pulse_variant=pulse_variant,
    )
    tc = transpile(qc, sim, optimization_level=0)
    result = sim.run(tc, shots=shots).result()
    return result.get_counts()


def pooled_echo_fidelity(
    sim,
    mode: str = "qsd",
    shots: int = 1000,
    tau_ns: float = 1000.0,
    theta: float = THETA_STAR_WILLOW,
    phi: float = 0.0,
    pulse_variant: str = DEFAULT_PULSE_VARIANT,
    states: tuple[str, ...] = STATES,
) -> float:
    """Mean survival fidelity pooled over input states."""
    succ = tot = 0
    for state in states:
        counts = _run_echo_shots(sim, state, mode, shots, tau_ns, theta, phi, pulse_variant)
        succ += _count_survival(counts)
        tot += shots
    return succ / tot if tot else 0.0


def run_willow_echo_benchmark(
    shots: int = 4000,
    tau_ns: float = 1000.0,
    n_random: int = 10,
    seed: int = 42,
    t2_ns: float = 2000.0,
    pulse_variant: str = DEFAULT_PULSE_VARIANT,
) -> WillowEchoResult:
    """Run echo benchmark matching Willow JSON schema."""
    _require_qiskit()
    from qiskit_aer import AerSimulator

    rng = np.random.default_rng(seed)
    phis = [float(x) for x in rng.uniform(0, 2 * np.pi, n_random)]

    sim = AerSimulator(noise_model=_willow_idle_noise_model(tau_ns=tau_ns, t2_ns=t2_ns))

    out = WillowEchoResult(shots_per_circuit=shots, tau_ns=tau_ns, random_phis_rad=phis)

    for mode_name, mode in [("echo_qsd", "qsd"), ("echo_x", "x"), ("no_echo", "none")]:
        out.per_state[mode_name] = {}
        for state in STATES:
            counts = _run_echo_shots(
                sim, state, mode, shots, tau_ns, THETA_STAR_WILLOW, 0.0, pulse_variant
            )
            out.per_state[mode_name][state] = {
                "succ": _count_survival(counts),
                "tot": shots,
            }

    out.per_state["echo_random"] = {s: {"succ": 0, "tot": 0} for s in STATES}
    for phi in phis:
        for state in STATES:
            counts = _run_echo_shots(sim, state, "random", shots, tau_ns, THETA_STAR_WILLOW, phi)
            out.per_state["echo_random"][state]["succ"] += _count_survival(counts)
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
