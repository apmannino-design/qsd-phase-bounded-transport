# QSD: Phase-Bounded Transport

Reproducibility repository for the QSD (Quantum Stabilization Dynamics) research program — observable-targeted control protocols on NISQ hardware.

**Owner:** Aurora Unified Energy Systems LLC
**Contact:** @apmannino (X) | apmannino@gmail.com
**Provisional patent:** #64/035,024

---

## What this is

QSD investigates whether a periodic re-preparation protocol ("depth sunscreen") at a fixed design angle preserves specific multi-qubit Z-correlators under noise. The correct framing is **operator-selective refocusing, not state protection**: at best it preserves a commuting family of Z-observables at a specific angle. Universal stability — protecting non-commuting observables simultaneously — is the job of quantum error correction, not a pulse-level protocol. Nothing here is a QEC replacement.

Whether the angle-specific preservation effect is real is currently an **open question**. The most recent controlled test (July 7, 2026, below) found the QVM-observed angle signature to be a coherent artifact of the circuit unitary, not noise protection. This README reports that finding with the same prominence as any positive result.

## Status at a glance (July 7, 2026)

**Defensible core** — claims we stand behind:
- ISS contraction theorem (Theorems 6–7): `|e_t| ≤ ρ^{t/2}|e_0| + D/(1−√ρ)` for bounded disturbance, with quantum extension via relative entropy under controlled CPTP maps.
- TriDelta decomposition and Heron closure invariant (mathematical results with passing self-tests in `code/`).
- Pre-registered null protocol and the discipline of publishing NULL results.
- IBM empirical anchor: 176-point `ibm_fez` Estimator sweep (job `d8o41uj2d42s73cejsv0`, median std 0.015); 1,800+ completed IBM Quantum jobs across `ibm_fez`, `ibm_marrakesh`, `ibm_kingston`.

**Open questions** — pre-registered, unresolved:
- Is θ-specific ⟨ZZZ⟩ preservation genuine noise protection? Current best evidence says **no** on the Willow QVM (July 7 retention audit). An ideal-referenced hardware test has not yet been run.
- Is π/8 a dynamical attractor or a control setpoint? Basin-sweep protocol queued (`qsd_basin_sweep.py`); differential-sweep hardware data so far: bias-corrected mean 22.331°, Z = −0.98σ (not significant).

**Published negative / NULL results:**
- Willow QVM (willow_pink spec) teleportation echo: **NULL** as pre-registered (z = −0.74 / −0.63).
- `ibm_fez` pre-committed falsification run (90 circuits, 12 qubits): **all three pre-committed tests failed** (PARTIAL_STABLE); π/8 was among the *least* robust angles tested; TriDelta tri-band certification 0/8.
- Ising/TFIM ground-state energy head-to-head: **bare Trotter won** on ΔE.
- July 7, 2026 retention audit: prior "ENDORSABLE" ⟨ZZZ⟩-vs-XY4 verdict **retracted** (details below).

## The design constant

**θ* = arctan(√2 − 1) = π/8 = 22.5° exactly** (half-angle identity: tan(π/8) = √2 − 1). Basin boundary 3θ* = 67.5° exactly.

Earlier materials in this repository stated θ* ≈ 22.47°–22.48° and claimed this was "not π/8." That was an arithmetic error, since corrected; those figures are superseded wherever they appear in older documents. Platform-calibrated settings are distinct empirical quantities and are labeled as such: willow_pink QVM empirical optimum 22.49°; legacy fez campaign setting 22.47° (bias-corrected fez hardware estimate: 22.331°, job `d8b3ln6honmc73cjfa10`).

## July 7, 2026 — Retention audit (read before citing any ⟨ZZZ⟩ preservation result)

A matched-depth XY4 control run (July 5–6) initially returned an "ENDORSABLE" verdict for angle-specific ⟨ZZZ⟩ preservation on the willow_pink QVM (interior line q(6,5)–q(6,7), 14 layers, re-lock/5, 4,000 shots). An independent audit added the measurement the pipeline lacked: the **noiseless ideal ⟨ZZZ⟩ per arm**.

| Arm | Ideal (noiseless) | Noisy (QVM) |
|---|---|---|
| QSD @ 22.49° | −0.19 | −0.31 |
| QSD @ +70° (wrong) | +0.98 | +0.51 |
| XY4 matched | +0.35 | +0.29 |

