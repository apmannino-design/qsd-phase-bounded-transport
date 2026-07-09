"""Tests for entanglement θ sweep 22.5°–90°."""

import pytest

from aurora_qsd.core.constants import BASIN_BOUNDARY_DEG, THETA_STAR_DEG
from aurora_qsd.quantum.entanglement_theta_sweep import (
    DEFAULT_THETA_SWEEP_DEG,
    _build_ibm_3q_entangle_circuit,
    generate_theta_sweep_deg,
    run_ibm_entanglement_theta_sweep,
)


def test_default_theta_corridor() -> None:
    assert DEFAULT_THETA_SWEEP_DEG[0] == pytest.approx(22.5)
    assert BASIN_BOUNDARY_DEG in DEFAULT_THETA_SWEEP_DEG
    assert 90.0 in DEFAULT_THETA_SWEEP_DEG


def test_generate_theta_sweep() -> None:
    pts = generate_theta_sweep_deg(22.5, 90.0, 5)
    assert len(pts) == 5
    assert pts[0] == pytest.approx(22.5)
    assert pts[-1] == pytest.approx(90.0)


def test_ibm_entangle_circuit_builds() -> None:
    pytest.importorskip("qiskit")
    c = _build_ibm_3q_entangle_circuit(22.5, el=2, arm="qsd")
    assert c.num_qubits == 3
    assert c.num_clbits == 3


def test_ibm_aer_theta_sweep_runs() -> None:
    pytest.importorskip("qiskit")
    result = run_ibm_entanglement_theta_sweep(
        shots=256,
        el=1,
        thetas_deg=[22.5, 45.0, 90.0],
        backend_name="aer_fez",
        noise="native",
    )
    assert len(result.points) == 3
    assert result.verdict in ("ENTANGLEMENT_ANGLE_WIN", "PARTIAL_ANGLE", "NULL")
    assert result.theta_sweep_deg[0] == 22.5
