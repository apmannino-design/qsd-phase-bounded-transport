#!/usr/bin/env python3
"""3-qubit Ising energy benchmark — ΔE vs exact ground state (usable metric)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from aurora_qsd.quantum.willow_ising_energy import run_usable_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Usable QSD benchmarks (Ising + ZZZ task)")
    parser.add_argument("--shots", type=int, default=800)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--J", type=float, default=1.2)
    parser.add_argument("--h", type=float, default=0.1)
    parser.add_argument("--out", default="results/willow_ising_energy.json")
    args = parser.parse_args()

    result = run_usable_benchmark(
        shots=args.shots,
        trotter_steps=args.steps,
        J=args.J,
        h=args.h,
    )

    out = Path(args.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2))

    print(json.dumps(result, indent=2))
    print(f"\nIsing Trotter: {result['ising_trotter']['verdict']} — bare |ΔE|={result['ising_trotter']['bare']['error_vs_ground']:.3f}")
    print(f"ZZZ task:      {result['zzz_hamiltonian']['verdict']} — |ΔZZZ|={result['zzz_hamiltonian']['abs_gap']:.3f}")
    print(f"\n{result['guidance']}")
    print(f"Saved:   {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
