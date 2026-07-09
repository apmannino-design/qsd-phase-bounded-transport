#!/usr/bin/env python3
"""
Willow entanglement stress — G(El) through CX depth (May 2026 protocol).

Tests whether TriLock @ θ* suppresses basin failure better than bare H-init
as entanglement layers stack on willow_pink.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.willow_entanglement_stress import run_entanglement_stress

RESULTS = Path("results")


def main() -> int:
    parser = argparse.ArgumentParser(description="Willow entanglement stress G(El) sweep")
    parser.add_argument("--shots", type=int, default=2000)
    parser.add_argument("--line", default="interior")
    parser.add_argument("--quick", action="store_true", help="El=0,1,2,5 only @ 1000 shots")
    parser.add_argument("--out", default="results/willow_entanglement_stress.json")
    args = parser.parse_args()

    shots = args.shots
    el_schedule = None
    if args.quick:
        shots = 1000
        el_schedule = [0, 1, 2, 5]

    RESULTS.mkdir(exist_ok=True)

    print("=" * 60, flush=True)
    print("Willow entanglement stress — G(El) through CX depth", flush=True)
    print("=" * 60, flush=True)

    result = run_entanglement_stress(
        shots=shots,
        el_schedule=el_schedule,
        line_name=args.line,
    )

    payload = result.to_dict()
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")

    print("\n--- SUMMARY ---", flush=True)
    print(f"Verdict: {result.verdict}", flush=True)
    print(f"G peak: {result.g_peak:.3f} @ El={result.g_peak_el}", flush=True)
    print(f"G@El=0: {result.g_at_el0:.3f}", flush=True)
    print(f"Sustained G>1: {result.g_sustained_el_ge_1}/{len([p for p in result.points if p.el > 0])}", flush=True)
    print(f"Notes: {result.notes}", flush=True)
    print(f"Wrote {out_path}", flush=True)

    return 0 if result.verdict != "NULL" else 1


if __name__ == "__main__":
    sys.exit(main())
