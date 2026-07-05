#!/usr/bin/env python3
"""Willow line echo benchmark on Cirq (matches willow_pink JSON schema)."""

from __future__ import annotations

import argparse
import json
import sys

from aurora_qsd.quantum.echo_cirq import run_willow_echo_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Willow QSD echo on Cirq")
    parser.add_argument("--shots", type=int, default=4000)
    parser.add_argument("--tau", type=float, default=1000.0, help="Idle time τ (ns)")
    parser.add_argument("--t2", type=float, default=2000.0, help="T2 for idle dephasing (ns)")
    parser.add_argument("--theta-deg", type=float, default=22.5, help="QSD echo angle (deg)")
    parser.add_argument("--pulse", default="phase", choices=["phase", "sunscreen", "hybrid", "relock"])
    parser.add_argument("--statevector", action="store_true", help="Use statevector sim (noiseless idle)")
    args = parser.parse_args()

    import numpy as np

    result = run_willow_echo_benchmark(
        shots=args.shots,
        tau_ns=args.tau,
        t2_ns=args.t2,
        theta=float(np.radians(args.theta_deg)),
        pulse_variant=args.pulse,
        use_density_matrix=not args.statevector,
    )
    print(json.dumps(result.to_dict(), indent=2))
    print(f"\nVERDICT: {result.verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
