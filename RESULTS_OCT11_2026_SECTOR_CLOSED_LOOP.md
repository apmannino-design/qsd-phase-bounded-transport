# QSD Sector-Bounded Closed Loop — Toy Acoustic Plant (Oct 11, 2026)

**Scope:** Classical illustration only. Minimal first-order lag plant with sector-saturated feedback; not a hardware or acoustic-field claim.

**Script:** `code/qsd_sector_closed_loop.py`

## What it demonstrates

- Design angle θ\* = π/8 = 22.5° (parameter context; plant update uses signed pressure residual).
- Sector saturation `sat(e, α)` with α = 0.15.
- Closed-loop recovery into a ΔE < 0.1 corridor after a load step (1.0–2.5 s) plus noise.
- Open-loop control remains outside the corridor (negative control).

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results
```

## Seeded summary (seed=42)

| Metric | Closed loop | Open loop |
|---|---|---|
| Final ΔE | 0.0082 | 0.7349 |
| Mean ΔE (last 1 s) | 0.0470 | 0.6909 |
| Corridor fraction (tail) | 0.921 | 0.000 |
| Final drive u | 1.232 | 0.000 |

Outputs: `results/qsd_sector_closed_loop.csv`, `results/qsd_sector_closed_loop_summary.json`, `results/qsd_sector_closed_loop.png`.
