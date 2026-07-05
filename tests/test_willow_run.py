"""Tests for correct Willow interior-line run."""

import pytest

import cirq


def test_sunscreen_body_init_once_per_block() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.willow_lines import get_line
    from aurora_qsd.quantum.willow_run import build_depth_sunscreen_circuit

    line = get_line("interior")
    c = build_depth_sunscreen_circuit(line, layers=6, relock_interval=3)
    ry_ops = [op for op in c.all_operations() if isinstance(op.gate, cirq.Ry)]
    # first layer init (3 RY) + one relock reset at layer 3 (3 RY) = 6
    assert len(ry_ops) == 6


def test_willow_correct_run_schema() -> None:
    pytest.importorskip("cirq")
    cirq_google = pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.willow_run import run_willow_correct

    result = run_willow_correct(
        shots=256,
        line_name="interior",
        compare_boundary=False,
        depth_layers=8,
        relock_interval=3,
    )
    d = result.to_dict()
    assert d["line"] == "interior"
    assert d["line_coords"] == ["q(6,5)", "q(6,6)", "q(6,7)"]
    assert d["theta_star_deg"] == 22.48
    assert "echo_qsd" in d["echo"]
    assert "qsd_theta_star" in d["depth"]
    assert "depth_gap" in d
    assert d["verdict"] in {"QSD_WIN", "ECHO_WIN", "DEPTH_WIN", "NULL"}


def test_interior_line_on_device() -> None:
    pytest.importorskip("cirq")
    from cirq_google import engine
    from aurora_qsd.quantum.willow_lines import get_line, validate_on_device

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    line = get_line("interior")
    assert validate_on_device(line, proc.get_device())
