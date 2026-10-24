# QSD × Aalyria Spacetime Bridge (Oct 24, 2026)

**Scope:** Integration sketch wiring the QSD ΔE-gated predictive re-lock into Aalyria Spacetime’s open SDN agent via `extproc`. Not a live-network claim.

**Code:** `qsd_spacetime/`

## Layout

| File | Role |
|---|---|
| `qsd_gate.py` | ΔE corridor + 2-state Kalman predictive trigger |
| `qsd_enact.py` | extproc enactment → `state/beams.json` |
| `qsd_daemon.py` | gate at terminal rate (`SimTerminal` / `HardwareTerminal` stub) |
| `qsd_telemetry.py` | extproc telemetry → interface state + SINR |
| `agent_config.textproto` | agent wiring |
| `test_integration.py` | end-to-end vs generated aalyria/api protos |

## Reproduce

```bash
pip install protobuf numpy
python3 qsd_spacetime/test_integration.py
```

## Seeded result (20 trials × 2000 steps)

| Mode | Re-locks / 2000 | Time outside corridor |
|---|---|---|
| reactive | ~32 | ~2.7% |
| predictive | ~39 | ~0.05% |

Predictive spends less time outside the corridor through the agent path. ALL PASS.
