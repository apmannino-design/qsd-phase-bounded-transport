# Unified QSD Scorecard (Oct 11, 2026)

**Scope:** Classical scientific sketches sharing `code/qsd_control_core.py`. Not hardware claims.

**Headline metric:** `rms_ratio = closed_rms / open_rms` (lower is better; <1 means closed wins).

## Shared core

- Sector `sat_α`, ΔE, DT-scaled rates, √DT Wiener noise
- `TriDeltaLock`: acquire → hold (ΔE₁) → arm (ΔE₂) → track (**physical** `|y−y_ref|<ε` & `|v|`)
- Stage-clock open-loop baseline (same stages, no feedback)
- Gain schedule: `results/qsd_gain_schedule.csv`
- Disturbance battery: `results/qsd_disturbance_battery.csv`

## Reproduce

```bash
python3 code/run_qsd_scorecard.py --self-test
python3 code/run_qsd_disturbance_battery.py --self-test
python3 code/qsd_cascaded_plant.py --self-test
```

## Seeded scorecard

| Demo | Lock | Corridor | **ratio** | Closed RMS | Open RMS |
|---|---|---|---|---|---|
| opto_acoustic | 0.006 s | 99.8% | **0.31** | 0.016 | 0.051 |
| lock_in | 0.259 s | 89.3% | **0.060** | 0.018 mm | 0.300 mm |
| spatial_match | 0.158 s | 99.4% | **0.036** | 0.003 | 0.083 |
| cascaded | 0.259 s | 89.3% | **0.057** | 0.088 | 1.54 |

## Disturbance battery (lock-in / cascaded)

All cases reach track with **0 drops** (seed=42): nominal, step_force, chirp, bias_walk, dropout_burst.
