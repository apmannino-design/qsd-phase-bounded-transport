# Quantum Stabilization Dynamics (QSD): Phase-Bounded Transport

**Reproducibility repository for the QSD framework.**

**Latest Paper Version: v30 Integrated (May 2026)**

**File:** `QSD Phase Bounded Transport v30 integrated 3.pdf`

**Key Highlights of v30:**
- Central result: Input-to-State Stability (ISS) bound on the closed-loop angular coordinate (Theorem 6): 
  \|e_t\| ≤ ρ^{t/2} \|e_0\| + D / (1 - √ρ) for any bounded disturbance D and any target θ* ∈ (0, π/2).
- Quantum extension (Theorem 7): Relative entropy ISS under controlled CPTP maps.
- IBM ibm_fez hardware validation: θ_source = 22.47° (|Δtan| = 0.0006), 3× improvement in median ZZZ to +0.911; periodic re-preparation sustains performance at circuit depth 1241.
- Real-data pilots: GOES-16 X9.3 flare (Z_θ,phase = +68.4, KS=0.941); DSCOVR solar wind (positive); LIGO GW150914 (negative control).
- TriDelta geometry, Heron closure invariant (p+), null-calibrated statistical inference.
- θ* = 22.48° (preregistered; theoretically motivated from TriLock Δ_J = Δ_X and tetrahedral projection; hardware-consistent).
- All code, data, circuits openly available here. Zenodo DOI referenced in paper.

**Previous versions and full manuscript available in the repo.**

**Structure:**
- Python reference implementation
- Notebooks and analysis scripts
- Data and circuit files for IBM validation
- This README and paper PDFs

For collaboration, outreach (e.g., SpaceX, academics), or questions on QSD/Aurora framework, contact via X @apmannino or email.

*Updated June 2026 with v30 integrated paper.*