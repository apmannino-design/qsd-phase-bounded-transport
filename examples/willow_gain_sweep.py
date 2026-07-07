#!/usr/bin/env python3
"""Maximize Willow QSD gain — θ × depth × re-lock sweep + validation."""

from __future__ import annotations

import argparse
import json
import sys

from aurora_qsd.quantum.willow_gain_sweep import run_full_gain_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="Willow gain maximization sweep")
    parser.add_argument("--coarse-shots", type=int, default=250)
    parser.add_argument("--fine-shots", type=int, default=350)
    parser.add_argument("--validate-shots", type=int, default=2000)
    parser.add_argument("--cell-shots", type=int, default=500)
    args = parser.parse_args()

    summary = run_full_gain_campaign(
        coarse_shots=args.coarse_shots,
        fine_shots=args.fine_shots,
        validate_shots=args.validate_shots,
        cell_shots=args.cell_shots,
    )

    print("\n" + json.dumps(summary, indent=2))
    b = summary["best_config"]
    print(
        f"\nWINNER: θ={b['theta_deg']:.3f}° depth={b['depth_layers']} "
        f"relock={b['relock_interval']} validated |Δ|={summary['validated_abs_gap']:.3f}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
