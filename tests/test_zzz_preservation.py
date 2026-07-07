"""Tests for ⟨ZZZ⟩ preservation vs matched-depth XY4 control."""

import numpy as np
import pytest


def test_xy4_body_matches_qsd_1q_budget() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.willow_lines import get_line
    from aurora_qsd.quantum.zzz_preservation import _count_gates, _xy4_body_ops
    from aurora_qsd.quantum.willow_run import _sunscreen_body_ops

    line = get_line("interior")
    qubits = list(line.qubits())
    theta = float(np.radians(22.49))
    qsd = _count_gates(_sunscreen_body_ops(qubits, theta, with_init=False))
    xy4 = _count_gates(_xy4_body_ops(qubits))
    assert xy4["one_qubit"] == qsd["one_qubit"]


def test_xy4_circuit_builds() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.willow_lines import get_line
    from aurora_qsd.quantum.zzz_preservation import build_xy4_matched_circuit

    line = get_line("interior")
    c = build_xy4_matched_circuit(line, theta=float(np.radians(22.49)), layers=14, relock_interval=5)
    assert len(c) > 0


def test_gate_budget_metadata() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.willow_lines import get_line
    from aurora_qsd.quantum.zzz_preservation import _gate_budget_metadata

    line = get_line("interior")
    meta = _gate_budget_metadata(line, float(np.radians(22.49)), layers=14, relock=5)
    assert meta["matched_1q_per_body_layer"] is True
    assert meta["qsd_total"]["two_qubit"] > meta["xy4_total"]["two_qubit"]


def test_zzz_preservation_schema() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.zzz_preservation import run_zzz_preservation_benchmark

    result = run_zzz_preservation_benchmark(shots=256, gap_threshold=0.05)
    d = result.to_dict()
    assert d["task"] == "zzz_preservation_xy4_control"
    assert "xy4_matched" in d
    assert "gaps" in d
    assert d["verdict"] in {"ENDORSABLE", "SURVIVES_XY4", "ANGLE_ONLY", "NULL"}
    assert "angle_specific_abs" in d["gaps"]
