# Spatial Match: Node Tracks Moving Target (Oct 11, 2026)

**Scope:** Classical two-source spatial match sketch. Not a hardware claim.

**Code:** `code/qsd_spatial_match.py`

## Idea (plain language)

Two waves from opposite sides make a pressure pattern with **zeros (nodes)**.  
Moving the relative phase slides a node left/right. The controller measures where the node is and nudges phase (and a little amplitude ratio) so that node follows a moving target.

## Reproduce

```bash
python3 code/qsd_spatial_match.py --self-test
python3 code/qsd_spatial_match.py --out-dir results
```

## Notes vs bare sketch

- Track one node continuously (don’t jump between zeros)
- Interpolate zero crossings
- Analytic phase feedforward \(\phi\approx\pi-2kx_{\mathrm{des}}\) plus sector feedback
- Keep amplitude ratio ≈ 1 (best contrast); phase is the node actuator

## Seeded (seed=42)

Closed-loop mean |node error| ≈ 0.001 vs open-loop ≈ 0.08; corridor fraction ≳ 0.95.

Artifact: `artifacts/spatial_match.png`
