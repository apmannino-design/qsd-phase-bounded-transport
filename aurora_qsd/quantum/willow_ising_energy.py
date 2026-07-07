"""
3-qubit Ising energy benchmark — task-level ΔE vs exact ground state.

H = -J (Z₀Z₁ + Z₁Z₂) - h (X₀ + X₁ + X₂)   on a line of 3 qubits.

Compares bare Trotter evolution vs periodic QSD sunscreen re-lock vs wrong θ.
Reports |⟨H⟩ - E₀| (lower = closer to true ground-state energy).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aurora_qsd.quantum.fez_cells import negative_control_angle
from aurora_qsd.quantum.willow_algorithm import (
    OPTIMAL_RELOCK_INTERVAL,
    OPTIMAL_SUNSCREEN_LAYERS,
    OPTIMAL_THETA_DEG,
    _append_sunscreen_block,
    _ising_trotter_step,
)
from aurora_qsd.quantum.willow_lines import WillowLine, get_line
from aurora_qsd.quantum.willow_run import _require_cirq


def _pauli_matrix(name: str) -> np.ndarray:
    if name == "I":
        return np.eye(2, dtype=complex)
    if name == "X":
        return np.array([[0, 1], [1, 0]], dtype=complex)
    if name == "Y":
        return np.array([[0, -1j], [1j, 0]], dtype=complex)
    if name == "Z":
        return np.array([[1, 0], [0, -1]], dtype=complex)
    raise ValueError(name)


def _kron3(a: str, b: str, c: str) -> np.ndarray:
    return np.kron(_pauli_matrix(a), np.kron(_pauli_matrix(b), _pauli_matrix(c)))


def exact_ising_ground_energy(J: float, h: float) -> tuple[float, float]:
    """Exact E₀ and ⟨Z⊗Z⊗Z⟩ for 3-qubit open-chain TFIM."""
    H = -J * (_kron3("Z", "Z", "I") + _kron3("I", "Z", "Z")) - h * (
        _kron3("X", "I", "I") + _kron3("I", "X", "I") + _kron3("I", "I", "X")
    )
    evals, evecs = np.linalg.eigh(H)
    psi = evecs[:, 0]
    e0 = float(np.real(evals[0]))
  # ZZZ expectation in ground state
    ZZZ = _kron3("Z", "Z", "Z")
    zzz = float(np.real(np.vdot(psi, ZZZ @ psi)))
    return e0, zzz


def build_evolution_ops(
    line: WillowLine,
    trotter_steps: int,
    J: float,
    h: float,
    dt: float,
    mode: str = "bare",
    theta_deg: float = OPTIMAL_THETA_DEG,
    sunscreen_layers: int = 3,
    sunscreen_every: int = 2,
) -> list:
    """
    Trotter evolution ops (no measurement).

    mode: bare | qsd | wrong
    qsd/wrong: insert mini sunscreen every `sunscreen_every` steps.
    """
    qubits = list(line.qubits())
    theta = float(np.radians(theta_deg))
    if mode == "wrong":
        theta = negative_control_angle(theta)
    ops: list = []
    for step in range(trotter_steps):
        if mode in ("qsd", "wrong") and step > 0 and step % sunscreen_every == 0:
            _append_sunscreen_block(ops, qubits, theta, sunscreen_layers, relock=2)
        ops.extend(_ising_trotter_step(qubits, J, h, dt))
    return ops


def _measure_keys(qubits: list) -> list[str]:
    return [f"m_{q.row}_{q.col}" for q in qubits]


def _counts_from_result(result, shots: int) -> dict[str, int]:
    keys = sorted(result.data.keys(), key=lambda k: str(k))
    counts: dict[str, int] = {}
    for i in range(shots):
        bits = "".join(str(int(result.data[k][i])) for k in keys)
        counts[bits] = counts.get(bits, 0) + 1
    return counts


def _zz_expectation(counts: dict[str, int], i: int, j: int) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    acc = 0.0
    for bitstring, n in counts.items():
        zi = int(bitstring[i])
        zj = int(bitstring[j])
        sign = 1.0 if zi == zj else -1.0
        acc += sign * n
    return acc / total


def _x_expectation_from_z_counts(counts: dict[str, int], i: int) -> float:
    """⟨Xᵢ⟩ from Z-basis counts after H applied (caller applies H)."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    acc = 0.0
    for bitstring, n in counts.items():
        # measure X via H then Z: P(0) - P(1)
        acc += (1.0 - 2.0 * int(bitstring[i])) * n
    return acc / total


