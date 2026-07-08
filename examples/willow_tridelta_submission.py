#!/usr/bin/env python3
"""Run April 2026 Willow Tridelta lattice submission protocol on willow_pink QVM."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.willow_tridelta_lattice import (
    default_theta_sweep,
    run_phase_diagram_on_willow,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tridelta lattice θ×depth phase diagram on Willow sim (submission protocol)"
    )
    parser.add_argument("--shots", type=int, default=500)
    parser.add_argument("--dt", type=float, default=0.08)
    parser.add_argument("--trotter-min", type=int, default=4)
    parser.add_argument("--trotter-max", type=int, default=12)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Smaller sweep: 9 θ points, steps 6–10",
    )
    parser.add_argument("--out", default="results/willow_tridelta_submission.json")
    args = parser.parse_args()

    if args.quick:
        thetas = [2.0, 14.0, 22.49, 26.0, 38.0, 50.0, 62.0, 74.0, 86.0]
        trotter_range = list(range(6, 11))
    else:
        thetas = default_theta_sweep()
        trotter_range = list(range(args.trotter_min, args.trotter_max + 1))

    print(
        f"Willow Tridelta submission sim: {len(thetas)} θ × {len(trotter_range)} depths, "
        f"{args.shots} shots/point",
        flush=True,
    )

    result = run_phase_diagram_on_willow(
        thetas_deg=thetas,
        trotter_range=trotter_range,
        shots=args.shots,
        dt=args.dt,
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
