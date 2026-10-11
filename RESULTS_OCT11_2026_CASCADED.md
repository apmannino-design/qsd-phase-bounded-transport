# Cascaded Plant: Gap + Phase + Spatial Node (Oct 11, 2026)

**Scope:** Classical cascaded sketch. Not a hardware claim.

**Code:** `code/qsd_cascaded_plant.py`

One plant, one TriDeltaLock, one scorecard:
- Levitator force residual → gap outer loop (stages 0–3)
- After stage 3, spatial node tracks a moving target (unwrapped FF+FB)

Shared disturbance battery with lock-in (`run_qsd_disturbance_battery.py`).

## Reproduce

```bash
python3 code/qsd_cascaded_plant.py --self-test
python3 code/qsd_cascaded_plant.py --out-dir results
```

## Seeded (seed=42)

Lock 0.259 s → track 0.404 s; combined normalized rms_ratio ≈ 0.057; 0 drops.

Artifact: `artifacts/cascaded_plant.png`
