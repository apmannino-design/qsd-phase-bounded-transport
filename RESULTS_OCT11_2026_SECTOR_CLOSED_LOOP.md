# Real-Time Lock-In: Tri-ΔE Three-Stage Lock (Oct 11, 2026)

**Scope:** Classical real-time lock-in sketch. Not a hardware claim.

**Code:** `code/qsd_sector_closed_loop.py` + `TriDeltaLock` in `qsd_control_core.py`

## Stages

| Stage | Name | Gate | Actuation |
|---|---|---|---|
| 0 | acquire | — | inner residual/phase, \(F_{\mathrm{ref}}=Mg\) |
| 1 | hold | residual \(\Delta E_1\) + \|v\| | freeze \(\phi_{\mathrm{ref}}\), keep \(F_{\mathrm{ref}}=Mg\) |
| 2 | armed | residual \(\Delta E_2\) | slew-limited outer PID begins |
| 3 | track | gap \(\Delta E_3\) | full outer track; \(\phi_{\mathrm{ref}}=\arcsin(F_{\mathrm{ref}}/A(y))\) |

Loss-of-lock uses a looser residual ΔE gate with hysteresis. Force demand is rate-limited so outer moves do not re-break acquisition.

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results
```

## Seeded summary (seed=42)

| Metric | Value |
|---|---|
| Hold (stage 1) | @ 0.264 s |
| Track (stage 3) | @ 0.420 s |
| Post-track mean / RMS | ≈ 1.500 / 0.018 mm |
| Lock / track fraction | ≈ 0.82 / 0.72 |
| Lock drops | 0 |
| Final gap | ≈ 1.48 mm |
| \(y_{\mathrm{ref}}\) | 1.50 mm |

Artifact: `artifacts/tri_delta_lockin.png`
