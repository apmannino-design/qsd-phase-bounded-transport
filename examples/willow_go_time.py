#!/usr/bin/env python3
"""
GO TIME — definitive Willow QSD hardware handoff run.

Optimum from gain sweep:
  θ* = 22.49°, depth = 14, re-lock = 5
  Interior line q(6,5)–q(6,6)–q(6,7)
  + top chip cells at same settings
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_THETA_DEG
from aurora_qsd.quantum.willow_gain_sweep import run_winning_cells
from aurora_qsd.quantum.willow_run import run_willow_correct

RESULTS = Path("results")


def main() -> int:
    RESULTS.mkdir(exist_ok=True)
    t0 = time.time()

    print("=" * 60, flush=True)
    print("GO TIME — Willow QSD hardware handoff", flush=True)
    print(f"θ*={OPTIMAL_THETA_DEG}°  depth=14  re-lock=/{OPTIMAL_RELOCK_INTERVAL}", flush=True)
    print("=" * 60, flush=True)

    print("\n[1/2] Interior line — 4000 shots ...", flush=True)
    interior = run_willow_correct(
        shots=4000,
        theta_star_deg=OPTIMAL_THETA_DEG,
        depth_layers=14,
        relock_interval=OPTIMAL_RELOCK_INTERVAL,
        line_name="interior",
        compare_boundary=False,
    )
    print(f"  |ΔZZZ| = {interior.depth_gap:.3f}  verdict = {interior.verdict}", flush=True)

    print("\n[2/2] Winning chip cells — 1000 shots each ...", flush=True)
    cells = run_winning_cells(
        theta_deg=OPTIMAL_THETA_DEG,
        depth_layers=14,
        relock_interval=OPTIMAL_RELOCK_INTERVAL,
        shots=1000,
    )
    print(
        f"  {cells['cells_winning']}/{cells['n_cells']} win  "
        f"median |Δ| = {cells['abs_gap_median']:.3f}",
        flush=True,
    )

    payload = {
        "status": "GO",
        "config": {
            "theta_star_deg": OPTIMAL_THETA_DEG,
            "depth_layers": 14,
            "relock_interval": OPTIMAL_RELOCK_INTERVAL,
            "line": "q(6,5)-q(6,6)-q(6,7)",
            "processor": "willow_pink",
        },
        "interior": interior.to_dict(),
        "cells": cells,
        "elapsed_s": time.time() - t0,
        "hardware_ready": interior.verdict in {"DEPTH_WIN", "QSD_WIN"}
            and cells["cells_winning"] >= cells["n_cells"] // 2,
    }

    out = RESULTS / "willow_go_time.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved {out}", flush=True)
    print(json.dumps(payload, indent=2))
    print(f"\nHARDWARE READY: {payload['hardware_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
