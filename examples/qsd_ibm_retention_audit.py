#!/usr/bin/env python3
"""
QSD IBM Hardware Retention Audit + θ Calibration
================================================
July 7, 2026 ideal-referenced ⟨ZZZ⟩ retention benchmark on IBM Quantum.

Workflow (user protocol):
  1. calibrate  — 1-layer θ sweep on hardware (campaign-comparable depth)
  2. wall       — calibrate first, then retention @ 22.28° wall @ 1L
  3. retention  — full retention audit (default 14L; use --layers 1 for D1 depth)

Mac — run ONE command at a time (no # comment lines in zsh):

  python3 examples/qsd_ibm_retention_audit.py calibrate --backend ibm_fez --qubits 20,21,36 --shots 2048

  python3 examples/qsd_ibm_retention_audit.py wall --backend ibm_fez --qubits 20,21,36

  python3 examples/qsd_ibm_retention_audit.py retention --backend ibm_fez --qubits 20,21,36 --theta-deg 22.28 --layers 1
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

from aurora_qsd.core.constants import THETA_STAR_DEG, THETA_STAR_HW_DEG
from aurora_qsd.quantum.ibm_retention_audit import (
    THETA_WALL_DEG,
    run_calibrate_then_wall_retention,
    run_diagnostic_retention,
    run_ibm_retention_benchmark,
    run_ibm_theta_calibration,
    save_retention_result,
    verify_xy4_layer_qiskit,
)
from aurora_qsd.quantum.willow_algorithm import OPTIMAL_RELOCK_INTERVAL, OPTIMAL_SUNSCREEN_LAYERS

RESULTS = Path("results")
KNOWN_COMMANDS = frozenset({"calibrate", "wall", "retention"})


def _parse_qubits(raw: str) -> tuple[int, int, int]:
    qubits = tuple(int(x) for x in raw.split(","))
    if len(qubits) != 3:
        raise SystemExit("Error: exactly 3 qubits required for ⟨ZZZ⟩")
    return qubits


def _add_common_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--backend", default="ibm_fez", help="aer_sim | aer_fez | ibm_fez | ...")
    ap.add_argument("--qubits", default="20,21,36", help="Comma-separated 3 physical qubit indices")
    ap.add_argument("--shots", type=int, default=2048)
    ap.add_argument("--out", default=None, help="Output JSON path")


def _add_retention_args(ap: argparse.ArgumentParser) -> None:
    _add_common_args(ap)
    ap.add_argument("--sweep-shots", type=int, default=1024)
    ap.add_argument("--layers", type=int, default=OPTIMAL_SUNSCREEN_LAYERS)
    ap.add_argument("--relock", type=int, default=OPTIMAL_RELOCK_INTERVAL)
    ap.add_argument("--theta-deg", type=float, default=THETA_STAR_DEG)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--diagnostic", action="store_true")
    ap.add_argument("--diagnostic-lines", type=int, default=3)
    ap.add_argument("--ideals-only", action="store_true")
    ap.add_argument("--md-out", default=None)


def _parse_legacy_retention_args(argv: list[str]) -> argparse.Namespace:
    """Backward-compatible flat CLI (pre-subcommand scripts and run_ibm_retention.sh aer-fez)."""
    parser = argparse.ArgumentParser(
        description="QSD IBM retention audit (legacy flat invocation → retention subcommand)",
    )
    _add_retention_args(parser)
    return parser.parse_args(argv)


def cmd_calibrate(args: argparse.Namespace) -> int:
    qubits = _parse_qubits(args.qubits)
    print("XY4 layer check:", json.dumps(verify_xy4_layer_qiskit(qubits), indent=2), flush=True)

    result = run_ibm_theta_calibration(
        backend_name=args.backend,
        qubits=qubits,
        shots=args.shots,
        theta_wall_deg=args.wall_deg,
        layers=1,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = Path(args.out or RESULTS / f"ibm_calib_{args.backend}_{stamp}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.to_dict(), indent=2) + "\n")

    print(json.dumps(result.to_dict(), indent=2))
    print(f"\nPeak θ={result.peak_theta_deg:.2f}°  ZZZ={result.peak_zzz:+.3f}")
    print(f"Wall θ={result.wall_theta_deg:.2f}°  ZZZ={result.wall_zzz:+.3f}  ideal={result.wall_ideal_zzz:+.3f}")
    print(f"Saved: {out_path}")
    return 0


def cmd_wall(args: argparse.Namespace) -> int:
    qubits = _parse_qubits(args.qubits)
    print("XY4 layer check:", json.dumps(verify_xy4_layer_qiskit(qubits), indent=2), flush=True)

    payload = run_calibrate_then_wall_retention(
        backend_name=args.backend,
        qubits=qubits,
        theta_wall_deg=args.wall_deg,
        calib_shots=args.calib_shots,
        retention_shots=args.retention_shots,
        retention_layers=args.layers,
        run_retention_sweep=args.sweep,
    )
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = Path(args.out or RESULTS / f"ibm_wall_{args.backend}_{stamp}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")

    ret = payload["retention"]
    print(json.dumps(payload, indent=2))
    print(f"\nCALIB peak: θ={payload['calibration']['peak_theta_deg']:.2f}°")
    print(f"WALL retention @ {args.wall_deg}°: {ret['verdict']}  {ret['notes']}")
    print(f"Saved: {out_path}")
    return 0


def cmd_retention(args: argparse.Namespace) -> int:
    qubits = _parse_qubits(args.qubits)
    print("XY4 layer check:", json.dumps(verify_xy4_layer_qiskit(qubits), indent=2), flush=True)

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
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        out_path = Path(args.out or RESULTS / f"ibm_retention_diag_{args.backend}_{stamp}.json")
        out_path.write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        print(f"\nSaved: {out_path}")
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
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = Path(args.out or RESULTS / f"ibm_retention_{args.backend}_{stamp}.json")
    md_path = json_path.with_suffix(".md")
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
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] not in KNOWN_COMMANDS:
        return int(cmd_retention(_parse_legacy_retention_args(argv)))

    parser = argparse.ArgumentParser(description="QSD IBM retention + θ calibration")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cal = sub.add_parser("calibrate", help="1-layer θ calibration sweep (run this first)")
    _add_common_args(p_cal)
    p_cal.add_argument("--wall-deg", type=float, default=THETA_WALL_DEG, help="wall angle to highlight (default 22.28)")
    p_cal.set_defaults(func=cmd_calibrate)

    p_wall = sub.add_parser("wall", help="calibrate then retention @ wall angle (22.28° default)")
    _add_common_args(p_wall)
    p_wall.add_argument("--wall-deg", type=float, default=THETA_WALL_DEG)
    p_wall.add_argument("--calib-shots", type=int, default=2048)
    p_wall.add_argument("--retention-shots", type=int, default=4096)
    p_wall.add_argument("--layers", type=int, default=1, help="retention depth (default 1 = campaign D1)")
    p_wall.add_argument("--sweep", action="store_true", help="θ-sweep during retention phase")
    p_wall.set_defaults(func=cmd_wall)

    p_ret = sub.add_parser("retention", help="retention audit (use --layers 1 for campaign depth)")
    _add_retention_args(p_ret)
    p_ret.set_defaults(func=cmd_retention)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
