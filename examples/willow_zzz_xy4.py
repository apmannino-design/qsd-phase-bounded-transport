#!/usr/bin/env python3
"""
⟨ZZZ⟩ preservation line — matched-depth XY4 control gate.

Run XY4 first. If QSD @ θ* survives vs XY4 AND shows angle-specific |ΔZZZ|,
the preservation claim is endorsable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.zzz_preservation import run_zzz_preservation_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="⟨ZZZ⟩ preservation vs XY4 control")
    parser.add_argument("--shots", type=int, default=4000)
    parser.add_argument("--theta-deg", type=float, default=22.49)
    parser.add_argument("--depth", type=int, default=14)
    parser.add_argument("--relock", type=int, default=5)
    parser.add_argument("--gap-threshold", type=float, default=0.5)
    parser.add_argument("--out", default="results/willow_zzz_xy4.json")
    args = parser.parse_args()

    result = run_zzz_preservation_campaign(
        shots=args.shots,
        theta_star_deg=args.theta_deg,
        layers=args.depth,
        relock_interval=args.relock,
        gap_threshold=args.gap_threshold,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    r = result["result"]
    print(json.dumps(result, indent=2))
    print(f"\nVERDICT:    {r['verdict']}")
    print(f"ENDORSABLE: {r['endorsable']}")
    print(f"|ΔZZZ| θ* vs wrong: {r['gaps']['angle_specific_abs']:.3f}")
    print(f"|θ* − XY4|:         {r['gaps']['qsd_vs_xy4_abs']:.3f}")
    print(f"XY4 ⟨ZZZ⟩:          {r['xy4_matched']['zzz']:+.3f}")
    print(f"NOTES: {r['notes']}")
    print(f"Saved: {out}")
    return 0 if r["endorsable"] else 1


if __name__ == "__main__":
    sys.exit(main())
