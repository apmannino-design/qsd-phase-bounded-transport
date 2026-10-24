# QSD × Aalyria Spacetime

Bridges QSD pointing control into Aalyria's open SDN agent
([github.com/aalyria/api](https://github.com/aalyria/api), Apache-2.0) via `extproc`.
No changes to Aalyria's code.

**Default controller: `qsd_stack_v2` (forecast OFF).** Bare `qsd_gate.py` is
`--legacy-gate` only (ideal random-walk demo). Do not deploy it on vibrating platforms.

Vendored API + Go agent: `../third_party/aalyria-api/` (pin `AALYRIA_API_PIN.txt`).

```
Spacetime ──schedule──> agent ──CreateEntryRequest──> qsd_enact.py ──> beams.json
                              └── POINT forward ──> enact_forward.jsonl / QSD_HW_POINT_CMD
                                                              │
         terminal <── offload/relock ── qsd_daemon.py (stack_v2) ─┤
                                                              ├─> status.json      (Spacetime-facing)
                                                              └─> local_metrics.json (ΔE/θ/headroom; local only)
Spacetime <──telemetry── agent <──ExportMetricsRequest── qsd_telemetry.py <── status.json
```

| File | Role |
|---|---|
| `qsd_stack_v2.py` | **Production** covariance supervisor (recoverable DEGRADED; forecast OFF) |
| `qsd_daemon.py` | Control loop; default stack_v2; `--legacy-gate` for demo |
| `qsd_terminal.py` | `HardwareTerminal` / `RecordingTerminal` / `ReplayTerminal` / `SimStackTerminal` |
| `qsd_enact.py` | extproc enactment + POINT forward to terminal |
| `qsd_telemetry.py` | extproc telemetry; **measured SINR only** |
| `qsd_calibrate.py` | Fit headroom/θ from a recording → `calibration.json` |
| `qsd_record_replay.py` | Record / replay terminal sessions through stack_v2 |
| `qsd_weather_ingest.py` | External weather → `weather_advice.json` + NBI hint |
| `qsd_gate.py` | Legacy Kalman gate (ideal plant) |
| `agent_config.textproto` | Production placeholders |
| `agent_config.staging.textproto` | Staging placeholders |
| `gen/` | Python protos from vendored aalyria/api |

## Verify

```bash
pip install protobuf numpy googleapis-common-protos
python3 test_upgrades.py
python3 test_integration.py
python3 qsd_stack_v2.py test
../scripts/spacetime_staging_dryrun.sh
../scripts/verify_qsd_spacetime.sh
```

## Deploy path (terminal)

```bash
# One-shot: record (sim) → train/holdout calibrate → equal-offload scorecard
../scripts/qsd_terminal_pipeline.sh --sim --seconds 30

# Or with a real recording already on disk:
../scripts/qsd_terminal_pipeline.sh --record /path/to/terminal.jsonl

# Hardware sample pump (driver writes JSON, or use --sim / --stdin / --udp)
QSD_HW_SAMPLE_PATH=state/hw_sample.json python3 qsd_hw_sample_pump.py --sim
export QSD_HW_SAMPLE_PATH=state/hw_sample.json
export QSD_HW_CMD_PATH=state/hw_commands.jsonl
export QSD_HW_OFFLOAD_CMD=/opt/terminal/offload.sh
export QSD_HW_RELOCK_CMD=/opt/terminal/relock.sh
export QSD_HW_POINT_CMD=/opt/terminal/point.sh   # args: az el beam_id
python3 qsd_daemon.py --dt 0.001   # loads calibration.json (predict from holdout verdict)
```

## Weather (external only)

Link-margin KF reroute was a negative result (`qsd_reroute_sim.py`). Use:

```bash
python3 qsd_weather_ingest.py --in weather.json
python3 qsd_weather_to_nbi.py --advice state/weather_advice.json --src-node gateway-1
# → state/nbi_service_request.json  (submit via NBI / nbictl; not SBI)
```

## Design notes
- Pointing (ms) is faster than Spacetime telemetry (s); extprocs only exchange state.
- Spacetime v1alpha has no custom pointing fields → interface oper state + measured SINR.
- ΔE / θ / headroom / p_exit stay in `local_metrics.json`.
- Forecast (`--predict`) stayed OFF after bench: more offloads, no lock-time win on the sim plant.

See `RESULTS_OCT24_2026_QSD_STACK_V2.md` and `RESULTS_OCT24_2026_QSD_UPGRADES.md`.
