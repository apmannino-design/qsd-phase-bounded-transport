"""
Casimir-style 3-qubit boundary Hamiltonian — plates, gap mode, and QSD binding.

Physical analogy on a linear 3Q cell:
  q0, q2  = plates (boundary conditions)
  q1      = gap / cavity mode between plates

    H = -J_p (Z₀Z₁ + Z₁Z₂)  -  J_c Z₀Z₂  -  g Z₀Z₁Z₂  -  h X₁

The direct Z₀Z₂ term is the Casimir-like coupling through the gap (non-local
across the cavity). The tripartite Z₀Z₁Z₂ term captures mode-aligned binding.

QSD depth sunscreen at θ* is applied when the target observable is Z-type
correlation / binding energy — the validated Willow use case.
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
)
from aurora_qsd.quantum.willow_lines import WillowLine, get_line
from aurora_qsd.quantum.willow_run import (
    _depth_head_to_head,
    _require_cirq,
    _zzz_from_result,
    build_depth_sunscreen_circuit,
)

def _cz_cnot(control, target) -> list:
    """CNOT via H–CZ–H (Willow native)."""
    import cirq

    return [cirq.H(target), cirq.CZ(control, target), cirq.H(target)]


def _pauli_matrix(name: str) -> np.ndarray:
    mats = {
        "I": np.eye(2, dtype=complex),
        "X": np.array([[0, 1], [1, 0]], dtype=complex),
        "Z": np.array([[1, 0], [0, -1]], dtype=complex),
    }
    return mats[name]


def _kron3(a: str, b: str, c: str) -> np.ndarray:
    return np.kron(_pauli_matrix(a), np.kron(_pauli_matrix(b), _pauli_matrix(c)))


@dataclass(frozen=True)
class CasimirHamiltonian:
    """
    3-qubit Casimir / cavity-boundary Hamiltonian on a line.

    J_plate: nearest-neighbor plate–gap coupling
    J_cas:   direct plate–plate coupling through gap (Casimir channel)
    g_zzz:   tripartite binding (mode-aligned ZZZ)
    h_gap:   transverse fluctuation on gap qubit
    """

    J_plate: float = 1.0
    J_cas: float = 0.5
    g_zzz: float = 0.8
    h_gap: float = 0.15

    def matrix(self) -> np.ndarray:
        z = _kron3
        return (
            -self.J_plate * (z("Z", "Z", "I") + z("I", "Z", "Z"))
            - self.J_cas * z("Z", "I", "Z")
            - self.g_zzz * z("Z", "Z", "Z")
            - self.h_gap * z("I", "X", "I")
        )

    def label(self) -> str:
        return (
            f"-{self.J_plate}*(Z0Z1+Z1Z2) -{self.J_cas}*Z0Z2 "
            f"-{self.g_zzz}*Z0Z1Z2 -{self.h_gap}*X1"
        )


@dataclass
class CasimirGroundState:
    energy: float
    zzz: float
    zz01: float
    zz12: float
    zz02: float
    psi: np.ndarray


def exact_casimir_ground(ham: CasimirHamiltonian) -> CasimirGroundState:
    """Exact ground state and Casimir observables."""
    H = ham.matrix()
    evals, evecs = np.linalg.eigh(H)
    psi = evecs[:, 0]
    e0 = float(np.real(evals[0]))

    def exp(pauli: str) -> float:
        op = _kron3(*pauli)
        return float(np.real(np.vdot(psi, op @ psi)))

    return CasimirGroundState(
        energy=e0,
        zzz=exp("ZZZ"),
        zz01=exp("ZZI"),
        zz12=exp("IZZ"),
        zz02=exp("ZIZ"),
        psi=psi,
    )


def _zz_pair_evolution(q0, q1, J: float, dt: float) -> list:
    import cirq

    return [
        cirq.CZ(q0, q1),
        cirq.rz(2.0 * J * dt)(q0),
        cirq.rz(2.0 * J * dt)(q1),
        cirq.CZ(q0, q1),
    ]


def _zz_nonlocal_evolution(q0, q1, q2, J: float, dt: float) -> list:
    """exp(-i dt J Z0 Z2) via middle qubit (Willow-native CNOT)."""
    import cirq

    ops: list = []
    ops.extend(_cz_cnot(q0, q1))
    ops.extend(_cz_cnot(q2, q1))
    ops.append(cirq.rz(2.0 * J * dt)(q1))
    ops.extend(_cz_cnot(q2, q1))
    ops.extend(_cz_cnot(q0, q1))
    return ops


def _zzz_evolution(q0, q1, q2, g: float, dt: float) -> list:
    """exp(-i dt g Z0 Z1 Z2) — parity-controlled rotation (Willow-native)."""
    import cirq

    ops: list = []
    ops.extend(_cz_cnot(q0, q1))
    ops.extend(_cz_cnot(q2, q1))
    ops.append(cirq.rz(2.0 * g * dt)(q1))
    ops.extend(_cz_cnot(q2, q1))
    ops.extend(_cz_cnot(q0, q1))
    return ops


def build_casimir_trotter_step(qubits: list, ham: CasimirHamiltonian, dt: float) -> list:
    """Single first-order Trotter step for CasimirHamiltonian."""
    import cirq

    q0, q1, q2 = qubits
    ops: list = []
    ops.extend(_zz_pair_evolution(q0, q1, ham.J_plate, dt))
    ops.extend(_zz_pair_evolution(q1, q2, ham.J_plate, dt))
    ops.extend(_zz_nonlocal_evolution(q0, q1, q2, ham.J_cas, dt))
    ops.extend(_zzz_evolution(q0, q1, q2, ham.g_zzz, dt))
    if ham.h_gap != 0.0:
        ops.append(cirq.rx(2.0 * ham.h_gap * dt)(q1))
    return ops


def build_casimir_evolution_ops(
    line: WillowLine,
    ham: CasimirHamiltonian,
    trotter_steps: int,
    dt: float,
    mode: str = "bare",
    theta_deg: float = OPTIMAL_THETA_DEG,
    sunscreen_layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    sunscreen_every: int = 3,
    relock: int = OPTIMAL_RELOCK_INTERVAL,
) -> list:
    """
    Trotter evolution under Casimir H with optional QSD sunscreen.

    mode: bare | qsd | wrong
    """
    qubits = list(line.qubits())
    theta = float(np.radians(theta_deg))
    if mode == "wrong":
        theta = negative_control_angle(theta)

    ops: list = []
    for step in range(trotter_steps):
        if mode in ("qsd", "wrong") and step > 0 and step % sunscreen_every == 0:
            _append_sunscreen_block(ops, qubits, theta, sunscreen_layers, relock=relock)
        ops.extend(build_casimir_trotter_step(qubits, ham, dt))
    return ops


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
        sign = 1.0 if int(bitstring[i]) == int(bitstring[j]) else -1.0
        acc += sign * n
    return acc / total


def _x_expectation(counts: dict[str, int], i: int) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    acc = 0.0
    for bitstring, n in counts.items():
        acc += (1.0 - 2.0 * int(bitstring[i])) * n
    return acc / total


def energy_from_counts(
    counts: dict[str, int],
    ham: CasimirHamiltonian,
    x_counts: dict[str, int] | None = None,
) -> dict[str, float]:
    """⟨H⟩ and component correlators from measurement counts."""
    zz01 = _zz_expectation(counts, 0, 1)
    zz12 = _zz_expectation(counts, 1, 2)
    zz02 = _zz_expectation(counts, 0, 2)
    zzz = sum(
        (1.0 if bs.count("1") % 2 == 0 else -1.0) * n
        for bs, n in counts.items()
    ) / sum(counts.values())
    x1 = _x_expectation(x_counts, 1) if x_counts else 0.0
    energy = float(
        -ham.J_plate * (zz01 + zz12)
        - ham.J_cas * zz02
        - ham.g_zzz * zzz
        - ham.h_gap * x1
    )
    return {
        "energy": energy,
        "zzz": zzz,
        "zz01": zz01,
        "zz12": zz12,
        "zz02": zz02,
        "x1": x1,
    }


def _run_casimir_noisy(
    sampler,
    line: WillowLine,
    ham: CasimirHamiltonian,
    shots: int,
    trotter_steps: int,
    dt: float,
    mode: str,
    theta_deg: float,
    **kwargs,
) -> dict:
    import cirq

    qubits = list(line.qubits())
    base = build_casimir_evolution_ops(
        line, ham, trotter_steps, dt, mode, theta_deg, **kwargs,
    )

    ops_z = list(base)
    for q in qubits:
        ops_z.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    rz = sampler.run(cirq.Circuit(ops_z), repetitions=shots)

    ops_x = list(base)
    ops_x.append(cirq.H(qubits[1]))
    for q in qubits:
        ops_x.append(cirq.measure(q, key=f"m_{q.row}_{q.col}"))
    rx = sampler.run(cirq.Circuit(ops_x), repetitions=shots)

    cz = _counts_from_result(rz, shots)
    cx = _counts_from_result(rx, shots)
    obs = energy_from_counts(cz, ham, cx)
    obs["n"] = shots
    return obs


def _noiseless_observables(
    line: WillowLine,
    ham: CasimirHamiltonian,
    trotter_steps: int,
    dt: float,
    mode: str,
    theta_deg: float,
    **kwargs,
) -> dict:
    import cirq

    ops = build_casimir_evolution_ops(
        line, ham, trotter_steps, dt, mode, theta_deg, **kwargs,
    )
    state = cirq.Simulator().simulate(cirq.Circuit(ops)).final_state_vector
    H = ham.matrix()
    energy = float(np.real(np.vdot(state, H @ state)))
    zzz_op = _kron3("Z", "Z", "Z")
    zzz = float(np.real(np.vdot(state, zzz_op @ state)))
    return {"energy": energy, "zzz": zzz}


@dataclass
class CasimirBenchmarkResult:
    task: str = "casimir_3q_hamiltonian"
    hamiltonian: str = ""
    line: list[str] = field(default_factory=list)
    line_role: str = ""
    trotter_steps: int = 8
    dt: float = 0.2
    shots: int = 0
    e_ground: float = 0.0
    zzz_ground: float = 0.0
    zz02_ground: float = 0.0
    bare: dict = field(default_factory=dict)
    qsd: dict = field(default_factory=dict)
    wrong: dict = field(default_factory=dict)
    depth_sunscreen: dict = field(default_factory=dict)
    verdict: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "task": self.task,
            "hamiltonian": self.hamiltonian,
            "line": self.line,
            "line_role": self.line_role,
            "trotter_steps": self.trotter_steps,
            "dt": self.dt,
            "shots": self.shots,
            "e_ground": self.e_ground,
            "zzz_ground": self.zzz_ground,
            "zz02_ground": self.zz02_ground,
            "bare": self.bare,
            "qsd": self.qsd,
            "wrong": self.wrong,
            "depth_sunscreen": self.depth_sunscreen,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def run_casimir_trotter_benchmark(
    shots: int = 800,
    trotter_steps: int = 8,
    dt: float = 0.2,
    line_name: str = "interior",
    ham: CasimirHamiltonian | None = None,
    theta_deg: float = OPTIMAL_THETA_DEG,
) -> CasimirBenchmarkResult:
    """
    Evolve under Casimir H via Trotter; compare bare vs QSD-wrapped vs wrong θ.

    Measures |⟨H⟩ - E₀| and Casimir channel ⟨Z₀Z₂⟩.
    """
    _require_cirq()
    from cirq_google import engine

    ham = ham or CasimirHamiltonian()
    line = get_line(line_name)
    gs = exact_casimir_ground(ham)
    role = "plate_edge" if line_name == "boundary" else "cavity_interior"

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()

    out = CasimirBenchmarkResult(
        hamiltonian=ham.label(),
        line=line.labels(),
        line_role=role,
        trotter_steps=trotter_steps,
        dt=dt,
        shots=shots,
        e_ground=gs.energy,
        zzz_ground=gs.zzz,
        zz02_ground=gs.zz02,
    )

    for label, mode in [("bare", "bare"), ("qsd", "qsd"), ("wrong", "wrong")]:
        noisy = _run_casimir_noisy(
            sampler, line, ham, shots, trotter_steps, dt, mode, theta_deg,
        )
        ideal = _noiseless_observables(
            line, ham, trotter_steps, dt, mode, theta_deg,
        )
        err = abs(noisy["energy"] - gs.energy)
        cas_err = abs(noisy["zz02"] - gs.zz02)
        out.__dict__[label] = {
            **noisy,
            "error_vs_ground": err,
            "zz02_error": cas_err,
            "noiseless_energy": ideal["energy"],
        }

    eb = out.bare["error_vs_ground"]
    eq = out.qsd["error_vs_ground"]
    ew = out.wrong["error_vs_ground"]
    cb = abs(out.bare["zz02"] - gs.zz02)
    cq = abs(out.qsd["zz02"] - gs.zz02)

    if eq < eb and eq < ew:
        out.verdict = "QSD_WINS"
        out.notes = (
            f"Casimir Trotter: QSD lowers |ΔE| ({eq:.3f} < bare {eb:.3f}, wrong {ew:.3f}); "
            f"|ΔZ₀Z₂| qsd={cq:.3f} vs bare {cb:.3f}."
        )
    elif cq < cb:
        out.verdict = "CASIMIR_CHANNEL"
        out.notes = f"QSD improves plate–plate correlator |ΔZ₀Z₂|: {cq:.3f} < bare {cb:.3f}."
    else:
        out.verdict = "NULL"
        out.notes = f"Casimir Trotter: no clear QSD gain (bare |ΔE|={eb:.3f}, qsd={eq:.3f})."

    return out


def run_casimir_depth_benchmark(
    shots: int = 800,
    line_name: str = "interior",
    ham: CasimirHamiltonian | None = None,
    theta_deg: float = OPTIMAL_THETA_DEG,
    layers: int = OPTIMAL_SUNSCREEN_LAYERS,
    relock: int = OPTIMAL_RELOCK_INTERVAL,
) -> dict:
    """
    Task-aligned Casimir binding via depth sunscreen (no Trotter).

    Binding energy E_bind = -⟨Z₀Z₁Z₂⟩; ground-state alignment on ZZZ.
    This is the validated QSD protocol applied to the Casimir tripartite term.
    """
    _require_cirq()
    from cirq_google import engine

    ham = ham or CasimirHamiltonian()
    line = get_line(line_name)
    gs = exact_casimir_ground(ham)
    role = "plate_edge" if line_name == "boundary" else "cavity_interior"

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    sampler = proc.get_sampler()
    theta = float(np.radians(theta_deg))
    theta_neg = negative_control_angle(theta)

    row = _depth_head_to_head(sampler, line, shots, theta, theta_neg, layers, relock)
    z_qsd = row["qsd_theta_star"]["zzz"]
    z_wrong = row["negative_theta"]["zzz"]

    e_qsd = -ham.g_zzz * z_qsd
    e_wrong = -ham.g_zzz * z_wrong
    e_zzz_ground = -ham.g_zzz * gs.zzz

    return {
        "task": "casimir_depth_binding",
        "hamiltonian": ham.label(),
        "line": line.labels(),
        "line_role": role,
        "e_zzz_component_ground": e_zzz_ground,
        "qsd": {
            "zzz": z_qsd,
            "binding_energy": e_qsd,
            "error_vs_ground": abs(e_qsd - e_zzz_ground),
        },
        "wrong": {
            "zzz": z_wrong,
            "binding_energy": e_wrong,
            "error_vs_ground": abs(e_wrong - e_zzz_ground),
        },
        "abs_gap": row["abs_gap"],
        "verdict": "QSD_WINS" if row["abs_gap"] >= 0.05 else "NULL",
        "notes": (
            f"Casimir ZZZ binding @ θ*={theta_deg}°: |ΔZZZ|={row['abs_gap']:.3f} "
            f"({role} line). Tripartite term captures mode-aligned plate coupling."
        ),
    }


def run_casimir_campaign(
    shots: int = 800,
    trotter_steps: int = 8,
    dt: float = 0.2,
    ham: CasimirHamiltonian | None = None,
    pattern: str = "all",
    **kwargs,
) -> dict:
    """
    Full Casimir Hamiltonian campaign: interior vs boundary, Trotter + depth binding.

    pattern: all | depth | trotter
    """
    ham = ham or CasimirHamiltonian()
    out: dict = {
        "hamiltonian": ham.label(),
        "analogy": (
            "q0,q2 = Casimir plates; q1 = gap mode; Z0Z2 = direct cavity coupling; "
            "Z0Z1Z2 = mode-aligned tripartite binding. Boundary line = physical chip edge."
        ),
        "guidance": (
            "Use depth sunscreen @ θ* for Casimir ZZZ binding (tripartite correlator). "
            "Trotter evolution under full Casimir H may still favor bare — check verdicts. "
            "Interior cavity lines outperform boundary plate-edge lines on Willow."
        ),
    }

    if pattern in ("all", "trotter"):
        out["interior_trotter"] = run_casimir_trotter_benchmark(
            shots=shots, trotter_steps=trotter_steps, dt=dt,
            line_name="interior", ham=ham, **kwargs,
        ).to_dict()
        out["boundary_trotter"] = run_casimir_trotter_benchmark(
            shots=shots, trotter_steps=trotter_steps, dt=dt,
            line_name="boundary", ham=ham, **kwargs,
        ).to_dict()

    if pattern in ("all", "depth"):
        out["interior_depth_binding"] = run_casimir_depth_benchmark(
            shots=shots, line_name="interior", ham=ham, **kwargs,
        )
        out["boundary_depth_binding"] = run_casimir_depth_benchmark(
            shots=shots, line_name="boundary", ham=ham, **kwargs,
        )

    interior_depth = out.get("interior_depth_binding", {})
    boundary_depth = out.get("boundary_depth_binding", {})
    depth_wins = sum(
        1 for d in (interior_depth, boundary_depth) if d.get("verdict") == "QSD_WINS"
    )
    out["summary"] = {
        "depth_binding_wins": depth_wins,
        "interior_depth_gap": interior_depth.get("abs_gap"),
        "boundary_depth_gap": boundary_depth.get("abs_gap"),
        "interior_trotter_verdict": out.get("interior_trotter", {}).get("verdict"),
        "boundary_trotter_verdict": out.get("boundary_trotter", {}).get("verdict"),
    }
    return out
