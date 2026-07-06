# Quantum Stabilization Dynamics (QSD): Phase-Bounded Transport

**Reproducibility repository for the QSD framework — Phase-Bounded Transport, TriDelta Geometry, and Aurora-QSD AI extensions.**

**Owner:** Aurora Unified Energy Systems (AURORA UES)  
**Contact:** @apmannino (X) | apmannino@gmail.com  
**Provisional Patent:** #64/035,024

---

## Latest Integrated Version: v31 (June 2026)

**Highlights of v30 → v31 Integration:**

- **Core Theory (Theorems 6 & 7)**: Input-to-State Stability (ISS) bound on closed-loop angular coordinate  
  `|e_t| ≤ ρ^{t/2} |e_0| + D / (1 - √ρ)` for bounded disturbance D and target θ* ∈ (0, π/2).  
  Quantum extension via relative entropy under controlled CPTP maps.

- **IBM `ibm_fez` Full-Chip Hardware Validation (129 qubits)**:
  - Achieved median ZZZ fidelity **+0.911** (3.07× improvement over pilot).
  - θ_source ≈ 22.47° with |Δ tan| = 0.0006.
  - Periodic re-preparation sustains performance to circuit depth **1241** (108k+ gates) with zero ancilla overhead — new ancilla-free error-mitigation strategy.
  - Basin sweep and hysteresis confirm ISS corridor (first hardware proof of Theorem 7).
  - Negative control confirms angle specificity.

- **Third-Harmonic Phase Potential (New Section XXXIII)**:
  - Effective potential V(Θ) = −cos Θ − (1/3)sin(3)
  - Three stable attractors; deepest at θ* satisfying TriLock identity sin(θ*) = cos(3θ*)
  - Basin edges at ±3θ* explain hardware escape thresholds.
  - Mathematical bridge from QSD contraction dynamics to nonlinear optics / third-harmonic generation.

- **Real-Data Pilots**:
  - GOES-16 X9.3 flare: Z_θ,phase = +68.4, KS = 0.941 (strong detection).
  - DSCOVR solar wind: Positive validation.
  - LIGO GW150914: Negative control (no spurious signal).
  - IonQ Forte Enterprise 1 (June 2026): Trapped-ion room-temperature invariants confirmation; cross-platform consistency with Rigetti data.

- **TriDelta Geometry & Heron Closure**: p+ invariant, null-calibrated statistical inference (IAAFT surrogates, Cochran Q, IVW meta-analysis).

- **Target Operating Point**: θ* ≈ 22.474° (refined; preregistered; consistent across hardware, GOES clustering, and geometric derivations). 4.42× enrichment, p < 10^{-80} in solar X-ray data.

**Manuscript**: `QSD Phase Bounded Transport v30 integrated 3.pdf` (v31 delta integrated). Full LaTeX sources in `paper/`.

**Zenodo Reproducibility Archive**: Linked in manuscript (v1.0.3+ workflow active).

---

## Aurora-QSD AI Framework (June 2026 Development)

**Aurora-QSD AI** — Intelligent agent layer combining QSD stabilization principles with adaptive reasoning for quantum systems and beyond.

**Key Capabilities** (available in `aurora_qsd/` package and CLI):
- Aurora condition checking: `Γ_lock > Γ_loss` for phase-bounded transport decisions.
- Re-preparation planning and scheduling for deep circuits (e.g., depth 1241 sustain).
- Natural-language query interface for TriDelta covariance analysis, ISS prediction, and stability diagnostics.
- Extension of TriDelta / TriLock to AI reasoning stability (QSD-AI for Stable Intelligence).
- Python API and CLI: `python3 -m aurora_qsd.cli`

**Branch**: `cursor/aurora-qsd-ai-c793` (active development). Core integration into main planned for v32.

**Applications**: Quantum circuit optimization, error mitigation, grid stability (QSD Grid Stability Analysis), and cross-domain unified reasoning (QSD Unified Framework Vision v1.0).

---

## Geometric Foundations (June 2026)

**Minimal Surfaces & Enneper Geodesics**:
- QSD phase dynamics reinterpreted through differential geometry of minimal surfaces.
- The canonical 22.48° TriDelta angle emerges as an intrinsic member of the Enneper surface geodesic family.
- Curvature flows and geodesic completeness provide new proofs of global convergence and basin stability.
- Fluctuation geometry and equilibrium ΔE=0 now have rigorous Riemannian manifold interpretations.
- Supports basis-invariance and phase-referenced forcing in control design.

This geometric view unifies QSD with loop quantum gravity motifs and relativistic topology gates (future work).

