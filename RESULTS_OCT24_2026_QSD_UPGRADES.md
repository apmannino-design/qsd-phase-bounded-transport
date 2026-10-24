# QSD Spacetime upgrades (Oct 24, 2026)

Implements the post-stress upgrade plan against `qsd_spacetime/`.

| Upgrade | Implementation |
|---|---|
| Terminal record / replay | `qsd_terminal.RecordingTerminal` / `ReplayTerminal`, CLI `qsd_record_replay.py` |
| Hardware contract | `qsd_terminal.HardwareTerminal` (`QSD_HW_*` env); enact `POINT` forward |
| Calibrate θ / headroom | `qsd_calibrate.py` → `state/calibration.json` loaded by daemon |
| stack_v2 default | `qsd_daemon.py` default path; `--legacy-gate` for ideal-plant demo |
| External weather | `qsd_weather_ingest.py` → `weather_advice.json` + `nbi_hint` |
| Telemetry honesty | measured SINR only; `local_metrics.json` for ΔE / θ / headroom / p_exit |
| Staging dry-run | `agent_config.staging.textproto` + `scripts/spacetime_staging_dryrun.sh` |

```bash
python3 qsd_spacetime/test_upgrades.py
python3 qsd_spacetime/test_integration.py
scripts/spacetime_staging_dryrun.sh
```
