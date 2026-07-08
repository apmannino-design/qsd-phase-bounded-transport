"""Tests for Casimir Hamiltonian module."""

import numpy as np
import pytest


def test_casimir_hamiltonian_ground_state() -> None:
    from aurora_qsd.quantum.casimir_hamiltonian import CasimirHamiltonian, exact_casimir_ground

    ham = CasimirHamiltonian(J_plate=1.0, J_cas=0.5, g_zzz=0.8, h_gap=0.1)
    gs = exact_casimir_ground(ham)
    H = ham.matrix()
    e0 = float(np.real(np.vdot(gs.psi, H @ gs.psi)))
    assert abs(gs.energy - e0) < 1e-10
    assert -1.0 <= gs.zzz <= 1.0
    assert -1.0 <= gs.zz02 <= 1.0 + 1e-9


def test_energy_from_counts() -> None:
    from aurora_qsd.quantum.casimir_hamiltonian import CasimirHamiltonian, energy_from_counts

    ham = CasimirHamiltonian(J_plate=1.0, J_cas=0.5, g_zzz=0.8, h_gap=0.0)
    counts = {"000": 100}
    obs = energy_from_counts(counts, ham)
    assert obs["zzz"] == pytest.approx(1.0, abs=0.01)
    assert obs["zz02"] == pytest.approx(1.0, abs=0.01)
    assert obs["energy"] < 0


def test_casimir_trotter_ops_build() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.casimir_hamiltonian import (
        CasimirHamiltonian,
        build_casimir_evolution_ops,
    )
    from aurora_qsd.quantum.willow_lines import get_line

    line = get_line("interior")
    ham = CasimirHamiltonian()
    ops = build_casimir_evolution_ops(line, ham, trotter_steps=3, dt=0.2, mode="bare")
    assert len(ops) > 0


def test_casimir_depth_benchmark_schema() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.casimir_hamiltonian import run_casimir_depth_benchmark

    result = run_casimir_depth_benchmark(shots=128, line_name="interior")
    assert result["task"] == "casimir_depth_binding"
    assert "abs_gap" in result
    assert result["verdict"] in {"QSD_WINS", "NULL"}
    assert result["line_role"] == "cavity_interior"
