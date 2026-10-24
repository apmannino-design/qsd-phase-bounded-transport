# QSD stack v2 + Spacetime stress suite (Oct 24, 2026)

**Scope:** Integrate uploaded `qsd_stack_v2` supervisor and `qsd_spacetime` stress / reroute studies. Classical sims only — not hardware claims.

## Added

| Path | Role |
|---|---|
| `qsd_spacetime/qsd_stack_v2.py` | Covariance supervisor + dual telemetry schemas; recoverable DEGRADED; optional forecast OFF by default |
| `qsd_spacetime/test_qsd_stack_v2.py` | Gap-robustness + equal-budget FSM plant comparison |
| `qsd_spacetime/bench_v2.py` / `bench_v2_fixed.out` | Forecast ON vs OFF equal-offload bench |
| `qsd_spacetime/qsd_stress_test.py` | Model-mismatch: basic Kalman vs reactive |
| `qsd_spacetime/qsd_stress_vibaware.py` | Vibration-aware filter (needs known frequency) |
| `qsd_spacetime/qsd_stress_fair.py` | Fair vib-aware with frequency error |
| `qsd_spacetime/qsd_reroute_sim.py` | Weather ground-station reroute (negative result) |

## Verification (this run)

| Check | Result |
|---|---|
| `python3 qsd_stack_v2.py test` | 14/14 OK |
| `python3 test_qsd_stack_v2.py` | EXIT 0 |
| `python3 test_integration.py` | ALL PASS |
| `qsd_stress_*.py` | EXIT 0 (slow vib: basic Kalman worse than reactive) |
| `qsd_reroute_sim.py` | EXIT 0 |

## Headline findings

1. **Do not deploy `qsd_gate.py` alone on vibrating platforms** — under slow vibration the basic Kalman predictive gate is worse than reactive at equal re-lock budget.
2. **Vib-aware filter** wins only with accurate vibration frequency; ~15% frequency error reverses the gain.
3. **`qsd_stack_v2` forecast** (`predict=True`): no lock-time benefit on the simulated plant; costs more offloads. Keep OFF unless real terminal data shows otherwise.
4. **Weather reroute:** predictive link-margin trends do not beat a reactive buffer at equal handovers/hour; early warning needs external weather sensors.
