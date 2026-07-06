#!/usr/bin/env python3
"""
Full-chip QSD stability controller — Ae → 0, Δσ → ∅ at θ*.

Closed-loop adaptive re-lock across all disjoint 3Q lines on Willow.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.chip_stability import run_chip_stability


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-chip QSD stability controller")
    parser.add_argument("--shots", type=int, default=400)
    parser.add_argument("--max-cells", type=int, default=None, help="Cap cells (default: all ~32)")
    parser.add_argument("--theta-deg", type=float, default=22.49)
    parser.add_argument("--depth", type=int, default=14)
    parser.add_argument("--relock", type=int, default=5)
    parser.add_argument("--ae-tol", type=float, default=3.0, help="Ae band tolerance (deg)")
    parser.add_argument("--sigma-tol", type=float, default=0.05)
    parser.add_argument("--out", default="results/willow_chip_stability.json")
    args = parser.parse_args()

    result = run_chip_stability(
        shots=args.shots,
        max_cells=args.max_cells,
        theta_star_deg=args.theta_deg,
        base_depth=args.depth,
        base_relock=args.relock,
        ae_tol_deg=args.ae_tol,
        sigma_tol=args.sigma_tol,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2))

    print(json.dumps(result.to_dict(), indent=2))
    print(f"\nVERDICT: {result.verdict}")
    print(f"NOTES:   {result.notes}")
    print(f"Saved:   {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
