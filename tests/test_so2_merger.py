"""Tests for SO(2) merger sweep and Willow θ comparison."""

from __future__ import annotations

import math

import numpy as np
import pytest

from aurora_qsd.core.constants import (
    MERGER_PARTITION_THETA_DEG,
    MERGER_PROJECTOR_ALPHA_DEG,
    MERGER_STRUCTURAL_RATIO_LX,
)
from aurora_qsd.core.so2_projector import (
    decompose_with_projector_rotation,
    merger_reference_invariants,
    run_so2_projector_sweep,
    run_so2_sweep_from_invariants,
    synthesis_sigma_for_merger_targets,
)


def test_synthesis_sigma_hits_merger_targets():
    delta_j, delta_l0, delta_x0 = merger_reference_invariants()
    result = run_so2_sweep_from_invariants(delta_j, delta_l0, delta_x0, n_points=3601)
    assert result.verdict == "MERGER_LOCK"
    assert abs(result.optimal_alpha_deg - MERGER_PROJECTOR_ALPHA_DEG) < 0.1
    assert abs(result.optimal_ratio_lx - MERGER_STRUCTURAL_RATIO_LX) < 0.01
    assert abs(result.optimal_theta_deg - MERGER_PARTITION_THETA_DEG) < 0.1


def test_sigma_path_sweep_runs():
    sigma = synthesis_sigma_for_merger_targets()
    result = run_so2_projector_sweep(sigma, n_points=181)
    assert result.verdict in {"MERGER_LOCK", "RATIO_LOCK", "NO_LOCK"}


def test_rotation_preserves_lx_radius():
    sigma = synthesis_sigma_for_merger_targets()
    td0 = decompose_with_projector_rotation(sigma, 0.0)
    td1 = decompose_with_projector_rotation(sigma, math.radians(30.0))
    r0 = math.hypot(td0.delta_l, td0.delta_x)
    r1 = math.hypot(td1.delta_l, td1.delta_x)
    assert abs(r0 - r1) < 1e-9


def test_merger_ratio_is_tan_65_53():
    assert abs(MERGER_STRUCTURAL_RATIO_LX - math.tan(math.radians(65.53))) < 0.001


@pytest.mark.slow
def test_theta_compare_smoke():
    cirq = pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from aurora_qsd.quantum.willow_theta_compare import run_theta_head_to_head

  # One cell worth of shots — smoke only
    result = run_theta_head_to_head(
        shots_interior=128,
        shots_cells=64,
        thetas=[(22.49, "platform"), (27.61, "merger")],
    )
    assert len(result.arms) == 2
    assert result.verdict in {"THETA_WIN", "MARGINAL", "TIE", "NULL"}
