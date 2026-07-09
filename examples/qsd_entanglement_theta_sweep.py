#!/usr/bin/env python3
"""
Entanglement θ sweep — G(El) across corridor 22.5° → 90°.

Willow sim:
  python3 examples/qsd_entanglement_theta_sweep.py --backend willow --quick

IBM noisy Aer:
  python3 examples/qsd_entanglement_theta_sweep.py --backend aer_fez --el 2

IBM hardware:
  python3 examples/qsd_entanglement_theta_sweep.py --backend ibm_fez --qubits 20,21,36 --el 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from aurora_qsd.quantum.entanglement_theta_sweep import (
    DEFAULT_THETA_SWEEP_DEG,
    generate_theta_sweep_deg,
    run_ibm_entanglement_theta_sweep,
    run_willow_entanglement_theta_sweep,
)

RESULTS = Path("results")


def _parse_thetas(raw: str | None, n_steps: int) -> list[float]:
    if raw:
        return [float(x.strip()) for x in raw.split(",") if x.strip()]
    if n_steps != len(DEFAULT_THETA_SWEEP_DEG):
        return generate_theta_sweep_deg(22.5, 90.0, n_steps)
    return list(DEFAULT_THETA_SWEEP_DEG)


def main() -> int:
    ap = argparse.ArgumentParser(description="Entanglement G(θ) sweep 22.5°–90°")
    ap.add_argument("--backend", default="willow", help="willow | aer_fez | ibm_fez")
    ap.add_argument("--qubits", default="20,21,36")
    ap.add_argument("--el", type=int, default=2, help="entanglement layers (2=galaxy probe)")
    ap.add_argument("--shots", type=int, default=2048)
    ap.add_argument("--thetas", default=None, help="comma angles, default corridor anchors")
    ap.add_argument("--n-steps", type=int, default=len(DEFAULT_THETA_SWEEP_DEG))
    ap.add_argument("--quick", action="store_true", help="5 angles, 512 shots")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    shots = 512 if args.quick else args.shots
    thetas = _parse_thetas(args.thetas, 5 if args.quick else args.n_steps)
    if args.quick and args.thetas is None:
        thetas = [22.5, 27.61, 45.0, 67.5, 90.0]

    print("=" * 60)
    print(f"Entanglement θ sweep  El={args.el}  shots={shots}")
    print(f"θ: {thetas}")
    print("=" * 60)

    if args.backend == "willow":
        result = run_willow_entanglement_theta_sweep(shots=shots, el=args.el, thetas_deg=thetas)
    else:
        qubits = tuple(int(x) for x in args.qubits.split(","))
        if len(qubits) != 3:
            print("Error: need 3 qubits", file=sys.stderr)
            return 1
        result = run_ibm_entanglement_theta_sweep(
            shots=shots,
            el=args.el,
            thetas_deg=thetas,
            backend_name=args.backend,
            physical_qubits=qubits,
            use_hardware=(args.backend not in ("aer_fez", "aer_sim", "aer")),
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = Path(args.out or RESULTS / f"entangle_theta_{args.backend}_{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), indent=2) + "\n")

    print("\n--- SUMMARY ---")
    print(f"Verdict: {result.verdict}")
    print(f"G peak: {result.g_peak:.3f} @ θ={result.theta_peak_deg:.2f}°")
    print(f"Interior peak: {result.interior_peak}")
    print(f"Notes: {result.notes}")
    print(f"Saved: {out}")
    return 0 if result.verdict != "NULL" else 1


if __name__ == "__main__":
    sys.exit(main())
