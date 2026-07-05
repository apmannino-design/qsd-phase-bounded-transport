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
