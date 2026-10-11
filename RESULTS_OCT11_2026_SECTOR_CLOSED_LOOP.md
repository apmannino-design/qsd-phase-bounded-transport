# QSD Sector Control on Near-Field Acoustic Levitation (Oct 11, 2026)

**Scope:** Reduced-order **scientific** NFAL plant + sector-bounded φ control. Not a hardware claim.

**Code:** `code/nfal_physics.py`, `code/qsd_sector_closed_loop.py`

## Physics

Near-field squeeze-film radiation pressure (Lee & Wang / Chu–Apfel, micrometer-gap limit):

\[
\bar p=\frac{\gamma(\gamma+1)}{8}\frac{a_{\mathrm{eff}}^{2}\,p_{0}}{h^{2}},\qquad
a_{\mathrm{eff}}=a_{\max}\sin\phi,\qquad
F_{\mathrm{ac}}=\bar p\,A
\]

Vertical plate dynamics:

\[
m\ddot h=F_{\mathrm{ac}}-mg-b\dot h
\]

Design identity: \(a_{\max}\) is solved so \(F(h^\*,\theta^\*)=mg\) with \(\theta^\*=\pi/8\).

Squeeze-number diagnostic \(\sigma=12\eta\omega R^{2}/(p_{0}h^{2})\) (≪1 free-flow, ≫1 trapped-film / NFAL).

## Control

A free plate already force-balances by changing \(h\). The controlled output is therefore **gap regulation**:

\[
e_h=\frac{h-h^\*}{h^\*},\quad
\Delta E=\log(1+|e_h|),\quad
\phi^{+}=\mathrm{clip}\bigl(\phi-K\,\mathrm{sat}_{\alpha}(e_h)\bigr)
\]

Open-loop negative control: φ held fixed (mass step drops the equilibrium gap).

## Nominal plant (SI)

| Quantity | Value |
|---|---|
| Drive frequency | 28 kHz |
| Plate radius | 20 mm |
| Payload mass | 12 g (+3 g step @ 1–2.5 s) |
| Design gap \(h^\*\) | 80 μm |
| Solved \(a_{\max}\) | ≈ 9.8 μm (\(a/h^\*\approx0.12\)) |
| Ambient | \(p_0=101325\) Pa, \(\gamma=1.4\), air |

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results --phi0 0.30
```

## Seeded summary (seed=42, φ₀=0.30)

Closed loop restores \(h\to h^\*\) through the mass step by raising φ; open loop settles to a lower gap.

See `results/qsd_sector_closed_loop_summary.json` for exact numbers and full parameter dump.
