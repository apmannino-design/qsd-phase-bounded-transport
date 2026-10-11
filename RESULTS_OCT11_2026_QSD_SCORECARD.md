# Unified QSD Scorecard (Oct 11, 2026)

**Scope:** Classical scientific sketches sharing `code/qsd_control_core.py`. Not hardware claims.

## Shared core

`qsd_control_core` encodes: sector `sat_α`, ΔE = log1p(|r|/scale), DT-scaled rates, √DT Wiener noise, quiet-window lock, SensorModel (lag/bias/dropout), Scorecard.

## Reproduce

```bash
python3 code/run_qsd_scorecard.py --self-test
python3 code/run_qsd_scorecard.py --out-dir results
```

## Seeded scorecard

| Demo | Lock | Corridor | Track RMS | Open RMS | ΔE∞ |
|---|---|---|---|---|---|
| opto_acoustic | 0.006 s | 99.8% | 0.016 | 0.051 | 0.009 |
| lock_in | 0.292 s | 83.7% | 0.081 mm | 0.300 mm | 0.015 |
| spatial_match | 0.158 s | 99.4% | 0.003 | 0.083 | 0.028 |

Artifact: `results/qsd_scorecard.json`
