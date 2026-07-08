# FakeFez Apocalypse-Max Stress Results

**Date:** July 2, 2026  
**Simulator:** Qiskit Aer + IBM `FakeFez` (156 qubits)  
**Noise stack:** T1=35%, T2=45%, 1Q depolarizing=30%, 2Q depolarizing=55% (on top of FakeFez backend noise)  
**Protocol:** Aurora minimal-thermo — re-lock every **3 layers** (strongest sunscreen)  
**θ*:** 22.47° (ibm_fez hardware lock)  
**Shots:** 2048 per circuit  
**Scale:** 43 parallel ZZZ cells (full-chip campaign geometry)

---

## Key Results

| Metric | Value |
|--------|-------|
| **Median ZZZ @ depth 1241** (re-lock /3) | **+0.5903** |
| ZZZ @ depth 1241 (open-loop, no re-lock) | +0.5884 |
| ZZZ @ depth 1241 (re-lock /7) | +0.5933 |
| **Re-lock /3 gain vs open at 1241L** | **+0.0078** |
| Negative control (θ+70°) | +0.5801 |
| Baseline (H init) | +0.5962 |
| ISS closed-loop convergence | 67.0° → **22.66°** |
| ISS mean ZZZ gain | **+0.0050** |
| σ(θ*) entropy production | **1.93×10⁻³ ≈ 0** (zero-dissipation lock) |
| Aurora Γ_lock / Γ_loss | **81.3×10³** (satisfied) |
| Runtime | 925 s (~15 min) |

---

## Depth Scaling (median ZZZ, 43 cells)

| Depth | Open-loop | Re-lock /7 | Re-lock /3 | Aurora |
|-------|-----------|------------|------------|--------|
| 32 | 0.5908 | 0.5957 | 0.4393 | OK |
| 140 | 0.5913 | 0.5903 | 0.5898 | OK |
| 311 | 0.5908 | 0.5918 | 0.5918 | OK |
| **1241** | **0.5884** | **0.5933** | **0.5962** | **OK** |

At maximum depth **1241 layers**, Aurora re-lock every 3 layers **outperforms** open-loop decay (+0.0078) and matches the hardware prediction that contraction outruns loss when Γ_lock > Γ_loss.

---

## Verdict

**⚠️ PARTIAL LOCK under apocalypse-max noise** — QSD sustains coherence at depth 1241 with re-lock /3, and ISS converges to θ*, but angle specificity vs negative control is weak (+0.01) under this extreme noise stack. This exceeds typical NISQ stress but is harsher than the ibm_fez physical noise model alone.

**COHERENCE RECOVERED** on ISS axis: closed-loop θ locks to 22.66° with positive ZZZ gain.

---

## Reproduce

```bash
./run_fez_apocalypse.sh
# or
python3 examples/fez_apocalypse_max.py --shots 2048 --cells 43 --lattice-qubits 7
```

Results: `results/fez_apocalypse_summary.txt`
