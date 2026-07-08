#!/usr/bin/env python3
"""How QSD is utilized: ZZZ engine + idle guard between algorithm blocks."""

from __future__ import annotations

import argparse
import json
import sys

from aurora_qsd.quantum.willow_algorithm import run_algorithm_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description="Willow QSD utilization benchmarks")
    parser.add_argument("--shots", type=int, default=500)
    parser.add_argument("--pattern", default="all", choices=["all", "zzz_engine", "idle_guard"])
    parser.add_argument("--theta-deg", type=float, default=22.49)
    args = parser.parse_args()

    results = run_algorithm_benchmark(
        shots=args.shots,
        pattern=args.pattern,
        theta_deg=args.theta_deg,
    )

    print(json.dumps(results, indent=2))
    for name, r in results.items():
        print(f"\n{name}: {r['verdict']} — {r['notes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
