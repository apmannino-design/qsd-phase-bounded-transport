# Cascaded NFAL Levitator: Outer Position + QSD Sector (Oct 11, 2026)

**Scope:** Reduced-order scientific control study. Not hardware validation.

**Code:** `code/nfal_physics.py`, `code/qsd_sector_closed_loop.py`

## Architecture

Inner residual/phase law unchanged in structure; improvements sit around it.

**Plant (gap-dependent coupling):**
\[
C(\phi,h)=\frac{\gamma(\gamma+1)}{8}\frac{(a_{\max}\sin\phi)^{2}p_{0}}{h^{2}}A,\quad
m\ddot h=C(\phi,h)-mg-b\dot h+d_{\mathrm{ext}}
\]

**Outer position/velocity loop** (stops force-only drift):
\[
r=( \hat F-mg)+K_p\,mg\,\frac{h-h^\*}{h^\*}+K_d\,mg\,\frac{v}{v_{\mathrm{scale}}}
\]

**Inner QSD sector** on \(r_n=r/mg\):
\[
\Delta E=\log(1+|r_n^{\mathrm{filt}}|),\quad
\phi^{+}=\mathrm{clip}_{\mathrm{rate}}\bigl(\phi-K\,\mathrm{sat}_\alpha(r_n)\bigr)
\]
with back-calculation anti-windup.

**Lock-in:** freeze φ when filtered ΔE and |v| are both small; unlock on corridor exit.

**Safety:** gap floor/ceiling interlocks, hard phase-rate limit.

**Disturbances:** thermal phase walk, gap/force sensor noise, mass step, impulse.

## Nominal plant

| Quantity | Value |
|---|---|
| Drive | 28 kHz |
| Plate radius | 20 mm |
| Mass | 12 g (+3 g @ 1–2.5 s) |
| \(h^\*\) | 80 μm |
| \(a_{\max}\) | ≈ 9.8 μm |
| \(C_0/Mg\) margin | ≈ 6.8 |

## Reproduce

```bash
python3 code/qsd_sector_closed_loop.py --self-test
python3 code/qsd_sector_closed_loop.py --out-dir results --phi0 0.30
```

## Seeded metrics (seed=42, φ₀=0.30)

Closed loop (typical): time-to-lock ~0.2 s, hold RMS < 5 μm, step peak ~13 μm with ~10 ms recovery; open loop drifts to ~62 μm and does not lock.

See `results/qsd_sector_closed_loop_summary.json` for the full dump.
