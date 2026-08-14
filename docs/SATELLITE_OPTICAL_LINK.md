# Satellite optical-link prototype

**Status:** simulation prototype. Not a hardware result. Not a flight waveform.

This package applies QSD Theorem 6 (ISS contraction under bounded disturbance) and the third-harmonic phase potential of Section XXXIII as a **pointing / phase-lock controller** on a physically standard free-space optical (FSO) channel. The mapping is analogical: θ* is a control-Lyapunov coordinate whose well is placed at **boresight**, not a 22.5° beam offset (that would dump the link).

The July 7 2026 retention audit still stands: nothing here revives a ⟨ZZZ⟩-preservation claim. ISS is a control-theoretic bound; using it on a PAT loop does not require the quantum protocol to be a noise-protection mechanism.

## What is simulated

| Piece | Model | Honesty bound |
|---|---|---|
| Orbits | Circular Keplerian LEO, 550 km SSO-class | No J2, no drag, no ephemeris |
| ISL geometry | Two coplanar sats, 20° true-anomaly offset (~2400 km) | Single plane |
| Downlink | OGS at the t=0 sub-satellite point, Haleakalā-class altitude (3055 m) | Not a real Haleakalā pass |
| Beam | Far-field Gaussian, 1550 nm, 8 cm Tx (40 cm OGS Rx) | No wave-optics, no AO |
| Pointing loss | exp(−2 (θ_err / θ_div)²) | Single-mode Gaussian |
| Atmosphere | Beer-Lambert + HV-5/7 Rytov σ_I² + lognormal fades | Engineering approximation |
| PAT plant | 2-axis 2nd-order FSM, 200 Hz, ζ=0.7 | No reaction-wheel harmonics, no gyro bias |
| Modem | Uncoded OOK / BPSK BER from electrical SNR | No FEC, no CCSDS, no SDA |

Default terminal: 1 W, 8 cm, 70% optical efficiency, 1 Gbps ISL / 10 Gbps downlink, PIN-class NEP. These are TESAT/Mynaric/TBIRD-family engineering numbers, not a specific flight unit.

## Controllers (fair plant, same disturbance)

1. **open** — FSM parked. Residual = platform jitter.
2. **pid** — classical type-1 PD/PID fine stage.
3. **qsd** — type-1 ISS step `cmd ← cmd + (1−√ρ) e` plus a restoring kick from F(Θ) and periodic re-lock pulses. Coarse acquisition outside the 200 μrad basin.
4. **qsd_wrong** — negative control: same law, lock point offset 40 μrad off boresight.

## Pre-registered tests

| ID | Hypothesis | Pass rule |
|---|---|---|
| T1 | QSD beats open-loop | mean residual(QSD) < mean residual(open) |
| T2 | ISS certificate | ≥95% of QSD samples under the Theorem 6 envelope, and the terminal bound is not vacuous (≤ 2× open-loop RMS) |
| T3 | Non-inferior availability vs PID | avail(QSD) ≥ avail(PID) − 2 percentage points |
| T4 | Acquisition | QSD time-to-12 μrad hold (20 samples) ≤ PID; NULL if neither acquires |
| T5 | Wrong well is worse | mean residual(QSD) < mean residual(wrong) |

NULL is a valid, publishable outcome. T3 in particular does **not** claim QSD beats industrial PAT; it asks whether the ISS law is non-inferior to a reasonably tuned PID on this plant.

## Run

```bash
python -m aurora_qsd.optical --all --seconds 4 --seed 0
# or
python examples/satellite_optical_link.py --scenario isl
python -m unittest tests.test_satellite_optical_link
```

Artifacts land in `results/optical/` (`optical_link_summary.csv`, `optical_link_verdicts.csv`, timeseries, figures).

Packet demo:

```python
from aurora_qsd.optical import OpticalTerminal
term = OpticalTerminal()
print(term.ping("HELLO FROM LEO-1"))
```

## What this is not

- Not a claim that θ* = 22.5° is an optical alignment angle.
- Not a claim that QSD replaces Tesat / Mynaric / SDA PAT.
- Not atmospheric wave-optics, not a CCSDS waveform, not a flight software load.
- Not evidence for the retracted ⟨ZZZ⟩-preservation result.

If a later hardware-in-the-loop test is run, it should keep these same five pre-registered tests and an ideal (noiseless plant) reference, in the spirit of the July 7 audit.
