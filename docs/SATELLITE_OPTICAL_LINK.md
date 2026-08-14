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
| Modem | Uncoded OOK / BPSK BER from electrical SNR; Hamming(7,4) optional | Not CCSDS, not SDA |
| Optical PLL | Costas-rate (20 kHz) loop-referred phase: Wiener linewidth + residual Doppler | Not a 1550 nm field propagator |
| Relay | LEO-A → LEO-B ISL, store-and-forward, LEO-B → OGS | Two hops, one plane |

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
| T6 | One-step ISS | ≥95% of QSD samples satisfy \|e_{t+1}\| ≤ √ρ \|e_t\| + D (the induction step; T2 is the unfolded envelope) |

NULL is a valid, publishable outcome. T3 in particular does **not** claim QSD beats industrial PAT; it asks whether the ISS law is non-inferior to a reasonably tuned PID on this plant.

## v0.2 — PLL, FEC, two-hop relay (14 Aug 2026)

The first campaign left T2 vacuous (unfolded envelope too loose) and had no actual carrier lock. v0.2 adds:

1. **T6** — one-step ISS certificate (Theorem 6 induction step). This can fail; T2 still reports the unfolded envelope.
2. **Optical PLL** at 20 kHz (loop-referred, Δν = 300 Hz) with Doppler feedforward. Pre-registered P1–P5. Negative control locks to the quadrature well (φ = π/2), which nulls BPSK.
3. **Hamming(7,4)** on the packet interface.
4. **Two-hop relay** LEO-A → LEO-B → OGS, store-and-forward, optional FEC per hop (R1–R3).

On this PLL plant QSD beat PI on residual phase and cycle slips (P1–P2 PASS). That does **not** reverse the PAT finding that PI is the better 500 Hz fine-stage tracker. Different loop rate, different disturbance.

## Matched-bandwidth test

`python -m aurora_qsd.optical --matched-only --seconds 4 --seed 0`

Pre-registered G1–G6: set PI `kp = 0`, `ki·dt = 1−√ρ`, and compare to full QSD and stripped ISS (no F(Θ), no re-lock). Hypothesis: the PAT/PLL reversal was gain scaling.

Result (seed 0): stripped ISS **equals** matched PI on PAT (8.302 μrad, G6a rel gap 0). PLL stripped vs matched PI within 15% (G6b). Full QSD still 18% better than matched PI on PLL (G5b NULL) — decorations, not θ*. Unmatched PI remains the best 500 Hz tracker. Details in `RESULTS_OPTICAL_LINK_PROTOTYPE.md`.

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
from aurora_qsd.optical import OpticalTerminal, TwoHopRelay
term = OpticalTerminal(fec=True)
print(term.ping("HELLO FROM LEO-1"))
print(TwoHopRelay(fec=True).send(b"HELLO FROM LEO-1"))
```

## What this is not

- Not a claim that θ* = 22.5° is an optical alignment angle.
- Not a claim that QSD replaces Tesat / Mynaric / SDA PAT.
- Not atmospheric wave-optics, not a CCSDS waveform, not a flight software load.
- Not evidence for the retracted ⟨ZZZ⟩-preservation result.

If a later hardware-in-the-loop test is run, it should keep these same five pre-registered tests and an ideal (noiseless plant) reference, in the spirit of the July 7 audit.
