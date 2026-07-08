#!/usr/bin/env python3
"""
QSD IBM Hardware Retention Audit + Diagnostic Sweep
===================================================
July 7, 2026 ideal-referenced ⟨ZZZ⟩ retention benchmark on IBM Quantum.

Exact QSD body from fez_cells; repaired XY4 matched-depth control; Aer ideal
cross-check; preregistered verdict ladder; optional θ-sweep and multi-line
diagnostic mode.

Usage:
  # Aer plumbing (no IBM token)
  python3 examples/qsd_ibm_retention_audit.py --backend aer_sim --shots 2048 --ideals-only

  # Aer noisy Fez model
  python3 examples/qsd_ibm_retention_audit.py --backend aer_fez --shots 2048 --layers 14 --sweep

  # Real hardware
  python3 examples/qsd_ibm_retention_audit.py --backend ibm_fez --qubits 0,1,2 --shots 4096 --sweep

  # Multi-line diagnostic
  python3 examples/qsd_ibm_retention_audit.py --backend ibm_fez --diagnostic --shots 2048
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow running without `pip install -e .` when executed from repo clone
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from aurora_qsd.core.constants import THETA_STAR_DEG, THETA_STAR_HW_DEG
from aurora_qsd.quantum.ibm_retention_audit import (
    run_diagnostic_retention,
    run_ibm_retention_benchmark,
    save_retention_result,
    verify_xy4_layer_qiskit,
)
from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_SUNSCREEN_LAYERS

RESULTS = Path("results")


def main() -> int:
    parser = argparse.ArgumentParser(description="QSD IBM retention audit (July 7 protocol)")
    parser.add_argument("--backend", default="aer_sim", help="aer_sim | aer_fez | ibm_fez | ...")
    parser.add_argument("--qubits", default="0,1,2", help="Comma-separated 3 physical qubit indices")
    parser.add_argument("--shots", type=int, default=4096)
    parser.add_argument("--sweep-shots", type=int, default=1024)
    parser.add_argument("--layers", type=int, default=OPTIMAL_SUNSCREEN_LAYERS)
    parser.add_argument("--relock", type=int, default=OPTIMAL_RELOCK_INTERVAL)
    parser.add_argument(
        "--theta-deg",
        type=float,
        default=THETA_STAR_DEG,
        help=f"design θ* (default {THETA_STAR_DEG}; IBM HW anchor {THETA_STAR_HW_DEG})",
    )
    parser.add_argument("--sweep", action="store_true", help="Run R(θ) sweep")
    parser.add_argument("--diagnostic", action="store_true", help="Multi-line champion-cell probe")
    parser.add_argument("--diagnostic-lines", type=int, default=3)
    parser.add_argument("--ideals-only", action="store_true", help="Skip noisy runs (fast ideal check)")
    parser.add_argument("--out", default=None, help="Output JSON path")
    parser.add_argument("--md-out", default=None, help="Optional Markdown RESULTS path")
    args = parser.parse_args()

    qubits = tuple(int(x) for x in args.qubits.split(","))
    if len(qubits) != 3:
        print("Error: exactly 3 qubits required for ⟨ZZZ⟩", file=sys.stderr)
        return 1

    xy4_check = verify_xy4_layer_qiskit(qubits)
    print("XY4 layer check:", json.dumps(xy4_check, indent=2), flush=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = Path(args.out or RESULTS / f"ibm_retention_{args.backend}_{stamp}.json")
    md_path = Path(args.md_out) if args.md_out else json_path.with_suffix(".md")

    if args.diagnostic:
        payload = run_diagnostic_retention(
            backend_name=args.backend,
            n_lines=args.diagnostic_lines,
            shots=args.shots,
            sweep_shots=args.sweep_shots,
            run_sweep=args.sweep,
            theta_star_deg=args.theta_deg,
            layers=args.layers,
            relock_interval=args.relock,
            ideals_only=args.ideals_only,
        )
        json_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        print(f"\nSaved: {json_path}")
        print(f"SUMMARY VERDICT: {payload['summary_verdict']}  endorsable=False")
        return 0

    result = run_ibm_retention_benchmark(
        backend_name=args.backend,
        qubits=qubits,
        theta_star_deg=args.theta_deg,
        layers=args.layers,
        relock_interval=args.relock,
        shots=args.shots,
        sweep_shots=args.sweep_shots,
        run_sweep=args.sweep,
        ideals_only=args.ideals_only,
    )

    save_retention_result(result, json_path, md_path)

    d = result.to_dict()
    print(json.dumps(d, indent=2))
    print("\n--- arms ---")
    for name, arm in d["arms"].items():
        print(
            f"  {name}: ideal={arm['ideal_zzz']:+.4f}  "
            f"noisy={arm.get('measured_zzz', 'n/a')}  R={arm.get('retention_signed')}"
        )
    print(f"\nVERDICT: {result.verdict}  endorsable={result.endorsable}")
    print(f"NOTES: {result.notes}")
    print(f"Saved: {json_path}")
    if md_path.exists():
        print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
