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
