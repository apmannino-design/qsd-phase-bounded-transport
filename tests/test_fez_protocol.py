"""Tests for hardware-faithful fez protocol (improvements 1–4)."""

import numpy as np

from aurora_qsd.quantum.fez_cells import (
    extract_zzz_triplets,
    zzz_correlator,
    negative_control_angle,
    build_zzz_cell_circuit,
)
from aurora_qsd.quantum.basin_sweep import run_basin_sweep
from aurora_qsd.agent.qsd_agent import QSDAuroraAgent


def test_3q_correlator_zeros():
    assert zzz_correlator({"000": 100}, 3) == 1.0


def test_3q_correlator_ones():
    assert zzz_correlator({"111": 100}, 3) == -1.0


def test_extract_triplets():
    cm = [(0, 1), (1, 2), (3, 4), (4, 5)]
    cells = extract_zzz_triplets(cm, max_cells=2)
    assert len(cells) == 2


def test_build_3q_cell():
    qc = build_zzz_cell_circuit(depth=4, relock_interval=2)
    assert qc.num_qubits == 3


def test_basin_sweep_ideal():
    r = run_basin_sweep(shots=512, depth=4, noise="ideal", n_points=5)
    assert r.optimal_zzz >= 0
    assert len(r.sweep_points) == 5


def test_agent_basin_intent():
    agent = QSDAuroraAgent()
    resp = agent.run_basin_sweep(shots=512, depth=4, noise="ideal")
    assert resp.intent == "optimize"
