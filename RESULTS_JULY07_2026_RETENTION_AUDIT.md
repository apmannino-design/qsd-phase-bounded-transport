# RESULTS — July 7, 2026: Retention audit of the ⟨ZZZ⟩ preservation / XY4 control run

**Status: COHERENT_ARTIFACT. The July 5–6 "ENDORSABLE" verdict is retracted.**

## What was tested

The `run_zzz_preservation_benchmark` pipeline (branch `cursor/zzz-xy4-control-c793`) scored three arms on the willow_pink QVM — QSD depth sunscreen @ θ = 22.49°, QSD @ θ+70° (negative control), matched-depth XY4 — using only arm-vs-arm gaps of noisy ⟨ZZZ⟩. No criterion referenced the noiseless ideal. This audit adds that reference.

**Setup (identical to the original run):** interior line q(6,5)–q(6,6)–q(6,7), 14 layers, re-lock every 5, 4,000 shots, willow_pink QVM (cirq-google 1.7.0, qsim backend), circuits built by the repo's own `build_depth_sunscreen_circuit` and `build_xy4_matched_circuit`.

**Reproduction check:** audit noisy values −0.31 / +0.51 / +0.29 match the original run's −0.30 / +0.51 / +0.29 within shot noise (σ ≈ 0.016). Same experiment.

## Headline table (4,000 shots)

| Arm | Ideal ⟨ZZZ⟩ (statevector) | Noisy ⟨ZZZ⟩ (QVM) | R = noisy/ideal |
|---|---|---|---|
| QSD @ 22.49° | −0.1877 | −0.3075 | 1.64 |
| QSD @ 92.49° (wrong) | +0.9769 | +0.5125 | 0.52 |
| XY4 matched | +0.3524 | +0.2935 | 0.83 |

Ideal values verified through two independent simulator paths (statevector and density-matrix).

## θ-sweep (QSD arm, 1,000 shots per point)

| θ (deg) | ideal | noisy |
|---|---|---|
| 2.00 | +0.9663 | −0.4200 |
| 8.00 | +0.5568 | −0.4720 |
| 14.00 | +0.0799 | −0.4780 |
| 20.00 | −0.1561 | −0.4220 |
| 22.49 | −0.1877 | −0.2780 |
| 26.00 | −0.1788 | −0.2800 |
| 32.00 | −0.0209 | −0.1560 |
| 38.00 | +0.2570 | +0.0900 |
| 44.00 | +0.4798 | +0.2160 |
| 50.00 | +0.5280 | +0.3080 |
| 56.00 | +0.4981 | +0.2420 |
| 62.00 | +0.4975 | +0.1660 |
| 68.00 | +0.4935 | −0.0020 |
| 74.00 | +0.5451 | +0.0580 |
| 80.00 | +0.7339 | +0.2300 |
| 86.00 | +0.9459 | +0.4560 |
| 92.49 | +0.9769 | +0.5340 |

## Findings

1. **The angle signature is coherent, not protective.** Ideal gap |ZZZ(θ*) − ZZZ(wrong)| = 1.16 exceeds the noisy gap 0.81. Noise attenuates the signature; it does not create it. All three original endorsement bars (interior ≥ 0.5, vs-XY4 ≥ 0.05, angle-specificity) pass on differences already present in the noiseless unitary.
2. **No target signal at θ*.** The ideal circuit at the "optimal" angle outputs ⟨ZZZ⟩ = −0.19; there is essentially nothing to preserve. The sweep shows noisy ⟨ZZZ⟩ pinned near −0.45 for θ ≤ 20° even where the ideal is +0.97 (sign inversion at θ = 2°) — the deep-circuit noise channel has a fixed point near −0.45 that dominates the low-θ region. The measured −0.31 at θ* is mostly that fixed point, coincidentally adjacent to a small negative ideal.
3. **The XY4 control was not a DD sequence.** `_xy4_body_ops` dropped the 12th pulse to match a 1q budget; the resulting per-layer unitary is exactly I⊗I⊗Y up to global phase (verified against the layer unitary). The "serious DD baseline" was a repeated Y-rotation on q2 with ideal ⟨ZZZ⟩ = +0.35.

## Corrective actions (this commit set)

- `_xy4_body_ops` repaired: three complete XY4 blocks (12 pulses/layer; the +1 1q-per-layer asymmetry vs QSD's 11 is documented in gate-budget metadata alongside QSD's +4 2q/layer).
- `run_zzz_preservation_benchmark` now computes the noiseless ideal per arm and scores retention. New verdict ladder: `NO_TARGET_SIGNAL` (|ideal(θ*)| < 0.5) → `COHERENT_ARTIFACT` (ideal gap ≥ noisy gap) → `NO_PROTECTION_ADVANTAGE` (retention advantage < 0.10 or R outside (0, 1.05]) → `PROTECTION_CANDIDATE`. Nothing is marked endorsable from simulation alone.
- `aurora_qsd/quantum/retention_audit.py` added: standalone re-run of this audit (`python3 -m aurora_qsd.quantum.retention_audit`).
- `constants.py`: the source comment claiming arctan(√2−1) ≈ 22.4794° corrected — the identity gives π/8 = 22.5° exactly; this comment is the origin of the 22.47/22.48 lineage. Willow platform setting updated 22.48° → 22.49° (calibrated QVM optimum, distinct from the design constant).

## What would change the verdict

A protection claim requires, at minimum: |ideal(θ*)| ≥ 0.5 (a signal worth preserving), retention R(θ*) ≥ R(repaired XY4) + 0.10 with R ∈ (0, 1.05], and a retention peak at θ* in the sweep — pre-registered before the run, on hardware, with the ideal computed from the as-compiled circuit.

*Audit run July 7, 2026. Original run data preserved unmodified in branch history.*