"""Tests for chip stability controller."""

import pytest


def test_chip_stability_schema() -> None:
    pytest.importorskip("cirq")
    cirq_google = pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.chip_stability import run_chip_stability

    result = run_chip_stability(shots=128, max_cells=2, theta_star_deg=22.49)
    d = result.to_dict()
    assert d["n_cells"] == 2
    assert d["n_qubits"] == 6
    assert len(d["cells"]) == 2
    assert "ae_median_deg" in d["aggregate"]
    assert "sigma_median" in d["aggregate"]
    assert d["verdict"] in {"CHIP_STABLE", "PARTIAL_STABLE", "NULL"}


def test_controller_adapts_relock() -> None:
    from aurora_qsd.quantum.chip_stability import ChipStabilityController

    ctrl = ChipStabilityController(base_relock=5, min_relock=2, max_relock=8)
    assert ctrl._adapt_relock(0, in_band=True) == 6
    assert ctrl._adapt_relock(0, in_band=True) == 7
    assert ctrl._adapt_relock(0, in_band=False) == 6