def _energy_from_z_counts(counts: dict[str, int], J: float, h: float, x_counts: dict[str, int] | None = None) -> float:
    zz01 = _zz_expectation(counts, 0, 1)
    zz12 = _zz_expectation(counts, 1, 2)
    if x_counts is None:
        xs = 0.0
    else:
        xs = sum(_x_expectation_from_z_counts(x_counts, i) for i in range(3))
    return float(-J * (zz01 + zz12) - h * xs)


def _noiseless_energy(
    line: WillowLine,
    trotter_steps: int,
    J: float,
    h: float,
    dt: float,
    mode: str,
    theta_deg: float,
) -> float:
    import cirq

    qubits = list(line.qubits())
    ops = build_evolution_ops(line, trotter_steps, J, h, dt, mode, theta_deg)
    state = cirq.Simulator().simulate(cirq.Circuit(ops)).final_state_vector
    Hmat = -J * (_kron3("Z", "Z", "I") + _kron3("I", "Z", "Z")) - h * (
        _kron3("X", "I", "I") + _kron3("I", "X", "I") + _kron3("I", "I", "X")
    )
    return float(np.real(np.vdot(state, Hmat @ state)))


def _run_energy_noisy(
    sampler,
    line: WillowLine,
    shots: int,
    trotter_steps: int,
    J: float,
    h: float,
    dt: float,
    mode: str,
    theta_deg: float,
) -> dict:
    import cirq

    qubits = list(line.qubits())
    base = build_evolution_ops(line, trotter_steps, J, h, dt, mode, theta_deg)

    # Z-basis for ZZ terms
    ops_z = list(base)
    for q in qubits:
        ops_z.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    rz = sampler.run(cirq.Circuit(ops_z), repetitions=shots)

    # X terms: H then measure
    ops_x = list(base)
    for q in qubits:
        ops_x.append(cirq.H(q))
    for q in qubits:
        ops_x.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    rx = sampler.run(cirq.Circuit(ops_x), repetitions=shots)

    cz = _counts_from_result(rz, shots)
    cx = _counts_from_result(rx, shots)
    energy = _energy_from_z_counts(cz, J, h, cx)
    return {"energy": energy, "n": shots}


