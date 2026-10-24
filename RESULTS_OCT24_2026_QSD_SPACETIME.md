# QSD × Aalyria Spacetime Bridge (Oct 24, 2026)

**Scope:** Wire the QSD ΔE-gated predictive re-lock into Aalyria Spacetime’s open SDN agent via `extproc`, against the full vendored [aalyria/api](https://github.com/aalyria/api) tree. Not a live-network claim.

**Code:** `qsd_spacetime/` · **Upstream vendor:** `third_party/aalyria-api/` (pin: `third_party/AALYRIA_API_PIN.txt`)

## Layout

| Path | Role |
|---|---|
| `qsd_spacetime/qsd_gate.py` | ΔE corridor + 2-state Kalman predictive trigger |
| `qsd_spacetime/qsd_enact.py` | extproc enactment → `state/beams.json` |
| `qsd_spacetime/qsd_daemon.py` | gate at terminal rate (`SimTerminal` / `HardwareTerminal` stub) |
| `qsd_spacetime/qsd_telemetry.py` | extproc telemetry → interface state + SINR |
| `qsd_spacetime/agent_config.textproto` | agent wiring (validated by Go agent `--dry-run`) |
| `qsd_spacetime/gen/` | Python protos regenerated from vendored aalyria/api + NMTS |
| `third_party/aalyria-api/` | Full Spacetime API + Go SBI agent |
| `scripts/fetch_aalyria_spacetime.sh` | Refresh vendor snapshot from GitHub |
| `scripts/regen_qsd_spacetime_protos.sh` | Regenerate `gen/` |
| `scripts/verify_qsd_spacetime.sh` | End-to-end verification |

## Reproduce

```bash
pip install protobuf numpy googleapis-common-protos
scripts/verify_qsd_spacetime.sh
# or: python3 qsd_spacetime/test_integration.py
```

## Verification (this run)

| Check | Result |
|---|---|
| Vendored `aalyria/api` @ `ee3f0ea4…` | present |
| Regenerated Python protos (`CreateEntryRequest`, `ExportMetricsRequest`, `AgentParams`) | OK |
| `test_integration.py` | ALL PASS |
| Go `//agent/cmd/agent` bazel build | OK |
| `agent --dry-run` on QSD `agent_config.textproto` | `config is valid` |
| `extproc` / `extprocs` / `protofmt` / `agentcli` unit tests | 4/4 PASS |

## Seeded result (20 trials × 2000 steps)

| Mode | Re-locks / 2000 | Time outside corridor |
|---|---|---|
| reactive | ~32 | ~2.7% |
| predictive | ~39 | ~0.05% |

Predictive spends less time outside the corridor through the agent path **on the ideal random-walk plant**. Under vibration / mismatch, see `RESULTS_OCT24_2026_QSD_STACK_V2.md` — deploy `qsd_stack_v2.py` (forecast OFF by default), not bare `qsd_gate.py`.
