"""Tests for ⟨ZZZ⟩ preservation retention scoring."""

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


def test_ideal_zzz_ground_state() -> None:
    pytest.importorskip("cirq")
    import cirq
    from aurora_qsd.quantum.zzz_preservation import ideal_zzz_from_circuit

    q0, q1, q2 = cirq.LineQubit.range(3)
    c = cirq.Circuit(cirq.X(q0), cirq.X(q1), cirq.X(q2))
    zzz = ideal_zzz_from_circuit(c)
    assert zzz == pytest.approx(-1.0, abs=1e-6)


def test_compute_retention_scenarios() -> None:
    from aurora_qsd.quantum.zzz_preservation import compute_retention

    # ideal ≈ −1, measured −0.30 → R ≈ 0.30
    r1 = compute_retention(-0.30, -1.0)
    assert r1["retention_signed"] == pytest.approx(0.30, abs=0.01)

    # ideal ≈ −0.30, measured −0.30 → R ≈ 1.0 (no protection)
    r2 = compute_retention(-0.30, -0.30)
    assert r2["retention_signed"] == pytest.approx(1.0, abs=0.01)

    # magnitude dead heat
    r3 = compute_retention(-0.30, -1.0)
    r4 = compute_retention(0.29, 1.0)
    assert abs(abs(r3["measured_zzz"]) - abs(r4["measured_zzz"])) == pytest.approx(0.01, abs=0.01)


def test_retention_analysis_flat_vs_peak() -> None:
    from aurora_qsd.quantum.zzz_preservation import _analyze_retention_curve

    flat = [{"theta_deg": t, "retention_signed": 0.3 + 0.01 * (i % 2)} for i, t in enumerate(range(10, 50, 5))]
    a_flat = _analyze_retention_curve(flat, 22.49, 0.29)
    assert a_flat["flat_curve"] is True

    peaked = [
        {"theta_deg": float(t), "retention_signed": 0.2 + (0.6 if abs(t - 22.0) < 3 else 0.0)}
        for t in range(10, 50, 5)
    ]
    a_peak = _analyze_retention_curve(peaked, 22.49, 0.29)
    assert a_peak["peak_near_theta_star"] or a_peak["r_peak"] > a_peak["r_median"]


def test_zzz_preservation_schema() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.zzz_preservation import run_zzz_preservation_benchmark

    result = run_zzz_preservation_benchmark(shots=128, sweep_shots=64, sweep_n_points=5)
    d = result.to_dict()
    assert "arms" in d
    assert "ideal_zzz" in d["arms"]["qsd_theta_star"]
    assert "retention_signed" in d["arms"]["xy4_matched"]
    assert d["verdict"] in {
        "PENDING_RETENTION",
        "WEAK_TARGET",
        "COHERENT_ARTIFACT",
        "ARM_GAP_ONLY",
        "RETENTION_WIN",
        "NULL",
    }
    assert d["preregistration"]["arm_gap_0_05"].startswith("NOT preregistered")
