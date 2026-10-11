# Real-Time Lock-In: Acquisition → Outer Loop (Oct 11, 2026)

**Scope:** Classical real-time lock-in sketch. Not a hardware claim.

**Code:** `code/qsd_sector_closed_loop.py`

## Architecture

1. **Acquisition** — inner residual/phase only, \(F_{\mathrm{ref}}=Mg\)
2. **Quiet-window detector** — mean/max \(\Delta E\) and \(|v|\) over ~25 ms
3. **Lock** — freeze \(\phi_{\mathrm{ref}}\), enable outer PID on gap
4. **Locked phase law** — \(\dot\phi=-K_{\mathrm{locked}}e-\lambda(\phi-\phi_{\mathrm{ref}})\)
5. **Loss-of-lock** — sustained high \(\Delta E\) after a short grace period

Also: monotonic \(\phi\) branch, consistent \(F_{\mathrm{ref}}\) bounds from \(A(y)\sin\phi\), DT-scaled force noise, light damping (required for a quiet acquisition window).

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results
```

## Seeded summary (seed=42)

| Metric | Value |
|---|---|
| Lock-in | True @ 0.269 s |
| Post-lock mean / RMS | ≈ 1.49 / 0.08 mm |
| Final gap | ≈ 1.52 mm |
| \(y_{\mathrm{ref}}\) | 1.50 mm |

Artifact: `artifacts/realtime_lockin.png`
