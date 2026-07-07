"""Tests for Willow entanglement stress G(El) protocol."""

import pytest


def test_p_fail_majority_one() -> None:
    from aurora_qsd.quantum.willow_entanglement_stress import p_fail_majority_one

    counts = {"000": 700, "111": 300}
    assert p_fail_majority_one(counts, n_qubits=3) == pytest.approx(0.3)

    counts = {"001": 500, "010": 500}
    assert p_fail_majority_one(counts, n_qubits=3) == pytest.approx(0.0)


def test_entanglement_stress_circuit_structure() -> None:
    pytest.importorskip("cirq")
    import cirq

    from aurora_qsd.quantum.willow_entanglement_stress import build_entanglement_stress_circuit
    from aurora_qsd.quantum.willow_lines import get_line

    line = get_line("interior")
    theta = 0.3925

    for arm in ("qsd", "wrong", "bare"):
        c = build_entanglement_stress_circuit(line, entanglement_layers=2, theta=theta, arm=arm)
        assert any(isinstance(op.gate, cirq.MeasurementGate) for op in c.all_operations())
        if arm == "bare":
            h_ops = [op for op in c.all_operations() if op.gate == cirq.H]
            assert len(h_ops) >= 3


def test_entanglement_stress_run_schema() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")

    from aurora_qsd.quantum.willow_entanglement_stress import run_entanglement_stress

    result = run_entanglement_stress(shots=256, el_schedule=[0, 1], line_name="interior")
    d = result.to_dict()
    assert d["line"] == ["q(6,5)", "q(6,6)", "q(6,7)"]
    assert d["theta_star_deg"] == 22.49
    assert len(d["points"]) == 2
    assert d["verdict"] in {"ENTANGLEMENT_SUPPRESSES", "PARTIAL_G", "NULL"}
    for pt in d["points"]:
        assert "g_qsd_vs_bare" in pt
        assert pt["shots"] == 256
