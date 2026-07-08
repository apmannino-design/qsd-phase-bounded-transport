#!/usr/bin/env python3
"""
Standalone retention audit — July 7, 2026 protocol.

Re-runs the ⟨ZZZ⟩ preservation / repaired XY4 control experiment with:
  - noiseless ideal ⟨ZZZ⟩ per arm (statevector + density-matrix check)
  - retention R = noisy / ideal
  - QSD θ-sweep for R(θ) curve

Verdict ladder (simulation does not endorse):
  NO_TARGET_SIGNAL → COHERENT_ARTIFACT → NO_PROTECTION_ADVANTAGE → PROTECTION_CANDIDATE

Usage:
  python3 -m aurora_qsd.quantum.retention_audit
  python3 -m aurora_qsd.quantum.retention_audit --shots 4000 --sweep-shots 1000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.zzz_preservation import (
    OPTIMAL_THETA_DEG,
    ideal_zzz_density_matrix,
    ideal_zzz_from_circuit,
    run_retention_audit_benchmark,
    verify_xy4_layer,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="July 7 retention audit (repaired XY4)")
    parser.add_argument("--shots", type=int, default=4000)
    parser.add_argument("--sweep-shots", type=int, default=1000)
    parser.add_argument("--theta-deg", type=float, default=OPTIMAL_THETA_DEG)
    parser.add_argument("--out", default="results/willow_retention_audit.json")
    parser.add_argument("--ideals-only", action="store_true", help="Skip noisy QVM (fast)")
    args = parser.parse_args(argv)

    xy4_check = verify_xy4_layer()
    print("XY4 layer check:", json.dumps(xy4_check, indent=2))

    result = run_retention_audit_benchmark(
        shots=args.shots,
        sweep_shots=args.sweep_shots,
        theta_star_deg=args.theta_deg,
        ideals_only=args.ideals_only,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    r = result["result"]
    print(json.dumps(result, indent=2))
    print("\n--- arms ---")
    for name, arm in r["arms"].items():
        print(
            f"  {name}: ideal={arm['ideal_zzz']:+.4f}  "
            f"noisy={arm.get('measured_zzz', 'n/a')}  R={arm.get('retention_signed')}"
        )
    print(f"\nVERDICT: {r['verdict']}  endorsable={r['endorsable']}")
    print(f"NOTES: {r['notes']}")
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
