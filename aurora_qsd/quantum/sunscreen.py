"""TriLock sunscreen protocol — periodic re-preparation at basin center."""

from __future__ import annotations

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_HW
from aurora_qsd.quantum.fez_cells import (
    _append_3q_qsd_layer,
    append_sunscreen_reset,
    build_zzz_cell_circuit,
)

try:
    from qiskit import QuantumCircuit
except ImportError:
    QuantumCircuit = None  # type: ignore[misc, assignment]


def build_sunscreen_circuit(
    theta: float = THETA_STAR_HW,
    total_layers: int = 1241,
    reset_interval: int = 8,
    n_qubits: int = 3,
) -> "QuantumCircuit":
    """
    Deep 3-qubit ZZZ circuit with ibm_fez sunscreen protocol.

    Inserts a single-layer TriLock re-preparation every `reset_interval` layers.
    Hardware validated: intervals 8–16; use 8 for default, 3 for aggressive Aurora.
    """
    if n_qubits == 3:
        return build_zzz_cell_circuit(
            theta=theta,
            depth=total_layers,
            relock_interval=reset_interval,
        )

    # 2-qubit fallback using fez_cells sunscreen via build_zzz path
    from aurora_qsd.quantum.circuit_builder import build_with_relock

    return build_with_relock(theta=theta, total_layers=total_layers, relock_interval=reset_interval)


def recommended_reset_interval(gamma_ratio: float) -> int:
    """Choose sunscreen interval from Aurora Γ_lock/Γ_loss ratio."""
    if gamma_ratio > 50_000:
        return 16
    if gamma_ratio > 10_000:
        return 8
    return 3
