# Spatial Match: Lock Mid-Node Then Track (Oct 11, 2026)

**Scope:** Classical two-source spatial match sketch. Not a hardware claim.

**Code:** `code/qsd_spatial_match.py` (via `qsd_control_core`)

## Idea (plain language)

Two waves from opposite sides make a pressure pattern with **zeros (nodes)**.  
Moving the relative phase slides a node left/right. The controller first locks a mid-domain node (quiet window), then tracks a moving target with unwrapped feedforward + sector feedback.

## Reproduce

```bash
python3 code/qsd_spatial_match.py --self-test
python3 code/qsd_spatial_match.py --out-dir results
```

## Notes vs bare sketch

- Continuous interpolated node tracking (no jump between zeros)
- Analytic phase feedforward \(\phi\approx\pi-2kx_{\mathrm{des}}\) on an **unwrapped** phase state
- Lock-then-track: acquire at \(x=0.5\), then follow the moving target
- Sensor lag/bias/dropout on measured node
- Amplitude ratio ≈ 1 (best contrast); phase is the node actuator
- √DT field noise

## Seeded (seed=42)

Lock @ ≈ 0.16 s; closed-loop mean |node error| ≈ 0.002 vs open-loop ≈ 0.07; corridor ≈ 99%.

Artifact: `artifacts/spatial_match.png`
