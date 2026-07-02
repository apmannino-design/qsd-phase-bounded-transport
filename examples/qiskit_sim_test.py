#!/usr/bin/env python3
"""
Qiskit Aer simulation test suite for Aurora-QSD AI.

Compares ideal vs noisy simulation:
  - Baseline (unmanaged H gates)
  - QSD cell at θ*
  - Deep QSD with/without periodic re-lock

Usage:
  python3 examples/qiskit_sim_test.py
  python3 examples/qiskit_sim_test.py --noise --shots 16384
  python3 examples/qiskit_sim_test.py --sweep
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (
    NoiseModel,
    amplitude_damping_error,
    depolarizing_error,
    phase_damping_error,
)

from aurora_qsd import QSDAuroraAgent, THETA_STAR, THETA_STAR_DEG
from aurora_qsd.quantum.circuit_builder import (
    build_qsd_cell,
    build_with_relock,
    parity_score,
)


def build_baseline(layers: int = 12) -> QuantumCircuit:
    """Unmanaged baseline (no QSD initialization)."""
    qc = QuantumCircuit(2, 2)
    for _ in range(layers):
        qc.h(0)
        qc.h(1)
        qc.cx(0, 1)
        qc.rz(np.pi / 4, 0)
        qc.rz(np.pi / 4, 1)
        qc.cx(1, 0)
    qc.measure([0, 1], [0, 1])
    return qc


def build_deep_qsd(theta: float, layers: int = 12) -> QuantumCircuit:
    """Multi-layer QSD cell without re-lock."""
    return build_qsd_cell(theta=theta, layers=layers)


def build_noise_model(use_fez: bool = True) -> NoiseModel:
    """Build noise model from FakeFez or fallback depolarizing stack."""
    if use_fez:
        try:
            from qiskit_ibm_runtime.fake_provider import FakeFez

            nm = NoiseModel.from_backend(FakeFez())
            t1 = amplitude_damping_error(0.25)
            t2 = phase_damping_error(0.35)
            dp1 = depolarizing_error(0.20, 1)
            dp2 = depolarizing_error(0.40, 2)
            sq = dp1.compose(t1).compose(t2)
            nm.add_all_qubit_quantum_error(sq, ["ry", "rx", "rz", "h", "x"])
            nm.add_all_qubit_quantum_error(dp2, ["cx"])
            return nm
        except ImportError:
            pass

    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(depolarizing_error(0.02, 1), ["ry", "rz", "h"])
    nm.add_all_qubit_quantum_error(depolarizing_error(0.05, 2), ["cx"])
    return nm


def run_circuit(qc: QuantumCircuit, sim: AerSimulator, shots: int) -> dict[str, int]:
    compiled = transpile(qc, sim, optimization_level=0)
    return sim.run(compiled, shots=shots).result().get_counts()


def test_comparison(sim: AerSimulator, shots: int, layers: int) -> None:
    """Compare baseline vs QSD vs re-lock."""
    circuits = {
        "Baseline (H init)": build_baseline(layers),
        f"QSD @ θ* ({layers} layers)": build_deep_qsd(THETA_STAR, layers),
        f"QSD re-lock /7 ({layers} layers)": build_with_relock(
            total_layers=layers, relock_interval=7
        ),
    }

    agent = QSDAuroraAgent()
    print(f"\n{'Circuit':<35} | {'Parity':>8} | {'θ (deg)':>8} | {'AE (deg)':>9}")
    print("-" * 70)

    for name, qc in circuits.items():
        counts = run_circuit(qc, sim, shots)
        parity = parity_score(counts)
        report = agent.analyze_counts(counts)
        print(
            f"{name:<35} | {parity:>8.4f} | {report.data['theta_deg']:>8.2f} | "
            f"{report.data['alignment_error_deg']:>+9.2f}"
        )


def test_theta_sweep(sim: AerSimulator, shots: int, layers: int = 12) -> None:
    """Sweep θ around θ* and find optimal parity."""
    baseline = parity_score(run_circuit(build_baseline(layers), sim, shots))

    print(f"\nθ sweep ({layers} layers, baseline parity = {baseline:.4f}):")
    print(f"  {'θ (deg)':>10} | {'Parity':>8} | {'Gain':>8}")
    print("  " + "-" * 36)

    best_theta, best_parity = THETA_STAR, 0.0
    for d in np.linspace(-8, 8, 17):
        theta = THETA_STAR + np.radians(d)
        counts = run_circuit(build_deep_qsd(theta, layers), sim, shots)
        p = parity_score(counts)
        gain = p - baseline
        marker = " ← θ*" if abs(d) < 0.5 else ""
        print(f"  {np.degrees(theta):>10.2f} | {p:>8.4f} | {gain:>+8.4f}{marker}")
        if p > best_parity:
            best_parity, best_theta = p, theta

    print(f"\n  Best: θ = {np.degrees(best_theta):.2f}°, parity = {best_parity:.4f}")


def test_depth_scaling(sim: AerSimulator, shots: int) -> None:
    """Show parity vs depth with and without re-lock."""
    depths = [7, 14, 35, 70]
    print(f"\nDepth scaling (re-lock every 7 layers):")
    print(f"  {'Depth':>6} | {'No re-lock':>10} | {'Re-lock /7':>10} | {'Δ':>8}")
    print("  " + "-" * 42)

    for d in depths:
        no_rl = parity_score(run_circuit(build_deep_qsd(THETA_STAR, d), sim, shots))
        with_rl = parity_score(
            run_circuit(build_with_relock(total_layers=d, relock_interval=7), sim, shots)
        )
        print(f"  {d:>6} | {no_rl:>10.4f} | {with_rl:>10.4f} | {with_rl - no_rl:>+8.4f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aurora-QSD Qiskit Aer simulation tests")
    parser.add_argument("--noise", action="store_true", help="Enable FakeFez-based noise model")
    parser.add_argument("--shots", type=int, default=8192, help="Measurement shots")
    parser.add_argument("--layers", type=int, default=12, help="Circuit depth for comparison")
    parser.add_argument("--sweep", action="store_true", help="Run θ sweep around θ*")
    parser.add_argument("--depth-scale", action="store_true", help="Run depth scaling test")
    args = parser.parse_args(argv)

    print("=" * 70)
    print(" Aurora-QSD Qiskit Aer Simulation Test")
    print(f" θ* = {THETA_STAR_DEG:.4f}° | shots = {args.shots} | noise = {args.noise}")
    print("=" * 70)

    if args.noise:
        sim = AerSimulator(noise_model=build_noise_model())
    else:
        sim = AerSimulator()

    test_comparison(sim, args.shots, args.layers)

    if args.sweep:
        test_theta_sweep(sim, args.shots, args.layers)

    if args.depth_scale:
        test_depth_scaling(sim, args.shots)

    # Agent summary
    agent = QSDAuroraAgent()
    aurora = agent.check_aurora()
    print(f"\n{aurora.message}")

    print("\n" + "=" * 70)
    print(" Done. Try: python3 examples/qiskit_sim_test.py --noise --sweep --depth-scale")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
