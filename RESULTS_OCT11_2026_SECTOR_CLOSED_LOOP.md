# QSD Sector-Bounded Closed Loop — Acoustic Force Balance (Oct 11, 2026)

**Scope:** Classical illustration only. Matches the φ / F_ac sketch below; not a hardware or acoustic-field claim.

**Script:** `code/qsd_sector_closed_loop.py`

## Model

\[
C(\phi)=C_0\sin\phi,\quad
\tau\dot F_{\mathrm{ac}}=C(\phi)-F_{\mathrm{ac}}+d(t),\quad
r=F_{\mathrm{ac}}-Mg,\quad
\Delta E=\log(1+|r|)
\]

\[
\phi^+=\mathrm{clip}\bigl(\phi-K\,\mathrm{sat}_\alpha(r)\bigr)
\]

\[
|r_t|\le\rho^{t/2}|r_0|+\frac{D}{1-\sqrt{\rho}},\quad\rho<1
\]

Discrete step uses the continuous-consistent Euler form
\(F\leftarrow F+(\Delta t/\tau)(C_0\sin\phi-F+d)\)
(load step on \(Mg\), process noise on \(d\)). Balanced load is
\(Mg_{\mathrm{base}}=C_0\sin\theta^\*\) with \(\theta^\*=\pi/8\).

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results --phi0 0.35
```

## Seeded summary (seed=42, φ₀=0.35)

| Metric | Closed loop | Open loop (φ held) |
|---|---|---|
| Final ΔE | 0.0004 | 0.0421 |
| Mean ΔE (last 1 s) | 0.0024 | 0.0388 |
| Corridor fraction (all / tail) | 0.998 / 1.000 | 0.625 / 1.000 |
| Final φ | 23.32° | 20.05° |
| \|r\| mean (tail) | 0.0024 | 0.0396 |

Outputs: `results/qsd_sector_closed_loop.csv`, `results/qsd_sector_closed_loop_summary.json`, `results/qsd_sector_closed_loop.png`.
