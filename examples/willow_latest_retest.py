#!/usr/bin/env python3
"""
July 7, 2026 unified Willow sim retest — incorporates latest findings:

  - Platform θ* = 22.49° (not design π/8 alone)
  - Interior line q(6,5)–q(6,6)–q(6,7)
  - Optimum depth 14L, re-lock /5 (gain sweep)
  - Retention scoring R = noisy/ideal; verdict ladder (no endorsable from sim)
  - Repaired XY4 control (12 pulses/layer)
  - Tridelta lattice submission protocol (9Q patch, optional)

Runs on willow_pink QVM only.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_THETA_DEG
from aurora_qsd.quantum.willow_gain_sweep import run_winning_cells
from aurora_qsd.quantum.willow_run import run_willow_correct
from aurora_qsd.quantum.zzz_preservation import (
    run_retention_audit_benchmark,
    verify_xy4_layer,
)

RESULTS = Path("results")

LATEST_FINDINGS = {
    "theta_star_deg": OPTIMAL_THETA_DEG,
    "design_theta_deg": 22.5,
    "depth_layers": 14,
    "relock_interval": OPTIMAL_RELOCK_INTERVAL,
    "line": "q(6,5)-q(6,6)-q(6,7)",
    "processor": "willow_pink",
    "verdict_policy": "COHERENT_ARTIFACT not ENDORSABLE; sim never endorses",
    "retention_metric": "R = noisy/ideal per arm",
    "xy4_control": "repaired 12-pulse/layer",
    "submission_protocol": "Tridelta Trotter lattice 9Q patch (separate module)",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified Willow sim retest (July 7 findings)")
    parser.add_argument("--shots-interior", type=int, default=2000)
    parser.add_argument("--shots-retention", type=int, default=2000)
    parser.add_argument("--sweep-shots", type=int, default=500)
    parser.add_argument("--shots-cells", type=int, default=400)
    parser.add_argument("--skip-cells", action="store_true")
    parser.add_argument("--skip-retention", action="store_true")
    parser.add_argument("--fast", action="store_true", help="1000/1500/300 shots")
    parser.add_argument("--out", default="results/willow_latest_retest.json")
    args = parser.parse_args()

    if args.fast:
        args.shots_interior = 1000
        args.shots_retention = 1500
        args.sweep_shots = 400
        args.shots_cells = 300

    t0 = time.time()
    payload: dict = {
        "status": "RETEST",
        "date": "2026-07-07",
        "findings_applied": LATEST_FINDINGS,
        "phases": {},
    }

    print("=" * 60, flush=True)
    print("WILLOW LATEST RETEST — willow_pink QVM", flush=True)
    print(json.dumps(LATEST_FINDINGS, indent=2), flush=True)
    print("=" * 60, flush=True)

    # Phase 0: XY4 repair check
    xy4 = verify_xy4_layer()
    payload["phases"]["xy4_check"] = xy4
    print(f"\n[0] XY4 layer OK: {xy4.get('pass', xy4)}", flush=True)

    # Phase 1: Canonical interior depth sunscreen
    print(
        f"\n[1] Interior depth sunscreen — {args.shots_interior} shots "
        f"@ θ*={OPTIMAL_THETA_DEG}° 14L relock/{OPTIMAL_RELOCK_INTERVAL}",
        flush=True,
    )
    interior = run_willow_correct(
        shots=args.shots_interior,
        theta_star_deg=OPTIMAL_THETA_DEG,
        depth_layers=14,
        relock_interval=OPTIMAL_RELOCK_INTERVAL,
        line_name="interior",
        compare_boundary=False,
    )
    payload["phases"]["interior_depth"] = interior.to_dict()
    print(
        f"    |ΔZZZ|={interior.depth_gap:.3f}  verdict={interior.verdict}",
        flush=True,
    )

    # Phase 2: Retention audit (July 7 protocol)
    if not args.skip_retention:
        print(
            f"\n[2] Retention audit — {args.shots_retention} shots, "
            f"sweep {args.sweep_shots}/θ",
            flush=True,
        )
        audit = run_retention_audit_benchmark(
            shots=args.shots_retention,
            sweep_shots=args.sweep_shots,
            theta_star_deg=OPTIMAL_THETA_DEG,
        )
        payload["phases"]["retention_audit"] = audit
        r = audit["result"]
        print(f"    verdict={r['verdict']}  endorsable={r['endorsable']}", flush=True)
        for name, arm in r["arms"].items():
            print(
                f"    {name}: ideal={arm['ideal_zzz']:+.3f}  "
                f"noisy={arm.get('measured_zzz', 'n/a')}  R={arm.get('retention_signed')}",
                flush=True,
            )
    else:
        print("\n[2] Retention audit skipped", flush=True)

    # Phase 3: Prior-winning chip cells at optimum
    if not args.skip_cells:
        print(f"\n[3] Prior-winning cells — {args.shots_cells} shots each", flush=True)
        cells = run_winning_cells(
            theta_deg=OPTIMAL_THETA_DEG,
            depth_layers=14,
            relock_interval=OPTIMAL_RELOCK_INTERVAL,
            shots=args.shots_cells,
        )
        payload["phases"]["chip_cells"] = cells
        print(
            f"    {cells['cells_winning']}/{cells['n_cells']} win  "
            f"median |Δ|={cells['abs_gap_median']:.3f}",
            flush=True,
        )
    else:
        print("\n[3] Chip cells skipped", flush=True)

    # Phase 4: Tridelta submission (attach if already complete)
    tridelta_path = RESULTS / "willow_tridelta_submission.json"
    if tridelta_path.exists():
        payload["phases"]["tridelta_submission"] = json.loads(tridelta_path.read_text())
        print(f"\n[4] Tridelta submission loaded from {tridelta_path}", flush=True)
    else:
        print("\n[4] Tridelta submission not finished — run willow_tridelta_submission.py", flush=True)

    payload["elapsed_s"] = time.time() - t0
    payload["summary"] = {
        "interior_abs_gap": interior.depth_gap,
        "interior_verdict": interior.verdict,
        "retention_verdict": payload.get("phases", {}).get("retention_audit", {}).get("result", {}).get("verdict"),
        "cells_winning": payload.get("phases", {}).get("chip_cells", {}).get("cells_winning"),
        "cells_median_gap": payload.get("phases", {}).get("chip_cells", {}).get("abs_gap_median"),
        "endorsable": False,
        "stamp_status": "HOLD",
    }

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print("\n" + "=" * 60, flush=True)
    print(json.dumps(payload["summary"], indent=2), flush=True)
    print(f"\nSaved: {out}  ({payload['elapsed_s']:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
