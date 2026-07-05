"""Tests for Willow line echo protocol (phase echo, not ZZZ depth)."""

import pytest

from aurora_qsd.quantum.echo_protocol import (
    STATES,
    build_echo_circuit,
    run_willow_echo_benchmark,
    _survival_probability,
)


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("mode", ["qsd", "x", "none", "random"])
def test_noiseless_echo_survival(state: str, mode: str) -> None:
  qc = build_echo_circuit(state=state, mode=mode, tau_ns=0, phi=0.7)
  assert _survival_probability(qc, state) == pytest.approx(1.0, abs=1e-9)


def test_willow_benchmark_schema() -> None:
    result = run_willow_echo_benchmark(shots=512, tau_ns=1000, n_random=3, seed=0, t2_ns=2000)
    d = result.to_dict()
    assert d["theta_star_deg"] == 22.5
    assert set(d["per_state"]) == {"echo_qsd", "echo_x", "echo_random", "no_echo"}
    for mode in d["per_state"]:
        assert set(d["per_state"][mode]) == set(STATES)
    for mode in d["pooled"]:
        assert 0.5 < d["pooled"][mode]["F"] < 1.0
    assert d["verdict"] in {"NULL", "MARGINAL", "QSD_ECHO_WIN"}


def test_echo_sweep_runs() -> None:
    from aurora_qsd.quantum.echo_sweep import run_willow_echo_sweep

    result = run_willow_echo_sweep(shots=256, span_deg=10.0, n_theta=5, taus_ns=(500, 1000))
    assert result.theta_sweep
    assert result.tau_sweep
    assert len(result.pulse_sweep) == 4
    assert result.recommendation


def test_cirq_echo_noiseless() -> None:
    cirq = pytest.importorskip("cirq")
    from aurora_qsd.quantum.echo_cirq import build_echo_circuit

    qubits = [cirq.LineQubit(i) for i in range(3)]
    target = qubits[1]
    for state in ("0", "+", "1"):
        circuit = build_echo_circuit(state=state, mode="x", tau_ns=0, t2_ns=2000)
        sim = cirq.Simulator()
        result = sim.run(circuit, repetitions=200)
        assert (result.data["m"] == 0).mean() == 1.0


def test_cirq_matches_qiskit_pooled() -> None:
    pytest.importorskip("cirq")
    from aurora_qsd.quantum.echo_cirq import run_willow_echo_benchmark as run_cirq
    from aurora_qsd.quantum.echo_protocol import run_willow_echo_benchmark as run_qiskit

    qc = run_qiskit(shots=800, tau_ns=1000, n_random=2, seed=1, t2_ns=2000)
    cc = run_cirq(shots=800, tau_ns=1000, n_random=2, seed=1, t2_ns=2000)
    for mode in ("echo_qsd", "echo_x", "no_echo"):
        assert abs(qc.pooled[mode]["F"] - cc.pooled[mode]["F"]) < 0.05
