"""Tests for Willow cascade entanglement protocol."""

import math

import pytest


def test_shannon_entropy() -> None:
    from aurora_qsd.quantum.willow_cascade_entanglement import shannon_entropy_bits

    assert shannon_entropy_bits({"000": 1000}) == pytest.approx(0.0)
    assert shannon_entropy_bits({"000": 500, "111": 500}) == pytest.approx(1.0)


def test_find_cascade_bridges() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from cirq_google import engine

    from aurora_qsd.quantum.willow_cascade_entanglement import find_cascade_bridges
    from aurora_qsd.quantum.willow_lines import extract_disjoint_3q_lines

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    device = proc.get_device()
    cells = extract_disjoint_3q_lines(device)[:4]
    bridges = find_cascade_bridges(cells, device)
    assert isinstance(bridges, list)
    # Adjacent disjoint cells on Willow grid should have at least one bridge.
    assert len(bridges) >= 1


def test_cascade_circuit_structure() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")
    from cirq_google import engine

    from aurora_qsd.quantum.willow_cascade_entanglement import (
        build_cascade_entanglement_circuit,
        find_cascade_bridges,
    )
    from aurora_qsd.quantum.willow_lines import extract_disjoint_3q_lines

    proc = engine.create_default_noisy_quantum_virtual_machine("willow_pink").get_processor(
        "willow_pink"
    )
    device = proc.get_device()
    cells = extract_disjoint_3q_lines(device)[:2]
    bridges = find_cascade_bridges(cells, device)
    theta = math.radians(22.49)

    import cirq

    for arm in ("qsd", "wrong", "bare"):
        c = build_cascade_entanglement_circuit(cells, bridges, cascade_layers=2, theta=theta, arm=arm)
        assert any(isinstance(op.gate, cirq.MeasurementGate) for op in c.all_operations())
        n_qubits = len({q for cell in cells for q in cell.qubits()})
        assert n_qubits == 6


def test_cascade_run_schema() -> None:
    pytest.importorskip("cirq")
    pytest.importorskip("cirq_google")

    from aurora_qsd.quantum.willow_cascade_entanglement import run_cascade_entanglement

    result = run_cascade_entanglement(shots=128, cc_schedule=[0, 1], max_cells=2)
    d = result.to_dict()
    assert d["n_qubits"] == 6
    assert d["n_cells"] == 2
    assert len(d["points"]) == 2
    assert d["verdict"] in {"CASCADE_STABILIZED", "PARTIAL_CASCADE", "NULL"}
    for pt in d["points"]:
        assert "g_qsd_vs_bare" in pt
        assert "entropy_qsd_bits" in pt
        assert pt["shots"] == 128
