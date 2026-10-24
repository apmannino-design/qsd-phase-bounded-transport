# QSD gate × Aalyria Spacetime

Plugs the QSD ΔE-gated predictive re-lock into Aalyria's open-source SDN agent
([github.com/aalyria/api](https://github.com/aalyria/api), Apache-2.0) using the agent's built-in `extproc`
hooks. No changes to Aalyria's code.

The full Spacetime API + Go SBI agent are vendored under `../third_party/aalyria-api`
(pinned in `../third_party/AALYRIA_API_PIN.txt`). Python bindings in `gen/` are
regenerated from that tree.

```
Spacetime ──Scheduling API──> agent ──stdin (CreateEntryRequest)──> qsd_enact.py ──> state/beams.json
                                                                                         │
                                       terminal <── re-lock ── qsd_daemon.py (QSD gate) ─┤
                                                                                         ▼
Spacetime <──Telemetry API── agent <──stdout (ExportMetricsRequest)── qsd_telemetry.py <── state/status.json
```

| File | Role |
|---|---|
| `qsd_gate.py` | ΔE corridor + 2-state Kalman predictive trigger (pure NumPy) |
| `qsd_enact.py` | extproc enactment: records `update_beam` / `delete_beam` targets |
| `qsd_daemon.py` | runs the gate at terminal rate; `SimTerminal` for tests, `HardwareTerminal` stub for real I/O |
| `qsd_telemetry.py` | extproc telemetry: interface state (UP / DORMANT / DOWN) + SINR to Spacetime |
| `qsd_stack_v2.py` | Covariance supervisor + Spacetime telemetry adapter (recoverable faults; optional forecast OFF by default) |
| `agent_config.textproto` | agent config wiring both extprocs |
| `gen/` | Python protos from vendored `aalyria/api` + NMTS |
| `test_integration.py` | end-to-end test against regenerated protos |
| `test_qsd_stack_v2.py` | supervisor robustness / equal-budget FSM plant tests |
| `qsd_stress_*.py` | model-mismatch stress (vibration / vib-aware / fair) |
| `qsd_reroute_sim.py` | weather ground-station reroute sim (negative result) |

## Verify

```bash
pip install protobuf numpy googleapis-common-protos
../scripts/verify_qsd_spacetime.sh          # protos + bridge + Go agent dry-run
python3 test_integration.py
python3 qsd_stack_v2.py test
python3 test_qsd_stack_v2.py
```

Refresh upstream + regenerate:

```bash
../scripts/fetch_aalyria_spacetime.sh
../scripts/regen_qsd_spacetime_protos.sh
```

## Design notes
- The gate runs in a separate daemon because pointing control (ms) is far faster
  than Spacetime's telemetry period (s); extprocs only exchange state.
- Spacetime's v1alpha telemetry has no pointing or custom fields, so gate state
  maps to interface operational state and SINR. Raw ΔE / p_exit stay local.
- A retargeted or new beam resets the gate (fresh acquisition).
- Only `az_el` beam targets are handled directly; state-vector / Chebyshev targets
  need the residual from the terminal's own tracker.

## Stress / mismatch results (do not skip)
Model-mismatch stress (`qsd_stress_test.py`, `qsd_stress_vibaware.py`,
`qsd_stress_fair.py`): the basic Kalman gate is 2–5× **worse** than reactive under slow
vibration; a vibration-aware filter wins only if the vibration frequency is known
(15% too high reverses it). Do not deploy `qsd_gate.py` as-is on a vibrating platform.
The upgraded `qsd_stack_v2.py` supervisor uses a frequency-free, fail-safe forecast instead
(`predict=True`; OFF by default). Bench (`bench_v2.py`): no lock-time benefit on the
simulated plant; forecast cost 5–170% more offloads — keep for real terminal data only.

## Weather rerouting (`qsd_reroute_sim.py`) — negative result
Predictive (Kalman trend) vs reactive (filtered margin + safety buffer) ground-station
switching under simulated cloud fades and scintillation, compared at equal handovers/hour.

- Heavy weather: both policies sit at the floor (all stations clouded + switching time). Gain ≤ 2%.
- Light weather: the best reactive policy's outage equals its handover time exactly
  (e.g. 2.9 HO/h × 3 s = 0.24%), i.e. it already avoids every fade. Nothing left to predict.
- With 15 s reacquisition, an 18 s horizon is too uncertain; the predictive gate thrashes.

Conclusion: cloud fades ramp over tens of seconds, so a reactive switch with a few dB of
buffer already gets out in time. Link-telemetry trends add no useful warning. Real early
warning would have to come from outside the link (weather radar, all-sky cameras, cloud imagery).

## Not yet done
- Not run against a live Spacetime instance (needs Aalyria credentials).
- `HardwareTerminal` is a stub: needs a real terminal's pointing readout and re-lock command.
