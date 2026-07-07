#!/usr/bin/env python3
"""
Maximum-qubit Willow sim campaign — July 7 corrected settings.

  θ* = 22.49°  |  depth = 14L  |  re-lock = /5  |  processor = willow_pink
  Phase A: interior line q(6,5)–q(6,6)–q(6,7)
  Phase B: all 32 disjoint 3Q cells (96 qubits)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_THETA_DEG
from aurora_qsd.quantum.willow_run import run_willow_max

RESULTS = Path("results")
OPTIMAL_DEPTH = 14


def run_phase(name: str, **kwargs) -> dict:
    print(f"\n{'='*60}\nPHASE: {name}\n{'='*60}", flush=True)
    t0 = time.time()
    result = run_willow_max(**kwargs)
    elapsed = time.time() - t0
    data = result.to_dict()
    data["elapsed_s"] = elapsed
    data["phase"] = name
    data["config_note"] = (
        f"Corrected July 7: θ*={OPTIMAL_THETA_DEG}° depth={kwargs.get('depth_layers')}L "
        f"relock=/{kwargs.get('relock_interval')}"
    )
    out = RESULTS / f"willow_max_{name}.json"
    out.write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))
    print(f"\nVERDICT: {result.verdict}")
    print(f"NOTES:   {result.notes}")
    print(f"Saved:   {out} ({elapsed:.0f}s)", flush=True)
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Max-qubit corrected Willow QVM campaign")
    parser.add_argument("--shots-interior", type=int, default=1000)
    parser.add_argument("--shots-cells", type=int, default=200)
    parser.add_argument("--interior-only", action="store_true")
    parser.add_argument("--cells-only", action="store_true")
    args = parser.parse_args()

    RESULTS.mkdir(exist_ok=True)
    t0 = time.time()

    interior = {}
    qubit_max = {}

    if not args.cells_only:
        interior = run_phase(
            "interior_14L_corrected",
            shots=args.shots_interior,
            theta_star_deg=OPTIMAL_THETA_DEG,
            depth_layers=OPTIMAL_DEPTH,
            relock_interval=OPTIMAL_RELOCK_INTERVAL,
            max_cells=0,
            include_interior=True,
        )

    if not args.interior_only:
        qubit_max = run_phase(
            "qubits_96_depth_14_corrected",
            shots=args.shots_cells,
            theta_star_deg=OPTIMAL_THETA_DEG,
            depth_layers=OPTIMAL_DEPTH,
            relock_interval=OPTIMAL_RELOCK_INTERVAL,
            max_cells=None,
            include_interior=False,
        )

    summary = {
        "date": "2026-07-07",
        "processor": "willow_pink",
        "theta_star_deg": OPTIMAL_THETA_DEG,
        "depth_layers": OPTIMAL_DEPTH,
        "relock_interval": OPTIMAL_RELOCK_INTERVAL,
        "corrections": [
            "platform θ*=22.49°",
            "optimal 14L relock/5 (gain sweep)",
            "interior line q(6,5)-q(6,6)-q(6,7)",
            "retention verdict HOLD — angle map not EC endorsement",
        ],
        "interior": {
            "qubits": 3,
            "abs_gap": interior.get("interior", {}).get("abs_gap"),
            "verdict": interior.get("verdict"),
        },
        "qubit_max": {
            "qubits": qubit_max.get("n_qubits"),
            "cells": qubit_max.get("n_cells"),
            "abs_gap_median": qubit_max.get("aggregate", {}).get("abs_gap_median"),
            "cells_winning": qubit_max.get("aggregate", {}).get("cells_winning"),
            "verdict": qubit_max.get("verdict"),
        },
        "elapsed_s": time.time() - t0,
    }
    summary_path = RESULTS / "willow_max_qubits_corrected_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSUMMARY: {summary_path}", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
