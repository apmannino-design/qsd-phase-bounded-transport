"""Tests for IBM Qiskit retention audit."""

import math

import pytest


def test_xy4_layer_not_degenerate() -> None:
    pytest.importorskip("qiskit")
    from aurora_qsd.quantum.ibm_retention_audit import verify_xy4_layer_qiskit

    check = verify_xy4_layer_qiskit((0, 1, 2))
    assert check["passes"]
    assert not check["degenerate_IIIY"]


def test_qsd_circuit_gate_budget() -> None:
    pytest.importorskip("qiskit")
    from aurora_qsd.quantum.ibm_retention_audit import gate_budget_metadata

    gb = gate_budget_metadata(22.5, layers=14, relock=5)
    assert gb["qsd_body_per_layer"]["two_qubit"] == 4
    assert gb["xy4_body_per_layer"]["one_qubit"] == 12
    assert gb["xy4_layer_check"]["passes"]


def test_verify_xy4_safe_for_sparse_physical_indices() -> None:
    pytest.importorskip("qiskit")
    from aurora_qsd.quantum.ibm_retention_audit import verify_xy4_layer_qiskit

    check = verify_xy4_layer_qiskit((20, 21, 36))
    assert check["passes"]
    assert check["requested_physical_qubits"] == [20, 21, 36]


def test_ideal_zzz_paths_agree() -> None:
    pytest.importorskip("qiskit")
    from aurora_qsd.quantum.ibm_retention_audit import build_qsd_sunscreen_circuit, ideal_zzz_qiskit

    c = build_qsd_sunscreen_circuit((0, 1, 2), 22.5, layers=2, relock_interval=5, measure=False)
    ideal = ideal_zzz_qiskit(c)
    assert ideal["ideal_paths_agree"]
    assert math.isfinite(ideal["ideal_zzz"])


def test_ibm_retention_ideals_only() -> None:
    pytest.importorskip("qiskit")
    from aurora_qsd.quantum.ibm_retention_audit import run_ibm_retention_benchmark

    result = run_ibm_retention_benchmark(
        backend_name="aer_sim",
        qubits=(0, 1, 2),
        shots=512,
        sweep_shots=256,
        run_sweep=False,
        ideals_only=True,
    )
    d = result.to_dict()
    assert d["task"] == "qsd_ibm_retention_audit"
    assert "qsd_theta_star" in d["arms"]
    assert d["arms"]["qsd_theta_star"]["measured_zzz"] is None
    assert d["verdict"] in {
        "NO_TARGET_SIGNAL",
        "COHERENT_ARTIFACT",
        "NO_PROTECTION_ADVANTAGE",
        "PROTECTION_CANDIDATE",
        "PENDING_RETENTION",
    }
