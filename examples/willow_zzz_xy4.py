#!/usr/bin/env python3
"""
⟨ZZZ⟩ preservation — matched-depth XY4 control + retention R = noisy/ideal.

Do NOT stamp endorsable until R(θ) is peaked at θ* and dominates R(XY4).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.zzz_preservation import run_zzz_preservation_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="⟨ZZZ⟩ preservation + retention scoring")
    parser.add_argument("--shots", type=int, default=4000)
    parser.add_argument("--sweep-shots", type=int, default=512)
    parser.add_argument("--theta-deg", type=float, default=22.49)
    parser.add_argument("--depth", type=int, default=14)
    parser.add_argument("--relock", type=int, default=5)
    parser.add_argument("--sweep-points", type=int, default=17)
    parser.add_argument("--no-sweep", action="store_true")
    parser.add_argument("--out", default="results/willow_zzz_xy4.json")
    args = parser.parse_args()

    result = run_zzz_preservation_campaign(
        shots=args.shots,
        sweep_shots=args.sweep_shots,
        theta_star_deg=args.theta_deg,
        layers=args.depth,
        relock_interval=args.relock,
        run_theta_sweep=not args.no_sweep,
        sweep_n_points=args.sweep_points,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    r = result["result"]
    arms = r["arms"]
    ra = r.get("retention_analysis", {})
    gaps = r["arm_gaps"]

    print(json.dumps(result, indent=2))
    print("\n--- retention per arm ---")
    for name, arm in arms.items():
        print(
            f"  {name}: ideal={arm['ideal_zzz']:+.4f}  "
            f"noisy={arm['measured_zzz']:+.4f}  R={arm['retention_signed']}"
        )
    print(f"\n|magnitude| θ* vs XY4 delta: {gaps['magnitude_qsd_vs_xy4_delta']:.4f}")
    print(f"post-hoc |θ*−XY4|≥0.05: {gaps['post_hoc_arm_gap_passes_0_05']} (NOT preregistered)")
    if ra.get("status") == "computed":
        print(f"\nR(θ*)={ra['r_at_theta_star']:.4f}  R(XY4)={ra['r_xy4']:.4f}  "
              f"peak@θ={ra['theta_peak_deg']:.1f}°  flat={ra['flat_curve']}")
    print(f"\nVERDICT:    {r['verdict']}")
    print(f"ENDORSABLE: {r['endorsable']}")
    print(f"STAMP:      HOLD (see stamp_status)")
    print(f"NOTES: {r['notes']}")
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
