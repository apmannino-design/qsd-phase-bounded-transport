# Real-Time Lock-In: Tri-ΔE + Physical Gap Gate (Oct 11, 2026)

**Scope:** Classical real-time lock-in sketch. Not a hardware claim.

**Code:** `code/qsd_sector_closed_loop.py` + `TriDeltaLock` in `qsd_control_core.py`

## Stages

| Stage | Name | Gate | Actuation |
|---|---|---|---|
| 0 | acquire | — | inner residual/phase, \(F_{\mathrm{ref}}=Mg\) |
| 1 | hold | residual \(\Delta E_1\) + \|v\| | freeze \(\phi_{\mathrm{ref}}\), keep \(F_{\mathrm{ref}}=Mg\) |
| 2 | armed | residual \(\Delta E_2\) | slew-limited outer PID |
| 3 | track | **physical** \|y−y_ref\|<ε and \|v\| | full track; \(\phi_{\mathrm{ref}}=\arcsin(F/A(y))\) |

Open-loop baseline replays the closed-loop **stage clock** (fair rms_ratio).  
Gain schedule: `results/qsd_gain_schedule.csv`.

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results
```

## Seeded summary (seed=42)

| Metric | Value |
|---|---|
| Hold / track | 0.259 s / 0.405 s |
| Post-track mean / RMS | ≈ 1.499 / 0.018 mm |
| rms_ratio (closed/open) | ≈ 0.060 |
| Lock drops | 0 |

Artifact: `artifacts/tri_delta_lockin.png`
