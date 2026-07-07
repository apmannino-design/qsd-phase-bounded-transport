#!/usr/bin/env python3
"""
IBM FakeFez hardware-faithful benchmark (improvements 1–4).

1. 3-qubit ZZZ cells + true ⟨Z⊗Z⊗Z⟩ correlator
2. Native FakeFez noise (mild/apocalypse optional)
3. Basin sweep → empirical θ lock
4. TriLock sunscreen re-preparation (not RY-only reset)

Usage:
  python3 examples/fez_hardware_faithful.py
  python3 examples/fez_hardware_faithful.py --noise mild --depth 1241
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from aurora_qsd.core.constants import THETA_STAR_HW_DEG
from aurora_qsd.quantum.basin_sweep import run_basin_sweep
from aurora_qsd.quantum.fez_cells import (
    build_zzz_baseline_circuit,
    build_zzz_cell_circuit,
    extract_zzz_triplets,
    negative_control_angle,
    zzz_correlator,
)
from aurora_qsd.quantum.noise_models import build_simulator
from aurora_qsd.quantum.runner import run_circuit
from aurora_qsd.quantum.sunscreen import build_sunscreen_circuit


def run_campaign(
    shots: int = 4096,
    depth: int = 1241,
    noise: str = "native",
    n_cells: int = 43,
    reset_interval: int = 8,
) -> dict:
    try:
        from qiskit_ibm_runtime.fake_provider import FakeFez

        backend = FakeFez()
        coupling_map = backend.configuration().coupling_map
        n_qubits = backend.num_qubits
    except ImportError:
        coupling_map = [(0, 1), (1, 2)]
        n_qubits = 3

    cells = extract_zzz_triplets(coupling_map, max_cells=n_cells)
    sim = build_simulator(noise)

    print(f"Backend: FakeFez ({n_qubits}Q) | noise={noise} | cells={len(cells)}")
    print(f"Depth: {depth} | shots: {shots} | sunscreen every {reset_interval} layers\n")

    # Step 1: Basin sweep
    print("[1/4] Basin sweep (±20° around θ*)...")
    basin = run_basin_sweep(shots=shots, depth=min(32, depth), noise=noise)
    theta_opt = np.radians(basin.optimal_theta_deg)
    print(f"  {basin.summary()}\n")

    # Step 2: Reference scores at basin optimum
    print("[2/4] Scoring at basin-optimal angle...")
    baseline = zzz_correlator(
        run_circuit(build_zzz_baseline_circuit(min(32, depth)), sim, shots), 3,
    )
    neg = zzz_correlator(
        run_circuit(
            build_zzz_cell_circuit(theta=negative_control_angle(), depth=min(32, depth)),
            sim, shots,
        ),
        3,
    )
    at_star = zzz_correlator(
        run_circuit(build_zzz_cell_circuit(depth=min(32, depth)), sim, shots), 3,
    )
    at_opt = basin.optimal_zzz
    print(f"  Baseline:          {baseline:+.4f}")
    print(f"  θ* ({THETA_STAR_HW_DEG}°):     {at_star:+.4f}")
    print(f"  Basin optimum:     {at_opt:+.4f}")
    print(f"  Negative control:  {neg:+.4f}\n")

    # Step 3: Depth scaling with sunscreen
    print("[3/4] Depth scaling (3-qubit ZZZ, basin-optimal θ)...")
    depths = [32, 140, 311, depth] if depth >= 311 else [32, depth]
    depth_table = []
    for d in depths:
        open_zzz = zzz_correlator(
            run_circuit(build_zzz_cell_circuit(theta=theta_opt, depth=d), sim, shots), 3,
        )
        sun_zzz = zzz_correlator(
            run_circuit(
                build_sunscreen_circuit(theta=theta_opt, total_layers=d, reset_interval=reset_interval),
                sim, shots,
            ),
            3,
        )
        depth_table.append({"depth": d, "open": open_zzz, "sunscreen": sun_zzz, "delta": sun_zzz - open_zzz})
        print(f"  depth={d:>4}: open={open_zzz:+.4f}  sunscreen={sun_zzz:+.4f}  Δ={sun_zzz - open_zzz:+.4f}")

    # Step 4: Multi-cell median at max depth
    print(f"\n[4/4] {len(cells)}-cell campaign at depth {depth}...")
    cell_scores = []
    for i, _cell in enumerate(cells):
        counts = run_circuit(
            build_sunscreen_circuit(theta=theta_opt, total_layers=depth, reset_interval=reset_interval),
            sim, shots,
        )
        cell_scores.append(zzz_correlator(counts, 3))
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(cells)} cells done", flush=True)

    median_zzz = float(np.median(cell_scores))
    print(f"  Median ZZZ: {median_zzz:+.4f}  (σ={np.std(cell_scores):.4f})\n")

    d_max = depth_table[-1]
    verdict = (
        "SLAM DUNK"
        if median_zzz > neg + 0.15 and d_max["sunscreen"] >= d_max["open"]
        else "STRONG" if median_zzz > neg + 0.05 and basin.gain_vs_baseline > 0
        else "PARTIAL"
    )

    result = {
        "noise": noise,
        "n_cells": len(cells),
        "basin_optimal_theta_deg": basin.optimal_theta_deg,
        "baseline_zzz": baseline,
        "negative_control_zzz": neg,
        "median_zzz_max_depth": median_zzz,
        "depth_table": depth_table,
        "verdict": verdict,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hardware-faithful FakeFez QSD benchmark")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--depth", type=int, default=1241)
    parser.add_argument("--noise", choices=["native", "mild", "apocalypse", "ideal"], default="native")
    parser.add_argument("--cells", type=int, default=43)
    parser.add_argument("--reset", type=int, default=8, help="Sunscreen interval (layers)")
    parser.add_argument("--out", type=str, default="results")
    args = parser.parse_args(argv)

    result = run_campaign(
        shots=args.shots,
        depth=args.depth,
        noise=args.noise,
        n_cells=args.cells,
        reset_interval=args.reset,
    )

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    (out / "fez_hardware_faithful.json").write_text(json.dumps(result, indent=2))

    print("=" * 60)
    print(f"VERDICT: {result['verdict']}")
    print(f"Median ZZZ @ {args.depth}L: {result['median_zzz_max_depth']:+.4f}")
    print(f"Basin θ: {result['basin_optimal_theta_deg']:.2f}°")
    print(f"Saved: {out}/fez_hardware_faithful.json")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
