#!/usr/bin/env python3
"""
Casimir Hamiltonian benchmark — plates, gap mode, QSD binding on Willow.

  H = -J_p(Z0Z1+Z1Z2) - J_c Z0Z2 - g Z0Z1Z2 - h X1

Compares interior (cavity) vs boundary (plate-edge) lines.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.casimir_hamiltonian import CasimirHamiltonian, run_casimir_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description="Casimir Hamiltonian + QSD on Willow")
    parser.add_argument("--shots", type=int, default=800)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--dt", type=float, default=0.2)
    parser.add_argument("--J-plate", type=float, default=1.0)
    parser.add_argument("--J-cas", type=float, default=0.5)
    parser.add_argument("--g-zzz", type=float, default=0.8)
    parser.add_argument("--h-gap", type=float, default=0.15)
    parser.add_argument("--theta-deg", type=float, default=22.49)
    parser.add_argument("--pattern", choices=("all", "depth", "trotter"), default="depth")
    parser.add_argument("--out", default="results/willow_casimir.json")
    args = parser.parse_args()

    ham = CasimirHamiltonian(
        J_plate=args.J_plate,
        J_cas=args.J_cas,
        g_zzz=args.g_zzz,
        h_gap=args.h_gap,
    )

    result = run_casimir_campaign(
        shots=args.shots,
        trotter_steps=args.steps,
        dt=args.dt,
        ham=ham,
        theta_deg=args.theta_deg,
        pattern=args.pattern,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    s = result["summary"]
    print(json.dumps(result, indent=2))
    if s.get("interior_depth_gap") is not None:
        print(f"\nDepth binding wins: {s['depth_binding_wins']}/2")
        print(
            f"Interior |ΔZZZ|: {s['interior_depth_gap']:.3f}  "
            f"Boundary: {s['boundary_depth_gap']:.3f}"
        )
    if s.get("interior_trotter_verdict"):
        print(
            f"Trotter: interior={s['interior_trotter_verdict']}  "
            f"boundary={s['boundary_trotter_verdict']}"
        )
    print(f"\n{result['guidance']}")
    print(f"Saved: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