Findings:
1. **The angle gap lives in the noiseless unitary.** Ideal gap 1.16 > noisy gap 0.81 — noise *shrinks* the signature. The θ-dependence is coherent circuit behavior, not protection.
2. **There is no target signal at θ*.** Ideal ⟨ZZZ⟩ = −0.19; a θ-sweep shows the noisy value pinned near −0.45 for all θ ≤ 20° even where the ideal is +0.97. The measured −0.31 mostly reflects the noise channel's fixed point.
3. **The XY4 control was defective.** A dropped 12th pulse made each control layer exactly I⊗I⊗Y up to global phase — a repeated Y-rotation, not dynamical decoupling.

**Verdict: COHERENT_ARTIFACT. The ENDORSABLE claim is retracted.** The scoring pipeline now requires an ideal reference (retention R = noisy/ideal), a minimum target signal |ideal(θ*)| ≥ 0.5, and a repaired XY4 control before any protection claim. Full data, sweep table, and reproduction script: `RESULTS_JULY07_2026_RETENTION_AUDIT.md` and `aurora_qsd/quantum/retention_audit.py` (experiment branch).

## Where this is and isn't useful

Candidate fits (contingent on protection surviving ideal-referenced tests): Z-diagonal variational readouts, ZZ/ZZZ physics correlators, stabilizer-adjacent measurements, and **chip-health monitoring** — a θ-resolved response curve only needs to be sharp and reproducible to serve as a calibration probe, which makes it the strongest near-term application regardless of the protection question.

Poor fits, stated explicitly: Ising/TFIM ground-state energy (bare Trotter won), echo/phase estimation (NULL on Willow), X-heavy arbitrary circuits, long-range entanglement, magic states / T gates / fault tolerance (different problem entirely).

## Repository structure

- `code/` — consolidated reference implementation of the paper's mathematical objects, with self-tests (29 passing).
- `aurora_qsd/` (feature branches) — experiment package: Willow/cirq modules, IBM/Qiskit cell protocols, CLI tooling.
- `notebooks/`, `scripts/` — analysis and pipeline runners.
- `data/` — instrument datasets used in early exploratory signal-processing pilots (GOES-16, DSCOVR, LIGO). These pilots are exploratory only and make no validated physical claims.
- `paper/` — LaTeX sources.
- `RESULTS_*.md` — dated, immutable result logs including NULL and failed runs.

**Branches:** `main` (stable baseline) · `cursor/zzz-xy4-control-c793` (⟨ZZZ⟩/XY4 experiments + retention audit) · other `cursor/willow-*` feature branches.

## Reproducibility

1. `git clone https://github.com/apmannino-design/qsd-phase-bounded-transport.git`
2. `pip install -r requirements.txt`
3. Willow QVM experiments additionally need: `pip install cirq-google qsimcirq` (QVM specs for `willow_pink` ship with cirq-google ≥ 1.7).
4. Core self-tests: see `TEST.md`. Retention audit: `python3 -m aurora_qsd.quantum.retention_audit` (experiment branch).

## Corrections & superseded claims

- **July 7, 2026** — "ENDORSABLE" ⟨ZZZ⟩-preservation-vs-XY4 verdict retracted: coherent artifact + defective control (audit above).
- **June 2026** — θ* = 22.47°/22.48° ("not π/8") corrected to θ* = π/8 = 22.5° exactly; basin edge 67.5° exactly.
- **June 2026** — `ibm_fez` deep-circuit claims re-scored under the pre-committed falsification protocol: PARTIAL_STABLE (0/8 tri-band); earlier "hardware validation" language withdrawn.
- **June 2026** — Cross-domain framing (solar/geomagnetic detections, gravitational-wave analysis, unification claims) moved out of the defensible core; retained in `data/` and old logs as exploratory history only.

## Roadmap (near term)

- Repaired matched-depth XY4 control + ideal-referenced retention scoring on QVM (done; this audit) → repeat on IBM hardware single line with pre-registered thresholds.
- Basin sweep to distinguish attractor vs setpoint (dθ/d(perturb), r²).
- θ-resolved chip-health probe characterization (reproducibility across lines/days).

---

*Rigor here means pre-registered thresholds, published NULLs, and dated retractions. Updated July 7, 2026.*