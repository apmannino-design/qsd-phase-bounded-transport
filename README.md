<!-- CDN purge May 23 2026 -->
# Quantum Stabilization Dynamics (QSD)

**A Unified Framework from Field-Theoretic Foundations to Input-to-State Stability**

**Version: v11** — May 23, 2026  
**Author:** Alexander P. Mannino  
Aurora Unified Energy Systems · Philadelphia, Pennsylvania  
Provisional Patent #64/035,024 (April 10, 2026)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18574110.svg)](https://doi.org/10.5281/zenodo.18574110)

-----

## Overview

Quantum Stabilization Dynamics (QSD) is a framework for monitoring and controlling multichannel dynamical systems — quantum processors, solar-wind plasma, gravitational-wave detectors, optical links. Starting from a scalar coherence-field Lagrangian, it derives through four successive layers a closed-form stability bound: angular error decays geometrically and stays bounded under any external disturbance.

The central structural result proves that the TriDelta covariance coordinates are exact algebraic functions of two-node sync-model parameters, and that a unique operating angle θ* = 22.48° emerges from the TriLock balance condition. IBM quantum hardware (ibm_fez, 156-qubit) independently measures θ_source = 22.47° across 9/9 positive-gain passes — within measurement precision of the theoretical value.

Validation covers nine real-instrument events across five domains: solar X-rays, solar wind, geomagnetic activity, gravitational waves, and optical links. Heterogeneity is zero (I² = 0%), pooled signal Zθ = +36.2 ± 2.4. Every free parameter is explicitly identified and accounted for.

-----

## Key Results

- **Theorem 5.4 (ISS):** ‖et‖ ≤ ρ^(t/2)‖e0‖ + D/(1−√ρ) under any bounded disturbance, for any θ* ∈ (0, π/2)
- **Theorem 3.2 (Bridge):** TriDelta coordinates are exact algebraic functions of sync-model parameters; TriLock selects θ* = arctan(√2−1) = 22.500°
- **Theorem 5.8 (Quantum ISS):** Relative-entropy contraction under controlled CPTP maps; η̂ = 0.083 ± 0.006 per Trotter layer (IBM ibm_fez)
- **Heron Closure (p+):** Model-free geometric diagnostic of projector balance, independent of θ*
- **Nine-event validation:** Cochran Q = 4.17, I² = 0%, IVW pooled Zθ = +36.2 ± 2.4

-----

## Validation Summary

|Event                  |Domain       |Zθ   |KS   |Pass     |
|-----------------------|-------------|-----|-----|---------|
|GOES X9.3 (2017-09-06) |Solar XRS    |+68.4|0.941|✓        |
|GOES X8.2 (2017-09-10) |Solar XRS    |+54.7|0.912|✓        |
|GOES X2.2 (2022-03-30) |Solar XRS    |+31.9|0.874|✓        |
|GOES M5.5 (2023-07-18) |Solar XRS    |+12.4|0.641|✓        |
|GOES M1.0 (2024-02-09) |Solar XRS    |+4.1 |0.317|✓        |
|GOES quiet (2017-09-01)|Solar XRS    |−0.3 |0.042|neg. ctrl|
|DSCOVR CME (2017-09-08)|Solar wind   |+7.2 |0.481|✓        |
|LIGO glitch (O3, 2019) |GW strain    |−1.1 |0.061|neg. ctrl|
|Geomag. substorm       |Geomagnetic  |+5.8 |0.604|✓        |
|Optical link           |Optical comms|+10.1|0.538|✓        |

-----

## Repository Structure

```
code/        Core QSD Python implementation
circuits/    IBM quantum circuits (trilock_scan.py)
notebooks/   Jupyter notebooks for all pilots
paper/       Manuscript v11 PDF and LaTeX source
data/        Supporting datasets
results/     Pipeline outputs and figures
outputs/     Processed results
scripts/     Pipeline runners
review/      Peer-review rubric and response-to-reviewers template
reports/     Validation reports
```

-----

## Installation

```bash
pip install -r requirements.txt
```

-----

## Usage

See `run_pipeline.sh` and `notebooks/` for examples on GOES, LIGO, DSCOVR, IBM quantum, and synthetic surrogates.

-----

## IBM Quantum Hardware

- **Job ID:** d58nobpsmlfc739jqrmg
- **Backend:** ibm_fez (156-qubit Eagle)
- **Circuits:** 12 circuits × 600 shots · Trotter depths d ∈ {2, 4, 6, 8, 10, 12}
- **Optimal corridor:** θ_source = 22.47°, θ_sync = 67.53°
- **Reproducible via:** Qiskit Runtime SamplerV2 — see `circuits/trilock_scan.py`

-----

## Data Sources

|Dataset             |URL                                            |
|--------------------|-----------------------------------------------|
|GOES-16 XRS L2      |<https://www.ngdc.noaa.gov/stp/satellite/goes/>|
|DSCOVR L2 solar wind|<https://www.ngdc.noaa.gov/dscovr/>            |
|LIGO GWOSC          |<https://gwosc.org/eventapi/html/allevents/>   |
|IBM Quantum         |<https://quantum.ibm.com>                      |

-----

## Citation

```bibtex
@misc{mannino2026qsd,
  author  = {Mannino, Alexander P.},
  title   = {Quantum Stabilization Dynamics: A Unified Framework from
             Field-Theoretic Foundations to Input-to-State Stability},
  year    = {2026},
  month   = {May},
  version = {11},
  doi     = {10.5281/zenodo.18574110},
  url     = {https://github.com/apmannino-design/qsd-phase-bounded-transport}
}
```

-----

## License

MIT License — see LICENSE file.

*README updated to v11 — May 23, 2026*