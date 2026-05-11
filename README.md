# Quantum Stabilization Dynamics (QSD)

**Covariance-Geometric Transport and Input-to-State Stability: Phase-Bounded Transport**

**Version: V103** — May 2026

**Author:** Alexander P. Mannino  
Philadelphia, Pennsylvania, United States of America

## Abstract

Quantum Stabilization Dynamics (QSD) is a geometric framework for stabilizing fluctuation-energy redistribution in multichannel dynamical systems. The central result (Theorem 5) is an input-to-state stability (ISS) bound

\|e_t\| \le \rho^{t/2} \|e_0\| + \frac{D}{1 - \sqrt{\rho}}

on the closed-loop angular error under sector-bounded residual feedback. A Heron closure invariant certifies geometric consistency of the covariance partition independently of any reference angle. The framework lifts to quantum states evolving under controlled CPTP maps, recovering the same ISS structure in quantum relative entropy (Theorem 7); the classical pipeline is the abelian-algebra restriction. All results hold for any target angle \theta^* \in (0, \pi/2).

The observable pipeline decomposes a finite-window covariance \Sigma_t via orthogonal projectors P_J, P_R into three scalar coordinates—the TriDelta (\Delta_J, \Delta_L, \Delta_X)—supporting a normalized energy coordinate \Delta E = \sqrt{\mathrm{Tr} \Sigma_t / M} and a partition angle \theta = \arctan(\Delta_J / R). Three real-data pilots are presented: GOES-16 X9.3 flare (Z_{\theta,phase} = +68.4, KS = 0.941, positive); DSCOVR solar wind (Z_{\theta,phase} = +4.7, KS = 0.312, positive in a distinct physical domain); and LIGO GW150914 (Z_{\theta,phase} = -0.8, KS = 0.073, negative control).

Three synthetic surrogates provide controlled baseline validation. Domain-specific empirical partition angles (62.1° GOES, 44.3° DSCOVR, 29.8° LIGO) reflect projector choice and physical coupling structure in each domain.

The value \theta^* = 22.48° is a theoretically motivated control reference derived from geometric symmetry projection (Remark 11) and the explicit basis of Provisional Patent #64/035,024. By "theoretically motivated control reference" we mean a mathematically natural feedback target, not an empirically validated universal constant. No claim is made that 22.48° is a natural attractor in real data; that hypothesis is the subject of the pre-registered companion study.

Companion validation closes three gaps: (i) a Cochran-Q heterogeneity analysis across four real datasets (Q = 2.91, p = 0.41, I^2 = 0%) confirms null-separation replication across physically independent domains; (ii) an ibm_fez quantum-processor demonstration (12 circuits × 600 shots) shows the purity proxy \hat{P}_k is non-increasing with Trotter depth, consistent with Theorem 7; and (iii) a direct QSD versus MEWMA and PCA benchmark confirms the methods are complementary, with QSD providing superior heavy-tail robustness (detection rate 0.88 vs 0.52 at \nu = 2) and competitive ROC performance on angular bursts. Simulated-feedback validation on real GOES-16 and DSCOVR records yields survival-fraction improvements of +0.329 and +0.188 respectively (paired block bootstrap, p < 10^{-4}). An eight-event empirical expansion (I^2 = 0% across six positive controls) and a complete reproducibility box complete the manuscript.

## Repository Contents

- `code/`: Core QSD Python implementation
- `notebooks/`: Jupyter notebooks for pilots and validation
- `paper/`: Manuscript source (qsd_v24_arxiv.tex) and latest PDF V103
- `data/`, `results/`, `outputs/`: Supporting datasets and figures
- `scripts/`: Pipeline runners

## Key Results

- **Theorem 5 (ISS)**: Closed-loop angular error bound for any bounded disturbance.
- **Theorem 6 (Quantum ISS)**: Relative-entropy contraction under controlled CPTP maps.
- **Heron Closure**: Model-free geometric consistency diagnostic (p_+ independent of \theta^*).
- **Null Protocol**: Phase, block, and channel-shuffle falsification tests with cross-domain pooling.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

See `run_pipeline.sh` and notebooks for examples on GOES, LIGO, DSCOVR, and synthetic surrogates.

## Citation

Please cite the manuscript (V103) and the Zenodo release for the reference implementation.

## License

See LICENSE file.

*This README updated to V103 on May 11, 2026.*