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
- **Aurora-QSD AI** (`aurora_qsd/`) — intelligent agent applying QSD + Aurora to quantum computing
- Notebooks and analysis scripts
- Data and circuit files for IBM validation
- This README and paper PDFs

## Aurora-QSD AI

An AI agent that applies QSD stabilization dynamics and the Aurora principle to quantum computing:

```bash
# Run full demonstration
python3 -m aurora_qsd.cli demo

# Check Aurora condition (Γ_lock > Γ_loss)
python3 -m aurora_qsd.cli aurora

# Plan re-preparation for deep circuits
python3 -m aurora_qsd.cli relock --depth 1241

# Analyze measurement counts
python3 -m aurora_qsd.cli analyze --counts '{"00":15000,"11":13000,"01":2000,"10":2000}'

# Natural-language queries
python3 -m aurora_qsd.cli query explain the Aurora principle for quantum circuits
```

**Python API:**

```python
from aurora_qsd import QSDAuroraAgent

agent = QSDAuroraAgent()
agent.query("optimize partition angle for ibm_fez")
agent.analyze_counts({"00": 15000, "11": 13000, "01": 2000, "10": 2000})
agent.plan_relock(depth=1241)
```

**Capabilities:**
- TriDelta covariance decomposition and partition angle analysis
- Aurora condition checking (phase-match faster than dissipate)
- ISS convergence prediction and closed-loop control simulation
- Re-preparation interval advisor (validated on ibm_fez depth 1241)
- QSD circuit construction with periodic re-lock
- Natural-language query routing with structured recommendations

See `examples/aurora_qsd_quantum_example.py` for full integration.

For collaboration, outreach (e.g., SpaceX, academics), or questions on QSD/Aurora framework, contact via X @apmannino or email.

*Updated June 2026 with v30 integrated paper.*