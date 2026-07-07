#!/usr/bin/env python3
"""Maximum Willow QSD run — 1241L depth, all disjoint 3Q cells (up to 96 qubits)."""

from __future__ import annotations

import argparse
import json
import sys

from aurora_qsd.quantum.willow_run import run_willow_max


def main() -> int:
    parser = argparse.ArgumentParser(description="Max Willow QSD (depth + multi-cell)")
    parser.add_argument("--shots", type=int, default=200)
    parser.add_argument("--theta-star-deg", type=float, default=22.48)
    parser.add_argument("--depth", type=int, default=1241, help="Sunscreen layers (fez max=1241)")
    parser.add_argument("--relock", type=int, default=3)
    parser.add_argument("--max-cells", type=int, default=None, help="Cap cells (default: all ~32)")
    parser.add_argument("--interior-only", action="store_true", help="Skip multi-cell; interior 3Q only")
    args = parser.parse_args()

    result = run_willow_max(
        shots=args.shots,
        theta_star_deg=args.theta_star_deg,
        depth_layers=args.depth,
        relock_interval=args.relock,
        max_cells=0 if args.interior_only else args.max_cells,
        include_interior=True,
    )

    print(json.dumps(result.to_dict(), indent=2))
    print(f"\nVERDICT: {result.verdict}")
    print(f"NOTES:   {result.notes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