**Related**: Number Theory module — primes interpreted as QSD-stabilized resonant systems (exploratory).

---

## Repository Structure

- `code/` — Core Python reference implementation (single-file consolidated module with all paper math objects + self-tests; Qiskit/IBM Quantum mappings).
- `aurora_qsd/` — Aurora-QSD AI package (CLI, API, condition checkers, planners).
- `notebooks/` — Jupyter analysis, visualization, and tutorials (including basin sweeps, depth scaling, geometric plots).
- `data/` — GOES XRS, DSCOVR, LIGO, IonQ/Rigetti circuit data and logs.
- `paper/` — LaTeX sources for manuscript (v30 integrated + v31 delta sections: XXXII IBM fez, XXXIII Third-Harmonic).
- `results/` & `reports/` — Validation summaries (RESULTS_JUNE*.md, RESULTS_MAY*.md, hardware logs).
- `scripts/` — Pipeline runners (`run_pipeline.sh`, `run_fez_hardware_faithful.sh`, etc.), figure generators.
- `outputs/` — Generated figures, circuit diagrams, statistical plots.
- `docs/` — Additional documentation and integration notes.
- `QSD_Manuscript_v30_Updates_June11.md`, `INTEGRATION_v31_READY.md`, `QSD_Updates_*.md` — Changelogs and merge guides.
- `Makefile`, `requirements.txt`, `pyproject.toml`, `run_pipeline.sh` — Build & reproducibility automation.
- `CITATION.cff`, `LICENSE` — Citation and licensing (Other).

**Testing**: See `TEST.md` for full instructions (updated May/June 2026). Self-tests pass on reference implementation.

**Branches**:
- `main` — Stable reproducibility baseline (v31 integrated).
- `cursor/aurora-qsd-ai-c793` — Aurora-QSD AI and latest agentic extensions.
- `cursor/willow-*` — Willow/Google Quantum specific experiments and gain sweeps.
- Other feature branches for geometric analysis, number theory, and grid applications.

---

## Recent Activity & Commits (as of July 2026)

- **June 15, 2026**: README update + v30 paper summary (main).
- **June 11, 2026**: IBM `ibm_fez` full-chip validation + v31 delta committed.
- **June 4, 2026**: IonQ Forte Enterprise 1 results + June hardware validation added.
- **May 29, 2026**: TriDelta G=∞ confirmed on 3/3 IBM backends (156q scale).
- Ongoing: Geometric minimal surface derivations, QSD-AI framework, Nvidia Quantum outreach (ibm_fez 129-qubit benchmarks shared with Elica Kyoseva), QSD Unified Framework Vision v1.0, Zenodo release workflow refinement.

**Latest push**: July 6, 2026 — Repository synchronization and documentation refresh.

---

## Getting Started & Reproducibility

1. Clone: `git clone https://github.com/apmannino-design/qsd-phase-bounded-transport.git`
2. Install: `pip install -r requirements.txt` (or `pip install -e .` via pyproject.toml)
3. Run full pipeline: `./run_pipeline.sh` or `make all`
4. IBM/Qiskit hardware: See `notebooks/` and `scripts/run_fez_*.sh` (requires IBM Quantum account / AWS Braket for IonQ).
5. Explore AI agent: `python3 -m aurora_qsd.cli --help`

All code, data (anonymized where required), circuits, and statistical protocols are open for verification and extension.

**Zenodo DOI** (latest archive): See manuscript or release assets for persistent reproducibility package.

---

## Roadmap & Outreach

**Next Milestones (v32+)**:
- Full merge of Aurora-QSD AI into main with expanded CLI and multi-backend support.
- Geometric minimal surface figures and Enneper geodesic validation notebooks.
- QSD Number Theory module (prime stabilization proofs).
- Expanded grid stability analysis (PJM AEP data protocol) and space-weather applications.
- Preparation of unified cross-domain manuscript / PRX-style submission.

**Outreach**:
- Active discussions with Nvidia Quantum, IBM Quantum, academic collaborators (Prof. Greene, Rabitz, Ticozzi, Lloyd).
- X/Twitter strategy via @apmannino for community engagement.
- SBIR / funding paths and provisional patent prosecution ongoing.
- Family legacy and IP protection via Aurora Unified Energy Systems corporate structure.

For collaboration proposals, technical feedback, or partnership inquiries (quantum hardware access, theoretical review, commercialization), reach out directly.

---

**This repository embodies the Aurora Unified Energy Systems mission: rigorous, falsifiable, open science advancing phase-stabilized quantum transport and unified dynamical frameworks.**

*Updated July 6, 2026 — Aurora QSD Team*