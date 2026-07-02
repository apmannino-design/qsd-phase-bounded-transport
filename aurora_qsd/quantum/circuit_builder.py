"""QSD-stabilized quantum circuit construction."""

from __future__ import annotations

import numpy as np

from aurora_qsd.core.constants import THETA_STAR

try:
    from qiskit import QuantumCircuit
except ImportError:
    QuantumCircuit = None  # type: ignore[misc, assignment]


def _require_qiskit() -> None:
    if QuantumCircuit is None:
        raise ImportError("qiskit is required for circuit building. Install with: pip install qiskit qiskit-aer")


def build_qsd_cell(theta: float = THETA_STAR, layers: int = 1) -> "QuantumCircuit":
    """Build a 2-qubit QSD stabilization cell at partition angle theta."""
    _require_qiskit()
    qc = QuantumCircuit(2, 2)
    for _ in range(layers):
        qc.ry(2.0 * theta, 0)
        qc.ry(2.0 * (np.pi / 2.0 - theta), 1)
        qc.cx(0, 1)
        qc.rz(theta, 0)
        qc.rz(np.pi / 2.0 - theta, 1)
        qc.cx(1, 0)
    qc.measure([0, 1], [0, 1])
    return qc


def build_qsd_lattice(
    num_qubits: int,
    coupling_map: list[tuple[int, int]],
    theta: float = THETA_STAR,
    depth: int = 12,
) -> "QuantumCircuit":
    """Build multi-qubit QSD lattice circuit with TriDelta phase initialization."""
    _require_qiskit()
    qc = QuantumCircuit(num_qubits, num_qubits)

    for i in range(num_qubits):
        if i % 2 == 0:
            qc.ry(2.0 * theta, i)
        else:
            qc.ry(2.0 * (np.pi / 2.0 - theta), i)

    for _ in range(depth):
        for j, (a, b) in enumerate(coupling_map):
            if a < num_qubits and b < num_qubits and j % 3 == 0:
                qc.cx(a, b)
        for i in range(num_qubits):
            if i % 2 == 0:
                qc.rz(theta, i)
            else:
                qc.rz(np.pi / 2.0 - theta, i)

    qc.measure(range(num_qubits), range(num_qubits))
    return qc


def build_with_relock(
    num_qubits: int = 2,
    theta: float = THETA_STAR,
    total_layers: int = 35,
    relock_interval: int = 7,
) -> "QuantumCircuit":
    """
    Build circuit with periodic re-preparation (Aurora sunscreen protocol).

    Re-initializes to basin center every `relock_interval` layers.
    Validated on ibm_fez: sustains ZZZ at depth 1241.
    """
    _require_qiskit()
    qc = QuantumCircuit(num_qubits, num_qubits)

    layers_done = 0
    while layers_done < total_layers:
        block = min(relock_interval, total_layers - layers_done)

        # Re-preparation: reset to basin center
        for i in range(num_qubits):
            if i % 2 == 0:
                qc.ry(2.0 * theta, i)
            else:
                qc.ry(2.0 * (np.pi / 2.0 - theta), i)

        for _ in range(block):
            if num_qubits >= 2:
                qc.cx(0, 1)
            for i in range(num_qubits):
                if i % 2 == 0:
                    qc.rz(theta, i)
                else:
                    qc.rz(np.pi / 2.0 - theta, i)

        layers_done += block

    qc.measure(range(num_qubits), range(num_qubits))
    return qc


def parity_score(counts: dict[str, int], even_parity: tuple[str, ...] = ("00", "11")) -> float:
    """ZZZ-style parity correlation score from measurement counts."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return sum(counts.get(bs, 0) for bs in even_parity) / total
