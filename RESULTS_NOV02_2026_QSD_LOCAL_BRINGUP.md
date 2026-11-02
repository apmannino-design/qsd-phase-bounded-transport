# QSD local production-path bringup (Nov 2, 2026)

**Scope:** Credential-free rehearsal of the Spacetime-facing I/O contract after
safety patches landed on `main`. Not a live-network claim.

## Gap this closes

After H1–H4 / MODEM_MAP / stack_v2 v2.1, the remaining local hole was that
`HardwareTerminal`, sample pump, example hooks, `qsd_daemon`, enact POINT, and
telemetry were never exercised **together** without Aalyria credentials.
`qsd_terminal_pipeline.sh` only covers record → holdout calibrate.

## What landed

| Artifact | Role |
|---|---|
| `qsd_spacetime/test_local_bringup.py` | CI gate: enact→POINT, pump→HardwareTerminal→daemon, modem_map→telemetry, H2 reject |
| `scripts/qsd_local_bringup.sh` | Multi-process rehearsal of the same path |
| `qsd_spacetime/modem_map.json.example` | Provisioning template (IDs never invented) |
| `scripts/qsd_doctor.sh` | Warns when `modem_map` is missing |

## Reproduce

```bash
python3 qsd_spacetime/test_local_bringup.py
scripts/qsd_local_bringup.sh
```

## Next (human / staging)

1. Land Spacetime JWT access scaffolding (open PR #19).
2. `scripts/generate_spacetime_keys.sh` → share `.cer` with Aalyria.
3. Fill `bringup.env`, run `spacetime_staging_dryrun.sh` against the real agent.
