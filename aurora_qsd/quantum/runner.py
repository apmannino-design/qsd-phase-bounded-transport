"""Circuit execution helper (avoids circular imports)."""

from __future__ import annotations

from qiskit import transpile
from qiskit_aer import AerSimulator

from aurora_qsd.core.constants import DEFAULT_SHOTS
from aurora_qsd.quantum.noise_models import build_simulator


def run_circuit(
    qc,
    sim: AerSimulator | None = None,
    shots: int = DEFAULT_SHOTS,
    noise: str = "native",
) -> dict[str, int]:
    sim = sim or build_simulator(noise)
    compiled = transpile(qc, sim, optimization_level=0)
    return sim.run(compiled, shots=shots).result().get_counts()