@dataclass
class IsingEnergyResult:
    task: str = "ising_3q_energy"
    line: list[str] = field(default_factory=list)
    J: float = 1.2
    h_field: float = 0.1
    trotter_steps: int = 10
    dt: float = 0.25
    shots: int = 0
    e_ground: float = 0.0
    zzz_ground: float = 0.0
    bare: dict = field(default_factory=dict)
    qsd: dict = field(default_factory=dict)
    wrong: dict = field(default_factory=dict)
    verdict: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "line": self.line,
            "J": self.J,
            "h_field": self.h_field,
            "trotter_steps": self.trotter_steps,
            "dt": self.dt,
            "shots": self.shots,
            "e_ground": self.e_ground,
            "zzz_ground": self.zzz_ground,
            "bare": self.bare,
            "qsd": self.qsd,
            "wrong": self.wrong,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def run_ising_energy_benchmark(
    shots: int = 800,
    trotter_steps: int = 10,
    J: float = 1.2,
    h: float = 0.1,
    dt: float = 0.25,
    line_name: str = "interior",
    theta_deg: float = OPTIMAL_THETA_DEG,
    sunscreen_layers: int = 3,
    sunscreen_every: int = 2,
) -> IsingEnergyResult:
    """Run Ising ΔE benchmark on willow_pink."""
    _require_cirq()
    from cirq_google import engine

    line = get_line(line_name)
    e0, zzz0 = exact_ising_ground_energy(J, h)
    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()

    out = IsingEnergyResult(
        line=line.labels(),
        J=J,
        h_field=h,
        trotter_steps=trotter_steps,
        dt=dt,
        shots=shots,
        e_ground=e0,
        zzz_ground=zzz0,
    )

    for label, mode in [("bare", "bare"), ("qsd", "qsd"), ("wrong", "wrong")]:
        noisy = _run_energy_noisy(sampler, line, shots, trotter_steps, J, h, dt, mode, theta_deg)
        ideal = _noiseless_energy(line, trotter_steps, J, h, dt, mode, theta_deg)
        err = abs(noisy["energy"] - e0)
        out.__dict__[label] = {
            "energy": noisy["energy"],
            "error_vs_ground": err,
            "noiseless_energy": ideal,
            "n": shots,
        }

    eb = out.bare["error_vs_ground"]
    eq = out.qsd["error_vs_ground"]
    ew = out.wrong["error_vs_ground"]

    if eq < eb and eq < ew:
        out.verdict = "QSD_WINS"
        out.notes = f"Periodic QSD lowers |ΔE| vs ground: {eq:.3f} < bare {eb:.3f}, wrong {ew:.3f}."
    elif eq < eb:
        out.verdict = "PARTIAL"
        out.notes = f"QSD beats bare on energy ({eq:.3f} < {eb:.3f})."
    else:
        out.verdict = "NULL"
        out.notes = f"Periodic QSD did not improve energy estimate (bare {eb:.3f}, qsd {eq:.3f})."

    return out


def run_zzz_task_energy_benchmark(
    shots: int = 800,
    line_name: str = "interior",
    theta_deg: float = OPTIMAL_THETA_DEG,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock: int = OPTIMAL_RELOCK_INTERVAL,
) -> dict:
    """
    Task-aligned benchmark: minimize H = -Z₀Z₁Z₂ via QSD depth sunscreen.

    Here the 'energy' is E = -⟨ZZZ⟩; lower is better (ground = -1).
    """
    _require_cirq()
    from cirq_google import engine

    from aurora_qsd.quantum.willow_run import _depth_head_to_head

    line = get_line(line_name)
    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()
    theta = float(np.radians(theta_deg))
    theta_neg = negative_control_angle(theta)
    row = _depth_head_to_head(sampler, line, shots, theta, theta_neg, layers, relock)

    e_qsd = -row["qsd_theta_star"]["zzz"]
    e_wrong = -row["negative_theta"]["zzz"]
    e_ground = -1.0

    return {
        "task": "zzz_hamiltonian_energy",
        "hamiltonian": "-Z0Z1Z2",
        "e_ground": e_ground,
        "qsd": {
            "energy": e_qsd,
            "error_vs_ground": abs(e_qsd - e_ground),
            "zzz": row["qsd_theta_star"]["zzz"],
        },
        "wrong": {
            "energy": e_wrong,
            "error_vs_ground": abs(e_wrong - e_ground),
            "zzz": row["negative_theta"]["zzz"],
        },
        "abs_gap": row["abs_gap"],
        "verdict": "QSD_WINS" if row["abs_gap"] >= 0.05 else "NULL",
        "notes": (
            f"Task-aligned: E=-⟨ZZZ⟩. θ* error {abs(e_qsd - e_ground):.3f} vs "
            f"wrong {abs(e_wrong - e_ground):.3f} (|ΔZZZ|={row['abs_gap']:.3f})."
        ),
    }


def run_usable_benchmark(shots: int = 800, **kwargs) -> dict:
    """Full usable package: Ising Trotter + ZZZ-task energy."""
    ising = run_ising_energy_benchmark(shots=shots, **kwargs).to_dict()
    zzz = run_zzz_task_energy_benchmark(shots=shots, **kwargs)
    return {
        "ising_trotter": ising,
        "zzz_hamiltonian": zzz,
        "guidance": (
            "Use bare Trotter for Ising energy; use QSD depth when the task "
            "is ZZZ correlation / -Z0Z1Z2 minimization."
        ),
    }
