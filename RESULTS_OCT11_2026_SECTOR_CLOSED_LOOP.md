# Conservative Outer Loop + QSD Sector Phase Law (Oct 11, 2026)

**Scope:** Full classical physics sketch for simultaneous force-match + gap hold. Not a hardware claim.

**Code:** `code/qsd_sector_closed_loop.py`

## Architecture

- Monotonic phase branch \(\phi\in[\phi_{\min},\pi/2]\)
- Timestep-scaled phase rates \(\phi\leftarrow\phi+\Delta t\,\dot\phi\)
- Gap-dependent authority \(A(y)=C_{0,\max}/(1+(y/h_0)^2)\), \(C=A\sin\phi\)
- Force lag \(\tau\dot F=C-F+d\) with **DT-scaled** Wiener noise (raw per-step \(dF\) escapes)
- Consistent \(F_{\mathrm{ref}}\) bounds from available coupling
- Conservative outer loop \(F_{\mathrm{ref}}=\mathrm{clip}(mg-K_p(y-y_{\mathrm{ref}})-K_d v)\)
- Inner residual \(r=F-F_{\mathrm{ref}}\), \(\dot\phi=-K_{\mathrm{lock}}\mathrm{sat}_\alpha(r/mg)\)
- Lock-in is a **status latch** (corridor + quiet \(v,y\)); phase law stays residual-driven
- Equilibrium initialization at \(y_{\mathrm{ref}}\)

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results
```

## Seeded summary (seed=42)

| Metric | Closed |
|---|---|
| Lock-in | True @ 0.050 s |
| Final gap | 1.500 mm |
| Hold mean / RMS | 1.500 / ~0.0004 mm |
| Gap RMS (last 0.1 s) | ~0.0004 mm |
| Final \(\Delta E\) | ~0.001 |

<img alt="stable conservative outer loop" src="/opt/cursor/artifacts/conservative_outer_stable.png" />
