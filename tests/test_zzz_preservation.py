"""Tests for ⟨ZZZ⟩ preservation retention scoring (repaired XY4)."""

import numpy as np
import pytest


def test_xy4_is_twelve_pulse_dd() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.zzz_preservation import _xy4_body_ops, verify_xy4_layer

    check = verify_xy4_layer()
    assert check["is_twelve_pulse_xy4"]
    assert check["passes"]
    assert not check["degenerate_IIIY"]
    assert len(_xy4_body_ops(list(__import__("cirq").LineQubit.range(3)))) == 12


def test_xy4_not_matched_1q_to_qsd() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.willow_lines import get_line
    from aurora_qsd.quantum.zzz_preservation import _count_gates, _xy4_body_ops
    from aurora_qsd.quantum.willow_run import _sunscreen_body_ops

    line = get_line("interior")
    qubits = list(line.qubits())
    theta = float(np.radians(22.49))
    qsd = _count_gates(_sunscreen_body_ops(qubits, theta, with_init=False))
    xy4 = _count_gates(_xy4_body_ops(qubits))
    assert xy4["one_qubit"] == 12
    assert qsd["one_qubit"] == 11


def test_ideal_zzz_dual_paths_agree() -> None:
    pytest.importorskip("cirq")
    import cirq
    from aurora_qsd.quantum.zzz_preservation import ideal_zzz_density_matrix, ideal_zzz_from_circuit

    q0, q1, q2 = cirq.LineQubit.range(3)
    c = cirq.Circuit(cirq.X(q0), cirq.X(q1), cirq.X(q2))
    sv = ideal_zzz_from_circuit(c)
    dm = ideal_zzz_density_matrix(c)
    assert sv == pytest.approx(dm, abs=1e-5)
    assert sv == pytest.approx(-1.0, abs=1e-6)


def test_compute_retention_scenarios() -> None:
    from aurora_qsd.quantum.zzz_preservation import compute_retention

    r1 = compute_retention(-0.30, -1.0)
    assert r1["retention_signed"] == pytest.approx(0.30, abs=0.01)

    r2 = compute_retention(-0.30, -0.30)
    assert r2["retention_signed"] == pytest.approx(1.0, abs=0.01)


def test_verdict_coherent_artifact() -> None:
    from aurora_qsd.quantum.zzz_preservation import assign_retention_verdict

    arms = {
        "qsd_theta_star": {"ideal_zzz": -0.19, "measured_zzz": -0.31, "retention_signed": 1.6},
        "qsd_wrong_theta": {"ideal_zzz": 0.98, "measured_zzz": 0.51, "retention_signed": 0.52},
        "xy4_matched": {"ideal_zzz": 0.35, "measured_zzz": 0.29, "retention_signed": 0.83},
    }
    gaps = {
        "magnitude_qsd_vs_xy4_delta": 0.01,
        "ideal_angle_gap": 1.17,
        "noisy_angle_gap": 0.82,
    }
    v, e, _ = assign_retention_verdict(arms, gaps, {})
    assert v == "NO_TARGET_SIGNAL"  # |ideal*| < 0.5 first

    arms["qsd_theta_star"]["ideal_zzz"] = -0.6
    v2, _, _ = assign_retention_verdict(arms, gaps, {})
    assert v2 == "COHERENT_ARTIFACT"


def test_zzz_preservation_schema() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.zzz_preservation import run_zzz_preservation_benchmark

    result = run_zzz_preservation_benchmark(
        shots=0, sweep_shots=0, run_theta_sweep=False, ideals_only=True,
    )
    d = result.to_dict()
    assert d["gate_budget"]["xy4_layer_check"]["passes"]
    assert d["verdict"] in {
        "NO_TARGET_SIGNAL",
        "COHERENT_ARTIFACT",
        "NO_PROTECTION_ADVANTAGE",
        "PROTECTION_CANDIDATE",
        "PENDING_RETENTION",
    }
    assert d["endorsable"] is False
