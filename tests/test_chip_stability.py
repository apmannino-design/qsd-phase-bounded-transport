"""Tests for chip stability controller."""

import numpy as np
import pytest


def test_covariance_from_3q_counts() -> None:
    from aurora_qsd.quantum.analyzer import covariance_from_counts

    # |000⟩ and |111⟩ equal weight → ⟨Zi⟩=0, ⟨ZiZj⟩=1
    counts = {"000": 50, "111": 50}
    cov = covariance_from_counts(counts, n_qubits=3)
    assert cov.shape == (3, 3)
    assert np.allclose(np.diag(cov), 1.0, atol=0.01)
    assert np.allclose(cov[0, 1], 1.0, atol=0.01)

    # |010⟩ only → Z1 = -1, others +1
    counts2 = {"010": 100}
    cov2 = covariance_from_counts(counts2, n_qubits=3)
    assert cov2[1, 1] < 0.1


def test_chip_stability_schema() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.chip_stability import run_chip_stability

    result = run_chip_stability(
        shots=128,
        max_cells=2,
        theta_star_deg=22.49,
        calibrate_theta=False,
        run_task_benchmark=False,
    )
    d = result.to_dict()
    assert d["n_cells"] == 2
    assert d["n_qubits"] == 6
    assert len(d["cells"]) == 2
    assert "ae_median_deg" in d["aggregate"]
    assert "sigma_median" in d["aggregate"]
    assert "cells_tri_band" in d["aggregate"]
    assert "cells_zzz_band" in d["aggregate"]
    assert d["verdict"] in {"CHIP_STABLE", "PARTIAL_STABLE", "ERROR_LIMITED", "NULL"}
    for cell in d["cells"]:
        assert "tri_band" in cell
        assert "zzz_band" in cell
        assert "task_energy_error" in cell


def test_controller_adapts_relock() -> None:
    from aurora_qsd.quantum.chip_stability import ChipStabilityController

    ctrl = ChipStabilityController(base_relock=5, min_relock=2, max_relock=8)
    assert ctrl._adapt_relock(0, in_band=True) == 6
    assert ctrl._adapt_relock(0, in_band=True) == 7
    assert ctrl._adapt_relock(0, in_band=False) == 6


def test_finetune_ae_sigma_schema() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.chip_stability import run_chip_stability

    result = run_chip_stability(
        shots=128,
        max_cells=1,
        theta_star_deg=22.49,
        calibrate_shots=64,
        finetune_ae_sigma=True,
        run_task_benchmark=False,
    )
    d = result.to_dict()
    assert "cells_ae_sigma_locked" in d["aggregate"]
    assert d["verdict"] in {"CHIP_STABLE", "PARTIAL_STABLE", "ERROR_LIMITED", "NULL"}


def test_dual_band_logic() -> None:
    from aurora_qsd.quantum.chip_stability import ChipStabilityController

    ctrl = ChipStabilityController(ae_tol_deg=3.0, zzz_gap_tol=0.05, zzz_ae_tol_deg=20.0)
    counts = {"000": 40, "111": 40, "001": 10, "110": 10}
    out = ctrl._monitor_cell(counts, abs_gap=0.6)
    assert len(out) == 7
    ae, sigma, theta, heron, in_band, tri, zzz = out
    assert isinstance(in_band, bool)
    assert isinstance(tri, bool)
    assert isinstance(zzz, bool)
    # Large gap + small Ae should satisfy ZZZ-native band
    out2 = ctrl._monitor_cell(counts, abs_gap=0.8)
    _, _, _, _, in2, _, zzz2 = out2
    if abs(ae) <= 20.0:
        assert zzz2
        assert in2
