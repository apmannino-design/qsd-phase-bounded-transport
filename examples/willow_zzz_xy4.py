#!/usr/bin/env python3
"""⟨ZZZ⟩ preservation — repaired XY4 + retention audit protocol."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.zzz_preservation import run_zzz_preservation_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="⟨ZZZ⟩ preservation + retention scoring")
    parser.add_argument("--shots", type=int, default=4000)
    parser.add_argument("--sweep-shots", type=int, default=1000)
    parser.add_argument("--theta-deg", type=float, default=22.49)
    parser.add_argument("--depth", type=int, default=14)
    parser.add_argument("--relock", type=int, default=5)
    parser.add_argument("--no-sweep", action="store_true")
    parser.add_argument("--ideals-only", action="store_true")
    parser.add_argument("--out", default="results/willow_zzz_xy4.json")
    args = parser.parse_args()

    result = run_zzz_preservation_campaign(
        shots=args.shots,
        sweep_shots=args.sweep_shots,
        theta_star_deg=args.theta_deg,
        layers=args.depth,
        relock_interval=args.relock,
        run_theta_sweep=not args.no_sweep,
        ideals_only=args.ideals_only,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    r = result["result"]
    print(json.dumps(result, indent=2))
    print(f"\nVERDICT: {r['verdict']}  endorsable={r['endorsable']}")
    print(f"NOTES: {r['notes']}")
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
