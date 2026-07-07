#!/usr/bin/env python3
"""
Apocalypse-max stress test on IBM FakeFez simulator.

Maximum noise, maximum depth (1241L), maximum ZZZ cell count,
Aurora minimal-thermo re-lock every 3 layers.

Usage:
  python3 examples/fez_apocalypse_max.py
  python3 examples/fez_apocalypse_max.py --shots 8192 --cells 43
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aurora_qsd.quantum.extreme_stress import run_apocalypse_max, save_results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="FakeFez apocalypse-max QSD stress test")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--cells", type=int, default=43, help="Parallel ZZZ cells (ibm_fez used 43)")
    parser.add_argument("--lattice-qubits", type=int, default=7, help="Lattice qubits (7=safe; 29=heavy)")
    parser.add_argument("--depths", type=str, default="32,140,311,1241", help="Comma-separated depths")
    parser.add_argument("--out", type=str, default="results")
    args = parser.parse_args(argv)

    depths = [int(x) for x in args.depths.split(",")]

    print("Starting apocalypse-max stress (this may take several minutes)...")
    result = run_apocalypse_max(
        shots=args.shots,
        max_cells=args.cells,
        lattice_qubits=args.lattice_qubits,
        depths=depths,
    )

    out_dir = Path(args.out)
    save_results(result, out_dir)
    print(result.summary())
    print(f"\nResults saved to {out_dir}/fez_apocalypse_summary.txt")
    print(f"              and {out_dir}/fez_apocalypse_depth_table.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
