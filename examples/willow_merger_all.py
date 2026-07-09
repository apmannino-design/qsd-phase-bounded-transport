#!/usr/bin/env python3
"""
All-in-one: SO(2) merger sweep + Willow θ head-to-head (platform vs merger).

  1. SO(2) projector sweep at peak merger (preregistered targets)
  2. Willow sim: 22.49° vs 27.61° on interior + 96 qubits
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.core.so2_projector import (
    merger_reference_invariants,
    run_so2_sweep_from_invariants,
    synthesis_sigma_for_merger_targets,
)
from aurora_qsd.quantum.willow_theta_compare import run_theta_head_to_head

RESULTS = Path("results")


def main() -> int:
    parser = argparse.ArgumentParser(description="SO(2) merger + Willow θ compare")
    parser.add_argument("--shots-interior", type=int, default=2000)
    parser.add_argument("--shots-cells", type=int, default=500)
    parser.add_argument("--full", action="store_true", help="4000 interior / 1000 cell shots")
    parser.add_argument("--skip-willow", action="store_true")
    parser.add_argument("--out", default="results/willow_merger_all.json")
    args = parser.parse_args()

    if args.full:
        args.shots_interior = 4000
        args.shots_cells = 1000

    RESULTS.mkdir(exist_ok=True)
    payload: dict = {"phases": {}}

    print("=" * 60, flush=True)
    print("PHASE 1: SO(2) Projector Sweep at Peak Merger", flush=True)
    print("=" * 60, flush=True)
    delta_j, delta_l0, delta_x0 = merger_reference_invariants()
    merger = run_so2_sweep_from_invariants(delta_j, delta_l0, delta_x0, store_curve=False)
    payload["phases"]["so2_merger"] = merger.to_dict()
    print(
        f"\n--- OPTIMAL GEOMETRIC ALIGNMENT FOUND ---\n"
        f"Projector Rotation (α) : {merger.optimal_alpha_deg:.2f}°\n"
        f"Structural Ratio (ΔL/ΔX) : {merger.optimal_ratio_lx:.4f} "
        f"(Target: {merger.target_ratio_lx:.4f})\n"
        f"Partition Angle (θ)    : {merger.optimal_theta_deg:.2f}°\n"
        f"VERDICT: {merger.verdict}\n",
        flush=True,
    )

    if not args.skip_willow:
        print("=" * 60, flush=True)
        print("PHASE 2: Willow θ head-to-head (platform vs merger)", flush=True)
        print("=" * 60, flush=True)
        compare = run_theta_head_to_head(
            shots_interior=args.shots_interior,
            shots_cells=args.shots_cells,
        )
        payload["phases"]["theta_compare"] = compare.to_dict()
        print(f"\nWINNER: {compare.winner_label} @ {compare.winner_theta_deg:.2f}°")
        print(f"VERDICT: {compare.verdict}")
        print(f"NOTES:   {compare.notes}")

    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved: {out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
