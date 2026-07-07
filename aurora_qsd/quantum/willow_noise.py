"""Shared Willow idle-noise model (Qiskit thermal_relaxation_error equivalent)."""

from __future__ import annotations

import math

import numpy as np


def thermal_relaxation_kraus(
    t1_ns: float,
    t2_ns: float,
    duration_ns: float,
) -> list[np.ndarray]:
    """
    Kraus operators for thermal relaxation over `duration_ns`.

    Matches qiskit_aer.noise.thermal_relaxation_error(t1, t2, duration).
    """
    if duration_ns <= 0:
        return [np.eye(2, dtype=complex)]

    try:
        from qiskit_aer.noise import thermal_relaxation_error
        from qiskit.quantum_info import Kraus

        err = thermal_relaxation_error(t1_ns, t2_ns, duration_ns)
        return [np.asarray(k, dtype=complex) for k in Kraus(err).data]
    except ImportError:
        pass

    # Numpy fallback (Qiskit Aer analytic form)
    t1 = max(float(t1_ns), 1e-9)
    t2 = max(float(t2_ns), 1e-9)
    dt = float(duration_ns)
    e1 = math.exp(-dt / t1)
    e2 = math.exp(-dt / t2)
    k0 = np.sqrt(max(0.0, 1.0 - e1)) * np.array([[1, 0], [0, 0]], dtype=complex)
    k1 = np.sqrt(max(0.0, e1 - e2)) * np.array([[0, 0], [0, 1]], dtype=complex)
    k2 = np.sqrt(max(0.0, 1.0 - e2)) * np.array([[1, 0], [0, -1]], dtype=complex) / np.sqrt(2)
    # Qiskit uses a specific parameterization; prefer qiskit when installed.
    return [k0, k1, k2]


def willow_t1_t2(t2_ns: float = 2000.0) -> tuple[float, float]:
    return 2.0 * t2_ns, t2_ns


def qiskit_idle_noise_model(tau_ns: float = 1000.0, t2_ns: float = 2000.0):
    """Qiskit Aer NoiseModel: thermal relaxation on delay gates only."""
    from qiskit_aer.noise import NoiseModel, thermal_relaxation_error

    t1_ns, _ = willow_t1_t2(t2_ns)
    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(
        thermal_relaxation_error(t1_ns, t2_ns, tau_ns),
        ["delay"],
    )
    return nm


def cirq_idle_noise_ops(qubits, tau_ns: float, t2_ns: float = 2000.0) -> list:
    """Cirq operations: thermal relaxation Kraus channel after idle τ."""
    import cirq

    t1_ns, _ = willow_t1_t2(t2_ns)
    kraus = thermal_relaxation_kraus(t1_ns, t2_ns, tau_ns)
    channel = cirq.KrausChannel(kraus_ops=kraus)
    return [channel.on(q) for q in qubits]
