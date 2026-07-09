#!/usr/bin/env python3
"""Willow line echo benchmark — correct QSD echo test (not ZZZ depth)."""

import json
import sys

from aurora_qsd.quantum.echo_protocol import run_willow_echo_benchmark


def main() -> int:
    result = run_willow_echo_benchmark(shots=4000, tau_ns=1000, n_random=10, seed=42)
    print(json.dumps(result.to_dict(), indent=2))
    print(f"\nVERDICT: {result.verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
