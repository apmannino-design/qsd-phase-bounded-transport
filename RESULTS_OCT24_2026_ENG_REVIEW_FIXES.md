# Engineering review fixes (Oct 24, 2026)

Addresses the high/medium findings in *Engineering Review: QSD Repository × Aalyria Spacetime*.

**Public technical brief:** [`docs/Technical_Brief_Link-Health_Supervisor_for_Aalyria_Spacetime.pdf`](docs/Technical_Brief_Link-Health_Supervisor_for_Aalyria_Spacetime.pdf)

| ID | Fix |
|---|---|
| H1 | `qsd_enact.py` returns **12 UNIMPLEMENTED** for non-beam changes (e.g. `set_route`) |
| H2 | Rejected `QSD_HW_POINT_CMD` → **14 UNAVAILABLE**; beam table not updated |
| H3 | `QSD_TELEMETRY_STARTUP_UP` defaults to **0** (strict DORMANT); staging opt-in only |
| H4 | `verify_qsd_spacetime.sh` uses stack_v2 + measured SINR; asserts modem only when IDs configured |
| M1 | `qsd_doctor.sh` treats staging **SKIP** as WARN, not OK |
| M2 | No invented modem IDs in daemon/telemetry |
| M4 | Results table labeled as unequal-budget; point to equal-budget suites |
| M5 | Weather→NBI marked experimental |
| M6 | `test_qsd_stack_v2.py` now asserts; long sweep renamed `bench_qsd_stack_v2.py` |
| L1 | `TEST.md` no longer references missing `tests/` |

```bash
python3 qsd_spacetime/test_integration.py
python3 qsd_spacetime/test_upgrades.py
python3 qsd_spacetime/test_qsd_stack_v2.py
scripts/verify_qsd_spacetime.sh
```
