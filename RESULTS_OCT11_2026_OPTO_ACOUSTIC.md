# Opto-Acoustic Frequency-Matched Residual Loop (Oct 11, 2026)

**Scope:** Classical photoacoustic match sketch. Not a hardware claim.

**Code:** `code/qsd_opto_acoustic.py` (via `qsd_control_core`)

## Model

\[
\tau\dot p = \eta I\sin\phi - p + d(t),\quad
r=p_{\mathrm{meas}}-p_{\mathrm{ref}},\quad
\Delta E=\log(1+|r|),\quad
\dot\phi=-K\,\mathrm{sat}_\alpha(r)
\]

DT-scaled \(\phi\) rate and √DT plant noise; sensor lag/bias/dropout on \(p\).
Balance: \(\phi^\*=\arcsin(p_{\mathrm{ref}}/(\eta I))\).

## Reproduce

```bash
python3 code/qsd_opto_acoustic.py --self-test
python3 code/qsd_opto_acoustic.py --out-dir results
```

## Seeded summary (seed=1)

| Metric | Closed |
|---|---|
| Final ΔE | ~0.009 |
| Corridor (ΔE < 0.07) | ~99.8% |
| Track RMS (closed / open) | ~0.016 / 0.051 |
| Final p | ~0.61 (target 0.60) |

Artifact: `artifacts/opto_acoustic.png`
