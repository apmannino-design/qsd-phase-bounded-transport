"""Noise models: native FakeFez first, mild stress optional, apocalypse for torture tests."""

from __future__ import annotations

from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    amplitude_damping_error,
    depolarizing_error,
    phase_damping_error,
)


def build_native_fez_noise_model() -> NoiseModel:
    """FakeFez backend noise only — hardware-faithful baseline."""
    from qiskit_ibm_runtime.fake_provider import FakeFez

    return NoiseModel.from_backend(FakeFez())


def build_mild_stress_noise_model(
    t1_scale: float = 0.08,
    t2_scale: float = 0.10,
    dp1: float = 0.03,
    dp2: float = 0.06,
) -> NoiseModel:
    """
    Native FakeFez + mild perturbation (not apocalypse).

    Use after native baseline passes; tune upward for stress sensitivity.
    """
    nm = build_native_fez_noise_model()
    t1 = amplitude_damping_error(t1_scale)
    t2 = phase_damping_error(t2_scale)
    sq = depolarizing_error(dp1, 1).compose(t1).compose(t2)
    gates_1q = ["ry", "rx", "rz", "h", "x", "sx", "id"]
    nm.add_all_qubit_quantum_error(sq, gates_1q)
    nm.add_all_qubit_quantum_error(depolarizing_error(dp2, 2), ["cx", "ecr", "cz"])
    return nm


def build_apocalypse_noise_model(
    t1: float = 0.35,
    t2: float = 0.45,
    dp1: float = 0.30,
    dp2: float = 0.55,
) -> NoiseModel:
    """FakeFez + heavy stacked decoherence (torture test only)."""
    nm = build_native_fez_noise_model()
    t1e = amplitude_damping_error(t1)
    t2e = phase_damping_error(t2)
    sq = depolarizing_error(dp1, 1).compose(t1e).compose(t2e)
    gates_1q = ["u1", "u2", "u3", "ry", "rx", "rz", "h", "x", "sx", "id"]
    nm.add_all_qubit_quantum_error(sq, gates_1q)
    nm.add_all_qubit_quantum_error(depolarizing_error(dp2, 2), ["cx", "ecr", "cz"])
    return nm


def build_simulator(noise: str = "native") -> AerSimulator:
    """
    Build Aer simulator with named noise profile.

    noise: 'native' | 'mild' | 'apocalypse' | 'ideal'
    """
    if noise == "ideal":
        return AerSimulator()
    if noise == "native":
        return AerSimulator(noise_model=build_native_fez_noise_model())
    if noise == "mild":
        return AerSimulator(noise_model=build_mild_stress_noise_model())
    if noise == "apocalypse":
        return AerSimulator(noise_model=build_apocalypse_noise_model())
    raise ValueError(f"Unknown noise profile: {noise!r}")
