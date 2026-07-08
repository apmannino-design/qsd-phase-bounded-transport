"""Tests for Willow Tridelta lattice submission protocol."""

from __future__ import annotations

import math

import numpy as np
import pytest

cirq = pytest.importorskip("cirq")
pytest.importorskip("cirq_google")

from aurora_qsd.quantum.willow_tridelta_lattice import (
    TRIDELTA_LOGICAL_EDGES,
    TrideltaLatticeConfig,
    build_tridelta_circuit,
    choose_willow_patch,
    couplings,
    delta_e_from_series,
    delta_e_from_shots,
    filter_edges_on_device,
    greedy_edge_layers,
    nearest_neighbor_correlator_per_shot,
)


def test_couplings_at_theta_star():
    jzz, jxx = couplings(22.49)
    assert abs(jzz - math.cos(math.radians(22.49))) < 1e-9
    assert abs(jxx - math.sin(math.radians(22.49))) < 1e-9


def test_greedy_layers_cover_edges():
    layers = greedy_edge_layers(TRIDELTA_LOGICAL_EDGES)
    flat = [e for layer in layers for e in layer]
    assert len(flat) == len(TRIDELTA_LOGICAL_EDGES)


def test_willow_patch_nine_qubits():
    from cirq_google import engine

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    patch = choose_willow_patch(proc.get_device())
    assert len(patch) == 9


def test_native_edges_subset():
    from cirq_google import engine

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    device = proc.get_device()
    patch = choose_willow_patch(device)
    edges = filter_edges_on_device(patch, TRIDELTA_LOGICAL_EDGES, device)
    assert len(edges) >= 12  # diagonals absent on Willow; horiz+vert remain


def test_circuit_builds():
    from cirq_google import engine

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    device = proc.get_device()
    patch = choose_willow_patch(device)
    edges = filter_edges_on_device(patch, TRIDELTA_LOGICAL_EDGES, device)
    cfg = TrideltaLatticeConfig(trotter_steps=4)
    c = build_tridelta_circuit(patch, edges, 22.49, cfg)
    assert len(c) > 0


def test_correlator_and_delta_e():
    arr = np.array([[0, 0, 0, 0, 0, 0, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1, 1, 1]])
    x = nearest_neighbor_correlator_per_shot(arr, [(0, 1), (1, 2)])
    assert x[0] == 1.0
    assert x[1] == 1.0  # all |1⟩ → Z eigenvalue −1, product (+1)
    assert delta_e_from_shots(x) >= 0.0
    assert delta_e_from_series(np.linspace(0.2, 0.8, 9)) >= 0.0
