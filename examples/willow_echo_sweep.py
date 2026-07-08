#!/usr/bin/env python3
"""Sweep θ, τ, and QSD pulse variants before running Willow hardware shots."""

from __future__ import annotations

import argparse
import json
import sys

from aurora_qsd.quantum.echo_sweep import (
    run_willow_echo_sweep,
    sweep_pulse_variants,
    sweep_tau,
    sweep_theta,
)


def _print_table(title: str, rows: list[dict], columns: tuple[str, ...]) -> None:
    print(f"\n{title}")
    print("  " + " | ".join(f"{c:>14}" for c in columns))
    print("  " + "-" * (16 * len(columns)))
    for row in rows:
        print("  " + " | ".join(f"{row[c]:>14}" for c in columns))


def main() -> int:
    parser = argparse.ArgumentParser(description="Willow QSD echo parameter sweep (simulator)")
    parser.add_argument("--shots", type=int, default=1000, help="Shots per circuit")
    parser.add_argument("--tau", type=float, default=1000.0, help="Baseline τ (ns)")
    parser.add_argument("--t2", type=float, default=2000.0, help="T2 for idle noise (ns)")
    parser.add_argument("--span-deg", type=float, default=20.0, help="θ sweep half-width (deg)")
    parser.add_argument("--theta-only", action="store_true", help="Only sweep θ")
    parser.add_argument("--tau-only", action="store_true", help="Only sweep τ")
    parser.add_argument("--pulse-only", action="store_true", help="Only sweep pulse variants")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()

    if args.theta_only:
        points = sweep_theta(args.shots, args.tau, args.t2, args.span_deg)
        rows = [p.__dict__ for p in points]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            _print_table("θ SWEEP (deg)", rows, ("label", "f_qsd", "f_x", "f_none", "delta_qsd_x"))
        return 0

    if args.tau_only:
        points = sweep_tau(args.shots, t2_ns=args.t2)
        rows = [p.__dict__ for p in points]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            _print_table("τ SWEEP", rows, ("label", "f_qsd", "f_x", "f_none", "delta_qsd_x"))
        return 0

    if args.pulse_only:
        rows = sweep_pulse_variants(args.shots, args.tau, t2_ns=args.t2)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            _print_table("PULSE VARIANTS", rows, ("pulse", "f_qsd", "f_x", "f_none", "delta_qsd_x"))
        return 0

    result = run_willow_echo_sweep(
        shots=args.shots,
        tau_ns=args.tau,
        t2_ns=args.t2,
        span_deg=args.span_deg,
    )

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
        return 0

    print("=" * 60)
    print(" WILLOW QSD ECHO SWEEP (simulator)")
    print(f" shots={args.shots}  τ₀={args.tau} ns  T2={args.t2} ns")
    print("=" * 60)

    _print_table(
        "θ SWEEP",
        [p.__dict__ for p in result.theta_sweep],
        ("label", "f_qsd", "f_x", "f_none", "delta_qsd_x"),
    )
    _print_table(
        "τ SWEEP (at best θ)",
        [p.__dict__ for p in result.tau_sweep],
        ("label", "f_qsd", "f_x", "f_none", "delta_qsd_x"),
    )
    _print_table(
        "PULSE VARIANTS (at best θ, τ)",
        result.pulse_sweep,
        ("pulse", "f_qsd", "f_x", "f_none", "delta_qsd_x"),
    )

    print("\nBEST CONFIG")
    print(f"  pulse : {result.best_pulse}")
    print(f"  θ     : {result.best_theta_deg:.1f}°")
    print(f"  τ     : {int(result.best_tau_ns)} ns")
    print(f"  F_qsd : {result.best_f_qsd:.4f}")
    print(f"\nRECOMMENDATION:\n  {result.recommendation}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
