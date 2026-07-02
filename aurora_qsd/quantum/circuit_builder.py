"""QSD-stabilized quantum circuit construction (ibm_fez-validated structure)."""

from __future__ import annotations

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_HW

try:
    from qiskit import QuantumCircuit
except ImportError:
    QuantumCircuit = None  # type: ignore[misc, assignment]


def _require_qiskit() -> None:
    if QuantumCircuit is None:
        raise ImportError("qiskit is required. Install with: pip install qiskit qiskit-aer")


def _append_qsd_cell(qc: "QuantumCircuit", theta: float) -> None:
    """Single QSD cell: RY(2θ) → CX → RZ(θ) → CX (reference implementation)."""
    qc.ry(2.0 * theta, 0)
    qc.ry(2.0 * (np.pi / 2.0 - theta), 1)
    qc.cx(0, 1)
    qc.rz(theta, 0)
    qc.rz(np.pi / 2.0 - theta, 1)
    qc.cx(1, 0)


def build_qsd_cell(theta: float = THETA_STAR_HW, layers: int = 1) -> "QuantumCircuit":
    """Build a 2-qubit QSD circuit with `layers` stacked cells at angle theta."""
    _require_qiskit()
    qc = QuantumCircuit(2, 2)
    for _ in range(layers):
        _append_qsd_cell(qc, theta)
    qc.measure([0, 1], [0, 1])
    return qc


def build_deep_qsd_circuit(theta: float = THETA_STAR_HW, layers: int = 12) -> "QuantumCircuit":
    """Alias matching code/qsd_reference_implementation.py."""
    return build_qsd_cell(theta=theta, layers=layers)


def build_baseline(layers: int = 12) -> "QuantumCircuit":
    """Unmanaged baseline (H init, π/4 RZ) — negative control."""
    _require_qiskit()
    qc = QuantumCircuit(2, 2)
    for _ in range(layers):
        qc.h(0)
        qc.h(1)
        qc.cx(0, 1)
        qc.rz(np.pi / 4, 0)
        qc.rz(np.pi / 4, 1)
        qc.cx(1, 0)
    qc.measure([0, 1], [0, 1])
    return qc


def build_with_relock(
    theta: float = THETA_STAR_HW,
    total_layers: int = 35,
    relock_interval: int = 7,
) -> "QuantumCircuit":
    """
    Deep QSD circuit with periodic re-preparation (Aurora sunscreen protocol).

    Stacks full QSD cells; between each block of `relock_interval` layers,
    re-initializes to basin center (validated ibm_fez: re-lock every 7 sustains ZZZ).
    """
    _require_qiskit()
    qc = QuantumCircuit(2, 2)
    layers_done = 0

    while layers_done < total_layers:
        if layers_done > 0:
            qc.ry(2.0 * theta, 0)
            qc.ry(2.0 * (np.pi / 2.0 - theta), 1)

        block = min(relock_interval, total_layers - layers_done)
        for _ in range(block):
            _append_qsd_cell(qc, theta)
        layers_done += block

    qc.measure([0, 1], [0, 1])
    return qc


def build_qsd_lattice(
    num_qubits: int,
    coupling_map: list[tuple[int, int]],
    theta: float = THETA_STAR_HW,
    depth: int = 12,
) -> "QuantumCircuit":
    """Multi-qubit QSD lattice with TriDelta phase initialization."""
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


def zzz_score(counts: dict[str, int]) -> float:
    """
    ZZZ parity proxy: fraction of |00⟩ and |11⟩ outcomes.

    Matches code/qsd_reference_implementation.py score() and ibm_fez ZZZ readout.
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return (counts.get("00", 0) + counts.get("11", 0)) / total


def parity_score(counts: dict[str, int]) -> float:
    """Alias for zzz_score."""
    return zzz_score(counts)
