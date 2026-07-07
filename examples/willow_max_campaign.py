#!/usr/bin/env python3
"""Run max Willow campaign and save JSON results."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from aurora_qsd.quantum.willow_run import run_willow_max

RESULTS = Path("results")


def run_phase(name: str, **kwargs) -> dict:
    print(f"\n{'='*60}\nPHASE: {name}\n{'='*60}", flush=True)
    t0 = time.time()
    result = run_willow_max(**kwargs)
    elapsed = time.time() - t0
    data = result.to_dict()
    data["elapsed_s"] = elapsed
    data["phase"] = name
    out = RESULTS / f"willow_max_{name}.json"
    out.write_text(json.dumps(data, indent=2))
    print(json.dumps(data, indent=2))
    print(f"\nVERDICT: {result.verdict}")
    print(f"NOTES:   {result.notes}")
    print(f"Saved:   {out} ({elapsed:.0f}s)", flush=True)
    return data


def main() -> int:
    RESULTS.mkdir(exist_ok=True)

    # Max depth: 3 qubits, 1241 layers (fez-scale)
    depth_max = run_phase(
        "depth_1241_interior",
        shots=150,
        theta_star_deg=22.48,
        depth_layers=1241,
        relock_interval=3,
        max_cells=0,
        include_interior=True,
    )

    # Max qubits: 96 qubits (32 cells), 64 layers (runtime-feasible on sim)
    qubit_max = run_phase(
        "qubits_96_depth_64",
        shots=100,
        theta_star_deg=22.48,
        depth_layers=64,
        relock_interval=3,
        max_cells=None,
        include_interior=False,
    )

    summary = {
        "depth_max": {
            "qubits": 3,
            "layers": 1241,
            "abs_gap": depth_max.get("interior", {}).get("abs_gap"),
            "verdict": depth_max.get("verdict"),
        },
        "qubit_max": {
            "qubits": qubit_max.get("n_qubits"),
            "cells": qubit_max.get("n_cells"),
            "layers": 64,
            "abs_gap_median": qubit_max.get("aggregate", {}).get("abs_gap_median"),
            "cells_winning": qubit_max.get("aggregate", {}).get("cells_winning"),
            "verdict": qubit_max.get("verdict"),
        },
    }
    summary_path = RESULTS / "willow_max_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    print(f"\nSUMMARY written to {summary_path}", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
