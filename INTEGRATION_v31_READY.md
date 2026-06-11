# QSD Manuscript v31 Integration — Ready on GitHub (June 11, 2026)

**Base**: v30 PDF (`Quantum_Stabilization_Dynamics__Phase_Bounded_Transport__30_.pdf`)
**Delta added**: Full `ibm_fez` hardware validation campaign + Third-Harmonic Phase Potential section

## Files now in repo for v31 build

- `paper/Section_XXXII_IBM_ibm_fez_Hardware_Validation.tex` — Complete replacement for old short pilot section (3 subsections + 2 tables)
- `paper/Section_XXXIII_Third_Harmonic_Phase_Potential.tex` — New section immediately after XXXII
- `RESULTS_JUNE11_2026_IBM_ibm_fez_Hardware_Validation.md` — Full narrative, tables, job IDs, stats, and reproducibility archive (lift directly into paper or Zenodo)
- `QSD_Manuscript_v30_Updates_June11.md` — Exact one-line abstract insertion, Table 6 rows (LaTeX fragment), conclusion paragraph, and integration checklist

## Quick merge instructions (for your local v30 .tex source)

1. Replace the entire old Section XXXII block with the content of `paper/Section_XXXII_IBM_ibm_fez_Hardware_Validation.tex`
2. Insert `paper/Section_XXXIII_Third_Harmonic_Phase_Potential.tex` right after the new XXXII
3. In the Abstract, append the exact sentence from `QSD_Manuscript_v30_Updates_June11.md` after the existing ibm_fez pilot line
4. In Table 6 (Parameter Accounting), add the 5 new rows (basin sweep, optimized angle, full-chip, sunscreen interval, max depth) using the LaTeX fragment provided
5. Append the new paragraph to the Conclusion (Section XXXIV)
6. Re-number subsequent sections if needed
7. Add cross-references to the new tables (fez_fullchip, depth_scaling) and figures (to be added)

## Key new scientific content

**Section XXXII (A–C)**:
- Basin sweep (5 cells, 20 pts): locked/escape/recovery hysteresis → first hardware proof of ISS corridor (Theorem 7)
- 43-cell full-chip (129Q, 5000 shots): median ZZZ = **+0.911** (3.07× boost from pilot +0.297); negative control +0.477 confirms angle specificity
- Depth scaling + sunscreen protocol: sustains median **+0.672** at depth 1241 (108,489 gates) with zero ancilla overhead → new ancilla-free error-mitigation strategy

**Section XXXIII**:
- Effective potential V(Θ) = −cos Θ − (1/3)sin(3Θ)
- Three stable attractors; deepest at θ* satisfying the TriLock identity sin(θ*) = cos(3θ*)
- Basin edges exactly at ±3θ* → explains escape thresholds seen on hardware
- Direct mathematical bridge from QSD contraction dynamics to nonlinear optics / third-harmonic generation

All data, job patterns, statistical tests, and code references are in the RESULTS file and ready for the reproducibility archive (Zenodo v1.0.3).

**Status**: v31 source delta is complete and committed. Pull, merge into your local v30 .tex, recompile, and the newest paper (with full-chip hardware validation arc closed) is ready for submission/outreach.

Next: figures for basin surface, depth-scaling curves, and V(Θ) potential can be generated on request.