"""Tests for correct Willow interior-line run."""

import pytest


def test_willow_correct_run_schema() -> None:
    pytest.importorskip("cirq")
    cirq_google = pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.willow_run import run_willow_correct

    result = run_willow_correct(
        shots=256,
        line_name="interior",
        compare_boundary=False,
        depth_layers=8,
    )
    d = result.to_dict()
    assert d["line"] == "interior"
    assert d["line_coords"] == ["q(6,5)", "q(6,6)", "q(6,7)"]
    assert "echo_qsd" in d["echo"]
    assert "qsd_theta_star" in d["depth"]
    assert d["verdict"] in {"QSD_WIN", "ECHO_WIN", "DEPTH_WIN", "NULL"}


def test_interior_line_on_device() -> None:
    pytest.importorskip("cirq")
    from cirq_google import engine
    from aurora_qsd.quantum.willow_lines import get_line, validate_on_device

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor("willow_pink")
    line = get_line("interior")
    assert validate_on_device(line, proc.get_device())
