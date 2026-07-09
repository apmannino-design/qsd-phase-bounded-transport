#!/usr/bin/env python3
"""
Willow cascade entanglement — max qubits, max depth, least entropy.

Full-chip cascade: TriLock @ θ* on all disjoint 3Q cells, bridge CX propagation,
re-lock every N layers. Sweeps cascade depth Cc and reports G(Cc), σ(θ*), Shannon H.

Examples:
  python3 examples/willow_cascade_entanglement.py --quick
  python3 examples/willow_cascade_entanglement.py --max --shots 2000
  python3 examples/willow_cascade_entanglement.py --max-cells 8 --cc 0,1,2,5,13
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.willow_cascade_entanglement import (
    DEFAULT_CC_SCHEDULE,
    QUICK_CC_SCHEDULE,
    run_cascade_entanglement,
)

RESULTS = Path("results")


def _parse_cc(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Willow cascade entanglement — max qubits × max depth, least entropy"
    )
    parser.add_argument("--shots", type=int, default=2000)
    parser.add_argument("--theta", type=float, default=22.49, help="platform θ* (deg)")
    parser.add_argument("--cc", default=None, help="comma cascade depths, e.g. 0,1,2,5,13")
    parser.add_argument("--quick", action="store_true", help="Cc=0,1,2,5,8,13 @ 1000 shots")
    parser.add_argument(
        "--max",
        action="store_true",
        help=f"full chip + default max schedule {DEFAULT_CC_SCHEDULE}",
    )
    parser.add_argument("--max-cells", type=int, default=None, help="cap disjoint cells (debug)")
    parser.add_argument("--relock", type=int, default=5, help="sunscreen re-lock interval")
    parser.add_argument("--out", default="results/willow_cascade_entanglement.json")
    args = parser.parse_args()

    shots = args.shots
    cc_schedule = _parse_cc(args.cc)
    if args.quick:
        shots = min(shots, 1000)
        cc_schedule = QUICK_CC_SCHEDULE
    elif args.max and cc_schedule is None:
        cc_schedule = DEFAULT_CC_SCHEDULE
    if cc_schedule is None:
        cc_schedule = QUICK_CC_SCHEDULE

    RESULTS.mkdir(exist_ok=True)

    print("=" * 62, flush=True)
    print("Willow cascade entanglement — max qubits × max depth, least entropy", flush=True)
    print("=" * 62, flush=True)
    print(f"Cc schedule: {cc_schedule}  shots={shots}  relock/{args.relock}", flush=True)

    result = run_cascade_entanglement(
        shots=shots,
        theta_star_deg=args.theta,
        cc_schedule=cc_schedule,
        max_cells=args.max_cells,
        relock_interval=args.relock,
    )

    payload = result.to_dict()
    out_path = Path(args.out)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")

    print("\n--- SUMMARY ---", flush=True)
    print(f"Verdict: {result.verdict}", flush=True)
    print(f"Qubits: {result.n_qubits}  cells: {result.n_cells}  bridges: {result.n_bridges}", flush=True)
    print(f"G peak: {result.g_peak:.3f} @ Cc={result.g_peak_cc}", flush=True)
    print(f"Sustained G>1: {result.g_sustained_cc_ge_1}", flush=True)
    print(
        f"Entropy @ max Cc: QSD={result.entropy_at_max_cc_qsd:.2f}b  "
        f"bare={result.entropy_at_max_cc_bare:.2f}b  min QSD={result.entropy_min_qsd_bits:.2f}b @ Cc={result.entropy_min_cc}",
        flush=True,
    )
    print(f"σ(θ*): {result.sigma_theta:.2e}  elapsed: {result.elapsed_s:.0f}s", flush=True)
    print(f"Notes: {result.notes}", flush=True)
    print(f"Wrote {out_path}", flush=True)

    return 0 if result.verdict != "NULL" else 1


if __name__ == "__main__":
    sys.exit(main())
