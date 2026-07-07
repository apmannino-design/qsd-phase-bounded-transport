#!/usr/bin/env python3
"""
Angle-map + Ae/σ fine-tune — drive Ae → ∅ and Δσ → ∅ on full Willow chip.

Phase 1: per-cell θ offset sweep (max |ΔZZZ|) — angle map placement
Phase 2: fine sweep around placement (min |Ae|, then σ) — error limiting
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.chip_stability import run_chip_stability

RESULTS = Path("results")


def main() -> int:
    parser = argparse.ArgumentParser(description="Ae/σ fine-tune on angle-mapped Willow chip")
    parser.add_argument("--shots", type=int, default=1000)
    parser.add_argument("--cal-shots", type=int, default=256, help="Shots per calibration point")
    parser.add_argument("--max-cells", type=int, default=None)
    parser.add_argument("--theta-deg", type=float, default=22.49)
    parser.add_argument("--ae-tol", type=float, default=5.0, help="|Ae| band for ∅ (deg)")
    parser.add_argument("--sigma-tol", type=float, default=0.15, help="σ band for ∅")
    parser.add_argument("--relock-sweep", action="store_true", help="Sweep relock in finetune pass")
    parser.add_argument("--quick", action="store_true", help="8 cells, 400 shots")
    parser.add_argument("--out", default="results/willow_ae_sigma_finetune.json")
    args = parser.parse_args()

    shots = args.shots
    max_cells = args.max_cells
    if args.quick:
        shots = 400
        max_cells = 8

    RESULTS.mkdir(exist_ok=True)

    print("=" * 60, flush=True)
    print("Angle map + Ae/σ fine-tune (Ae → ∅, Δσ → ∅)", flush=True)
    print("=" * 60, flush=True)

    result = run_chip_stability(
        shots=shots,
        max_cells=max_cells,
        theta_star_deg=args.theta_deg,
        ae_tol_deg=args.ae_tol,
        sigma_tol=args.sigma_tol,
        calibrate_theta=True,
        calibrate_shots=args.cal_shots,
        finetune_ae_sigma=True,
        finetune_relock_sweep=args.relock_sweep,
        run_task_benchmark=True,
    )

    out_path = Path(args.out)
    out_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")

    agg = result.aggregate
    print("\n--- SUMMARY ---", flush=True)
    print(f"Verdict: {result.verdict}", flush=True)
    print(f"Angle-map wins: {agg['cells_winning']}/{result.n_cells}", flush=True)
    print(f"Ae→∅ cells: {agg['cells_ae_near_zero']}/{result.n_cells}", flush=True)
    print(f"Δσ→∅ cells: {agg['cells_sigma_near_zero']}/{result.n_cells}", flush=True)
    print(f"Both locked: {agg['cells_ae_sigma_locked']}/{result.n_cells}", flush=True)
    print(f"median |Ae|={agg['ae_median_deg']:.2f}°, median σ={agg['sigma_median']:.4f}", flush=True)
    print(f"Notes: {result.notes}", flush=True)
    print(f"Wrote {out_path}", flush=True)

    return 0 if result.verdict == "ERROR_LIMITED" else 1


if __name__ == "__main__":
    sys.exit(main())
