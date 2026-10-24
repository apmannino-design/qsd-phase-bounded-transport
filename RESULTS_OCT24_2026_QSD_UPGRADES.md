# QSD Spacetime upgrades (Oct 24, 2026)

Implements the post-stress upgrade plan against `qsd_spacetime/`.

| Upgrade | Implementation |
|---|---|
| Terminal record / replay | `qsd_terminal.RecordingTerminal` / `ReplayTerminal`, CLI `qsd_record_replay.py` |
| Hardware contract | `HardwareTerminal` (`QSD_HW_*`); `qsd_hw_sample_pump.py` (`--sim`/`--stdin`/`--udp`) |
| Calibrate θ / headroom | `qsd_calibrate.py` + **holdout** `qsd_scorecard_holdout.py` |
| Predict ON/OFF decision | Equal-offload holdout scorecard → writes `predict` into `calibration.json` |
| stack_v2 default | `qsd_daemon.py` default path; `--legacy-gate` for ideal-plant demo |
| External weather → NBI | `qsd_weather_ingest.py` + `qsd_weather_to_nbi.py` (ServiceRequest fragment) |
| Telemetry honesty | measured SINR only; `local_metrics.json` for ΔE / θ / headroom |
| Staging warm-up | `QSD_TELEMETRY_STARTUP_UP=1` maps regime 0/5 + valid → UP |
| Staging dry-run | `agent_config.staging.textproto` + `scripts/spacetime_staging_dryrun.sh` |
| One-shot pipeline | `scripts/qsd_terminal_pipeline.sh` |

```bash
python3 qsd_spacetime/test_upgrades.py
python3 qsd_spacetime/test_integration.py
scripts/qsd_terminal_pipeline.sh --sim --seconds 3
scripts/spacetime_staging_dryrun.sh
```

**Note:** Until a real terminal fills `QSD_HW_SAMPLE_PATH` (or `--stdin`/`--udp`), the pipeline uses the dry plant. The holdout verdict is what decides whether forecast stays OFF.
