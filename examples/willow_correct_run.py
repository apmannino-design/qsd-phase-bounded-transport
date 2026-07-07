#!/usr/bin/env python3
"""Correct Willow run — interior line + native willow_pink noise."""

from __future__ import annotations

import argparse
import json
import sys

from aurora_qsd.quantum.willow_run import run_willow_correct


def main() -> int:
    parser = argparse.ArgumentParser(description="Correct Willow QSD run (interior line)")
    parser.add_argument("--shots", type=int, default=4000)
    parser.add_argument("--tau", type=float, default=1000.0, help="Echo idle τ (ns)")
    parser.add_argument("--theta-deg", type=float, default=0.0, help="QSD echo angle (0° best for phase)")
    parser.add_argument(
        "--theta-star-deg",
        type=float,
        default=22.48,
        help="Hardware lock angle for depth sunscreen (default 22.48°)",
    )
    parser.add_argument("--pulse", default="phase", choices=["phase", "tridelta"])
    parser.add_argument("--line", default="interior", choices=["interior", "interior_center", "boundary"])
    parser.add_argument("--depth", type=int, default=16, help="Sunscreen depth layers")
    parser.add_argument("--relock", type=int, default=3, help="Re-lock interval (Aurora aggressive)")
    parser.add_argument("--no-boundary-compare", action="store_true")
    args = parser.parse_args()

    result = run_willow_correct(
        shots=args.shots,
        tau_ns=args.tau,
        theta_deg=args.theta_deg,
        theta_star_deg=args.theta_star_deg,
        pulse=args.pulse,
        line_name=args.line,
        depth_layers=args.depth,
        relock_interval=args.relock,
        compare_boundary=not args.no_boundary_compare,
    )

    print(json.dumps(result.to_dict(), indent=2))
    print(f"\nVERDICT: {result.verdict}")
    print(f"NOTES:   {result.notes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
