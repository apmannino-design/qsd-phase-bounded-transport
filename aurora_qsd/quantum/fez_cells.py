"""IBM ibm_fez 3-qubit ZZZ cell protocol — topology mapping and true correlator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_HW

try:
    from qiskit import QuantumCircuit
except ImportError:
    QuantumCircuit = None  # type: ignore[misc, assignment]


@dataclass(frozen=True)
class ZZZCell:
    """A 3-qubit line cell mapped to hardware qubit indices."""

    qubits: tuple[int, int, int]
    cell_id: int


def _require_qiskit() -> None:
    if QuantumCircuit is None:
        raise ImportError("qiskit is required. Install with: pip install qiskit qiskit-aer")


def extract_zzz_triplets(
    coupling_map: list[tuple[int, int]],
    max_cells: int = 43,
) -> list[ZZZCell]:
    """
    Extract disjoint 3-qubit line triplets (a—b—c) from device coupling map.

    Matches ibm_fez 43-cell full-chip campaign geometry.
    """
    edges: set[tuple[int, int]] = set()
    for a, b in coupling_map:
        edges.add((min(a, b), max(a, b)))

    adj: dict[int, set[int]] = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    cells: list[ZZZCell] = []
    used: set[int] = set()

    for a, b in sorted(edges):
        for c in sorted(adj.get(b, ())):
            if c == a:
                continue
            triplet = tuple(sorted((a, b, c)))
            # prefer line a-b-c
            line = (a, b, c) if (a, b) in edges and (b, c) in edges else None
            if line is None:
                line = (a, b, c) if (b, c) in edges or (c, b) in edges else None
            if line is None:
                continue
            q0, q1, q2 = line
            if q0 in used or q1 in used or q2 in used:
                continue
            cells.append(ZZZCell(qubits=(q0, q1, q2), cell_id=len(cells)))
            used.update(line)
            if len(cells) >= max_cells:
                return cells

    return cells


def zzz_correlator(counts: dict[str, int], n_qubits: int = 3) -> float:
    """
    True ZZZ correlator ⟨Z⊗Z⊗Z⟩ from measurement counts.

    For n_qubits=3: ⟨Z⊗Z⊗Z⟩ = Σ (-1)^(popcount) · P(bitstring)
    For n_qubits=2: falls back to ⟨Z⊗Z⟩ = P(00) + P(11) - P(01) - P(10)
    """
    total = sum(counts.values())
    if total == 0:
        return 0.0

    if n_qubits == 2:
        p00 = counts.get("00", 0) / total
        p01 = counts.get("01", 0) / total
        p10 = counts.get("10", 0) / total
        p11 = counts.get("11", 0) / total
        return float(p00 + p11 - p01 - p10)

    acc = 0.0
    for bitstring, count in counts.items():
        parity = bitstring.count("1")
        sign = 1.0 if parity % 2 == 0 else -1.0
        acc += sign * count
    return float(acc / total)


def _trilock_init(qc: "QuantumCircuit", qubits: tuple[int, ...], theta: float) -> None:
    """TriDelta phase initialization at basin angle θ."""
    for i, q in enumerate(qubits):
        angle = 2.0 * theta if i % 2 == 0 else 2.0 * (np.pi / 2.0 - theta)
        qc.ry(angle, q)


def _append_2q_qsd_layer(
    qc: "QuantumCircuit",
    q0: int,
    q1: int,
    theta: float,
    with_init: bool = True,
) -> None:
    """Core 2-qubit QSD layer (reference-validated)."""
    if with_init:
        qc.ry(2.0 * theta, q0)
        qc.ry(2.0 * (np.pi / 2.0 - theta), q1)
    qc.cx(q0, q1)
    qc.rz(theta, q0)
    qc.rz(np.pi / 2.0 - theta, q1)
    qc.cx(q1, q0)


def _append_3q_qsd_layer(
    qc: "QuantumCircuit",
    qubits: tuple[int, int, int],
    theta: float,
    with_init: bool = True,
) -> None:
    """
    3-qubit ZZZ cell layer: TriLock init + QSD on (q0,q1) + phase bridge to q2.

    Propagates phase lock along the line for ZZZ readout on all three qubits.
    """
    q0, q1, q2 = qubits
    if with_init:
        _trilock_init(qc, qubits, theta)

    _append_2q_qsd_layer(qc, q0, q1, theta, with_init=False)
    qc.cx(q1, q2)
    qc.rz(theta if q2 % 2 == 0 else np.pi / 2.0 - theta, q2)
    qc.cx(q1, q2)


def append_sunscreen_reset(
    qc: "QuantumCircuit",
    qubits: tuple[int, ...],
    theta: float,
) -> None:
    """
    Single-layer TriLock re-preparation (ibm_fez sunscreen protocol).

    One full QSD layer at basin center — not a partial RY-only reset.
    """
    if len(qubits) == 2:
        _append_2q_qsd_layer(qc, qubits[0], qubits[1], theta, with_init=True)
    elif len(qubits) >= 3:
        _append_3q_qsd_layer(qc, (qubits[0], qubits[1], qubits[2]), theta, with_init=True)


def build_zzz_cell_circuit(
    qubits: tuple[int, int, int] | None = None,
    theta: float = THETA_STAR_HW,
    depth: int = 12,
    relock_interval: int | None = None,
) -> "QuantumCircuit":
    """
    Build a 3-qubit ZZZ correlation cell circuit on logical qubits (0,1,2).

    If `qubits` is provided, it's metadata only — circuit uses local indices 0,1,2
  for simulation; transpilation maps to hardware indices separately.
    """
    _require_qiskit()
    logical = (0, 1, 2)
    qc = QuantumCircuit(3, 3)

    if relock_interval is None:
        for layer in range(depth):
            _append_3q_qsd_layer(qc, logical, theta, with_init=(layer == 0))
    else:
        layers_done = 0
        while layers_done < depth:
            if layers_done > 0:
                append_sunscreen_reset(qc, logical, theta)
            block = min(relock_interval, depth - layers_done)
            for j in range(block):
                _append_3q_qsd_layer(qc, logical, theta, with_init=(layers_done == 0 and j == 0))
            layers_done += block

    qc.measure([0, 1, 2], [0, 1, 2])
    return qc


def build_zzz_baseline_circuit(depth: int = 12) -> "QuantumCircuit":
    """Negative-control-style baseline on 3 qubits (H init, no QSD lock)."""
    _require_qiskit()
    qc = QuantumCircuit(3, 3)
    for _ in range(depth):
        for q in range(3):
            qc.h(q)
        qc.cx(0, 1)
        qc.cx(1, 2)
        qc.rz(np.pi / 4, 0)
        qc.rz(np.pi / 4, 1)
        qc.rz(np.pi / 4, 2)
        qc.cx(1, 2)
        qc.cx(0, 1)
    qc.measure([0, 1, 2], [0, 1, 2])
    return qc


def negative_control_angle(theta: float = THETA_STAR_HW, offset_deg: float = 70.0) -> float:
    """Off-basin angle for negative control (hardware: THETA_SRC + 70°)."""
    return float(theta + np.radians(offset_deg))
