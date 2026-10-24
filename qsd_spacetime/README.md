# QSD gate × Aalyria Spacetime

Plugs the QSD ΔE-gated predictive re-lock into Aalyria's open-source SDN agent
(github.com/aalyria/api, Apache-2.0) using the agent's built-in `extproc`
hooks. No changes to Aalyria's code.

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
| `agent_config.textproto` | agent config wiring both extprocs |
| `test_integration.py` | end-to-end test against protos generated from aalyria/api (`gen/`) |

Run the test: `pip install protobuf numpy && python3 test_integration.py`

## Design notes
- The gate runs in a separate daemon because pointing control (ms) is far faster
  than Spacetime's telemetry period (s); extprocs only exchange state.
- Spacetime's v1alpha telemetry has no pointing or custom fields, so gate state
  maps to interface operational state and SINR. Raw ΔE / p_exit stay local.
- A retargeted or new beam resets the gate (fresh acquisition).
- Only `az_el` beam targets are handled directly; state-vector / Chebyshev targets
  need the residual from the terminal's own tracker.

## Not yet done
- Not run against the real Go agent binary or a live Spacetime instance (needs Aalyria credentials).
- `HardwareTerminal` is a stub: needs a real terminal's pointing readout and re-lock command.
- Plant model is the ideal random-walk case; model-mismatch stress test still pending.
