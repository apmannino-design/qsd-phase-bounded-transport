# Conservative Outer Loop + QSD Sector Phase Law (Oct 11, 2026)

**Scope:** Full classical physics sketch for simultaneous force-match + gap hold. Not a hardware claim.

**Code:** `code/qsd_sector_closed_loop.py`  
**Lee–Wang NFAL helpers (prior):** `code/nfal_physics.py`

## Architecture

- **Monotonic phase branch** \(\phi\in[\phi_{\min},\pi/2]\)
- **Timestep-scaled phase rates** \(\phi\leftarrow\phi+\Delta t\,\dot\phi\)
- **Gap-dependent authority** \(A(y)=C_{0,\max}/(1+(y/h_0)^2)\), \(C=A\sin\phi\)
- **Force lag** \(\tau\dot F_{\mathrm{ac}}=C-F_{\mathrm{ac}}+d(t)\) with **DT-scaled** Wiener noise
- **Consistent \(F_{\mathrm{ref}}\) bounds** from available coupling
- **Conservative outer loop** \(F_{\mathrm{ref}}=\mathrm{clip}(mg-K_p(y-y_{\mathrm{ref}})-K_d v)\)
- **Inner residual** \(r=F_{\mathrm{ac}}-F_{\mathrm{ref}}\), \(e=\mathrm{sat}_\alpha(r/mg)\)
- **Lock-in status** when corridor + low \(|v|\) + low gap error; milder \(K_{\mathrm{inner}}\) + soft \(\phi_{\mathrm{ref}}\) spring after lock
- **Equilibrium initialization** at \((y_{\mathrm{ref}},\phi=\arcsin(mg/A(y_{\mathrm{ref}})))\)

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results
```

## Seeded summary (seed=42)

| Metric | Closed | Open |
|---|---|---|
| Lock-in | True @ 0.050 s | False |
| Hold mean / RMS | 1.500 / 0.014 mm | — |
| Final gap | 1.549 mm | 5.312 mm |
| Gap RMS (last 0.1 s) | 0.032 mm | 1.738 mm |
| Final \(\Delta E\) | 0.014 | 0.134 |

Outputs: `results/qsd_sector_closed_loop.*`, `artifacts/conservative_outer.png`.
