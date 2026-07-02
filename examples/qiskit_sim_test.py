#!/usr/bin/env python3
"""
Qiskit Aer simulation test suite for Aurora-QSD AI.

Uses hardware-faithful circuits from code/qsd_reference_implementation.py.

Usage:
  python3 examples/qiskit_sim_test.py
  python3 examples/qiskit_sim_test.py --noise --sweep --depth-scale
  python3 examples/qiskit_sim_test.py --stress
"""

from __future__ import annotations

import argparse
import sys

import numpy as np

from aurora_qsd import QSDAuroraAgent, THETA_STAR_DEG
from aurora_qsd.core.constants import THETA_STAR_HW, THETA_STAR_HW_DEG
from aurora_qsd.quantum.circuit_builder import (
    build_baseline,
    build_deep_qsd_circuit,
    build_with_relock,
    zzz_score,
)
from aurora_qsd.quantum.simulator import (
    build_ideal_simulator,
    build_noisy_simulator,
    run_circuit,
    run_stress_test,
)


def test_comparison(sim, shots: int, layers: int) -> float:
    """Compare baseline vs QSD vs re-lock. Returns baseline ZZZ."""
    circuits = {
        "Baseline (H init)": build_baseline(layers),
        f"QSD @ θ* ({THETA_STAR_HW_DEG}°, {layers}L)": build_deep_qsd_circuit(THETA_STAR_HW, layers),
        f"QSD re-lock /7 ({layers}L)": build_with_relock(total_layers=layers, relock_interval=7),
    }

    print(f"\n{'Circuit':<38} | {'ZZZ':>8} | {'Gain':>8}")
    print("-" * 60)

    baseline_zzz = zzz_score(run_circuit(build_baseline(layers), sim, shots))

    for name, qc in circuits.items():
        counts = run_circuit(qc, sim, shots)
        zzz = zzz_score(counts)
        gain = zzz - baseline_zzz
        print(f"{name:<38} | {zzz:>8.4f} | {gain:>+8.4f}")

    return baseline_zzz


def test_theta_sweep(sim, shots: int, layers: int, baseline_zzz: float) -> None:
    """Sweep θ around θ* — reference style with gain vs baseline."""
    print(f"\nθ sweep ({layers} layers, baseline ZZZ = {baseline_zzz:.4f}):")
    print(f"  {'θ (deg)':>10} | {'ZZZ':>8} | {'Gain':>8} | Status")
    print("  " + "-" * 48)

    best_theta, best_gain = THETA_STAR_HW_DEG, -1.0
    passes = 0

    for d in np.linspace(-8, 8, 17):
        theta = THETA_STAR_HW + np.radians(d)
        counts = run_circuit(build_deep_qsd_circuit(theta, layers), sim, shots)
        zzz = zzz_score(counts)
        gain = zzz - baseline_zzz
        ok = gain > 0
        passes += int(ok)
        marker = " ← θ*" if abs(d) < 0.5 else ""
        status = "✅" if ok else "❌"
        print(f"  {np.degrees(theta):>10.2f} | {zzz:>8.4f} | {gain:>+8.4f} | {status}{marker}")
        if gain > best_gain:
            best_gain, best_theta = gain, float(np.degrees(theta))

    print(f"\n  Best: θ = {best_theta:.2f}° (gain {best_gain:+.4f}) | Passes: {passes}/17")


def test_depth_scaling(sim, shots: int) -> None:
    """ZZZ vs depth with and without re-lock."""
    depths = [7, 14, 35, 70]
    print("\nDepth scaling (re-lock every 7 layers):")
    print(f"  {'Depth':>6} | {'No re-lock':>10} | {'Re-lock /7':>10} | {'Δ':>8}")
    print("  " + "-" * 42)

    for d in depths:
        no_rl = zzz_score(run_circuit(build_deep_qsd_circuit(THETA_STAR_HW, d), sim, shots))
        with_rl = zzz_score(run_circuit(build_with_relock(total_layers=d, relock_interval=7), sim, shots))
        print(f"  {d:>6} | {no_rl:>10.4f} | {with_rl:>10.4f} | {with_rl - no_rl:>+8.4f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aurora-QSD Qiskit Aer simulation tests")
    parser.add_argument("--noise", action="store_true", help="Use apocalyptic FakeFez noise model")
    parser.add_argument("--shots", type=int, default=8192)
    parser.add_argument("--layers", type=int, default=12)
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--depth-scale", action="store_true")
    parser.add_argument("--stress", action="store_true", help="Run full 3-stage stress test")
    args = parser.parse_args(argv)

    print("=" * 70)
    print(" Aurora-QSD Qiskit Aer Simulation (hardware-faithful circuits)")
    print(f" θ*_hw = {THETA_STAR_HW_DEG}° | θ*_alg = {THETA_STAR_DEG:.4f}° | shots = {args.shots}")
    print("=" * 70)

    if args.stress:
        print("\n[FULL STRESS TEST]")
        result = run_stress_test(shots=args.shots, layers=args.layers, noisy=True)
        print(result.summary())
        return 0

    sim = build_noisy_simulator() if args.noise else build_ideal_simulator()
    baseline = test_comparison(sim, args.shots, args.layers)

    if args.sweep or args.noise:
        test_theta_sweep(sim, args.shots, args.layers, baseline)

    if args.depth_scale:
        test_depth_scaling(sim, args.shots)

    agent = QSDAuroraAgent()
    print(f"\n{agent.check_aurora().message}")

    print("\n" + "=" * 70)
    print(" Done. For full validation: python3 examples/qiskit_sim_test.py --stress")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
