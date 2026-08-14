# Satellite optical-link prototype — first campaign (14 Aug 2026)

**Status:** simulation only. Not a hardware result. Not a flight waveform.

Seed 0, 4.0 s, dt = 2 ms (500 Hz), 1550 nm, 8 cm Tx, 1 W. ISL range ~2400 km (20° coplanar LEO). Downlink: OGS at the t=0 sub-satellite point, 40 cm Rx. Stress: 40 μrad RMS jitter.

θ* is a control-Lyapunov coordinate mapped so the well sits at **boresight**. It is not a 22.5° beam offset.

## Summary

| Scenario | open RMS (μrad) | PID RMS | QSD RMS | wrong-well RMS | QSD vs PID availability |
|---|---|---|---|---|---|
| ISL | 17.8 | 6.7 | 8.7 | 40.8 | −0.15 pp (non-inferior) |
| Downlink | 17.8 | 6.7 | 8.7 | 40.8 | −0.10 pp (non-inferior) |
| Stress | 56.5 | 21.6 | 25.7 | 49.8 | −13.5 pp (**NULL**) |

## Pre-registered tests

| ID | ISL | Downlink | Stress |
|---|---|---|---|
| T1 QSD < open-loop residual | PASS | PASS | PASS |
| T2 ISS coverage, non-vacuous bound | NULL (vacuous envelope) | NULL | NULL |
| T3 availability non-inferior to PID (−2 pp) | PASS | PASS | NULL |
| T4 acquisition ≤ PID (12 μrad hold) | NULL (84 vs 25 samples) | NULL | NULL (neither) |
| T5 wrong well is worse | PASS | PASS | PASS |

**Reading.** On this plant a type-1 PI fine stage is a slightly better tracker than the ISS step `k = 1 − √ρ`. QSD still halves open-loop residual and is availability-non-inferior on the quiet ISL/downlink cases. Under 40 μrad RMS stress it is not: T3 NULL. The Theorem 6 envelope built from a priori jitter increments is too loose to certify the closed-loop residual (T2 NULL). That is the correct outcome, not a pass to polish.

This does **not** claim QSD replaces Tesat/Mynaric/SDA PAT, and it does not revive the retracted ⟨ZZZ⟩-preservation result.

Reproduce: `python3 -m aurora_qsd.optical --all --seconds 4 --seed 0`

Artifacts: `results/optical/`.

## v0.2 — PLL + FEC + two-hop (same day)

T6 (one-step ISS) **PASS** on ISL/downlink/stress (coverage 0.995–0.996). The unfolded T2 envelope remains NULL/vacuous; that is the distinction the test was added to make.

**Optical PLL** (20 kHz, Δν = 300 Hz, Doppler feedforward on):

| ctrl | RMS phase (rad) | cycle slips | BPSK BER |
|---|---|---|---|
| open | 1.72 | 93 | 3.7e-2 |
| pid | 1.31 | 17 | 4.5e-2 |
| qsd | **0.91** | **8** | **1.5e-2** |
| quadrature well | 1.85 | 62 | 6.7e-2 |

P1–P5 all PASS, including Doppler feedforward (0.91 rad with FF vs 1.58 rad without). On this Costas-rate plant QSD beat PI; that does not reverse the 500 Hz PAT result.

**Two-hop relay** (LEO-A → LEO-B → OGS): PID and QSD delivered `HELLO FROM LEO-1` intact with or without Hamming; open-loop raw failed (e2e BER 2.3e-2) and was recovered by FEC. R1–R3 PASS.

