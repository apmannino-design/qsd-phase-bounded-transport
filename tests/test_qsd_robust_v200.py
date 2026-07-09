"""Tests for QSD Robust Test Suite v2.0.0."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from aurora_qsd.core.constants import THETA_STAR_DEG
from aurora_qsd.quantum.robust_test_suite import (
    compute_ks_distance,
    compute_platform_independence_score,
    compute_relative_entropy_from_bloch,
    disorder_from_counts,
    fit_contraction_rate,
    load_prereg_v200,
    relative_entropy_vs_mixed_qiskit,
    run_robust_suite,
    run_t1_tomography,
    run_t2_basin_sweep,
    run_t3_reprep_robustness,
    run_t4_cross_platform,
)


def test_prereg_v200_loads() -> None:
    blob = load_prereg_v200()
    assert blob["protocol"] == "QSD_ROBUST_TEST_SUITE_v200"
    assert blob["parameters"]["theta_star_deg"] == 22.5
    assert blob["parameters"]["theta_wall_deg"] == 22.28


def test_bloch_entropy_limits() -> None:
    assert compute_relative_entropy_from_bloch(0.0) == 0.0
    assert compute_relative_entropy_from_bloch(1.0) == pytest.approx(math.log(2.0))


def test_fit_contraction_detects_decay() -> None:
    depths = [2, 4, 6, 8]
    entropies = [0.69, 0.43, 0.29, 0.14]
    rho_q, _, p_val = fit_contraction_rate(depths, entropies)
    assert rho_q is not None
    assert rho_q < 1.0
    assert p_val < 0.05


def test_ks_distance_separates_distributions() -> None:
    a = list(range(10))
    b = list(range(50, 60))
    assert compute_ks_distance(a, b) >= 0.9
    assert compute_ks_distance([1, 2, 3], [1, 2, 3]) == 0.0


def test_t1_noisy_tomography_runs() -> None:
    pytest.importorskip("qiskit")
    dec = run_t1_tomography(backend_name="aer_sim", depths=(2, 4, 6), noise="native", shots=512)
    assert dec.test == "T1"
    assert dec.decision in ("PASS", "FAIL")
    assert dec.details["mode"] == "aer_native"
    assert len(dec.details["relative_entropies"]) == 3


def test_t1_ideal_is_inconclusive() -> None:
    pytest.importorskip("qiskit")
    dec = run_t1_tomography(backend_name="aer_sim", depths=(2, 4, 6), noise="ideal")
    assert dec.decision == "INCONCLUSIVE"


def test_disorder_from_counts() -> None:
    counts = {"000": 500, "001": 500, "010": 500, "011": 500}
    d = disorder_from_counts(counts, n_qubits=3)
    assert d < math.log(8)


def test_t2_basin_sweep_runs() -> None:
    dec = run_t2_basin_sweep(n_steps=7, n_null=10, shots=128, depth=4)
    assert dec.test == "T2"
    assert "peak_angle_deg" in dec.details
    assert "contrast" in dec.details
    assert dec.details["ks_stat"] >= 0.0


def test_t3_reprep_simulation() -> None:
    dec = run_t3_reprep_robustness(max_layers=35, reset_intervals=(1, 7, 14))
    assert dec.test == "T3"
    assert dec.details["min_survival_fraction"] >= 0.0


def test_t4_platform_spread() -> None:
    dec = run_t4_cross_platform({"a": 22.0, "b": 22.5, "c": 23.0})
    assert dec.test == "T4"
    assert dec.details["max_spread_deg"] == pytest.approx(1.0)
    assert dec.decision == "PASS"


def test_t4_fails_wide_spread() -> None:
    dec = run_t4_cross_platform({"a": 10.0, "b": 30.0})
    assert dec.decision == "FAIL"


def test_full_suite_sim() -> None:
    pytest.importorskip("qiskit")
    report = run_robust_suite(backend_name="aer_sim")
    assert set(report.tests) == {"T1", "T2", "T3", "T4"}
    assert report.overall in ("ALL_PASS", "PARTIAL")
    assert report.endorsable is False


def test_cli_prereg_json_exists() -> None:
    p = Path("results/prereg_v200.json")
    assert p.is_file()
    data = json.loads(p.read_text())
    assert data["parameters"]["theta_star_deg"] == pytest.approx(THETA_STAR_DEG)
